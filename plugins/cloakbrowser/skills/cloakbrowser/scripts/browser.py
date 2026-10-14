"""Browser launch shared by the helper scripts.

Two engines:

- ``chromium`` (default): the stock Playwright Chromium, current with the
  installed ``playwright`` package. Install it once with
  ``python3 -m playwright install chromium``.
- ``cloak``: the CloakBrowser stealth Chromium, for pages that must not see an
  automated browser. Needs the ``cloakbrowser`` package and its binary.
"""

from __future__ import annotations

import argparse
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

ENGINES = ('chromium', 'cloak')

# Keys Playwright's add_cookies accepts, and the ones that are not plain strings.
COOKIE_KEYS = ('name', 'value', 'url', 'domain', 'path', 'expires', 'httpOnly', 'secure', 'sameSite')
COOKIE_BOOL_KEYS = ('httpOnly', 'secure')
COOKIE_SAME_SITE = ('Strict', 'Lax', 'None')
COOKIE_MAX_EXPIRES = 253402300799  # Playwright's kMaxCookieExpiresDateInSeconds


def parse_cookie(value: str) -> dict:
    """Parse a `key=value key2=value2` string into a Playwright-style cookie dict."""
    out: dict = {}
    for part in value.split():
        if '=' not in part:
            raise argparse.ArgumentTypeError(f'cookie part must be key=value: {part!r}')  # noqa: TRY003
        k, v = part.split('=', 1)
        if k in out:
            raise argparse.ArgumentTypeError(f'cookie key {k!r} given twice')  # noqa: TRY003
        if k not in COOKIE_KEYS:
            raise argparse.ArgumentTypeError(  # noqa: TRY003
                f'unknown cookie key {k!r}; expected one of {", ".join(COOKIE_KEYS)}')
        if k in COOKIE_BOOL_KEYS:
            if v not in ('true', 'false'):
                raise argparse.ArgumentTypeError(  # noqa: TRY003
                    f'cookie {k} got {v!r}; expected true or false')
            out[k] = v == 'true'
        elif k == 'expires':
            try:
                expires = float(v)
            except ValueError:
                expires = None
            if expires is None or not (expires == -1 or 0 <= expires <= COOKIE_MAX_EXPIRES):
                raise argparse.ArgumentTypeError(  # noqa: TRY003
                    f'cookie expires got {v!r}; expected -1 (session cookie) or a Unix '
                    f'timestamp in seconds from 0 to {COOKIE_MAX_EXPIRES}')
            out[k] = expires
        elif k == 'sameSite':
            if v not in COOKIE_SAME_SITE:
                raise argparse.ArgumentTypeError(  # noqa: TRY003
                    f'cookie sameSite got {v!r}; expected one of {", ".join(COOKIE_SAME_SITE)}')
            out[k] = v
        else:
            out[k] = v
    for required in ('name', 'value'):
        if required not in out:
            raise argparse.ArgumentTypeError(f"cookie must include '{required}'")  # noqa: TRY003
    # The same placement rules Playwright's add_cookies enforces, checked here so a
    # bad cookie fails before the browser starts.
    if 'url' in out:
        if 'domain' in out or 'path' in out:
            raise argparse.ArgumentTypeError(  # noqa: TRY003
                'cookie takes either url or domain+path, not both')
    elif 'domain' not in out or 'path' not in out:
        raise argparse.ArgumentTypeError(  # noqa: TRY003
            'cookie must include url, or both domain and path')
    return out


def add_context_arguments(parser: argparse.ArgumentParser) -> None:
    """Options that shape the browser context: cookies and certificate checks."""
    parser.add_argument(
        '--cookie',
        action='append',
        type=parse_cookie,
        metavar='"name=… value=… domain=… path=… [secure=true] [httpOnly=true]"',
        help='Repeatable. Add cookies before navigation (e.g. for auth-gated pages). '
        'Keys: name, value, url, domain, path, expires (Unix seconds), '
        'httpOnly and secure (true|false), sameSite (Strict|Lax|None).',
    )
    parser.add_argument(
        '--ignore-https-errors',
        action='store_true',
        help='Accept invalid TLS certificates (self-signed local stands). Off by default.',
    )


def add_engine_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        '--engine',
        choices=ENGINES,
        default='chromium',
        help='Browser to drive: "chromium" (default) — stock Playwright Chromium; '
        '"cloak" — CloakBrowser stealth Chromium, for sites that block automated browsers.',
    )


@asynccontextmanager
async def open_browser(engine: str) -> AsyncIterator:
    if engine == 'cloak':
        import cloakbrowser

        browser = await cloakbrowser.launch_async(headless=True)
        try:
            yield browser
        finally:
            await browser.close()
        return

    if engine != 'chromium':
        raise ValueError(f'unknown engine {engine!r}; expected one of {", ".join(ENGINES)}')  # noqa: TRY003

    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            await browser.close()
