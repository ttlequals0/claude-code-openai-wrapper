#!/usr/bin/env python3
"""
Unit tests for src/model_service.py

Tests the ModelService class that fetches models from Anthropic API
with graceful fallback to static constants.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from src.model_service import ModelService, MODEL_FETCH_TIMEOUT
from src.constants import CLAUDE_MODELS


class TestModelService:
    """Test ModelService class."""

    @pytest.fixture
    def model_service(self):
        """Create a fresh ModelService instance for each test."""
        return ModelService()

    @pytest.mark.asyncio
    async def test_fetch_models_success(self, model_service):
        """Successfully fetches models from API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "claude-sonnet-4-5-20250929", "name": "Claude Sonnet"},
                {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku"},
            ]
        }

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.object(model_service, "_http_client") as mock_client:
                mock_client.get = AsyncMock(return_value=mock_response)

                result = await model_service.fetch_models_from_api()

        assert result is not None
        assert len(result) == 2
        assert "claude-sonnet-4-5-20250929" in result
        assert "claude-haiku-4-5-20251001" in result

    @pytest.mark.asyncio
    async def test_fetch_models_timeout(self, model_service):
        """Returns None on timeout, allowing fallback to constants."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.object(model_service, "_http_client") as mock_client:
                mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

                result = await model_service.fetch_models_from_api()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_models_auth_error(self, model_service):
        """Returns None on 401 auth error, allowing fallback."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "invalid-key"}):
            with patch.object(model_service, "_http_client") as mock_client:
                mock_client.get = AsyncMock(return_value=mock_response)

                result = await model_service.fetch_models_from_api()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_models_rate_limited(self, model_service):
        """Returns None on 429 rate limit, allowing fallback."""
        mock_response = MagicMock()
        mock_response.status_code = 429

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.object(model_service, "_http_client") as mock_client:
                mock_client.get = AsyncMock(return_value=mock_response)

                result = await model_service.fetch_models_from_api()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_models_network_error(self, model_service):
        """Returns None on network error, allowing fallback."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.object(model_service, "_http_client") as mock_client:
                mock_client.get = AsyncMock(
                    side_effect=httpx.RequestError("connection failed")
                )

                result = await model_service.fetch_models_from_api()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_models_no_api_key(self, model_service):
        """Returns None when no API key is set."""
        with patch.dict("os.environ", {}, clear=True):
            # Ensure ANTHROPIC_API_KEY is not set
            import os
            if "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]

            result = await model_service.fetch_models_from_api()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_models_empty_response(self, model_service):
        """Returns None when API returns empty model list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.object(model_service, "_http_client") as mock_client:
                mock_client.get = AsyncMock(return_value=mock_response)

                result = await model_service.fetch_models_from_api()

        assert result is None

    def test_get_models_returns_cached(self, model_service):
        """Returns cached models when available."""
        model_service._cached_models = ["model-a", "model-b", "model-c"]

        result = model_service.get_models()

        assert result == ["model-a", "model-b", "model-c"]

    def test_get_models_returns_fallback(self, model_service):
        """Returns CLAUDE_MODELS fallback when no cached models."""
        model_service._cached_models = None

        result = model_service.get_models()

        assert result == list(CLAUDE_MODELS)

    def test_get_models_returns_fallback_empty_cache(self, model_service):
        """Returns CLAUDE_MODELS fallback when cache is empty list."""
        # Empty list is falsy, so should fall back
        model_service._cached_models = []

        result = model_service.get_models()

        # Empty list is falsy, so fallback is used
        assert result == list(CLAUDE_MODELS)

    def test_is_initialized_false_by_default(self, model_service):
        """Service is not initialized by default."""
        assert model_service.is_initialized() is False

    @pytest.mark.asyncio
    async def test_initialize_sets_initialized(self, model_service):
        """Initialize sets initialized flag."""
        with patch.object(model_service, "fetch_models_from_api", new_callable=AsyncMock) as mock:
            mock.return_value = None

            await model_service.initialize()

        assert model_service.is_initialized() is True

    @pytest.mark.asyncio
    async def test_initialize_caches_fetched_models(self, model_service):
        """Initialize caches successfully fetched models."""
        fetched = ["claude-3-opus", "claude-3-sonnet"]

        with patch.object(model_service, "fetch_models_from_api", new_callable=AsyncMock) as mock:
            mock.return_value = fetched

            await model_service.initialize()

        assert model_service._cached_models == fetched

    @pytest.mark.asyncio
    async def test_initialize_only_once(self, model_service):
        """Initialize only fetches models once."""
        with patch.object(model_service, "fetch_models_from_api", new_callable=AsyncMock) as mock:
            mock.return_value = ["model-1"]

            await model_service.initialize()
            await model_service.initialize()  # Second call should be no-op

        mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_closes_client(self, model_service):
        """Shutdown closes the HTTP client."""
        mock_client = AsyncMock()
        model_service._http_client = mock_client
        model_service._initialized = True

        await model_service.shutdown()

        mock_client.aclose.assert_called_once()
        assert model_service._http_client is None
        assert model_service._initialized is False

    @pytest.mark.asyncio
    async def test_shutdown_safe_when_not_initialized(self, model_service):
        """Shutdown is safe when called before initialization."""
        # Should not raise
        await model_service.shutdown()

        assert model_service._http_client is None


class TestModelServiceIntegration:
    """Integration-style tests for ModelService."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test full initialize-use-shutdown lifecycle."""
        service = ModelService()

        # Mock the API call
        with patch.object(service, "fetch_models_from_api", new_callable=AsyncMock) as mock:
            mock.return_value = ["test-model-1", "test-model-2"]

            # Initialize
            await service.initialize()
            assert service.is_initialized()

            # Use
            models = service.get_models()
            assert models == ["test-model-1", "test-model-2"]

            # Shutdown
            await service.shutdown()
            assert not service.is_initialized()

            # After shutdown, should return fallback
            models = service.get_models()
            assert models == list(CLAUDE_MODELS)

    @pytest.mark.asyncio
    async def test_fallback_on_api_failure(self):
        """Test that API failure results in fallback models."""
        service = ModelService()

        # Mock API failure
        with patch.object(service, "fetch_models_from_api", new_callable=AsyncMock) as mock:
            mock.return_value = None  # API failed

            await service.initialize()

            models = service.get_models()
            assert models == list(CLAUDE_MODELS)

            await service.shutdown()
