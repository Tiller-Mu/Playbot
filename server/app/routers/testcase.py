from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import TestCase, get_db
from app.schemas.schemas import (
    TestCaseCreate,
    TestCaseUpdate,
    TestCaseOut,
    NLEditRequest,
    NLEditResponse,
)
from app.services.llm_service import llm_chat

router = APIRouter(prefix="/api/testcase", tags=["testcase"])


@router.get("", response_model=list[TestCaseOut])
async def list_testcases(
    project_id: str = Query(...),
    group_name: str | None = None,
    enabled: bool | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(TestCase).where(TestCase.project_id == project_id)
    if group_name:
        query = query.where(TestCase.group_name == group_name)
    if enabled is not None:
        query = query.where(TestCase.enabled == enabled)
    if search:
        query = query.where(
            TestCase.title.contains(search) | TestCase.description.contains(search)
        )
    query = query.order_by(TestCase.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{case_id}", response_model=TestCaseOut)
async def get_testcase(case_id: str, db: AsyncSession = Depends(get_db)):
    tc = await db.get(TestCase, case_id)
    if not tc:
        raise HTTPException(404, "用例不存在")
    return tc


@router.post("", response_model=TestCaseOut)
async def create_testcase(data: TestCaseCreate, db: AsyncSession = Depends(get_db)):
    tc = TestCase(**data.model_dump())
    db.add(tc)
    await db.commit()
    await db.refresh(tc)
    return tc


@router.put("/{case_id}", response_model=TestCaseOut)
async def update_testcase(
    case_id: str, data: TestCaseUpdate, db: AsyncSession = Depends(get_db)
):
    tc = await db.get(TestCase, case_id)
    if not tc:
        raise HTTPException(404, "用例不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(tc, field, value)
    await db.commit()
    await db.refresh(tc)
    return tc


@router.delete("/{case_id}")
async def delete_testcase(case_id: str, db: AsyncSession = Depends(get_db)):
    tc = await db.get(TestCase, case_id)
    if not tc:
        raise HTTPException(404, "用例不存在")
    await db.delete(tc)
    await db.commit()
    return {"message": "用例已删除"}


@router.post("/{case_id}/edit", response_model=NLEditResponse)
async def nl_edit_testcase(
    case_id: str, data: NLEditRequest, db: AsyncSession = Depends(get_db)
):
    """用自然语言修改测试用例，LLM 同步更新代码。"""
    tc = await db.get(TestCase, case_id)
    if not tc:
        raise HTTPException(404, "用例不存在")

    messages = [
        {
            "role": "system",
            "content": (
                "你是一个 Playwright Python 测试脚本专家。"
                "用户会给你一个现有的测试用例（包含自然语言描述和 Python 测试代码），"
                "以及一条自然语言修改指令。"
                "请根据指令修改测试用例，返回更新后的自然语言描述和完整的 Python 测试代码。\n\n"
                "要求：\n"
                "1. 使用 pytest + playwright (sync_api)\n"
                "2. 测试函数参数为 page: Page\n"
                "3. 使用 expect() 做断言\n"
                "4. 遇到前端UI库（如 Ant Design 的 Select 组件）中被 span 层拦截导致 Timeout 时，务必使用 locator.click(force=True)\n"
                "5. 避开严格模式(Strict Mode)与精准定位：严禁无脑使用 .first！应优先使用 exact=True (如 get_by_text('xx', exact=True))、get_by_role('option')、filter(visible=True) 或限定父级范围，确保命中需要真实交互的元素。\n"
                "6. 代码中加中文注释说明每个步骤\n"
                "7. 只返回 JSON 格式: {\"description\": \"...\", \"script_content\": \"...\"}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"当前用例标题: {tc.title}\n"
                f"当前自然语言描述:\n{tc.description}\n\n"
                f"当前测试代码:\n```python\n{tc.script_content or '# 暂无代码'}\n```\n\n"
                f"修改指令: {data.instruction}"
            ),
        },
    ]

    import json
    raw = await llm_chat(messages, temperature=0.2)
    # Try to parse JSON from response
    try:
        # Handle markdown code blocks in response
        content = raw.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(500, f"LLM 返回格式错误: {raw[:200]}")

    tc.description = result.get("description", tc.description)
    tc.script_content = result.get("script_content", tc.script_content)
    await db.commit()
    await db.refresh(tc)

    return NLEditResponse(
        description=tc.description,
        script_content=tc.script_content or "",
    )
