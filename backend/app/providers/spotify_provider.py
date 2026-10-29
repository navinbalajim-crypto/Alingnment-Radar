"""Spotify Web API provider using client-credentials authorization flow."""

import base64
import time
from typing import Any, Dict, List, Optional
import httpx
from app.core.config import settings
from app.core.errors import ProviderError, ProviderUnavailableError
from app.core.logging import logger


class SpotifyProvider:
    """Interacts with Spotify Web API using cached Client Credentials flow."""

    TOKEN_URL = "https://accounts.spotify.com/api/token"
    SEARCH_URL = "https://api.spotify.com/v1/search"

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self._client = client
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def _ensure_configured(self) -> None:
        if not settings.is_provider_configured("spotify"):
            raise ProviderUnavailableError("Spotify Web API", "Client ID or Client Secret not configured.")

    async def _get_access_token(self) -> str:
        """Fetch or return cached access token using client-credentials flow."""
        now = time.time()
        if self._access_token and now < (self._token_expires_at - 60):
            return self._access_token

        self._ensure_configured()

        credentials = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
        encoded_creds = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

        headers = {
            "Authorization": f"Basic {encoded_creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials"}

        try:
            if self._client:
                response = await self._client.post(self.TOKEN_URL, data=data, headers=headers, timeout=10.0)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(self.TOKEN_URL, data=data, headers=headers)

            if response.status_code >= 400:
                logger.error(f"Spotify token retrieval failed: HTTP {response.status_code}")
                raise ProviderError("Spotify Web API", "Authentication failed with Spotify.")

            token_data = response.json()
            self._access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)
            self._token_expires_at = now + expires_in
            return self._access_token  # type: ignore
        except httpx.RequestError as exc:
            logger.error(f"Spotify token request error: {exc}")
            raise ProviderError("Spotify Web API", "Network error obtaining Spotify access token.")

    async def search_tracks(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search tracks on Spotify and return real metadata and Spotify web URLs.
        """
        self._ensure_configured()
        token = await self._get_access_token()

        headers = {
            "Authorization": f"Bearer {token}",
        }
        params = {
            "q": query,
            "type": "track",
            "limit": min(limit, 10),
        }

        try:
            if self._client:
                response = await self._client.get(self.SEARCH_URL, params=params, headers=headers, timeout=10.0)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(self.SEARCH_URL, params=params, headers=headers)

            if response.status_code >= 400:
                logger.error(f"Spotify search failed: HTTP {response.status_code}")
                raise ProviderError("Spotify Web API", f"Search failed with status {response.status_code}")

            data = response.json()
            tracks = data.get("tracks", {}).get("items", [])
            results: List[Dict[str, Any]] = []

            for track in tracks:
                track_id = track.get("id")
                name = track.get("name", "")
                external_urls = track.get("external_urls", {})
                spotify_url = external_urls.get("spotify", "")
                if not spotify_url:
                    continue

                artists = [a.get("name", "") for a in track.get("artists", []) if a.get("name")]
                artist_str = ", ".join(artists) if artists else "Unknown Artist"
                album = track.get("album", {})
                album_name = album.get("name", "")
                release_date = album.get("release_date", "")
                images = album.get("images", [])
                image_url = images[0].get("url") if images else ""

                snippet = f"Track by {artist_str}"
                if album_name:
                    snippet += f" • Album: {album_name}"

                results.append({
                    "source": "spotify",
                    "title": f"{name} - {artist_str}",
                    "url": spotify_url,
                    "snippet": snippet,
                    "category": "music",
                    "published_date": release_date,
                    "extra_data": {
                        "track_id": track_id,
                        "artist": artist_str,
                        "artists": artists,
                        "album_name": album_name,
                        "image_url": image_url,
                        "thumbnail": image_url,
                        "duration_ms": track.get("duration_ms"),
                    },
                })

            return results
        except httpx.TimeoutException:
            logger.error("Spotify search timed out")
            raise ProviderError("Spotify Web API", "Search request timed out.")
        except httpx.RequestError as exc:
            logger.error(f"Spotify search network error: {exc}")
            raise ProviderError("Spotify Web API", "Network error communicating with Spotify.")


spotify_provider = SpotifyProvider()
