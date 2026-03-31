from __future__ import annotations

import base64
import hashlib
import logging
from typing import Callable

import litellm
from cryptography.fernet import Fernet, InvalidToken
from langchain_litellm import ChatLiteLLM

from app.config import settings as app_settings
from app.db.models.llm_provider import LlmProvider

logger = logging.getLogger(__name__)

litellm.num_retries = 3
litellm.request_timeout = 120
litellm.modify_params = True


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(app_settings.secret_key.encode()).digest())
    return Fernet(key)


def decrypt_key(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""


def encrypt_key(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def build_llm_from_provider(provider: LlmProvider, *, streaming: bool = True) -> ChatLiteLLM:
    kwargs: dict = {
        "model": provider.model,
        "temperature": provider.temperature,
        "streaming": streaming,
        "max_retries": 5,
    }
    if provider.api_key_encrypted:
        api_key = decrypt_key(provider.api_key_encrypted)
        if api_key:
            kwargs["api_key"] = api_key
    if provider.base_url:
        kwargs["api_base"] = provider.base_url

    try:
        if litellm.supports_reasoning(model=provider.model):
            kwargs.setdefault("model_kwargs", {})["reasoning_effort"] = "medium"
            kwargs["temperature"] = 1
            logger.debug("Reasoning enabled for model %s", provider.model)
    except Exception:
        logger.debug("Could not check reasoning support for %s", provider.model)

    return ChatLiteLLM(**kwargs)


def build_embeddings_from_provider(
    provider: LlmProvider,
) -> Callable[[list[str]], list[list[float]]]:
    """Return an async embedding callable suitable for PostgresStore index config."""
    api_key: str | None = None
    if provider.api_key_encrypted:
        api_key = decrypt_key(provider.api_key_encrypted)

    async def _embed(texts: list[str]) -> list[list[float]]:
        kwargs: dict = {"model": provider.model, "input": texts}
        if api_key:
            kwargs["api_key"] = api_key
        if provider.base_url:
            kwargs["api_base"] = provider.base_url
        response = await litellm.aembedding(**kwargs)
        return [item["embedding"] for item in response.data]

    return _embed


def get_embedding_dims(provider: LlmProvider) -> int:
    """Resolve the embedding dimension for a provider model."""
    try:
        info = litellm.get_model_info(provider.model)
        output_dim = info.get("output_vector_size")
        if output_dim and isinstance(output_dim, int) and output_dim > 0:
            return output_dim
    except Exception:
        logger.debug("Could not auto-detect embedding dims for %s", provider.model)
    return 1536
