"""
Model service for dynamically fetching available models from Anthropic API.

This service provides:
- Dynamic model discovery from Anthropic API on startup
- Runtime model refresh via refresh_models() method
- Graceful fallback to static CLAUDE_MODELS when API is unavailable
- Caching of fetched models with refresh timestamp tracking
"""

import os
import time
import logging
from typing import List, Optional, Dict, Any

import httpx

from src.constants import CLAUDE_MODELS

logger = logging.getLogger(__name__)

# Anthropic API configuration
ANTHROPIC_API_BASE = "https://api.anthropic.com"
ANTHROPIC_API_VERSION = "2023-06-01"
MODEL_FETCH_TIMEOUT = 10.0  # seconds


class ModelService:
    """Fetches models from Anthropic API with fallback to constants."""

    def __init__(self):
        self._cached_models: Optional[List[str]] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        self._initialized: bool = False
        self._last_refresh: Optional[float] = None
        self._source: str = "fallback"  # "api" or "fallback"

    async def initialize(self) -> None:
        """Called during app startup - fetch models from API."""
        if self._initialized:
            return

        self._http_client = httpx.AsyncClient(timeout=MODEL_FETCH_TIMEOUT)

        # Attempt to fetch models from API
        fetched_models = await self.fetch_models_from_api()

        if fetched_models:
            self._cached_models = fetched_models
            self._source = "api"
            self._last_refresh = time.time()
            logger.info(f"Successfully fetched {len(fetched_models)} models from Anthropic API")
        else:
            self._cached_models = None
            self._source = "fallback"
            logger.info("Using fallback static model list from constants")

        self._initialized = True

    async def shutdown(self) -> None:
        """Close HTTP client on app shutdown."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._cached_models = None
        self._initialized = False
        self._last_refresh = None
        self._source = "fallback"

    async def fetch_models_from_api(self) -> Optional[List[str]]:
        """
        Fetch models from Anthropic API.

        GET https://api.anthropic.com/v1/models
        Headers:
           - x-api-key: {ANTHROPIC_API_KEY}
           - anthropic-version: 2023-06-01

        Returns list of model IDs on success, None on failure.
        """
        api_key = os.getenv("ANTHROPIC_API_KEY")

        if not api_key:
            logger.debug("ANTHROPIC_API_KEY not set, skipping API model fetch")
            return None

        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=MODEL_FETCH_TIMEOUT)

        try:
            response = await self._http_client.get(
                f"{ANTHROPIC_API_BASE}/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": ANTHROPIC_API_VERSION,
                },
            )

            if response.status_code == 200:
                data = response.json()
                # Extract model IDs from the response
                # API returns {"data": [{"id": "claude-...", ...}, ...]}
                models = []
                for model_data in data.get("data", []):
                    model_id = model_data.get("id")
                    if model_id:
                        models.append(model_id)

                if models:
                    logger.debug(f"Fetched models from API: {models}")
                    return models
                else:
                    logger.warning("API returned empty model list")
                    return None

            elif response.status_code == 401:
                logger.warning("Anthropic API authentication failed (401). Check ANTHROPIC_API_KEY.")
                return None
            elif response.status_code == 429:
                logger.warning("Anthropic API rate limited (429). Using fallback models.")
                return None
            else:
                logger.warning(
                    f"Anthropic API returned status {response.status_code}. Using fallback models."
                )
                return None

        except httpx.TimeoutException:
            logger.warning(f"Anthropic API request timed out after {MODEL_FETCH_TIMEOUT}s")
            return None
        except httpx.RequestError as e:
            logger.warning(f"Network error fetching models from Anthropic API: {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error fetching models: {e}")
            return None

    def get_models(self) -> List[str]:
        """Return cached models or CLAUDE_MODELS fallback."""
        if self._cached_models:
            return self._cached_models
        return list(CLAUDE_MODELS)

    def is_initialized(self) -> bool:
        """Check if service has been initialized."""
        return self._initialized

    async def refresh_models(self) -> Dict[str, Any]:
        """Force refresh models from Anthropic API.

        Returns a dict with refresh status and model information.
        If the API call fails, existing cached models are preserved.
        """
        models = await self.fetch_models_from_api()
        if models:
            self._cached_models = models
            self._last_refresh = time.time()
            self._source = "api"
            logger.info(f"Refreshed {len(models)} models from Anthropic API")
            return {
                "success": True,
                "count": len(models),
                "source": "api",
                "models": models,
            }
        else:
            return {
                "success": False,
                "message": "API fetch failed, keeping existing models",
                "current_count": len(self.get_models()),
                "source": self._source,
            }

    def get_status(self) -> Dict[str, Any]:
        """Get service status including source and last refresh time."""
        return {
            "initialized": self._initialized,
            "source": self._source,
            "model_count": len(self.get_models()),
            "last_refresh": self._last_refresh,
        }


# Global singleton instance
model_service = ModelService()
