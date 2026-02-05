# Changelog

All notable changes to the Claude Code OpenAI Wrapper project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
