# Langfuse API Quick Reference

Base URL: `{LANGFUSE_HOST}/api/public`
Auth: Basic Auth (username=public_key, password=secret_key)
Pagination: `page` (1-based) + `limit` params; response has `meta.totalPages`

## Sessions

```
GET /sessions                         # List sessions (page, limit, fromTimestamp, toTimestamp)
GET /sessions/{sessionId}             # Get session with trace list
```

## Traces

```
GET /traces                           # List traces
  ?sessionId=xxx                      # Filter by session
  ?userId=xxx                         # Filter by user
  ?name=xxx                           # Filter by trace name
  ?tags=tag1&tags=tag2                # Filter by tags
  ?fromTimestamp=ISO&toTimestamp=ISO   # Time range
  ?page=1&limit=50                    # Pagination

GET /traces/{traceId}                 # Get trace detail (includes observations inline)
PATCH /traces/{traceId}               # Update trace metadata (tags, public, metadata)
```

## Observations

```
GET /observations                     # List observations
  ?traceId=xxx                        # Filter by trace (most common)
  ?name=xxx                           # Filter by name
  ?type=GENERATION|SPAN|EVENT         # Filter by type
  ?level=DEFAULT|DEBUG|WARNING|ERROR  # Filter by level
  ?fromStartTime=ISO&toStartTime=ISO # Time range
  ?page=1&limit=100                   # Pagination

GET /observations/{observationId}     # Get single observation with full input/output
```

### Observation fields

| Field | Description |
|-------|-------------|
| `type` | GENERATION (LLM call), SPAN (tool/function), EVENT |
| `name` | e.g. `ai.streamText.doStream`, `ai.toolCall queryMetrics` |
| `model` | Model ID (for GENERATION) |
| `usage.input`, `usage.output` | Token counts |
| `output` | Response content (list of text/tool-call parts, or string/dict) |
| `level` | DEFAULT, DEBUG, WARNING, ERROR |
| `statusMessage` | Error details if any |
| `startTime`, `endTime` | Timestamps for duration calculation |

## Scores

```
POST /scores                          # Create score
  body: {traceId, name, value, observationId?, comment?, dataType?}

GET /scores                           # List scores
  ?traceId=xxx
  ?name=xxx
  ?page=1&limit=50

DELETE /scores/{scoreId}              # Delete score
```

## Common patterns

**Find all errors in a session:**
```
GET /traces?sessionId=xxx
  → for each trace:
    GET /observations?traceId={id}&limit=100
      → filter: type=GENERATION and output is empty/null = DSML hallucination
      → filter: level=ERROR or statusMessage contains "error"
```

**Token usage summary:**
```
GET /traces?sessionId=xxx
  → for each trace:
    GET /observations?traceId={id}&type=GENERATION
      → sum usage.input and usage.output
```
