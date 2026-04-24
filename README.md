# Claude Code OpenAI API Wrapper

OpenAI API-compatible wrapper for Claude Code. Drop it in front of any OpenAI client library and talk to Claude instead.

## Version

**Current:** 2.9.3

Highlights of recent releases (full history in [CHANGELOG.md](./CHANGELOG.md)):

- **2.9.x** - CodeQL hardening: sanitised error responses (no more `str(e)` to clients), `filter_content` rewrite against polynomial ReDoS, `/v1/debug/request` gated behind `DEBUG_MODE`/`VERBOSE`, workflow permissions pinned. Image trimmed to 775 MB (`poetry install --only main`, `.dockerignore`). `claude-agent-sdk` pinned to 0.1.65 with the `[otel]` extra.
- **2.8.x** - Security dep bumps, breaker defaults loosened, CLI stderr capture, structured-log state unmasked.
- **2.7.0** - Added `claude-opus-4-7`; retired `claude-3-*` family; corrected context-window and max-output metadata.
- **2.6.0** - OpenAI function calling simulation (`tools` / `tool_choice`), JSON schema support in `response_format`, real-time streaming fence stripping, CPU watchdog.
- **2.5.x** - Landing-page redesign, model catalogue from the open-sourced Claude Code source, 41 tools tracked, retry + model fallback, cost tracking, `X-Claude-Effort` / `X-Claude-Thinking` headers.

## Status

Production ready. **650 tests passing (31 skipped)**. Streaming works. Sessions work. JSON mode works. Function calling works. Tools are off by default for speed - pass `enable_tools: true` to turn them on. Auth supports API key, Bedrock, Vertex AI, and CLI.

## Quick Start

```bash
# Clone and install
git clone https://github.com/ttlequals0/claude-code-openai-wrapper
cd claude-code-openai-wrapper
poetry install

# Authenticate (pick one)
export ANTHROPIC_API_KEY=your-api-key
# or: claude auth login

# Start
poetry run uvicorn src.main:app --reload --port 8000

# Test
poetry run pytest tests/
```

Server is at `http://localhost:8000`. Point your OpenAI client there.

## Prerequisites

1. **Python 3.10+**
2. **Poetry** for dependency management:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```
3. **Authentication** (pick one):
   - `export ANTHROPIC_API_KEY=your-api-key` (recommended)
   - `claude auth login` (CLI auth)
   - AWS Bedrock or Google Vertex AI (see Configuration)

The Claude Code CLI comes bundled with the SDK. No Node.js or npm needed.

## Installation

```bash
git clone https://github.com/ttlequals0/claude-code-openai-wrapper
cd claude-code-openai-wrapper
poetry install
cp .env.example .env  # edit with your preferences
```

## Configuration

Edit `.env`:

```env
# Auth (optional - auto-detects if not set)
# CLAUDE_AUTH_METHOD=cli|api_key|bedrock|vertex

# Optional client API key protection
# API_KEY=your-optional-api-key

PORT=8000
MAX_TIMEOUT=600000           # milliseconds (10 min default)
# CLAUDE_CWD=/path/to/workspace   # defaults to isolated temp dir
# DEFAULT_MODEL=claude-sonnet-4-6  # override default model
```

### Working Directory

By default, Claude Code runs in an isolated temporary directory so it can't access the wrapper's own source. Set `CLAUDE_CWD` to point it at a specific project instead.

### API Key Protection

If no `API_KEY` is set, the server prompts on startup whether to generate one. Useful for remote access over VPN or Tailscale.

### Rate Limiting

Per-IP rate limiting is on by default. Per-endpoint defaults and the env vars that override them:

| Endpoint group | Default | Env var |
|----------------|---------|---------|
| `/v1/chat/completions`, `/v1/messages` | 10/min | `RATE_LIMIT_CHAT_PER_MINUTE` |
| `/v1/debug/request` | 2/min | `RATE_LIMIT_DEBUG_PER_MINUTE` |
| `/v1/auth/status` | 10/min | `RATE_LIMIT_AUTH_PER_MINUTE` |
| `/v1/sessions/*` | 15/min | `RATE_LIMIT_SESSION_PER_MINUTE` |
| `/health`, `/healthz/deep` | 30/min | `RATE_LIMIT_HEALTH_PER_MINUTE` |
| everything else | 30/min | `RATE_LIMIT_PER_MINUTE` |

Disable entirely with `RATE_LIMIT_ENABLED=false`.

## Running the Server

```bash
# Development (auto-reload)
poetry run uvicorn src.main:app --reload --port 8000

# Production
poetry run claude-wrapper
```

## Docker

Pre-built image on Docker Hub: `ttlequals0/claude-code-openai-wrapper`.

```bash
# Pull and run
docker run -d -p 8000:8000 \
  -v ~/.claude:/root/.claude \
  --name claude-wrapper \
  ttlequals0/claude-code-openai-wrapper:latest

# Pin to a specific version
docker run -d -p 8000:8000 \
  -v ~/.claude:/root/.claude \
  --name claude-wrapper \
  ttlequals0/claude-code-openai-wrapper:2.9.3

# Or build locally (prod stage is the default target)
docker build --platform linux/amd64 -t claude-wrapper:local .
```

Docker Compose (matches `docker-compose.yml` in the repo):

```yaml
version: '3.8'
services:
  claude-wrapper:
    image: ttlequals0/claude-code-openai-wrapper:latest
    pull_policy: always   # redeploy webhooks re-pull :latest
    build:
      context: .
      target: prod
    container_name: claude-wrapper
    ports:
      - "8000:8000"
    volumes:
      - ~/.claude:/root/.claude
    environment:
      - PORT=8000
      - MAX_TIMEOUT=600000
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

### Environment variables

Listed in roughly the order you will reach for them.

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | `8000` |
| `CLAUDE_WRAPPER_HOST` | Bind address (`127.0.0.1` for local-only, `0.0.0.0` for all) | `0.0.0.0` |
| `MAX_TIMEOUT` | Per-request timeout (ms) | `600000` (10 min) |
| `MAX_REQUEST_SIZE` | Max request body size (bytes) | `10485760` (10 MB) |
| `CLAUDE_CWD` | Working directory Claude Code runs in | isolated temp dir |
| `CLAUDE_AUTH_METHOD` | `cli`, `api_key`, `bedrock`, `vertex` | auto-detect |
| `API_KEY` | Require this key on every request; prompts at startup if unset | interactive prompt |
| `ANTHROPIC_API_KEY` | Direct API key (for `api_key` auth) | - |
| `CLAUDE_CODE_USE_BEDROCK` | Enable AWS Bedrock backend | `false` |
| `AWS_REGION` / `AWS_DEFAULT_REGION` / `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Bedrock credentials | - |
| `CLAUDE_CODE_USE_VERTEX` | Enable Google Vertex AI backend | `false` |
| `ANTHROPIC_VERTEX_PROJECT_ID` / `CLOUD_ML_REGION` / `GOOGLE_APPLICATION_CREDENTIALS` | Vertex credentials | - |
| `DEFAULT_MODEL` | Default model id when request omits one | `claude-sonnet-4-6` |
| `DEBUG_MODE` | Enable debug logging and unlock `/v1/debug/request` | `false` |
| `VERBOSE` | Same unlock effect on `/v1/debug/request` | `false` |
| `CORS_ORIGINS` | Allowed CORS origins (JSON array) | `["*"]` |
| `REQUEST_CACHE_ENABLED` | Enable request-dedup cache | `false` |
| `REQUEST_CACHE_TTL_SECONDS` | Cache entry TTL | service-managed |
| `REQUEST_CACHE_MAX_SIZE` | Max cached entries | service-managed |
| `WRAPPER_DEFAULT_MAX_TURNS` | Default `max_turns` when caller does not enable tools | `3` |
| `WRAPPER_MAP_MAX_TOKENS_TO_THINKING` | Map OpenAI `max_tokens` to Claude `max_thinking_tokens` (legacy) | `false` |
| `WATCHDOG_ENABLED` | Enable CPU watchdog (for Docker) | `true` |
| `WATCHDOG_CPU_THRESHOLD` / `WATCHDOG_INTERVAL` / `WATCHDOG_STRIKES` | Watchdog tuning | see `src/cpu_watchdog.py` |
| `UVICORN_WORKERS` | Worker count for the prod image | `2` |
| `RATE_LIMIT_ENABLED` / `RATE_LIMIT_*_PER_MINUTE` | See rate-limit section above | - |

## Usage Examples

### curl

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [
      {"role": "user", "content": "What is 2 + 2?"}
    ]
  }'
```

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-api-key-if-required"
)

# Basic completion
response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What files are in the current directory?"}
    ]
)
print(response.choices[0].message.content)

# With tools enabled
response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[
        {"role": "user", "content": "What files are in the current directory?"}
    ],
    extra_body={"enable_tools": True}
)

# Streaming
stream = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "Explain quantum computing"}],
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### Claude-specific headers

Claude-specific options via HTTP headers:

| Header | Values | Description |
|--------|--------|-------------|
| `X-Claude-Max-Turns` | integer | Max conversation turns |
| `X-Claude-Allowed-Tools` | comma-separated | Tools to allow |
| `X-Claude-Permission-Mode` | `default`, `acceptEdits`, `bypassPermissions`, `plan` | Permission mode |
| `X-Claude-Effort` | `low`, `medium`, `high`, `max` | Model effort level |
| `X-Claude-Thinking` | `adaptive`, `enabled`, `disabled` | Extended thinking mode |
| `X-Claude-Max-Thinking-Tokens` | integer | Thinking token budget |
| `X-Enable-Cache` | `true` / `1` / `yes` | Opt in to response cache on this request |

## Supported Models

Model IDs, context windows, and pricing are sourced from the Anthropic models docs (`platform.claude.com/docs/en/about-claude/models/overview`) and mirrored in `src/constants.py`.

### Latest
| Model | Context | Max Output | Input $/MTok | Output $/MTok |
|-------|---------|-----------|-------------|--------------|
| `claude-opus-4-7` | 1M | 128K | $5 | $25 |
| `claude-sonnet-4-6` (default) | 1M | 64K | $3 | $15 |
| `claude-haiku-4-5-20251001` | 200K | 64K | $1 | $5 |

### Legacy (active, consider migrating)
| Model | Context | Max Output | Input $/MTok | Output $/MTok |
|-------|---------|-----------|-------------|--------------|
| `claude-opus-4-6` | 1M | 128K | $5 | $25 |
| `claude-opus-4-5-20251101` | 200K | 64K | $5 | $25 |
| `claude-opus-4-1-20250805` | 200K | 32K | $15 | $75 |
| `claude-sonnet-4-5-20250929` | 200K | 64K | $3 | $15 |

### Deprecated (retires 2026-06-15)
| Model | Context | Max Output | Input $/MTok | Output $/MTok | Replacement |
|-------|---------|-----------|-------------|--------------|-------------|
| `claude-sonnet-4-20250514` | 200K | 64K | $3 | $15 | `claude-sonnet-4-6` |
| `claude-opus-4-20250514` | 200K | 32K | $15 | $75 | `claude-opus-4-7` |

## Session Continuity

Pass a `session_id` to keep conversation context across requests:

```python
# Start a conversation
response1 = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "My name is Alice."}],
    extra_body={"session_id": "my-session"}
)

# Continue it - Claude remembers the context
response2 = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "What's my name?"}],
    extra_body={"session_id": "my-session"}
)
```

Sessions expire after 1 hour of inactivity. Management endpoints:
- `GET /v1/sessions` - list active sessions
- `GET /v1/sessions/{id}` - session details
- `DELETE /v1/sessions/{id}` - delete session
- `GET /v1/sessions/stats` - session statistics

## API Endpoints

### Core API
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Landing page with API explorer |
| `/v1/chat/completions` | POST | OpenAI-compatible chat |
| `/v1/messages` | POST | Anthropic-compatible messages |

### Models
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/models` | GET | List available models |
| `/v1/models/status` | GET | Model service status |
| `/v1/models/refresh` | POST | Refresh model catalogue |

### Sessions
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/sessions` | GET | List active sessions |
| `/v1/sessions/stats` | GET | Session statistics |
| `/v1/sessions/{id}` | GET | Get session by ID |
| `/v1/sessions/{id}` | DELETE | Delete session |

### Tools
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/tools` | GET | List available tools |
| `/v1/tools/config` | GET | Get tool configuration |
| `/v1/tools/config` | POST | Update tool configuration |
| `/v1/tools/stats` | GET | Tool usage statistics |

### MCP Servers
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/mcp/servers` | GET | List MCP servers |
| `/v1/mcp/servers` | POST | Register MCP server |
| `/v1/mcp/connect` | POST | Connect to MCP server |
| `/v1/mcp/disconnect` | POST | Disconnect MCP server |
| `/v1/mcp/stats` | GET | MCP statistics |

### Cache / Auth / System
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/cache/stats` | GET | Cache statistics |
| `/v1/cache/clear` | POST | Clear request cache |
| `/v1/auth/status` | GET | Auth status |
| `/v1/compatibility` | POST | Parameter compatibility check |
| `/v1/debug/request` | POST | Request debugging; **emits only `{"enabled": false}` unless `DEBUG_MODE` or `VERBOSE` is set** |
| `/health` | GET | Liveness probe (no upstream call) |
| `/healthz/deep` | GET | Deep readiness probe (performs an SDK round-trip) |
| `/version` | GET | Wrapper version |

## Function Calling

Pass OpenAI-format tool definitions. The wrapper injects them into Claude's system prompt and parses structured responses back into `tool_calls` format.

```python
response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "What's the weather in NYC?"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    }],
    tool_choice="auto",
)

# Response includes tool_calls when Claude decides to call a function
if response.choices[0].finish_reason == "tool_calls":
    for tc in response.choices[0].message.tool_calls:
        print(f"Call: {tc.function.name}({tc.function.arguments})")
```

Supports `tool_choice`: `"auto"` (default), `"required"`, `"none"`, or `{"type": "function", "function": {"name": "..."}}`.

Multi-turn tool conversations work - pass assistant messages with `tool_calls` and `tool` role result messages back. The wrapper converts them to text for Claude.

## JSON Response Mode

Set `response_format` to get JSON back:

```python
response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "List 3 colors with hex codes"}],
    response_format={"type": "json_object"}
)
```

With `json_object` mode, the wrapper adds system prompt instructions for JSON output, strips preambles like "Here is the JSON:", and uses brace-matching extraction as a fallback. Works streaming and non-streaming. JSON schema is also accepted via `response_format={"type": "json_schema", "json_schema": {...}}`.

## Limitations

- Images in messages are converted to text placeholders.
- `temperature` and `top_p` are applied via system-prompt instructions (best-effort approximation, not native SDK parameters).
- `presence_penalty` and `frequency_penalty` are accepted but ignored.
- Multiple responses (`n > 1`) are not supported.

## Testing

```bash
# Run the full test suite (650 tests, ~3 s on a laptop)
poetry run pytest tests/

# Quick endpoint test (server must be running)
poetry run python tests/test_endpoints.py
```

## Terms

You need your own Claude subscription or API access. This wrapper translates request formats - it does not provide Claude access.

| Use Case | Recommended Auth |
|----------|------------------|
| Personal projects | CLI Auth or API Key |
| Business / commercial | API Key, Bedrock, or Vertex AI |
| High-scale | Bedrock or Vertex AI |

See [Anthropic's Terms of Service](https://www.anthropic.com/legal).

## License

MIT

## Contributing

PRs welcome.
