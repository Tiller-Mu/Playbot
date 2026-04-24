from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import subprocess
import re

from app.models.database import Project, get_db
from app.schemas.schemas import ProjectCreate, ProjectUpdate, ProjectOut
from app.services.git_service import clone_repo, pull_repo

router = APIRouter(prefix="/api/project", tags=["project"])


@router.post("", response_model=ProjectOut)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    """创建项目 - 支持Git仓库或本地路径"""
    import os
    
    repo_path = None
    
    # 如果提供了本地路径，直接使用
    if data.local_path:
        # 验证路径存在
        if not os.path.exists(data.local_path):
            raise HTTPException(400, f"本地路径不存在: {data.local_path}")
        
        # 转为绝对路径
        repo_path = os.path.abspath(data.local_path)
        
        # 验证是目录
        if not os.path.isdir(repo_path):
            raise HTTPException(400, f"本地路径不是目录: {repo_path}")
    
    project = Project(
        name=data.name,
        git_url=data.git_url or "",  # 如果没有git_url，使用空字符串
        branch=data.branch,
        base_url=data.base_url,
        repo_path=repo_path,  # 设置本地路径
        username=data.username,
        password=data.password,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return result.scalars().all()


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: str, data: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    await db.delete(project)
    await db.commit()
    return {"message": "项目已删除"}


@router.post("/{project_id}/clone")
async def clone_project_repo(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    try:
        repo_path = await clone_repo(project.git_url, project.branch, project.id)
        project.repo_path = repo_path
        await db.commit()
        return {"message": "代码拉取成功", "repo_path": repo_path}
    except Exception as e:
        raise HTTPException(500, f"代码拉取失败: {str(e)}")


@router.post("/{project_id}/pull")
async def pull_project_repo(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if not project.repo_path:
        raise HTTPException(400, "请先拉取代码")
    try:
        await pull_repo(project.repo_path, project.branch)
        return {"message": "代码更新成功"}
    except Exception as e:
        raise HTTPException(500, f"代码更新失败: {str(e)}")


@router.get("/{project_id}/branches")
async def get_remote_branches(project_id: str, db: AsyncSession = Depends(get_db)):
    """获取远程仓库的所有分支列表"""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    
    try:
        # 使用 git ls-remote --heads 获取远程分支
        cmd = ["git", "ls-remote", "--heads", project.git_url]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            raise HTTPException(500, f"Git命令执行失败: {result.stderr}")
        
        # 解析输出，提取分支名
        # 格式: <commit-hash>\trefs/heads/<branch-name>
        branches = []
        for line in result.stdout.strip().split('\n'):
            if line:
                match = re.search(r'refs/heads/(.+)$', line)
                if match:
                    branches.append(match.group(1))
        
        # 排序：main/master 排在前面
        priority_branches = ['main', 'master', 'develop', 'dev']
        branches.sort(key=lambda x: (
            priority_branches.index(x) if x in priority_branches else len(priority_branches),
            x
        ))
        
        return {"branches": branches}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"获取分支列表失败: {str(e)}")
