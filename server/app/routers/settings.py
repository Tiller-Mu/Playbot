from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.models.database import AppSettings, get_db
from app.schemas.schemas import LLMSettingsUpdate, LLMSettingsOut
from app.services.llm_service import verify_llm_connection

router = APIRouter(prefix="/api/settings", tags=["settings"])

LLM_KEYS = ["llm_endpoint", "llm_api_key", "llm_model"]


class LLMVerifyRequest(BaseModel):
    llm_endpoint: str
    llm_api_key: str
    llm_model: str


class LLMVerifyResponse(BaseModel):
    success: bool
    message: str
    model: str = ""
    interaction_log: list[dict] = []


@router.get("/llm", response_model=LLMSettingsOut)
async def get_llm_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AppSettings).where(AppSettings.key.in_(LLM_KEYS))
    )
    rows = {r.key: r.value for r in result.scalars().all()}
    return LLMSettingsOut(
        llm_endpoint=rows.get("llm_endpoint", "https://api.openai.com/v1"),
        llm_api_key=_mask_key(rows.get("llm_api_key", "")),
        llm_model=rows.get("llm_model", "gpt-4o"),
    )


@router.put("/llm", response_model=LLMSettingsOut)
async def update_llm_settings(data: LLMSettingsUpdate, db: AsyncSession = Depends(get_db)):
    for key, value in [
        ("llm_endpoint", data.llm_endpoint),
        ("llm_api_key", data.llm_api_key),
        ("llm_model", data.llm_model),
    ]:
        result = await db.execute(select(AppSettings).where(AppSettings.key == key))
        row = result.scalar_one_or_none()
        if row:
            row.value = value
        else:
            db.add(AppSettings(key=key, value=value))
    await db.commit()

    return LLMSettingsOut(
        llm_endpoint=data.llm_endpoint,
        llm_api_key=_mask_key(data.llm_api_key),
        llm_model=data.llm_model,
    )


@router.post("/llm/verify", response_model=LLMVerifyResponse)
async def verify_llm(data: LLMVerifyRequest, db: AsyncSession = Depends(get_db)):
    """验证 LLM 连接是否正常"""
    api_key = data.llm_api_key
    if "*" in api_key:
        result = await db.execute(select(AppSettings).where(AppSettings.key == "llm_api_key"))
        row = result.scalar_one_or_none()
        if row and row.value:
            api_key = row.value
            
    success, message, model, interaction_log = await verify_llm_connection(
        data.llm_endpoint,
        api_key,
        data.llm_model
    )
    return LLMVerifyResponse(
        success=success,
        message=message,
        model=model,
        interaction_log=interaction_log
    )


def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return key
    return key[:4] + "*" * (len(key) - 8) + key[-4:]
