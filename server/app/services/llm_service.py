from openai import AsyncOpenAI
import logging
import asyncio

from app.core.config import settings
from app.models.database import async_session, AppSettings
from sqlalchemy import select

logger = logging.getLogger(__name__)

# LLM调用超时时间（秒）
LLM_TIMEOUT = 30


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
    import httpx
    client = AsyncOpenAI(
        base_url=cfg["endpoint"], 
        api_key=cfg["api_key"],
        timeout=httpx.Timeout(LLM_TIMEOUT, connect=10.0)
    )
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


async def verify_llm_connection(
    endpoint: str,
    api_key: str,
    model: str,
) -> tuple[bool, str, str, list[dict]]:
    """
    验证 LLM 连接是否正常
    返回: (是否成功, 消息, 模型名称, 交互记录)
    """
    interaction_log = []
    
    try:
        client = AsyncOpenAI(base_url=endpoint, api_key=api_key)
        
        # 记录请求信息
        request_info = {
            "type": "request",
            "endpoint": endpoint,
            "model": model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 10,
            "temperature": 0.1,
        }
        interaction_log.append(request_info)
        
        # 发送一个简单的测试请求
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "Hi"}
            ],
            max_tokens=10,
            temperature=0.1,
        )
        
        # 记录响应信息
        response_info = {
            "type": "response",
            "status": "success",
            "model": response.model if hasattr(response, 'model') else model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            } if response.usage else {},
            "content": response.choices[0].message.content if response.choices else "",
        }
        interaction_log.append(response_info)
        
        # 检查是否有响应
        if response.choices and len(response.choices) > 0:
            logger.info(f"LLM 连接验证成功: {endpoint}, 模型: {model}")
            return True, f"连接成功！模型 {model} 响应正常", model, interaction_log
        else:
            response_info["status"] = "error"
            response_info["error"] = "模型未返回有效响应"
            return False, "连接失败：模型未返回有效响应", model, interaction_log
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"LLM 连接验证失败: {error_msg}")
        
        # 记录错误信息
        error_info = {
            "type": "error",
            "error": error_msg,
        }
        interaction_log.append(error_info)
        
        # 提供更友好的错误信息
        if "401" in error_msg or "Unauthorized" in error_msg or "invalid_api_key" in error_msg.lower():
            return False, "API Key 无效，请检查后重试", model, interaction_log
        elif "404" in error_msg or "model_not_found" in error_msg.lower():
            return False, f"模型 {model} 不存在，请检查模型名称", model, interaction_log
        elif "403" in error_msg or "Forbidden" in error_msg:
            return False, "API Key 权限不足，请检查账户状态", model, interaction_log
        elif "Connection" in error_msg or "connection" in error_msg.lower():
            return False, "无法连接到服务端，请检查网络或端点地址", model, interaction_log
        else:
            return False, f"连接失败: {error_msg}", model, interaction_log
