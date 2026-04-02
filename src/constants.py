"""
Constants and configuration for Claude Code OpenAI Wrapper.

Single source of truth for tool names, models, and other configuration values.

Usage Examples:
    # Check if a model is supported
    from src.constants import CLAUDE_MODELS
    if model_name in CLAUDE_MODELS:
        # proceed with request

    # Get default allowed tools
    from src.constants import DEFAULT_ALLOWED_TOOLS
    options = {"allowed_tools": DEFAULT_ALLOWED_TOOLS}

    # Use rate limits in FastAPI
    from src.constants import RATE_LIMIT_CHAT
    @limiter.limit(f"{RATE_LIMIT_CHAT}/minute")
    async def chat_endpoint(): ...

Note:
    - Tool configurations are managed by ToolManager (see tool_manager.py)
    - Model validation uses graceful degradation (warns but allows unknown models)
    - Rate limits can be overridden via environment variables
"""

import os

# Claude Code tool inventory (sourced from open-sourced Claude Code CLI)
CLAUDE_TOOLS = [
    "Agent", "Task", "SendMessage", "ListPeers",
    "Bash",
    "Glob", "Grep", "Read", "Edit", "Write", "NotebookEdit",
    "WebFetch", "WebSearch",
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskOutput", "TaskStop",
    "EnterPlanMode", "ExitPlanMode", "VerifyPlanExecution",
    "EnterWorktree", "ExitWorktree",
    "ToolSearch", "AskUserQuestion",
    "CronCreate", "CronDelete", "CronList", "RemoteTrigger",
    "TodoWrite", "Skill", "Brief", "Config",
    "REPL", "Sleep", "Monitor",
    "SendUserFile", "PushNotification",
    "ListMcpResources", "ReadMcpResource",
]

# Default tools to allow when tools are enabled
# Subset of CLAUDE_TOOLS that are safe and commonly used
DEFAULT_ALLOWED_TOOLS = [
    "Read",
    "Glob",
    "Grep",
    "Bash",
    "Write",
    "Edit",
]

# Tools to disallow by default (potentially dangerous or resource-intensive)
DEFAULT_DISALLOWED_TOOLS = [
    "Agent",  # Can spawn sub-agents
    "Task",  # Alias for Agent
    "WebFetch",  # External network access
    "WebSearch",  # External network access
    "SendMessage",  # External communication
    "RemoteTrigger",  # Remote execution
]

# Model metadata (sourced from open-sourced Claude Code CLI)
# Only models that differ from the default are listed explicitly.
_DEFAULT_MODEL_META = {"context_window": 200_000, "default_max_output": 32_000, "max_output_limit": 64_000}

_MODEL_OVERRIDES = {
    "claude-opus-4-6": {"default_max_output": 64_000, "max_output_limit": 128_000},
    "claude-sonnet-4-6": {"max_output_limit": 128_000},
    "claude-3-5-sonnet-20241022": {"default_max_output": 8_192, "max_output_limit": 8_192},
    "claude-3-5-haiku-20241022": {"default_max_output": 8_192, "max_output_limit": 8_192},
}

# All supported model IDs (order: newest first)
_ALL_MODEL_IDS = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-1-20250805",
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-3-7-sonnet-20250219",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
]

MODEL_METADATA = {
    model_id: {**_DEFAULT_MODEL_META, **_MODEL_OVERRIDES.get(model_id, {})}
    for model_id in _ALL_MODEL_IDS
}

# Derived from MODEL_METADATA so they can't drift out of sync
CLAUDE_MODELS = list(MODEL_METADATA.keys())

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6")
FAST_MODEL = "claude-haiku-4-5-20251001"

# Pricing tiers (per million tokens, USD)
# Sourced from open-sourced Claude Code CLI (src/utils/modelCost.ts)
_PRICING_SONNET = {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75}
_PRICING_OPUS = {"input": 5.0, "output": 25.0, "cache_read": 0.50, "cache_write": 6.25}
_PRICING_OPUS_LEGACY = {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75}
_PRICING_HAIKU_45 = {"input": 1.0, "output": 5.0, "cache_read": 0.10, "cache_write": 1.25}
_PRICING_HAIKU_35 = {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_write": 1.00}

MODEL_PRICING = {
    "claude-sonnet-4-6": _PRICING_SONNET,
    "claude-sonnet-4-5-20250929": _PRICING_SONNET,
    "claude-sonnet-4-20250514": _PRICING_SONNET,
    "claude-3-7-sonnet-20250219": _PRICING_SONNET,
    "claude-3-5-sonnet-20241022": _PRICING_SONNET,
    "claude-opus-4-6": _PRICING_OPUS,
    "claude-opus-4-5-20251101": _PRICING_OPUS,
    "claude-opus-4-1-20250805": _PRICING_OPUS_LEGACY,
    "claude-opus-4-20250514": _PRICING_OPUS_LEGACY,
    "claude-haiku-4-5-20251001": _PRICING_HAIKU_45,
    "claude-3-5-haiku-20241022": _PRICING_HAIKU_35,
}

# Web search cost (per request, all models)
WEB_SEARCH_COST_USD = 0.01

# Fallback model mapping: when an Opus model is overloaded, fall back to Sonnet
# Sourced from Claude Code's FallbackTriggeredError pattern
MODEL_FALLBACK_MAP = {
    "claude-opus-4-6": "claude-sonnet-4-6",
    "claude-opus-4-5-20251101": "claude-sonnet-4-5-20250929",
    "claude-opus-4-1-20250805": "claude-sonnet-4-20250514",
    "claude-opus-4-20250514": "claude-sonnet-4-20250514",
}

# Effort levels supported by Claude API
VALID_EFFORT_LEVELS = {"low", "medium", "high", "max"}

# Thinking modes supported by Claude API
VALID_THINKING_MODES = {"adaptive", "enabled", "disabled"}

# System Prompt Types
SYSTEM_PROMPT_TYPE_TEXT = "text"
SYSTEM_PROMPT_TYPE_PRESET = "preset"

# System Prompt Presets
SYSTEM_PROMPT_PRESET_CLAUDE_CODE = "claude_code"

# API Configuration
DEFAULT_MAX_TURNS = 10
DEFAULT_TIMEOUT_MS = 600000  # 10 minutes
DEFAULT_PORT = 8000

# Session Management
SESSION_CLEANUP_INTERVAL_MINUTES = 5
SESSION_MAX_AGE_MINUTES = 60

# Rate Limiting (requests per minute)
RATE_LIMIT_DEFAULT = 60
RATE_LIMIT_CHAT = 30
RATE_LIMIT_MODELS = 100
RATE_LIMIT_HEALTH = 200
