# Storyboard page — build & verify

Guidance for stages 6–7: turning an approved plan into the interactive
"user-stories storyboard" page, and verifying it in a browser. Start from
`assets/storyboard-template.html` — it is the canonical shape. Keep its engine
and structure; replace the **data**, the **theme tokens**, and (optionally) the
sandbox.

## What the page is

A single self-contained HTML file with a header (title + tabs + a theme toggle)
and two tabs:

- **Scenarios** — a stepper over user stories. The left panel lists scenarios;
  the right shows, per step: **one window per role** side by side (declare the
  roles in `ACTORS` — **one** for a single-user feature, **two** for a pair,
  **three+** for multi-role; the grid sizes to the count), a one-line
  **caption**, and an **"under the hood" panel** (a grid of cells showing the
  state/mechanism behind the visible step — server, client, external service,
  whatever the plan says). At the bottom is a **collapsible scenario-text
  panel**: collapsed by default to a thin bar; when expanded it grows **only into
  the free space below the block**, never covering the actor windows or the
  under-the-hood panel.
- **Input sandbox** (optional) — a live composer demonstrating an input/mode
  concept (the shipped example: choosing a recipient). Adapt to the feature's
  input affordance, or delete the tab entirely if there isn't one.

The page is a teaching tool: a stakeholder steps through a scenario and *sees*
the feature from each role's perspective, with the mechanism revealed beneath.

**Fit note.** The engine renders each window as a message feed, which suits
interaction/communication features. If the feature is a different shape (a form
wizard, a dashboard, a settings flow), keep the page's layout and the
under-the-hood panel, but rewrite `clientHTML` so each window shows that role's
screen/state rather than a chat feed. Don't force a chat metaphor onto a
non-chat feature just because the template ships one.

## Adapting the template

### 1. Theme tokens → product palette

The `:root` block holds the CSS tokens (background, panels, text, accent, etc.);
per-actor colors are auto-assigned from the `PALETTE` array by declaration order,
so you don't hand-pick them. Fill the tokens from the **product's own UI** so the
page reads as part of the app — open the product's stylesheet/Tailwind config or
screenshot a real screen and lift the palette (and, if you like, reorder
`PALETTE` to the product's accent hues). The template ships a dark default and a
`[data-theme]` light override plus a header toggle; keep both unless the user
wants one theme. Match the product's font stack too.

### 2. `SCENARIOS` data

Each scenario is an object keyed by id, listed in `ORDER`:

- `title`, `desc` — shown on the sidebar button.
- `story` — one-line user story ("As a …, I want …, so that …").
- `under` — one line on what happens under the hood, drawn from the plan's
  architecture/decisions (this is what makes the page honest).
- `steps[]` — ordered steps. Each step has:
  - `cap` — caption (may contain light HTML like `<b>`).
  - `actors` — a map keyed by the ids declared in `ACTORS`; one entry per role
    present in this step. Each holds `msgs` (built with the message constructors)
    plus optional flags: `online`, `presence`, `mode`, `typing`, `stop`,
    `closed`, `stale`. (How many keys = how many roles the feature has.)
  - `srv` — the under-the-hood cells: free-form keys the template renders, plus
    `note` (a sentence) and `hot` (array of cell-keys to highlight as "what
    changed this step").

Message constructors (top of the script) keep step data readable: `U(who, text)`
a person's line and `A(text, streaming)` a system line are generic; `T` (peer
line), `P` (queued) and `SI` (interrupted) are **examples** from a chat-like
feature — keep, rename, or drop them. Add constructors to fit the feature's own
message/event kinds; update the renderer's `if (m.type === …)` branches to match.

### 3. Sandbox (optional)

If the feature has an input-routing/mode concept worth letting the user *feel*,
keep the sandbox and adapt its parsing (the template demonstrates a sticky
toggle + inline commands + a one-shot prefix). If not, remove the second tab,
its panel, and its JS block.

### Keep it honest and self-contained

- Every `under`/`srv.note` should correspond to something real in the plan. The
  page's value is that the "under the hood" view matches the approved design.
- Inline all CSS/JS. No CDNs, no external fonts that block render — the page must
  work offline from `file://`.

## Verifying in a browser (stage 7)

Never hand over the page unseen — type-checks don't exist for a static HTML and
a silent JS error leaves a blank panel. Use the project's browser inspector.
With `cloakbrowser`:

```
python3 <cloakbrowser-skill-dir>/scripts/inspect_page.py \
  "file:///abs/path/to/page.html" --out /tmp/page-1.png --viewport 1320x900 \
  --wait 400 \
  --eval "async () => { /* drive to a state */ await new Promise(r=>setTimeout(r,400)); }"
```

Then `grep -iE 'PAGEERROR|CONSOLE\[error\]|SCREENSHOT'` the output and **Read**
the PNG.

Checklist:
- Screenshot the **default** state and each **distinct** state worth seeing:
  a couple of scenario steps, the expanded prompt panel, the sandbox after a few
  inputs, the light theme. Drive state changes inside `--eval` by calling the
  page's own handlers / clicking elements (`document.querySelector(...).click()`).
- Assert **no** `PAGEERROR` and **no** `CONSOLE[error]` lines.
- Read each screenshot and fix layout/logic before shipping.

### Gotchas

- **CSS transition artifact in screenshots.** Elements with a `transition` (tab
  highlight, panel expand) are mid-animation right after a click, so a screenshot
  taken immediately shows the *previous* state. Always settle with
  `await new Promise(r=>setTimeout(r, ~350ms))` inside the `--eval` before the
  shot. If a measurement looks "inverted", it's almost always this, not a bug —
  confirm by reading the DOM state (`classList`, `getComputedStyle`) rather than
  trusting the pixel.
- **Collapsible panel sizing.** The expand-into-free-space behavior relies on the
  content block having height-by-content (`flex:0 1 auto`) and the open panel
  growing with `flex:1 1 0` (basis 0) so it takes only the leftover space and
  never shrinks the block above it. If the panel eats the block, the open
  panel's flex-basis is wrong (it's demanding its content height) — set it to 0.
- **Opening for the user.** On WSL use `wslview <path>`; otherwise `xdg-open` /
  `open`. Re-run it after edits so the user gets the fresh file (browsers don't
  auto-reload `file://`); mention they can also just refresh (F5).

## Output

Write the page beside the plan as `<plan-basename>-user-stories.html`. After it's
verified, add the prominent link back in the plan (stage 5).
