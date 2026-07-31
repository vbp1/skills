---
name: telemost-scribe-api
description: Use the local Telemost Scribe HTTP API to inspect capabilities, search meeting transcripts and summaries, and answer questions from the meeting archive with citations. Use when the user asks Codex to query Telemost Scribe history, test the agent API, check OpenAPI availability, or answer questions about recorded meetings through the API.
---

# Telemost Scribe API

## Quick Start

Use the bundled script relative to this skill directory:

```bash
python scripts/search.py capabilities
python scripts/search.py search "question text"
```

Default base URL is `http://127.0.0.1:8765`. Override it with `--base-url` or `TELEMOST_SCRIBE_API_URL`.

## Workflow

1. Check capabilities before a search when the service may have been restarted:
   `search.py capabilities`.
2. Search with both sources by default:
   `search.py search "<question>" --limit 8 --context-segments 1`.
3. Use `--source segments` for transcript-only search, `--source summary` for resume-only search, or repeat `--source` for both.
4. Use `--meeting-id` one or more times to narrow the search to specific meetings.
5. Use `--json` when exact payload inspection is needed.

## Answering Rules

- Answer from returned API results only.
- Include citations with meeting title or ID, timestamp, segment ID, and source.
- If results are weak or empty, say that the API did not return enough evidence.
- Prefer short Russian answers unless the user asks for raw data.

## API Shape

`GET /api/agent/capabilities` returns supported search settings and OpenAPI path.

`POST /api/agent/search` accepts:

```json
{
  "query": "question",
  "meeting_ids": ["optional-meeting-id"],
  "sources": ["segments", "summary"],
  "limit": 10,
  "context_segments": 1
}
```

Each result contains `source`, `meeting_id`, `meeting_title`, `segment_id`, `timestamp`, `speaker`, `text`, and `context`.
