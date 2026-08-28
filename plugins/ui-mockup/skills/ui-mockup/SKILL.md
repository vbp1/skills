---
name: ui-mockup
description: >-
  Build a self-contained, clickable HTML mockup that closely matches THIS
  project's real UI, for design review before any real code is written. Use this
  whenever the user wants to SEE how a feature or UI change will look from the
  user's perspective: a "mockup", "clickable prototype", "interactive preview",
  "storyboard", "show me how it will look", or wants to compare design options
  for a product surface — even if they don't say the word "mockup". Produces a
  single portable HTML file themed with the project's actual design tokens, with
  a stepper to scrub through behaviour over time. NOT for production components
  (that's real code), NOT for backend-only work, and NOT for generic explainer
  diagrams.
---

# UI mockup (project-themed, clickable, single file)

## What this produces

One self-contained `.html` file (inline CSS + inline SVG + inline JS, no build, no
external deps beyond an optional web-font link) that looks like it was cut out of
the running app, and that the user can **click through** to watch a flow play out.
The point is a fast, throwaway, high-fidelity design review: the user sees the real
look and the real behaviour *before* anyone writes a component.

Two things make it land:

1. **It uses the project's real design tokens**, not approximations. The colors,
   radii, fonts and component shapes are copied from the codebase, so it reads as
   native and a stakeholder can judge the actual look.
2. **It's behavioural, not a single frame.** Most UI questions are about *change
   over time* — a list ticking off, a panel appearing, a state swapping. A stepper
   that scrubs through snapshots answers those in a way a static image can't.

## Workflow

Work top to bottom, but loop on steps 4–6 until it looks right.

### 1. Pin down the scenario(s) and the behaviour to show

A mockup is only as good as the moment it captures. Before touching HTML, get
concrete about: which surface(s) of the app, which user or role, and **what changes
on screen** across the flow (what appears, advances, swaps, disappears). If the
behaviour has product forks the user hasn't decided ("does the panel stay or
disappear when X?"), surface them in plain language via `AskUserQuestion` — those
decisions *are* the mockup. One flow per scenario; offer a second scenario (a tab)
only when it teaches something the first can't.

**Ask where the running product is reachable, before step 3.** Put the question to
the user with `AskUserQuestion`; record the answer and reuse it for the rest of the
task without asking again. When that address does not answer, does not let you in,
or the surfaces you need are missing from it, STOP and ask the user — never fall
back to drawing from the source code alone.

### 2. Extract the project's real theme tokens — copy them verbatim

This is what separates an authentic mockup from a generic one. Read the token
source and paste the actual values in; do not eyeball colors. Fill in
[references/project-ui.md](references/project-ui.md) once per project — it is the
place that records where the tokens, fonts and component anchors live — and keep it
current.

The skeleton ships with a **placeholder palette** so it renders before you have
filled anything in. Replace it with the project's own tokens (both the light and the
dark block, so the theme toggle keeps working) and trim to the variables you use.

### 3. Study the real layout of the surfaces you're mocking

So the mockup *shapes* match, not just the palette. Don't guess the markup — read
it. Grep the project's component directory for the surfaces in scope and note the
real container widths, row and bubble structure, icon usage, and any per-element
rendering you need to mirror. Mirroring real class intent (a centered narrow
column, a fixed avatar size, a monospace identifier, pill badges) is what makes it
feel native.

**Reading the code is half of it — open every surface in the running product and
capture it.** For each surface in scope, at the address from step 1: sign in,
navigate to it, screenshot it, and pull the `outerHTML` of the elements you will
mirror. Capture each state you intend to draw (empty / in progress / failed /
expanded / the dialog open), and the page chrome around the surface (header, tabs,
column widths). Keep the shots in a scratch directory, one file per surface and
state, and read every image. A surface you could not reach live is a blocker for
step 5 — take it to the user.

### 4. Assemble the single file from the skeleton

Start from [assets/mockup-skeleton.html](assets/mockup-skeleton.html) — copy it to
your target path (a throwaway location, or next to a plan document if it documents
one) and fill in the scenario. The skeleton already implements the reusable
machinery so you don't reinvent it:

- **Scrubbable snapshots.** Build state by mutation and call `snap()` after each
  visible change; each snapshot is a deep copy. The stepper renders any frame, so
  the user can scrub forward and back and you can screenshot any moment. Build a
  flow inside a `buildX()` function that resets state, mutates and snaps step by
  step, and returns the frames. This is the core pattern — lean on it.
- **Generic controls, already wired:** play / step / reset / previous / next (and
  the arrow keys), a light-dark toggle, and scenario tabs. You write
  `render(frame)` for your domain and the `buildX()` scenarios; leave the controls
  alone. The skeleton also follows a parent wrapper's theme and announces its
  active scenario via `postMessage` (both harmless standalone) — this lets an
  embedding annotation wrapper, such as the one `taskflow` builds, scope its pins
  to the screen on show.
- **UI-only state stays out of the snapshots.** Things like "is the panel
  expanded" or "which theme" are view state the user toggles — keep them in plain
  variables so they survive scrubbing, and don't bake them into frames.
- **Optional per-step caption + "under the hood" panel.** A mockup answers *what
  the user sees*; for flows where the *why* matters, pair each step with a one-line
  caption and a synced commentary panel showing the mechanism beneath — what gets
  computed, saved or decided this step. The skeleton renders both from each frame
  (`caption` / `under`) and hides them when empty, so a plain mockup stays plain
  and a teaching mockup also explains itself.

Conventions that keep it honest and useful:

- **Keep it honest.** Every caption and "under the hood" note must match real
  behaviour in the code (or the agreed design for unbuilt work) — a mockup that
  looks authoritative while showing a flow the system doesn't do is worse than
  none.
- **Separate the demo controls from the product UI.** The stepper bar, tabs, intro
  banner and any commentary are scaffolding, not part of the product — style them
  distinctly (a floating pill, a dashed banner) so no one mistakes them for the
  real design.
- **Inline icons** via the `svg(name)` helper, in the icon family the product uses;
  add paths to the `ICON` map as needed.
- **Add kebab-case `data-testid`** to the elements a real implementation would
  expose (panels, items, toggles), scoped by surface — it mirrors the usual e2e
  convention and lets a future spec target the same handles.
- **Self-contained.** Everything inline. The only allowed external reference is a
  web-font link with a system fallback, so it still renders offline.

### 5. Reconcile the mockup against the running product

Mandatory for every surface that already exists. Put each mockup frame next to the
live shot of the same surface and state, walk the *What usually diverges* checklist
in [references/project-ui.md](references/project-ui.md) over it, and produce a
two-column table — "in the product" / "in the mockup" — with one row per difference
found.

- **Fix every row** where the mockup draws something the product already does
  differently: wording of buttons and labels, date and duration formats, what
  surrounds a message, state colors and icons, column contents, container width,
  the page header and its tabs.
- **Keep the deliberate differences as their own short list**, one sentence each
  saying what is new and why it looks unlike anything on screen today. Present that
  list to the user when you hand over the mockup, so each deliberate difference is
  confirmed rather than assumed.
- **Re-capture the mockup frames after fixing** and compare again, until the table
  holds only deliberate rows.
- Record both lists where the caller keeps them (a taskflow task file's mockups
  section, otherwise your hand-over message).

### 6. Verify in the browser, in both themes — iterate

Type-checks don't exist here; *looking* is the test. Drive the file with whatever
browser tool you have: shoot the key frames (advance the stepper and toggle theme
and tabs before each shot) and confirm there are **no page or console errors**.
Check light and dark. Fix layout collisions and re-shoot. One gotcha worth knowing:
elements with a CSS `transition` are mid-animation right after a click, so a shot
taken immediately captures the *previous* frame — settle ~350 ms before shooting,
and trust the DOM state over the pixel if something looks inverted.

### 7. Open it for the user

Open the file with the platform's opener: `xdg-open` on Linux, `open` on macOS,
`wslview` (or `explorer.exe`) under WSL. Tell the user the controls (play / step /
arrow keys / theme toggle / tabs) and that they should refresh the page if a tab is
already open after you edit the file.

## Pointers

- [assets/mockup-skeleton.html](assets/mockup-skeleton.html) — copy this to start;
  the snapshot stepper, controls and a placeholder palette are already in it.
- [references/project-ui.md](references/project-ui.md) — fill this in per project:
  where the tokens and fonts live, which components to mirror, what usually
  diverges, and how to reach the running product.

## Relation to other skills

Reach for this when the deliverable is a **fast, high-fidelity, clickable preview of
a single product surface** themed like the real app — not tied to a plan document or
to multiple roles.

- `taskflow` calls this skill at its stories step and wraps the result in an
  annotation shell so the user can pin comments on it.
- Diagram skills explain a system; this one mimics the product.
- Prototype and playground skills explore non-product-themed UI.

Those explain or explore; this one mimics the real product so closely a stakeholder
can sign off on the look and the flow.
