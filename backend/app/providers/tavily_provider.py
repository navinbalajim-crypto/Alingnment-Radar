"""Tavily Search API provider for web and cricket context retrieval."""

from typing import Any, Dict, List, Optional
import httpx
from app.core.config import settings
from app.core.errors import ProviderError, ProviderUnavailableError
from app.core.logging import logger


class TavilyProvider:
    """Interacts with Tavily Search API for real-time web context and cricket updates."""

    SEARCH_URL = "https://api.tavily.com/search"

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self._client = client

    def _ensure_configured(self) -> None:
        if not settings.is_provider_configured("tavily"):
            raise ProviderUnavailableError("Tavily Search API", "API key not configured.")

    async def search(self, query: str, limit: int = 5, category: str = "web") -> List[Dict[str, Any]]:
        """
        Execute search against Tavily and return real provider results.
        Validates URL schemes strictly.
        """
        self._ensure_configured()

        payload = {
            "api_key": settings.TAVILY_API_KEY,
            "query": query,
            "search_depth": "basic",
            "max_results": min(limit, 10),
            "include_answer": False,
        }

        try:
            if self._client:
                response = await self._client.post(self.SEARCH_URL, json=payload, timeout=12.0)
            else:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    response = await client.post(self.SEARCH_URL, json=payload)

            if response.status_code >= 400:
                logger.error(f"Tavily search failed: HTTP {response.status_code}")
                raise ProviderError("Tavily Search API", f"Search failed with status {response.status_code}")

            data = response.json()
            raw_results = data.get("results", [])
            results: List[Dict[str, Any]] = []

            for item in raw_results:
                url = item.get("url", "").strip()
                # Strict URL validation (HTTP / HTTPS only)
                if not (url.startswith("http://") or url.startswith("https://")):
                    continue

                title = item.get("title", "").strip()
                content = item.get("content", "").strip()
                published_date = item.get("published_date")
                score = item.get("score", 0.0)

                results.append({
                    "source": "tavily",
                    "title": title,
                    "url": url,
                    "snippet": content,
                    "category": category,
                    "published_date": published_date,
                    "extra_data": {
                        "relevance_score": score,
                    },
                })

            return results
        except httpx.TimeoutException:
            logger.error("Tavily search request timed out")
            raise ProviderError("Tavily Search API", "Search request timed out.")
        except httpx.RequestError as exc:
            logger.error(f"Tavily search network error: {exc}")
            raise ProviderError("Tavily Search API", "Network error communicating with Tavily.")


tavily_provider = TavilyProvider()
