#!/usr/bin/env python3
"""Regression test for --cookie parsing and --ignore-https-errors."""

from __future__ import annotations

import http.server
import importlib.util
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIRS = (
    ROOT / "plugins/cloakbrowser/skills/cloakbrowser/scripts",
    ROOT / "plugins/cloakbrowser-codex/skills/cloakbrowser/scripts",
)
ENGINES = ("chromium", "cloak")
SECURE_COOKIE ="name=__Secure-probe value=ok domain=localhost path=/ secure=true"


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = b"<!doctype html><title>tls</title><p>tls-ok</p>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        del format, args


def run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )


@unittest.skipUnless(shutil.which("openssl"), "openssl is needed to make a self-signed certificate")
class SelfSignedHttpsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cert = Path(cls.tmp.name) / "cert.pem"
        key = Path(cls.tmp.name) / "key.pem"
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
             "-subj", "/CN=localhost", "-keyout", str(key), "-out", str(cert)],
            check=True,
            capture_output=True,
        )
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert, key)
        cls.server.socket = tls.wrap_socket(cls.server.socket, server_side=True)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"https://localhost:{cls.server.server_address[1]}/"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def test_inspect_page_needs_the_flag(self) -> None:
        for scripts in SCRIPT_DIRS:
            script = scripts / "inspect_page.py"
            for engine in ENGINES:
                with self.subTest(script=script, engine=engine):
                    self._check_inspect_page(script, engine)

    def _check_inspect_page(self, script: Path, engine: str) -> None:
        strict = run(script, self.url, "--engine", engine, "--wait-until", "load", "--wait", "0")
        self.assertEqual(strict.returncode, 2, strict.stdout + strict.stderr)
        self.assertIn("ERR_CERT", strict.stdout)

        loose = run(
            script, self.url, "--engine", engine, "--wait-until", "load", "--wait", "0",
            "--ignore-https-errors", "--cookie", SECURE_COOKIE,
            "--eval", "() => document.body.innerText",
            "--eval", "() => document.cookie",
        )
        self.assertEqual(loose.returncode, 0, loose.stdout + loose.stderr)
        self.assertIn('EVAL "tls-ok"', loose.stdout)
        self.assertIn('EVAL "__Secure-probe=ok"', loose.stdout)

    def test_capture_needs_the_flag(self) -> None:
        for scripts in SCRIPT_DIRS:
            script = scripts / "capture.py"
            with self.subTest(script=script), tempfile.TemporaryDirectory() as out_dir:
                out = Path(out_dir) / "page.png"
                strict = run(script, self.url, "--wait-until", "load", "--out", str(out))
                self.assertNotEqual(strict.returncode, 0)
                self.assertIn("ERR_CERT", strict.stderr)
                self.assertFalse(out.exists())

                loose = run(
                    script, self.url, "--wait-until", "load", "--out", str(out),
                    "--ignore-https-errors", "--cookie", SECURE_COOKIE,
                )
                self.assertEqual(loose.returncode, 0, loose.stdout + loose.stderr)
                self.assertTrue(out.stat().st_size > 0)


def load_browser_module(scripts: Path):
    spec = importlib.util.spec_from_file_location(f"browser_{scripts.parts[-4]}", scripts / "browser.py")
    assert spec is not None and spec.loader is not None, scripts
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CookieArgumentTest(unittest.TestCase):
    BASE = "name=a value=b domain=localhost path=/"
    BAD = (
        (f"{BASE} secure=yes", "expected true or false"),
        (f"{BASE} httpOnly=1", "expected true or false"),
        (f"{BASE} expires=tomorrow", "expected -1 (session cookie) or a Unix timestamp"),
        (f"{BASE} expires=-5", "expected -1 (session cookie) or a Unix timestamp"),
        (f"{BASE} expires=nan", "expected -1 (session cookie) or a Unix timestamp"),
        (f"{BASE} expires=253402300800", "expected -1 (session cookie) or a Unix timestamp"),
        (f"{BASE} sameSite=lax", "expected one of Strict, Lax, None"),
        (f"{BASE} Secure=true", "unknown cookie key 'Secure'"),
        (f"{BASE} name=c", "cookie key 'name' given twice"),
        ("name=a value=b domain=localhost", "must include url, or both domain and path"),
        ("name=a value=b url=https://localhost/ domain=localhost", "either url or domain+path"),
    )

    def test_flags_and_numbers_are_typed(self) -> None:
        for scripts in SCRIPT_DIRS:
            with self.subTest(scripts=scripts):
                browser = load_browser_module(scripts)
                cookie = browser.parse_cookie(
                    f"{self.BASE} secure=true httpOnly=false expires=1700000000 sameSite=Lax")
                self.assertIs(cookie["secure"], True)
                self.assertIs(cookie["httpOnly"], False)
                self.assertEqual(cookie["expires"], 1700000000.0)
                self.assertEqual(cookie["sameSite"], "Lax")
                self.assertEqual(browser.parse_cookie("name=a value=b url=https://x/")["url"], "https://x/")

    def test_bad_cookie_fails_before_the_browser(self) -> None:
        for scripts in SCRIPT_DIRS:
            for name in ("inspect_page.py", "capture.py"):
                for cookie, message in self.BAD:
                    with self.subTest(script=scripts / name, cookie=cookie):
                        # An unreachable URL: reaching navigation would hang or fail differently.
                        result = run(scripts / name, "https://127.0.0.1:9/", "--cookie", cookie)
                        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                        self.assertIn(message, result.stderr)
                        self.assertNotIn("GOTO", result.stdout)


if __name__ == "__main__":
    unittest.main()
