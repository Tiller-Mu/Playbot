"""页面树管理 API 路由。"""
import json
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import TestPage, TestCase, Project, get_db
from app.schemas.schemas import TestPageOut, TestCaseOut
from app.services.page_analyzer import extract_page_tree

router = APIRouter(prefix="/api/pages", tags=["pages"])


def build_tree_response(pages: list[TestPage], case_counts: dict[str, int]) -> list[dict]:
    """将扁平的页面列表转换为树形结构"""
    page_map = {}
    root_pages = []
    
    # 创建所有节点
    for page in pages:
        # 优先使用静态分析的 imported_components，其次使用 component_name
        components = []
        
        # 1. 优先使用 imported_components（从页面源码静态分析得到）
        if hasattr(page, 'imported_components') and page.imported_components:
            try:
                if isinstance(page.imported_components, str):
                    components = json.loads(page.imported_components)
                else:
                    components = page.imported_components
            except:
                components = []
        # 2. 其次使用 component_name
        elif page.component_name:
            try:
                if isinstance(page.component_name, str):
                    if page.component_name.startswith('['):
                        components = json.loads(page.component_name)
                    else:
                        components = [c.strip() for c in page.component_name.split(',') if c.strip()]
                elif isinstance(page.component_name, list):
                    components = page.component_name
            except:
                components = [page.component_name] if page.component_name else []
        
        node = {
            "id": page.id,
            "project_id": page.project_id,
            "parent_id": page.parent_id,
            "name": page.name,
            "path": page.path,
            "full_path": page.full_path,
            "is_leaf": page.is_leaf,
            "file_path": page.file_path,
            "component_name": page.component_name,
            "components": components,  # 组件列表
            "page_comments": page.page_comments or "",  # 页面注释
            "component_comments": page.component_comments or "",  # 组件注释
            "description": page.description or "",
            "is_captured": page.is_captured or False,  # 是否已录制
            "children": [],
            "case_count": case_counts.get(page.id, 0),
        }
        page_map[page.id] = node
    
    # 构建树结构
    for page in pages:
        node = page_map[page.id]
        if page.parent_id and page.parent_id in page_map:
            parent_node = page_map[page.parent_id]
            parent_node["children"].append(node)
        else:
            root_pages.append(node)
    
    return root_pages


@router.get("/{project_id}")
async def get_page_tree(project_id: str, db: AsyncSession = Depends(get_db)):
    """获取项目的页面树"""
    result = await db.execute(
        select(TestPage)
        .where(TestPage.project_id == project_id)
        .order_by(TestPage.full_path)
    )
    pages = result.scalars().all()
    
    case_count_result = await db.execute(
        select(TestPage.id, func.count(TestCase.id))
        .outerjoin(TestCase, TestPage.id == TestCase.page_id)
        .where(TestPage.project_id == project_id)
        .group_by(TestPage.id)
    )
    case_counts = {row[0]: row[1] for row in case_count_result.all()}
    
    tree = build_tree_response(list(pages), case_counts)
    return {"pages": tree, "total_cases": sum(case_counts.values())}


@router.post("/{project_id}/refresh")
async def refresh_page_tree(project_id: str, db: AsyncSession = Depends(get_db)):
    """重新分析代码生成页面树"""
    project = await db.get(Project, project_id)
    if not project or not project.repo_path:
        raise HTTPException(400, "项目不存在或未拉取代码")
    
    tree_data = await extract_page_tree(project.repo_path)
    if not tree_data:
        return {"pages": [], "total_cases": 0, "message": "未检测到页面文件"}
    
    # 清空旧数据
    await db.execute(update(TestCase).where(TestCase.project_id == project_id).values(page_id=None))
    old_pages_result = await db.execute(select(TestPage.id).where(TestPage.project_id == project_id))
    for pid in [row[0] for row in old_pages_result.all()]:
        op = await db.get(TestPage, pid)
        if op: await db.delete(op)
    await db.commit()
    
    async def save_tree(nodes: list[dict], parent_id: str | None = None):
        for node in nodes:
            imported = node.get("imported_components", [])
            page = TestPage(
                project_id=project_id,
                parent_id=parent_id,
                name=node.get("name", ""),
                path=node.get("path", ""),
                full_path=node.get("full_path", ""),
                is_leaf=node.get("is_leaf", False),
                file_path=node.get("file_path", ""),
                component_name=node.get("component"),
                imported_components=json.dumps(imported, ensure_ascii=False) if imported else None,
                page_comments=node.get("page_comments"),
                component_comments=json.dumps(node.get("component_comments", {}), ensure_ascii=False) if node.get("component_comments") else None,
            )
            db.add(page)
            await db.flush() # 获取ID
            if node.get("children"):
                await save_tree(node["children"], page.id)
    
    await save_tree(tree_data)
    await db.commit()
    return await get_page_tree(project_id, db)


@router.post("/{page_id}/generate")
async def generate_page_cases(page_id: str, db: AsyncSession = Depends(get_db)):
    """为指定页面生成测试用例（使用DOM数据 + 源代码 + 优化Prompt）"""
    import re
    import json
    import os
    import traceback
    from pathlib import Path
    from datetime import datetime
    from app.services.llm_service import llm_chat_stream
    from app.core.websocket import ws_manager
    from app.services.mcp_log_service import mcp_log_service
    from app.services.playwright_mcp import PlaywrightMCPService
    
    page = await db.get(TestPage, page_id)
    project = await db.get(Project, page.project_id) if page else None
    if not page or not project: raise HTTPException(404, "页面或项目不存在")
    
    async def send_log(level: str, message: str):
        await ws_manager.broadcast({"type": "log", "level": level, "message": message, "timestamp": datetime.now().isoformat()}, channel=f"mcp_{project.id}")
        mcp_log_service.log(project.id, level, message)
    
    await send_log("info", f"🔍 开始为页面生成专家级用例: {page.name}")
    
    # 1. 获取 DOM
    from app.routers.recording import _get_session
    session = _get_session(project.id)
    dom_data = session.discovered_pages.get(page.full_path, {}).get('dom')
    
    if not dom_data:
        alt_p = page.full_path[:-1] if page.full_path.endswith('/') and len(page.full_path) > 1 else page.full_path + '/'
        dom_data = session.discovered_pages.get(alt_p, {}).get('dom')

    if not dom_data:
        await send_log("warning", "⚠️ 未发现录制数据，尝试实时获取...")
        mcp = PlaywrightMCPService(headless=True)
        dom_data = await mcp.analyze_page(f"{project.base_url.rstrip('/')}/{page.full_path.lstrip('/')}", page.name)
    
    if dom_data: await send_log("success", "✅ 已锁定真实 DOM 数据")

    # 2. 读取源码及组件
    source_code = ""
    component_codes = []
    if project.repo_path:
        current_file_path = page.file_path
        if not current_file_path:
            search_name = page.path.lower()
            if search_name == '/': search_name = 'home'
            for pattern in [f"**/{search_name}.vue", f"**/{search_name}View.vue", f"**/{search_name}Page.vue", "**/index.vue"]:
                matches = list(Path(project.repo_path).glob(pattern))
                if matches:
                    current_file_path = str(matches[0].relative_to(project.repo_path)).replace('\\', '/')
                    await send_log("success", f"🎯 自动匹配到源码: {current_file_path}")
                    break
        
        if current_file_path:
            full_p = os.path.join(project.repo_path, current_file_path)
            if os.path.exists(full_p):
                with open(full_p, 'r', encoding='utf-8') as f: source_code = f.read()
        
        from app.services.component_analyzer import analyze_components
        comp_info = await analyze_components(project.repo_path)
        comp_registry = {c['name']: c['file_path'] for c in comp_info.get('components', [])}
        try:
            used_names = json.loads(page.imported_components) if page.imported_components else []
            for name in used_names:
                if name in comp_registry:
                    cp = os.path.join(project.repo_path, comp_registry[name])
                    if os.path.exists(cp):
                        with open(cp, 'r', encoding='utf-8') as f: 
                            component_codes.append(f"### 组件: {name}\n{f.read()}")
        except: pass
    
    # 3. 使用AST分析代码和DOM
    await send_log("info", "🔬 正在分析页面结构...")
    from app.agents.utils.code_analyzer import analyze_page_data, format_for_llm
    
    page_analysis = analyze_page_data(source_code, dom_data, current_file_path or '')
    analysis_text = format_for_llm(page_analysis)
    
    await send_log("success", f"✅ 分析完成: 发现 {page_analysis['dom_structure'].get('interactive_count', 0)} 个交互元素")
    await send_log("debug", f"发现 {page_analysis['dom_structure'].get('interactive_count', 0)} 个交互元素")
    
    # 检查是否有足够信息生成用例
    if not page_analysis['code_structure'] and not page_analysis['dom_structure'].get('interactive_elements'):
        await send_log("error", "❌ 页面信息不足，无法生成用例")
        raise HTTPException(400, "页面信息不足，无法生成用例")
    
    # 4. 构建指令（使用分析后的精简信息）
    system_content = (
        "你是一个顶级的 Playwright Python 专家。\n"
        "**只准返回 JSON，严禁文字说明！**\n"
        "**JSON 必须包含 'test_cases' 字段，每个用例必须有 'script_content' 字段，其值为完整的 Python 代码字符串。**\n"
        "代码要求：包含 import、包含 expect 断言、使用真实选择器。"
    )
    
    user_content = f"""为页面生成测试用例。

页面路径: {page.full_path}
URL: {project.base_url.rstrip('/')}/{page.full_path.lstrip('/')}

{analysis_text}

请生成 2-3 个核心测试用例，覆盖最重要的交互场景。

返回格式:
{{
  "test_cases": [
    {{
      "title": "用例标题",
      "description": "测试目的描述",
      "script_content": "import pytest\\nfrom playwright.sync_api import Page, expect\\ndef test_xxx(page: Page):\\n    ..."
    }}
  ]
}}"""

    # 4. 调用 LLM
    await send_log("info", "🤖 正在调用专家级 LLM 生成完整代码...")
    full_response = []
    async def on_token(t: str):
        full_response.append(t)
        await ws_manager.broadcast({"type": "log", "level": "stream", "message": "".join(full_response)}, channel=f"mcp_{project.id}")

    try:
        raw = await llm_chat_stream([{"role": "system", "content": system_content}, {"role": "user", "content": user_content}], on_token=on_token)
    except Exception as e:
        await send_log("error", f"❌ LLM 故障: {str(e)}")
        raise HTTPException(500, f"LLM 故障: {str(e)}")
    
    # 5. 超强力解析
    await send_log("info", "📋 正在执行超强力解析...")
    try:
        content = raw.strip()
            
        # 调试：记录原始内容长度
        await send_log("debug", f"原始响应长度: {len(content)} 字符")
            
        # 尝试提取 Markdown 代码块
        code_block_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
        if code_block_match:
            content = code_block_match.group(1).strip()
            await send_log("debug", "从Markdown代码块提取内容")
            
        # 寻找 JSON 块（使用更健壮的方式）
        json_str = None
            
        # 尝试找 test_cases 键
        if '"test_cases"' in content or "'test_cases'" in content:
            # 找最外层的大括号
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = content[start_idx:end_idx+1]
                await send_log("debug", f"提取JSON范围: {start_idx} 到 {end_idx}")
            
        # 如果没找到，尝试其他方式
        if not json_str:
            json_match = re.search(r'\{.*"test_cases".*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            
        if not json_str:
            # 尝试寻找列表块并包装
            list_match = re.search(r'\[.*\]', content, re.DOTALL)
            if list_match:
                json_str = f'{{"test_cases": {list_match.group(0)}}}'
                await send_log("debug", "从列表包装为test_cases")
            else:
                raise ValueError(f"响应中未发现 test_cases。原始内容前500字符: {content[:500]}")
            
        # 清洗（保留代码中的换行）
        json_str = json_str.replace('\r\n', '\n').replace('\r', '\n')
                
        # 修复非标准JSON：将单引号转为双引号，给无引号的属性名加引号
        import re as regex
        # 先处理字符串值中的单引号（简单替换，可能不完美）
        # 将属性名的单引号替换为双引号: 'key': -> "key":
        json_str = regex.sub(r"'([^']+)'\s*:", r'"\1":', json_str)
        # 将字符串值的单引号替换为双引号: 'value' -> "value"
        # 注意：这可能会破坏包含单引号的文本内容，但作为fallback尝试
                
        # 尝试解析
        try:
            result = json.loads(json_str)
        except json.JSONDecodeError as je:
            await send_log("warning", f"标准JSON解析失败，尝试容错解析: {je}")
            # 尝试使用更宽松的解析（如yaml）或手动修复
            try:
                # 尝试用ast.literal_eval解析Python字典格式
                import ast
                result = ast.literal_eval(json_str)
                await send_log("debug", "使用ast.literal_eval解析成功")
            except Exception as e2:
                await send_log("error", f"JSON解析失败: {je}")
                await send_log("debug", f"问题JSON前300字符: {json_str[:300]}")
                raise
            
        # 兼容性处理
        if isinstance(result, list):
            cases_data = result
            await send_log("debug", f"结果直接是列表，共 {len(cases_data)} 条")
        else:
            cases_data = result.get("test_cases", [])
            await send_log("debug", f"从test_cases提取，共 {len(cases_data)} 条")
            
        if not cases_data:
            await send_log("warning", "test_cases 为空列表")
            return {"status": "success", "count": 0}
            
        created_count = 0
        for i, cd in enumerate(cases_data):
            # 关键：确保 script_content 存在
            script = cd.get("script_content") or cd.get("script")
            if not script and cd.get("steps"):
                script = f"# 步骤化用例：\n# " + str(cd.get("steps"))
                
            title = cd.get("title") or cd.get("name", f"用例_{i+1}")
                
            tc = TestCase(
                project_id=project.id, 
                page_id=page.id, 
                title=title, 
                description=cd.get("description", ""), 
                script_content=script or "# 无代码内容", 
                group_name=page.full_path
            )
            db.add(tc)
            created_count += 1
                
        await db.commit()
        await send_log("success", f"✅ 专家级用例已入库 ({created_count} 条)")
        return {"status": "success", "count": created_count}
    except Exception as e:
        await send_log("error", f"❌ 解析/保存失败: {str(e)}")
        print(f"[解析异常] 原始内容前1000字符: {raw[:1000]}", flush=True)
        raise HTTPException(500, f"处理失败: {str(e)}")


@router.get("/{page_id}/cases")
async def get_page_cases(page_id: str, db: AsyncSession = Depends(get_db)):
    page = await db.get(TestPage, page_id)
    if not page: return []
    
    async def get_child_ids(pid):
        r = await db.execute(select(TestPage.id).where(TestPage.parent_id == pid))
        ids = [row[0] for row in r.all()]
        for cid in list(ids): ids.extend(await get_child_ids(cid))
        return ids

    pids = [page_id] + await get_child_ids(page_id)
    res = await db.execute(select(TestCase).where(TestCase.page_id.in_(pids)).order_by(TestCase.created_at.desc()))
    return res.scalars().all()


# ========== 智能体生成用例（LangGraph） ==========

@router.post("/{page_id}/generate-agent")
async def generate_cases_with_agent(
    page_id: str, 
    db: AsyncSession = Depends(get_db)
):
    """
    使用LangGraph智能体生成测试用例
    
    流程：
    1. 获取页面源码和DOM数据
    2. 调用智能体分析（代码分析 → DOM分析 → 策略分析 → 生成用例）
    3. 保存生成的用例到数据库
    4. 返回完整结果（包含分析过程和用例）
    """
    from app.agents import TestCaseAgent, AgentConfig, TestCaseInput
    from app.services.llm_service import llm_chat_json
    from app.core.config import settings
    from app.core.websocket import ws_manager
    from datetime import datetime
    
    # 获取页面信息
    page = await db.get(TestPage, page_id)
    if not page:
        raise HTTPException(404, "页面不存在")
    
    project = await db.get(Project, page.project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    
    # 获取源码
    source_code = ""
    if page.file_path and os.path.exists(page.file_path):
        try:
            with open(page.file_path, 'r', encoding='utf-8') as f:
                source_code = f.read()
        except Exception as e:
            print(f"[智能体生成] 读取源码失败: {e}")
    
    # 获取DOM数据（从录制会话中获取）
    dom_data = {}
    try:
        from app.routers.recording import _get_session
        session = _get_session(project.id)
        
        # 尝试匹配页面路径
        if page.full_path in session.discovered_pages:
            dom_data = session.discovered_pages[page.full_path].get('dom', {})
        else:
            # 尝试其他匹配方式（带/不带末尾斜杠）
            alt_path = page.full_path.rstrip('/') if page.full_path.endswith('/') else page.full_path + '/'
            if alt_path in session.discovered_pages:
                dom_data = session.discovered_pages[alt_path].get('dom', {})
        
        if dom_data:
            print(f"[智能体生成] 从录制会话获取DOM数据: {page.full_path}", flush=True)
    except Exception as e:
        print(f"[智能体生成] 获取DOM数据失败: {e}", flush=True)
    
    # 日志回调函数
    logs = []
    async def log_callback(level: str, message: str):
        logs.append({"level": level, "message": message, "time": datetime.now().isoformat()})
        # 同时发送到WebSocket (复用MCP日志面板订阅的频道)
        await ws_manager.broadcast({
            "type": "agent_log",
            "page_id": page_id,
            "level": level,
            "message": message
        }, channel=f"mcp_{project.id}")
        
        # 不要把累加形的流式输出打印到标准控制台，只打印离散节点的心跳日志
        if level != "stream":
            print(f"[智能体-{level}] {message}")
    
    try:
        from app.services.llm_service import llm_chat_stream
        
        async def streaming_llm_caller(messages):
            # 获取全内容的累加 buffer 向前台冲刷
            buffer = []
            async def on_token_callback(token_text: str):
                buffer.append(token_text)
                await log_callback("stream", "".join(buffer))
            # 在外层包装一次，拦截调用直接抛到 websocket 里
            return await llm_chat_stream(messages, on_token=on_token_callback)

        config = AgentConfig(
            llm_caller=streaming_llm_caller,
            langfuse_public_key=settings.langfuse_public_key,
            langfuse_secret_key=settings.langfuse_secret_key,
            langfuse_host=settings.langfuse_host
        )
        # 创建智能体并生成
        agent = TestCaseAgent(config=config, log_callback=log_callback)
        
        await log_callback("info", f"🚀 开始为页面 [{page.full_path}] 生成测试用例")
        await log_callback("info", f"📄 源码长度: {len(source_code)} 字符")
        await log_callback("info", f"🌐 页面URL: {project.base_url}{page.path}")
        await log_callback("info", f"📊 DOM数据: {'已获取' if dom_data else '未获取'} ({len(str(dom_data)) if dom_data else 0} 字符)")
        
        input_data = TestCaseInput(
            page_url=f"{project.base_url}{page.path}",
            file_path=page.file_path or "", 
            source_code=source_code,
            dom_data=dom_data
        )
        result = await agent.generate(input_data)
        
        # 保存用例到数据库
        test_cases = result.get("test_cases", [])
        created_cases = []
        
        for case_data in test_cases:
            tc = TestCase(
                project_id=page.project_id,
                page_id=page_id,
                title=case_data.get("title", "未命名用例"),
                description=case_data.get("description", ""),
                script_content=case_data.get("script_content", ""),
                group_name=page.full_path,
                enabled=True
            )
            db.add(tc)
            created_cases.append(tc)
        
        await db.commit()
        
        # 刷新获取ID
        for tc in created_cases:
            await db.refresh(tc)
        
        if result.get("error"):
            await log_callback("error", f"❌ 任务生成因异常被迫终止: {result.get('error')}")
        else:
            await log_callback("success", f"✅ 成功生成并保存 {len(created_cases)} 个用例")
        
        return {
            "status": "success",
            "page_id": page_id,
            "page_path": page.full_path,
            "generated_count": len(created_cases),
            "test_cases": [
                {
                    "id": tc.id,
                    "title": tc.title,
                    "description": tc.description,
                    "script_content": tc.script_content
                }
                for tc in created_cases
            ],
            "analysis": result.get("analysis", {}),
            "logs": logs
        }
        
    except Exception as e:
        error_msg = str(e)
        await log_callback("error", f"❌ 生成失败: {error_msg}")
        raise HTTPException(500, f"智能体生成失败: {error_msg}")


@router.get("/debug/langfuse-status")
async def get_langfuse_status():
    """
    获取 Langfuse 追踪状态
    
    用于调试和确认 Langfuse 是否正确配置
    """
    from app.core.config import settings
    
    enabled = bool(settings.langfuse_enabled and settings.langfuse_public_key and settings.langfuse_secret_key)
    base_url = settings.langfuse_host.rstrip('/')
    
    return {
        "enabled": enabled,
        "config": {
            "enabled": enabled,
            "host": settings.langfuse_host,
            "public_key_configured": bool(settings.langfuse_public_key),
            "secret_key_configured": bool(settings.langfuse_secret_key),
        },
        "trace_url": f"{base_url}/traces",
        "setup_guide": "访问 https://cloud.langfuse.com 获取 API Keys 或本地部署 Langfuse"
    }
