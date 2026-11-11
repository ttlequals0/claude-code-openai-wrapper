# Claude Code OpenAI API Wrapper

OpenAI API-compatible wrapper for Claude Code. Drop it in front of any OpenAI client library and talk to Claude instead.

## Features

- OpenAI `/v1/chat/completions` and Anthropic `/v1/messages`, both with streaming.
- JSON mode (`response_format` with `json_object` or `json_schema`) and function calling (`tools` and `tool_choice`), simulated on top of Claude Code.
- Sessions: pass a `session_id` to keep a conversation going; list and delete them under `/v1/sessions`.
- `/v1/models` reads Anthropic's live catalogue when an API key is set and falls back to a built-in list otherwise.
- `/v1/usage` reports each Claude subscription window with its utilization and reset time. A 429 carries a `Retry-After` set to the real reset.
- Overloaded Opus requests fall back to Sonnet. Repeated upstream failures open a short-lived circuit breaker instead of piling up.
- Usage is priced per model, and `X-Claude-*` headers set effort, thinking, turns, tools and permission mode per request.
- Auth through Claude CLI login, Anthropic API key, Bedrock or Vertex AI, with an optional API key on the wrapper itself.
- Tools are off by default for speed. Send `enable_tools: true` to turn them on. With tools off, the CLI also skips user and project settings, so plugins and MCP servers in a mounted `~/.claude` are not loaded.

Release notes live in [CHANGELOG.md](./CHANGELOG.md) and on the GitHub releases page.

## Quick start

You need Python 3.10+ and [Poetry](https://python-poetry.org/docs/#installation). The Claude Code CLI comes bundled with the SDK, so Node.js and npm are not needed.

```bash
git clone https://github.com/ttlequals0/claude-code-openai-wrapper
cd claude-code-openai-wrapper
poetry install
cp .env.example .env  # optional

# Authenticate (pick one)
export ANTHROPIC_API_KEY=your-api-key
# or: claude auth login
# or: Bedrock / Vertex AI, see Configuration

# Development server with auto-reload
poetry run uvicorn src.main:app --reload --port 8000

# Production
poetry run claude-wrapper
```

The server listens on `http://localhost:8000`. Point your OpenAI client there.

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
  ttlequals0/claude-code-openai-wrapper:2.14.0

# Or build locally (prod stage is the default target)
docker build --platform linux/amd64 -t claude-wrapper:local .
```

For Docker Compose, use the `docker-compose.yml` in the repo: `docker compose up -d`.

## Configuration

All settings are environment variables. `.env.example` has a starting set.

By default Claude Code runs in an isolated temporary directory, so it cannot read the wrapper's own source. Set `CLAUDE_CWD` to point it at a project.

If `API_KEY` is unset, the server asks at startup whether to generate one. That is useful for remote access over VPN or Tailscale.

### Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | `8000` |
| `CLAUDE_WRAPPER_HOST` | Bind address (`127.0.0.1` for local only) | `0.0.0.0` |
| `MAX_TIMEOUT` | Per-request timeout (ms) | `600000` (10 min) |
| `MAX_REQUEST_SIZE` | Max request body size (bytes) | `10485760` (10 MB) |
| `CLAUDE_CWD` | Working directory Claude Code runs in | isolated temp dir |
| `CLAUDE_AUTH_METHOD` | `cli`, `api_key`, `bedrock`, `vertex` | auto-detect |
| `API_KEY` | Require this key on every request | interactive prompt |
| `CLAUDE_CODE_OAUTH_TOKEN` | Subscription OAuth token, read by the bundled Claude CLI. Alternative to `ANTHROPIC_API_KEY` for `cli` auth. | - |
| `ANTHROPIC_API_KEY` | API key for `api_key` auth. Also enables live `/v1/models` and the latest-Sonnet default. | - |
| `CLAUDE_CODE_USE_BEDROCK` | Enable AWS Bedrock backend | `false` |
| `AWS_REGION` / `AWS_DEFAULT_REGION` / `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Bedrock credentials | - |
| `CLAUDE_CODE_USE_VERTEX` | Enable Google Vertex AI backend | `false` |
| `ANTHROPIC_VERTEX_PROJECT_ID` / `CLOUD_ML_REGION` / `GOOGLE_APPLICATION_CREDENTIALS` | Vertex credentials | - |
| `DEFAULT_MODEL` | Model used when a request names none. Unset: latest Sonnet when `ANTHROPIC_API_KEY` is set, else `claude-sonnet-5-5`. | auto |
| `FAST_MODEL` | Speed and cost optimized model alias | `claude-haiku-5-5` |
| `CLAUDE_MODELS_OVERRIDE` | Comma-separated model IDs for `/v1/models`. Overrides the live and static lists. | - |
| `MODEL_LIST_CACHE_TTL_SECONDS` | Cache TTL for live `/v1/models` results | `3600` |
| `MODEL_LIST_ERROR_TTL_SECONDS` | Cache TTL after a failed live fetch | `60` |
| `MODEL_LIST_REQUEST_TIMEOUT_SECONDS` | HTTP timeout for the live model fetch | `5` |
| `ANTHROPIC_MODELS_URL` | Live models endpoint | `https://api.anthropic.com/v1/models` |
| `ANTHROPIC_VERSION` | `anthropic-version` header sent to the Models API | `2023-06-01` |
| `ANTHROPIC_BETA` / `ANTHROPIC_BETA_HEADER` | Optional `anthropic-beta` header sent to the Models API | - |
| `CLI_AUTH_PROBE_INTERVAL_SECONDS` | Seconds between background CLI auth probes under `cli` auth. Each probe is a real 1-turn query. Only an `auth_failure` result makes requests return 401. `0` disables. | `600` (10 min) |
| `WRAPPER_QUOTA_ENFORCEMENT_ENABLED` | Refuse requests with 429 while a quota window is `rejected` | `false` |
| `WRAPPER_QUOTA_PROBE_EVERY_N_REQUESTS` | Requests between quota refresh probes. A probe is a real 1-turn call that spends quota. `0` relies on live traffic alone. | `100` |
| `WRAPPER_QUOTA_PROBE_MIN_INTERVAL_SECONDS` | Minimum seconds between quota probes | `300` (5 min) |
| `WRAPPER_QUOTA_STALE_AFTER_SECONDS` | Age at which a `/v1/usage` reading is flagged `stale` | `900` (15 min) |
| `DEBUG_MODE` | Debug logging; unlocks `/v1/debug/request` | `false` |
| `VERBOSE` | Also unlocks `/v1/debug/request` | `false` |
| `CORS_ORIGINS` | Allowed CORS origins (JSON array) | `["*"]` |
| `REQUEST_CACHE_ENABLED` | Enable the request-dedup cache | `false` |
| `REQUEST_CACHE_TTL_SECONDS` | Cache entry TTL | `60` seconds |
| `REQUEST_CACHE_MAX_SIZE` | Max cached entries | `100` |
| `WRAPPER_CIRCUIT_BREAKER_ENABLED` | Enable the upstream failure circuit breaker | `true` |
| `WRAPPER_CIRCUIT_BREAKER_WINDOW_SECONDS` | Failure-rate measurement window | `60` seconds |
| `WRAPPER_CIRCUIT_BREAKER_THRESHOLD` | Failure ratio that opens the breaker | `0.75` |
| `WRAPPER_CIRCUIT_BREAKER_MIN_REQUESTS` | Minimum requests before the breaker can open | `20` |
| `WRAPPER_CIRCUIT_BREAKER_OPEN_SECONDS` | Time before the breaker allows a probe request | `30` seconds |
| `WRAPPER_DEFAULT_MAX_TURNS` | Default `max_turns` when tools are off | `3` |
| `WRAPPER_MAP_MAX_TOKENS_TO_THINKING` | Map OpenAI `max_tokens` to Claude `max_thinking_tokens` (legacy) | `false` |
| `WATCHDOG_ENABLED` | Enable the CPU watchdog (for Docker) | `false` |
| `WATCHDOG_CPU_THRESHOLD` / `WATCHDOG_INTERVAL` / `WATCHDOG_STRIKES` | Watchdog tuning | see `src/cpu_watchdog.py` |
| `UVICORN_WORKERS` | Worker count for the prod image. Quota and breaker state is per process, so more than 1 worker splits it. | `1` |
| `RATE_LIMIT_ENABLED` / `RATE_LIMIT_*_PER_MINUTE` | See Rate limiting | - |

### Rate limiting

Per-IP rate limiting is on by default. Set `RATE_LIMIT_ENABLED=false` to turn it off.

| Endpoint group | Default | Env var |
|----------------|---------|---------|
| `/v1/chat/completions`, `/v1/messages` | 120/min | `RATE_LIMIT_CHAT_PER_MINUTE` |
| `/v1/debug/request` | 2/min | `RATE_LIMIT_DEBUG_PER_MINUTE` |
| `/v1/auth/status` | 10/min | `RATE_LIMIT_AUTH_PER_MINUTE` |
| `/v1/sessions/*` | 15/min | `RATE_LIMIT_SESSION_PER_MINUTE` |
| `/health`, `/healthz/deep` | 30/min | `RATE_LIMIT_HEALTH_PER_MINUTE` |
| everything else | 30/min | `RATE_LIMIT_PER_MINUTE` |

## Usage

### curl

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key-if-required" \
  -d '{
    "model": "claude-sonnet-5-5",
    "messages": [{"role": "user", "content": "What is 2 + 2?"}],
    "stream": true
  }'
```

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-api-key-if-required"
)

response = client.chat.completions.create(
    model="claude-sonnet-5-5",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum computing in one paragraph."}
    ]
)
print(response.choices[0].message.content)

# With Claude Code tools enabled
response = client.chat.completions.create(
    model="claude-sonnet-5-5",
    messages=[{"role": "user", "content": "What files are in the current directory?"}],
    extra_body={"enable_tools": True}
)

# Streaming
stream = client.chat.completions.create(
    model="claude-sonnet-5-5",
    messages=[{"role": "user", "content": "Explain quantum computing"}],
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

A system message replaces Claude Code's default system prompt. More examples are in `examples/`.

### Claude-specific headers

| Header | Values | Description |
|--------|--------|-------------|
| `X-Claude-Max-Turns` | integer | Max conversation turns |
| `X-Claude-Allowed-Tools` | comma-separated | Tools to allow |
| `X-Claude-Permission-Mode` | `default`, `acceptEdits`, `bypassPermissions`, `plan` | Permission mode |
| `X-Claude-Effort` | `low`, `medium`, `high`, `xhigh`, `max` | Model effort level |
| `X-Claude-Thinking` | `adaptive`, `enabled`, `disabled` | Extended thinking mode |
| `X-Claude-Max-Thinking-Tokens` | integer | Thinking token budget |
| `X-Enable-Cache` | `true` / `1` / `yes` | Opt in to the response cache for this request |

## Supported models

Model IDs, context windows and pricing come from the Anthropic models docs (`platform.claude.com/docs/en/models/overview`, pricing page) and are mirrored in `src/constants.py`.

With `ANTHROPIC_API_KEY` set, `/v1/models` returns Anthropic's live catalogue (cached for `MODEL_LIST_CACHE_TTL_SECONDS`) and the wrapper picks the latest Sonnet as the default at startup. Without it (Bedrock, Vertex or Claude CLI auth), the static list below is served and `claude-sonnet-5-5` is the default. `CLAUDE_MODELS_OVERRIDE=a,b,c` pins the list regardless of auth.

### Latest
| Model | Context | Max output | Input $/MTok | Output $/MTok |
|-------|---------|-----------|-------------|--------------|
| `claude-fable-5-2` | 1M | 128K | $8 | $40 |
| `claude-opus-5-5` | 1M | 128K | $4 | $20 |
| `claude-sonnet-5-5` (static default) | 1M | 128K | $2 | $10 |
| `claude-haiku-5-5` | 1M | 128K | $0.10 | $0.50 |

Cache reads are 0.1x input except Fable 5.2 (0.025x, $0.20/MTok), Fable 5.1 (0.025x, $0.25/MTok), Opus 5.5 (0.05x, $0.20/MTok) and Sonnet 5.5 (0.05x, $0.10/MTok). Haiku 5.5 prompts over 100K tokens bill at 5x the listed rate ($0.50/$2.50, cache read $0.05, cache write $0.625); the cost tracker uses the base tier.

### Legacy (active, consider migrating)
| Model | Context | Max output | Input $/MTok | Output $/MTok |
|-------|---------|-----------|-------------|--------------|
| `claude-fable-5-1` | 1M | 128K | $10 | $50 |
| `claude-fable-5` | 1M | 128K | $10 | $50 |
| `claude-opus-5` | 1M | 128K | $5 | $25 |
| `claude-opus-4-8` | 1M | 128K | $5 | $25 |
| `claude-opus-4-7` | 1M | 128K | $5 | $25 |
| `claude-opus-4-6` | 1M | 128K | $5 | $25 |
| `claude-sonnet-5` | 1M | 128K | $2 | $10 |
| `claude-sonnet-4-6` | 1M | 64K | $3 | $15 |
| `claude-opus-4-5-20251101` | 200K | 64K | $5 | $25 |
| `claude-sonnet-4-5-20250929` | 200K | 64K | $3 | $15 |
| `claude-haiku-4-5-20251001` | 200K | 64K | $1 | $5 |

Claude 3.x models are not supported by the Claude Agent SDK. `claude-opus-4-1-20250805`, `claude-sonnet-4-20250514` and `claude-opus-4-20250514` are no longer served by the Anthropic Models API and are not in this list.

## Sessions

Pass a `session_id` to keep conversation context across requests:

```python
response1 = client.chat.completions.create(
    model="claude-sonnet-5-5",
    messages=[{"role": "user", "content": "My name is Alice."}],
    extra_body={"session_id": "my-session"}
)

response2 = client.chat.completions.create(
    model="claude-sonnet-5-5",
    messages=[{"role": "user", "content": "What's my name?"}],
    extra_body={"session_id": "my-session"}
)
```

Sessions expire after 1 hour of inactivity. See `examples/session_continuity.py` and `examples/session_curl_example.sh`.

## API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Landing page with API documentation |
| `/v1/chat/completions` | POST | OpenAI-compatible chat |
| `/v1/messages` | POST | Anthropic-compatible messages |
| `/v1/models` | GET | List available models |
| `/v1/models/status` | GET | Model service status |
| `/v1/models/refresh` | POST | Refresh model catalogue |
| `/v1/sessions` | GET | List active sessions |
| `/v1/sessions/stats` | GET | Session statistics |
| `/v1/sessions/{id}` | GET | Get session by ID |
| `/v1/sessions/{id}` | DELETE | Delete session |
| `/v1/tools` | GET | List available tools |
| `/v1/tools/config` | GET | Get tool configuration |
| `/v1/tools/config` | POST | Update tool configuration |
| `/v1/tools/stats` | GET | Tool usage statistics |
| `/v1/mcp/servers` | GET | List MCP servers |
| `/v1/mcp/servers` | POST | Register MCP server |
| `/v1/mcp/connect` | POST | Connect to MCP server |
| `/v1/mcp/disconnect` | POST | Disconnect MCP server |
| `/v1/mcp/stats` | GET | MCP statistics |
| `/v1/cache/stats` | GET | Cache statistics |
| `/v1/cache/clear` | POST | Clear request cache |
| `/v1/auth/status` | GET | Auth status, including `cli_health` and a `quota` summary |
| `/v1/usage` | GET | Subscription quota per rate-limit window |
| `/v1/compatibility` | POST | Parameter compatibility check |
| `/v1/debug/request` | POST | Request debugging; returns only `{"enabled": false}` unless `DEBUG_MODE` or `VERBOSE` is set |
| `/health` | GET | Liveness probe (no upstream call) |
| `/healthz/deep` | GET | Readiness probe (performs an SDK round-trip) |
| `/version` | GET | Wrapper version |

## Function calling

Pass OpenAI-format tool definitions. The wrapper injects them into Claude's system prompt and parses the response back into `tool_calls`. Streamed tool calls carry an `index` and the stream ends with `finish_reason: "tool_calls"`.

```python
response = client.chat.completions.create(
    model="claude-sonnet-5-5",
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

if response.choices[0].finish_reason == "tool_calls":
    for tc in response.choices[0].message.tool_calls:
        print(f"Call: {tc.function.name}({tc.function.arguments})")
```

`tool_choice` accepts `"auto"` (default), `"required"`, `"none"` or `{"type": "function", "function": {"name": "..."}}`.

For multi-turn tool conversations, pass the assistant messages with `tool_calls` and the `tool` role results back. The wrapper converts them to text for Claude.

## JSON response mode

Set `response_format` to get JSON back:

```python
response = client.chat.completions.create(
    model="claude-sonnet-5-5",
    messages=[{"role": "user", "content": "List 3 colors with hex codes"}],
    response_format={"type": "json_object"}
)
```

The wrapper adds JSON instructions to the system prompt, strips preambles like "Here is the JSON:" and falls back to brace-matching extraction. It works streaming and non-streaming. A schema is accepted via `response_format={"type": "json_schema", "json_schema": {...}}`.

In either JSON mode the wrapper moves your system prompt to the front of the user turn. It is a move, so your token count does not change. Plain text requests are not affected.

## Quota and rate limits

`GET /v1/usage` reports what the Claude CLI last said about your subscription quota. Windows appear only once the CLI has reported them, so a wrapper that has served no traffic returns an empty set.

```json
{
  "blocked": false,
  "blocked_until": null,
  "blocked_until_iso": null,
  "seconds_until_reset": null,
  "binding_window": "five_hour",
  "closest_to_limit": {
    "window": "seven_day",
    "utilization": 0.05,
    "resets_at": 1788732000,
    "resets_at_iso": "2026-09-06T22:00:00+00:00",
    "seconds_until_reset": 599454
  },
  "windows": {
    "five_hour": {
      "status": "allowed",
      "utilization": 0.29,
      "resets_at": 1788145200,
      "resets_at_iso": "2026-08-31T03:00:00+00:00",
      "seconds_until_reset": 12654,
      "representative": true,
      "observed_at": "2026-08-30T23:29:05.694090+00:00",
      "source": "passive",
      "stale": false
    },
    "seven_day": {
      "status": null,
      "utilization": 0.05,
      "resets_at": 1788732000,
      "resets_at_iso": "2026-09-06T22:00:00+00:00",
      "seconds_until_reset": 599454,
      "representative": false,
      "observed_at": "2026-08-30T23:29:05.694090+00:00",
      "source": "passive",
      "stale": false
    }
  },
  "observed_windows": 2
}
```

- `closest_to_limit` names the window nearest its cap. That is the one that will cut you off, and it is not always `binding_window`, so check it first.
- Window keys are `five_hour`, `seven_day`, `seven_day_opus`, `seven_day_sonnet` and `overage`.
- `status` is `allowed`, `allowed_warning` (close to the limit) or `rejected`. It is set only on the window flagged `representative`, because the CLI reports one status per event.
- `source` is `passive` for a reading from live traffic and `probe` for one from a refresh probe.
- `stale` marks a reading older than `WRAPPER_QUOTA_STALE_AFTER_SECONDS`.
- A `rejected` window stops reporting as rejected once its reset time has passed. When the CLI named no reset time, it expires `WRAPPER_QUOTA_STALE_AFTER_SECONDS` after it was observed.
- A `rejected` overage pool usually means pay-as-you-go is switched off. Check `disabled_reason` (for example `org_level_disabled`) before treating it as a quota problem.

The data comes from the SDK's `RateLimitEvent`, which the CLI emits whenever rate-limit state changes. State is per process, so with `UVICORN_WORKERS` above 1 each worker reports only what its own traffic showed it.

When the upstream rejects a request for quota, the wrapper returns 429 with a `Retry-After` derived from the real reset time and capped at 3600 seconds. The exact reset is in the body:

```json
{"error": {"type": "rate_limit_exceeded", "code": "upstream_quota_exhausted",
           "resets_at": 1788135731, "seconds_until_reset": 1799}}
```

Set `WRAPPER_QUOTA_ENFORCEMENT_ENABLED=true` to refuse requests before the round-trip while a window is rejected.

## Limitations

- Image parts in messages are dropped; only text reaches Claude.
- `temperature` and `top_p` are applied through system-prompt instructions, which is a best-effort approximation.
- `presence_penalty` and `frequency_penalty` are accepted but ignored.
- `max_tokens` is ignored unless `WRAPPER_MAP_MAX_TOKENS_TO_THINKING=true`.
- Multiple responses (`n > 1`) are not supported.

## Testing

```bash
# Full test suite
poetry run pytest tests/

# Endpoint test against a running server
poetry run python tests/test_endpoints.py
```

## Terms

You need your own Claude subscription or API access. This wrapper translates request formats and does not provide Claude access.

| Use case | Recommended auth |
|----------|------------------|
| Personal projects | CLI auth or API key |
| Business / commercial | API key, Bedrock or Vertex AI |
| High-scale | Bedrock or Vertex AI |

See [Anthropic's Terms of Service](https://www.anthropic.com/legal).

## License

MIT

## Contributing

PRs welcome.
