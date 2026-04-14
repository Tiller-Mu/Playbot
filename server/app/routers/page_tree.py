"""页面树管理 API 路由。"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import TestPage, TestCase, Project, get_db
from app.schemas.schemas import TestPageOut, TestCaseOut
from app.services.page_analyzer import extract_page_tree
from app.services.llm_service import llm_chat

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
            components = page.imported_components
        # 2. 其次使用 component_name（从 MCP 分析或数据库得到）
        elif page.component_name:
            try:
                # 尝试解析JSON
                if isinstance(page.component_name, str):
                    if page.component_name.startswith('['):
                        components = json.loads(page.component_name)
                    else:
                        # 逗号分隔的字符串
                        components = [c.strip() for c in page.component_name.split(',') if c.strip()]
                elif isinstance(page.component_name, list):
                    components = page.component_name
            except:
                # 解析失败，当作单个组件名
                components = [page.component_name] if page.component_name else []
        
        node = {
            "id": page.id,
            "project_id": page.project_id,
            "parent_id": page.parent_id,
            "name": page.name,
            "path": page.path,
            "full_path": page.full_path,
            "is_leaf": page.is_leaf,
            "component_name": page.component_name,
            "components": components,  # 组件列表
            "page_comments": page.page_comments or "",  # 页面注释
            "component_comments": page.component_comments or "",  # 组件注释（JSON字符串）
            "description": page.description or "",
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
    # 查询所有页面
    result = await db.execute(
        select(TestPage)
        .where(TestPage.project_id == project_id)
        .order_by(TestPage.full_path)
    )
    pages = result.scalars().all()
    
    # 统计每个页面的用例数
    case_count_result = await db.execute(
        select(TestPage.id, func.count(TestCase.id))
        .outerjoin(TestCase, TestPage.id == TestCase.page_id)
        .where(TestPage.project_id == project_id)
        .group_by(TestPage.id)
    )
    case_counts = {row[0]: row[1] for row in case_count_result.all()}
    
    # 构建树形结构
    tree = build_tree_response(list(pages), case_counts)
    
    return {"pages": tree, "total_cases": sum(case_counts.values())}


@router.post("/{project_id}/refresh")
async def refresh_page_tree(project_id: str, db: AsyncSession = Depends(get_db)):
    """重新分析代码生成页面树"""
    # 检查项目是否存在
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    
    if not project.repo_path:
        raise HTTPException(400, "请先拉取项目代码")
    
    # 分析页面树
    tree_data = await extract_page_tree(project.repo_path)
    
    if not tree_data:
        return {"pages": [], "total_cases": 0, "message": "未检测到页面文件"}
    
    # 清空旧的页面树（保留用例，page_id 设为 NULL）
    await db.execute(
        update(TestCase)
        .where(TestCase.project_id == project_id)
        .values(page_id=None)
    )
    
    old_pages_result = await db.execute(
        select(TestPage.id).where(TestPage.project_id == project_id)
    )
    old_page_ids = [row[0] for row in old_pages_result.all()]
    
    for page_id in old_page_ids:
        old_page = await db.get(TestPage, page_id)
        if old_page:
            await db.delete(old_page)
    
    await db.commit()
    
    # 保存新的页面树
    async def save_tree(nodes: list[dict], parent_id: str | None = None):
        saved_pages = []
        for node in nodes:
            # 保存静态分析的数据
            imported_components = node.get("imported_components", [])
            page_comments = node.get("page_comments", "")
            component_comments = node.get("component_comments", {})
            
            page = TestPage(
                project_id=project_id,
                parent_id=parent_id,
                name=node.get("name", ""),
                path=node.get("path", ""),
                full_path=node.get("full_path", ""),
                is_leaf=node.get("is_leaf", False),
                file_path=node.get("file_path", ""),  # 保存源代码文件路径
                component_name=node.get("component"),
                imported_components=json.dumps(imported_components, ensure_ascii=False) if imported_components else None,
                page_comments=page_comments if page_comments else None,
                component_comments=json.dumps(component_comments, ensure_ascii=False) if component_comments else None,
            )
            db.add(page)
            saved_pages.append(page)
            
            # 递归保存子节点
            children = node.get("children")
            if children:
                child_pages = await save_tree(children, page.id)
                saved_pages.extend(child_pages)
        
        return saved_pages
    
    await save_tree(tree_data)
    await db.commit()
    
    # 返回新的页面树
    result = await db.execute(
        select(TestPage)
        .where(TestPage.project_id == project_id)
        .order_by(TestPage.full_path)
    )
    pages = result.scalars().all()
    
    case_counts = {}  # 新页面树还没有用例
    tree = build_tree_response(list(pages), case_counts)
    
    return {"pages": tree, "total_cases": 0, "message": f"成功分析 {len(pages)} 个页面节点"}


@router.post("/{page_id}/generate")
async def generate_page_cases(page_id: str, db: AsyncSession = Depends(get_db)):
    """为指定页面生成测试用例（使用DOM数据 + 源代码）"""
    from app.services.llm_service import llm_chat_stream
    from app.core.websocket import ws_manager
    from app.services.mcp_log_service import mcp_log_service
    from app.services.playwright_mcp import PlaywrightMCPService
    import traceback
    import os
    
    page = await db.get(TestPage, page_id)
    if not page:
        raise HTTPException(404, "页面不存在")
    
    if not page.is_leaf:
        raise HTTPException(400, "只能为叶子节点（页面）生成用例")
    
    project = await db.get(Project, page.project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    
    # WebSocket日志推送函数
    async def send_log(level: str, message: str):
        """发送WebSocket日志"""
        log_entry = {
            "type": "log",
            "level": level,
            "message": message,
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }
        await ws_manager.broadcast(log_entry, channel=f"mcp_{project.id}")
        mcp_log_service.log(project.id, level, message)
    
    await send_log("info", f"🔍 开始为页面生成用例: {page.name}")
    await send_log("info", f"📄 页面路径: {page.full_path}")
    
    # 第一步：使用PlaywrightMCP获取真实DOM数据
    await send_log("info", "🌐 正在使用Playwright访问页面获取DOM数据...")
    
    mcp = PlaywrightMCPService(headless=True)
    dom_data = None
    try:
        # 构建页面URL
        page_url = f"{project.base_url}{page.full_path}"
        await send_log("info", f"🔗 访问页面: {page_url}")
        
        # 分析页面（内部会自动创建/关闭浏览器）
        dom_data = await mcp.analyze_page(
            url=page_url,
            page_name=page.name,
            timeout=15000
        )
        
        if not dom_data:
            await send_log("warning", "⚠️ analyze_page返回None，检查后端日志获取详细错误")
            print(f"[生成用例] analyze_page返回None, URL: {page_url}", flush=True)
        
        if dom_data:
            # 额外获取完整的DOM结构和CSS选择器
            if mcp.context:
                dom_page = await mcp.context.new_page()
                await dom_page.goto(page_url, wait_until='domcontentloaded', timeout=10000)
                
                # 获取DOM结构
                dom_structure = await dom_page.evaluate("""
                    () => {
                        const getAllElements = (element, depth = 0) => {
                            if (depth > 5) return [];
                            const result = [];
                            const tag = element.tagName?.toLowerCase();
                            if (!tag) return result;
                            
                            const id = element.id ? `#${element.id}` : '';
                            const classes = element.className && typeof element.className === 'string' 
                                ? `.${element.className.split(' ').filter(c => c).join('.')}` 
                                : '';
                            
                            result.push({
                                tag: tag + id + classes,
                                text: element.childNodes.length === 1 && element.childNodes[0].nodeType === 3 
                                    ? element.textContent.substring(0, 50) 
                                    : '',
                                children: []
                            });
                            
                            for (const child of element.children) {
                                result[result.length - 1].children.push(...getAllElements(child, depth + 1));
                            }
                            
                            return result;
                        };
                        return getAllElements(document.body);
                    }
                """)
                
                # 获取CSS选择器
                all_selectors = await dom_page.evaluate("""
                    () => {
                        const elements = [];
                        const allEls = document.querySelectorAll('*');
                        
                        allEls.forEach((el, index) => {
                            if (index > 200) return;
                            
                            const rect = el.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0) return;
                            
                            let selector = el.tagName.toLowerCase();
                            if (el.id) {
                                selector += `#${el.id}`;
                            } else if (el.className && typeof el.className === 'string') {
                                const classes = el.className.split(' ').filter(c => c && !c.startsWith('ant'));
                                if (classes.length > 0) {
                                    selector += `.${classes.slice(0, 2).join('.')}`;
                                }
                            }
                            
                            elements.push({
                                selector,
                                tag: el.tagName.toLowerCase(),
                                text: el.innerText?.substring(0, 100) || '',
                                visible: true
                            });
                        });
                        
                        return elements;
                    }
                """)
                
                dom_data['dom_structure'] = dom_structure
                dom_data['all_selectors'] = all_selectors
                
                await send_log("success", f"✅ DOM数据获取成功: {len(dom_data.get('interactive_elements', []))}个交互元素, {len(all_selectors)}个CSS选择器")
            else:
                await send_log("warning", "⚠️ DOM数据获取不完整")
        else:
            await send_log("error", "❌ 无法获取DOM数据，终止生成")
            await send_log("info", "💡 请检查：1)前端是否运行 2)页面路径是否正确 3)查看后端日志获取详细错误")
            return {"error": "DOM数据获取失败", "page_id": page_id}
            
    except Exception as e:
        await send_log("error", f"❌ Playwright访问页面失败: {str(e)}")
        await send_log("info", "💡 请检查：1)前端是否运行 2)页面路径是否正确 3)查看后端日志获取详细错误")
        print(f"[生成用例] Playwright访问失败: {e}", flush=True)
        return {"error": f"Playwright访问失败: {str(e)}", "page_id": page_id}
    
    # 第二步：读取页面对应的Vue源代码
    await send_log("info", "📂 正在读取页面源代码...")
    
    source_code = ""
    if project.repo_path and page.file_path:
        # 构建源代码文件路径
        source_file_path = os.path.join(project.repo_path, page.file_path)
        
        if os.path.exists(source_file_path):
            try:
                with open(source_file_path, 'r', encoding='utf-8') as f:
                    source_code = f.read()
                await send_log("success", f"✅ 源代码读取成功: {len(source_code)} 字")
            except Exception as e:
                await send_log("warning", f"⚠️ 源代码读取失败: {str(e)}")
                print(f"[生成用例] 源代码读取失败: {e}", flush=True)
        else:
            await send_log("warning", f"⚠️ 源代码文件不存在: {source_file_path}")
    elif not page.file_path:
        await send_log("warning", "⚠️ 页面没有file_path信息，请重新刷新页面树")
    else:
        await send_log("warning", "⚠️ 项目代码路径未配置")
    
    # 第三步：构建Prompt
    await send_log("info", "📝 正在构建Prompt...")
    
    # 获取组件列表
    components = []
    if page.component_name:
        try:
            components = json.loads(page.component_name)
            if not isinstance(components, list):
                components = []
        except:
            components = []
    
    # 构建DOM数据描述
    dom_description = ""
    if dom_data:
        dom_description = f"""
## 真实DOM数据（通过Playwright获取）

页面标题: {dom_data.get('title', '')}

### 交互元素
```json
{json.dumps(dom_data.get('interactive_elements', [])[:20], ensure_ascii=False, indent=2)}
```

### CSS选择器（部分）
```json
{json.dumps(dom_data.get('all_selectors', [])[:30], ensure_ascii=False, indent=2)}
```
"""
    
    # 构建Prompt
    system_content = (
        "你是一个资深QA工程师和Playwright Python测试专家。\n\n"
        "**极其重要的要求：**\n"
        "1. **直接返回JSON，不要任何思考过程、分析、解释、说明**\n"
        "2. **不要使用markdown代码块**\n"
        "3. **第一个字符必须是{，最后一个字符必须是}**\n"
        "4. 基于源代码理解业务逻辑和预期行为\n"
        "5. 基于DOM数据使用真实的选择器\n"
        "6. 每个用例必须包含断言\n"
        "7. 使用pytest格式\n"
        "8. 代码要完整可执行\n\n"
        "**如果你返回任何非JSON内容，系统将无法解析，任务会失败！**"
    )
    
    user_content = f"""请为Playbot的页面生成全面的端到端测试用例。

## 页面信息
- 页面名称: {page.name}
- 页面路径: {page.full_path}
- 页面URL: {project.base_url}{page.full_path}

## 源代码

{source_code if source_code else '（源代码未提供）'}

{dom_description if dom_description else '（DOM数据未提供）'}

## 生成要求

基于源代码和DOM数据，生成覆盖以下场景的测试用例：
1. 页面加载测试（验证页面结构、关键元素）
2. 主要功能测试（基于源代码的业务逻辑）
3. 表单交互测试（如果有表单）
4. 边界情况和错误处理

## 输出格式

**再次强调：直接返回JSON，不要任何其他内容！**

返回格式：
{{
  "test_cases": [
    {{
      "title": "测试用例标题",
      "description": "测试用例描述",
      "script_content": "完整的pytest测试代码"
    }}
  ]
}}

**重要：script_content中的代码必须使用真实的选择器（从DOM数据中获取），不要硬编码或猜测选择器！**
**重要：不要返回任何分析过程，直接返回JSON！**
"""
    
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    
    # 显示发送给LLM的完整Prompt
    await send_log("info", f"📤 发送给LLM的Prompt:\n\n【System】\n{system_content}\n\n【User】\n{user_content}")
    
    await send_log("info", "🤖 正在调用LLM生成测试用例...")
    
    # 使用流式输出，每100字推送一次累积内容
    token_buffer = []
    last_push_length = 0
    
    async def on_token(token: str):
        """每收到一个token的回调"""
        nonlocal last_push_length
        token_buffer.append(token)
        
        # 每累积100字推送一次
        current_content = "".join(token_buffer)
        if len(current_content) - last_push_length >= 100:
            last_push_length = len(current_content)
            # 使用特殊level标记这是流式内容，前端不显示时间戳
            await send_log("stream", current_content)
    
    try:
        raw = await llm_chat_stream(
            messages, 
            temperature=0.3, 
            max_tokens=8192,
            on_token=on_token
        )
        
        if not raw or len(raw) == 0:
            await send_log("error", "❌ LLM返回内容为空，请检查后端日志")
            raise HTTPException(500, "LLM返回内容为空")
        
        # 推送剩余内容
        remaining = "".join(token_buffer)
        if len(remaining) > last_push_length:
            await send_log("stream", remaining)
        
        await send_log("success", f"\n✅ LLM生成完成，共 {len(raw)} 字")
    except Exception as e:
        await send_log("error", f"❌ LLM调用失败: {str(e)}")
        print(f"[生成用例] LLM调用失败: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        raise HTTPException(500, f"LLM调用失败: {str(e)}")
    
    # 解析 LLM 响应
    await send_log("info", "📋 正在解析LLM返回的测试用例...")
    try:
        content = raw.strip()
        
        # 智能提取JSON - 跳过LLM的分析过程，直接找到JSON部分
        # 从后往前找，因为JSON通常在最后
        last_brace = content.rfind("}")
        if last_brace == -1:
            raise ValueError("未找到JSON结束标记 }")
        
        # 找test_cases字段
        test_cases_idx = content.rfind('"test_cases"')
        if test_cases_idx == -1:
            raise ValueError("未找到test_cases字段")
        
        # 从test_cases往前找{
        start_idx = content.rfind("{", 0, test_cases_idx)
        if start_idx == -1:
            raise ValueError("未找到JSON开始标记 {")
        
        content = content[start_idx:last_brace+1]
        await send_log("info", f"✅ 提取JSON成功: {len(content)} 字")
        
        print(f"[生成用例] 解析内容长度: {len(content)}, 前100字: {content[:100]}", flush=True)
        
        result = json.loads(content)
        cases_data = result.get("test_cases", [])
        await send_log("success", f"✅ 成功解析到 {len(cases_data)} 条测试用例")
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        await send_log("error", f"❌ 解析失败: {str(e)}")
        await send_log("error", f"原始内容前200字: {raw[:200]}")
        print(f"[生成用例] 解析失败: {e}", flush=True)
        print(f"[生成用例] 原始内容前500字: {raw[:500]}", flush=True)
        raise HTTPException(500, f"LLM 返回格式错误: {str(e)}")
    
    # 保存用例
    await send_log("info", f"💾 正在保存 {len(cases_data)} 条测试用例到数据库...")
    created_cases = []
    for idx, case_data in enumerate(cases_data):
        tc = TestCase(
            project_id=project.id,
            page_id=page.id,
            title=case_data.get("title", f"测试用例 {idx + 1}"),
            description=case_data.get("description", ""),
            script_content=case_data.get("script_content", ""),
            group_name=page.full_path,  # 使用页面路径作为分组
        )
        db.add(tc)
        created_cases.append(tc)
    
    await db.commit()
    for tc in created_cases:
        await db.refresh(tc)
    
    await send_log("success", f"✅ 成功生成并保存 {len(created_cases)} 条测试用例")
    return created_cases


@router.get("/{page_id}/cases")
async def get_page_cases(page_id: str, db: AsyncSession = Depends(get_db)):
    """获取页面下的所有用例（包括子页面）"""
    page = await db.get(TestPage, page_id)
    if not page:
        raise HTTPException(404, "页面不存在")
    
    # 获取该页面及所有子页面的 ID
    async def get_all_child_page_ids(parent_id: str) -> list[str]:
        result = await db.execute(
            select(TestPage.id).where(TestPage.parent_id == parent_id)
        )
        child_ids = [row[0] for row in result.all()]
        
        all_ids = list(child_ids)
        for child_id in child_ids:
            all_ids.extend(await get_all_child_page_ids(child_id))
        
        return all_ids
    
    page_ids = [page_id] + await get_all_child_page_ids(page_id)
    
    # 查询这些页面的所有用例
    result = await db.execute(
        select(TestCase)
        .where(TestCase.page_id.in_(page_ids))
        .order_by(TestCase.created_at.desc())
    )
    cases = result.scalars().all()
    
    return cases


# 需要导入 update
from sqlalchemy import update
