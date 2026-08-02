#!/usr/bin/env python3
"""Report which panel tracks have drifted from the upstream agents they were forked from.

Six of the eight tracks are derived from Anthropic's pr-review-toolkit agents. They are
copies, not references, because those agents declare no `tools:` field and therefore
inherit Write, Edit and an unrestricted shell — depending on them directly would trade a
structural read-only guarantee for a string match against someone else's naming.

The cost of copying is staleness: upstream improves a prompt and nothing tells us. This
script is what tells us. It compares the recorded upstream hash in fork-sources.json
against the installed pr-review-toolkit, and names every file that moved, so re-forking
is a decision someone made rather than a discovery six months later.

Drift is not an error. It means "go read the upstream diff and decide". Exit code 3 says
so distinctly, so a caller can treat it as informational.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "fork-sources.json"


def die(msg: str, code: int = 1) -> None:
    print(f"check-forks: {msg}", file=sys.stderr)
    raise SystemExit(code)


def blob_hash(path: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "hash-object", "--", str(path)], capture_output=True, text=True, check=True
        )
    except FileNotFoundError:
        die("git not found on PATH")
    except subprocess.CalledProcessError as exc:
        die(f"git hash-object failed for {path}: {exc.stderr.strip() or exc}")
    return out.stdout.strip()


def find_upstream(plugin: str, explicit: str | None) -> Path:
    """Locate the installed upstream agents directory.

    The install path carries version and cache segments that differ per machine, so it is
    discovered rather than assumed. Not finding it is reported, never silently treated as
    "nothing drifted" — that would turn this check into decoration.
    """
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_dir():
            die(f"--upstream {p} is not a directory. Nothing was checked.")
        return p

    roots = [Path.home() / ".claude" / "plugins"]
    candidates = sorted(
        {c for root in roots if root.is_dir() for c in root.glob(f"**/{plugin}/**/agents") if c.is_dir()}
    )
    if not candidates:
        die(
            f"the upstream plugin '{plugin}' is not installed under ~/.claude/plugins, so drift "
            f"cannot be checked. Install it, or pass --upstream <dir> pointing at its agents/ "
            f"directory. Nothing was checked.",
            code=2,
        )
    if len(candidates) > 1:
        print(
            f"check-forks: {len(candidates)} candidate upstream directories found; using {candidates[0]}",
            file=sys.stderr,
        )
    return candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="check-forks.py",
        description="Report review-panel tracks whose upstream source has changed since the fork.",
        epilog=(
            "WHAT IT COMPARES\n"
            "  fork-sources.json records, per forked track, the upstream file it came from and\n"
            "  that file's git blob hash at fork time. This compares those hashes against the\n"
            "  installed plugin.\n\n"
            "WHAT DRIFT MEANS\n"
            "  Not an error. Upstream changed the prompt; read their diff and decide whether the\n"
            "  change is worth carrying into the fork. Re-record with --update once you have.\n\n"
            "EXIT CODES\n"
            "  0  every fork matches its recorded upstream\n"
            "  1  bad input, unreadable records, or git failure\n"
            "  2  upstream plugin not installed — nothing was checked\n"
            "  3  at least one fork has drifted\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--upstream", help="path to the upstream agents/ directory (default: discover it)")
    parser.add_argument(
        "--update", action="store_true", help="re-record the current upstream hashes as the new baseline"
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    try:
        records = json.loads(SOURCES.read_text(encoding="utf-8"))
    except Exception as exc:
        die(f"cannot read {SOURCES}: {exc}")

    upstream = find_upstream(records["upstream"]["plugin"], args.upstream)

    drifted: list[dict] = []
    missing: list[dict] = []
    ok: list[str] = []

    for fork, rec in records["forks"].items():
        src = upstream / rec["source"]
        if not src.is_file():
            missing.append({"fork": fork, "source": rec["source"]})
            continue
        now = blob_hash(src)
        if now != rec["sha1"]:
            drifted.append({"fork": fork, "source": rec["source"], "was": rec["sha1"], "now": now})
            if args.update:
                rec["sha1"] = now
        else:
            ok.append(fork)

    if args.update and drifted:
        # rec["sha1"] was rewritten in place above, so records already holds the new baseline.
        SOURCES.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps({"upstream": str(upstream), "ok": ok, "drifted": drifted, "missing": missing}, indent=2))
    else:
        print(f"upstream: {upstream}")
        for entry in missing:
            print(f"  MISSING  {entry['fork']:<28} upstream file {entry['source']} is gone")
        for entry in drifted:
            print(f"  DRIFTED  {entry['fork']:<28} {entry['source']}  {entry['was'][:8]} → {entry['now'][:8]}")
        if not drifted and not missing:
            print(f"  all {len(ok)} forks match their recorded upstream")
        elif args.update:
            print("\n  baseline re-recorded. The forks themselves were not changed — read the upstream")
            print("  diff and decide what to carry over.")

    if missing:
        raise SystemExit(1)
    if drifted and not args.update:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
