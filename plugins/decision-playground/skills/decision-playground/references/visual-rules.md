# Visual Rules

Decision pages must make choices faster to understand than a chat transcript.

## Layout

- Put the decision goal and export controls within the first viewport.
- Use a two-column layout on desktop when it helps: controls on the left, summary or preview on the right.
- Use a single column on mobile.
- Keep required choices visibly grouped.
- Avoid nesting cards inside cards.
- Use real HTML form controls where possible.

## Text

- Use short labels.
- Put consequences beside options, not in a separate wall of prose.
- Prefer "Fastest, least flexible" over abstract names like "Option A".
- Keep each option explanation to 1-2 sentences.
- Match the user's language for user-facing page text.

## Defaults

- Mark one recommended option for every required decision when there is a defensible default.
- Explain the default with a short consequence.
- Do not auto-select destructive or irreversible choices unless the user already asked for them.

## Visual Encoding

- Use consistent colors for meaning:
  - Green or teal: recommended, accepted, lower risk.
  - Amber or gold: caution, medium risk, needs attention.
  - Rose or red: high risk, rejected, destructive, blocked.
  - Slate or neutral: undecided or informational.
- Use badges for cost, risk, and confidence.
- Use meters only when they summarize choices from the current state.

## Accessibility

- Keep contrast readable in light and dark modes.
- Use labels associated with inputs.
- Ensure keyboard users can reach every control.
- Do not rely on color alone; include text badges.
- Respect `prefers-reduced-motion`.

## Implementation

- Keep generated pages self-contained.
- Use inline CSS and inline JavaScript.
- Avoid external dependencies unless the page cannot work well without them.
- Store all decision data in a single `data` or `state` object near the top of the script.
- Generate exports from state instead of hand-maintaining separate strings.
- Include a fallback text area when clipboard copy fails.
