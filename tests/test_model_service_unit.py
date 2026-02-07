#!/usr/bin/env python3
"""
Unit tests for src/model_service.py

Tests the ModelService class that fetches models from Anthropic API
with graceful fallback to static constants. Includes tests for
different authentication methods (anthropic, cli, bedrock, vertex).
"""

import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, PropertyMock
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
        """Successfully fetches models from API with anthropic auth."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "claude-sonnet-4-5-20250929", "name": "Claude Sonnet"},
                {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku"},
            ]
        }

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "anthropic"
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
        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "anthropic"
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

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "anthropic"
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

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "anthropic"
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                with patch.object(model_service, "_http_client") as mock_client:
                    mock_client.get = AsyncMock(return_value=mock_response)

                    result = await model_service.fetch_models_from_api()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_models_network_error(self, model_service):
        """Returns None on network error, allowing fallback."""
        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "anthropic"
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                with patch.object(model_service, "_http_client") as mock_client:
                    mock_client.get = AsyncMock(
                        side_effect=httpx.RequestError("connection failed")
                    )

                    result = await model_service.fetch_models_from_api()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_models_no_api_key(self, model_service):
        """Returns None when no API key is set (anthropic auth)."""
        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "anthropic"
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

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "anthropic"
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


class TestModelServiceRefresh:
    """Tests for model refresh functionality."""

    @pytest.fixture
    def model_service(self):
        """Create a fresh ModelService instance for each test."""
        return ModelService()

    @pytest.mark.asyncio
    async def test_refresh_models_success(self, model_service):
        """Refresh successfully updates cached models with anthropic auth."""
        # First, initialize with some models
        model_service._cached_models = ["old-model-1", "old-model-2"]
        model_service._source = "api"
        model_service._initialized = True

        new_models = ["new-model-1", "new-model-2", "new-model-3"]

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "anthropic"
            with patch.object(
                model_service, "fetch_models_from_api", new_callable=AsyncMock
            ) as mock:
                mock.return_value = new_models

                result = await model_service.refresh_models()

        assert result["success"] is True
        assert result["count"] == 3
        assert result["source"] == "api"
        assert result["models"] == new_models
        assert result["auth_method"] == "anthropic"
        assert model_service._cached_models == new_models
        assert model_service._source == "api"
        assert model_service._last_refresh is not None

    @pytest.mark.asyncio
    async def test_refresh_models_failure_preserves_existing(self, model_service):
        """Refresh failure preserves existing cached models."""
        existing_models = ["existing-model-1", "existing-model-2"]
        model_service._cached_models = existing_models
        model_service._source = "api"
        model_service._initialized = True

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "anthropic"
            with patch.object(
                model_service, "fetch_models_from_api", new_callable=AsyncMock
            ) as mock:
                mock.return_value = None  # API failed

                result = await model_service.refresh_models()

        assert result["success"] is False
        assert "API fetch failed" in result["message"]
        assert result["current_count"] == 2
        assert result["source"] == "api"
        assert result["auth_method"] == "anthropic"
        # Existing models should be preserved
        assert model_service._cached_models == existing_models

    @pytest.mark.asyncio
    async def test_refresh_models_updates_last_refresh_time(self, model_service):
        """Refresh updates the last_refresh timestamp."""
        model_service._initialized = True

        before_time = time.time()

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "anthropic"
            with patch.object(
                model_service, "fetch_models_from_api", new_callable=AsyncMock
            ) as mock:
                mock.return_value = ["model-1"]

                await model_service.refresh_models()

        after_time = time.time()

        assert model_service._last_refresh is not None
        assert before_time <= model_service._last_refresh <= after_time

    @pytest.mark.asyncio
    async def test_refresh_models_failure_does_not_update_timestamp(self, model_service):
        """Refresh failure does not update last_refresh timestamp."""
        model_service._cached_models = ["model-1"]
        model_service._last_refresh = 1000.0  # Some old timestamp
        model_service._initialized = True

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "anthropic"
            with patch.object(
                model_service, "fetch_models_from_api", new_callable=AsyncMock
            ) as mock:
                mock.return_value = None

                await model_service.refresh_models()

        # Timestamp should remain unchanged
        assert model_service._last_refresh == 1000.0

    def test_get_status_returns_correct_info(self, model_service):
        """get_status returns correct service status including auth_method."""
        model_service._initialized = True
        model_service._source = "api"
        model_service._cached_models = ["model-1", "model-2", "model-3"]
        model_service._last_refresh = 1234567890.0

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "anthropic"
            status = model_service.get_status()

        assert status["initialized"] is True
        assert status["source"] == "api"
        assert status["model_count"] == 3
        assert status["last_refresh"] == 1234567890.0
        assert status["auth_method"] == "anthropic"

    def test_get_status_fallback_source(self, model_service):
        """get_status shows fallback source when not from API."""
        model_service._initialized = True
        model_service._source = "fallback"
        model_service._cached_models = None
        model_service._last_refresh = None

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "claude_cli"
            status = model_service.get_status()

        assert status["initialized"] is True
        assert status["source"] == "fallback"
        assert status["model_count"] == len(CLAUDE_MODELS)
        assert status["last_refresh"] is None
        assert status["auth_method"] == "claude_cli"

    @pytest.mark.asyncio
    async def test_initialize_sets_source_api_on_success(self, model_service):
        """Initialize sets source to 'api' when fetch succeeds."""
        with patch.object(
            model_service, "fetch_models_from_api", new_callable=AsyncMock
        ) as mock:
            mock.return_value = ["model-1", "model-2"]

            await model_service.initialize()

        assert model_service._source == "api"
        assert model_service._last_refresh is not None

    @pytest.mark.asyncio
    async def test_initialize_sets_source_fallback_on_failure(self, model_service):
        """Initialize sets source to 'fallback' when fetch fails."""
        with patch.object(
            model_service, "fetch_models_from_api", new_callable=AsyncMock
        ) as mock:
            mock.return_value = None

            await model_service.initialize()

        assert model_service._source == "fallback"
        assert model_service._last_refresh is None

    @pytest.mark.asyncio
    async def test_shutdown_resets_source_and_timestamp(self, model_service):
        """Shutdown resets source and last_refresh."""
        model_service._source = "api"
        model_service._last_refresh = 1234567890.0
        model_service._initialized = True

        await model_service.shutdown()

        assert model_service._source == "fallback"
        assert model_service._last_refresh is None


class TestModelServiceAuthMethods:
    """Tests for different authentication method behaviors."""

    @pytest.fixture
    def model_service(self):
        """Create a fresh ModelService instance for each test."""
        return ModelService()

    @pytest.mark.asyncio
    async def test_fetch_models_cli_auth_returns_none(self, model_service):
        """CLI auth method returns None (uses static fallback)."""
        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "claude_cli"

            result = await model_service.fetch_models_from_api()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_models_bedrock_auth_returns_none(self, model_service):
        """Bedrock auth method returns None (uses static fallback)."""
        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "bedrock"

            result = await model_service.fetch_models_from_api()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_models_vertex_auth_returns_none(self, model_service):
        """Vertex auth method returns None (uses static fallback)."""
        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "vertex"

            result = await model_service.fetch_models_from_api()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_models_unknown_auth_returns_none(self, model_service):
        """Unknown auth method returns None (uses static fallback)."""
        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "unknown_method"

            result = await model_service.fetch_models_from_api()

        assert result is None

    @pytest.mark.asyncio
    async def test_refresh_models_cli_auth_fails(self, model_service):
        """Refresh with CLI auth returns failure with auth_method in response."""
        model_service._cached_models = ["model-1"]
        model_service._source = "fallback"
        model_service._initialized = True

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "claude_cli"

            result = await model_service.refresh_models()

        assert result["success"] is False
        assert "Dynamic refresh requires ANTHROPIC_API_KEY" in result["message"]
        assert result["auth_method"] == "claude_cli"
        assert result["current_count"] == 1

    @pytest.mark.asyncio
    async def test_refresh_models_bedrock_auth_fails(self, model_service):
        """Refresh with Bedrock auth returns failure with auth_method in response."""
        model_service._cached_models = None
        model_service._source = "fallback"
        model_service._initialized = True

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "bedrock"

            result = await model_service.refresh_models()

        assert result["success"] is False
        assert "Dynamic refresh requires ANTHROPIC_API_KEY" in result["message"]
        assert result["auth_method"] == "bedrock"
        assert result["current_count"] == len(CLAUDE_MODELS)

    @pytest.mark.asyncio
    async def test_refresh_models_vertex_auth_fails(self, model_service):
        """Refresh with Vertex auth returns failure with auth_method in response."""
        model_service._cached_models = None
        model_service._source = "fallback"
        model_service._initialized = True

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "vertex"

            result = await model_service.refresh_models()

        assert result["success"] is False
        assert "Dynamic refresh requires ANTHROPIC_API_KEY" in result["message"]
        assert result["auth_method"] == "vertex"
        assert result["current_count"] == len(CLAUDE_MODELS)

    def test_get_status_includes_auth_method_cli(self, model_service):
        """get_status includes auth_method for CLI auth."""
        model_service._initialized = True
        model_service._source = "fallback"

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "claude_cli"
            status = model_service.get_status()

        assert status["auth_method"] == "claude_cli"

    def test_get_status_includes_auth_method_bedrock(self, model_service):
        """get_status includes auth_method for Bedrock auth."""
        model_service._initialized = True
        model_service._source = "fallback"

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "bedrock"
            status = model_service.get_status()

        assert status["auth_method"] == "bedrock"

    def test_get_status_includes_auth_method_vertex(self, model_service):
        """get_status includes auth_method for Vertex auth."""
        model_service._initialized = True
        model_service._source = "fallback"

        with patch("src.model_service.auth_manager") as mock_auth:
            mock_auth.auth_method = "vertex"
            status = model_service.get_status()

        assert status["auth_method"] == "vertex"
