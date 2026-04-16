from pydantic import BaseModel, Field
from typing import Callable, Any, Optional

class AgentConfig(BaseModel):
    """智能体运行配置"""
    # 【核心解耦】调用LLM的具体执行函数，签名要求: async def(messages: list) -> str
    llm_caller: Callable = Field(description="负责处理大模型交互的异步闭包或函数。要求接收 messages 列表，返回响应文本（建议强制JSON模式）")
    
    # Langfuse相关的非必填观测性参数
    langfuse_public_key: Optional[str] = Field(None, description="Langfuse公钥，指定了则开启云端图流观测")
    langfuse_secret_key: Optional[str] = Field(None, description="Langfuse密钥")
    langfuse_host: Optional[str] = Field("https://cloud.langfuse.com", description="自定义 Langfuse 域名服务")

class TestCaseInput(BaseModel):
    """测试用例智能体专属输入载荷"""
    # 1. 页面元信息
    page_url: str = Field(description="目标页面待测试URL（用于代码中 goto 方法的锚定与注释）")
    
    # 2. 源码信息（智能体通过本地技能自理加载 或者 直传）
    file_path: Optional[str] = Field(None, description="【推荐】只传路径，让智能体自行提取")
    source_code: Optional[str] = Field(None, description="【备选】直接传入读取完毕的字符串")
    
    # 3. 页面DOM碎片（智能体通过读取本地录制结果解析 或者 直传）
    dom_json_path: Optional[str] = Field(None, description="【推荐】系统存放在工作区的录制 DOM JSON 数据快照绝对路径")
    dom_data: Optional[Any] = Field(None, description="【备选】直接传入序列化的 Python Dict 对象（预先准备好的DOM）")
