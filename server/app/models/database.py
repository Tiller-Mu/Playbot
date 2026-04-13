import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Float,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

from app.core.config import settings


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    git_url = Column(String(500), nullable=False)
    branch = Column(String(100), default="main")
    base_url = Column(String(500), nullable=False, comment="被测站点 URL")
    repo_path = Column(String(500), comment="本地代码路径")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pages = relationship("TestPage", back_populates="project", cascade="all, delete-orphan")
    test_cases = relationship("TestCase", back_populates="project", cascade="all, delete-orphan")
    executions = relationship("Execution", back_populates="project", cascade="all, delete-orphan")


class TestPage(Base):
    """页面树节点 - 支持多级目录结构"""
    __tablename__ = "test_pages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    parent_id = Column(String(36), ForeignKey("test_pages.id"), nullable=True, comment="父节点ID")
    name = Column(String(200), nullable=False, comment="节点名称")
    path = Column(String(500), nullable=False, comment="路径片段")
    full_path = Column(String(1000), nullable=False, comment="完整路径")
    is_leaf = Column(Boolean, default=False, comment="是否叶子节点（页面）")
    component_name = Column(Text, comment="组件名称列表（JSON格式）")
    imported_components = Column(Text, comment="静态分析的组件引用列表（JSON格式）")
    page_comments = Column(Text, comment="页面级注释（文件顶部注释等）")
    component_comments = Column(Text, comment="组件级注释（JSON格式：{组件名: 注释内容}）")
    description = Column(Text, comment="页面功能描述（Markdown格式）")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="pages")
    parent = relationship("TestPage", remote_side=[id], backref="children")
    test_cases = relationship("TestCase", back_populates="page", cascade="all, delete-orphan")


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    page_id = Column(String(36), ForeignKey("test_pages.id"), nullable=True, comment="所属页面ID")
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False, comment="自然语言描述")
    script_path = Column(String(500), comment=".py 测试脚本路径")
    script_content = Column(Text, comment="测试脚本内容")
    group_name = Column(String(100), default="default")
    tags = Column(String(500), default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="test_cases")
    page = relationship("TestPage", back_populates="test_cases")
    execution_details = relationship("ExecutionDetail", back_populates="test_case", cascade="all, delete-orphan")


class Execution(Base):
    __tablename__ = "executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    status = Column(String(20), default="pending", comment="pending/running/passed/failed/error")
    total_cases = Column(Integer, default=0)
    passed_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    report_path = Column(String(500))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="executions")
    details = relationship("ExecutionDetail", back_populates="execution", cascade="all, delete-orphan")


class ExecutionDetail(Base):
    __tablename__ = "execution_details"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    execution_id = Column(String(36), ForeignKey("executions.id"), nullable=False)
    test_case_id = Column(String(36), ForeignKey("test_cases.id"), nullable=False)
    status = Column(String(20), default="pending", comment="pending/running/passed/failed/skipped")
    error_message = Column(Text)
    screenshot_path = Column(String(500))
    duration_ms = Column(Float, default=0)

    execution = relationship("Execution", back_populates="details")
    test_case = relationship("TestCase", back_populates="execution_details")


class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, default="")


# Database engine and session
# SQLite 需要启用外键约束
connect_args = {}
if "sqlite" in settings.database_url:
    connect_args = {"check_same_thread": False}

engine = create_async_engine(
    settings.database_url, 
    echo=settings.debug,
    connect_args=connect_args
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        # SQLite 需要启用外键约束
        if "sqlite" in settings.database_url:
            await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
