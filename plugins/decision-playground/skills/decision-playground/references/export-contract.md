# Export Contract

Generated decision pages must export choices in three forms: Markdown, agent prompt, and JSON. Keep these forms aligned so the user can return any one of them and Codex can continue without re-asking the same questions.

## JSON Shape

Use this structure by default:

```json
{
  "title": "Decision page title",
  "goal": "What this decision unblocks",
  "version": 1,
  "completedAt": "ISO-8601 timestamp",
  "status": "complete",
  "decisions": [
    {
      "id": "stable-id",
      "label": "Human-readable decision",
      "value": "selected-value",
      "summary": "Short meaning of the selected value",
      "rationale": "Why this option was selected or recommended",
      "impact": "Effect on implementation, UX, risk, or scope",
      "confidence": "high"
    }
  ],
  "notes": "User notes or constraints",
  "openQuestions": [
    "Only include unresolved questions that still block work"
  ],
  "agentPrompt": "Follow-up instruction for Codex"
}
```

Allowed `status` values:

- `complete`: all required decisions have a selected value.
- `partial`: some non-blocking choices are missing.
- `blocked`: one or more required choices are missing.

Allowed `confidence` values:

- `high`
- `medium`
- `low`
- `unknown`

## Markdown Summary

Keep the Markdown short and easy to paste into chat:

```markdown
# Decision Summary: <title>

Goal: <goal>
Status: <complete|partial|blocked>

## Selected Decisions

- <label>: <value> — <impact>
- <label>: <value> — <impact>

## Notes

<user notes>

## Open Questions

- <remaining blocker>
```

## Agent Prompt

The agent prompt must be action-oriented:

```markdown
Use these decisions as the source of truth.

Goal: <goal>

Decisions:
- <label>: <value>. <impact>

Notes:
<user notes>

Continue by <specific next action>.
Do not re-ask resolved decisions unless the implementation uncovers a contradiction.
```

## Copy Behavior

Each copy button must:

1. Recompute the current state.
2. Validate required choices.
3. Copy the selected export to the clipboard.
4. Show a short visible confirmation.
5. If clipboard access fails, reveal a text area with the export selected.

## Stable IDs

Use stable lowercase IDs with hyphens, such as `auth-model`, `rollout-strategy`, or `dashboard-density`. Do not use display labels as IDs; labels may change while IDs should remain stable.
