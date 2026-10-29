"""Groq cloud AI provider implementation using OpenAI-compatible API."""

from typing import Optional
import httpx
from app.core.config import settings
from app.providers.base_ai_provider import BaseAIProvider


class GroqProvider(BaseAIProvider):
    """
    Groq high-speed cloud inference provider using OpenAI-compatible chat completions API.
    Provides sub-second inference with models such as llama-3.3-70b-versatile and llama-3.1-8b-instant.
    """

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        super().__init__(provider_name="groq", client=client)

    def is_configured(self) -> bool:
        return settings.is_provider_configured("groq")

    def get_model_name(self) -> str:
        return settings.GROQ_MODEL

    def get_base_url(self) -> str:
        return settings.GROQ_BASE_URL

    def get_api_key(self) -> str:
        return settings.GROQ_API_KEY

    def get_default_timeout(self) -> float:
        return float(settings.GROQ_TIMEOUT_SECONDS)


groq_provider = GroqProvider()
