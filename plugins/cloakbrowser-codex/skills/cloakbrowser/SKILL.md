---
name: cloakbrowser
description: >-
  Use a local stealth headless Chromium (CloakBrowser) to inspect web pages:
  screenshots, client-side JS errors with stack traces, console messages,
  failed network requests, JS injection, long-task/TBT measurement for
  UI-freeze and perf checks. Use proactively for client-side exceptions,
  "Application error" overlays, hydration/RSC issues — anything where the
  answer lives in DevTools rather than server logs. Triggers: "use
  cloakbrowser", "посмотри в браузере", "сделай скриншот", "check visually",
  "замерь фриз".
---

# CloakBrowser

Local stealth headless Chromium driven via the `cloakbrowser` Python package
(thin wrapper over Playwright). Use it instead of asking the user to paste
DevTools output — the cost is one `python3` invocation and a screenshot.

## When to reach for it (proactive)

- A user reports an `Application error: a client-side exception has
  occurred…` overlay → drive the page with `inspect_page.py` and grep the
  output for `PAGEERROR`/`CONSOLE[error]`.
- "What does the page look like" / visual review of a UI change → use
  `capture.py` for a screenshot before/after.
- Hydration mismatches, RSC errors, or any "works in Node, breaks in browser"
  bug — server logs won't show JS-side stack traces; CloakBrowser will.
- Smoke testing a freshly-rebuilt local app after a change (e.g. after
  `docker compose up`).

## Local tooling check

```bash
~/.local/bin/cloakbrowser info
# → reports Chromium version + cache path; "Installed: True" means ready.
```

If `Installed: False`, run `~/.local/bin/cloakbrowser install`
to download the stealth Chromium bundle (one-time, ~150MB).

## Two helper scripts

Both live under this skill's `scripts/` directory.

### `inspect_page.py` — the primary one

Opens a URL, listens for everything an agent would otherwise have to ask
about from DevTools, prints one event per line to stdout, and optionally
takes a screenshot. Exits non-zero if a `pageerror` fired.

Output format:

```
GOTO <url>
CONSOLE[<type>] <message>          # browser console.log/warn/error/...
PAGEERROR <Error object string>    # uncaught JS exception with stack
REQFAIL <method> <url> :: <reason> # network request failed
HTTP <status> <url>                # any response with status >= 400
NAVERROR <exception>               # navigation itself threw
CLICKERROR <exception>             # --click-selector failed
WAITSELECTOR ok <selector>         # --wait-selector matched (WAITSELECTORERROR on timeout)
TYPED <selector>                   # --type filled an input (TYPEERROR on failure)
EVAL <json>                        # --eval result of page.evaluate (EVALERROR on throw)
PERF count=… max=… total=… TBT=…ms # --measure-longtasks long-task summary
PERF dom_nodes=<N>                 # DOM node count at measure time
SCREENSHOT <path>                  # final screenshot saved
```

Typical client-side-error session:

```bash
python3 <skill-dir>/scripts/inspect_page.py \
    "http://localhost:8080/projects/<id>/chats/<id>?autorun=true" \
    --out /tmp/error.png --wait 3000
```

Then grep:

```bash
... | grep -E "PAGEERROR|CONSOLE\[error\]"
```

### `capture.py` — screenshot only

Wraps `page.goto` + `page.screenshot`. Use it for visual review without
needing console output.

```bash
python3 <skill-dir>/scripts/capture.py \
    http://localhost:8080/ \
    --out /tmp/page.png \
    --viewport 1440x900 \
    --wait 800 \
    [--click-selector "button[type=submit]"] \
    [--full-page]
```

Both scripts share these flags: `--viewport WxH` (default 1440x900),
`--wait MS` (post-nav delay), `--wait-until {load,domcontentloaded,networkidle,commit}`,
`--timeout MS`, `--click-selector`, `--full-page`.

### Capturing content inside scrolled containers (`inspect_page.py` only)

Chat surfaces, log panels, and any layout where content lives inside an
`overflow: auto` div with internal scroll defeat both viewport and
`--full-page` — the screenshot only captures whatever happens to be in
view at the moment. Two extra flags fix this:

- `--scroll-element SELECTOR --scroll-to top|bottom|PIXELS [--scroll-settle MS]` —
  programmatically `scrollTop=` on the matched element before screenshot.
  Defaults: `--scroll-to top`, `--scroll-settle 300` (ms for virtualized
  lists / smooth scroll to settle).

- `--find-scroller` — with `--scroll-element`, scroll the nearest element
  around it that actually scrolls when the named one does not, and print
  which one was scrolled. Without `--scroll-element`, list every vertically
  scrolling element on the page and scroll nothing.

- `--screenshot-element SELECTOR` — capture only this element's bounding
  box via `page.locator(SELECTOR).screenshot()`. Playwright auto-scrolls
  it into view first, so this also bypasses viewport size. Overrides
  `--full-page`.

```bash
# Scroll the chat container to the top so failed tool calls (which are at
# the start of a long assistant message) become visible:
python3 <skill-dir>/scripts/inspect_page.py \
    "$URL" --out /tmp/chat.png --wait 5000 \
    --scroll-element 'main' --scroll-to top --viewport 1600x1200
```

Read the scroll lines before trusting the screenshot. A selector often
matches a wrapper around the real scroller, and assigning `scrollTop` to a
non-scrolling element is accepted and does nothing.

- `SCROLLED <selector> -> <target> scrollTop <before> -> <after> (scrollHeight=… clientHeight=…)`
  — what moved, and by how much.
- `SCROLLWARN <selector> …` — nothing moved: the element does not scroll, or
  it was already where it was asked to go. The screenshot shows the same view
  as without the flag.
- `SCROLLER <selector> …` — an element nearby that does scroll. Re-run against
  it, or add `--find-scroller`.
- `SCROLLSUBST <asked> does not scroll; scrolled <selector>` — `--find-scroller`
  used a different element; the screenshot belongs to that element.
- `SCROLLERROR <msg>` — the selector matched nothing, or `--scroll-to` got a
  value that is neither `top`, `bottom`, nor a whole number of pixels.

### Measuring client-side perf & injecting JS (`inspect_page.py` only)

For verifying client-side performance fixes (e.g. UI freezes) or probing page
state, `inspect_page.py` can inject scripts and measure main-thread long tasks
without an ad-hoc Playwright script:

- `--measure-longtasks` — injects a `PerformanceObserver({entryTypes:['longtask']})`
  *before* navigation (so it catches initial render + hydration), then after the
  waits/actions prints `PERF count=… max=… total=… TBT=…ms` and `PERF dom_nodes=N`.
  TBT (Total Blocking Time) sums `duration - 50ms` over every long task — the
  standard main-thread responsiveness metric. A multi-second `max` ≈ a freeze.
- `--init-script FILE` — inject an arbitrary JS file via `context.add_init_script`
  before navigation (runs before page scripts on every frame). For custom probes.
- `--eval "JS"` (repeatable) — run `page.evaluate(JS)` after navigation/actions/
  scroll and print the JSON result as `EVAL <json>`. `JS` may be an expression or
  `() => …`.
- `--type SELECTOR TEXT` (repeatable) — `locator(SELECTOR).fill(TEXT)`, run after
  `--wait-selector` and before `--click-selector`. Use to trigger actions.
- `--wait-selector SELECTOR` — wait for `SELECTOR` to appear before typing/measuring.

Execution order: init-script → goto → `--wait-selector` → `--type` →
`--click-selector` → `--wait` → scroll → `--eval` → `--measure-longtasks` →
screenshot.

```bash
# Measure freezes during initial load AND a streamed chat response:
python3 <skill-dir>/scripts/inspect_page.py "$URL" \
    --cookie "name=authjs.session-token value=$TOKEN domain=localhost path=/" \
    --measure-longtasks \
    --wait-selector '[data-testid="multimodal-input"]' \
    --type '[data-testid="multimodal-input"]' 'List the tables in this database.' \
    --click-selector '[data-testid="send-button"]' \
    --wait 8000
# → PERF count=… max=…ms total=…ms TBT=…ms  /  PERF dom_nodes=…
```

## Auth-gated pages

CloakBrowser keeps a persistent profile under `~/.cloakbrowser/`. If the
user has already signed in through CloakBrowser earlier in the session, the
session cookie persists and you can hit protected URLs without re-auth — try
it first; if you get redirected to `/signin`, fall back to one of:

1. **Pass cookies explicitly** (uses Playwright's `add_cookies` API):

   ```bash
   python3 <skill-dir>/scripts/inspect_page.py \
       http://localhost:8080/private/page \
       --cookie "name=authjs.session-token value=<token> domain=localhost path=/"
   ```

2. **Ask the user to sign in via CloakBrowser once** (just open the dev login
   page with `inspect_page.py`, no automation needed — the profile catches
   it). Subsequent calls reuse the cookie.

Do **not** drive a credentialed sign-in flow programmatically without
explicit user permission — it would imply storing or handling credentials
that aren't yours to handle.

## Reading the screenshot

After capture, use the available image-viewing tool on the PNG path. Codex
renders images in context, so it can inspect the actual rendered UI (including
any red error overlay) without further round-trips.

```
view_image /tmp/error.png
```

## What this skill does NOT do

- Full end-to-end test automation (use a dedicated framework like
  `playwright test` for that — CloakBrowser is for *inspection*).
- Full performance profiling (CPU flamegraphs, Lighthouse audits) or
  accessibility scans — use Lighthouse/axe directly. (Main-thread long-task /
  TBT measurement *is* supported, via `--measure-longtasks` — see above.)
- Anything beyond a single page session — the script tears the browser
  down on exit.

## Common pitfalls

- CloakBrowser runs on the host, so it can only reach what the host can
  reach. Services bound to `127.0.0.1` inside a Docker container, or to a
  container's internal port that isn't published, are invisible — use
  `docker exec` (or a temporary port-publish) to inspect those.
