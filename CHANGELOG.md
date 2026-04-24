# Changelog

All notable changes to the Claude Code OpenAI Wrapper project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.9.2] - 2026-04-24

### Build / CI

- `Dockerfile`: `poetry install --only main` now excludes dev packages
  from the runtime image. Removes the one Trivy HIGH with an upstream
  fix (CVE-2026-32274, black < 26.3.1) and drops image size from
  1.18 GB to 775 MB. BUILD_INFO stamps cleanly.
- Added `.dockerignore` so `COPY . /app` stops pulling `.git`, `.venv`,
  `.hypothesis`, `.pytest_cache`, `tests`, `docs`, `.env*`, and editor
  cruft.
- Remaining Trivy HIGHs (7) are in the Debian 13.4 base (ncurses,
  nghttp2, systemd); all `fix: null` upstream. Accepted risk until
  `python:3.12-slim` rebases.
- `.github/workflows/ci.yml`: added `timeout-minutes: 15`,
  `fail-fast: false`, `poetry check --lock` to catch lockfile drift,
  replaced deprecated `safety check` with `pip-audit`, and added a
  `docker` job that smoke-builds the prod image on every PR.
- `.github/workflows/claude.yml`: repo-specific `claude_args` with a
  read-only tool allowlist (no write commands, no PR mutations).
- Ran `black` across `src/` and `tests/` so the linting gate in CI
  actually passes; 18 files reformatted with no behavioural change.
- Disabled the `Claude Code Review` workflow upstream; the file was
  removed from the repo in 2.9.1 but `pull_request_target` kept
  executing it from `main` until explicit disable.

## [2.9.1] - 2026-04-24

### Security

Closes the ten CodeQL code-scanning alerts open on `main`.

- **Workflow: `claude-code-review.yml` removed** (alert #1,
  `actions/untrusted-checkout/high`). The file checked out
  `pull_request.head.sha` inside a `pull_request_target` job, exposing
  repo secrets to untrusted code. Deleted entirely; automated PR review
  can be reintroduced later behind a non-privileged trigger.
- **Workflow: `ci.yml` permissions pinned** (alert #2,
  `actions/missing-workflow-permissions`). Added top-level
  `permissions: {contents: read}`.
- **Error responses no longer leak exception detail** (alerts #7-#10,
  `py/stack-trace-exposure`). `str(e)` has been replaced with static,
  client-safe strings in:
  - `_build_assistant_error_response` (new `_safe_assistant_error_message`
    helper keyed on the upstream subtype);
  - the `generate_streaming_response` SSE error chunk;
  - the chat-completions and Anthropic-messages 500 HTTPException
    handlers;
  - `/v1/debug/request`, which is now entirely gated behind
    `DEBUG_MODE`/`VERBOSE` and emits only the exception *type name* when
    enabled. All server-side logging of the full exception is preserved.
- **`MessageAdapter.filter_content` regexes hardened against
  polynomial ReDoS** (alerts #3-#6, `py/polynomial-redos`). The lazy
  `<tag>.*?</tag>` patterns were rewritten to the non-backtracking
  `<tag>[^<]*(?:<(?!/tag>)[^<]*)*</tag>` form and pre-compiled at module
  scope. The image-reference pattern now uses fixed upper bounds
  (`[^\]]{0,1024}` / `[^\s]{0,65536}`) instead of lazy quantifiers with
  a lookahead. A 1 MB input length guard short-circuits
  `filter_content` on pathological payloads.

### Tests

- New `tests/test_redos_safety.py`: six pathological inputs that the
  pre-fix regexes would have spent seconds-to-minutes on each complete
  in under 1 s. Plus behavioural regression tests asserting the
  rewritten patterns still strip `<thinking>`, extract nested
  `<attempt_completion>`/`<result>`, replace image tokens, and return
  oversized input unchanged.

### Notes

- Client-visible error message text has changed (now generic strings
  like "Chat completion failed"). The OpenAI-style `type` and `code`
  fields are unchanged, so programmatic error routing is unaffected.
- `/v1/debug/request` returns `{"debug_info": {"enabled": false, ...}}`
  unless `DEBUG_MODE=true` or `VERBOSE=true` is set on the server.

### Docker image

- `Dockerfile`: `poetry install --no-root` is now scoped to `--only main`.
  Dev-group packages (black, bandit, pytest, mypy, safety, etc.) no
  longer ship inside the runtime image. This removes the one Trivy
  HIGH with an available fix (CVE-2026-32274, `black < 26.3.1`) and
  drops the image from 1.18 GB to 775 MB.
- Added `.dockerignore` so `COPY . /app` stops pulling `.git`, `.venv`,
  `.hypothesis`, `.pytest_cache`, `tests`, `docs`, `.env*`, and editor
  cruft into the image. BUILD_INFO now stamps cleanly at build time.
- Remaining Trivy HIGHs (7) are in the Debian 13.4 base - ncurses
  (CVE-2025-69720), nghttp2 (CVE-2026-27135), and systemd
  (CVE-2026-29111). All have `fix: null` upstream at the time of this
  release; they will clear when `python:3.12-slim` rebases. Accepted
  risk.

### Workflows

- `.github/workflows/ci.yml`: added `timeout-minutes: 15`,
  `fail-fast: false`, `poetry check --lock` (catches the lockfile
  drift that burned us on the 0.1.65 SDK bump), replaced deprecated
  `safety check` with `pip-audit`, and added a `docker` job that
  smoke-builds the prod image on every PR.
- `.github/workflows/claude.yml`: repo-specific `claude_args` with a
  read-only tool allowlist (no write commands, no PR mutations) and
  inline documentation of why the `contains()` gate on user-controlled
  event fields is safe.

## [2.9.0] - 2026-04-23

### Changed

- **`claude-agent-sdk` bumped from `0.1.18` to `0.1.65`** (exact pin). 47 patch releases worth of CLI and subprocess-handling fixes. The rationale for bumping specifically now is the background-constant `error_during_execution` rate observed on 2.8.2 in production (~48/hr, `num_turns=2`, `usage.input_tokens=0`, `stderr_tail_chars=0` — CLI dying silently before reaching Claude). Notable fixes in the range:
  - **0.1.52** — `control_cancel_request` handling (#751): in-flight hook callbacks properly cancelled when the CLI abandons them. A plausible source of 2-turn silent abort.
  - **0.1.53** — string-prompt deadlock fix (#780): spawned `wait_for_result_and_end_input()` as a background task to avoid hangs on hook/MCP-heavy calls. Related symptom class.
  - **0.1.57** — thinking-config serialization fix (#796): `thinking={"type":"adaptive"}` and `{"type":"disabled"}` now use `--thinking` flag not `--max-thinking-tokens`. Directly affects the path the 2.8.0 `WRAPPER_MAP_MAX_TOKENS_TO_THINKING` opt-in touches.
  - **0.1.60** — `setting_sources=[]` no longer silently dropped (#822). W3C distributed-tracing propagation added.
  - **0.1.51** — preserve dropped fields on `AssistantMessage` and `ResultMessage` for forward compatibility (#718); `ResultMessage.errors` field now populated (#749).
  - Bundled Claude CLI advanced from 2.0.72 (at 0.1.18) to 2.1.118 (at 0.1.65) — 46 CLI versions of bug fixes, auth handling, and error reporting.

### Tests

- Full suite green on 0.1.65: 640 passed, 31 skipped. No test changes required — existing fixtures still match the dict shapes parse_claude_message consumes.

### Expected runtime impact

- Fewer `error_during_execution` subprocess failures (hypothesis to be confirmed post-deploy).
- `ResultMessage.errors` may now carry actual strings on failure paths, so the `claude_sdk_error` log line's `errors=` field should start populating instead of always `errors=[]`. This is the data we've been missing.
- `max_thinking_tokens` semantics on 0.1.57+ differ from 0.1.18 — our `WRAPPER_MAP_MAX_TOKENS_TO_THINKING=false` default makes this a no-op, but anyone opting in should retest.

## [2.8.2] - 2026-04-23

Dependency bump to clear trivy HIGH/CRITICAL findings against 2.8.1.
No code change.

### Security

Locked versions after `poetry lock` with the new constraints:

| Package | Before | After | CVEs cleared |
|---|---|---|---|
| fastapi | 0.115.14 | 0.128.1 | (bumped to allow starlette >=0.49) |
| starlette | 0.46.2 | 0.50.0 | CVE-2025-62727 (HIGH, DoS via Range header) |
| urllib3 | 2.5.0 | 2.6.3 | CVE-2025-66418, CVE-2025-66471, CVE-2026-21441 (HIGH) |
| python-multipart | 0.0.18 | 0.0.22 | CVE-2026-24486 (HIGH, path traversal) |
| cryptography | 46.0.3 | 46.0.7 | CVE-2026-26007 (HIGH) |
| pyjwt | 2.10.1 | 2.12.1 | CVE-2026-32597 (HIGH) |
| authlib | 1.6.6 | 1.7.0 | CVE-2026-27962 (CRITICAL), CVE-2026-28802, CVE-2026-28490, CVE-2026-28498 (HIGH) |
| mcp | 1.20.0 | 1.27.0 | CVE-2025-66416 (HIGH) |
| nltk | 3.9.2 | 3.9.4 | CVE-2025-14009 (CRITICAL), CVE-2026-0846 (HIGH) |

### Remaining (no fix available upstream)

- nltk CVE-2026-33231, CVE-2026-33236 (XML path traversal) — no patched version published; track upstream
- Debian base-image packages: libncursesw6, libnghttp2-14, libsystemd0, libtinfo6, libudev1, ncurses-base, ncurses-bin — no fix in current debian:13 stream; addressed when base image is rebased

### Changed

- `pyproject.toml`: explicit security-floor pins added for `starlette`, `urllib3`, `cryptography`, `pyjwt`, `authlib`, `mcp`, `nltk`. Each is a transitive of fastapi/claude-agent-sdk/bundled CLI but needs a minimum version higher than the parent's ceiling allowed, so we list them directly. `fastapi` widened to `>=0.119,<1.0` to allow starlette 0.49.x+.

## [2.8.1] - 2026-04-23

Hotfix on top of 2.8.0 after observing breaker cascade during live
reprocessing. Three small fixes; no new behavior.

### Fixed

- **Structured log extras now render in plain-text logs** (`src/main.py`): replaced every `logger.xxx("event", extra={...})` call with `logger.xxx(_kv("event", **fields))`. The wrapper's default format is `%(asctime)s - %(name)s - %(levelname)s - %(message)s` with no extras-printer, so `circuit_breaker_open`, `completion_result`, `claude_sdk_error*`, `claude_sdk_assistant_error`, and the streaming-path variants were all shipping to Loki with the state dict silently dropped. They now serialize inline as `event key=value key=value ...`.
- **Circuit breaker defaults loosened** (`src/circuit_breaker.py`): `min_requests_for_trip` raised from 10 to 20; `failure_ratio_threshold` raised from 0.5 to 0.75. The previous values tripped mid-way through a single episode's 6-8 detection windows when the upstream SDK returned a transient burst of `error_during_execution` (5/10 = 0.5), turning a recoverable hiccup into a full-episode outage via 503 cascade. All thresholds plus enable-state are now env-configurable: `WRAPPER_CIRCUIT_BREAKER_ENABLED`, `WRAPPER_CIRCUIT_BREAKER_THRESHOLD`, `WRAPPER_CIRCUIT_BREAKER_MIN_REQUESTS`, `WRAPPER_CIRCUIT_BREAKER_OPEN_SECONDS`, `WRAPPER_CIRCUIT_BREAKER_WINDOW_SECONDS`. Setting `WRAPPER_CIRCUIT_BREAKER_ENABLED=false` short-circuits both `allow_request()` and `record()`, acting as a kill switch for situations where the breaker itself is the problem.

### Added

- **CLI subprocess stderr capture** (`src/claude_cli.py`): bounded ring buffer (40 lines) installed as `ClaudeAgentOptions.stderr` callback on every request. On non-success `ResultMessage`, the tail is logged at WARNING level with the session id and num_turns, AND attached to the yielded dict as `stderr_tail` so downstream `parse_claude_message` forwards it onto `ClaudeResultError.stderr_tail`. The `chat_completions` error handler now logs it alongside the `claude_sdk_error` k/v line. Fixes the 2.8.0 gap where `error_during_execution` with `input_tokens=0, num_turns=2` gave us no insight into WHY the CLI subprocess died.

### Changed

- `ClaudeResultError` gained a `stderr_tail` attribute (default `None`).
- Breaker snapshot dict now also includes `enabled` and `min_requests_for_trip` so the snapshot body on `503 circuit_breaker_open` responses matches what the env var set.

## [2.8.0] - 2026-04-23

### Fixed

- **SDK `error_max_turns` no longer leaks `[Request interrupted by user]` as response content** (`src/claude_cli.py`): `parse_claude_message` now raises `ClaudeResultError` when any `ResultMessage` has `is_error=True` or a subtype in `{error_max_turns, error_during_execution, error}`. The SDK inserts a synthetic `UserMessage(text='[Request interrupted by user]')` right before those results; previously the fallback loop returned that text as the assistant response, which shipped as valid content to OpenAI clients and propagated into downstream artifacts (e.g. MinusPod chapter titles). `UserMessage` is now explicitly filtered out of response-text collection (identifiable by `uuid` field with no `model` field).
- **`max_turns=1` when `enable_tools=False` raised to `3`** (`src/main.py:_build_claude_options`): the hardcoded `max_turns=1` caused `error_max_turns` on any prompt where the agent engaged extended thinking and then needed a second turn to emit the final assistant message. New default is configurable via `WRAPPER_DEFAULT_MAX_TURNS`.
- **`max_tokens -> max_thinking_tokens` mapping is off by default** (`src/models.py`): OpenAI `max_tokens` is a response-length cap; the Claude Agent SDK has no direct equivalent. Mapping it to `max_thinking_tokens` caused short prompts (e.g. `max_tokens=500` for a title) to burn the thinking budget before emitting output, occasionally busting `max_turns`. Opt in to the legacy mapping via `WRAPPER_MAP_MAX_TOKENS_TO_THINKING=true`.
- **Non-success `ResultMessage` now produces a proper OpenAI-shaped HTTP response** (`src/main.py`): `error_max_turns` -> `200` with `finish_reason="length"` and empty `content`; other SDK errors -> `502` with a structured error body; streaming path emits a terminal SSE event with the matching `finish_reason` and `[DONE]`.

### Added

- **`ClaudeResultError` exception** (`src/claude_cli.py`): typed error surface for SDK failures. Carries `subtype`, `num_turns`, `errors`, `stop_reason`, and `error_message`.
- **Structured AssistantMessage error taxonomy** (`src/main.py`): `AssistantMessage.error` literals map to HTTP status codes -- `rate_limit` -> 429 with `Retry-After: 30`, `billing_error` -> 402, `authentication_failed` -> 401, `invalid_request` -> 400, `server_error`/`unknown` -> 502. Parser also detects `RateLimitInfo` messages (SDK 0.1.49+, future-compatible).
- **Circuit breaker on SDK errors** (`src/circuit_breaker.py`): in-process rolling-window breaker. Default: opens when >=50% of the last 60s are failures and >=10 requests, 30s cool-off, half-opens with a single probe. Completion handler returns `503 Retry-After: 30` with a structured body when the breaker is open.
- **`/healthz/deep` endpoint** (`src/main.py`): end-to-end probe that actually exercises the completion path. Tracks a rolling window of 10 outcomes and returns `503` when the failure rate exceeds 20%. Unlike `/health` (process liveness only), this catches upstream-SDK incidents that leave the wrapper process up while returning garbage.
- **Structured `completion_result` log line** (`src/main.py`): one INFO-level record per successful completion with `request_id`, `session_id`, `subtype`, `num_turns`, `duration_ms`, `total_cost_usd`, `is_error`, `finish_reason`, `model`, and token counts. Simplifies Grafana triage.
- **`BUILD_INFO` image stamp** (`Dockerfile`): records the installed `claude-agent-sdk` version and bundled-CLI presence at build time. Logged at startup via `_log_build_info()`.
- **Multi-stage Dockerfile with `dev` and `prod` targets**: `dev` keeps `--reload` for local iteration; `prod` runs with `--workers 2 --no-access-log` (override via `UVICORN_WORKERS`). `docker-compose.yml` defaults to the `prod` target.
- **Regression tests** covering the sentinel leak and the error taxonomy: `tests/test_claude_cli_unit.py` (`test_error_max_turns_raises_instead_of_returning_sentinel`, `test_user_message_content_never_leaks_as_response`, `test_is_error_true_raises_even_when_subtype_missing`, `test_assistant_rate_limit_raises`), `tests/test_error_path_unit.py` (HTTP-shape translations for each error class), `tests/test_circuit_breaker_unit.py` (state machine).

### Changed

- **SDK pinned exactly** (`pyproject.toml`): `claude-agent-sdk = "0.1.18"` (was `^0.1.18`). The caret range resolved to whatever 0.1.x was latest at install time, which let semantics drift between Docker builds without a code change (SDK 0.1.57 changed how thinking config is serialized to the CLI). Bump this pin deliberately and regenerate `poetry.lock` in the same commit. Upstream latest at time of pin: `0.1.65`.
- **`docker-compose.yml`**: adds `build.target: prod`, documents new env vars (`UVICORN_WORKERS`, `WRAPPER_DEFAULT_MAX_TURNS`, `WRAPPER_MAP_MAX_TOKENS_TO_THINKING`).

### Notes

- `claude-agent-sdk` stays pinned to `0.1.18` because that's the version the production image has been running. Bump to `0.1.65` in a separate commit after validating behavior changes across `0.1.18..0.1.65` (particularly `0.1.57` thinking handling and `0.1.49` `RateLimitInfo` surfacing).
- Upstream consumer affected by the `error_max_turns` leak was MinusPod; see that project's `2.0.12` release notes for the consumer-side defensive changes landing in parallel.

## [2.7.0] - 2026-04-16

### Added

- **Claude Opus 4.7** (`claude-opus-4-7`): new flagship model -- 1M token context window, 128K max output, $5/$25 per MTok, falls back to `claude-sonnet-4-6` on overload

### Changed

- **Model metadata corrections** (`src/constants.py`): aligned with Anthropic docs (`platform.claude.com/docs/en/about-claude/models/overview`)
  - `claude-opus-4-6`: context window 200K -> 1M
  - `claude-sonnet-4-6`: context window 200K -> 1M, max output 128K -> 64K (synchronous Messages API)
  - `claude-opus-4-1-20250805`: max output 64K -> 32K
  - `claude-opus-4-20250514`: max output 64K -> 32K
- **Default model example**: `.env.example` `DEFAULT_MODEL` now matches code default (`claude-sonnet-4-6`)
- **Landing page quickstart** (`src/main.py`): uses `claude-sonnet-4-6` instead of dated Sonnet 4.5 snapshot
- **Debug endpoint example**: `example_valid_request.model` updated from retired `claude-3-sonnet-20240229` to `claude-sonnet-4-6`

### Removed

- **Retired models** removed from `CLAUDE_MODELS`, `MODEL_METADATA`, `MODEL_PRICING`:
  - `claude-3-7-sonnet-20250219` (retired 2026-02-19)
  - `claude-3-5-sonnet-20241022` (retired 2025-10-28)
  - `claude-3-5-haiku-20241022` (retired 2026-02-19)
- `_PRICING_HAIKU_35` constant (no remaining consumers)

## [2.6.0] - 2026-04-02

### Added

- **OpenAI Function Calling** (`src/function_calling.py`): Simulates OpenAI tool/function calling via system prompt injection and response parsing
  - Converts `tools` array and `tool_choice` into Claude-compatible system prompts
  - Parses Claude's response for ```tool_calls``` blocks and bare JSON arrays
  - Returns OpenAI-format `tool_calls` in the response with generated call IDs
  - Handles multi-turn conversations: assistant tool_calls and tool result messages converted to text
- **JSON Schema in response_format**: Support for `response_format.type = "json_schema"` with schema definition
  - Schema injected into user prompt (not system_prompt) for SDK subprocess compatibility
  - Includes explicit rules for required properties, exact names, and exact types
- **Streaming Fence Stripping** (`JsonFenceStripper` in `src/message_adapter.py`): Real-time removal of markdown ```json fences during streaming
  - Hold-back buffers detect and strip opening/closing fences across chunk boundaries
  - Replaces full-buffer strategy for JSON streaming -- chunks flow in real-time
- **CPU Watchdog** (`src/cpu_watchdog.py`): Background CPU monitor for Docker/Linux deployments
  - Reads /proc/self/stat every 30s, sends SIGTERM after 3 consecutive strikes above 80% CPU
  - Disabled by default, enable with `WATCHDOG_ENABLED=true`
  - Configurable interval, threshold, and strike count via env vars

### Changed

- **Message model**: Added `tool` role, `tool_calls`, `tool_call_id` fields for function calling support
- **ResponseFormat model**: Extended with `json_schema` type and `JsonSchema` model
- **Choice/StreamChoice**: Added `tool_calls` finish reason

## [2.5.2] - 2026-04-01

### Fixed

- **Removed fake tools**: Removed BashOutput, KillShell, and SlashCommand from tool inventory -- these do not exist in Claude Code's tool registry and were diversions in the source

### Added

- **11 real tools**: Added Brief, Config, ListPeers, REPL, Sleep, Monitor, SendUserFile, PushNotification, ListMcpResources, ReadMcpResource, VerifyPlanExecution -- all verified against Claude Code source (`src/tools.ts:getAllBaseTools()`)

### Changed

- Tool count: 33 -> 41 (removed 3 fake, added 11 real)

## [2.5.1] - 2026-04-01

### Fixed

- **GitHub URL**: Corrected repository link from aaronlippold fork to ttlequals0/claude-code-openai-wrapper
- **OpenAPI Version**: FastAPI docs version now uses dynamic `__version__` instead of hardcoded "1.0.0"

### Changed

- **Landing Page Redesign**: Complete UI overhaul replacing generic AI-generated aesthetics with a clean, utilitarian developer dashboard
  - Dropped Pico CSS in favor of custom minimal CSS
  - Typography: DM Sans headings, JetBrains Mono for code paths
  - Muted neutral color palette with method-specific badge colors (blue GET, amber POST, red DELETE)
  - Removed gradient logo container, pulsing animations, and decorative section icons
- **Endpoint Documentation**: Landing page now lists all 25 endpoints grouped into 8 categories (Core API, Models, Sessions, Tools, MCP Servers, Cache, Auth/Debug, System) -- previously showed only 9
- **Configuration Section**: Condensed from a full card into a compact footer line

## [2.5.0] - 2026-03-31

### Added

- **Model Metadata**: Per-model context window sizes, default/max output token limits sourced from open-sourced Claude Code CLI
- **Model Pricing Data**: Per-model pricing (input, output, cache read/write) for all supported models, sourced from Claude Code source
- **Cost Tracker** (`src/cost_tracker.py`): New module for per-request and per-session cost estimation using authoritative pricing data
  - Tracks input/output tokens, cache tokens, web search requests
  - Per-model usage breakdown per session
- **Retry Logic** (`src/retry.py`): New module implementing retry with exponential backoff and jitter
  - Configurable max retries (default 10), base delay (500ms), max delay (30s)
  - Model fallback: after 3 consecutive 529 (overloaded) errors, falls back from Opus to Sonnet
  - Retryable status codes: 429, 529, 5xx, 401, 400
- **New Tools**: Added 18 tools to match Claude Code's actual tool inventory:
  - `Agent` (with `Task` as backward-compatible alias)
  - `SendMessage`, `TaskCreate`, `TaskUpdate`, `TaskGet`, `TaskList`, `TaskOutput`, `TaskStop`
  - `EnterPlanMode`, `ExitPlanMode`, `EnterWorktree`, `ExitWorktree`
  - `ToolSearch`, `AskUserQuestion`
  - `CronCreate`, `CronDelete`, `CronList`, `RemoteTrigger`
- **Effort Level Support**: New `X-Claude-Effort` header (low, medium, high, max)
- **Thinking Mode Support**: New `X-Claude-Thinking` header (adaptive, enabled, disabled)
- **Max Tokens Validation**: Model-specific max_tokens validation and capping via `ParameterValidator.validate_max_tokens()`
- **Model Fallback Map**: Automatic Opus-to-Sonnet fallback mapping for overload resilience

### Changed

- **Model List Updated**: Added `claude-sonnet-4-6` (latest) and re-added Claude 3.x models (`claude-3-7-sonnet-20250219`, `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`) which are confirmed supported by Claude Code
- **Default Model**: Changed from `claude-sonnet-4-5-20250929` to `claude-sonnet-4-6` (latest Sonnet)
- **Tool Safety Classifications**: Updated based on Claude Code source -- `Bash` now marked as requiring permissions, `Agent`/`SendMessage`/`RemoteTrigger` marked as unsafe
- **Default Disallowed Tools**: Added `SendMessage` and `RemoteTrigger` to default disallow list

## [2.4.2] - 2026-02-06

### Added

- **Auth Method Awareness in Model Service**: Model refresh now respects `CLAUDE_AUTH_METHOD` configuration
  - `anthropic` auth: Full support for dynamic model fetching from API
  - `cli`, `bedrock`, `vertex` auth: Uses static fallback model list (API key not available)
- **Auth Method in Responses**: `/v1/models/refresh` and `/v1/models/status` responses now include `auth_method` field
- **Landing Page Updates**: Added `/v1/models/status` and `/v1/models/refresh` endpoint cards to the dashboard UI with interactive refresh button
- **Unit Tests**: Comprehensive tests for different auth method behaviors in model service

### Changed

- **Updated Model List**: Added `claude-opus-4-6` (latest), removed outdated `claude-opus-4-5-20250929` from static fallback list
- **Improved Error Messages**: Refresh endpoint now returns clear message when using non-anthropic auth methods

## [2.4.1] - 2026-02-06

### Added

- **Dynamic Model Refresh**: New `POST /v1/models/refresh` endpoint to refresh models from Anthropic API at runtime without server restart
- **Model Service Status**: New `GET /v1/models/status` endpoint returning service status including source (api/fallback) and last refresh timestamp
- **Refresh Tracking**: ModelService now tracks `_last_refresh` timestamp and `_source` (api or fallback) for observability
- **Unit Tests**: Comprehensive tests for model refresh functionality including success/failure scenarios, timestamp tracking, and status reporting

### Changed

- **ModelService**: Enhanced with `refresh_models()` async method and `get_status()` method for runtime model management

## [2.4.0] - 2026-02-04

### Added

- **Improved JSON Mode Instructions**: Enhanced system prompt instructions with numbered rules format, explicit prohibition of preambles, and stronger emphasis on first/last character requirements
- **Common Preamble Detection**: New `COMMON_PREAMBLES` constant with 19 common Claude preambles that are automatically stripped
- **Balanced JSON Extraction**: New `_find_balanced_json()` helper method using brace/bracket matching that correctly handles escaped quotes and braces inside strings
- **JSON Extraction Metadata**: New `JsonExtractionResult` dataclass and `extract_json_with_metadata()` method providing detailed extraction information
- **Metadata-Enabled Enforcement**: New `enforce_json_format_with_metadata()` method returning both extracted content and extraction details
- **Enhanced Extraction Diagnostics**: New `_log_extraction_diagnostics()` method for detailed debugging of extraction failures
- **Request Deduplication Cache**: Optional caching layer for identical requests with LRU eviction and TTL expiration
  - Configure via environment variables: `REQUEST_CACHE_ENABLED`, `REQUEST_CACHE_MAX_SIZE`, `REQUEST_CACHE_TTL_SECONDS`
  - Enable per-request via `X-Enable-Cache: true` header
- **Cache Management Endpoints**:
  - `GET /v1/cache/stats` - View cache statistics
  - `POST /v1/cache/clear` - Clear all cached entries
- **Unit Tests**: Comprehensive tests for balanced JSON extraction, metadata tracking, and request cache

### Changed

- **JSON Extraction Priority**: Reordered extraction methods for better reliability:
  1. Pure JSON (fast path)
  2. Preamble removal + parse
  3. Markdown code block extraction
  4. Balanced brace/bracket matching
  5. First-to-last fallback
- **Improved Logging**: JSON enforcement now logs extraction method used (e.g., `method=preamble_removed`)
- **Debug Output**: Enhanced debug logging with extraction metadata in both streaming and non-streaming modes

### Fixed

- JSON extraction now correctly handles escaped quotes (`\"`) within strings
- JSON extraction no longer confused by braces/brackets inside string values

## [2.3.1] - Previous Release

Initial tracked version with JSON mode support.
