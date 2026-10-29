"""Nebius Token Factory inference provider using OpenAI-compatible API.

Serves NVIDIA Nemotron open-source models (e.g. Nemotron-3-Nano) via Nebius Token
Factory. Scoped to text-based tasks only (alignment analysis, draft/text correction) -
see AIRouter.select_cloud_provider. Speech recognition and translation remain on the
existing NVIDIA ASR/Riva providers (app/services/speech_service.py), untouched.
"""

from typing import Optional
import httpx
from app.core.config import settings
from app.providers.base_ai_provider import BaseAIProvider


class NebiusProvider(BaseAIProvider):
    """Nebius Token Factory provider; OpenAI-compatible chat completions over NVIDIA open models."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        super().__init__(provider_name="nebius", client=client)

    def is_configured(self) -> bool:
        return settings.is_provider_configured("nebius")

    def get_model_name(self) -> str:
        return settings.NEBIUS_MODEL

    def get_base_url(self) -> str:
        return settings.NEBIUS_BASE_URL

    def get_api_key(self) -> str:
        return settings.NEBIUS_API_KEY

    def get_default_timeout(self) -> float:
        return float(settings.NEBIUS_TIMEOUT_SECONDS)


nebius_provider = NebiusProvider()
