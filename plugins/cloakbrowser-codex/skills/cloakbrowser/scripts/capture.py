#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import cloakbrowser

VIEWPORT_PARTS = 2


def parse_viewport(value: str) -> tuple[int, int]:
    parts = value.lower().split('x', 1)
    if len(parts) != VIEWPORT_PARTS:
        raise argparse.ArgumentTypeError('viewport must use WIDTHxHEIGHT format')  # noqa: TRY003
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError('viewport values must be integers') from exc  # noqa: TRY003
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError('viewport values must be positive')  # noqa: TRY003
    return width, height


async def capture(args: argparse.Namespace) -> None:
    width, height = args.viewport
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    browser = await cloakbrowser.launch_async(headless=True)
    try:
        page = await browser.new_page(viewport={'width': width, 'height': height})
        await page.goto(args.url, wait_until=args.wait_until, timeout=args.timeout)

        if args.click_selector:
            await page.click(args.click_selector, timeout=args.timeout)

        if args.wait:
            await page.wait_for_timeout(args.wait)

        await page.screenshot(path=str(out_path), full_page=args.full_page)
    finally:
        await browser.close()

    sys.stdout.write(f'{out_path}\n')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Capture a screenshot through the local CloakBrowser Chromium.'
    )
    parser.add_argument('url', help='URL to open')
    parser.add_argument('--out', default='cloakbrowser-page.png', help='Output PNG path')
    parser.add_argument(
        '--viewport',
        type=parse_viewport,
        default=parse_viewport('1440x1000'),
        help='Viewport size as WIDTHxHEIGHT',
    )
    parser.add_argument('--wait', type=int, default=0, help='Extra wait after navigation in ms')
    parser.add_argument('--click-selector', help='CSS selector to click before the screenshot')
    parser.add_argument('--full-page', action='store_true', help='Capture the full page')
    parser.add_argument(
        '--wait-until',
        default='networkidle',
        choices=('commit', 'domcontentloaded', 'load', 'networkidle'),
        help='Playwright navigation readiness state',
    )
    parser.add_argument('--timeout', type=int, default=30_000, help='Navigation timeout in ms')
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(capture(args))


if __name__ == '__main__':
    main()
