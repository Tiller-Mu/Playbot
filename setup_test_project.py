"""快速设置测试项目的脚本"""
import asyncio
import sys
from pathlib import Path

# 添加 server 目录到路径
sys.path.insert(0, str(Path(__file__).parent / "server"))

from app.models.database import Project, init_db, async_session
from app.core.config import settings


async def setup_test_project():
    """创建测试项目"""
    # 初始化数据库
    await init_db()
    
    # client 项目的绝对路径
    client_path = str(Path(__file__).parent / "client")
    
    async with async_session() as session:
        # 检查是否已有测试项目
        from sqlalchemy import select
        result = await session.execute(
            select(Project).where(Project.name == "TestPilot Client")
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"测试项目已存在，ID: {existing.id}")
            print(f"Repo 路径: {existing.repo_path}")
            return existing
        
        # 创建测试项目
        project = Project(
            name="TestPilot Client",
            git_url="https://github.com/test/testpilot-client",  # 占位 URL
            branch="main",
            base_url="http://localhost:5174",
            repo_path=client_path,  # 直接设置为本地路径
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        
        print(f"✅ 测试项目创建成功!")
        print(f"项目 ID: {project.id}")
        print(f"项目名称: {project.name}")
        print(f"Repo 路径: {project.repo_path}")
        print(f"Base URL: {project.base_url}")
        print(f"\n现在可以在前端访问这个项目了!")
        
        return project


if __name__ == "__main__":
    asyncio.run(setup_test_project())
