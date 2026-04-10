from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AppSettings, get_db
from app.schemas.schemas import LLMSettingsUpdate, LLMSettingsOut

router = APIRouter(prefix="/api/settings", tags=["settings"])

LLM_KEYS = ["llm_endpoint", "llm_api_key", "llm_model"]


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


def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return key
    return key[:4] + "*" * (len(key) - 8) + key[-4:]
