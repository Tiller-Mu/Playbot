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
                "4. 【极端重要】对于任何元素的点击操作（`.click()`），尤其是前端UI组件库（如 Ant Design 的 Select，Dropdown 等），常常由于内部复杂的 span 层级导致 `intercepts pointer events` 错误。你必须在所有的 click 操作中加上 `force=True`（例如 `locator.click(force=True)`），强制跳过默认遮挡检测。\n"
                "5. 避开严格模式(Strict Mode)与精准定位：严禁无脑使用 .first！应优先使用 exact=True (如 get_by_text('xx', exact=True))、get_by_role('option')、filter(visible=True) 或限定父级范围，确保命中需要真实交互的元素。\n"
                "6. 代码中加中文注释说明每个步骤\n"
                "7. 只返回 JSON 格式: {\"description\": \"...\", \"script_content\": \"...\"}\n"
                "8. 【定位器高危警告】绝对不要生造元素的标签名（如凭空写出 `div#provider-select`，直接写 `#provider-select` 即可）。严禁使用多个 `.locator(...).locator(...)` 级联去强行寻找内部 span！直接对带有特征（如 ID 或 class）的元素执行 `.click(force=True)` 即可！"
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


@router.post("/{case_id}/compile")
async def compile_testcase(case_id: str, db: AsyncSession = Depends(get_db)):
    """将语义用例大纲编译为可执行的 Pytest-Playwright 脚本 (Phase 2)"""
    from app.models.database import ActionTrace
    from sqlalchemy import select

    tc = await db.get(TestCase, case_id)
    if not tc:
        raise HTTPException(404, "用例不存在")
        
    if not tc.page_id:
        raise HTTPException(400, "该用例未绑定页面，无法获取上下文进行编译")

    # 获取关联的 ActionTrace 作为物理 DOM 上下文
    trace_query = select(ActionTrace).where(ActionTrace.page_id == tc.page_id).order_by(ActionTrace.created_at.desc()).limit(1)
    trace_result = await db.execute(trace_query)
    trace = trace_result.scalars().first()
    
    trace_context = "暂无物理轨迹数据"
    if trace:
        trace_context = trace.trace_data

    # 构建专门用于代码编译的 System Prompt
    system_prompt = (
        "你是一个顶级的 Playwright QA 自动化测试专家。\n"
        "你的任务是接收一份【纯语义测试大纲（JSON格式）】和一份【物理操作轨迹（包含 DOM特征）】，"
        "并输出一份可以直接运行的 Pytest-Playwright (sync API) Python 测试代码。\n\n"
        "【强制规范】\n"
        "1. 使用 `def test_xxx(page: Page):` 作为函数入口，并导入必要的模块 (如 `from playwright.sync_api import Page, expect`)。\n"
        "2. 根据传入的语义大纲中的 `steps` 生成代码。利用物理操作轨迹（trace_data）中的 `dom_fragment`、`path` 或属性来推断最精准的 Locator。\n"
        "3. 严禁使用毫无意义的绝对 CSS 路径或深度嵌套（如 `.class > div:nth-child(2)`）。优先使用 `get_by_role`, `get_by_text`, `get_by_placeholder`, 或带有明确描述的 CSS 类。\n"
        "4. 【极端重要】对于任何元素的点击操作（`.click()`），尤其是前端UI组件库（如 Ant Design 的 Select，Dropdown 等），常常由于内部复杂的 span 层级导致 `intercepts pointer events` 错误。你必须在所有的 click 操作中加上 `force=True`（例如 `locator.click(force=True)`），强制跳过默认遮挡检测。\n"
        "5. 所有的 expect 断言（`expect_visible`, `expect_text`）必须真实地通过 `expect(locator).to_be_visible()` 等 Playwright 断言实现。\n"
        "6. 代码需包含中文注释解释每一步的 `intent_reason`。\n"
        "7. 只需要输出纯 Python 代码，严禁包裹在 ```python ... ``` 块中，也不要附带任何多余的解释文字，从第一行直接开始写 Python 代码！\n"
        "8. 【定位器高危警告】绝对不要生造元素的标签名（如凭空写出 `div#provider-select`，直接写 `#provider-select` 即可）。严禁使用多个 `.locator(...).locator(...)` 级联去强行寻找内部 span！直接对带有特征（如 ID 或 class）的元素执行 `.click(force=True)` 即可！"
    )

    user_prompt = (
        f"用例标题：{tc.title}\n\n"
        f"【纯语义测试大纲】（即 description）:\n{tc.description}\n\n"
        f"【物理操作轨迹】（用于推断 DOM Locator）:\n{trace_context}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    from app.core.websocket import ws_manager
    from datetime import datetime
    
    channel = f"mcp_{tc.project_id}"
    
    await ws_manager.broadcast({
        "type": "agent_log",
        "page_id": tc.page_id,
        "level": "info",
        "message": f"[Phase 2 编译] 正在将语义大纲转化为可执行脚本：《{tc.title}》..."
    }, channel=channel)

    # 调用大模型生成代码
    from app.services.llm_service import llm_chat_stream
    
    buffer = []
    async def on_token_callback(token_text: str):
        buffer.append(token_text)
        await ws_manager.broadcast({
            "type": "agent_log",
            "page_id": tc.page_id,
            "level": "stream",
            "message": "".join(buffer)
        }, channel=channel)

    try:
        raw_script = await llm_chat_stream(messages, temperature=0.1, on_token=on_token_callback)
        await ws_manager.broadcast({
            "type": "agent_log",
            "page_id": tc.page_id,
            "level": "info",
            "message": f"✅ [编译成功] 《{tc.title}》的代码已生成"
        }, channel=channel)
    except Exception as e:
        await ws_manager.broadcast({
            "type": "agent_log",
            "page_id": tc.page_id,
            "level": "error",
            "message": f"❌ [编译失败] {str(e)}"
        }, channel=channel)
        raise e
    
    # 清洗可能带有的 markdown 代码块
    cleaned_script = raw_script.strip()
    if cleaned_script.startswith("```"):
        cleaned_script = cleaned_script.split("\n", 1)[-1]
        if cleaned_script.endswith("```"):
            cleaned_script = cleaned_script[:-3]
    elif cleaned_script.startswith("```python"):
        cleaned_script = cleaned_script.split("\n", 1)[-1]
        if cleaned_script.endswith("```"):
            cleaned_script = cleaned_script[:-3]
            
    # 直接覆写现有的脚本内容，并设置已编译标记
    tc.script_content = cleaned_script.strip()
    tc.is_compiled = True
    await db.commit()
    await db.refresh(tc)

    return tc


from app.schemas.schemas import HealRequest

@router.post("/{case_id}/heal")
async def heal_testcase(case_id: str, data: HealRequest, db: AsyncSession = Depends(get_db)):
    """AI 自愈回环：根据执行失败的报错堆栈自动修复代码"""
    from app.core.websocket import ws_manager
    from datetime import datetime
    
    tc = await db.get(TestCase, case_id)
    if not tc:
        raise HTTPException(404, "用例不存在")
        
    channel = f"mcp_{tc.project_id}"
    
    await ws_manager.broadcast({
        "type": "agent_log",
        "page_id": tc.page_id,
        "level": "info",
        "message": f"[🏥 脚本自愈] 正在分析报错并重构代码：《{tc.title}》..."
    }, channel=channel)

    system_prompt = (
        "你是一个顶级的 Playwright 自动化测试修 Bug 专家。\n"
        "这端代码刚刚在真实浏览器中执行失败了。你需要阅读具体的【报错堆栈】(Call log)，分析错误原因（例如 Locator Timeout，或者 intercepts pointer events 遮挡），并重新编写这段测试脚本来修复它。\n"
        "【修复指南】\n"
        "1. 仔细阅读 Call log 的最后几行，如果是被其它元素（如 ant-select-selection-item）遮挡，务必在 click 操作加上 `force=True`。\n"
        "2. 如果是等不到元素，检查 Locator 是否写错了，尝试用更宽松的匹配（如 `exact=False` 的 get_by_text，或者跳过深层包裹元素，直接找外层特征）。\n"
        "3. 保持原有测试用例的逻辑完整性。只输出修复后的 Pytest-Playwright Python 代码。\n"
        "4. 严禁包裹在 ```python ``` 块中，直接从第一行输出 Python 代码。\n"
        "5. 【高危警告】绝对禁止为了找一个文本，盲目使用 `.locator('..')` 去向上爬树！请直接寻找明确的文字或组件容器。\n"
    )

    user_prompt = (
        f"用例标题：{tc.title}\n"
        f"原语义大纲：\n{tc.description}\n\n"
        f"原执行代码：\n{tc.script_content}\n\n"
        f"【执行报错堆栈】(请仔细分析这里)：\n{data.error_message}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    from app.services.llm_service import llm_chat_stream
    
    buffer = []
    async def on_token_callback(token_text: str):
        buffer.append(token_text)
        await ws_manager.broadcast({
            "type": "agent_log",
            "page_id": tc.page_id,
            "level": "stream",
            "message": "".join(buffer)
        }, channel=channel)

    try:
        raw_script = await llm_chat_stream(messages, temperature=0.1, on_token=on_token_callback)
        await ws_manager.broadcast({
            "type": "agent_log",
            "page_id": tc.page_id,
            "level": "info",
            "message": f"✅ [自愈成功] 《{tc.title}》的 Bug 已被修复，快去验证吧！"
        }, channel=channel)
    except Exception as e:
        await ws_manager.broadcast({
            "type": "agent_log",
            "page_id": tc.page_id,
            "level": "error",
            "message": f"❌ [自愈失败] {str(e)}"
        }, channel=channel)
        raise e
    
    cleaned_script = raw_script.strip()
    if cleaned_script.startswith("```"):
        cleaned_script = cleaned_script.split("\n", 1)[-1]
        if cleaned_script.endswith("```"):
            cleaned_script = cleaned_script[:-3]
    elif cleaned_script.startswith("```python"):
        cleaned_script = cleaned_script.split("\n", 1)[-1]
        if cleaned_script.endswith("```"):
            cleaned_script = cleaned_script[:-3]
            
    tc.script_content = cleaned_script.strip()
    tc.is_compiled = True
    await db.commit()
    await db.refresh(tc)

    return tc


