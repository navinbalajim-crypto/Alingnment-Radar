"""NVIDIA NIM inference provider using OpenAI-compatible API and Nemotron models."""

from typing import Optional
import httpx
from app.core.config import settings
from app.providers.base_ai_provider import BaseAIProvider

DRAFT_TIMEOUT_SECONDS = 12.0


class NvidiaProvider(BaseAIProvider):
    """
    NVIDIA NIM inference provider using OpenAI-compatible API for Nemotron models.
    Supports high-context reasoning and conversation alignment analysis.
    """

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        super().__init__(provider_name="nvidia", client=client)

    def is_configured(self) -> bool:
        return settings.is_provider_configured("nvidia")

    def get_model_name(self) -> str:
        return settings.NVIDIA_MODEL

    def get_base_url(self) -> str:
        return settings.NVIDIA_BASE_URL

    def get_api_key(self) -> str:
        return settings.NVIDIA_API_KEY

    def get_default_timeout(self) -> float:
        return float(settings.NVIDIA_TIMEOUT_SECONDS)


nvidia_provider = NvidiaProvider()
