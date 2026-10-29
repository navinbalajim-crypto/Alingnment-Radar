"""YouTube Data API v3 provider for video search and recommendation."""

import time
from typing import Any, Dict, List, Optional
import httpx
from app.core.config import settings
from app.core.errors import ProviderError, ProviderUnavailableError
from app.core.logging import logger


class YouTubeProvider:
    """Interacts with Google YouTube Data API v3 for video search."""

    SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self._client = client
        self._cooldown_until: float = 0.0

    def _ensure_configured(self) -> None:
        if not settings.is_provider_configured("youtube"):
            raise ProviderUnavailableError("YouTube Data API", "API key not configured.")
        if time.time() < self._cooldown_until:
            raise ProviderUnavailableError("YouTube Data API", "YouTube API quota temporarily exceeded (in cooldown).")

    async def search_videos(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search YouTube videos for query. Returns real provider-supplied metadata.
        """
        self._ensure_configured()

        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": min(limit, 10),
            "key": settings.YOUTUBE_DATA_API_KEY,
        }

        try:
            if self._client:
                response = await self._client.get(self.SEARCH_URL, params=params, timeout=10.0)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(self.SEARCH_URL, params=params)

            if response.status_code in (403, 429):
                self._cooldown_until = time.time() + 300.0  # 5 minutes cooldown
                logger.warning("YouTube API quota exceeded or rate limited (entering 5m cooldown)")
                raise ProviderError("YouTube Data API", "Quota exceeded or invalid API key.")
            if response.status_code >= 400:
                logger.error(f"YouTube API error: {response.status_code}")
                raise ProviderError("YouTube Data API", f"Search failed with status {response.status_code}")

            data = response.json()
            items = data.get("items", [])
            results: List[Dict[str, Any]] = []

            for item in items:
                video_id = item.get("id", {}).get("videoId")
                if not video_id:
                    continue

                import html
                snippet = item.get("snippet", {})
                title = html.unescape(snippet.get("title", ""))
                description = html.unescape(snippet.get("description", ""))
                channel_title = snippet.get("channelTitle", "")
                published_at = snippet.get("publishedAt", "")
                thumbnails = snippet.get("thumbnails", {})
                thumbnail_url = (
                    thumbnails.get("high", {}).get("url")
                    or thumbnails.get("medium", {}).get("url")
                    or thumbnails.get("default", {}).get("url")
                    or ""
                )

                results.append({
                    "source": "youtube",
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "snippet": description,
                    "category": "music",
                    "published_date": published_at,
                    "extra_data": {
                        "video_id": video_id,
                        "channel_title": channel_title,
                        "thumbnail_url": thumbnail_url,
                    },
                })

            return results
        except httpx.TimeoutException:
            logger.error("YouTube search request timed out")
            raise ProviderError("YouTube Data API", "Search request timed out.")
        except httpx.RequestError as exc:
            logger.error(f"YouTube search network error: {exc}")
            raise ProviderError("YouTube Data API", "Network error communicating with YouTube.")


youtube_provider = YouTubeProvider()
