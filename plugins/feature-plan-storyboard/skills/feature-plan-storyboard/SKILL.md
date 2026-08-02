---
name: feature-plan-storyboard
description: >-
  End-to-end feature-planning workflow: create or update the plan, verify every
  claim against the current code with parallel agents (file:line evidence),
  surface product forks via plain-language questions, write prose + file:line
  links (no code blocks), cross-review with codex until APPROVED, then build
  and browser-verify an interactive user-stories storyboard HTML page themed to
  the product UI. Triggers (RU): "оцени/обнови/создай план", "сверь план с
  кодом", "страничка сценариев", "storyboard". Triggers (EN): "assess/update
  the plan", "check plan against code", "user-stories storyboard page".
---

# Feature Plan & Storyboard

This skill captures a full path from a rough feature idea (or an existing,
possibly-stale plan) to a code-verified, peer-reviewed plan **and** an
interactive page that explains the feature the way users will experience it.

Two deliverables, produced in order:

1. **A plan** (the project's plan/design-doc location — e.g. a `todos/*.md`,
   `docs/`, or an issue body) — prose + `file:line` links, reviewed by a second
   AI until formally approved.
2. **A storyboard page** (`<plan-basename>-user-stories.html`) — a
   self-contained, themed, interactive walkthrough of the feature.

The plan is the source of truth; the storyboard makes it tangible. Build the
plan first — the storyboard's scenarios and "under the hood" notes come straight
from it, so a shaky plan yields a misleading page.

## Why this shape

A plan that drifts from the code is worse than no plan: it reads authoritative
while pointing at functions and tables that no longer exist. So the spine of
this skill is **verification against the current codebase**, not prose polish.
The storyboard exists because architecture tables and ASCII diagrams don't let a
stakeholder *feel* the feature — side-by-side actor windows (one per role)
playing through a scenario do, and the "under the hood" panel ties each visible
step back to the mechanism in the plan. The engine renders each actor's view as
a message feed, which fits interaction/communication features best; for a
feature of another shape (a form wizard, a dashboard, a settings flow) keep the
layout but make each window show that actor's screen/state instead of a feed.

## When NOT to use

- Pure implementation with no planning artifact → just write code.
- A one-paragraph note that needs no code verification or review.
- The user wants a generic data/UX playground unrelated to a feature plan →
  use the `playground` skill instead.

## Workflow

Run the stages in order, but adapt: if the user only wants the plan, stop after
stage 5; if they only want the page for an already-approved plan, start at
stage 6. Always confirm scope before a long stage (verification, codex loop,
page build).

### Stage 0 — Scope

Determine in one or two questions (via `AskUserQuestion`, plain language):
- **Create vs update** an existing plan? Locate the plan file if it exists.
- **Deliverables**: plan only, page only, or both?
- For the page: **theme** (light / dark / both with a toggle) and which product
  UI it should resemble.

Don't ask what you can read: open the plan file, the project's `CLAUDE.md`/
`AGENTS.md`, and recent git history first.

### Stage 1 — Verify the plan against current code

This is the load-bearing stage. **Read `references/plan-method.md`** for the full
method. In short: extract every concrete claim the plan makes about the code
(file paths, symbols, line refs, "X already works", dependency statuses) and
verify each against the working tree. Fan out **parallel research agents** (the
`Agent` tool, `Explore` or `general-purpose`) — one sweep per subsystem — and
require `file:line` evidence with a verdict per claim: CONFIRMED / STALE /
WRONG. Personally re-open anything load-bearing before you rely on it; a
mis-cited line number poisons everything downstream.

Surface the findings as a severity-ranked table (blocker / important /
cosmetic) before editing, per the project's "present findings before
implementing" rule.

### Stage 2 — Resolve forks with the user

When verification exposes a real product or architecture decision (e.g. a data
store the plan assumed is gone), don't silently pick — put it to the user via
`AskUserQuestion`. Phrase questions and every option in **plain language**: no
class/method/table names, no internal jargon, describe each option by its
*consequence*. Put the recommended option first. (This mirrors the user's global
question-style rule.) Technical detail goes in your prose *after* they choose.

### Stage 3 — Write / update the plan

**Prose + `file:line` links, never code blocks** (ASCII diagrams and tables are
fine; pseudocode only if meaning is lost without it). `references/plan-method.md`
gives the section template (status, dependencies, "what already works", "what's
new", key-decisions table, architecture ASCII, data model, phases, test strategy
incl. e2e, affected files, security, open decisions). Keep every section
mutually consistent — the codex loop punishes drift hard.

### Stage 4 — Cross-review with a second AI (codex), iterate to APPROVED

Use the project's `codex-review` skill (or equivalent). `init` a session, submit
the plan, then iterate: read each finding, **critically** accept or argue it
(verify cited code yourself — reviewers err too), fix the plan addressing every
point, resubmit. Synchronize **all** sections on each pass — a fix in one place
that contradicts a diagram elsewhere will bounce. Proceed only on a formal
`APPROVED` verdict (check the verdict helper, not the prose). Details and the
accept/argue discipline: `references/plan-method.md`.

### Stage 5 — Add the storyboard link to the plan

Once the page exists (stage 6), add a prominent link to it near the top of the
plan and contextual links from the routing/UX and test-strategy sections.

### Stage 6 — Build the storyboard page

**Read `references/storyboard.md`** and start from
`assets/storyboard-template.html`. The template is the canonical shape — keep its
structure and engine; replace only the data and theme tokens:

- **Theme & design**: fill the `:root` (and `[data-theme="light"]`) CSS tokens
  with the **product's own palette/typography** so the page looks like the real
  app, not generic Bootstrap. Inspect the product's UI for colors/fonts. Keep
  the built-in light/dark toggle unless the user wants a single theme.
- **Actors**: declare one entry per role in `ACTORS` — **one** window for a
  single-user feature, **two** for a pair, **three+** for multi-role. Colors are
  auto-assigned from a palette; the grid sizes itself to the count. Don't hardwire
  two — pick the number the feature actually has.
- **Scenarios tab**: define the `SCENARIOS` data — each is a titled user story
  with a `story` line, an `under` ("under the hood") line drawn from the plan,
  and ordered `steps`. Each step renders one window per role (via the step's
  `actors` map) and a synchronized "under the hood" panel; a bottom scenario-text
  panel is collapsible and expands **only into the free space below the block**,
  never over it.
- **Input-sandbox tab** (optional): a live composer for features with an
  input-routing/mode concept. The shipped example (pick recipient A/B via toggle
  + `/a`·`/b` + one-shot `@a`) is just one pattern — adapt to the feature's real
  input affordance, or delete the tab if there's no such concept.
- **Self-contained**: inline all CSS/JS, no external requests.

### Stage 7 — Verify in a browser and open

Never ship the page unseen. Use the project's browser-inspection tool
(`cloakbrowser`'s `inspect_page.py`, or `webapp-testing`) to screenshot the key
states and assert **no `PAGEERROR` / `CONSOLE[error]`**. Drive tab switches and
scenario steps via `--eval` to capture distinct states; settle CSS transitions
with a short delay before the screenshot. Read the screenshots, fix layout/logic
issues, re-verify. Then open it for the user (`wslview`/`xdg-open`/`open`).
Full recipe and the transition-artifact gotcha: `references/storyboard.md`.

## Output conventions

- Plan path: follow the project's convention (e.g. `todos/NNN-*.md` if the
  project uses numbered plan files).
- Page path: `<plan-basename>-user-stories.html` beside the plan.
- Respond in the user's language; keep code identifiers/paths verbatim.
- Don't commit unless asked; if the plan dir is git-excluded, say so.
