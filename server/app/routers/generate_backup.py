import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Project, TestCase, TestPage, get_db
from app.schemas.schemas import GenerateRequest, MCPGenerateRequest, TestCaseOut, TestPageOut
from app.services.llm_service import llm_chat
from app.services.analyzer import analyze_project
from app.services.component_analyzer import analyze_components
from app.services.mcp_explorer import MCPPageExplorer
from app.services.mcp_rules import MCPRulesLoader
from app.services.mcp_log_service import mcp_log_service
from app.services.playwright_skills import PlaywrightCLISkills
from app.core.config import settings
from app.core.websocket import ws_manager

router = APIRouter(prefix="/api/generate", tags=["generate"])

logger = logging.getLogger(__name__)


@router.get("/components/{project_id}", response_model=dict)
async def get_components(project_id: str, db: AsyncSession = Depends(get_db)):
    """
    获取项目的组件列表（通过静态代码分析）
    
    返回:
    - components: 所有组件列表
    - page_components: 页面组件（路由入口）
    - common_components: 普通组件
    """
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if not project.repo_path:
        raise HTTPException(400, "请先拉取项目代码")

    try:
        # 静态分析
        logger.info(f"开始静态组件分析: {project.repo_path}")
        components_info = await analyze_components(project.repo_path)
        logger.info(f"组件分析完成，发现 {len(components_info.get('components', []))} 个组件")
        
        return {
            "components": components_info.get("components", []),
            "page_components": components_info.get("page_components", []),
            "common_components": components_info.get("common_components", []),
            "framework": components_info.get("framework", "未知"),
            "entry_points": components_info.get("entry_points", [])
        }
    except Exception as e:
        logger.error(f"组件分析失败: {e}", exc_info=True)
        raise HTTPException(500, f"组件分析失败: {str(e)}")


@router.post("", response_model=list[TestCaseOut])
async def generate_testcases(data: GenerateRequest, db: AsyncSession = Depends(get_db)):
    """分析项目代码，自动生成测试用例。"""
    project = await db.get(Project, data.project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if not project.repo_path:
        raise HTTPException(400, "请先拉取项目代码")

    # Step 1: Analyze the project source code
    analysis = await analyze_project(project.repo_path)

    # Step 2: Ask LLM to generate test cases based on analysis
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个资深 QA 工程师和 Playwright Python 测试专家。\n"
                "根据提供的 Web 项目代码分析结果，生成一组全面的端到端测试用例。\n\n"
                "要求：\n"
                "1. 每个用例包含: title(标题), description(自然语言描述), script_content(完整的 Python 测试代码), group_name(分组名)\n"
                "2. 测试代码使用 pytest + playwright sync_api\n"
                "3. 测试函数参数为 page: Page\n"
                "4. 使用 expect() 做断言\n"
                "5. 代码中用中文注释说明每个步骤\n"
                f"6. 被测站点 base_url: {project.base_url}\n"
                "7. 覆盖主要页面和核心业务流程\n"
                "8. 返回 JSON 格式: {\"test_cases\": [{\"title\": \"\", \"description\": \"\", \"script_content\": \"\", \"group_name\": \"\"}]}"
            ),
        },
        {
            "role": "user",
            "content": f"项目代码分析结果:\n\n{analysis}",
        },
    ]

    raw = await llm_chat(messages, temperature=0.3, max_tokens=8192)

    # Parse LLM response
    try:
        content = raw.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(content)
        cases_data = result.get("test_cases", [])
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(500, f"LLM 返回格式错误")

    # Step 3: Save to database
    created_cases = []
    for idx, case_data in enumerate(cases_data):
        tc = TestCase(
            project_id=project.id,
            title=case_data.get("title", f"测试用例 {idx + 1}"),
            description=case_data.get("description", ""),
            script_content=case_data.get("script_content", ""),
            group_name=case_data.get("group_name", "default"),
        )
        db.add(tc)
        created_cases.append(tc)

    await db.commit()
    for tc in created_cases:
        await db.refresh(tc)

    return created_cases


@router.post("/mcp/discover", response_model=dict)
async def mcp_discover_pages(data: MCPGenerateRequest, db: AsyncSession = Depends(get_db)):
    """
    MCP 页面嗅探 - 通过LLM分析每个页面的组件引用关系
    
    流程：
    1. 静态分析发现组件（输出组件清单）
    2. 逐页面LLM分析（独立会话，防遗漏）
    3. 将页面写入页面树
    4. 通过WebSocket实时推送日志
    """
    print(f"[MCP-API] mcp_discover_pages 被调用, project_id={data.project_id}", flush=True)
    
    project = await db.get(Project, data.project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if not project.repo_path:
        raise HTTPException(400, "请先拉取项目代码")
    if not project.base_url:
        raise HTTPException(400, "请先配置项目 base_url")

    # 获取project_id用于WebSocket频道
    project_id = data.project_id
    
    async def send_log(level: str, message: str, log_data: dict = None):
        """异步发送WebSocket日志"""
        log_entry = {
            "type": "log",
            "level": level,
            "message": message,
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            "data": log_data
        }
        # 发送到对应的WebSocket频道
        print(f"[MCP-LOG] Broadcasting to mcp_{project_id}: {message[:50]}...", flush=True)
        await ws_manager.broadcast(log_entry, channel=f"mcp_{project_id}")
        # 同时记录到日志服务
        mcp_log_service.log(project_id, level, message, log_data)

    try:
        # 开始会话
        await send_log("info", f"🚀 开始MCP页面分析，项目: {project.name}")
        await send_log("info", f"📂 项目路径: {project.repo_path}")
        await send_log("info", f"🌐 Base URL: {project.base_url}")
        
        # Step 1: 静态组件分析
        await send_log("info", f"📊 Step 1/3: 开始静态组件分析...")
        components_info = await analyze_components(project.repo_path)
        
        component_count = len(components_info.get('components', []))
        page_count = len(components_info.get('page_components', []))
        common_count = len(components_info.get('common_components', []))
        
        await send_log("success", 
            f"✓ 静态分析完成: 共 {component_count} 个组件 "
            f"({page_count} 个页面组件, {common_count} 个普通组件)",
            {
                "framework": components_info.get('framework', '未知'),
                "entry_points": components_info.get('entry_points', [])
            }
        )

        # Step 2: MCP 页面分析（使用LLM逐页面分析）
        await send_log("info", f"🤖 Step 2/3: 开始MCP页面分析（LLM）...")
        await send_log("info", f"📄 共 {len(components_info.get('page_components', []))} 个页面待分析")
        
        # 创建WebSocket日志回调函数（必须是async函数）
        async def ws_log(level: str, message: str, data=None):
            log_entry = {
                "type": "log",
                "level": level,
                "message": message,
                "timestamp": __import__('datetime').datetime.now().isoformat(),
                "data": data
            }
            await ws_manager.broadcast(log_entry, channel=f"mcp_{project_id}")
            mcp_log_service.log(project_id, level, message, data)
        
        explorer = MCPPageExplorer(
            repo_path=project.repo_path,
            project_id=project_id,
            log_callback=ws_log  # 传递异步日志回调
        )
        
        # 加载全局规则
        rules_loader = MCPRulesLoader(project_id=data.project_id)
        global_rules = rules_loader.load_global_rules() or ""
        if global_rules:
            await send_log("info", "📋 已加载全局规则")
        
        discovered_pages = await explorer.discover_pages(
            base_url=project.base_url,
            entry_points=components_info.get("entry_points", ["/"]),
            components_info=components_info,
            global_rules=global_rules,
            concurrent=False  # 串行分析，便于调试
        )
        
        await send_log("success", f"✓ MCP分析完成，发现 {len(discovered_pages)} 个页面")

        # Step 2.5: Playwright CLI Skills验证（混合模式）
        await send_log("info", f"🎭 Step 2.5/4: Playwright CLI Skills验证...")
        
        pw_skills = PlaywrightCLISkills(project_id=data.project_id)
        
        # 对每个页面执行Skills
        verified_count = 0
        for page_info in discovered_pages:
            route = page_info.get("route", "")
            if not route.startswith("/"):
                route = "/" + route
            
            page_url = f"{project.base_url.rstrip('/')}{route}"
            page_name = page_info.get("title", route)
            
            await send_log("info", f"🔍 分析页面: {page_name} ({route})")
            
            # 使用asyncio.to_thread在线程池中执行同步命令
            import asyncio
            
            # Skill 1: 截图
            await send_log("debug", f"📸 Skill 1: 页面快照")
            screenshot_result = await asyncio.to_thread(
                pw_skills.take_screenshot,
                url=page_url,
                full_page=True,
                timeout=15000
            )
            
            if screenshot_result.get("success"):
                page_info["screenshot"] = screenshot_result.get("screenshot_base64", "")
                await send_log("success", f"  ✓ 截图成功 ({screenshot_result.get('dimensions', {}).get('width', 0)}x{screenshot_result.get('dimensions', {}).get('height', 0)})")
            else:
                await send_log("warning", f"  ⚠ 截图失败: {screenshot_result.get('error', '')}")
            
            # Skill 4: DOM树提取
            await send_log("debug", f"🌳 Skill 2: DOM树提取")
            dom_result = await asyncio.to_thread(
                pw_skills.extract_dom_tree,
                url=page_url,
                max_depth=4,
                timeout=15000
            )
            
            if dom_result.get("success"):
                total_elements = dom_result.get("total_elements", 0)
                await send_log("success", f"  ✓ DOM树提取成功 (共 {total_elements} 个元素)")
                
                # 从DOM树中提取组件信息（辅助LLM分析）
                page_info["dom_tree"] = dom_result.get("dom_tree", {})
                page_info["total_elements"] = total_elements
            else:
                await send_log("warning", f"  ⚠ DOM提取失败: {dom_result.get('error', '')}")
            
            # Skill 5: 无障碍分析
            await send_log("debug", f"♿ Skill 3: 无障碍分析")
            a11y_result = await asyncio.to_thread(
                pw_skills.analyze_accessibility,
                url=page_url,
                timeout=15000
            )
            
            if a11y_result.get("success"):
                score = a11y_result.get("accessibility_score", 100)
                issues = a11y_result.get("total_issues", 0)
                await send_log("success", f"  ✓ 无障碍评分: {score}/100 ({issues} 个问题)")
                page_info["accessibility_score"] = score
                page_info["accessibility_issues"] = a11y_result.get("issues", [])
            
            verified_count += 1
            await send_log("info", f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        await send_log("success", f"✓ Playwright Skills验证完成: {verified_count}/{len(discovered_pages)} 个页面")

        # Step 3: 将页面写入页面树数据库
        await send_log("info", f"💾 Step 3/3: 写入页面树数据库...")
        created_pages = []
        
        for page_info in discovered_pages:
            route = page_info["route"]
            
            # 检查页面是否已存在
            existing_page = await db.execute(
                select(TestPage).where(
                    TestPage.project_id == data.project_id,
                    TestPage.full_path == route
                )
            )
            existing_page = existing_page.scalar_one_or_none()
            
            if existing_page:
                # 更新现有页面
                existing_page.name = page_info.get("title", route)
                
                # 合并静态和动态分析的组件
                static_components = page_info.get("detected_components", [])
                verified_components = page_info.get("verified_components", [])
                
                # 优先使用Playwright验证的组件，如果没有则使用静态分析结果
                final_components = verified_components if verified_components else static_components
                
                existing_page.component_name = json.dumps(final_components, ensure_ascii=False)
                existing_page.description = page_info.get("description", "")
                created_pages.append(existing_page)
                
                comp_count = len(final_components)
                await send_log("info", f"📝 更新页面: {route} ({comp_count} 个组件)")
            else:
                # 创建新页面
                static_components = page_info.get("detected_components", [])
                verified_components = page_info.get("verified_components", [])
                final_components = verified_components if verified_components else static_components
                
                test_page = TestPage(
                    project_id=data.project_id,
                    name=page_info.get("title", route),
                    path=route,
                    full_path=route,
                    is_leaf=True,
                    component_name=json.dumps(final_components, ensure_ascii=False),
                    description=page_info.get("description", "")
                )
                db.add(test_page)
                created_pages.append(test_page)
                
                comp_count = len(final_components)
                await send_log("success", f"✨ 新增页面: {route} ({comp_count} 个组件)")
        
        await db.commit()
        for page in created_pages:
            await db.refresh(page)
        
        await send_log("success", f"🎉 MCP页面分析完成！共 {len(created_pages)} 个页面已保存",
            {
                "total_pages": len(created_pages),
                "total_components": component_count
            }
        )
        
        return {
            "message": f"MCP 嗅探完成，发现 {len(discovered_pages)} 个页面",
            "page_count": len(discovered_pages),
            "pages": [{
                "id": p.id,
                "route": p.full_path,
                "name": p.name,
                "components": json.loads(p.component_name) if p.component_name else []
            } for p in created_pages]
        }
    
    except HTTPException:
        await send_log("error", "MCP分析失败: 项目不存在或配置不完整")
        raise
    except Exception as e:
        logger.error(f"MCP 页面嗅探失败: {e}", exc_info=True)
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        raise HTTPException(500, f"MCP 页面嗅探失败: {str(e)}")
    finally:
        # 确保浏览器关闭
        try:
            await explorer.cleanup()
        except Exception as cleanup_error:
            logger.warning(f"清理浏览器时出错: {cleanup_error}")


@router.post("/mcp/{page_id}/generate", response_model=list[TestCaseOut])
async def mcp_generate_page_cases(page_id: str, db: AsyncSession = Depends(get_db)):
    """
    为指定页面生成测试用例
    
    参数:
        page_id: 页面 ID
    """
    # 获取页面信息
    page = await db.get(TestPage, page_id)
    if not page:
        raise HTTPException(404, "页面不存在")
    
    project = await db.get(Project, page.project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if not project.base_url:
        raise HTTPException(400, "请先配置项目 base_url")

    try:
        # 加载页面规则
        rules_loader = MCPRulesLoader(project_id=project.id)
        page_rules = rules_loader.load_page_rules(page.full_path) or ""
        
        # 构建 prompt
        page_info = {
            "route": page.full_path,
            "url": f"{project.base_url}{page.full_path}",
            "title": page.name,
            "detected_components": json.loads(page.component_name) if page.component_name else [],
            "dom_summary": "待补充",
            "internal_links": []
        }
        
        page_prompt = build_mcp_prompt_for_page(page_info, project, page_rules)
        
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个资深 QA 工程师和 Playwright Python 测试专家。\n"
                    "根据提供的页面信息，生成一组全面的端到端测试用例。\n\n"
                    "要求：\n"
                    "1. 每个用例包含: title(标题), description(自然语言描述), script_content(完整的 Python 测试代码), group_name(分组名)\n"
                    "2. 测试代码使用 pytest + playwright sync_api\n"
                    "3. 测试函数参数为 page: Page\n"
                    "4. 使用 expect() 做断言\n"
                    "5. 代码中用中文注释说明每个步骤\n"
                    f"6. 被测站点 base_url: {project.base_url}\n"
                    f"7. 页面路由: {page.full_path}\n"
                    "8. 覆盖该页面的主要功能和交互流程\n"
                    '9. 返回 JSON 格式: {"test_cases": [{"title": "", "description": "", "script_content": "", "group_name": ""}]}'
                ),
            },
            {
                "role": "user",
                "content": page_prompt,
            },
        ]
        
        raw = await llm_chat(messages, temperature=0.3, max_tokens=8192)
        
        # 解析 LLM 响应
        content = raw.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(content)
        cases_data = result.get("test_cases", [])
        
        # 保存用例
        created_cases = []
        for idx, case_data in enumerate(cases_data):
            tc = TestCase(
                project_id=project.id,
                page_id=page.id,  # 关联到页面
                title=case_data.get("title", f"测试用例 {idx + 1}"),
                description=case_data.get("description", ""),
                script_content=case_data.get("script_content", ""),
                group_name=page.full_path,
            )
            db.add(tc)
            created_cases.append(tc)
        
        await db.commit()
        for tc in created_cases:
            await db.refresh(tc)
        
        logger.info(f"页面 {page.full_path} 生成 {len(cases_data)} 个用例")
        return created_cases
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"页面用例生成失败: {e}", exc_info=True)
        raise HTTPException(500, f"页面用例生成失败: {str(e)}")


def build_mcp_prompt_for_page(page_info: dict, project: Project, page_rules: str = "") -> str:
    """
    为单个页面构建 MCP prompt
    
    参数:
        page_info: 页面信息（来自 MCP 探索）
        project: 项目对象
        page_rules: 页面规则（可选）
    
    返回:
        格式化的 prompt 文本
    """
    prompt_parts = [
        f"## 页面信息\n",
        f"- 路由: {page_info['route']}",
        f"- URL: {page_info.get('url', 'N/A')}",
        f"- 标题: {page_info.get('title', 'N/A')}",
        f"\n## 检测到的组件",
        f"{', '.join(page_info.get('detected_components', ['无']))}",
        f"\n## 页面结构摘要",
        f"{page_info.get('dom_summary', 'N/A')}",
        f"\n## 页面内的链接",
    ]
    
    # 添加链接列表
    for link in page_info.get("internal_links", [])[:20]:  # 限制链接数量
        prompt_parts.append(f"- {link.get('text', '')} -> {link.get('href', '')}")
    
    # 添加页面规则
    if page_rules:
        prompt_parts.append(f"\n## 页面探索规则\n\n{page_rules}")
    
    return "\n".join(prompt_parts)
