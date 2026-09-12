# Project UI reference

Fill this file in once per project, then keep it current. Everything in angle
brackets is a blank to replace; the checklists below are project-independent and are
meant to be used as they are.

## Design tokens (the source of the look)

- **Token source: `<path to the file that defines the design tokens>`** — copy the
  variables you need verbatim into the mockup's `<style>`, both the light and the
  dark block so the theme toggle works. Record here which names carry the
  background, the foreground, the surface, the brand color, the muted pair, the
  border, the focus ring, the destructive / success / warning colors, and the
  radius.
- **Component-library config: `<path, if the project uses one>`** — style, base
  color, icon family, aliases. This is what tells you which component vocabulary
  the mockup should imitate.
- **Fonts: `<sans>` and `<mono>`** — where they are declared, and the web-font URL
  to load in the mockup with a system fallback so it renders offline.
- **Customized components: `<list>`** — the ones whose look departs from the
  library defaults, so a mockup that draws them copies the project's version.

## Component anchors (study before mirroring)

List the files worth reading before drawing each surface. One line each: the
surface, its file, and the two or three facts that make it look like itself.

- `<surface>` — `<path>` — `<container width, row structure, icon usage>`
- `<surface>` — `<path>` — `<…>`

Mirror the *intent* of the real classes (widths, radii, icon sizes, pill shapes),
not every utility. The goal is "looks cut from the app", not pixel-exact.

## Reaching the running product

- **Address:** ask the user; the answer belongs in the caller's task file, not here.
- **Signing in:** `<how, and with which test account>`.
- **Navigating to each surface:** `<the path, or the clicks>`.
- **Noise to ignore:** `<requests that always fail and mean nothing>`.

## What usually diverges (walk this list at SKILL step 5)

Capture each surface twice over: the rendered image, and the `outerHTML` of the
element you mirror — read the real classes and the literal strings out of the markup
rather than inferring them from the component source. Then check each line against
the capture, per surface and per state:

- **Button and menu wording** — the literal caption ("Cancel", not "Stop").
- **Duration format** — how the product spells an elapsed time, and whether the row
  form differs from the card form.
- **Date and time format** — full date vs time only, per column and per surface.
- **What surrounds a message or a row** — author name, avatar, timestamp,
  alignment, background per role.
- **Which element owns a block** — a report as its own indented row vs part of the
  answer above it; an error as its own row vs a paragraph.
- **State icons and colors** — whether a waiting card shows a status icon at all;
  which color means "running".
- **Table columns** — what each column actually holds and its header wording.
- **Container width** — full-width region vs centered narrow column.
- **Page chrome** — the header above the surface and its tab strip.
- **App frame** — the left menu (every item, its order, its grouping, the badge
  counts, which one is active), the top bar and what sits in it (logo, project
  switcher, status, avatar). The frame is product UI and is drawn around every
  surface; a logo or illustration comes from the product's own image file, embedded
  as a `data:` URI.
- **Empty, loading and failure states** — all three, not just the happy frame.

## Verifying the mockup itself

Looking is the test — there are no type-checks here. Any browser tool does; what has
to come out of it:

- **No page errors and no console errors**, on every scenario of the list.
- **Both themes**, light and dark — the review column follows the theme too.
- **Every frame you intend to show** — advance the stepper to it before the shot
  rather than shooting the first frame only.
- **The column collapsed**, so the screen can be judged on its own.
- **Scroll and pinning behaviour** wherever the surface has a scrolling region.
- Read the resulting image; fix layout collisions (a product dialog or toast that
  escapes the mockup area over the column belongs in `.mk-stage` with
  `position: absolute`) and re-shoot.

**CSS-transition gotcha.** Elements with a `transition` (theme highlight, chevron
rotate, panel expand) are mid-animation right after a click, so a shot taken
immediately captures the *previous* state. Settle ~350 ms after the click before
shooting. When a state looks inverted in the image, confirm against the DOM
(`classList`, `getComputedStyle`) before assuming a bug.

## Conventions

- **`data-testid`**: kebab-case, scoped by surface (e.g. `task-checklist`,
  `task-checklist-item`, `task-checklist-toggle`), matching the project's e2e rule so
  a future spec can target the same handles.
- **Where to put the file**: throwaway → a scratch directory; documents a plan →
  next to it.
- **Plain-language product forks**: when the mockup exposes an undecided product
  question, ask it with `AskUserQuestion` in everyday words — the user is judging the
  *experience*, not the implementation.
