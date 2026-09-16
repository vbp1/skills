#!/usr/bin/env python3
"""Open a URL in cloakbrowser and capture all browser-side signals an agent
would otherwise have to ask the user for from DevTools: console messages,
page errors with stack traces, failed network requests, and a screenshot of
the rendered page (useful when the app shows an error overlay).

Output is plain text, one line per event, prefixed with the event kind so
the caller can grep/parse. Final screenshot path is printed on the last line
as ``SCREENSHOT <path>``.

Example::

    python3 inspect.py http://localhost:8080/some/page \
        --out /tmp/page.png \
        --wait 3000

With auth cookies::

    python3 inspect.py http://localhost:8080/private \
        --cookie name=session value=abc123 domain=localhost path=/ \
        --cookie name=other value=xyz domain=localhost path=/

Measuring a client-side perf fix (main-thread long tasks) — wait for the
input, type a prompt, click send, watch for long tasks during streaming::

    python3 inspect.py http://localhost:8080/chat \
        --measure-longtasks \
        --wait-selector '[data-testid="multimodal-input"]' \
        --type '[data-testid="multimodal-input"]' 'List the tables.' \
        --click-selector '[data-testid="send-button"]' \
        --wait 8000 \
        --eval '() => document.querySelectorAll("*").length'
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import cloakbrowser

VIEWPORT_PARTS = 2
LONGTASK_THRESHOLD_MS = 50

# Injected before page scripts (via add_init_script) so the PerformanceObserver
# is active from the very first frame and catches long tasks during initial
# render, hydration, and any later actions. Results accumulate on window.__lt.
LONGTASK_INIT = """
(() => {
  window.__lt = [];
  try {
    const obs = new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        window.__lt.push({start: Math.round(e.startTime), dur: Math.round(e.duration)});
      }
    });
    obs.observe({entryTypes: ['longtask']});
  } catch (e) { window.__ltErr = String(e); }
})();
"""

# CloakBrowser suppresses the CDP Runtime events that Playwright normally uses
# for page.on('console') and page.on('pageerror'). Capture the same signals in
# the page before application scripts run, then read the buffer at the end.
BROWSER_SIGNALS_INIT = r"""
(() => {
  const signals = [];
  Object.defineProperty(window, '__cloakbrowserSignals', {value: signals});

  const render = (value) => {
    if (typeof value === 'string') return value;
    if (value instanceof Error) return value.stack || value.message;
    try {
      const json = JSON.stringify(value);
      return json === undefined ? String(value) : json;
    } catch (_) {
      return String(value);
    }
  };

  for (const level of ['log', 'debug', 'info', 'warn', 'error']) {
    const original = console[level];
    console[level] = (...args) => {
      signals.push({kind: 'console', level, text: args.map(render).join(' ')});
      return Reflect.apply(original, console, args);
    };
  }

  addEventListener('error', (event) => {
    const text = event.error?.stack || event.message;
    if (text) signals.push({kind: 'pageerror', text});
  }, true);
  addEventListener('unhandledrejection', (event) => {
    signals.push({kind: 'pageerror', text: render(event.reason)});
  });
})();
"""

BROWSER_SIGNALS_READ = "() => window.__cloakbrowserSignals || []"


# Scrolls a container and reports what actually happened. A selector can match an
# element that is not the scroller (a wrapper around the scrolling div), and then
# `el.scrollTop = N` is accepted and does nothing; this returns the measurements
# that show it, plus the scrollable elements near the target.
SCROLL_JS = """
(args) => {
  const path = (el) => {
    if (!el) return null;
    if (el === document.documentElement) return ':root';
    if (el === document.body) return 'body';
    if (el.id) return '#' + CSS.escape(el.id);
    const cls = (el.getAttribute('class') || '').trim().split(/\\s+/)
      .filter(Boolean).slice(0, 3).map((c) => '.' + CSS.escape(c)).join('');
    return el.tagName.toLowerCase() + cls;
  };
  const scrollable = (el) => {
    const overflow = getComputedStyle(el).overflowY;
    return /(auto|scroll|overlay)/.test(overflow) && el.scrollHeight - el.clientHeight > 1;
  };
  const measure = (el) => ({
    selector: path(el),
    scrollTop: Math.round(el.scrollTop),
    scrollHeight: el.scrollHeight,
    clientHeight: el.clientHeight,
    overflowY: getComputedStyle(el).overflowY,
    scrollable: scrollable(el),
  });

  if (!args.sel) {
    const all = Array.from(document.querySelectorAll('*')).filter(scrollable);
    all.sort((a, b) => b.scrollHeight - a.scrollHeight);
    return {found: true, candidates: all.slice(0, 10).map(measure), applied: null};
  }

  const el = document.querySelector(args.sel);
  if (!el) return {found: false, selector: args.sel};

  const near = [];
  for (let p = el.parentElement; p; p = p.parentElement) {
    if (scrollable(p)) { near.push(p); break; }
  }
  for (const d of el.querySelectorAll('*')) {
    if (scrollable(d)) { near.push(d); if (near.length >= 4) break; }
  }

  const chosen = scrollable(el) ? el : (args.find && near.length ? near[0] : el);
  const before = measure(chosen);
  const value = args.target === 'top' ? 0
    : args.target === 'bottom' ? chosen.scrollHeight
    : parseInt(args.target, 10);
  chosen.scrollTop = value;
  const after = measure(chosen);
  return {
    found: true,
    requested: measure(el),
    applied: {before, after, substituted: chosen !== el, wanted: value},
    candidates: near.map(measure),
  };
}
"""


def write_scroll_report(args: argparse.Namespace, report: dict) -> None:
    """Print what the scroll did, and say so when it did nothing."""
    if not report.get('found'):
        sys.stdout.write(f'SCROLLERROR scroll-element not found: {report.get("selector")}\n')
        return

    def describe(m: dict) -> str:
        return (f'{m["selector"]} scrollTop={m["scrollTop"]} scrollHeight={m["scrollHeight"]} '
                f'clientHeight={m["clientHeight"]} overflow-y={m["overflowY"]}')

    applied = report.get('applied')
    if applied is None:
        found = report.get('candidates') or []
        sys.stdout.write(f'SCROLLERS {len(found)}\n')
        for m in found:
            sys.stdout.write(f'SCROLLER {describe(m)}\n')
        if not found:
            sys.stdout.write('SCROLLWARN no element on the page scrolls vertically\n')
        return

    before, after = applied['before'], applied['after']
    where = args.scroll_element
    if applied['substituted']:
        # --find-scroller was asked for and the named element does not scroll:
        # report the element that was actually scrolled, under its own name.
        sys.stdout.write(f'SCROLLSUBST {where} does not scroll; scrolled {after["selector"]}\n')
    sys.stdout.write(f'SCROLLED {after["selector"]} -> {args.scroll_to or "top"} '
                     f'scrollTop {before["scrollTop"]} -> {after["scrollTop"]} '
                     f'(scrollHeight={after["scrollHeight"]} clientHeight={after["clientHeight"]})\n')

    if before['scrollTop'] == after['scrollTop'] and after['scrollTop'] != applied['wanted']:
        if not after['scrollable']:
            sys.stdout.write(
                f'SCROLLWARN {after["selector"]} does not scroll vertically '
                f'(overflow-y={after["overflowY"]}, scrollHeight={after["scrollHeight"]} '
                f'<= clientHeight={after["clientHeight"]}); the screenshot is unchanged\n')
        else:
            sys.stdout.write(
                f'SCROLLWARN {after["selector"]} did not move; asked for '
                f'{applied["wanted"]}, stayed at {after["scrollTop"]}\n')
        for m in report.get('candidates') or []:
            sys.stdout.write(f'SCROLLER {describe(m)}\n')
        if not report.get('candidates'):
            sys.stdout.write('SCROLLER none near it; run with --find-scroller and no '
                             '--scroll-element to list every scroller on the page\n')


def summarize_longtasks(entries: list) -> str:
    """One-line summary of PerformanceObserver longtask entries.

    TBT (Total Blocking Time) sums the blocking portion (duration - 50ms) of
    every long task, the standard main-thread responsiveness metric.
    """
    if not entries:
        return 'count=0 max=0ms total=0ms TBT=0ms'
    durs = sorted((int(e['dur']) for e in entries), reverse=True)
    tbt = sum(d - LONGTASK_THRESHOLD_MS for d in durs if d > LONGTASK_THRESHOLD_MS)
    return (f'count={len(durs)} max={durs[0]}ms total={sum(durs)}ms '
            f'TBT={tbt}ms top5={durs[:5]}')


async def write_browser_signals(page) -> bool:
    """Print buffered console/page errors from the page and all live frames."""
    had_pageerror = False
    for frame in page.frames:
        try:
            signals = await frame.evaluate(BROWSER_SIGNALS_READ)
        except Exception:
            continue
        for signal in signals:
            if signal.get('kind') == 'console':
                sys.stdout.write(
                    f'CONSOLE[{signal.get("level", "log")}] {signal.get("text", "")}\n')
            elif signal.get('kind') == 'pageerror':
                had_pageerror = True
                sys.stdout.write(f'PAGEERROR {signal.get("text", "")}\n')
    return had_pageerror


def parse_viewport(value: str) -> tuple[int, int]:
    parts = value.lower().split('x', 1)
    if len(parts) != VIEWPORT_PARTS:
        raise argparse.ArgumentTypeError('viewport must use WIDTHxHEIGHT format')
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError('viewport values must be integers') from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError('viewport values must be positive')
    return width, height


def parse_cookie(value: str) -> dict:
    """Parse a `key=value key2=value2` string into a Playwright-style cookie dict."""
    out = {}
    for part in value.split():
        if '=' not in part:
            raise argparse.ArgumentTypeError(f'cookie part must be key=value: {part!r}')
        k, v = part.split('=', 1)
        out[k] = v
    for required in ('name', 'value'):
        if required not in out:
            raise argparse.ArgumentTypeError(f"cookie must include '{required}'")
    return out


async def inspect(args: argparse.Namespace) -> int:
    width, height = args.viewport
    out_path = Path(args.out).expanduser().resolve() if args.out else None
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)

    browser = await cloakbrowser.launch_async(headless=True)
    exit_code = 0
    try:
        context = await browser.new_context(viewport={'width': width, 'height': height})
        if args.cookie:
            await context.add_cookies(args.cookie)
        await context.add_init_script(BROWSER_SIGNALS_INIT)
        # Init scripts run before any page script on every new page/frame, so
        # they must be registered before the page is created (and thus before
        # goto) to capture the earliest activity.
        if args.measure_longtasks:
            await context.add_init_script(LONGTASK_INIT)
        if args.init_script:
            init_path = Path(args.init_script).expanduser().resolve()
            if not init_path.is_file():
                sys.stderr.write(f'init-script not found: {init_path}\n')
                return 3
            await context.add_init_script(path=str(init_path))
        page = await context.new_page()

        def on_requestfailed(req):
            sys.stdout.write(f'REQFAIL {req.method} {req.url} :: {req.failure}\n')

        def on_response(resp):
            if resp.status >= 400:
                sys.stdout.write(f'HTTP {resp.status} {resp.url}\n')

        page.on('requestfailed', on_requestfailed)
        page.on('response', on_response)

        sys.stdout.write(f'GOTO {args.url}\n')
        try:
            await page.goto(args.url, wait_until=args.wait_until, timeout=args.timeout)
        except Exception as exc:
            sys.stdout.write(f'NAVERROR {exc}\n')
            exit_code = 2

        if args.wait_selector:
            try:
                await page.wait_for_selector(args.wait_selector, timeout=args.timeout)
                sys.stdout.write(f'WAITSELECTOR ok {args.wait_selector}\n')
            except Exception as exc:
                sys.stdout.write(f'WAITSELECTORERROR {exc}\n')

        if args.type:
            for sel, text in args.type:
                try:
                    await page.locator(sel).fill(text)
                    sys.stdout.write(f'TYPED {sel}\n')
                except Exception as exc:
                    sys.stdout.write(f'TYPEERROR {sel} :: {exc}\n')

        if args.click_selector:
            try:
                await page.click(args.click_selector, timeout=args.timeout)
            except Exception as exc:
                sys.stdout.write(f'CLICKERROR {exc}\n')

        if args.wait:
            await page.wait_for_timeout(args.wait)

        # Programmatic scroll inside an overflow:auto/scroll container before
        # screenshot. The chat surface (and many SPA panels) put their content
        # in a fixed-height container with internal scroll, so neither viewport
        # nor --full-page captures the off-screen rows. This lets the caller
        # scroll the container itself; pass `top`, `bottom`, or a pixel offset.
        if args.scroll_element or args.find_scroller:
            try:
                target = args.scroll_to or 'top'
                if target not in ('top', 'bottom'):
                    try:
                        int(target)  # checked before the page is touched
                    except ValueError:
                        raise ValueError(
                            f'--scroll-to got {target!r}; expected "top", "bottom", '
                            f'or a whole number of pixels') from None
                report = await page.evaluate(SCROLL_JS, {
                    'sel': args.scroll_element,
                    'target': target,
                    'find': bool(args.find_scroller),
                })
                # Settle: give virtualized lists / smooth scroll handlers time.
                if report.get('applied'):
                    await page.wait_for_timeout(args.scroll_settle)
                write_scroll_report(args, report)
            except Exception as exc:
                sys.stdout.write(f'SCROLLERROR {exc}\n')

        if args.eval:
            for js in args.eval:
                try:
                    result = await page.evaluate(js)
                    sys.stdout.write(f'EVAL {json.dumps(result, ensure_ascii=False, default=str)}\n')
                except Exception as exc:
                    sys.stdout.write(f'EVALERROR {exc}\n')

        if args.measure_longtasks:
            try:
                data = await page.evaluate(
                    "() => ({lt: window.__lt || [], err: window.__ltErr || null,"
                    " nodes: document.querySelectorAll('*').length})")
                if data.get('err'):
                    sys.stdout.write(f'PERF obs_error {data["err"]}\n')
                sys.stdout.write(f'PERF {summarize_longtasks(data.get("lt", []))}\n')
                sys.stdout.write(f'PERF dom_nodes={data.get("nodes")}\n')
            except Exception as exc:
                sys.stdout.write(f'PERFERROR {exc}\n')

        if await write_browser_signals(page):
            exit_code = 1

        if out_path is not None:
            if args.screenshot_element:
                # Locator.screenshot auto-scrolls the element into view and
                # captures only its bounding box — bypasses viewport limits.
                try:
                    await page.locator(args.screenshot_element).screenshot(path=str(out_path))
                except Exception as exc:
                    sys.stdout.write(f'SCREENSHOTERROR {exc}\n')
                    return exit_code or 4
            else:
                await page.screenshot(path=str(out_path), full_page=args.full_page)
            sys.stdout.write(f'SCREENSHOT {out_path}\n')

    finally:
        await browser.close()

    return exit_code


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('url')
    p.add_argument('--out', help='Screenshot output path. Omit to skip screenshot.')
    p.add_argument('--viewport', type=parse_viewport, default=(1440, 900), metavar='WxH')
    p.add_argument('--wait', type=int, default=2000, help='ms to wait after navigation (default: 2000)')
    p.add_argument('--wait-until', default='networkidle', choices=('load', 'domcontentloaded', 'networkidle', 'commit'))
    p.add_argument('--timeout', type=int, default=30000, help='ms')
    p.add_argument('--click-selector')
    p.add_argument('--full-page', action='store_true')
    p.add_argument(
        '--scroll-element',
        metavar='SELECTOR',
        help='Before screenshot, scroll this element (e.g. a div with overflow:auto). '
        'Combine with --scroll-to. Useful when chat/log surfaces have their own '
        'internal scrollbar that viewport/--full-page does not cover.',
    )
    p.add_argument(
        '--scroll-to',
        metavar='top|bottom|PIXELS',
        help='Where to scroll --scroll-element. "top" (default), "bottom", or an integer pixel offset.',
    )
    p.add_argument(
        '--find-scroller',
        action='store_true',
        help='With --scroll-element: when that element does not scroll, scroll the '
        'nearest element around it that does, and print which one it was. '
        'Without --scroll-element: print every vertically scrolling element on the '
        'page and scroll nothing.',
    )
    p.add_argument(
        '--scroll-settle',
        type=int,
        default=300,
        metavar='MS',
        help='ms to wait after scrolling for virtualized lists / smooth scroll (default: 300)',
    )
    p.add_argument(
        '--screenshot-element',
        metavar='SELECTOR',
        help='Capture only the bounding box of this element instead of the viewport. '
        'Playwright auto-scrolls the element into view first, so this bypasses '
        'viewport size and outer scroll constraints. Overrides --full-page.',
    )
    p.add_argument(
        '--cookie',
        action='append',
        type=parse_cookie,
        metavar='"name=… value=… domain=… path=…"',
        help='Repeatable. Add cookies before navigation (e.g. for auth-gated pages).',
    )
    p.add_argument(
        '--init-script',
        metavar='FILE',
        help='Inject a JS file via context.add_init_script before navigation '
        '(runs before page scripts on every frame). Use for custom instrumentation.',
    )
    p.add_argument(
        '--measure-longtasks',
        action='store_true',
        help='Inject a PerformanceObserver for main-thread long tasks before '
        'navigation; after waits/actions print "PERF count/max/total/TBT(ms)" and '
        '"PERF dom_nodes=N". For verifying client-side perf fixes (e.g. UI freezes).',
    )
    p.add_argument(
        '--eval',
        action='append',
        metavar='JS',
        help='Repeatable. Run page.evaluate(JS) after navigation/actions/scroll and '
        'print the JSON result prefixed "EVAL". JS may be an expression or "() => …".',
    )
    p.add_argument(
        '--type',
        action='append',
        nargs=2,
        metavar=('SELECTOR', 'TEXT'),
        help='Repeatable. Fill SELECTOR with TEXT (locator.fill) after --wait-selector '
        'and before --click-selector. Use to trigger actions (type a prompt, then send).',
    )
    p.add_argument(
        '--wait-selector',
        metavar='SELECTOR',
        help='After navigation, wait for SELECTOR to appear (page.wait_for_selector) '
        'before typing/measuring.',
    )
    args = p.parse_args()
    return asyncio.run(inspect(args))


if __name__ == '__main__':
    raise SystemExit(main())
