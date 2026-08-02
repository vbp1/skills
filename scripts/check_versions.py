#!/usr/bin/env python3
"""Report plugins whose files changed since their version was last tagged.

Claude Code caches an installed plugin by its version string. Change a plugin's files
without moving its number and the change reaches nobody: `claude plugin update` answers
"already at the latest version" and the user keeps the old copy. Nothing errors, nothing
warns — the release simply does not happen. This is what catches that.

For each plugin it takes the version in its manifest, looks for the release tag
`{name}--v{version}`, and asks whether anything under `plugins/{name}/` has moved since —
committed or not. If something has, the version is stale and must be bumped before the
change can ship.

A plugin whose tag does not exist yet is not stale: the number was already raised past the
last release, which is exactly the correct state between a bump and its tag.

The module name uses an underscore so `gen-manifests.py` can import it and run the same
check before it writes anything. Importing has no side effects.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys


def git(root: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0 and args[:1] != ("rev-parse",):
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def tag_exists(root: pathlib.Path, tag: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
        capture_output=True,
        text=True,
    ).returncode == 0


def manifest_versions(root: pathlib.Path) -> dict[str, str]:
    """Versions as currently published on disk, for a standalone run."""
    out: dict[str, str] = {}
    for manifest in sorted((root / "plugins").glob("*/.claude-plugin/plugin.json")):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        out[data["name"]] = data.get("version", "")
    return out


def stale_plugins(root: pathlib.Path, versions: dict[str, str]) -> list[dict]:
    """Plugins whose files moved since their current version was tagged.

    `versions` is what the release WILL carry — the generator passes its own table rather
    than the manifests on disk, because during a bump those still hold the previous number
    and would report a freshly bumped plugin as stale.
    """
    stale: list[dict] = []
    for name, version in sorted(versions.items()):
        if not version:
            continue  # no explicit version: updates follow the commit SHA, nothing to bump
        tag = f"{name}--v{version}"
        if not tag_exists(root, tag):
            continue  # already bumped past the last release, or never tagged
        rel = f"plugins/{name}"
        committed = [f for f in git(root, "diff", "--name-only", f"{tag}..HEAD", "--", rel).splitlines() if f]
        uncommitted = [
            line[3:] for line in git(root, "status", "--porcelain", "--", rel).splitlines() if line.strip()
        ]
        changed = sorted(set(committed) | set(uncommitted))
        if changed:
            stale.append({"plugin": name, "version": version, "tag": tag, "changed": changed})
    return stale


def format_report(stale: list[dict]) -> str:
    lines = []
    for entry in stale:
        lines.append(
            f"  {entry['plugin']} is still at {entry['version']}, but "
            f"{len(entry['changed'])} file(s) changed since {entry['tag']}:"
        )
        for f in entry["changed"][:8]:
            lines.append(f"      {f}")
        if len(entry["changed"]) > 8:
            lines.append(f"      … and {len(entry['changed']) - 8} more")
        lines.append(f"      → bump '{entry['plugin']}' in VERSIONS, or the change reaches nobody.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="check_versions.py",
        description="Report plugins whose files changed since their version was last tagged.",
        epilog=(
            "WHY\n"
            "  Claude Code caches an installed plugin by its version string. Editing a plugin\n"
            "  without bumping its number means the change never reaches users, and nothing\n"
            "  reports an error — `claude plugin update` says 'already at the latest version'.\n\n"
            "WHAT COUNTS AS CHANGED\n"
            "  Anything under plugins/<name>/ that differs from the release tag\n"
            "  {name}--v{version}, whether committed since the tag or still uncommitted.\n\n"
            "WHAT IS NOT STALE\n"
            "  A plugin whose tag does not exist yet — the number was already raised past the\n"
            "  last release. That is the correct state between a bump and its tag.\n"
            "  A plugin with no explicit version — its updates follow the commit SHA instead.\n\n"
            "RELEASE CYCLE\n"
            "  edit a plugin → bump it in VERSIONS → scripts/gen-manifests.py → commit →\n"
            "  claude plugin tag ./plugins/<name> [--push]\n\n"
            "EXIT CODES\n"
            "  0  every plugin's version matches what is tagged\n"
            "  1  not a git repository, or git failed\n"
            "  3  at least one plugin changed without a version bump\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        default=pathlib.Path(__file__).resolve().parent.parent,
        type=pathlib.Path,
        help="repository root (default: parent of scripts/)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    if not (args.root / "plugins").is_dir():
        print(f"check_versions: no plugins/ directory under {args.root}", file=sys.stderr)
        raise SystemExit(1)

    try:
        stale = stale_plugins(args.root, manifest_versions(args.root))
    except RuntimeError as exc:
        print(f"check_versions: {exc}", file=sys.stderr)
        raise SystemExit(1)

    if args.json:
        print(json.dumps({"stale": stale}, indent=2))
    elif stale:
        print(f"{len(stale)} plugin(s) changed without a version bump:")
        print(format_report(stale))
    else:
        print("every plugin's version matches what is tagged")

    raise SystemExit(3 if stale else 0)


if __name__ == "__main__":
    main()
