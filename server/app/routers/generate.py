import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Project, TestCase, get_db
from app.schemas.schemas import GenerateRequest, TestCaseOut
from app.services.llm_service import llm_chat
from app.services.analyzer import analyze_project
from app.core.config import settings

router = APIRouter(prefix="/api/generate", tags=["generate"])


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
