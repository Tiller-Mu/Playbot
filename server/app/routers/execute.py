import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Project, TestCase, Execution, ExecutionDetail, get_db
from app.schemas.schemas import ExecuteRequest, ExecutionOut, ExecutionDetailOut
from app.services.executor import run_tests

router = APIRouter(prefix="/api/execute", tags=["execute"])


@router.post("", response_model=ExecutionOut)
async def start_execution(data: ExecuteRequest, db: AsyncSession = Depends(get_db)):
    """启动测试执行。"""
    if not data.case_ids:
        raise HTTPException(400, "请选择要执行的用例")

    # Verify cases exist and get project
    result = await db.execute(
        select(TestCase).where(TestCase.id.in_(data.case_ids))
    )
    cases = list(result.scalars().all())
    if not cases:
        raise HTTPException(404, "用例不存在")

    project_id = cases[0].project_id
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")

    # Create execution record
    execution = Execution(
        project_id=project_id,
        status="pending",
        total_cases=len(cases),
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    # Run tests in background
    asyncio.create_task(
        run_tests(execution.id, data.case_ids, project.base_url, data.headless)
    )

    return execution


@router.get("/history", response_model=list[ExecutionOut])
async def list_executions(
    project_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Execution)
        .where(Execution.project_id == project_id)
        .order_by(Execution.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/{execution_id}", response_model=ExecutionOut)
async def get_execution(execution_id: str, db: AsyncSession = Depends(get_db)):
    execution = await db.get(Execution, execution_id)
    if not execution:
        raise HTTPException(404, "执行记录不存在")
    return execution


@router.get("/{execution_id}/details", response_model=list[ExecutionDetailOut])
async def get_execution_details(execution_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ExecutionDetail).where(ExecutionDetail.execution_id == execution_id)
    )
    return result.scalars().all()
