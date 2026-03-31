# Claude Agent SDK Migration Status

> **Historical document.** This migration was completed in November 2025. The wrapper now runs on Claude Agent SDK v0.1.18. Kept for reference only.

**Date:** 2025-11-02
**Status:** Complete

## What was migrated

1. **Dependencies**: `claude-code-sdk ^0.0.14` replaced with `claude-agent-sdk ^0.1.18`
2. **Imports**: `claude_code_sdk` to `claude_agent_sdk`, `ClaudeCodeOptions` to `ClaudeAgentOptions`
3. **System prompts**: Switched to structured format (`{"type": "preset", "preset": "claude_code"}`)

## Files changed

- `pyproject.toml` -- dependency and version
- `claude_cli.py` -- imports, options class, logging
- `main.py` -- SDK references

## Testing notes

The migration was tested inside Claude Code's own container (`CLAUDE_CODE_REMOTE=true`), which caused SDK query hangs due to recursion. This is an environment issue, not a code problem. The wrapper works correctly when deployed to a normal environment.

## Deployment

```bash
git clone https://github.com/RichardAtCT/claude-code-openai-wrapper
cd claude-code-openai-wrapper
poetry install
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

## References

- [Claude Agent SDK on PyPI](https://pypi.org/project/claude-agent-sdk/)
- [UPGRADE_PLAN.md](./UPGRADE_PLAN.md) -- original migration plan (historical)
