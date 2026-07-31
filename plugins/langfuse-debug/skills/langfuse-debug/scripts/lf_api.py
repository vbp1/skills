#!/usr/bin/env python3
"""Langfuse API client with credential discovery, pagination, and safe JSON parsing."""

import json
import os
import re
import sys
import urllib.request
import urllib.error
import urllib.parse
import base64
from pathlib import Path

# ---------------------------------------------------------------------------
# Credential discovery
# ---------------------------------------------------------------------------

ENV_FILES = [".env.production", ".env.local", ".env"]


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE pairs from a dotenv file (ignores comments, exports, quotes)."""
    result = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:]
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            result[key] = value
    except (OSError, UnicodeDecodeError):
        pass
    return result


def _search_env_files() -> dict[str, str]:
    """Walk CWD and parent dirs looking for .env files with Langfuse credentials."""
    cwd = Path.cwd()
    dirs_to_check = [cwd] + list(cwd.parents)
    for d in dirs_to_check:
        for name in ENV_FILES:
            envfile = d / name
            if envfile.is_file():
                parsed = _parse_env_file(envfile)
                if "LANGFUSE_PUBLIC_KEY" in parsed and "LANGFUSE_SECRET_KEY" in parsed:
                    return parsed
    return {}


def resolve_credentials() -> tuple[str, str, str]:
    """Return (host, public_key, secret_key). Raises SystemExit on failure."""
    host = os.environ.get("LANGFUSE_HOST")
    public = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret = os.environ.get("LANGFUSE_SECRET_KEY")

    if public and secret:
        host = host or "https://cloud.langfuse.com"
        return host, public, secret

    env_vals = _search_env_files()
    if env_vals.get("LANGFUSE_PUBLIC_KEY") and env_vals.get("LANGFUSE_SECRET_KEY"):
        host = host or env_vals.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
        # Rewrite Docker-internal hostnames to localhost
        host = re.sub(r"https?://langfuse[^:/]*", "http://localhost", host)
        return host, env_vals["LANGFUSE_PUBLIC_KEY"], env_vals["LANGFUSE_SECRET_KEY"]

    print("ERROR: Langfuse credentials not found.", file=sys.stderr)
    print("Set LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST env vars", file=sys.stderr)
    print(f"or place them in one of: {', '.join(ENV_FILES)}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# URL parsing helpers
# ---------------------------------------------------------------------------

_SESSION_RE = re.compile(r"/sessions?/([0-9a-f-]{36})")
_TRACE_RE = re.compile(r"/traces?/([0-9a-f]{32})")
_UUID_RE = re.compile(r"^[0-9a-f-]{36}$")
_HEX32_RE = re.compile(r"^[0-9a-f]{32}$")


def parse_session_id(url_or_id: str) -> str:
    """Extract session ID from a Langfuse URL or return as-is if already an ID."""
    url_or_id = url_or_id.strip()
    m = _SESSION_RE.search(url_or_id)
    if m:
        return m.group(1)
    if _UUID_RE.match(url_or_id):
        return url_or_id
    return url_or_id


def parse_trace_id(url_or_id: str) -> str:
    """Extract trace ID from a Langfuse URL or return as-is if already an ID."""
    url_or_id = url_or_id.strip()
    m = _TRACE_RE.search(url_or_id)
    if m:
        return m.group(1)
    if _HEX32_RE.match(url_or_id):
        return url_or_id
    return url_or_id


# ---------------------------------------------------------------------------
# HTTP client (stdlib only — no requests dependency)
# ---------------------------------------------------------------------------


def _make_auth_header(public_key: str, secret_key: str) -> str:
    creds = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    return f"Basic {creds}"


def api_get(path: str, params: dict | None = None, credentials: tuple | None = None) -> dict:
    """Single GET request to Langfuse API. Returns parsed JSON dict."""
    host, public, secret = credentials or resolve_credentials()
    url = f"{host}/api/public{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": _make_auth_header(public, secret),
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        print(f"HTTP {e.code}: {e.reason}\n{body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        sys.exit(1)
    return json.loads(raw, strict=False)


def api_get_all(path: str, params: dict | None = None, credentials: tuple | None = None,
                max_pages: int = 20) -> list:
    """Paginated GET — returns all items from `data` key."""
    params = dict(params or {})
    params.setdefault("limit", 50)
    all_items = []
    for page_num in range(1, max_pages + 1):
        params["page"] = page_num
        resp = api_get(path, params, credentials)
        items = resp.get("data", [])
        all_items.extend(items)
        meta = resp.get("meta", {})
        total_pages = meta.get("totalPages", 1)
        if page_num >= total_pages:
            break
    return all_items


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

USAGE = """Usage: lf_api.py <command> [args]

Commands:
  health                    Check credentials and API connectivity
  get <path> [--params JSON]  Raw GET request to /api/public<path>

Examples:
  lf_api.py health
  lf_api.py get /sessions/SESSION_ID
  lf_api.py get /traces --params '{"sessionId":"xxx","limit":10}'
  lf_api.py get /observations --params '{"traceId":"xxx","limit":50}'
"""


def cmd_health():
    host, public, secret = resolve_credentials()
    masked_secret = secret[:8] + "..." + secret[-4:]
    print(f"Host:       {host}")
    print(f"Public Key: {public}")
    print(f"Secret Key: {masked_secret}")
    try:
        resp = api_get("/health", credentials=(host, public, secret))
        print(f"API Status: {resp.get('status', 'unknown')}")
    except SystemExit:
        print("API Status: UNREACHABLE")


def cmd_get(args: list[str]):
    if not args:
        print("Error: path required. Example: lf_api.py get /traces", file=sys.stderr)
        sys.exit(1)
    path = args[0]
    params = None
    if "--params" in args:
        idx = args.index("--params")
        if idx + 1 < len(args):
            params = json.loads(args[idx + 1])
    resp = api_get(path, params)
    print(json.dumps(resp, indent=2, ensure_ascii=False, default=str))


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(USAGE)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "health":
        cmd_health()
    elif cmd == "get":
        cmd_get(sys.argv[2:])
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
