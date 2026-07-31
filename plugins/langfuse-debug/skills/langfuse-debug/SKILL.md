---
name: langfuse-debug
description: >
  Debug and analyze LLM agent execution traces in Langfuse (self-hosted or cloud).
  Use when investigating agent failures, analyzing session traces, reviewing token usage,
  or debugging tool call patterns in Langfuse. Triggers: "langfuse", "трейсы",
  "traces", "debug session", "investigate failures", "analyze trace",
  "token usage", "посмотри в langfuse", "исследуй трейсы", "langfuse session".
---

# Langfuse Debug

Analyze LLM agent execution traces in Langfuse to investigate failures, token usage, and tool call patterns.

## Prerequisites

Credentials are auto-discovered in this order:
1. Env vars: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
2. `.env.production`, `.env.local`, `.env` files in CWD and parent dirs

Docker-internal hosts (e.g. `langfuse-web:3000`) are rewritten to `localhost` automatically.

Verify connectivity: `python scripts/lf_api.py health`

## Quick Start

```bash
# Analyze a session (accepts URL or UUID)
python scripts/lf_session.py https://langfuse.example.com/project/xxx/sessions/SESSION_ID
python scripts/lf_session.py SESSION_UUID

# Deep dive into a specific trace
python scripts/lf_trace.py TRACE_ID

# Show only errors
python scripts/lf_session.py SESSION_ID --errors-only
python scripts/lf_trace.py TRACE_ID --errors-only
```

## Workflow: Investigate Agent Failures

1. **Get session report**: `python scripts/lf_session.py <session-url-or-id>`
   - Review "Issues Found" section for EMPTY_TEXT, ERROR counts
   - Check "Trace Timeline" for traces with issues

2. **Drill into failing trace**: `python scripts/lf_trace.py <trace-id>`
   - Look for `[EMPTY_TEXT]` flags on GENERATION observations
   - Check SPAN observations for tool error results
   - Note token counts growing → context window pressure

3. **Interpret common patterns**:
   - **Many consecutive EMPTY_TEXT generations** → model hallucinating tool calls as text (DSML)
   - **EMPTY_TEXT after large tool result** → context overload causing format confusion
   - **ERROR level observations** → explicit failures in tool execution
   - **High output tokens but empty text** → reasoning tokens consumed without producing visible output

## Workflow: Token Usage Analysis

Run `python scripts/lf_session.py <session-id>` — the "Token Usage" table shows per-trace breakdown with input/output/total columns.

## Script Reference

### lf_api.py — Core API client

```
lf_api.py health                              # Check credentials + API status
lf_api.py get <path> [--params '{"key":"val"}']  # Raw GET to /api/public<path>
```

### lf_session.py — Session analyzer

```
lf_session.py <session-url-or-id>             # Full session report
lf_session.py <id> --errors-only              # Only observations with issues
lf_session.py <id> --trace-index N            # Detail for specific trace only
```

### lf_trace.py — Trace deep dive

```
lf_trace.py <trace-url-or-id>                # Full observation timeline
lf_trace.py <id> --generations-only           # Only GENERATION observations
lf_trace.py <id> --errors-only               # Only observations with issues
```

## Advanced: Raw API

When scripts don't cover a case, use `lf_api.py get` or consult [references/api-endpoints.md](references/api-endpoints.md) for endpoint details.

```bash
# List recent traces
lf_api.py get /traces --params '{"limit":5}'

# Get specific observation with full I/O
lf_api.py get /observations/OBSERVATION_ID

# Create a score for a trace
# (Use curl directly for POST requests)
```
