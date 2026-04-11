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
        node = {
            "id": page.id,
            "project_id": page.project_id,
            "parent_id": page.parent_id,
            "name": page.name,
            "path": page.path,
            "full_path": page.full_path,
            "is_leaf": page.is_leaf,
            "component_name": page.component_name,
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
            page = TestPage(
                project_id=project_id,
                parent_id=parent_id,
                name=node.get("name", ""),
                path=node.get("path", ""),
                full_path=node.get("full_path", ""),
                is_leaf=node.get("is_leaf", False),
                component_name=node.get("component"),
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
    """为指定页面生成测试用例"""
    page = await db.get(TestPage, page_id)
    if not page:
        raise HTTPException(404, "页面不存在")
    
    if not page.is_leaf:
        raise HTTPException(400, "只能为叶子节点（页面）生成用例")
    
    project = await db.get(Project, page.project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    
    # 读取页面文件内容作为上下文
    page_content = ""
    if project.repo_path:
        try:
            from pathlib import Path
            # 这里需要从 page 中获取 file_path，但目前没有存储
            # 暂时使用 full_path 作为提示
            page_content = f"页面路径: {page.full_path}\n"
            if page.component_name:
                page_content += f"组件名称: {page.component_name}\n"
        except Exception:
            pass
    
    # 调用 LLM 生成用例
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个资深 QA 工程师和 Playwright Python 测试专家。\n"
                f"为以下 Web 页面生成一组全面的端到端测试用例。\n\n"
                "要求：\n"
                "1. 每个用例包含: title(标题), description(自然语言描述), script_content(完整的 Python 测试代码)\n"
                "2. 测试代码使用 pytest + playwright sync_api\n"
                "3. 测试函数参数为 page: Page\n"
                "4. 使用 expect() 做断言\n"
                "5. 代码中用中文注释说明每个步骤\n"
                f"6. 被测站点 base_url: {project.base_url}\n"
                f"7. 当前页面路径: {page.full_path}\n"
                "8. 覆盖页面的主要功能、交互流程、边界情况\n"
                "9. 返回 JSON 格式: {\"test_cases\": [{\"title\": \"\", \"description\": \"\", \"script_content\": \"\"}]}"
            ),
        },
        {
            "role": "user",
            "content": f"页面信息:\n{page_content}\n\n请为该页面生成测试用例。",
        },
    ]
    
    raw = await llm_chat(messages, temperature=0.3, max_tokens=8192)
    
    # 解析 LLM 响应
    try:
        content = raw.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(content)
        cases_data = result.get("test_cases", [])
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(500, "LLM 返回格式错误")
    
    # 保存用例
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
