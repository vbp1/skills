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
