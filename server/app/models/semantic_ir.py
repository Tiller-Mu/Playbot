from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class ActionType(str, Enum):
    NAVIGATE = "navigate"
    VIRTUAL_NAVIGATE = "virtual_navigate"  # SPA 无刷新跳转
    SWITCH_VIEW = "switch_view"  # 大面积DOM更换的视图切换
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"  # 经提纯后的下拉框综合选择
    SUBMIT_FORM = "submit_form"
    HOVER = "hover"  # 引发DOM突变的有效悬停
    HANDLE_DIALOG = "handle_dialog"  # 处理原生弹窗
    UPLOAD_FILE = "upload_file"  # 文件上传
    ASSERT_VISIBLE = "assert_visible"

class TargetElement(BaseModel):
    tag: str = Field(..., description="Element tag name (e.g., input, button)")
    attributes: Dict[str, str] = Field(default_factory=dict, description="Captured attributes like id, data-testid, placeholder")
    text: Optional[str] = Field(None, description="Visible text of the element")
    component: Optional[str] = Field(None, description="Bounded component name if any")
    path: Optional[str] = Field(None, description="Fallback DOM path")

class SemanticAction(BaseModel):
    action: ActionType
    target: Optional[TargetElement] = None
    url: Optional[str] = None
    value: Optional[str] = Field(None, description="The input value for fill action or dialog text")
    
    # 核心补齐：快照链路和网络追踪
    dom_snapshot_id: Optional[str] = Field(None, description="此动作发生后的 DOM 快照参照ID")
    network: Optional[Dict[str, Any]] = Field(None, description="动作引发的关键 XHR/Fetch 请求状态，格式为 {request: '/api/xxx', method: 'POST', status: 200}")
    after_dom_changed: bool = Field(False, description="标记此动作是否引起了页面的局部或整体重绘")

class IntentPlan(BaseModel):
    intent: str = Field(default="Automated cross-page intent", description="Natural language description of intent")
    steps: List[SemanticAction]
    assertions: List[SemanticAction] = Field(default_factory=list)
    
    # 覆盖率相关数据
    recorded_components: List[str] = Field(default_factory=list, description="本次运行真实捕获渲染出来的组件列表")
    missed_components: List[str] = Field(default_factory=list, description="静态源码有引用，但本次未渲染执行到的遗漏组件列表")
