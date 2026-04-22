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
from jinja2 import Environment, FileSystemLoader

from .tools import CodeAnalyzerTool, DOMExtractorTool, TestStrategyTool
from .langfuse_utils import get_langfuse_callback_handler
from .schemas import AgentConfig, TestCaseInput
from app.schemas.test_schema import AgentTestBlueprint, TestCaseIntent, TestActionSchema

class AgentState(TypedDict, total=False):
    input_data: TestCaseInput
    source_code: str
    dom_data: Any
    
    page_summary: str
    element_whitelist: Dict[str, Any]
    
    blueprint: AgentTestBlueprint
    
    test_cases: Annotated[List[Dict[str, Any]], operator.add]
    logs: Annotated[List[str], operator.add]
    error: Optional[str]

class TestCaseAgent:
    def __init__(self, config: AgentConfig, log_callback: Optional[Callable[[str, str], None]] = None):
        self.config = config
        self.log_callback = log_callback
        self.graph = self._build_graph()
        
        # Setup Jinja2 Environment
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        self.jinja_env = Environment(loader=FileSystemLoader(template_dir))
    
    async def _log(self, level: str, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        if self.log_callback:
            await self.log_callback(level, log_msg)
        return log_msg
    
    def _build_graph(self) -> StateGraph:
        async def understand_page(state: AgentState) -> dict:
            logs_delta = [await self._log("info", "🔬 [步骤1] 大模型正在提取页面功能摘要...")]
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
            
            dom_data = state.get("dom_data")
            if not dom_data:
                json_path = state["input_data"].dom_json_path
                if json_path and os.path.exists(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            dom_data = json.load(f)
                    except:
                        pass

            system_prompt = "你是一个专业的前端功能分析师。请根据提供的 Vue/HTML 源码和 DOM 结构，用不超过 50 个字的简练中文，总结这个页面的核心作用和主要的交互区域。"
            user_prompt = f"【源码】\n```\n{source_code[:5000]}\n```\n\n【DOM概览】\n{str(dom_data)[:2000]}"
            
            try:
                response = await self.config.llm_caller([
                    {"role": "system", "content": system_prompt}, 
                    {"role": "user", "content": user_prompt}
                ])
                logs_delta.append(await self._log("success", f"✅ 页面理解完成: {response.strip()}"))
                return {"page_summary": response.strip(), "source_code": source_code, "dom_data": dom_data, "logs": logs_delta}
            except Exception as e:
                logs_delta.append(await self._log("error", f"❌ 页面理解失败: {e}"))
                return {"error": f"页面理解失败: {e}", "logs": logs_delta}
        
        async def extract_whitelist(state: AgentState) -> dict:
            logs_delta = [await self._log("info", "⚙️ [步骤2] 本地提取控件物理坐标白名单...")]
            dom_data = state.get("dom_data")
            whitelist = {}
            if dom_data:
                # 解析 dom_data 寻找 interactives
                interactive = []
                if isinstance(dom_data, dict):
                    interactive = dom_data.get('interactive_elements', [])
                elif isinstance(dom_data, list):
                    interactive = dom_data
                
                # 建立安全白名单字典
                for i, elem in enumerate(interactive):
                    elem_id = f"ELEM_{i:03d}"
                    placeholder = elem.get("placeholder", "").strip()
                    text_content = elem.get("text", "").strip()
                    html_id = elem.get("id", "").strip()
                    tag = elem.get("tag", "").lower()
                    
                    if html_id:
                        selector = f"locator('#{html_id}')"
                    elif placeholder:
                        safe_ph = placeholder.replace('"', '\\"')
                        selector = f'get_by_placeholder("{safe_ph}").first'
                    elif text_content and tag in ['button', 'a']:
                        safe_text = text_content.replace('"', '\\"')
                        role = "link" if tag == 'a' else "button"
                        selector = f'get_by_role("{role}", name="{safe_text}").first'
                    elif text_content:
                        safe_text = text_content.replace('"', '\\"')
                        selector = f'get_by_text("{safe_text}").first'
                    else:
                        raw_sel = elem.get("selector", "")
                        if not raw_sel:
                            if elem.get("class"): raw_sel = f".{elem.get('class').split()[0]}"
                            else: raw_sel = tag
                        safe_sel = raw_sel.replace('"', '\\"')
                        selector = f'locator("{safe_sel}").first'
                    
                    attrs = elem.get("attributes", {}) or {}
                    # Try to deduce readonly from attr, class, or unselectable
                    is_readonly = attrs.get("readonly") is not None or "readonly" in elem.get("class", "") or attrs.get("unselectable") == "on"
                    role = attrs.get("role", "")
                    
                    whitelist[elem_id] = {
                        "tag": elem.get("tag", "unknown"),
                        "text": elem.get("text", "")[:30],
                        "selector": selector,
                        "type": elem.get("type", ""),
                        "role": role,
                        "readonly": is_readonly
                    }
            
            logs_delta.append(await self._log("info", f"✅ 白名单提取完成，共获得 {len(whitelist)} 个可用靶标。"))
            return {"element_whitelist": whitelist, "logs": logs_delta}
            
        async def plan_and_orchestrate(state: AgentState) -> dict:
            logs_delta = [await self._log("info", "🧠 [步骤3] 调度大模型输出结构化意图 JSON...")]
            summary = state.get("page_summary", "")
            whitelist = state.get("element_whitelist", {})
            
            # Format whitelist for LLM
            whitelist_str_lines = []
            for k, v in whitelist.items():
                desc = f"[{k}] 标签: <{v['tag']}>"
                if v['type']: desc += f" 类型: {v['type']}"
                if v['role']: desc += f" 角色: {v['role']}"
                if v.get('readonly'): desc += f" [⚠️只读状态(不能fill,请改用click)]"
                if v['text']: desc += f" 文本/内容: '{v['text']}'"
                whitelist_str_lines.append(desc)
            whitelist_str = "\n".join(whitelist_str_lines)
            
            system_prompt = """你是一个专业的自动化测试架构师。
你的任务是根据给定的页面摘要和严酷限定的【元素字典（白名单）】，设计出涵盖正向与异常流的测试用例集。
【核心规则】：
1. 所有的动作 target_id MUST 且 ONLY 能从下方给定的白名单 ID (如 ELEM_001) 中选取！严禁随意自创 ID！如果某个元素不在白名单里，请调整测试策略避开它。
2. 动作必须明确且颗粒度足够，比如 fill 值之后记得 click 提交。
3. 遇到组件库渲染的 下拉框/选项(combobox) 或 带有 [⚠️只读] 标记的输入框时，绝对不要使用 fill 试图填充（会引发不可控的 Playwright Timeout），必须改用明确的 click 点击展开，然后紧跟下一个选项的 click。
4. 【无断言不测试】：在每个测试用例的关键操作（如点击提交、保存、搜索等）之后，你**必须**使用大纲里的断言动作（如 `expect_visible`, `expect_text`）来验证预期结果！找白名单里可能出现的弹窗提示或结果文本做断言目标！没有断言的用例是全瞎的！"""
            
            user_prompt = f"""【页面核心功能摘要】:
{summary}

【可利用的元素字典（白名单）】:
{whitelist_str}

请输出完整的 TestCaseIntent 测试图纸！"""
            
            try:
                if self.config.structured_llm_caller:
                    blueprint = await self.config.structured_llm_caller(
                        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], 
                        AgentTestBlueprint
                    )
                else:
                    raise Exception("当前模型接口未绑定 structured_llm_caller!")
                    
                cases_count = len(blueprint.test_cases)
                logs_delta.append(await self._log("success", f"✅ 意图图纸设计完成，包含 {cases_count} 个用例流水线。"))
                return {"blueprint": blueprint, "logs": logs_delta}
            except Exception as e:
                logs_delta.append(await self._log("error", f"❌ 意图大纲生成失败: {e}"))
                return {"error": f"意图大纲生成失败: {e}", "logs": logs_delta}
                
        async def compile_to_python(state: AgentState) -> dict:
            blueprint = state.get("blueprint")
            whitelist = state.get("element_whitelist", {})
            logs_delta = [await self._log("info", "🏭 [步骤4] 启动 Jinja2 组装引擎，生成安全沙盒代码...")]
            
            test_cases = []
            try:
                template = self.jinja_env.get_template('playwright_test.py.j2')
                
                # 扁平化映射表用于模板查找
                mapping = {k: v["selector"] for k, v in whitelist.items()}
                
                import uuid
                
                for i, case in enumerate(blueprint.test_cases):
                    case_uid = str(uuid.uuid4()).replace('-', '_')[:8]
                    # 渲染 Jinja
                    script_content = template.render(
                        case_uid=case_uid,
                        case_title=case.title,
                        case_description=case.description,
                        base_url=state.get("input_data").page_url if state.get("input_data") else "http://localhost",
                        steps=case.steps,
                        mapping=mapping
                    )
                    
                    test_cases.append({
                        "title": case.title,
                        "description": case.description,
                        "script_content": script_content.strip(),
                        "enabled": True
                    })
                    
                logs_delta.append(await self._log("success", f"✅ 印刷厂流水线完成，所有 Python 代码已组装落库！"))
                return {"test_cases": test_cases, "logs": logs_delta}
            except Exception as e:
                logs_delta.append(await self._log("error", f"❌ Jinja2 渲染失败: {e}"))
                return {"error": f"代码渲染失败: {e}", "logs": logs_delta}
                

        def route_after_step(state: AgentState) -> str:
            if state.get("error"): return "error_end"
            return "next"

        workflow = StateGraph(AgentState)
        workflow.add_node("understand_page", understand_page)
        workflow.add_node("extract_whitelist", extract_whitelist)
        workflow.add_node("plan_and_orchestrate", plan_and_orchestrate)
        workflow.add_node("compile_to_python", compile_to_python)
        
        workflow.set_entry_point("understand_page")
        
        workflow.add_conditional_edges("understand_page", route_after_step, {"error_end": END, "next": "extract_whitelist"})
        workflow.add_conditional_edges("extract_whitelist", route_after_step, {"error_end": END, "next": "plan_and_orchestrate"})
        workflow.add_conditional_edges("plan_and_orchestrate", route_after_step, {"error_end": END, "next": "compile_to_python"})
        workflow.add_conditional_edges("compile_to_python", route_after_step, {"error_end": END, "next": END})
        
        return workflow.compile()
    
    def _create_initial_state(self, input_data: TestCaseInput) -> AgentState:
        return {
            "input_data": input_data,
            "source_code": input_data.source_code or "",
            "dom_data": input_data.dom_data,
            "page_summary": "",
            "element_whitelist": {},
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
        await self._log("info", "🚀 绝地反击：工业级 JSON-DSL 意图执行剥离架构启动！...")
        invoke_config = self._get_invoke_config()
        if invoke_config: await self._log("info", "📊 Langfuse 追踪回调已挂载")
        try:
            final_state = await self.graph.ainvoke(self._create_initial_state(input_data), config=invoke_config)
            
            try:
                import langfuse
                langfuse.flush()
                lh = invoke_config.get("callbacks", [None])[0]
                if lh and hasattr(lh, "flush"): lh.flush()
            except: pass
            
            return {
                "test_cases": final_state.get("test_cases", []),
                "analysis": {
                    "code": final_state.get("page_summary", ""),
                    "dom": "白名单已提取: " + str(len(final_state.get("element_whitelist", {}))) + " 个",
                    "strategy": "已使用 JSON 意图图纸编排"
                },
                "generated_count": len(final_state.get("test_cases", [])),
                "error": final_state.get("error")
            }
        except Exception as e:
            if invoke_config: await self._log("error", f"📊 Langfuse 追踪异常退出: {e}")
            raise
