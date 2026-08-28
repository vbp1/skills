#!/usr/bin/env python3
"""taskflow feedback helper — a tiny localhost server that SERVES the task pages
and SAVES user feedback (answers to open questions / mockup notes) as JSON right
next to them.

Why it exists: a page opened as a plain file:// cannot write a file to disk. So
while the user reviews a page and leaves feedback, the conductor runs this helper,
opens the page through it (http://127.0.0.1:PORT/NNN-spec.html), and the page's
"Save" button POSTs to /save — which writes <root>/<name>.json in place.

Stdlib only. Binds 127.0.0.1. Static GET from --root; POST /save with body
{"file":"<name>.json","data":{...}} writes <root>/<name>.json. The filename is
restricted to a safe pattern inside root (no path traversal); body size is capped.

Usage:
  feedback-server.py --root <dir> [--port 8799]
  # then open http://127.0.0.1:<port>/<page>.html and Save from the page.
Stop it with SIGTERM / Ctrl-C when the user is done. Exit codes: 0 ok, 1 bad args.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+\.json$")
MAX_BODY = 4_000_000
CTYPES = {
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


class Handler(BaseHTTPRequestHandler):
    root: Path = Path(".")

    def _send(self, code: int, body: bytes = b"", ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _safe_target(self, rel: str) -> Path | None:
        target = (self.root / rel).resolve()
        try:
            target.relative_to(self.root.resolve())
        except ValueError:
            return None
        return target

    def do_GET(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        rel = path.lstrip("/") or "index.html"
        target = self._safe_target(rel)
        if target is None:
            return self._send(403, b"forbidden", "text/plain")
        if not target.is_file():
            return self._send(404, b"not found", "text/plain")
        self._send(200, target.read_bytes(), CTYPES.get(target.suffix, "application/octet-stream"))

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/save":
            return self._send(404, b'{"error":"unknown endpoint"}')
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                raise ValueError("bad content length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            fname = str(payload.get("file", ""))
            if not SAFE_NAME.match(fname):
                raise ValueError("filename must match [A-Za-z0-9._-]+.json")
            target = self._safe_target(fname)
            if target is None:
                raise ValueError("path traversal rejected")
            target.write_text(
                json.dumps(payload.get("data"), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001 — report any failure to the page
            return self._send(400, json.dumps({"error": str(exc)}).encode("utf-8"))
        return self._send(200, json.dumps({"ok": True, "saved": fname}).encode("utf-8"))

    def log_message(self, *args):  # keep the console quiet
        pass


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="feedback-server",
        description="Serve taskflow pages on localhost and save their feedback JSON next to them.",
        epilog="Example: feedback-server.py --root todos/pages --port 8799",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--root", required=True, help="Directory to serve and save into (e.g. todos/pages).")
    ap.add_argument("--port", type=int, default=8799, help="Port to listen on (default 8799).")
    ap.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default 127.0.0.1). Use 0.0.0.0 only if the browser cannot reach the WSL "
        "loopback via localhost forwarding — it exposes the save endpoint to the local network while running.",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        sys.exit(f"feedback-server: --root is not a directory: {root}")
    Handler.root = root

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"taskflow feedback helper → http://{args.host}:{args.port}  (root={root})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
