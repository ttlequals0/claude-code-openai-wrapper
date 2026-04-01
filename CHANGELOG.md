# Changelog

All notable changes to the Claude Code OpenAI Wrapper project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
