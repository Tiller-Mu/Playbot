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

    from app.models.semantic_ir import TestCasePlan
    schema_json = json.dumps(TestCasePlan.model_json_schema(), ensure_ascii=False)
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个专业的测试用例规划专家。"
                "用户会给你一个现有的测试用例大纲（JSON 格式的 TestCasePlan），"
                "以及一条自然语言修改指令。"
                "请根据指令修改测试用例大纲，返回更新后的 JSON 计划。\n\n"
                "【核心原则】\n"
                "1. 你绝对不能写任何 Python 代码、Playwright API、CSS Selector。\n"
                "2. 你只输出语义化的步骤描述，包含: action(动作类型)、target_hint(元素特征)、intent_reason(业务意图)。\n"
                "3. target_hint 必须包含 text(可见文本)、tag(标签名)、role(ARIA角色) 等线索。\n"
                "4. 保留原计划中的 dom_fragment 和 recorded_selector，它们是执行引擎的兜底策略。\n"
                "5. 每个关键操作后必须规划断言步骤（如 expect_visible 或 expect_text）。\n"
                f"6. 只返回 JSON 格式，严格遵循以下 Schema:\n{schema_json}\n"
            ),
        },
        {
            "role": "user",
            "content": (
                f"当前用例标题: {tc.title}\n"
                f"当前用例计划 (TestCasePlan JSON):\n{tc.description}\n\n"
                f"修改指令: {data.instruction}\n\n"
                "请直接返回修改后的 TestCasePlan JSON。"
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

    # result 是 TestCasePlan JSON，整体存入 description 供 ExecutionEngine 消费
    tc.description = json.dumps(result, ensure_ascii=False, indent=2)
    # script_content 保留旧值，执行引擎从 description 读取 JSON Plan
    tc.script_content = tc.script_content or ""
    await db.commit()
    await db.refresh(tc)

    return NLEditResponse(
        description=tc.description,
        script_content=tc.script_content or "",
    )


@router.post("/{case_id}/compile")
async def compile_testcase(case_id: str, db: AsyncSession = Depends(get_db)):
    """将语义用例大纲进行二次审查优化 (Phase 2 Auditor)"""
    from app.models.database import ActionTrace, TestPage
    from sqlalchemy import select
    import json
    
    tc = await db.get(TestCase, case_id)
    if not tc:
        raise HTTPException(404, "用例不存在")
        
    if not tc.page_id:
        raise HTTPException(400, "该用例未绑定页面，无法获取上下文进行编译")
        
    page = await db.get(TestPage, tc.page_id)
    
    # 提取 Vue 源码
    source_code = "未找到页面组件源码"
    if page and page.file_path:
        from app.core.config import settings
        full_path = settings.workspace_dir / page.file_path
        if full_path.exists():
            source_code = full_path.read_text(encoding="utf-8")
            import re
            source_code = re.sub(r'<style[^>]*>.*?</style>', '', source_code, flags=re.DOTALL)

    # 获取关联的 ActionTrace 作为物理 DOM 上下文
    trace_query = select(ActionTrace).where(ActionTrace.page_id == tc.page_id).order_by(ActionTrace.created_at.desc()).limit(1)
    trace_result = await db.execute(trace_query)
    trace = trace_result.scalars().first()
    
    trace_context = "暂无物理轨迹数据"
    if trace:
        trace_context = trace.trace_data

    from app.models.semantic_ir import TestCasePlan
    schema_json = json.dumps(TestCasePlan.model_json_schema(), ensure_ascii=False)

    system_prompt = (
        "你是一个顶级的 Playwright QA 自动化测试审核专家 (Auditor)。\n"
        "你的任务是接收一份【初稿语义测试大纲（JSON格式）】、前端 Vue 源码以及用户的真实【物理操作轨迹】，"
        "对初稿进行严厉的逻辑审查，并输出一份【修复并完善后的纯 JSON 数据】。\n\n"
        "【核心审查原则】\n"
        "1. 查找缺失的触发动作：很多时候初稿会在没有点击“保存/验证/提交”按钮的情况下，直接去 `expect_visible` 等待 Toast 提示出现。这是极其愚蠢的跳步！你必须仔细对比源码，发现这种断言前遗漏的点击或输入操作，并将它们补充到步骤列表中。\n"
        "2. 修复无效的选择器：检查 target_hint 中的内容是否过于含糊，如果 ActionTrace 提供了更有力的属性，补充进去。\n"
        "3. navigate 动作用 value 字段填 URL：导航目标 URL 必须填入 value 字段，绝对不能填入 url 字段（url 是录制元数据）。\n"
        "4. 纯净输出：直接输出原生 JSON，禁止使用 markdown 代码块包裹，不要包含任何前后缀解释文字！\n"
        f"必须严格遵循以下 Schema 输出 JSON 对象：\n{schema_json}"
    )

    user_prompt = (
        f"用例标题：{tc.title}\n\n"
        f"【初稿测试大纲 (JSON)】:\n{tc.description}\n\n"
        f"【前端 Vue 源码】:\n{source_code[:6000]}\n\n"
        f"【物理操作轨迹 (ActionTrace)】:\n{trace_context[:6000]}\n\n"
        "请深思熟虑，修复遗漏的交互步骤，直接返回优化后的 JSON 数据。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    from app.core.websocket import ws_manager
    
    channel = f"mcp_{tc.project_id}"
    
    await ws_manager.broadcast({
        "type": "agent_log",
        "page_id": tc.page_id,
        "level": "info",
        "message": f"[Phase 2 审计] 正在审查并优化用例 JSON 逻辑：《{tc.title}》..."
    }, channel=channel)

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
        
        import json_repair
        repaired_str = json_repair.repair_json(raw_script)
        if not repaired_str:
            raise Exception("审查引擎返回了空的 JSON")
            
        parsed_obj = json.loads(repaired_str)
        if isinstance(parsed_obj, list) and len(parsed_obj) > 0:
            parsed_obj = parsed_obj[0]
            
        refined_case = TestCasePlan.model_validate(parsed_obj)
        
        json_content = refined_case.model_dump_json(indent=2, ensure_ascii=False)
        tc.description = json_content
        tc.script_content = f"# 本用例已由 AI 审查引擎深度优化，修复了诸如缺失点击、断言前未触发事件等逻辑漏洞。\n# 执行引擎将直接读取原生 JSON 进行寻址和操作，无需 Python 脚本翻译。\n\n{json_content}"
        tc.is_compiled = True
        await db.commit()
        await db.refresh(tc)
        
        await ws_manager.broadcast({
            "type": "agent_log",
            "page_id": tc.page_id,
            "level": "info",
            "message": f"✅ [审计成功] 《{tc.title}》已完成逻辑补全和优化"
        }, channel=channel)
    except Exception as e:
        await ws_manager.broadcast({
            "type": "agent_log",
            "page_id": tc.page_id,
            "level": "error",
            "message": f"❌ [审计失败] 无法解析大模型审查结果: {str(e)}"
        }, channel=channel)
        raise e
        
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


