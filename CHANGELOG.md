# Changelog

All notable changes to the Claude Code OpenAI Wrapper project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.14.0] - 2026-11-10

### Added

- `claude-fable-5-2` (Fable 5.2): 1M context, 128K max output, $8/$40 per
  MTok, cache read $0.20, cache write $10. It leads the static model list;
  Fable 5.1 moves to Legacy in the README.
- `xhigh` is accepted as an effort level (`X-Claude-Effort`).

### Fixed

- A client's system message now reaches the model. `run_completion` passed
  it as a `{"type": "text"}` dict, a shape the Agent SDK turns into no CLI
  flag, so every request ran on Claude Code's default prompt instead. It is
  now passed as a plain string and replaces that prompt. Requests without a
  system message still use the `claude_code` preset. Reported upstream as
  RichardAtCT#54; fix ported from the eddikh-ai fork.
- Streamed tool calls are valid for OpenAI clients: each delta carries an
  `index` and the stream ends with `finish_reason: "tool_calls"`.
- Tool calls Claude writes in its native `<invoke>` markup are parsed into
  `tool_calls` when they name a function the client defined. This and the
  streaming fix are ported from the eddikh-ai fork.
- With tools disabled, the CLI now starts with no built-in tools
  (`--tools ""`) and loads no user or project settings
  (`--setting-sources=`). The denylist alone missed tools added by newer
  CLI releases, and the settings in a mounted `~/.claude` (plugins, MCP
  tool definitions, memory files) were sent with every request. Measured
  on a development machine with Haiku 5.5: 107,079 input tokens and
  $0.0156 per one-word reply before, 572 tokens and $0.0002 after.
  Requests with `enable_tools=true` still load settings. Based on the
  eddikh-ai fork.

### Changed

- `claude-agent-sdk` pinned to 0.2.180 (bundled Claude CLI 2.1.321). Folds
  the automated bump PRs #63 and #64.
- The `completion_result` log line reports `failed=False` instead of
  `is_error=False`, so log pipelines that match on "error" stop tagging
  successful completions as errors.
- Docs audited against the code. README: the setup sections are merged,
  the copy of `docker-compose.yml` is gone, examples use
  `claude-sonnet-5-5`, and the Limitations list is corrected. The claim
  that the SDK ignores instructions in the system prompt slot is removed:
  with the system message fix above, a six-key JSON contract in the system
  slot came back correct on 9 of 9 runs (Haiku 5.5, Sonnet 5, Opus 5.5).
  `examples/` no longer use the retired `claude-3-5-sonnet-20241022`. Older
  entries in this file are shortened.

### Security

- `authlib` floor raised to 1.9.1 (locked 1.9.5) for eight advisories,
  including GHSA-6v38-4h7w-rj9h (empty JWS signatures accepted, critical)
  and GHSA-8m4g-j4wp-wgcg (empty HMAC key allows JWT forgery, high).
- `opentelemetry-api` floor 1.45.1 (locked 1.45.2) for GHSA-xcq7-p3pf-p88h
  and dev-only `black` 26.10.1 for GHSA-cg8m-r9f2-5wm2. Covers Dependabot
  #62.
- `joserfc` floor raised to 1.7.6 (locked 1.7.7 or 1.8.0 by Python
  version) for CVE-2026-119283 and CVE-2026-119284, found by pip-audit.

## [2.13.2] - 2026-10-27

### Fixed

- Chat messages from agentic clients no longer fail with 422. Content arrays
  may carry `tool_use`, `tool_result` and image parts next to text; the
  non-text parts are accepted and skipped, and the text inside a
  `tool_result` is kept. Ported from #41.

### Changed

- `claude-agent-sdk` pinned to 0.2.174 (bundled Claude CLI 2.1.310; parallel
  tool calls no longer go missing from session messages). Folds the automated
  bump PRs #57, #58 and #60.

### Security

- `mcp` raised to 1.30.0 for GHSA-84m7-p3x7-pcfv (unbounded session
  accumulation in the StreamableHTTP transport). `anyio`, `certifi`, `pyjwt`
  and `urllib3` moved to their current releases in the same lock refresh,
  which also covers Dependabot #59.

## [2.13.1] - 2026-10-10

### Fixed

- An exhausted account quota reached callers as a plain 429 while
  `/v1/usage` kept reporting `blocked=false`. The CLI's literal
  `error='rate_limit'` path never parsed a reset time or recorded the
  rejection. The reset hour named in the message ("resets 6pm (UTC)") is now
  parsed and recorded there too.
- A rejection recorded with no reset time read as blocked forever in
  `/v1/usage` and the enforcement gate. It now expires
  `WRAPPER_QUOTA_STALE_AFTER_SECONDS` after it was observed. A rejection
  whose reset time has passed also stops reporting as `rejected`; on the
  representative window it reports `status: null`.
- The reset-hour parser accepted any parenthesised timezone name as UTC. It
  now trusts only `(UTC)`, `(GMT)`, `(Etc/UTC)` or no timezone; any other
  zone falls back to no reset. A reset named a few seconds in the past
  (clock skew) no longer rolls to tomorrow; that now needs more than a
  minute.
- A rejection with no parsed reset time was recorded under `five_hour`
  whatever the text said, so a bare 429 could mark the window rejected. The
  text must now name an account limit ("session limit", "usage limit",
  "weekly limit", "limit reached").
- Recording a rejection from error text wiped the window's last known
  utilization and could leave two windows flagged `representative`. It now
  carries the utilization forward and clears `representative` on every
  other window.
- An exhausted account quota (`assistant_rate_limit`) counted as a circuit
  breaker failure, so a burst of rejections could trip the breaker and fail
  healthy traffic. Account limits are no longer recorded to the breaker.

### Changed

- README: the per-version highlights list is replaced by a short Features
  section.
- The session-limit rejection is recorded under the `five_hour` window
  instead of a separate `session_limit` window type.
- `RATE_LIMIT_CHAT_PER_MINUTE` default raised from 10 to 120 per minute. The
  old default rejected ordinary traffic before the account quota became
  binding.
- `UVICORN_WORKERS` default lowered from 2 to 1 for the prod image. The quota
  tracker and circuit breaker are in-process state, which more than one
  worker splits. Request handling is async around the SDK subprocess, so one
  worker still serves concurrent requests.

## [2.13.0] - 2026-10-08

### Added

- `claude-sonnet-5-5` (Sonnet 5.5): 1M context, 128K max output, effort
  low..max, adaptive thinking only (`disabled` not supported). $2/$10 per
  MTok, cache read $0.10 (0.05x input), cache write $2.50.
- `claude-haiku-5-5` (Haiku 5.5): 1M context, 128K max output, effort
  low..max, adaptive thinking (no `enabled`/budget_tokens). Pricing is tiered
  by prompt size: up to 100K tokens $0.10/$0.50 per MTok, cache read $0.01,
  cache write $0.125; over 100K tokens 5x that ($0.50/$2.50, cache read
  $0.05, cache write $0.625). The cost tracker uses the base tier.

### Changed

- `FAST_MODEL` default moves from `claude-haiku-4-5-20251001` to
  `claude-haiku-5-5`.
- `claude-opus-5-5` overload fallback moves from `claude-sonnet-5` to
  `claude-sonnet-5-5`.
- `DEFAULT_MODEL_FALLBACK` moves from `claude-sonnet-5` to
  `claude-sonnet-5-5`.

### Removed

- `claude-opus-4-1-20250805`, `claude-sonnet-4-20250514` and
  `claude-opus-4-20250514` are no longer served by the Anthropic Models API
  (absent from `GET /v1/models` as of 2026-10-08) and are dropped from the
  static catalogue, metadata, pricing and fallback tables.

## [2.12.1] - 2026-09-30

### Fixed

- Update `claude-agent-sdk` to 0.2.162, which bundles Claude Code 2.1.285. The
  previous bundled CLI could not serve `claude-opus-5-5`, which requires
  Claude Code 2.1.280 or newer.
- Return a specific upgrade-required error for incompatible bundled CLI
  versions, and recognize expired CLI authentication in SDK result messages.
  These responses do not expose raw SDK result text.
- Correct documented runtime defaults and remove stale test counts and example
  image versions.
- Verify the bundled CLI version during the image build and record it in
  `BUILD_INFO`. Missing, incompatible or non-executable CLI binaries now fail
  the build.

### Security

- Exclude local agent instructions, logs and build artifacts from the image
  context.
- Raise the PyJWT minimum to 2.14.0 and lock 2.15.1 to fix the JWT validation
  advisories found by the release dependency scan.

## [2.12.0] - 2026-09-22

### Added

- `claude-opus-5-5` (Opus 5.5): 1M context, 128K max output, $4/$20 per MTok,
  cache read $0.20 (0.05x input). Overload fallback is `claude-sonnet-5`.
- `claude-fable-5-1` (Fable 5.1): 1M context, 128K max output, $10/$50 per
  MTok, cache read $0.25 (0.025x input).

### Changed

- Bump `claude-agent-sdk` 0.2.152 to 0.2.157 (supersedes #49). `RateLimitInfo`
  field names unchanged.
- Sonnet 5 cost tracking now uses $2/$10 per MTok. Anthropic made the launch
  price standard and cancelled the move to $3/$15.
- README model tables: Fable 5, Opus 5, Opus 4.8 and Opus 4.7 moved to Legacy.
  Opus 4.1, Opus 4 and Sonnet 4 are listed as retired on the Claude API.
- Documented `CLAUDE_CODE_OAUTH_TOKEN` in the README env table. Removed the
  unused `CLAUDE_CLI_PATH` from `.env.example`.

### Security

- Remove the dev-only `safety` package. It was not run anywhere (CI uses
  pip-audit) and was the only thing pulling in `nltk`, which has no fix for
  CVE-2026-81726 (GHSA-8mgp-746c-j5xp, Dependabot #35). nltk is now out of
  `poetry.lock`.

## [2.11.0] - 2026-09-20

### Changed

- Bump `claude-agent-sdk` 0.2.148 to 0.2.152 (supersedes #45).

### Security

- Drop the runtime `nltk` pin. nltk is only required by the dev-only `safety`
  tool, and CVE-2026-81726 (GHSA-8mgp-746c-j5xp, path traversal in
  model-artifact APIs) has no patched release. nltk no longer ships in the
  `--only main` production image.

## [2.10.3] - 2026-09-20

### Security

- Bump `anyio` to >=4.14.2 (locked 4.15.1), closing GHSA-82r6-8w77-94w6
  (TLSStream IDNA 2003 host-name encoding enabling TLS certificate spoofing,
  critical) and GHSA-5p39-cfhj-2xmp (process-pool workers blocking on
  undrained stderr, medium). Pinned directly because it is a transitive
  dependency that Dependabot cannot bump otherwise.

## [2.10.2] - 2026-08-31

### Fixed

- An exhausted subscription quota answered 502 instead of 429, after holding
  the caller's connection open for minutes. Observed 2026-08-31: the CLI
  exits 1 with "You've hit your session limit - resets 6pm (UTC)" after
  emitting `ResultMessage(subtype='success', is_error=True)`. The retry loop
  retried it inline (10 attempts, 60s waits, per request), then mapped the
  unrecognized error to
  `502 {"message": "SDK returned success", "type": "upstream_sdk_error"}`
  with no reset time in the response. Three changes close that path:
  - Quota rejections fail fast. A query error carrying HTTP 429 or
    quota-shaped prose is never retried inline.
  - Error results whose prose describes an exhausted quota (session limit,
    usage limit, rate limit) classify as `assistant_rate_limit`, which the
    HTTP layer maps to 429 with `Retry-After` and reset fields in the body.
  - The reset hour the CLI names is parsed into an epoch, used for
    `Retry-After`, and recorded into the quota tracker so `/v1/usage` and
    the enforcement gate know about a rejection no `RateLimitEvent` reported.
- The "session limit" wording was missing from the quota text markers, so
  the auth probe classified it only through the HTTP status. The marker list
  is now shared between the probe classifier and the completion error path.
- A 502 for an error result with no detail no longer claims
  "SDK returned success"; it reads
  "SDK returned an error result (subtype=...)".

## [2.10.1] - 2026-08-30

### Fixed

- `/v1/usage` reported no `seven_day` window and a null `utilization` for
  every window. `RateLimitInfo` exposes the representative window plus the
  overage pool, but the CLI sends every window under
  `raw["unifiedWindows"]`, and that is the only place utilization appears.
  Observed payload from production:

  ```json
  {"status": "allowed", "rateLimitType": "five_hour", "resetsAt": 1788145200,
   "overageStatus": "rejected", "overageDisabledReason": "org_level_disabled",
   "unifiedWindows": {"five_hour": {"utilization": 0.29, "resetsAt": 1788145200},
                      "seven_day": {"utilization": 0.05, "resetsAt": 1788732000}}}
  ```

  The 2026-08-30 outage ran 13h26m, longer than a five-hour window can
  account for, so the weekly cap is the likely cause and `seven_day` was the
  window not being reported.

  Every window in `unifiedWindows` is now recorded with its own utilization
  and reset time. `status` is set only on the window the CLI names as
  representative, since the payload carries no per-window status. Each
  window gains a `representative` flag.
- A rejected overage pool looked like a quota problem. `overage` now carries
  `disabled_reason`, so `org_level_disabled` shows as configuration.

### Added

- `closest_to_limit` in the `/v1/usage` payload names the window nearest its
  cap with its utilization and reset time. That is not always the window the
  CLI names.
- `binding_window` names the window the CLI reported as representative.

## [2.10.0] - 2026-08-30

### Fixed

- A Claude subscription usage limit was reported to every caller as HTTP 401
  `authentication_error`. On 2026-08-30 this held for 13h26m (08:35:45 to
  22:02:12 UTC), during which no request succeeded while CLI authentication
  was healthy. A downstream consumer treated the 401 as non-retryable,
  opened its own circuit breaker and dropped work instead of deferring it.

  The chain: the CLI emitted a result frame with `is_error: true`, an empty
  `errors[]` and `subtype: "success"`, then exited non-zero. `verify_cli()`
  caught the exception and returned a bare `False`. `probe_cli_auth` marked
  `cli_health` failed with `kind=unknown`. `_check_cli_auth_or_401` gated on
  `cli_health.ok` alone and ignored `error_kind`, so every request got a 401.

  The gate now fires only on `error_kind == "auth_failure"`. Every other
  failure kind falls through to the SDK, which reports an accurate status.

  `verify_cli()` propagates SDK exceptions instead of collapsing them to
  `False`, and drains the message stream instead of breaking at the first
  assistant turn. That break tested `getattr(message, "type")`, which no SDK
  dataclass has, so it never fired.

  Classification now prefers `ResultError.api_error_status` (429 ->
  `quota_exhausted`, 401/403 -> `auth_failure`) over string matching, falling
  back to text markers with quota checked before auth.
- `Retry-After` on a 429 was hardcoded to `"30"`. The upstream reset now
  flows through, capped at 3600s because a rejected `seven_day` window can
  reset days out. The true reset is in the body as `resets_at`,
  `resets_at_iso` and `seconds_until_reset`.
- `/v1/messages` raised `HTTPException(502)` for every subtype except
  `error_max_turns`, so a rate limit reached the Anthropic SDK as a broken
  upstream. It now returns 429 with an Anthropic-shaped `rate_limit_error`.
- The streaming SSE error frame was a generic `upstream_sdk_error` whatever
  the subtype. Rate limits now carry the reset time in the body.
- `parse_claude_message` matched a flat `{status, resets_at,
  rate_limit_type}` dict for rate-limit events. The SDK nests those under
  `rate_limit_info`, so the branch was unreachable. Rewritten against the
  real shape.
- `retry_delay` never received the `retry_after` argument `calculate_delay`
  already accepted. Wired through and bounded at 60s, since it runs inside a
  live request.

### Added

- `GET /v1/usage` reports the Claude subscription quota per rate-limit window
  (`five_hour`, `seven_day`, `seven_day_opus`, `seven_day_sonnet`, `overage`):
  status, utilization, `resets_at` as unix and ISO, `seconds_until_reset`,
  whether the reading came from live traffic or a probe, and whether it has
  gone stale. Windows appear only once the CLI has reported them.
  `/v1/auth/status` gains a matching `quota` block.

  The data comes from the SDK's `RateLimitEvent`, which the CLI emits in-band
  whenever rate-limit state changes, so no proxy in front of the API is
  needed. State is per-process: with `UVICORN_WORKERS > 1` each worker learns
  only from the traffic it serves.
- Opt-in 429 enforcement via `WRAPPER_QUOTA_ENFORCEMENT_ENABLED` (default
  `false`). When on, a request is refused before the round-trip while a
  window is `rejected`. Off by default because refusing is a behaviour change
  for existing callers.
- Quota refresh probes, triggered by request volume:
  `WRAPPER_QUOTA_PROBE_EVERY_N_REQUESTS` (default 100) with a
  `WRAPPER_QUOTA_PROBE_MIN_INTERVAL_SECONDS` floor (default 300); `0` disables.
  The bundled CLI has no `usage` subcommand, so a probe is a real inference
  call that spends the quota it measures. The probe reuses `probe_cli_auth`,
  so one call refreshes both auth and quota state.
- `CLAUDE_CODE_OAUTH_TOKEN` passed through `docker-compose.yml`, so
  subscription users authenticating with `claude auth` no longer need an API
  key. Ported from RichardAtCT/claude-code-openai-wrapper#50 by safrano9999.

### Changed

- `claude-agent-sdk` 0.2.128 -> 0.2.148. `ResultError` (a `ProcessError`
  subclass) now carries structured `subtype`, `errors`, `result`,
  `api_error_status` and `terminal_reason`, so a failed run can be classified
  without string matching. `_error_result_text` prefers `errors[]` ->
  `result` -> non-success `subtype` -> HTTP status, which fixes the "Claude
  Code returned an error result: success" text this outage produced.
  `RateLimitInfo` field names are unchanged across the range.
- `cryptography` floor raised to `>=50.0.0` for GHSA-g6cj-pr64-35w5
  (Dependabot #29, high), superseding the `>=48.0.1` floor.
- pip removed from the runtime image: the app virtualenv, system
  site-packages, Poetry's own installer venv and the virtualenv wheel cache.
  pip vendors its own `msgpack` and `setuptools`, which had tripped the trivy
  HIGH/CRITICAL gate on every build since 2.9.13. Trivy on the 2.10.0 image
  reports 28 HIGH/CRITICAL, all Debian 13 base-image CVEs with no fix
  available, and zero language-package findings; 2.9.14 reported 31
  including the pip-vendored pair.
- `~/.claude` volume mount carries the `:Z` SELinux label, fixing permission
  denied on SELinux-enforcing hosts and rootless Podman. Ported from
  RichardAtCT/claude-code-openai-wrapper#49 by safrano9999.
- README version block corrected: it had been left at 2.9.12 through the
  2.9.13 and 2.9.14 releases.

## [2.9.14] - 2026-08-03

Supersedes the interim `2.9.13` image, which was built from this branch
before the formatting fix and the SDK bump below. No `2.9.13` release
reached `main`, so the version is retired.

### Fixed

- A caller's system prompt was ignored when it carried an output contract.
  A contract asking for six named keys came back with four differently named
  ones on 5 of 5 runs. The same text moved into the user turn returned the
  requested shape on 15 of 15 runs. In JSON mode (`json_object` and
  `json_schema`) the wrapper now relocates the caller's system prompt to the
  head of the user turn and keeps the JSON formatting rules in the system
  slot. The text moves, so token count is unchanged. Plain text requests are
  untouched.

  This entry blamed the Agent SDK for treating the system slot as a persona.
  The cause, found in 2.14.0, was that the wrapper never passed the system
  prompt to the CLI at all.
- Multiple system messages in one request no longer collapse to the last one.
  They are now joined with a blank line, matching OpenAI's behaviour.

### Changed

- `test_multiple_system_messages_uses_last` becomes
  `test_multiple_system_messages_are_joined`.
- Bumped `claude-agent-sdk` from `0.2.127` to `0.2.128`, rolling in Dependabot
  PR #36. Transitive updates include `pydantic` 2.11.7 -> 2.13.4 and
  `typing-extensions` 4.14.0 -> 4.16.0.
- Reformatted `src/main.py`, `src/message_adapter.py` and
  `tests/test_message_adapter_unit.py` with `black`. The CI style gate was
  failing on all three Python versions.

## [2.9.12] - 2026-07-24

### Added

- `claude-opus-5` (Claude Opus 5): 1M context, 64K default / 128K max output,
  $5/$25 per MTok, overload fallback to `claude-sonnet-5`.

### Changed

- Bumped `claude-agent-sdk` from `0.2.110` to `0.2.127`.
- Raised the `mcp` floor from `>=1.23.0` to `>=1.28.1` to close three high
  Dependabot alerts: #26 `GHSA-hvrp-rf83-w775` (experimental task handlers
  allow any client to access and cancel other clients' tasks), #27
  `GHSA-jpw9-pfvf-9f58` (HTTP transports serve session requests without
  verifying the authenticated principal) and #28 `GHSA-vj7q-gjh5-988w`
  (WebSocket server transport lacks Host/Origin validation).
- Raised the `nltk` floor from `>=3.9.3` to `>=3.10.0` to close Dependabot
  #24 `GHSA-p4gq-832x-fm9v` (URL-encoded path traversal in `nltk.data.load`,
  high).

### Security

- `/healthz/deep` no longer returns exception messages in its JSON payload
  (CodeQL alert #11, `py/stack-trace-exposure`). The message is still logged
  server-side; clients see only the exception class name.

## [2.9.11] - 2026-07-01

### Added

- `claude-sonnet-5` (Claude Sonnet 5, GA 2026-06-09): 1M context, 64K default
  / 128K max output. Priced at the `$3/$15` Sonnet tier; the introductory
  `$2/$10` per MTok that applies through 2026-08-31 is not encoded.
- `claude-fable-5` (Claude Fable 5, GA 2026-06-09): 1M context, 64K default /
  128K max output, `$10/$50` per MTok; cache read and write derived from the
  same ratios as the other tiers. `claude-mythos-5` is excluded (Project
  Glasswing limited availability only).

### Changed

- Bumped `claude-agent-sdk` from `0.2.93` to `0.2.110`.
- `DEFAULT_MODEL_FALLBACK` changed from `claude-sonnet-4-6` to
  `claude-sonnet-5`.
- Raised the `cryptography` floor from `>=46.0.5` to `>=48.0.1` to close
  `GHSA-537c-gmf6-5ccf` (high, vulnerable OpenSSL bundled in cryptography
  wheels). Dependabot alert #23.
- Raised the `pyjwt` floor from `>=2.12.0` to `>=2.13.0` to close five alerts
  (#14-18), including `GHSA-xgmm-8j9v-c9wx` (high): a public-key JWK accepted
  as an HMAC secret enables forged HS256 tokens.
- Raised the `python-multipart` floor from `^0.0.27` to `>=0.0.31` to close
  four alerts (#19-22), including `GHSA-5rvq-cxj2-64vf` (high):
  quadratic-time semicolon querystring parsing.
- Added a `joserfc` floor of `>=1.6.7` to close `GHSA-wphv-vfrh-23q5`
  (medium): `b64=false` RFC7797 JWS payloads bypass payload-size limits.
  Transitive via `authlib`. Dependabot alert #25.

### Security

- 11 of 12 open Dependabot alerts are resolved by the floor raises above.
  Alert #24 (`GHSA-p4gq-832x-fm9v`, nltk path traversal in
  `nltk.data.load()`, high) has no upstream fix as of this release (affected
  `<= 3.9.4`, the latest published version) and is accepted as a known risk.

## [2.9.10] - 2026-06-14

### Changed

- Bumped `claude-agent-sdk` from `0.2.87` to `0.2.93`, from the workflow's
  draft PR #25.
- Raised the `starlette` floor from `>=0.49.1` to `>=1.0.1` to close
  `GHSA-86qp-5c8j-p5mr` (medium): missing Host-header validation poisons
  `request.url.path`. Dependabot alert #13. Resolves to `starlette 1.3.1`.
- Raised the `fastapi` floor from `>=0.119.0` to `>=0.133.1` (range stays
  `<1.0`). fastapi `<=0.132.x` caps `starlette` at `<1.0.0`. Resolves to
  `fastapi 0.137.0`.

## [2.9.9] - 2026-05-28

### Added

- `claude-opus-4-8`: 1M context, 64K default / 128K max output, $5/$25 per
  MTok, falls back to `claude-sonnet-4-6` on overload. `claude-opus-4-7`
  remains supported.

### Changed

- README `claude-opus-4-20250514` deprecation row now points at
  `claude-opus-4-8` as the replacement.

## [2.9.8] - 2026-05-24

### Changed

- Bumped `claude-agent-sdk` from `0.2.82` to `0.2.87`. All five releases only
  update the bundled Claude CLI, from `2.1.145` to `2.1.150`.

### Security

- Bumped `idna` from `3.10` to `3.15` for CVE-2026-45409 (oversize-input
  quadratic-time bypass of the CVE-2024-3651 mitigation, fixed in 3.14) plus
  the `check_label` DNS-length cap added in 3.15.

## [2.9.7] - 2026-05-12

### Added

- CLI auth health probe. When `CLAUDE_AUTH_METHOD=claude_cli`, a background
  task periodically runs `claude_cli.verify_cli()` (a 1-turn query) and
  updates a shared `cli_health` state. The interval is
  `CLI_AUTH_PROBE_INTERVAL_SECONDS` (default 600s; `0` disables). It is
  skipped for API key, Bedrock and Vertex auth. Results are at
  `GET /v1/auth/status` under `cli_health`: `ok`, `last_probed_at`,
  `last_ok_at`, `error_kind` (`auth_failure`, `unknown` or `null`) and
  `error_message`.

### Changed

- `POST /v1/chat/completions` and `POST /v1/messages` return HTTP 401 with
  `error.type=authentication_error` and
  `error.code=claude_cli_not_authenticated` when the latest CLI probe failed,
  instead of a generic 502 or 503.
- `_build_sdk_error_response` scans `error_message` and `stderr_tail` for the
  CLI auth failure markers the probe uses (`not logged in`,
  `please run /login`, `invalid api key`, `authentication_error`, `401`). On
  a match the response is 401 and `cli_health` is marked failed.
- Auth-failure responses return `JSONResponse` directly, bypassing the global
  `http_exception_handler`, which rewrote the body as `error.type=api_error`.

## [2.9.6] - 2026-05-11

### Changed

- `claude-agent-sdk`: 0.1.68 -> 0.1.81.
- Synced upstream `RichardAtCT/claude-code-openai-wrapper#46`: dynamic
  Anthropic Models API integration for `/v1/models`. With `ANTHROPIC_API_KEY`
  set the endpoint returns Anthropic's live model list (cached
  `MODEL_LIST_CACHE_TTL_SECONDS`, default 3600s) and the wrapper resolves the
  latest Sonnet as `DEFAULT_MODEL` at startup. Without the key the static
  catalog is served and `DEFAULT_MODEL_FALLBACK=claude-sonnet-4-6` is used.
  `CLAUDE_MODELS_OVERRIDE` pins the advertised list regardless of auth.
  Failed fetches use `MODEL_LIST_ERROR_TTL_SECONDS` (default 60s).

### Security

- `python-multipart`: ^0.0.26 -> ^0.0.27 (closes Dependabot alert #8,
  `GHSA-pp6c-gr5w-3c5g`, denial of service via unbounded multipart part
  headers). Supersedes Dependabot PR #16.
- `urllib3` floor: >=2.6.3 -> >=2.7.0 (closes Dependabot alerts #9
  `GHSA-mf9v-mfxr-j63j` decompression-bomb safeguard bypass and #10
  `GHSA-qccp-gfcp-xxvc` proxy redirect header leak).

### CI

- `check-sdk-version.yml`: when the pin is behind PyPI the workflow opens a
  draft `chore/sdk-bump-<latest>` PR with the pin bump and regenerated
  `poetry.lock`. A reviewer bumps the project version, adds a CHANGELOG entry
  and merges. Permissions widened to `contents: write` and
  `pull-requests: write`.

## [2.9.5] - 2026-04-27

### Changed

- `claude-agent-sdk`: 0.1.65 -> 0.1.68. The SDK now declares
  `sniffio >= 1.0.0` as a runtime dependency; the lock picks up
  `sniffio 1.3.1`.

### CI

- `check-sdk-version.yml`: replaced the issue-creation step with a
  `GITHUB_STEP_SUMMARY` write. The repo has issues disabled, which made the
  weekly job fail at `gh issue create`. Dropped the unused `issues: write`
  permission.

## [2.9.4] - 2026-04-24

### Security

Closes all seven open Dependabot alerts. Three affect the runtime image; four
are dev-only.

| Package | From | To | CVE | Severity | Runtime? |
|---------|------|----|-----|----------|----------|
| black | 24.10.0 | 26.3.1 | CVE-2026-32274 (arbitrary file write from unsanitized cache input) | high | dev only |
| filelock | 3.20.1 | 3.29.0 | CVE-2026-22701 (TOCTOU symlink) | medium | dev only |
| requests | 2.32.4 | 2.33.1 | CVE-2026-25645 (insecure tmp file reuse in `extract_zipped_paths`) | medium | runtime (also in dev group) |
| pytest | 8.4.1 | 9.0.3 | CVE-2025-71176 (tmpdir handling) | medium | dev only |
| python-multipart | 0.0.22 | 0.0.26 | CVE-2026-40347 (DoS via large preamble/epilogue) | medium | runtime |
| python-dotenv | 1.1.1 | 1.2.2 | CVE-2026-28684 (symlink follow in `set_key`) | medium | runtime |
| Pygments | 2.19.2 | 2.20.0 | CVE-2026-4539 (GUID ReDoS) | low | dev only (transitive) |

### Changed

- `pytest-asyncio ^0.23 -> ^1.3.0`, required by pytest 9.
- Reformatted three test files with black 26.

## [2.9.3] - 2026-04-24

### Fixed

- `ModuleNotFoundError: No module named 'opentelemetry'` at first SDK
  connect. `claude-agent-sdk 0.1.65` imports `opentelemetry.propagate`
  unconditionally, but PyPI declares `opentelemetry-api` only as an optional
  `[otel]` extra. The 2.9.2 image (built with `poetry install --only main`)
  shipped without it. The pin is now
  `claude-agent-sdk = {version = "0.1.65", extras = ["otel"]}`, and
  `opentelemetry-api 1.41.1` ships in the image.

## [2.9.2] - 2026-04-24

### Changed

- CI has no Docker smoke-build step: images are built and pushed locally, and
  CI only gates Python-side checks.
- Ran `black` across `src/` and `tests/`; 18 files reformatted with no
  behavioural change.
- Disabled the `Claude Code Review` workflow on GitHub. The file was removed
  in 2.9.1, but `pull_request_target` kept executing it from `main` until it
  was disabled.

## [2.9.1] - 2026-04-24

### Security

Closes the ten CodeQL code-scanning alerts open on `main`.

- `claude-code-review.yml` removed (alert #1,
  `actions/untrusted-checkout/high`). It checked out `pull_request.head.sha`
  inside a `pull_request_target` job, exposing repo secrets to untrusted
  code.
- `ci.yml` permissions pinned to `contents: read` (alert #2,
  `actions/missing-workflow-permissions`).
- Error responses no longer leak exception detail (alerts #7-#10,
  `py/stack-trace-exposure`). `str(e)` is replaced with static strings in
  `_build_assistant_error_response`, the streaming SSE error chunk, the
  chat-completions and Anthropic-messages 500 handlers, and
  `/v1/debug/request`. That endpoint is now gated behind `DEBUG_MODE` or
  `VERBOSE` and emits only the exception type name. Server-side logging of
  the full exception is unchanged.
- `MessageAdapter.filter_content` regexes hardened against polynomial ReDoS
  (alerts #3-#6, `py/polynomial-redos`). The lazy `<tag>.*?</tag>` patterns
  are rewritten to the non-backtracking
  `<tag>[^<]*(?:<(?!/tag>)[^<]*)*</tag>` form. The image-reference pattern
  uses fixed upper bounds (`[^\]]{0,1024}` / `[^\s]{0,65536}`). Input over
  1 MB is returned unchanged.

### Changed

- Client-visible error message text is now generic ("Chat completion
  failed"). The `type` and `code` fields are unchanged.
- `Dockerfile`: `poetry install --no-root --only main` keeps dev packages out
  of the runtime image. This removes the one Trivy HIGH with an available fix
  (CVE-2026-32274, `black < 26.3.1`) and drops the image from 1.18 GB to
  775 MB.
- Added `.dockerignore` so `COPY . /app` stops pulling `.git`, `.venv`,
  `.hypothesis`, `.pytest_cache`, `tests`, `docs`, `.env*` and editor files
  into the image.
- The remaining 7 Trivy HIGHs are in the Debian 13.4 base: ncurses
  (CVE-2025-69720), nghttp2 (CVE-2026-27135) and systemd (CVE-2026-29111).
  None had an upstream fix at release. Accepted risk.
- `ci.yml`: added `timeout-minutes: 15`, `fail-fast: false` and
  `poetry check --lock`, replaced the deprecated `safety check` with
  `pip-audit`, and added a `docker` job that smoke-builds the prod image on
  every PR.
- `claude.yml`: repo-specific `claude_args` with a read-only tool allowlist.

## [2.9.0] - 2026-04-23

### Changed

- `claude-agent-sdk` bumped from `0.1.18` to `0.1.65` (exact pin), 47 patch
  releases. The reason was the `error_during_execution` rate seen on 2.8.2 in
  production (about 48/hr, `num_turns=2`, `usage.input_tokens=0`,
  `stderr_tail_chars=0`). Fixes in the range:
  - 0.1.51: `ResultMessage.errors` is populated (#749); dropped fields on
    `AssistantMessage` and `ResultMessage` are preserved (#718).
  - 0.1.52: `control_cancel_request` handling (#751). In-flight hook
    callbacks are cancelled when the CLI abandons them.
  - 0.1.53: string-prompt deadlock fix (#780).
  - 0.1.57: thinking-config serialization fix (#796).
    `thinking={"type":"adaptive"}` and `{"type":"disabled"}` now use the
    `--thinking` flag instead of `--max-thinking-tokens`.
  - 0.1.60: `setting_sources=[]` is no longer silently dropped (#822). W3C
    distributed-tracing propagation added.
  - Bundled Claude CLI advanced from 2.0.72 to 2.1.118.

## [2.8.2] - 2026-04-23

Dependency bump to clear trivy HIGH/CRITICAL findings against 2.8.1. No code
change.

### Security

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

No fix was available for nltk CVE-2026-33231 and CVE-2026-33236 (XML path
traversal) or for the Debian base-image packages libncursesw6, libnghttp2-14,
libsystemd0, libtinfo6, libudev1, ncurses-base and ncurses-bin.

### Changed

- `pyproject.toml`: explicit security floors for `starlette`, `urllib3`,
  `cryptography`, `pyjwt`, `authlib`, `mcp` and `nltk`. `fastapi` widened to
  `>=0.119,<1.0` to allow starlette 0.49.x and later.

## [2.8.1] - 2026-04-23

Hotfix on top of 2.8.0 after a breaker cascade during live reprocessing.

### Fixed

- Structured log fields now render in plain-text logs. The default log
  format has no extras printer, so `circuit_breaker_open`,
  `completion_result`, `claude_sdk_error*` and `claude_sdk_assistant_error`
  reached Loki without their fields. They now serialize inline as
  `event key=value key=value`.
- Circuit breaker defaults loosened: `min_requests_for_trip` raised from 10
  to 20 and `failure_ratio_threshold` from 0.5 to 0.75. The old values
  tripped on a transient burst of `error_during_execution` (5/10 = 0.5). All
  thresholds are env-configurable: `WRAPPER_CIRCUIT_BREAKER_ENABLED`,
  `WRAPPER_CIRCUIT_BREAKER_THRESHOLD`, `WRAPPER_CIRCUIT_BREAKER_MIN_REQUESTS`,
  `WRAPPER_CIRCUIT_BREAKER_OPEN_SECONDS` and
  `WRAPPER_CIRCUIT_BREAKER_WINDOW_SECONDS`.

### Added

- CLI subprocess stderr capture: a 40-line ring buffer is installed as the
  `ClaudeAgentOptions.stderr` callback on every request. On a non-success
  `ResultMessage` the tail is logged at WARNING with the session id and
  `num_turns`, and attached as `stderr_tail` on `ClaudeResultError`.

### Changed

- The breaker snapshot includes `enabled` and `min_requests_for_trip`.

## [2.8.0] - 2026-04-23

### Fixed

- SDK `error_max_turns` no longer leaks `[Request interrupted by user]` as
  response content. `parse_claude_message` raises `ClaudeResultError` when a
  `ResultMessage` has `is_error=True` or a subtype in `{error_max_turns,
  error_during_execution, error}`. The SDK inserts a synthetic `UserMessage`
  with that text before those results, and the fallback loop had returned it
  as the assistant response. `UserMessage` is now filtered out of response
  text.
- `max_turns` with tools off raised from 1 to 3, configurable via
  `WRAPPER_DEFAULT_MAX_TURNS`. A value of 1 caused `error_max_turns` when the
  agent used extended thinking and needed a second turn for the final
  message.
- The `max_tokens -> max_thinking_tokens` mapping is off by default. OpenAI
  `max_tokens` caps response length, which the Agent SDK has no equivalent
  for, and the mapping made short prompts burn the thinking budget. Opt in
  with `WRAPPER_MAP_MAX_TOKENS_TO_THINKING=true`.
- A non-success `ResultMessage` produces an OpenAI-shaped HTTP response:
  `error_max_turns` -> `200` with `finish_reason="length"` and empty
  `content`; other SDK errors -> `502` with a structured error body. The
  streaming path emits a terminal SSE event with the matching
  `finish_reason` and `[DONE]`.

### Added

- `ClaudeResultError` exception carrying `subtype`, `num_turns`, `errors`,
  `stop_reason` and `error_message`.
- `AssistantMessage.error` values map to HTTP status codes: `rate_limit` ->
  429 with `Retry-After: 30`, `billing_error` -> 402,
  `authentication_failed` -> 401, `invalid_request` -> 400, `server_error`
  and `unknown` -> 502.
- Circuit breaker on SDK errors (`src/circuit_breaker.py`): an in-process
  rolling-window breaker. It opens when at least 50% of at least 10 requests
  in the last 60s failed, cools off for 30s and half-opens with a single
  probe. While open, completions return `503 Retry-After: 30`.
- `/healthz/deep` endpoint: a probe that exercises the completion path. It
  tracks 10 outcomes and returns `503` when the failure rate exceeds 20%.
- `completion_result` log line: one INFO record per successful completion
  with `request_id`, `session_id`, `subtype`, `num_turns`, `duration_ms`,
  `total_cost_usd`, `is_error`, `finish_reason`, `model` and token counts.
- `BUILD_INFO` image stamp recording the installed `claude-agent-sdk`
  version and bundled-CLI presence, logged at startup.
- Multi-stage Dockerfile with `dev` and `prod` targets. `dev` keeps
  `--reload`; `prod` runs with `--workers 2 --no-access-log` (override via
  `UVICORN_WORKERS`). `docker-compose.yml` defaults to `prod`.

### Changed

- SDK pinned exactly: `claude-agent-sdk = "0.1.18"` (was `^0.1.18`). The
  caret range let behaviour change between Docker builds without a code
  change.

## [2.7.0] - 2026-04-16

### Added

- `claude-opus-4-7` (Claude Opus 4.7): 1M context, 128K max output, $5/$25
  per MTok, falls back to `claude-sonnet-4-6` on overload.

### Changed

- Model metadata aligned with the Anthropic docs:
  - `claude-opus-4-6`: context window 200K -> 1M
  - `claude-sonnet-4-6`: context window 200K -> 1M, max output 128K -> 64K
  - `claude-opus-4-1-20250805`: max output 64K -> 32K
  - `claude-opus-4-20250514`: max output 64K -> 32K
- `.env.example`, the landing page quickstart and the debug endpoint example
  use `claude-sonnet-4-6`.

### Removed

- Retired models removed from `CLAUDE_MODELS`, `MODEL_METADATA` and
  `MODEL_PRICING`: `claude-3-7-sonnet-20250219` (retired 2026-02-19),
  `claude-3-5-sonnet-20241022` (retired 2025-10-28) and
  `claude-3-5-haiku-20241022` (retired 2026-02-19).

## [2.6.0] - 2026-04-02

### Added

- OpenAI function calling (`src/function_calling.py`), simulated through
  system prompt injection and response parsing. `tools` and `tool_choice`
  become system prompt text; `tool_calls` blocks and bare JSON arrays in the
  response become OpenAI-format `tool_calls` with generated call IDs.
  Assistant tool calls and tool results in multi-turn conversations are
  converted to text.
- `response_format.type = "json_schema"`. The schema is injected into the
  user prompt with rules for required properties, exact names and exact
  types.
- Streaming fence stripping (`JsonFenceStripper`): markdown `json` fences are
  removed during streaming, across chunk boundaries, so JSON chunks flow in
  real time.
- CPU watchdog (`src/cpu_watchdog.py`) for Docker and Linux. It reads
  `/proc/self/stat` every 30s and sends SIGTERM after 3 consecutive readings
  above 80% CPU. Off by default; enable with `WATCHDOG_ENABLED=true`.

### Changed

- `Message` gained the `tool` role and the `tool_calls` and `tool_call_id`
  fields. `ResponseFormat` gained the `json_schema` type. `Choice` and
  `StreamChoice` gained the `tool_calls` finish reason.

## [2.5.2] - 2026-04-01

### Fixed

- Removed BashOutput, KillShell and SlashCommand from the tool inventory.
  They do not exist in Claude Code's tool registry.

### Added

- 11 tools verified against Claude Code source: Brief, Config, ListPeers,
  REPL, Sleep, Monitor, SendUserFile, PushNotification, ListMcpResources,
  ReadMcpResource and VerifyPlanExecution. Tool count: 33 -> 41.

## [2.5.1] - 2026-04-01

### Fixed

- Repository link corrected from the aaronlippold fork to
  ttlequals0/claude-code-openai-wrapper.
- FastAPI docs version uses `__version__` instead of a hardcoded "1.0.0".

### Changed

- Landing page redesigned with custom CSS in place of Pico CSS. It lists all
  25 endpoints in 8 categories; it previously showed 9.

## [2.5.0] - 2026-03-31

### Added

- Per-model context window sizes and output token limits.
- Per-model pricing (input, output, cache read and write).
- Cost tracker (`src/cost_tracker.py`): per-request and per-session cost
  estimates from input, output and cache tokens and web search requests.
- Retry logic (`src/retry.py`): exponential backoff with jitter, 10 retries
  by default, 500ms base delay, 30s max delay. After 3 consecutive 529
  responses an Opus request falls back to Sonnet. Retryable status codes:
  429, 529, 5xx, 401, 400.
- 18 tools added to match Claude Code's inventory: `Agent` (with `Task` as an
  alias), `SendMessage`, `TaskCreate`, `TaskUpdate`, `TaskGet`, `TaskList`,
  `TaskOutput`, `TaskStop`, `EnterPlanMode`, `ExitPlanMode`, `EnterWorktree`,
  `ExitWorktree`, `ToolSearch`, `AskUserQuestion`, `CronCreate`,
  `CronDelete`, `CronList` and `RemoteTrigger`.
- `X-Claude-Effort` header (low, medium, high, max).
- `X-Claude-Thinking` header (adaptive, enabled, disabled).
- Model-specific `max_tokens` validation and capping.

### Changed

- Added `claude-sonnet-4-6` and re-added `claude-3-7-sonnet-20250219`,
  `claude-3-5-sonnet-20241022` and `claude-3-5-haiku-20241022`.
- Default model changed from `claude-sonnet-4-5-20250929` to
  `claude-sonnet-4-6`.
- `Bash` is marked as requiring permissions; `Agent`, `SendMessage` and
  `RemoteTrigger` are marked unsafe. `SendMessage` and `RemoteTrigger` are
  disallowed by default.

## [2.4.2] - 2026-02-06

### Added

- Model refresh respects `CLAUDE_AUTH_METHOD`: `anthropic` auth fetches
  models from the API; `cli`, `bedrock` and `vertex` use the static list.
- `/v1/models/refresh` and `/v1/models/status` responses include
  `auth_method`.
- Landing page cards for `/v1/models/status` and `/v1/models/refresh`.

### Changed

- Added `claude-opus-4-6`; removed `claude-opus-4-5-20250929` from the static
  list.
- The refresh endpoint returns a clear message under non-anthropic auth.

## [2.4.1] - 2026-02-06

### Added

- `POST /v1/models/refresh` refreshes models from the Anthropic API without
  a restart.
- `GET /v1/models/status` returns the source (api or fallback) and the last
  refresh timestamp.

## [2.4.0] - 2026-02-04

### Added

- JSON mode instructions rewritten as numbered rules that prohibit preambles.
- 19 common Claude preambles are stripped from JSON responses.
- Balanced brace and bracket extraction that handles escaped quotes and
  braces inside strings.
- `extract_json_with_metadata()` and `enforce_json_format_with_metadata()`
  return the extraction method along with the content.
- Request deduplication cache with LRU eviction and TTL expiry. Configure
  with `REQUEST_CACHE_ENABLED`, `REQUEST_CACHE_MAX_SIZE` and
  `REQUEST_CACHE_TTL_SECONDS`; enable per request with
  `X-Enable-Cache: true`.
- `GET /v1/cache/stats` and `POST /v1/cache/clear`.

### Changed

- JSON extraction order: pure JSON, preamble removal, markdown code block,
  balanced brace matching, first-to-last fallback.
- JSON enforcement logs the extraction method used.

### Fixed

- JSON extraction handles escaped quotes within strings and is no longer
  confused by braces inside string values.

## [2.3.1] - Previous Release

Initial tracked version with JSON mode support.
