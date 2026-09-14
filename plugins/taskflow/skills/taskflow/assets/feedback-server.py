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

Feedback is collected once and cannot be collected again, so a save never destroys
what the last one left. The version being replaced is copied to
<root>/.history/<name>.<timestamp>.json first, and a save that carries nothing over
a file that carries something is refused with HTTP 409 until the same body comes
back with "confirm": true — the page asks the user and resends.

The helper has a second mode, --wait, that answers the other half of the loop:
when did the user actually press Save? Serving mode never ends on its own, so the
conductor also starts a waiter, which blocks until one of the named JSON files is
written and then prints what was saved and exits — waking the agent through the
harness's background-task notification. The waiter only watches the filesystem, so
the serving process is untouched and keeps accepting further saves.

Usage:
  feedback-server.py --root <dir> [--port 8799]
  # then open http://127.0.0.1:<port>/<page>.html and Save from the page.
  feedback-server.py --root <dir> --wait 042-spec.answers.json,042-spec.notes.json
  # blocks; prints {"saved": [...]} and exits once the batch has settled.
Stop serving with SIGTERM / Ctrl-C when the user is done.
Exit codes: 0 ok, 1 bad args, 2 --wait hit --timeout with nothing saved,
3 a saved file could not be read as JSON, 4 the port is already taken,
130 interrupted.
"""

from __future__ import annotations

import argparse
import errno
import json
import re
import shutil
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+\.json$")
MAX_BODY = 4_000_000
HISTORY_DIR = ".history"
HISTORY_KEEP = 20
# Keys every page writes whether or not the user entered anything. They say what the
# file is, not what the user said, so they do not count as content.
BOOKKEEPING_KEYS = {"task", "kind", "ts"}
CTYPES = {
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


def has_content(value) -> bool:
    """Whether a saved payload carries anything the user put there."""
    if isinstance(value, dict):
        return any(has_content(v) for k, v in value.items() if k not in BOOKKEEPING_KEYS)
    if isinstance(value, (list, tuple)):
        return any(has_content(v) for v in value)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None and value is not False


def keep_previous(target: Path) -> Path | None:
    """Copy the version about to be replaced into <root>/.history/. Returns its path."""
    if not target.is_file():
        return None
    history = target.parent / HISTORY_DIR
    history.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    kept = history / f"{target.stem}.{stamp}{target.suffix}"
    n = 1
    while kept.exists():
        n += 1
        kept = history / f"{target.stem}.{stamp}-{n}{target.suffix}"
    shutil.copy2(target, kept)
    older = sorted(history.glob(f"{target.stem}.*{target.suffix}"))
    for stale in older[:-HISTORY_KEEP]:
        stale.unlink()
    return kept


class Refused(Exception):
    """A save the helper will not make without the user saying so again."""


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
            data = payload.get("data")
            if not has_content(data) and payload.get("confirm") is not True:
                previous = None
                if target.is_file():
                    try:
                        previous = json.loads(target.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        previous = None
                if has_content(previous):
                    raise Refused(
                        f"{fname} already holds feedback and this save is empty. "
                        f"Save again to confirm the file should be emptied; the version "
                        f"on disk is kept either way under {HISTORY_DIR}/."
                    )
            kept = keep_previous(target)
            target.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Refused as exc:
            return self._send(409, json.dumps(
                {"error": str(exc), "needsConfirm": True}, ensure_ascii=False
            ).encode("utf-8"))
        except Exception as exc:  # noqa: BLE001 — report any failure to the page
            return self._send(400, json.dumps({"error": str(exc)}).encode("utf-8"))
        body = {"ok": True, "saved": fname}
        if kept is not None:
            body["kept"] = f"{HISTORY_DIR}/{kept.name}"
        return self._send(200, json.dumps(body).encode("utf-8"))

    def log_message(self, *args):  # keep the console quiet
        pass


def _signature(path: Path):
    """What the waiter compares between polls: absent, or (size, mtime)."""
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return (st.st_size, st.st_mtime_ns)


def wait_for_saves(root: Path, names: list[str], quiet: float, timeout: float, interval: float = 0.5) -> int:
    """Block until one of `names` is written under `root`, then until `quiet` seconds
    pass with no further write among them — a page that saves two files in a row
    (answers, then notes) is reported as one batch. Prints the batch and returns 0."""
    targets = {name: root / name for name in names}
    baseline = {name: _signature(path) for name, path in targets.items()}
    changed: dict[str, None] = {}
    started = time.monotonic()
    last_change = 0.0

    while True:
        for name, path in targets.items():
            sig = _signature(path)
            if sig is not None and sig != baseline[name]:
                baseline[name] = sig
                changed[name] = None
                last_change = time.monotonic()
        if changed and time.monotonic() - last_change >= quiet:
            break
        if not changed and timeout and time.monotonic() - started >= timeout:
            print(
                f"feedback-server: nothing was saved in {timeout:g}s. Watched under {root}: "
                + ", ".join(names),
                file=sys.stderr,
            )
            return 2
        time.sleep(interval)

    saved = []
    for name in changed:
        text = targets[name].read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            # The page wrote something unreadable. Say so — an empty batch would read as "no feedback".
            print(f"feedback-server: {targets[name]} is not valid JSON: {exc}", file=sys.stderr)
            return 3
        saved.append({"file": name, "data": data})

    print(json.dumps({"saved": saved}, ensure_ascii=False, indent=2), flush=True)
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="feedback-server",
        description=(
            "Serve taskflow pages on localhost and save their feedback JSON next to them, "
            "or (--wait) block until one of those files is saved and print it."
        ),
        epilog=(
            "Examples:\n"
            "  Serve the pages (long-lived, stop it with Ctrl-C / SIGTERM):\n"
            "    feedback-server.py --root todos/pages --port 8799\n"
            "  Wait for the user to press Save on the spec page, then print the batch and exit:\n"
            "    feedback-server.py --root todos/pages --wait 042-spec.answers.json,042-spec.notes.json\n"
            "\n"
            "Waiting mode prints {\"saved\": [{\"file\": ..., \"data\": ...}, ...]} on stdout.\n"
            "It watches the files only, so run it alongside a serving process.\n"
            "\n"
            "A save never destroys the version before it: that one is copied into\n"
            "<root>/.history/<name>.<timestamp>.json (last 20 per file kept), and an empty\n"
            "save over a file that holds feedback is answered 409 until the page resends it\n"
            "with \"confirm\": true.\n"
            "\n"
            "Exit codes: 0 ok, 1 bad arguments, 2 --timeout expired with nothing saved,\n"
            "            3 a saved file is not readable JSON, 4 the port is already taken,\n"
            "            130 interrupted."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--root", required=True, help="Directory to serve and save into (e.g. todos/pages).")
    ap.add_argument("--port", type=int, help="Port to listen on (default 8799). Serving mode only.")
    ap.add_argument(
        "--wait",
        metavar="NAMES",
        help="Comma-separated JSON filenames inside --root to wait for instead of serving. "
        "Blocks until one of them is written, then prints every file written in that batch and exits.",
    )
    ap.add_argument(
        "--quiet",
        type=float,
        default=8.0,
        help="Waiting mode: seconds without a further save before the batch is reported (default 8). "
        "Covers a page that saves answers and notes one after the other.",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=0.0,
        help="Waiting mode: give up after this many seconds if nothing was saved at all "
        "(default 0 = wait indefinitely).",
    )
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

    if args.wait is not None:
        if args.port is not None:
            sys.exit("feedback-server: --port belongs to serving mode and cannot be combined with --wait")
        names = [n.strip() for n in args.wait.split(",") if n.strip()]
        if not names:
            sys.exit("feedback-server: --wait needs at least one filename, e.g. --wait 042-spec.notes.json")
        bad = [n for n in names if not SAFE_NAME.match(n)]
        if bad:
            sys.exit(f"feedback-server: --wait names must match [A-Za-z0-9._-]+.json, got: {', '.join(bad)}")
        if args.quiet < 0 or args.timeout < 0:
            sys.exit(f"feedback-server: --quiet and --timeout must be >= 0, got {args.quiet} and {args.timeout}")
        try:
            sys.exit(wait_for_saves(root, names, args.quiet, args.timeout))
        except KeyboardInterrupt:
            sys.exit(130)

    Handler.root = root
    port = 8799 if args.port is None else args.port
    try:
        srv = ThreadingHTTPServer((args.host, port), Handler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        # Serving on another port would leave the pages pointing at whoever holds this
        # one: it answers GET and drops every save. Name the collision and stop.
        print(
            f"feedback-server: port {port} on {args.host} is already taken, so nothing is "
            f"serving and no page was opened. Something else answers there and it will not "
            f"accept saves. Find it with `ss -ltnp | grep :{port}`, then either stop it or "
            f"start this helper on a free port with --port.",
            file=sys.stderr,
        )
        sys.exit(4)
    print(f"taskflow feedback helper → http://{args.host}:{port}  (root={root})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
