from datetime import datetime
from pydantic import BaseModel


# ---- Project ----
class ProjectCreate(BaseModel):
    name: str
    git_url: str | None = None  # Git仓库地址（可选）
    branch: str = "main"
    base_url: str
    local_path: str | None = None  # 本地代码路径（可选）


class ProjectUpdate(BaseModel):
    name: str | None = None
    git_url: str | None = None
    branch: str | None = None
    base_url: str | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    git_url: str
    branch: str
    base_url: str
    repo_path: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---- TestPage ----
class TestPageOut(BaseModel):
    id: str
    project_id: str
    parent_id: str | None
    name: str
    path: str
    full_path: str
    is_leaf: bool
    is_captured: bool = False
    component_name: str | None
    children: list['TestPageOut'] = []
    case_count: int = 0
    
    model_config = {"from_attributes": True}


class TestPageTreeOut(BaseModel):
    """完整页面树"""
    pages: list[TestPageOut]
    total_cases: int


# ---- TestCase ----
class TestCaseCreate(BaseModel):
    project_id: str
    title: str
    description: str
    script_content: str | None = None
    group_name: str = "default"
    tags: str = ""


class TestCaseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    script_content: str | None = None
    group_name: str | None = None
    tags: str | None = None
    enabled: bool | None = None


class TestCaseOut(BaseModel):
    id: str
    project_id: str
    page_id: str | None
    title: str
    description: str
    script_path: str | None
    script_content: str | None
    group_name: str
    tags: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---- NL Edit ----
class NLEditRequest(BaseModel):
    instruction: str  # 用户的自然语言修改指令


class NLEditResponse(BaseModel):
    description: str  # 更新后的自然语言描述
    script_content: str  # 更新后的代码


# ---- Execution ----
class ExecuteRequest(BaseModel):
    case_ids: list[str]  # 要执行的用例 ID 列表
    headless: bool = True


class ExecutionOut(BaseModel):
    id: str
    project_id: str
    status: str
    total_cases: int
    passed_count: int
    failed_count: int
    skipped_count: int
    start_time: datetime | None
    end_time: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExecutionDetailOut(BaseModel):
    id: str
    execution_id: str
    test_case_id: str
    status: str
    error_message: str | None
    screenshot_path: str | None
    duration_ms: float

    model_config = {"from_attributes": True}


# ---- Generate ----
class GenerateRequest(BaseModel):
    project_id: str


class MCPGenerateRequest(BaseModel):
    """MCP 页面用例生成请求"""
    project_id: str


# ---- Settings ----
class LLMSettingsUpdate(BaseModel):
    llm_endpoint: str
    llm_api_key: str
    llm_model: str


class LLMSettingsOut(BaseModel):
    llm_endpoint: str
    llm_api_key: str  # 前端显示时会脱敏
    llm_model: str
