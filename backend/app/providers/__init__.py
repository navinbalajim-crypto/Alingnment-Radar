"""External providers package."""

from app.providers.base_ai_provider import BaseAIProvider
from app.providers.email_provider import EmailProvider, email_provider
from app.providers.groq_provider import GroqProvider, groq_provider
from app.providers.nvidia_provider import NvidiaProvider, nvidia_provider
from app.providers.youtube_provider import YouTubeProvider, youtube_provider
from app.providers.spotify_provider import SpotifyProvider, spotify_provider
from app.providers.tavily_provider import TavilyProvider, tavily_provider
from app.providers.google_provider import GoogleOAuthProvider, google_provider

__all__ = [
    "BaseAIProvider",
    "EmailProvider",
    "email_provider",
    "GroqProvider",
    "groq_provider",
    "NvidiaProvider",
    "nvidia_provider",
    "YouTubeProvider",
    "youtube_provider",
    "SpotifyProvider",
    "spotify_provider",
    "TavilyProvider",
    "tavily_provider",
    "GoogleOAuthProvider",
    "google_provider",
]

