#!/usr/bin/env python3
"""Report plugins whose files changed since their version was last tagged.

Claude Code caches an installed plugin by its version string. Change a plugin's files
without moving its number and the change reaches nobody: `claude plugin update` answers
"already at the latest version" and the user keeps the old copy. Nothing errors, nothing
warns — the release simply does not happen. This is what catches that.

For each plugin it takes the version in its manifest, looks for the release tag
`{name}--v{version}`, and asks whether anything under `plugins/{name}/` has moved since. If
something has, the version is stale and must be bumped before the change can ship.

What "moved" means depends on the question being asked. Run by hand or by the generator, it
is the checkout as it stands: HEAD plus anything still uncommitted, because that is what the
next write will publish. Run from the pre-push hook (`--from-push`), it is the commits git is
about to send, read from the lines git writes to the hook's stdin; work in progress sitting
beside them in the working tree belongs to no push and blocks none.

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


def stale_plugins(
    root: pathlib.Path, versions: dict[str, str], commit: str | None = None
) -> list[dict]:
    """Plugins whose files moved since their current version was tagged.

    `versions` is what the release WILL carry — the generator passes its own table rather
    than the manifests on disk, because during a bump those still hold the previous number
    and would report a freshly bumped plugin as stale.

    `commit` names what to measure against. Left out, it is the checkout as it stands:
    HEAD plus whatever is still uncommitted — the right question before writing files.
    Given a commit, only that commit's tree counts and the working tree is ignored — the
    right question before a push, which carries commits and not the desk they were made on.
    """
    stale: list[dict] = []
    target = commit or "HEAD"
    for name, version in sorted(versions.items()):
        if not version:
            continue  # no explicit version: updates follow the commit SHA, nothing to bump
        tag = f"{name}--v{version}"
        if not tag_exists(root, tag):
            continue  # already bumped past the last release, or never tagged
        rel = f"plugins/{name}"
        changed = {
            f for f in git(root, "diff", "--name-only", f"{tag}..{target}", "--", rel).splitlines() if f
        }
        if commit is None:
            changed |= {
                line[3:]
                for line in git(root, "status", "--porcelain", "--", rel).splitlines()
                if line.strip()
            }
        if changed:
            stale.append(
                {"plugin": name, "version": version, "tag": tag, "changed": sorted(changed)}
            )
    return stale


def pushed_heads(stream) -> list[tuple[str, str]]:
    """The branches a pre-push hook is being asked to send: (ref, commit).

    git feeds `<local ref> <local sha> <remote ref> <remote sha>` per ref. A deletion
    carries an all-zero local sha and sends no files. Tags are skipped: a tag push moves
    no plugin file, and `claude plugin tag --push` is the step that follows a release.
    """
    out: list[tuple[str, str]] = []
    for line in stream:
        parts = line.split()
        if len(parts) != 4:
            continue
        local_ref, local_sha = parts[0], parts[1]
        if not local_ref.startswith("refs/heads/") or set(local_sha) == {"0"}:
            continue
        out.append((local_ref, local_sha))
    return out


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
            "  {name}--v{version}: committed since the tag, or still uncommitted.\n"
            "  With --from-push, the commits being pushed only — the working tree is not\n"
            "  read, so unfinished work on another plugin does not block the push.\n\n"
            "WHAT IS NOT STALE\n"
            "  A plugin whose tag does not exist yet — the number was already raised past the\n"
            "  last release. That is the correct state between a bump and its tag.\n"
            "  A plugin with no explicit version — its updates follow the commit SHA instead.\n\n"
            "RELEASE CYCLE\n"
            "  edit a plugin → bump it in VERSIONS → scripts/gen-manifests.py → commit →\n"
            "  claude plugin tag ./plugins/<name> [--push]\n\n"
            "EXIT CODES\n"
            "  0  every plugin's version matches what is tagged; with --from-push, also\n"
            "     when no branch is being pushed (a tag push, or a deletion)\n"
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
    parser.add_argument(
        "--from-push",
        action="store_true",
        help="read the pre-push lines git writes to stdin and check the commits being "
        "pushed instead of the checkout; uncommitted work is not considered",
    )
    args = parser.parse_args()

    if not (args.root / "plugins").is_dir():
        print(f"check_versions: no plugins/ directory under {args.root}", file=sys.stderr)
        raise SystemExit(1)

    try:
        if args.from_push:
            heads = pushed_heads(sys.stdin)
            if not heads:
                if not args.json:
                    print("nothing to check: no branch is being pushed")
                else:
                    print(json.dumps({"stale": []}, indent=2))
                raise SystemExit(0)
            by_plugin: dict[str, dict] = {}
            for _, commit in heads:
                for entry in stale_plugins(args.root, manifest_versions(args.root), commit):
                    kept = by_plugin.setdefault(entry["plugin"], entry)
                    kept["changed"] = sorted(set(kept["changed"]) | set(entry["changed"]))
            stale = [by_plugin[name] for name in sorted(by_plugin)]
        else:
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
