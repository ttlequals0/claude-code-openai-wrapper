#!/usr/bin/env python3
"""
Unit tests for src/claude_cli.py

Tests the ClaudeCodeCLI class methods.
These are pure unit tests that don't require a running server or Claude SDK.
"""

import pytest
import os
import tempfile
import sys
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path


class TestClaudeCodeCLIParseMessage:
    """Test ClaudeCodeCLI.parse_claude_message()"""

    @pytest.fixture
    def cli_class(self):
        """Get the ClaudeCodeCLI class without instantiating."""
        from src.claude_cli import ClaudeCodeCLI

        return ClaudeCodeCLI

    def test_parse_result_message(self, cli_class):
        """Parses result message with 'result' field."""
        # Use classmethod-like approach - create minimal mock instance
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [{"subtype": "success", "result": "The final answer is 42."}]
        result = cli.parse_claude_message(messages)
        assert result == "The final answer is 42."

    def test_parse_assistant_message_with_content_list(self, cli_class):
        """Parses assistant message with content list."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [
            {
                "content": [
                    {"type": "text", "text": "Hello "},
                    {"type": "text", "text": "World!"},
                ]
            }
        ]
        result = cli.parse_claude_message(messages)
        assert result == "Hello \nWorld!"

    def test_parse_assistant_message_with_textblock_objects(self, cli_class):
        """Parses assistant message with TextBlock objects."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        # Mock TextBlock object
        text_block = MagicMock()
        text_block.text = "Response text"

        messages = [{"content": [text_block]}]
        result = cli.parse_claude_message(messages)
        assert result == "Response text"

    def test_parse_assistant_message_with_string_content(self, cli_class):
        """Parses assistant message with string content blocks."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [{"content": ["Part 1", "Part 2"]}]
        result = cli.parse_claude_message(messages)
        assert result == "Part 1\nPart 2"

    def test_parse_old_format_assistant_message(self, cli_class):
        """Parses old format assistant message."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Old format response"}]},
            }
        ]
        result = cli.parse_claude_message(messages)
        assert result == "Old format response"

    def test_parse_old_format_string_content(self, cli_class):
        """Parses old format with string content."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [
            {
                "type": "assistant",
                "message": {"content": "Simple string content"},
            }
        ]
        result = cli.parse_claude_message(messages)
        assert result == "Simple string content"

    def test_parse_empty_messages_returns_none(self, cli_class):
        """Empty messages list returns None."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        result = cli.parse_claude_message([])
        assert result is None

    def test_parse_no_matching_messages_returns_none(self, cli_class):
        """No matching messages returns None."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [{"type": "system", "content": "System message"}]
        result = cli.parse_claude_message(messages)
        assert result is None

    def test_parse_uses_last_text(self, cli_class):
        """When multiple messages, uses the last one with text."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [
            {"content": [{"type": "text", "text": "First response"}]},
            {"content": [{"type": "text", "text": "Second response"}]},
        ]
        result = cli.parse_claude_message(messages)
        assert result == "Second response"

    def test_result_takes_priority(self, cli_class):
        """ResultMessage.result takes priority over AssistantMessage."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [
            {"content": [{"type": "text", "text": "Some response"}]},
            {"subtype": "success", "result": "Final result"},
        ]
        result = cli.parse_claude_message(messages)
        assert result == "Final result"

    def test_error_max_turns_raises_instead_of_returning_sentinel(self, cli_class):
        """When the SDK reports error_max_turns, parse_claude_message raises
        ClaudeResultError. Previously the loop fell through to the synthetic
        UserMessage('[Request interrupted by user]') and returned its text
        verbatim as the response body, which shipped as the OpenAI response
        content and made its way into downstream artifacts (e.g. chapter
        titles). This test pins the fix.
        """
        from src.claude_cli import ClaudeResultError

        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        # Shape matches what the SDK emits on error_max_turns: a synthetic
        # UserMessage with the interrupt sentinel, then a ResultMessage with
        # subtype='error_max_turns', result=None.
        messages = [
            {
                "content": [{"type": "text", "text": "[Request interrupted by user]"}],
                "uuid": "u-sentinel",
                "parent_tool_use_id": None,
            },
            {
                "subtype": "error_max_turns",
                "is_error": False,
                "num_turns": 2,
                "duration_ms": 2159,
                "duration_api_ms": 0,
                "result": None,
                "session_id": "sess-err",
            },
        ]
        with pytest.raises(ClaudeResultError) as excinfo:
            cli.parse_claude_message(messages)
        assert excinfo.value.subtype == "error_max_turns"
        assert excinfo.value.num_turns == 2

    def test_user_message_content_never_leaks_as_response(self, cli_class):
        """A SDK UserMessage (identified by uuid + no model field) must never
        be returned as assistant content, even when it precedes a successful
        result. Guards against the same leak as the error_max_turns case."""
        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [
            {
                "content": [{"type": "text", "text": "[Request interrupted by user]"}],
                "uuid": "u-sentinel",
                "parent_tool_use_id": None,
            },
            # AssistantMessage shape: has model, no uuid-only marker.
            {
                "content": [{"type": "text", "text": "Real answer"}],
                "model": "claude-sonnet-4-6",
                "parent_tool_use_id": None,
            },
        ]
        result = cli.parse_claude_message(messages)
        assert result == "Real answer"
        assert "Request interrupted" not in (result or "")

    def test_is_error_true_raises_even_when_subtype_missing(self, cli_class):
        """If a ResultMessage has is_error=True without a matching subtype
        literal, we still raise. This covers future SDK changes that add new
        error subtypes we haven't enumerated."""
        from src.claude_cli import ClaudeResultError

        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        messages = [
            {
                "subtype": "something_new",
                "is_error": True,
                "num_turns": 1,
                "duration_ms": 100,
                "result": None,
                "errors": ["upstream_exploded"],
            },
        ]
        with pytest.raises(ClaudeResultError) as excinfo:
            cli.parse_claude_message(messages)
        assert "upstream_exploded" in excinfo.value.errors

    def test_stderr_tail_propagates_through_result_error(self, cli_class):
        """The run_completion loop copies the CLI subprocess's captured
        stderr onto the ResultMessage dict; parse_claude_message must forward
        it onto the ClaudeResultError so the HTTP layer can log the actual
        reason the CLI died."""
        from src.claude_cli import ClaudeResultError

        cli = MagicMock()
        cli.parse_claude_message = cli_class.parse_claude_message.__get__(cli, cli_class)

        stderr_tail = "Error: auth rejected\nnode:internal/abort\n"
        messages = [
            {
                "subtype": "error_during_execution",
                "is_error": False,
                "num_turns": 2,
                "duration_ms": 2000,
                "result": None,
                "stderr_tail": stderr_tail,
            },
        ]
        with pytest.raises(ClaudeResultError) as excinfo:
            cli.parse_claude_message(messages)
        assert excinfo.value.stderr_tail == stderr_tail


class TestClaudeCodeCLIExtractMetadata:
    """Test ClaudeCodeCLI.extract_metadata()"""

    @pytest.fixture
    def cli_class(self):
        """Get the ClaudeCodeCLI class."""
        from src.claude_cli import ClaudeCodeCLI

        return ClaudeCodeCLI

    def test_extract_from_result_message(self, cli_class):
        """Extracts metadata from new SDK ResultMessage."""
        cli = MagicMock()
        cli.extract_metadata = cli_class.extract_metadata.__get__(cli, cli_class)

        messages = [
            {
                "subtype": "success",
                "total_cost_usd": 0.05,
                "duration_ms": 1500,
                "num_turns": 3,
                "session_id": "sess-123",
            }
        ]
        metadata = cli.extract_metadata(messages)

        assert metadata["total_cost_usd"] == 0.05
        assert metadata["duration_ms"] == 1500
        assert metadata["num_turns"] == 3
        assert metadata["session_id"] == "sess-123"

    def test_extract_from_system_init_message(self, cli_class):
        """Extracts metadata from SystemMessage init."""
        cli = MagicMock()
        cli.extract_metadata = cli_class.extract_metadata.__get__(cli, cli_class)

        messages = [
            {
                "subtype": "init",
                "data": {"session_id": "init-sess-456", "model": "claude-3-opus"},
            }
        ]
        metadata = cli.extract_metadata(messages)

        assert metadata["session_id"] == "init-sess-456"
        assert metadata["model"] == "claude-3-opus"

    def test_extract_from_old_result_message(self, cli_class):
        """Extracts metadata from old format result message."""
        cli = MagicMock()
        cli.extract_metadata = cli_class.extract_metadata.__get__(cli, cli_class)

        messages = [
            {
                "type": "result",
                "total_cost_usd": 0.03,
                "duration_ms": 1000,
                "num_turns": 2,
                "session_id": "old-sess",
            }
        ]
        metadata = cli.extract_metadata(messages)

        assert metadata["total_cost_usd"] == 0.03
        assert metadata["duration_ms"] == 1000
        assert metadata["session_id"] == "old-sess"

    def test_extract_from_old_system_init(self, cli_class):
        """Extracts metadata from old format system init."""
        cli = MagicMock()
        cli.extract_metadata = cli_class.extract_metadata.__get__(cli, cli_class)

        messages = [
            {
                "type": "system",
                "subtype": "init",
                "session_id": "old-init-sess",
                "model": "claude-3-haiku",
            }
        ]
        metadata = cli.extract_metadata(messages)

        assert metadata["session_id"] == "old-init-sess"
        assert metadata["model"] == "claude-3-haiku"

    def test_extract_empty_messages_returns_defaults(self, cli_class):
        """Empty messages returns default metadata."""
        cli = MagicMock()
        cli.extract_metadata = cli_class.extract_metadata.__get__(cli, cli_class)

        metadata = cli.extract_metadata([])

        assert metadata["session_id"] is None
        assert metadata["total_cost_usd"] == 0.0
        assert metadata["duration_ms"] == 0
        assert metadata["num_turns"] == 0
        assert metadata["model"] is None


class TestClaudeCodeCLIEstimateTokenUsage:
    """Test ClaudeCodeCLI.estimate_token_usage()"""

    @pytest.fixture
    def cli_class(self):
        """Get the ClaudeCodeCLI class."""
        from src.claude_cli import ClaudeCodeCLI

        return ClaudeCodeCLI

    def test_estimate_basic(self, cli_class):
        """Basic token estimation."""
        cli = MagicMock()
        cli.estimate_token_usage = cli_class.estimate_token_usage.__get__(cli, cli_class)

        # 12 chars / 4 = 3 tokens, 16 chars / 4 = 4 tokens
        result = cli.estimate_token_usage("Hello World!", "Response here!")
        assert result["prompt_tokens"] == 3
        assert result["completion_tokens"] == 3
        assert result["total_tokens"] == 6

    def test_estimate_minimum_one_token(self, cli_class):
        """Minimum is 1 token."""
        cli = MagicMock()
        cli.estimate_token_usage = cli_class.estimate_token_usage.__get__(cli, cli_class)

        result = cli.estimate_token_usage("Hi", "X")
        assert result["prompt_tokens"] >= 1
        assert result["completion_tokens"] >= 1

    def test_estimate_long_text(self, cli_class):
        """Longer text estimation."""
        cli = MagicMock()
        cli.estimate_token_usage = cli_class.estimate_token_usage.__get__(cli, cli_class)

        prompt = "a" * 400  # 100 tokens
        completion = "b" * 200  # 50 tokens
        result = cli.estimate_token_usage(prompt, completion)

        assert result["prompt_tokens"] == 100
        assert result["completion_tokens"] == 50
        assert result["total_tokens"] == 150

    def test_estimate_empty_strings(self, cli_class):
        """Empty strings return minimum 1 token each."""
        cli = MagicMock()
        cli.estimate_token_usage = cli_class.estimate_token_usage.__get__(cli, cli_class)

        result = cli.estimate_token_usage("", "")
        assert result["prompt_tokens"] == 1
        assert result["completion_tokens"] == 1


class TestClaudeCodeCLICleanupTempDir:
    """Test ClaudeCodeCLI._cleanup_temp_dir()"""

    def test_cleanup_removes_existing_dir(self):
        """Cleanup removes existing temp directory."""
        from src.claude_cli import ClaudeCodeCLI

        # Create a mock instance
        cli = MagicMock(spec=ClaudeCodeCLI)

        # Create an actual temp directory
        temp_dir = tempfile.mkdtemp(prefix="test_cleanup_")
        cli.temp_dir = temp_dir

        # Bind the method
        cli._cleanup_temp_dir = ClaudeCodeCLI._cleanup_temp_dir.__get__(cli, ClaudeCodeCLI)

        assert os.path.exists(temp_dir)

        cli._cleanup_temp_dir()

        assert not os.path.exists(temp_dir)

    def test_cleanup_handles_missing_dir(self):
        """Cleanup handles already-deleted directory gracefully."""
        from src.claude_cli import ClaudeCodeCLI

        cli = MagicMock(spec=ClaudeCodeCLI)
        cli.temp_dir = "/nonexistent/test/dir/12345"

        cli._cleanup_temp_dir = ClaudeCodeCLI._cleanup_temp_dir.__get__(cli, ClaudeCodeCLI)

        # Should not raise
        cli._cleanup_temp_dir()

    def test_cleanup_no_temp_dir_set(self):
        """Cleanup does nothing when temp_dir is None."""
        from src.claude_cli import ClaudeCodeCLI

        cli = MagicMock(spec=ClaudeCodeCLI)
        cli.temp_dir = None

        cli._cleanup_temp_dir = ClaudeCodeCLI._cleanup_temp_dir.__get__(cli, ClaudeCodeCLI)

        # Should not raise
        cli._cleanup_temp_dir()


class TestClaudeCodeCLIInit:
    """Test ClaudeCodeCLI.__init__() initialization logic."""

    def test_timeout_conversion(self):
        """Timeout is converted from milliseconds to seconds."""
        # Test the conversion logic directly
        timeout_ms = 120000
        timeout_seconds = timeout_ms / 1000
        assert timeout_seconds == 120.0

    def test_path_handling_with_valid_dir(self):
        """Valid directory path is handled correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir)
            assert path.exists()

    def test_path_handling_with_invalid_dir(self):
        """Invalid directory path is detected."""
        path = Path("/nonexistent/path/12345")
        assert not path.exists()

    def test_init_with_cwd(self):
        """ClaudeCodeCLI initializes with provided cwd."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.auth.validate_claude_code_auth") as mock_validate:
                with patch("src.auth.auth_manager") as mock_auth:
                    mock_validate.return_value = (True, {"method": "anthropic"})
                    mock_auth.get_claude_code_env_vars.return_value = {}

                    from src.claude_cli import ClaudeCodeCLI

                    cli = ClaudeCodeCLI(cwd=temp_dir)

                    assert cli.cwd == Path(temp_dir)
                    assert cli.temp_dir is None
                    assert cli.timeout == 600.0  # 600000ms / 1000

    def test_init_with_invalid_cwd_raises(self):
        """ClaudeCodeCLI raises ValueError for non-existent cwd."""
        with patch("src.auth.validate_claude_code_auth") as mock_validate:
            with patch("src.auth.auth_manager") as mock_auth:
                mock_validate.return_value = (True, {"method": "anthropic"})
                mock_auth.get_claude_code_env_vars.return_value = {}

                from src.claude_cli import ClaudeCodeCLI

                with pytest.raises(ValueError, match="Working directory does not exist"):
                    ClaudeCodeCLI(cwd="/nonexistent/path/12345")

    def test_init_without_cwd_creates_temp(self):
        """ClaudeCodeCLI creates temp directory when no cwd provided."""
        with patch("src.auth.validate_claude_code_auth") as mock_validate:
            with patch("src.auth.auth_manager") as mock_auth:
                with patch("atexit.register"):  # Don't actually register cleanup
                    mock_validate.return_value = (True, {"method": "anthropic"})
                    mock_auth.get_claude_code_env_vars.return_value = {}

                    from src.claude_cli import ClaudeCodeCLI

                    cli = ClaudeCodeCLI()

                    assert cli.temp_dir is not None
                    assert cli.cwd == Path(cli.temp_dir)
                    assert "claude_code_workspace_" in cli.temp_dir

                    # Cleanup
                    if cli.temp_dir and os.path.exists(cli.temp_dir):
                        import shutil

                        shutil.rmtree(cli.temp_dir)

    def test_init_with_custom_timeout(self):
        """ClaudeCodeCLI uses custom timeout."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.auth.validate_claude_code_auth") as mock_validate:
                with patch("src.auth.auth_manager") as mock_auth:
                    mock_validate.return_value = (True, {"method": "anthropic"})
                    mock_auth.get_claude_code_env_vars.return_value = {}

                    from src.claude_cli import ClaudeCodeCLI

                    cli = ClaudeCodeCLI(timeout=120000, cwd=temp_dir)

                    assert cli.timeout == 120.0

    def test_init_auth_validation_failure(self):
        """ClaudeCodeCLI handles auth validation failure gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.auth.validate_claude_code_auth") as mock_validate:
                with patch("src.auth.auth_manager") as mock_auth:
                    # Auth fails
                    mock_validate.return_value = (False, {"errors": ["Missing API key"]})
                    mock_auth.get_claude_code_env_vars.return_value = {}

                    from src.claude_cli import ClaudeCodeCLI

                    # Should not raise, just log warning
                    cli = ClaudeCodeCLI(cwd=temp_dir)
                    assert cli.cwd == Path(temp_dir)


class TestClaudeCodeCLIVerifyCLI:
    """Test ClaudeCodeCLI.verify_cli()"""

    @pytest.fixture
    def cli_instance(self):
        """Create a CLI instance with mocked auth."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.auth.validate_claude_code_auth") as mock_validate:
                with patch("src.auth.auth_manager") as mock_auth:
                    mock_validate.return_value = (True, {"method": "anthropic"})
                    mock_auth.get_claude_code_env_vars.return_value = {}

                    from src.claude_cli import ClaudeCodeCLI

                    cli = ClaudeCodeCLI(cwd=temp_dir)
                    yield cli

    @pytest.mark.asyncio
    async def test_verify_cli_success(self, cli_instance):
        """verify_cli returns True on successful SDK response."""
        mock_message = {"type": "assistant", "content": [{"type": "text", "text": "Hello"}]}

        async def mock_query(*args, **kwargs):
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            result = await cli_instance.verify_cli()
            assert result is True

    @pytest.mark.asyncio
    async def test_verify_cli_no_messages(self, cli_instance):
        """verify_cli returns False when no messages returned."""

        async def mock_query(*args, **kwargs):
            return
            yield  # Make it a generator but yield nothing

        with patch("src.claude_cli.query", mock_query):
            result = await cli_instance.verify_cli()
            assert result is False

    @pytest.mark.asyncio
    async def test_verify_cli_propagates_exception(self, cli_instance):
        """verify_cli raises rather than collapsing an SDK failure to False.

        The caller needs the exception to classify the failure; swallowing it
        is what reported a quota rejection as an auth failure on 2026-08-30.
        """

        async def mock_query(*args, **kwargs):
            raise RuntimeError("SDK error")
            yield  # Make it a generator

        with patch("src.claude_cli.query", mock_query):
            with pytest.raises(RuntimeError, match="SDK error"):
                await cli_instance.verify_cli()


class TestClaudeCodeCLIRunCompletion:
    """Test ClaudeCodeCLI.run_completion()"""

    @pytest.fixture
    def cli_instance(self):
        """Create a CLI instance with mocked auth."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.auth.validate_claude_code_auth") as mock_validate:
                with patch("src.auth.auth_manager") as mock_auth:
                    mock_validate.return_value = (True, {"method": "anthropic"})
                    mock_auth.get_claude_code_env_vars.return_value = {
                        "ANTHROPIC_API_KEY": "test-key"
                    }

                    from src.claude_cli import ClaudeCodeCLI

                    cli = ClaudeCodeCLI(cwd=temp_dir)
                    yield cli

    @pytest.mark.asyncio
    async def test_run_completion_basic(self, cli_instance):
        """run_completion yields messages from SDK."""
        mock_message = {"type": "assistant", "content": [{"type": "text", "text": "Hello"}]}

        async def mock_query(*args, **kwargs):
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            messages = []
            async for msg in cli_instance.run_completion("Hello"):
                messages.append(msg)

            assert len(messages) == 1
            assert messages[0] == mock_message

    @pytest.mark.asyncio
    async def test_run_completion_with_system_prompt(self, cli_instance):
        """run_completion sets system_prompt option."""
        mock_message = {"type": "assistant", "content": "Response"}
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion("Hello", system_prompt="You are helpful"):
                pass

            assert len(captured_options) == 1
            opts = captured_options[0]
            assert opts.system_prompt == {"type": "text", "text": "You are helpful"}

    @pytest.mark.asyncio
    async def test_run_completion_with_model(self, cli_instance):
        """run_completion sets model option."""
        mock_message = {"type": "assistant"}
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion("Hello", model="claude-3-opus"):
                pass

            assert captured_options[0].model == "claude-3-opus"

    @pytest.mark.asyncio
    async def test_run_completion_with_tool_restrictions(self, cli_instance):
        """run_completion sets allowed/disallowed tools."""
        mock_message = {"type": "assistant"}
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion(
                "Hello",
                allowed_tools=["Bash", "Read"],
                disallowed_tools=["Task"],
            ):
                pass

            assert captured_options[0].allowed_tools == ["Bash", "Read"]
            assert captured_options[0].disallowed_tools == ["Task"]

    @pytest.mark.asyncio
    async def test_run_completion_with_permission_mode(self, cli_instance):
        """run_completion sets permission_mode."""
        mock_message = {"type": "assistant"}
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion("Hello", permission_mode="acceptEdits"):
                pass

            assert captured_options[0].permission_mode == "acceptEdits"

    @pytest.mark.asyncio
    async def test_run_completion_continue_session(self, cli_instance):
        """run_completion sets continue_session option."""
        mock_message = {"type": "assistant"}
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion("Hello", continue_session=True):
                pass

            assert captured_options[0].continue_session is True

    @pytest.mark.asyncio
    async def test_run_completion_resume_session(self, cli_instance):
        """run_completion sets resume option for session_id."""
        mock_message = {"type": "assistant"}
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion("Hello", session_id="sess-123"):
                pass

            assert captured_options[0].resume == "sess-123"

    @pytest.mark.asyncio
    async def test_run_completion_converts_objects_to_dicts(self, cli_instance):
        """run_completion converts message objects to dicts."""
        # Create a mock object with attributes
        mock_obj = MagicMock()
        mock_obj.type = "assistant"
        mock_obj.content = "Hello"

        async def mock_query(*args, **kwargs):
            yield mock_obj

        with patch("src.claude_cli.query", mock_query):
            messages = []
            async for msg in cli_instance.run_completion("Hello"):
                messages.append(msg)

            assert len(messages) == 1
            # Should be converted to dict
            assert isinstance(messages[0], dict)
            assert "type" in messages[0]

    @pytest.mark.asyncio
    async def test_run_completion_exception_yields_error(self, cli_instance):
        """run_completion yields error message on exception."""

        async def mock_query(*args, **kwargs):
            raise RuntimeError("SDK failed")
            yield  # Make it a generator

        with patch("src.claude_cli.query", mock_query):
            messages = []
            async for msg in cli_instance.run_completion("Hello"):
                messages.append(msg)

            assert len(messages) == 1
            assert messages[0]["type"] == "result"
            assert messages[0]["subtype"] == "error_during_execution"
            assert messages[0]["is_error"] is True
            assert "SDK failed" in messages[0]["error_message"]

    @pytest.mark.asyncio
    async def test_run_completion_restores_env_vars(self, cli_instance):
        """run_completion restores environment variables after execution."""
        # Set an env var that will be modified
        original_key = os.environ.get("ANTHROPIC_API_KEY")

        mock_message = {"type": "assistant"}

        async def mock_query(*args, **kwargs):
            yield mock_message

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion("Hello"):
                pass

        # Env should be restored
        if original_key is None:
            assert (
                "ANTHROPIC_API_KEY" not in os.environ
                or os.environ.get("ANTHROPIC_API_KEY") == original_key
            )
        else:
            assert os.environ.get("ANTHROPIC_API_KEY") == original_key


class TestClaudeCodeCLICleanupException:
    """Test ClaudeCodeCLI._cleanup_temp_dir() exception handling."""

    def test_cleanup_exception_is_caught(self):
        """Cleanup catches exceptions during rmtree."""
        from src.claude_cli import ClaudeCodeCLI

        cli = MagicMock(spec=ClaudeCodeCLI)
        temp_dir = tempfile.mkdtemp(prefix="test_cleanup_exc_")
        cli.temp_dir = temp_dir

        # Bind the real method
        cli._cleanup_temp_dir = ClaudeCodeCLI._cleanup_temp_dir.__get__(cli, ClaudeCodeCLI)

        with patch("shutil.rmtree", side_effect=PermissionError("Cannot delete")):
            # Should not raise
            cli._cleanup_temp_dir()

        # Clean up manually
        import shutil

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


class TestQuotaErrorClassification:
    """An exhausted quota must surface as a rate-limit error, not a 502.

    Observed 2026-08-31: the CLI exits 1 with 'You've hit your session limit,
    resets 6pm (UTC)' after emitting ResultMessage(subtype='success',
    is_error=True), which the old first-error raise reported as
    'SDK returned success'.
    """

    @pytest.fixture
    def cli(self):
        from src.claude_cli import ClaudeCodeCLI

        mock = MagicMock()
        mock.parse_claude_message = ClaudeCodeCLI.parse_claude_message.__get__(mock, ClaudeCodeCLI)
        return mock

    def test_session_limit_result_is_rate_limit(self, cli):
        from src.claude_cli import ClaudeResultError

        messages = [
            {
                "subtype": "success",
                "is_error": True,
                "num_turns": 1,
                "errors": [],
                "result": "You've hit your session limit · resets 6pm (UTC)",
            }
        ]
        with pytest.raises(ClaudeResultError) as exc_info:
            cli.parse_claude_message(messages)
        err = exc_info.value
        assert err.subtype == "assistant_rate_limit"
        assert err.errors == ["rate_limit"]
        assert err.resets_at is not None

    def test_quota_text_in_a_later_flattened_exception_still_classifies(self, cli):
        """run_completion's outer handler flattens exceptions into an
        error_during_execution dict; the limit prose there must classify."""
        from src.claude_cli import ClaudeResultError

        messages = [
            {
                "subtype": "error_during_execution",
                "is_error": True,
                "error_message": (
                    "Claude SDK returned assistant_rate_limit after None turns: "
                    "You've hit your session limit · resets 6pm (UTC)"
                ),
            }
        ]
        with pytest.raises(ClaudeResultError) as exc_info:
            cli.parse_claude_message(messages)
        assert exc_info.value.subtype == "assistant_rate_limit"

    def test_non_quota_error_result_raises_unchanged(self, cli):
        from src.claude_cli import ClaudeResultError

        messages = [
            {
                "subtype": "success",
                "is_error": True,
                "num_turns": 1,
                "result": "something else broke",
            }
        ]
        with pytest.raises(ClaudeResultError) as exc_info:
            cli.parse_claude_message(messages)
        assert exc_info.value.subtype == "success"

    def test_quota_error_records_the_parsed_reset(self):
        from src.claude_cli import _quota_result_error
        from src.quota_tracker import QuotaTracker

        fresh = QuotaTracker()
        with patch("src.claude_cli.quota_tracker", fresh):
            err = _quota_result_error("hit your session limit; resets 6pm (UTC)")
        assert err.resets_at is not None
        assert fresh.blocked_until() == err.resets_at


class TestRunCompletionQuotaFailFast:
    """A quota rejection must not be retried inline (observed: 10x60s per
    request, holding the caller's connection until the window reset)."""

    @pytest.fixture
    def cli_instance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.auth.validate_claude_code_auth") as mock_validate:
                with patch("src.auth.auth_manager") as mock_auth:
                    mock_validate.return_value = (True, {"method": "anthropic"})
                    mock_auth.get_claude_code_env_vars.return_value = {
                        "ANTHROPIC_API_KEY": "test-key"
                    }

                    from src.claude_cli import ClaudeCodeCLI

                    yield ClaudeCodeCLI(cwd=temp_dir)

    @pytest.mark.asyncio
    async def test_session_limit_exception_is_not_retried(self, cli_instance):
        attempts = []

        async def mock_query(*args, **kwargs):
            attempts.append(1)
            raise RuntimeError(
                "Claude Code returned an error result: "
                "You've hit your session limit · resets 6pm (UTC) (exit code: 1)"
            )
            yield  # pragma: no cover - makes this an async generator

        collected = []
        with patch("src.claude_cli.query", mock_query):
            async for msg in cli_instance.run_completion("Hello"):
                collected.append(msg)

        # One attempt, no inline retries; the failure is flattened into an
        # error result dict whose prose parse_claude_message maps to 429.
        assert len(attempts) == 1
        assert collected[-1]["is_error"] is True
        assert "session limit" in collected[-1]["error_message"]

    @pytest.mark.asyncio
    async def test_api_error_status_429_is_not_retried(self, cli_instance):
        attempts = []

        class FakeResultError(Exception):
            api_error_status = 429

        async def mock_query(*args, **kwargs):
            attempts.append(1)
            raise FakeResultError("upstream said no")
            yield  # pragma: no cover

        with patch("src.claude_cli.query", mock_query):
            async for _ in cli_instance.run_completion("Hello"):
                pass

        assert len(attempts) == 1
