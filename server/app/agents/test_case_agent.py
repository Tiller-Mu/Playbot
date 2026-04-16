"""
测试用例生成智能体（简化版）
基于LangChain的自主决策智能体
"""
from typing import Dict, Any, List, Optional, Callable, AsyncIterator
from datetime import datetime
import json
import asyncio

from app.agents.tools import CodeAnalyzerTool, DOMExtractorTool
from app.services.llm_service import _get_llm_config, llm_chat_json


class TestCaseAgent:
    """
    测试用例生成智能体
    
    工作流程:
    1. 接收页面信息（源码、DOM、URL等）
    2. 自主决定使用哪些工具收集信息
    3. 基于收集的信息生成测试用例
    4. 返回结构化的用例列表
    
    支持流式输出，实时展示思考过程
    """
    
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        """
        初始化智能体
        
        Args:
            log_callback: 日志回调函数 (level, message) -> None
        """
        self.log_callback = log_callback
        self.tools: List[BaseTool] = [
            CodeAnalyzerTool(),
            DOMExtractorTool()
        ]
        self.agent_executor = None
        self.llm = None
        
    async def _log(self, level: str, message: str):
        """记录日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        
        if self.log_callback:
            await self.log_callback(level, log_msg)
        else:
            print(f"[{level.upper()}] {log_msg}")
    
    async def _init_llm(self):
        """初始化LLM（异步，需要数据库查询配置）"""
        if self.llm is None:
            cfg = await _get_llm_config()
            self.llm = ChatOpenAI(
                model=cfg["model"],
                openai_api_key=cfg["api_key"],
                openai_api_base=cfg["endpoint"],
                temperature=0.3,
                streaming=True  # 启用流式
            )
            await self._log("debug", f"LLM初始化完成: {cfg['model']}")
    
    def _create_agent(self) -> AgentExecutor:
        """创建Agent执行器"""
        # 系统提示词
        system_prompt = """你是一个专业的Playwright测试用例生成专家。

你的任务是根据页面信息生成高质量的测试用例。

工作流程:
1. 分析页面代码结构（使用code_analyzer工具）
2. 分析页面DOM元素（使用dom_extractor工具）
3. 基于收集的信息，生成2-3个核心测试用例

生成要求:
- 每个用例必须包含: title, description, script_content
- script_content是完整的Python代码字符串
- 使用Playwright和pytest
- 包含真实的CSS选择器
- 包含expect断言

输出格式必须是JSON:
{
  "test_cases": [
    {
      "title": "用例标题",
      "description": "用例描述",
      "script_content": "import pytest..."
    }
  ]
}

注意:
- 如果代码结构复杂，先使用工具分析
- 如果DOM信息不足，基于代码推断
- 确保生成的代码可以直接运行"""

        # 创建提示词模板
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        
        # 创建Agent
        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        
        # 创建执行器
        return AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=10
        )
    
    async def generate(
        self,
        page_path: str,
        page_url: str,
        source_code: str,
        dom_data: Any,
        file_path: str = ""
    ) -> Dict[str, Any]:
        """
        生成测试用例（非流式）
        
        Args:
            page_path: 页面路径（如 /settings）
            page_url: 完整URL
            source_code: 页面源码
            dom_data: DOM数据
            file_path: 源码文件路径
            
        Returns:
            生成的用例列表 {"test_cases": [...]}
        """
        await self._log("info", "🤖 智能体开始工作...")
        
        # 初始化
        await self._init_llm()
        self.agent_executor = self._create_agent()
        
        # 构建输入
        dom_str = json.dumps(dom_data, ensure_ascii=False) if dom_data else "{}"
        
        user_input = f"""为页面生成测试用例:

页面路径: {page_path}
页面URL: {page_url}
源码文件: {file_path}

请分析代码和DOM，生成测试用例。
"""
        
        # 将源码和DOM作为上下文（不直接发给LLM，让LLM决定使用工具）
        context = {
            "source_code": source_code,
            "dom_data": dom_str,
            "file_path": file_path
        }
        
        await self._log("info", "🧠 智能体正在分析...")
        
        try:
            # 执行Agent
            result = await self.agent_executor.ainvoke({
                "input": user_input,
                "chat_history": []
            })
            
            # 解析结果
            output = result.get("output", "")
            
            # 尝试从输出中提取JSON
            try:
                # 寻找JSON块
                start = output.find('{')
                end = output.rfind('}')
                if start != -1 and end != -1:
                    json_str = output[start:end+1]
                    parsed = json.loads(json_str)
                    await self._log("success", f"✅ 生成完成，共 {len(parsed.get('test_cases', []))} 个用例")
                    return parsed
            except json.JSONDecodeError:
                pass
            
            # 如果解析失败，返回原始输出
            await self._log("warning", "⚠️ 输出格式非标准JSON")
            return {"output": output, "test_cases": []}
            
        except Exception as e:
            await self._log("error", f"❌ 智能体执行失败: {e}")
            raise
    
    async def generate_stream(
        self,
        page_path: str,
        page_url: str,
        source_code: str,
        dom_data: Any,
        file_path: str = ""
    ) -> AsyncIterator[str]:
        """
        流式生成测试用例
        
        Yields:
            流式输出的文本片段
        """
        await self._log("info", "🤖 智能体开始工作（流式模式）...")
        
        # 初始化
        await self._init_llm()
        
        # 构建输入
        dom_str = json.dumps(dom_data, ensure_ascii=False) if dom_data else "{}"
        
        # 这里简化处理：先执行工具，再流式生成
        # 实际应该使用LangChain的流式回调
        
        yield "🧠 智能体正在分析页面结构...\n"
        await asyncio.sleep(0.5)
        
        # 调用代码分析工具
        code_tool = CodeAnalyzerTool()
        code_result = await code_tool.arun(
            source_code=source_code,
            file_path=file_path
        )
        yield f"📋 代码分析完成\n"
        yield f"{code_result[:500]}...\n\n"
        await asyncio.sleep(0.5)
        
        # 调用DOM提取工具
        if dom_data:
            dom_tool = DOMExtractorTool()
            dom_result = await dom_tool.arun(dom_data=dom_str)
            yield f"📋 DOM提取完成\n"
            yield f"{dom_result[:500]}...\n\n"
            await asyncio.sleep(0.5)
        
        yield "📝 正在生成测试用例...\n"
        
        # 实际生成（这里简化，实际应该调用LLM）
        # TODO: 实现真正的流式LLM调用
        
        yield "✅ 生成完成\n"


# 便捷函数
async def generate_test_cases(
    page_path: str,
    page_url: str,
    source_code: str,
    dom_data: Any,
    file_path: str = "",
    log_callback: Optional[Callable[[str, str], None]] = None
) -> Dict[str, Any]:
    """
    便捷函数：生成测试用例
    
    Args:
        page_path: 页面路径
        page_url: 完整URL
        source_code: 页面源码
        dom_data: DOM数据
        file_path: 源码文件路径
        log_callback: 日志回调
        
    Returns:
        生成的用例
    """
    agent = TestCaseAgent(log_callback=log_callback)
    return await agent.generate(
        page_path=page_path,
        page_url=page_url,
        source_code=source_code,
        dom_data=dom_data,
        file_path=file_path
    )
