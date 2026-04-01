# Claude Code OpenAI API Wrapper

An OpenAI API-compatible wrapper for Claude Code, powered by the Claude Agent SDK v0.1.18. Use Claude Code with any OpenAI client library.

## Version

**Current:** 2.5.1

What's new in 2.5.x:
- Landing page redesigned with all 25 endpoints grouped by category
- Model list updated from open-sourced Claude Code source (11 models, per-model metadata and pricing)
- 33 tools tracked (up from 15), matching Claude Code's actual inventory
- Cost tracking with authoritative per-model pricing
- Retry logic with exponential backoff and model fallback
- `X-Claude-Effort` and `X-Claude-Thinking` headers for fine-grained control
- Model-specific `max_tokens` validation

See [CHANGELOG.md](./CHANGELOG.md) for full history.

## Status

Production ready. Core features working and tested:
- Chat completions with Claude Agent SDK v0.1.18
- Anthropic Messages API (`/v1/messages`)
- Streaming and non-streaming responses
- OpenAI SDK compatibility
- Multi-provider auth (API key, Bedrock, Vertex AI, CLI)
- System prompt support, model selection with validation
- Tools disabled by default for speed; opt-in with `enable_tools: true`
- Cost and token tracking
- Session continuity across requests
- Interactive landing page with API explorer

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
poetry run python test_endpoints.py
```

Your OpenAI-compatible Claude Code API is now running on `http://localhost:8000`.

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

The Claude Code CLI is bundled with the SDK. No separate Node.js or npm install needed.

## Installation

```bash
git clone https://github.com/ttlequals0/claude-code-openai-wrapper
cd claude-code-openai-wrapper
poetry install
cp .env.example .env  # Edit with your preferences
```

## Configuration

Edit `.env`:

```env
# Auth (optional - auto-detects if not set)
# CLAUDE_AUTH_METHOD=cli|api_key|bedrock|vertex

# Optional client API key protection
# API_KEY=your-optional-api-key

PORT=8000
MAX_TIMEOUT=600000        # milliseconds
# CLAUDE_CWD=/path/to/workspace  # defaults to isolated temp dir
```

### Working Directory

By default, Claude Code runs in an isolated temporary directory so it can't access the wrapper's own source. Set `CLAUDE_CWD` to point it at a specific project instead.

### API Key Protection

If no `API_KEY` is set, the server prompts on startup whether to generate one. Useful for remote access over VPN or Tailscale.

### Rate Limiting

Per-IP rate limiting is built in. Defaults:

| Endpoint | Limit |
|----------|-------|
| `/v1/chat/completions` | 10/min |
| `/v1/debug/request` | 2/min |
| `/v1/auth/status` | 10/min |
| `/health` | 30/min |

Configure via environment variables: `RATE_LIMIT_ENABLED`, `RATE_LIMIT_CHAT_PER_MINUTE`, etc.

## Running the Server

```bash
# Development (auto-reload)
poetry run uvicorn src.main:app --reload --port 8000

# Production
poetry run python main.py
```

## Docker

```bash
# Build
docker build -t claude-wrapper:latest .

# Run
docker run -d -p 8000:8000 \
  -v ~/.claude:/root/.claude \
  --name claude-wrapper \
  claude-wrapper:latest

# With custom workspace
docker run -d -p 8000:8000 \
  -v ~/.claude:/root/.claude \
  -v /path/to/project:/workspace \
  -e CLAUDE_CWD=/workspace \
  claude-wrapper:latest
```

Docker Compose:

```yaml
version: '3.8'
services:
  claude-wrapper:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ~/.claude:/root/.claude
    environment:
      - PORT=8000
      - MAX_TIMEOUT=600
    restart: unless-stopped
```

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | `8000` |
| `MAX_TIMEOUT` | Request timeout (seconds) | `300` |
| `CLAUDE_CWD` | Working directory | temp dir |
| `CLAUDE_AUTH_METHOD` | `cli`, `api_key`, `bedrock`, `vertex` | auto-detect |
| `ANTHROPIC_API_KEY` | Direct API key | - |

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

Pass Claude SDK options via custom HTTP headers:

| Header | Values | Description |
|--------|--------|-------------|
| `X-Claude-Max-Turns` | integer | Max conversation turns |
| `X-Claude-Allowed-Tools` | comma-separated | Tools to allow |
| `X-Claude-Permission-Mode` | `default`, `acceptEdits`, `bypassPermissions`, `plan` | Permission mode |
| `X-Claude-Effort` | `low`, `medium`, `high`, `max` | Model effort level |
| `X-Claude-Thinking` | `adaptive`, `enabled`, `disabled` | Extended thinking mode |
| `X-Claude-Max-Thinking-Tokens` | integer | Thinking token budget |

## Supported Models

All model IDs, context windows, and pricing sourced from the open-sourced Claude Code CLI.

### Claude 4.6 (Latest)
| Model | Context | Max Output | Input $/MTok | Output $/MTok |
|-------|---------|-----------|-------------|--------------|
| `claude-opus-4-6` | 200K | 128K | $5 | $25 |
| `claude-sonnet-4-6` (default) | 200K | 128K | $3 | $15 |

### Claude 4.5
| Model | Context | Max Output | Input $/MTok | Output $/MTok |
|-------|---------|-----------|-------------|--------------|
| `claude-opus-4-5-20251101` | 200K | 64K | $5 | $25 |
| `claude-sonnet-4-5-20250929` | 200K | 64K | $3 | $15 |
| `claude-haiku-4-5-20251001` | 200K | 64K | $1 | $5 |

### Claude 4.1 / 4.0
| Model | Context | Max Output | Input $/MTok | Output $/MTok |
|-------|---------|-----------|-------------|--------------|
| `claude-opus-4-1-20250805` | 200K | 64K | $15 | $75 |
| `claude-opus-4-20250514` | 200K | 64K | $15 | $75 |
| `claude-sonnet-4-20250514` | 200K | 64K | $3 | $15 |

### Claude 3.x
| Model | Context | Max Output | Input $/MTok | Output $/MTok |
|-------|---------|-----------|-------------|--------------|
| `claude-3-7-sonnet-20250219` | 200K | 64K | $3 | $15 |
| `claude-3-5-sonnet-20241022` | 200K | 8K | $3 | $15 |
| `claude-3-5-haiku-20241022` | 200K | 8K | $0.80 | $4 |

## Session Continuity

Maintain conversation context across requests by including a `session_id`:

```python
# Start a conversation
response1 = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "My name is Alice."}],
    extra_body={"session_id": "my-session"}
)

# Continue it -- Claude remembers the context
response2 = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "What's my name?"}],
    extra_body={"session_id": "my-session"}
)
```

Sessions expire after 1 hour of inactivity. Manage them via:
- `GET /v1/sessions` -- list active sessions
- `GET /v1/sessions/{id}` -- session details
- `DELETE /v1/sessions/{id}` -- delete session
- `GET /v1/sessions/stats` -- session statistics

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
| `/v1/models/refresh` | POST | Refresh models from API |

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
| `/v1/debug/request` | POST | Debug request validation |
| `/health` | GET | Health check |
| `/version` | GET | API version |

## JSON Response Mode

Force JSON output using the OpenAI-compatible `response_format` parameter:

```python
response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "List 3 colors with hex codes"}],
    response_format={"type": "json_object"}
)
```

When `response_format.type` is `json_object`, the wrapper:
- Injects system prompt instructions requiring valid JSON output
- Strips common preambles (e.g. "Here is the JSON:") from responses
- Uses balanced brace/bracket matching to extract JSON from mixed output
- Handles escaped quotes and nested structures correctly

Works with both streaming and non-streaming responses.

## Limitations

- Images in messages are converted to text placeholders
- OpenAI-style function calling not supported (tools auto-execute based on prompts)
- `temperature`, `top_p`, `presence_penalty`, `frequency_penalty` are accepted but not passed to Claude SDK
- Multiple responses (`n > 1`) not supported

## Testing

```bash
# Run the full test suite
poetry run pytest tests/

# Quick endpoint test (server must be running)
poetry run python test_endpoints.py
```

## Terms Compliance

This wrapper requires your own Claude subscription or API access. It translates request formats -- it does not provide Claude access itself.

- Uses the official Claude Agent SDK
- Each user authenticates individually (no credential sharing)
- No reselling, no data harvesting

| Use Case | Recommended Auth |
|----------|-----------------|
| Personal projects | CLI Auth or API Key |
| Business / commercial | API Key, Bedrock, or Vertex AI |
| High-scale | Bedrock or Vertex AI |

See [Anthropic's Terms of Service](https://www.anthropic.com/legal) for details.

## Licence

MIT

## Contributing

Contributions welcome. Open an issue or submit a pull request.
