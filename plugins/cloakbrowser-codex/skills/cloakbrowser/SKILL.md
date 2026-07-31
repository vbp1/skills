---
name: cloakbrowser
description: Use local CloakBrowser stealth Chromium for visual UI inspection, screenshots, and browser checks when the user asks to look at a page, inspect the interface, verify frontend changes, or use cloakbrowser/cloak-browser.
---

# CloakBrowser

## Overview

Use CloakBrowser when a task needs a real browser view instead of code-only reasoning: UI review, layout checks, screenshots, local web app inspection, or reproducing browser-visible behavior.

Prefer this skill before changing UI code when the user asks to "look at it", "see how it looks", "check visually", "use cloakbrowser", or mentions `cloak-browser`.

## Local Tooling

- CLI: `~/.local/bin/cloakbrowser`
- Python package: `cloakbrowser`
- Browser cache: `~/.cloakbrowser`
- Check installation: `~/.local/bin/cloakbrowser info`
- Install or refresh binary: `~/.local/bin/cloakbrowser install`

If the CLI is not on `PATH`, call it by the absolute path above.

## Workflow

1. Make sure the target page is reachable. Start the local development server if the application needs one.
2. Run `cloakbrowser info` to confirm the bundled Chromium binary is installed.
3. Capture a screenshot with `scripts/capture.py` or use the Python API directly for a custom interaction.
4. Inspect the screenshot with available image-viewing tools.
5. Report concrete visual findings before editing. After edits, capture another screenshot to verify the result.

## Screenshot Helper

Use the helper for the common "open URL and save screenshot" case. `<skill-dir>` is the
directory that holds this SKILL.md:

```bash
python3 <skill-dir>/scripts/capture.py \
  http://127.0.0.1:8765/ \
  --out /tmp/cloakbrowser-page.png \
  --viewport 1440x1000 \
  --wait 500
```

Options:

- `--viewport WIDTHxHEIGHT` sets the browser viewport.
- `--wait MS` waits after navigation and interaction.
- `--click-selector SELECTOR` clicks a CSS selector before the screenshot.
- `--full-page` captures the full page instead of only the viewport.

## Direct Python Pattern

Use the async API for interactions that need more than a static screenshot:

```python
import asyncio
import cloakbrowser


async def main():
    browser = await cloakbrowser.launch_async(headless=True)
    page = await browser.new_page(viewport={"width": 1440, "height": 1000})
    await page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
    await page.screenshot(path="/tmp/page.png", full_page=True)
    await browser.close()


asyncio.run(main())
```

Keep browser automation focused on the user's requested check. Do not use CloakBrowser as a replacement for unit tests, linters, or accessibility checks.
