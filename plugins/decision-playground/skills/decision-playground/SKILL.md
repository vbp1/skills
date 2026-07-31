---
name: decision-playground
description: Create self-contained interactive HTML decision pages for long questionnaires, architecture tradeoffs, UI variants, implementation choices, prioritization, and situations where the user should choose visually instead of reading a long text prompt. Use when Codex needs to gather many user decisions, explain alternatives with consequences, compare options side by side, or turn selected choices into a reusable decision summary, JSON export, or follow-up agent prompt.
---

# Decision Playground

Create a self-contained HTML page that helps the user make choices visually, then export those choices back into the agent workflow. Use this instead of sending long text questionnaires or dense option lists in chat.

The goal is not just explanation. The page must produce a usable decision artifact: a concise summary, a structured JSON export, and a follow-up prompt or instruction set that Codex can use after the user returns it.

## Use This Skill When

Use this skill when the next step requires user choices across multiple dimensions:

- A long questionnaire with more than 3-5 meaningful questions.
- Architecture or implementation alternatives with tradeoffs.
- UI, UX, layout, density, wording, or interaction variants.
- Scope negotiation: must-have, should-have, out-of-scope, later.
- Prioritization, triage, or sequencing decisions.
- Prompt, policy, configuration, or feature-flag tuning.

Do not use it for a single small clarification. Use the built-in clarification flow for that.

Do not use it for a static diagram or visual report. Use `visual-explainer` when the user needs to understand information, and use this skill when the user needs to decide and export choices.

## Core Workflow

1. Define the decision goal in one sentence.
2. Extract the smallest set of real choices needed to unblock the work.
3. Pick one template from `templates/`:
   - `questionnaire.html` for structured multi-question intake.
   - `tradeoff-matrix.html` for architecture and implementation forks.
   - `code-approaches.html` for choosing between concrete coding strategies.
   - `option-gallery.html` for UI, UX, design, and copy variants.
   - `component-variants.html` for selecting a specific component treatment.
   - `flow-prototype.html` for clickable interaction-flow decisions.
   - `triage-board.html` for priority, scope, and sequencing.
   - `implementation-brief-builder.html` for turning decisions into a scoped
     implementation brief.
4. Read `references/export-contract.md` and keep the export fields compatible.
5. Read `references/interaction-patterns.md` if the decision type is not obvious.
6. Read `references/visual-rules.md` before styling or adapting a template.
7. Copy the chosen template into `~/.agent/diagrams/` with a descriptive filename.
8. Replace the sample data with task-specific decisions, consequences, and presets.
9. Keep the page self-contained: inline CSS, inline JavaScript, no build step.
10. Open the HTML page in a browser.
11. Ask the user to complete the page and return one of the exports.
12. Continue from the returned export and save durable decisions into the project artifact when relevant.

## Decision Quality Rules

- Ask for decisions, not preferences disguised as decisions.
- Keep each choice tied to a consequence: implementation cost, user effect, compatibility, risk, or sequencing.
- Provide a recommended default for each choice, but make alternatives visible.
- Prefer fewer high-quality decisions over many low-signal questions.
- Use presets when they reflect real strategies, such as "fast prototype", "safe migration", "enterprise-ready", or "minimal UI".
- Mark irreversible or expensive decisions clearly.
- Make uncertainty visible with `unknown`, `needs research`, or `blocked` choices instead of forcing a fake answer.

## Required Page Features

Every generated page must include:

- A visible decision goal near the top.
- Interactive controls for each meaningful choice.
- A preview, comparison, board, or summary that updates as choices change.
- Clear recommended defaults.
- `Copy decision summary` for concise Markdown.
- `Copy agent prompt` for the next Codex step.
- `Copy JSON` for structured state.
- A small validation area that shows missing required choices.

Optional, when useful:

- Preset buttons.
- Risk, cost, complexity, or confidence meters.
- Side-by-side option comparison.
- Free-text notes for user constraints.
- `Download JSON` when the user may want to attach a file.

## Output Location

Write generated pages to `~/.agent/diagrams/`.

Use a descriptive filename:

- `rbac-architecture-decisions.html`
- `dashboard-ui-options.html`
- `migration-scope-questionnaire.html`
- `release-triage-board.html`
- `search-code-approaches.html`
- `settings-flow-prototype.html`
- `card-component-variants.html`
- `comments-implementation-brief.html`

Open the result in the browser:

```bash
xdg-open ~/.agent/diagrams/<filename>.html
```

## After the User Returns an Export

Treat the returned export as the source of truth for the next step.

1. Parse the returned summary or JSON.
2. Restate the selected decisions briefly.
3. Identify any remaining blockers.
4. Continue with the requested artifact: plan, PRD, issues, code, review, or documentation.
5. If decisions are long-lived, write them into the project document, `decisions/` file, issue body, or other canonical artifact.

Do not ask the same questions again unless the export is incomplete or contradictory.
