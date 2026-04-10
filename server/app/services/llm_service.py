from openai import AsyncOpenAI

from app.core.config import settings
from app.models.database import async_session, AppSettings
from sqlalchemy import select


async def _get_llm_config() -> dict:
    """Load LLM config from database, falling back to env/defaults."""
    async with async_session() as session:
        result = await session.execute(select(AppSettings))
        rows = {r.key: r.value for r in result.scalars().all()}

    return {
        "endpoint": rows.get("llm_endpoint", settings.llm_endpoint),
        "api_key": rows.get("llm_api_key", settings.llm_api_key),
        "model": rows.get("llm_model", settings.llm_model),
    }


async def get_llm_client() -> tuple[AsyncOpenAI, str]:
    """Return an OpenAI-compatible async client and the model name."""
    cfg = await _get_llm_config()
    client = AsyncOpenAI(base_url=cfg["endpoint"], api_key=cfg["api_key"])
    return client, cfg["model"]


async def llm_chat(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """Send a chat completion request and return the assistant message content."""
    client, model = await get_llm_client()
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


async def llm_chat_json(
    messages: list[dict],
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    """Send a chat request with JSON response format."""
    client, model = await get_llm_client()
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or "{}"
