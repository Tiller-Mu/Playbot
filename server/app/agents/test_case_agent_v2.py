"""
测试用例生成智能体 - 基于LangGraph实现
独立的、无状态的代理包，不依赖宿主的数据库或核心配置
"""
from typing import Dict, Any, List, Optional, Callable, TypedDict, Annotated
import operator
from datetime import datetime
import json
import asyncio
import os
import re

from langgraph.graph import StateGraph, END

from .tools import CodeAnalyzerTool, DOMExtractorTool, TestStrategyTool
from .langfuse_utils import get_langfuse_callback_handler
from .schemas import AgentConfig, TestCaseInput
from .utils.python_validator import validate_python_code
from pydantic import BaseModel, Field


class SingleCasePlan(BaseModel):
    title: str = Field(description="测试用例标题，注意要用人类可读的短语，严禁使用...占位符。")
    description: str = Field(description="该用例执行的具体测试意图、断点和操作流程描述。")

class PlannedCasesOutput(BaseModel):
    thought: str = Field(description="分析该页面特征与策略，输出为什么这么设计用例的思考与依据")
    cases: list[SingleCasePlan] = Field(description="规划出的独立测试用例列表。请根据页面特征产出最合理数量的测试用例，自然拆分相关意图，无需刻意增减数量。")


class AgentState(TypedDict, total=False):
    input_data: TestCaseInput
    source_code: str
    dom_data: Any
    code_analysis: str
    dom_analysis: str
    test_strategy: str
    planned_cases: List[Dict[str, Any]]
    current_case_index: int
    current_case_feedback: str
    retry_count: int
    raw_llm_response: str
    test_cases: Annotated[List[Dict[str, Any]], operator.add]
    logs: Annotated[List[str], operator.add]
    error: Optional[str]


class TestCaseAgent:
    def __init__(self, config: AgentConfig, log_callback: Optional[Callable[[str, str], None]] = None):
        self.config = config
        self.log_callback = log_callback
        self.code_tool = CodeAnalyzerTool()
        self.dom_tool = DOMExtractorTool()
        self.strategy_tool = TestStrategyTool()
        self.graph = self._build_graph()
    
    async def _log(self, level: str, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        if self.log_callback:
            await self.log_callback(level, log_msg)
        return log_msg
    
    def _build_graph(self) -> StateGraph:
        async def analyze_code(state: AgentState) -> dict:
            logs_delta = [await self._log("info", "🔬 获取并分析代码结构...")]
            source_code = state.get("source_code")
            if not source_code:
                file_path = state["input_data"].file_path
                if file_path and os.path.exists(file_path):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            source_code = f.read()
                    except Exception as e:
                        logs_delta.append(await self._log("error", f"❌ 读取源码文件失败: {e}"))
                else:
                    source_code = ""
            try:
                result = await self.code_tool.arun({"source_code": source_code, "file_path": state["input_data"].file_path or "", "analysis_depth": "basic"})
                logs_delta.append(await self._log("info", "✅ 代码分析完成"))
                return {"source_code": source_code, "code_analysis": result, "logs": logs_delta}
            except Exception as e:
                logs_delta.append(await self._log("error", f"❌ 代码分析失败: {e}"))
                return {"error": f"代码分析失败: {e}", "source_code": source_code, "logs": logs_delta}
        
        async def analyze_dom(state: AgentState) -> dict:
            logs_delta = [await self._log("info", "🔬 提取DOM元素特征...")]
            dom_data = state.get("dom_data")
            if not dom_data:
                json_path = state["input_data"].dom_json_path
                if json_path and os.path.exists(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            dom_data = json.load(f)
                    except Exception as e:
                        pass
            if not dom_data:
                return {"dom_data": None, "dom_analysis": "无DOM数据", "logs": logs_delta}
            try:
                dom_str = json.dumps(dom_data, ensure_ascii=False) if not isinstance(dom_data, str) else dom_data
                result = await self.dom_tool.arun({"dom_data": dom_str, "extract_type": "interactive"})
                logs_delta.append(await self._log("info", "✅ DOM分析提取完成"))
                return {"dom_data": dom_data, "dom_analysis": result, "logs": logs_delta}
            except Exception as e:
                logs_delta.append(await self._log("error", f"❌ DOM分析失败: {e}"))
                return {"error": f"DOM分析失败: {e}", "dom_data": dom_data, "logs": logs_delta}
        
        async def analyze_strategy(state: AgentState) -> dict:
            logs_delta = [await self._log("info", "🎯 分析测试策略...")]
            try:
                result = await self.strategy_tool.arun({
                    "code_analysis": state.get("code_analysis", ""),
                    "dom_analysis": state.get("dom_analysis", ""),
                    "page_path": state["input_data"].file_path or ""
                })
                logs_delta.append(await self._log("info", "✅ 策略分析完成"))
                return {"test_strategy": result, "logs": logs_delta}
            except Exception as e:
                logs_delta.append(await self._log("error", f"❌ 策略分析失败: {e}"))
                return {"error": f"策略分析失败: {e}", "logs": logs_delta}
        
        async def plan_cases(state: AgentState) -> dict:
            logs_delta = [await self._log("info", "📝 正在制定测试用例大纲计划...")]
            system_prompt = """你是一个专业的Playwright测试架构师。
基于提供的策略分析和页面全量信息，分解出你需要编写的各个单一测试用例计划。
要求：基于页面的模块逻辑，产出最合理数量的、能够独立运行的测试大纲（只需覆盖真实的核心正反向场景，不过度拆分，也不盲目合并），包含该测试的标题和具体的意图说明。
严禁使用 "..." 等省略号，每个用例都必须具备完整的意图！

【强制响应格式要求】
你必须且仅能返回一个包含双通道数据的纯净 JSON 对象！绝不允许使用 ```json 等 Markdown 标记块结构来包裹数据！！
首先在 `thought` 字段中写下你的深度推理和决策，最后在 `cases` 字段中输出最终用例！
示例：
{
  "thought": "页面拥有完整的登录树和设置选项卡，应该分别测试...",
  "cases": [
    {"title": "测试保存设置", "description": "测试正常的保存流验证"}
  ]
}"""
            user_prompt = f"""【测试策略总旨】
{state.get('test_strategy', '')}

【目标页面运行时 DOM 树特征】
{state.get('dom_analysis', '无DOM特征数据')}

【目标页面核心代码架构】
{state.get('code_analysis', '无代码分析数据')}

【目标页面原始源码全貌】
```
{state.get('source_code') or '由于缺少文件路径，未能加载源码'}
```

请结合以上真实的 DOM 结构图和源码，产出最合理数量的测试用例流。保持每个用例的功能聚焦即可，严禁使用 "..." 占位！"""
            try:
                if self.config.structured_llm_caller:
                    result_obj = await self.config.structured_llm_caller(
                        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], 
                        PlannedCasesOutput
                    )
                    planned_cases = [case.model_dump() for case in result_obj.cases]
                else:
                    response = await self.config.llm_caller([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}])
                    response = response.strip()
                    
                    # 容错：直接尝试提取 cases 的数组
                    # 增强型 JSON Array 兜底解析：即使大模型带有 thought，我们也只去找带有 [ ] 的 cases 内容
                    match = re.search(r'"cases"\s*:\s*(\[.*?\])\s*\}?', response, re.DOTALL)
                    if match:
                        planned_cases = json.loads(match.group(1))
                    else:
                        # 兜底到原来的提取
                        fallback_match = re.search(r'\[.*\]', response, re.DOTALL)
                        if fallback_match:
                            planned_cases = json.loads(fallback_match.group(0))
                        else:
                            if '```json' in response.lower():
                                content = response.split('```')[1].replace('json', '', 1).strip()
                                data = json.loads(content)
                                planned_cases = data.get("cases", data) if isinstance(data, dict) else data
                            else:
                                data = json.loads(response)
                                planned_cases = data.get("cases", data) if isinstance(data, dict) else data
                                
                logs_delta.append(await self._log("success", f"✅ 计划完成，即将生成 {len(planned_cases)} 个流水线用例任务..."))
                return {"planned_cases": planned_cases, "logs": logs_delta, "current_case_index": 0}
            except Exception as e:
                err_msg = f"计划生成失败或Schema解析异常: {e}"
                logs_delta.append(await self._log("error", f"❌ {err_msg}"))
                return {"error": err_msg, "logs": logs_delta}

        async def generate_single_case(state: AgentState) -> dict:
            idx = state.get("current_case_index", 0)
            cases = state.get("planned_cases", [])
            if idx >= len(cases): return {}
            current_task = cases[idx]
            retry = state.get("retry_count", 0)
            logs_delta = []
            
            if retry == 0:
                logs_delta.append(await self._log("info", f"🔨 [子任务 {idx+1}/{len(cases)}] 开始编写: {current_task.get('title')}"))
            else:
                logs_delta.append(await self._log("warning", f"⚠️ [用例 {idx+1}/{len(cases)}] 第 {retry} 次重修: {current_task.get('title')}"))
            
            playwright_cheat_sheet = """
【Playwright 常用语法速查手册 (Cheat Sheet)】
• 定位元素: 
  - page.locator(".class-name") / page.locator("#id") / page.locator("text=确认")
  - page.get_by_role("button", name="提交")
  - page.get_by_placeholder("请输入")
• 常见动作: 
  - locator.click() / locator.fill("text") / locator.press("Enter") 
  - locator.hover() / locator.check()
• 断言 (expect):
  - expect(locator).to_be_visible() / expect(locator).not_to_be_empty()
  - expect(locator).to_have_text("预期文本") / expect(locator).to_have_value("值")
  - expect(page).to_have_url(re.compile(".*dashboard"))
"""
            system_prompt = f"""你是一个专业的Playwright测试用例编程专家。
为一个具体的测试任务编写能够直接运行的独立Python脚本。
{playwright_cheat_sheet}
代码要求：
1. 务必使用下方 Context 中提供的真实的CSS选择器，参考上述速查手册的标准语法。
2. 在动手写 Python 代码之前，你必须使用 <thinking></thinking> 标签包裹你的思考过程（分析意图、决定查找哪些真实 DOM，使用何种断言）。
3. 思考完毕后，严格按照下面的模板输出最终代码，绝对不要在代码块以外输出额外的中文闲聊！
4. 你的这个 Python 文件中只能包含当前这 1 个测试用例，绝对不要将多个毫不相干的测试写在一块儿！

输出格式模板必须严格遵循：
<thinking>
1. 需求分析：...
2. 定位 DOM：用 page.locator("...") 还是 get_by_role...
3. 断言设计：...
</thinking>

```python
import pytest
from playwright.sync_api import Page, expect

def test_xxx_xxx(page: Page):
    # 你的所有测试动作与预期断言...
```"""
            feedback = state.get("current_case_feedback", "")
            if feedback:
                user_prompt = f"""该测试任务在 Python AST 编译器审查中遭到了【报错打回】！
【致命编译报错原因】：{feedback}
【你上次抛出的病态代码】：
{state.get('raw_llm_response', '')}

> 请注意：上面的错误通常是因为你忘记导入库、缺少括号、缩进断裂，或者是在纯代码块中混入了中文解释性废话。
> 请深呼吸，修复这个该死的错误，然后重新、严格、且仅仅输出通过了词法校验的独立 Python 代码块！！！"""
            else:
                user_prompt = f"""当前需编写的新测试子任务：
【用例标题】：{current_task.get('title')}
【核心意图】：{current_task.get('description')}

================ Context ================
【页面URL】: {state.get('input_data').page_url if state.get('input_data') else '无'}
【本地代码路径】: {state.get('input_data').file_path if state.get('input_data') else '无'}

【总局测试策略指导】
{state.get('test_strategy', '无特定策略指导')}

【目标页面运行时 DOM 树提取特征】
{state.get('dom_analysis', '无DOM特征数据')}

【目标页面核心代码架构分析】
{state.get('code_analysis', '无代码分析数据')}

【目标页面原始源码全貌】
```
{state.get('source_code') or '由于缺少文件路径，未能加载源码'}
```
=========================================

请严格匹配源码中绑定的业务逻辑和 DOM 分析提供的真实 id / class / placeholder 等特征，编写出精准打击的 Playwright 断言脚本。"""
            try:
                response = await self.config.llm_caller([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}])
                return {"raw_llm_response": response, "logs": logs_delta}
            except Exception as e:
                logs_delta.append(await self._log("error", f"❌ 编码流水线故障: {e}"))
                return {"error": f"编码流水线故障: {e}", "logs": logs_delta}

        async def validate_single_case(state: AgentState) -> dict:
            idx = state.get("current_case_index", 0)
            task = state.get("planned_cases", [])[idx]
            code_str = state.get("raw_llm_response", "")
            logs_delta = []
            
            clean_code = code_str.strip()
            if "```" in clean_code:
                try:
                     clean_code = re.search(r'```(?:python|py)?\s*(.*?)```', clean_code, re.DOTALL).group(1).strip()
                except:
                     pass
            
            # 使用提取干净的 Python 代码块去执行词法审查
            is_valid, err_msg = validate_python_code(clean_code)
            
            new_case = {
                "title": task.get("title", f"测试用例 {idx+1}"),
                "description": task.get("description", ""),
                "script_content": clean_code,
                "enabled": True
            }
            if is_valid:
                logs_delta.append(await self._log("success", f"✅ [用例 {idx+1}] 编译验证完美通过，收录投产。"))
                return {"test_cases": [new_case], "current_case_index": idx + 1, "retry_count": 0, "current_case_feedback": "", "logs": logs_delta}
            else:
                retry = state.get("retry_count", 0)
                if retry < 3:
                    logs_delta.append(await self._log("warning", f"🚨 [用例 {idx+1}] 查杀出语法错误，已打回大模型复写重修。"))
                    return {"retry_count": retry + 1, "current_case_feedback": err_msg, "logs": logs_delta}
                else:
                    logs_delta.append(await self._log("error", f"❌ [用例 {idx+1}] 连续3次重修失败，已禁用该残次用例存查。"))
                    new_case["enabled"] = False
                    new_case["script_content"] = f"# ⚠️ 智能体巡检警告：经历了多次尝试仍然抱撼编译，请人工介入修复以下原由：\n# {err_msg}\n\n{new_case['script_content']}"
                    return {"test_cases": [new_case], "current_case_index": idx + 1, "retry_count": 0, "current_case_feedback": "", "logs": logs_delta}

        def route_after_step(state: AgentState) -> str:
            if state.get("error"): return "error_end"
            return "next"
            
        def route_after_planner(state: AgentState) -> str:
            if state.get("error"): return "error_end"
            planned_cases = state.get("planned_cases", [])
            if not planned_cases or len(planned_cases) == 0:
                return "error_end"
            return "generate_single_case"

        def route_after_validate(state: AgentState) -> str:
            if state.get("error"): return "error_end"
            if state.get("current_case_feedback"): return "generate_single_case"
            idx = state.get("current_case_index", 0)
            total = len(state.get("planned_cases", []))
            if idx < total: return "generate_single_case"
            return "success_end"

        workflow = StateGraph(AgentState)
        workflow.add_node("analyze_code", analyze_code)
        workflow.add_node("analyze_dom", analyze_dom)
        workflow.add_node("analyze_strategy", analyze_strategy)
        workflow.add_node("plan_cases", plan_cases)
        workflow.add_node("generate_single_case", generate_single_case)
        workflow.add_node("validate_single_case", validate_single_case)
        workflow.set_entry_point("analyze_code")
        
        workflow.add_conditional_edges("analyze_code", route_after_step, {"error_end": END, "next": "analyze_dom"})
        workflow.add_conditional_edges("analyze_dom", route_after_step, {"error_end": END, "next": "analyze_strategy"})
        workflow.add_conditional_edges("analyze_strategy", route_after_step, {"error_end": END, "next": "plan_cases"})
        workflow.add_conditional_edges("plan_cases", route_after_planner, {"error_end": END, "generate_single_case": "generate_single_case"})
        workflow.add_edge("generate_single_case", "validate_single_case")
        workflow.add_conditional_edges("validate_single_case", route_after_validate, {
            "error_end": END, "generate_single_case": "generate_single_case", "success_end": END
        })
        return workflow.compile()
    
    def _create_initial_state(self, input_data: TestCaseInput) -> AgentState:
        return {
            "input_data": input_data,
            "source_code": input_data.source_code or "",
            "dom_data": input_data.dom_data,
            "code_analysis": "",
            "dom_analysis": "",
            "test_strategy": "",
            "planned_cases": [],
            "current_case_index": 0,
            "current_case_feedback": "",
            "retry_count": 0,
            "raw_llm_response": "",
            "test_cases": [],
            "logs": [],
            "error": None
        }

    def _get_invoke_config(self):
        lh = get_langfuse_callback_handler(
            public_key=self.config.langfuse_public_key,
            secret_key=self.config.langfuse_secret_key,
            host=self.config.langfuse_host
        )
        return {"callbacks": [lh]} if lh else {}

    async def generate(self, input_data: TestCaseInput) -> Dict[str, Any]:
        await self._log("info", "🤖 智能体开始工作...")
        invoke_config = self._get_invoke_config()
        if invoke_config: await self._log("info", "📊 Langfuse 追踪回调已挂载")
        try:
            final_state = await self.graph.ainvoke(self._create_initial_state(input_data), config=invoke_config)
            if invoke_config: await self._log("info", "📊 Langfuse 追踪图状态流已结束")
            try:
                import langfuse
                langfuse.flush()
                lh = invoke_config.get("callbacks", [None])[0]
                if lh and hasattr(lh, "flush"): lh.flush()
            except: pass
            
            return {
                "test_cases": final_state.get("test_cases", []),
                "analysis": {
                    "code": final_state.get("code_analysis", ""),
                    "dom": final_state.get("dom_analysis", ""),
                    "strategy": final_state.get("test_strategy", "")
                },
                "generated_count": len(final_state.get("test_cases", [])),
                "error": final_state.get("error")
            }
        except Exception as e:
            if invoke_config: await self._log("error", f"📊 Langfuse 追踪异常退出: {e}")
            raise
