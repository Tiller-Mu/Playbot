from pydantic import BaseModel, Field
from typing import List, Literal, Optional

ActionType = Literal[
    "navigate", "click", "fill", "hover", "press", "check", "uncheck", "clear",
    "expect_visible", "expect_hidden", "expect_text", "expect_enabled", "expect_disabled", "custom_script"
]

class SemanticStep(BaseModel):
    action: ActionType = Field(..., description="纯语义动作类型，如 click, fill, expect_visible 等。")
    target_description: str = Field(..., description="描述操作的目标元素（如：'邮箱输入框'、'页面右上角的保存按钮'，无需具体 CSS 选择器）")
    value: Optional[str] = Field(None, description="当需要输入或验证时附加的值。无输入要求留空。")
    intent_reason: str = Field(..., description="这步操作的理由，为什么要这么做（比如：'用于触发邮箱格式校验报错'）")

class TestPlanCase(BaseModel):
    title: str = Field(..., description="用例标题，如 '正确填写所有项并成功保存'")
    description: str = Field(..., description="用例概要，说明用例主要测试的业务点、前置条件与验证目标。")
    steps: List[SemanticStep] = Field(..., description="实现此用例的交互步骤列表")

class TestPlanBlueprint(BaseModel):
    page_summary: str = Field(..., description="对当前页面功能和所提取轨迹的简明总结")
    test_cases: List[TestPlanCase] = Field(..., description="由模型规划的全部测试用例大纲列表，包含所有的正向和各种异常边界流")
