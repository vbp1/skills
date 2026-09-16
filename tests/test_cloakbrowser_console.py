#!/usr/bin/env python3
"""Regression test for browser-side console and page-error capture."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    ROOT / "plugins/cloakbrowser/skills/cloakbrowser/scripts/inspect_page.py",
    ROOT / "plugins/cloakbrowser-codex/skills/cloakbrowser/scripts/inspect_page.py",
)


class InspectPageSignalsTest(unittest.TestCase):
    def test_console_and_pageerror_are_reported(self) -> None:
        html = """<script>
console.error("smoke-console");
setTimeout(() => { throw new Error("smoke-pageerror"); }, 0);
</script>"""
        url = f"data:text/html,{quote(html)}"

        for script in SCRIPTS:
            with self.subTest(script=script):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        url,
                        "--wait-until",
                        "load",
                        "--wait",
                        "100",
                    ],
                    capture_output=True,
                    check=False,
                    text=True,
                    timeout=10,
                )

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("CONSOLE[error] smoke-console", result.stdout)
                self.assertIn("PAGEERROR Error: smoke-pageerror", result.stdout)


if __name__ == "__main__":
    unittest.main()
