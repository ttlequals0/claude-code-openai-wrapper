# Claude Code OpenAI Wrapper -- Upgrade Plan

> **Historical document.** This plan was written 2025-11-02 for the SDK migration from `claude-code-sdk 0.0.14` to `claude-agent-sdk 0.1.6`. The migration is complete and the wrapper now runs on v0.1.18. Kept for reference.

## What was planned

### Phase 1: SDK Migration (completed)
- Replace `claude-code-sdk` with `claude-agent-sdk`
- Rename `ClaudeCodeOptions` to `ClaudeAgentOptions`
- Switch to structured system prompt format
- Handle settings sources change (SDK no longer auto-reads filesystem settings)

### Phase 2: OpenAI API parameter support (partially completed)
- `max_tokens` / `max_completion_tokens` -- now validated against per-model limits (v2.5.0)
- `stream_options.include_usage` -- implemented
- `temperature`, `top_p`, `stop` -- accepted but not passed through to Claude SDK
- `n > 1`, function calling -- not supported

### Key breaking changes that were handled
1. **System prompt**: No longer defaults to Claude Code preset; explicitly set via `{"type": "preset", "preset": "claude_code"}`
2. **Settings sources**: Must be explicitly enabled if needed
3. **Package name**: `claude-code-sdk` renamed to `claude-agent-sdk`

## What wasn't implemented

- OpenAI-style function calling / tool use translation
- In-process MCP servers via `create_sdk_mcp_server()`
- SDK hooks for pre/post tool validation
- `ClaudeSDKClient` for bidirectional conversations

These remain potential future work.

## References

- [Claude Agent SDK on PyPI](https://pypi.org/project/claude-agent-sdk/)
- [MIGRATION_STATUS.md](./MIGRATION_STATUS.md) -- migration completion report
