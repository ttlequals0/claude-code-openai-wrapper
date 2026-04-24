import os
import tempfile
import atexit
import shutil
from typing import AsyncGenerator, Dict, Any, Optional, List
from pathlib import Path
import logging

from claude_agent_sdk import query, ClaudeAgentOptions

from src.retry import RetryState, retry_delay

logger = logging.getLogger(__name__)


# ResultMessage subtypes that mean the SDK failed to produce a valid response.
# The SDK inserts a synthetic UserMessage(text='[Request interrupted by user]')
# before emitting a ResultMessage with one of these subtypes; without explicit
# handling, the sentinel leaks into the OpenAI response body.
_ERROR_RESULT_SUBTYPES = frozenset(
    {
        "error_max_turns",
        "error_during_execution",
        "error",
    }
)

# AssistantMessage.error literal values that the SDK attaches when the
# upstream API fails mid-response. Source: claude_agent_sdk.types
# AssistantMessageError = Literal["authentication_failed", "billing_error",
# "rate_limit", "invalid_request", "server_error", "unknown"].
_ASSISTANT_ERROR_VALUES = frozenset(
    {
        "authentication_failed",
        "billing_error",
        "rate_limit",
        "invalid_request",
        "server_error",
        "unknown",
    }
)


def _extract_text_blocks(content: List[Any]) -> List[str]:
    """Flatten a list of SDK content blocks into plain text strings.

    Accepts TextBlock objects (with a ``.text`` attribute), dict blocks of the
    form ``{"type": "text", "text": ...}``, and bare strings. Ignores other
    block types (e.g. ``ToolUseBlock``).
    """
    text_parts: List[str] = []
    for block in content:
        if hasattr(block, "text"):
            text_parts.append(block.text)
        elif isinstance(block, dict) and block.get("type") == "text":
            text_parts.append(block.get("text", ""))
        elif isinstance(block, str):
            text_parts.append(block)
    return text_parts


class ClaudeResultError(Exception):
    """Raised when the Claude Agent SDK emits a non-success ResultMessage.

    Callers in the HTTP layer translate this into a proper OpenAI-compatible
    response: error_max_turns -> 200 with finish_reason='length' and empty
    content; other subtypes -> 5xx with a structured error body.
    """

    def __init__(
        self,
        subtype: Optional[str],
        num_turns: Optional[int] = None,
        errors: Optional[List[str]] = None,
        stop_reason: Optional[str] = None,
        error_message: Optional[str] = None,
        stderr_tail: Optional[str] = None,
    ):
        self.subtype = subtype
        self.num_turns = num_turns
        self.errors = errors or []
        self.stop_reason = stop_reason
        self.error_message = error_message
        self.stderr_tail = stderr_tail
        detail = error_message or (self.errors[0] if self.errors else subtype)
        super().__init__(f"Claude SDK returned {subtype} after {num_turns} turns: {detail}")


class ClaudeCodeCLI:
    def __init__(self, timeout: int = 600000, cwd: Optional[str] = None):
        self.timeout = timeout / 1000  # Convert ms to seconds
        self.temp_dir = None

        # If cwd is provided (from CLAUDE_CWD env var), use it
        # Otherwise create an isolated temp directory
        if cwd:
            self.cwd = Path(cwd)
            # Check if the directory exists
            if not self.cwd.exists():
                logger.error(f"ERROR: Specified working directory does not exist: {self.cwd}")
                logger.error(
                    "Please create the directory first or unset CLAUDE_CWD to use a temporary directory"
                )
                raise ValueError(f"Working directory does not exist: {self.cwd}")
            else:
                logger.info(f"Using CLAUDE_CWD: {self.cwd}")
        else:
            # Create isolated temp directory (cross-platform)
            self.temp_dir = tempfile.mkdtemp(prefix="claude_code_workspace_")
            self.cwd = Path(self.temp_dir)
            logger.info(f"Using temporary isolated workspace: {self.cwd}")

            # Register cleanup function to remove temp dir on exit
            atexit.register(self._cleanup_temp_dir)

        # Import auth manager
        from src.auth import auth_manager, validate_claude_code_auth

        # Validate authentication
        is_valid, auth_info = validate_claude_code_auth()
        if not is_valid:
            logger.warning(f"Claude Code authentication issues detected: {auth_info['errors']}")
        else:
            logger.info(f"Claude Code authentication method: {auth_info.get('method', 'unknown')}")

        # Store auth environment variables for SDK
        self.claude_env_vars = auth_manager.get_claude_code_env_vars()

    async def verify_cli(self) -> bool:
        """Verify Claude Agent SDK is working and authenticated."""
        try:
            # Test SDK with a simple query
            logger.info("Testing Claude Agent SDK...")

            messages = []
            async for message in query(
                prompt="Hello",
                options=ClaudeAgentOptions(
                    max_turns=1,
                    cwd=self.cwd,
                    system_prompt={"type": "preset", "preset": "claude_code"},
                ),
            ):
                messages.append(message)
                # Break early on first response to speed up verification
                # Handle both dict and object types
                msg_type = (
                    getattr(message, "type", None)
                    if hasattr(message, "type")
                    else message.get("type") if isinstance(message, dict) else None
                )
                if msg_type == "assistant":
                    break

            if messages:
                logger.info("✅ Claude Agent SDK verified successfully")
                return True
            else:
                logger.warning("⚠️ Claude Agent SDK test returned no messages")
                return False

        except Exception as e:
            logger.error(f"Claude Agent SDK verification failed: {e}")
            logger.warning("Please ensure Claude Code is installed and authenticated:")
            logger.warning("  1. Install: npm install -g @anthropic-ai/claude-code")
            logger.warning("  2. Set ANTHROPIC_API_KEY environment variable")
            logger.warning("  3. Test: claude --print 'Hello'")
            return False

    async def run_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        stream: bool = True,
        max_turns: int = 10,
        allowed_tools: Optional[List[str]] = None,
        disallowed_tools: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        continue_session: bool = False,
        permission_mode: Optional[str] = None,
        effort: Optional[str] = None,
        thinking: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run Claude Agent using the Python SDK and yield response chunks."""

        try:
            # Set authentication environment variables (if any)
            original_env = {}
            if self.claude_env_vars:  # Only set env vars if we have any
                for key, value in self.claude_env_vars.items():
                    original_env[key] = os.environ.get(key)
                    os.environ[key] = value

            try:
                # Capture the CLI subprocess's stderr into a bounded ring so we
                # can attach it to non-success ResultMessage log lines. The
                # bundled Claude CLI prints its real failure reason
                # (auth rejection, permission denial, network error) to
                # stderr, but previously we only saw the typed SDK error
                # subtype (``error_during_execution``) and zero context.
                stderr_buffer: List[str] = []
                _STDERR_MAX_LINES = 40

                def _stderr_capture(line: str) -> None:
                    stderr_buffer.append(line)
                    if len(stderr_buffer) > _STDERR_MAX_LINES:
                        del stderr_buffer[: len(stderr_buffer) - _STDERR_MAX_LINES]

                # Build SDK options
                options = ClaudeAgentOptions(max_turns=max_turns, cwd=self.cwd)
                options.stderr = _stderr_capture

                # Set model if specified
                if model:
                    options.model = model

                # Set system prompt - CLAUDE AGENT SDK STRUCTURED FORMAT
                # Use structured format as per SDK documentation
                if system_prompt:
                    options.system_prompt = {"type": "text", "text": system_prompt}
                else:
                    # Use Claude Code preset to maintain expected behavior
                    options.system_prompt = {"type": "preset", "preset": "claude_code"}

                # Set tool restrictions
                if allowed_tools:
                    options.allowed_tools = allowed_tools
                if disallowed_tools:
                    options.disallowed_tools = disallowed_tools

                # Set permission mode (needed for tool execution in API context)
                if permission_mode:
                    options.permission_mode = permission_mode

                # Set effort level and thinking mode if specified
                if effort:
                    options.effort = effort
                if thinking:
                    options.thinking = thinking

                # Handle session continuity
                if continue_session:
                    options.continue_session = True
                elif session_id:
                    options.resume = session_id

                # Run the query with retry logic
                retry_state = RetryState()
                current_model = model

                while True:
                    try:
                        if current_model and current_model != model:
                            options.model = current_model

                        async for message in query(prompt=prompt, options=options):
                            logger.debug(f"Raw SDK message type: {type(message)}")
                            logger.debug(f"Raw SDK message: {message}")

                            if hasattr(message, "__dict__") and not isinstance(message, dict):
                                message_dict = {}
                                for attr_name in dir(message):
                                    if not attr_name.startswith("_"):
                                        try:
                                            attr_value = getattr(message, attr_name)
                                            if not callable(attr_value):
                                                message_dict[attr_name] = attr_value
                                        except:
                                            pass
                                logger.debug(f"Converted message dict: {message_dict}")

                                # If the SDK is reporting a non-success result,
                                # surface whatever the CLI subprocess wrote to
                                # stderr so triage doesn't have to guess why it
                                # died. Attach to the dict too so callers
                                # (parse_claude_message, HTTP layer) can relay it.
                                subtype = message_dict.get("subtype")
                                is_error = message_dict.get("is_error") is True
                                if subtype in _ERROR_RESULT_SUBTYPES or is_error:
                                    stderr_tail = "\n".join(stderr_buffer).strip()
                                    if stderr_tail:
                                        logger.warning(
                                            f"SDK {subtype} stderr tail "
                                            f"(session={message_dict.get('session_id')}, "
                                            f"num_turns={message_dict.get('num_turns')}):\n"
                                            f"{stderr_tail}"
                                        )
                                        message_dict["stderr_tail"] = stderr_tail
                                    else:
                                        logger.warning(
                                            f"SDK {subtype} with empty stderr "
                                            f"(session={message_dict.get('session_id')}, "
                                            f"num_turns={message_dict.get('num_turns')})"
                                        )

                                yield message_dict
                            else:
                                yield message

                        break  # Success, exit retry loop

                    except Exception as query_error:
                        error_str = str(query_error)
                        status_code = getattr(query_error, "status_code", None)

                        retry_state.record_attempt(status_code)

                        # Check for model fallback on overload
                        if current_model:
                            fallback = retry_state.get_fallback_model(current_model)
                            if fallback:
                                current_model = fallback
                                options.model = current_model

                        if retry_state.should_retry(status_code=status_code, error=query_error):
                            await retry_delay(retry_state)
                            continue

                        raise  # Not retryable, propagate

            finally:
                # Restore original environment (if we changed anything)
                if original_env:
                    for key, original_value in original_env.items():
                        if original_value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = original_value

        except Exception as e:
            logger.error(f"Claude Agent SDK error: {e}")
            # Emit a dict that matches the shape parse_claude_message expects
            # for a ResultMessage, so the HTTP layer surfaces the failure via
            # ClaudeResultError rather than silently returning empty content.
            yield {
                "type": "result",
                "subtype": "error_during_execution",
                "is_error": True,
                "error_message": str(e),
                "num_turns": 0,
                "duration_ms": 0,
            }

    def parse_claude_message(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """Extract the assistant message from Claude Agent SDK messages.

        Prioritizes ResultMessage.result for multi-turn conversations,
        falls back to last AssistantMessage content.

        Raises:
            ClaudeResultError: if any ResultMessage indicates an error (e.g.
                error_max_turns, error_during_execution) or has is_error=True.
                The SDK inserts a synthetic UserMessage with text
                '[Request interrupted by user]' immediately before such a
                ResultMessage; without this check the sentinel leaks as
                response content. Callers translate this into a proper
                HTTP response.
        """
        # Reject errored ResultMessages outright. The SDK puts a synthetic
        # UserMessage('[Request interrupted by user]') just before these, and
        # we must not let that text escape as response content.
        for message in messages:
            subtype = message.get("subtype")
            is_error = message.get("is_error") is True
            if subtype in _ERROR_RESULT_SUBTYPES or is_error:
                raise ClaudeResultError(
                    subtype=subtype,
                    num_turns=message.get("num_turns"),
                    errors=message.get("errors"),
                    stop_reason=message.get("stop_reason"),
                    error_message=message.get("error_message"),
                    stderr_tail=message.get("stderr_tail"),
                )

        # AssistantMessage.error carries upstream-API failure details (rate
        # limit, billing, auth). Surface those as ClaudeResultError too so the
        # HTTP layer can map each literal to the right status code (429, 402,
        # 401, 400, 502) rather than returning partial content with finish_reason=stop.
        for message in messages:
            assistant_error = message.get("error")
            if isinstance(assistant_error, str) and assistant_error in _ASSISTANT_ERROR_VALUES:
                raise ClaudeResultError(
                    subtype=f"assistant_{assistant_error}",
                    num_turns=None,
                    errors=[assistant_error],
                    stop_reason=message.get("stop_reason"),
                    error_message=None,
                )

        # RateLimitInfo messages (SDK 0.1.49+): emitted by the CLI when the
        # rate-limit state changes. If status is 'rejected', the upstream has
        # cut us off and callers should back off rather than consume the
        # partial response.
        for message in messages:
            if (
                isinstance(message, dict)
                and message.get("status") == "rejected"
                and "resets_at" in message
                and "rate_limit_type" in message
            ):
                resets_at = message.get("resets_at")
                raise ClaudeResultError(
                    subtype="assistant_rate_limit",
                    num_turns=None,
                    errors=["rate_limit"],
                    stop_reason=None,
                    error_message=f"upstream rate_limit ({message.get('rate_limit_type')}); resets_at={resets_at}",
                )

        # Prefer ResultMessage.result (multi-turn completion).
        for message in messages:
            if message.get("subtype") == "success" and "result" in message:
                return message["result"]

        # Fall back to AssistantMessage content. Skip SDK UserMessage dicts
        # (the wrapper's dict conversion produces a UserMessage with a uuid
        # field and no model field; the AssistantMessage has model).
        last_text = None
        for message in messages:
            if not isinstance(message, dict):
                continue

            # Skip UserMessage shapes so the synthetic interrupt sentinel
            # cannot leak through as response text.
            if (
                isinstance(message.get("content"), list)
                and "uuid" in message
                and "model" not in message
            ):
                continue

            # Primary path: any message with a content list is treated as an
            # AssistantMessage (same as the pre-fix behavior) once UserMessage
            # is excluded above.
            if isinstance(message.get("content"), list):
                text_parts = _extract_text_blocks(message["content"])
                if text_parts:
                    last_text = "\n".join(text_parts)
                continue

            # Legacy fallback: { type: "assistant", message: { content: ... } }
            if message.get("type") == "assistant" and "message" in message:
                sdk_message = message["message"]
                if isinstance(sdk_message, dict) and "content" in sdk_message:
                    content = sdk_message["content"]
                    if isinstance(content, list) and len(content) > 0:
                        text_parts = _extract_text_blocks(content)
                        if text_parts:
                            last_text = "\n".join(text_parts)
                    elif isinstance(content, str):
                        last_text = content

        return last_text

    @staticmethod
    def _extract_text_blocks(content: List[Any]) -> List[str]:
        text_parts = []
        for block in content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
            elif isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif isinstance(block, str):
                text_parts.append(block)
        return text_parts

    def extract_metadata(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract metadata like costs, tokens, and session info from SDK messages."""
        metadata = {
            "session_id": None,
            "total_cost_usd": 0.0,
            "duration_ms": 0,
            "num_turns": 0,
            "model": None,
        }

        for message in messages:
            # New SDK format - ResultMessage
            if message.get("subtype") == "success" and "total_cost_usd" in message:
                metadata.update(
                    {
                        "total_cost_usd": message.get("total_cost_usd", 0.0),
                        "duration_ms": message.get("duration_ms", 0),
                        "num_turns": message.get("num_turns", 0),
                        "session_id": message.get("session_id"),
                    }
                )
            # New SDK format - SystemMessage
            elif message.get("subtype") == "init" and "data" in message:
                data = message["data"]
                metadata.update({"session_id": data.get("session_id"), "model": data.get("model")})
            # Old format fallback
            elif message.get("type") == "result":
                metadata.update(
                    {
                        "total_cost_usd": message.get("total_cost_usd", 0.0),
                        "duration_ms": message.get("duration_ms", 0),
                        "num_turns": message.get("num_turns", 0),
                        "session_id": message.get("session_id"),
                    }
                )
            elif message.get("type") == "system" and message.get("subtype") == "init":
                metadata.update(
                    {"session_id": message.get("session_id"), "model": message.get("model")}
                )

        return metadata

    def estimate_token_usage(
        self, prompt: str, completion: str, model: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Estimate token usage based on character count.

        Uses rough approximation: ~4 characters per token for English text.
        This is approximate and may not match actual tokenization.
        """
        # Rough approximation: 1 token ≈ 4 characters
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(1, len(completion) // 4)

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def _cleanup_temp_dir(self):
        """Clean up temporary directory on exit."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temporary workspace: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory {self.temp_dir}: {e}")
