from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Project, get_db
from app.schemas.schemas import ProjectCreate, ProjectUpdate, ProjectOut
from app.services.git_service import clone_repo, pull_repo

router = APIRouter(prefix="/api/project", tags=["project"])


@router.post("", response_model=ProjectOut)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(
        name=data.name,
        git_url=data.git_url,
        branch=data.branch,
        base_url=data.base_url,
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
