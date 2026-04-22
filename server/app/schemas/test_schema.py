from pydantic import BaseModel, Field
from typing import List, Literal, Optional

# Supported Actions Expanded
ActionType = Literal[
    "click", "fill", "hover", "press", "check", "uncheck", "clear",
    "expect_visible", "expect_hidden", "expect_text", "expect_enabled", "expect_disabled"
]

class TestActionSchema(BaseModel):
    action: ActionType = Field(..., description="测试动作类型")
    target_id: str = Field(..., description="操作目标元素的唯一 ID，必须严格来源于系统给定的【元素字典（白名单）】")
    value: Optional[str] = Field(None, description="当 action 需要附带值时使用（例如 fill 的文本、press 的按键名如 'Enter' 等）。无需取值的动作留空。")
    description: str = Field(..., description="这步操作的人类可读注释意图概述（比如：'点击提交按钮'、'验证错误弹窗显示'）")

class TestCaseIntent(BaseModel):
    title: str = Field(..., description="测试用例标题，要求简洁反映测试内容")
    description: str = Field(..., description="测试目的详述（中文），包括前置条件和预期结果的简要说明")
    steps: List[TestActionSchema] = Field(..., description="序列化的测试步骤")

class AgentTestBlueprint(BaseModel):
    page_summary: str = Field(..., description="对页面的核心功能区一两句话提炼总结")
    test_cases: List[TestCaseIntent] = Field(..., description="根据提供的有效元素白名单编排的多条测试用例集")
