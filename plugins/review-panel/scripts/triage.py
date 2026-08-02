#!/usr/bin/env python3
"""Mechanical track selection for the review panel — costs no tokens.

Turns a diff into a proposed subset of review tracks, with a stated reason per
track kept and per track skipped, plus the questions a regex structurally cannot
answer. Everything that needs judgment is deliberately left to the judge subagent
rather than guessed at here with a cleverer pattern.

The proposal is a starting point, not a verdict: the judge adjusts it and the
user confirms it. Running the same diff twice always yields the same proposal,
which is the point — it makes the panel's size an argued decision rather than a
mood.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

# Optional per-project config. The first path is this plugin's own name; the
# second is read as well so a project that already configured the pre-commit
# barrier does not have to duplicate its zone list.
CONFIG_PATHS = [
    Path(".claude") / "review-panel.json",
    Path(".claude") / "hooks" / "precommit-gate.json",
]

# Source files worth reviewing. Test files are recognised separately below,
# because "source changed but no test touched" is what earns the tests track.
CODE_RE = re.compile(
    r"\.(ts|tsx|js|jsx|mjs|cjs|py|go|rs|rb|java|kt|kts|swift|m|mm|c|cc|cpp|cxx|h|hpp|cs|php|scala|ex|exs|erl|lua|sh|bash|zsh|sql)$"
)
TEST_RE = re.compile(
    r"(\.(test|spec)\.[a-z]+$|(^|/)tests?/|(^|/)test_[^/]+\.py$|_test\.(py|go|rb|exs)$|Test[A-Z][^/]*\.(java|kt|cs|scala)$|(^|/)spec/)"
)
COMMENT_LINE_RE = re.compile(r"^\s*(//|/\*|\*|#|--)")
DEPS_RE = re.compile(
    r"(^|/)(package\.json|requirements[^/]*\.txt|pyproject\.toml|Pipfile|go\.mod|Cargo\.toml|Gemfile|pom\.xml|build\.gradle(\.kts)?|composer\.json|mix\.exs)$"
)

# Each signal turns ADDED diff lines into one review track. Patterns cover the
# common languages rather than one ecosystem — a track that never fires in a Go
# repository is a track the panel silently lost.
SIGNALS = [
    (
        "silent-failures",
        re.compile(
            r"\b(try|catch|except|rescue|finally|recover|throw|raise|panic)\b|\.catch\(|\?\?|"
            r"err\s*!=\s*nil|\.unwrap\(|\.expect\(|console\.(error|warn)|Promise\.(all|allSettled|race)"
        ),
        "error handling / fallback / rejection paths in the added lines",
    ),
    (
        "type-design",
        re.compile(
            r"\b(interface|enum|struct|trait|impl|dataclass|TypedDict|NamedTuple|protocol|satisfies)\b|"
            r"\btype\s+\w+\s*=|\bclass\s+\w+|\bz\.[a-z]|as\s+unknown|export\s+(type|interface)|:\s*Promise<"
        ),
        "types, schemas or exported signatures touched",
    ),
    (
        "adversary",
        re.compile(
            r"\b(if|for|while|switch|match|elif|unless)\b\s*[\(:]|\.map\(|\.filter\(|\.reduce\(|"
            r"JSON\.parse|json\.loads|Unmarshal|serde_json|new RegExp|re\.compile|\.split\(|"
            r"parseInt|Number\(|strconv\.|\bint\(|\bfloat\("
        ),
        "branching / parsing logic in the added lines",
    ),
]

ALL_TRACKS = [
    "correctness",
    "silent-failures",
    "type-design",
    "tests",
    "comments",
    "adversary",
    "over-engineering",
    "simplify",
]

# What the regexes structurally cannot decide — handed to the judge subagent.
JUDGE_QUESTIONS = [
    "Is this a BUG FIX? If so the tests track is mandatory (regression test that fails without the fix), even when tests were already touched.",
    "Does it change a contract other code depends on — exported signature, wire format, provider option, DB column semantics? If so add type-design + correctness regardless of size.",
    "Is a SMALL diff sitting on a dangerous path (auth, permissions, migrations, scheduler, money/retry loops)? Size is not risk.",
    "Is a LARGE diff mechanical (rename, move, formatting, generated file)? Then most tracks are noise — say which to drop and why.",
    "Was a helper/factory extracted that many call sites now route through? That widens blast radius beyond the changed lines.",
]

LOC_OVERENGINEERING = 80  # added LOC above which the over-engineering lens earns its slot
LOC_SIMPLIFY = 100
LOC_HIGH_ZONE = 200
FILES_HIGH_ZONE = 10
COMMENT_LINES_MIN = 5


def die(msg: str) -> None:
    print(f"triage: {msg}", file=sys.stderr)
    raise SystemExit(1)


def git(root: str, *args: str) -> str:
    try:
        result = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, check=True)
    except FileNotFoundError:
        die("git not found on PATH")
    except subprocess.CalledProcessError as exc:
        die(f"git {' '.join(args)} failed: {exc.stderr.strip() or exc}")
    return result.stdout


def repo_root(start: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", start, "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        )
    except Exception:
        die(f"not inside a git repository: {start}")
    root = out.stdout.strip()
    if not root:
        die(f"not inside a git repository: {start}")
    return root


def load_config(root: str) -> dict:
    """A missing or broken config is not fatal — triage still works without zones."""
    for rel in CONFIG_PATHS:
        try:
            with (Path(root) / rel).open(encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            continue
    return {}


def nontrivial_hits(files: list[str], globs: list[str]) -> list[str]:
    return [f for f in files if any(fnmatch.fnmatch(f, g) for g in globs)]


def diff_args(scope: str, base: str | None) -> list[str]:
    if base:
        return ["diff", base]
    if scope == "staged":
        return ["diff", "--cached"]
    return ["diff", "HEAD"]


def untracked_files(root: str) -> list[str]:
    return [p for p in git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0") if p]


def collect_changes(root: str, scope: str, base: str | None) -> dict:
    """Changed paths + the ADDED text of the diff (untracked files count as fully added)."""
    files = [p for p in git(root, *diff_args(scope, base), "--name-only", "-z").split("\0") if p]
    new_files = [
        p for p in git(root, *diff_args(scope, base), "--name-only", "--diff-filter=A", "-z").split("\0") if p
    ]

    untracked: list[str] = []
    if scope != "staged":
        untracked = untracked_files(root)
        files += untracked
        new_files += untracked

    added: list[str] = []
    for line in git(root, *diff_args(scope, base), "-U0").splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    for path in untracked:
        p = Path(root) / path
        try:
            if p.stat().st_size > 1_000_000:
                continue
            added.extend(p.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue

    return {"files": sorted(set(files)), "new_files": sorted(set(new_files)), "added": added}


def triage(root: str, config: dict, scope: str, base: str | None) -> dict:
    ch = collect_changes(root, scope, base)
    files, new_files, added = ch["files"], ch["new_files"], ch["added"]
    code_files = [f for f in files if CODE_RE.search(f)]
    test_files = [f for f in code_files if TEST_RE.search(f)]
    src_files = [f for f in code_files if not TEST_RE.search(f)]
    new_code_files = [f for f in new_files if CODE_RE.search(f)]
    # Zone is about production blast radius, so a test file sitting under a
    # sensitive directory must not drag the whole panel in on its own.
    hits = nontrivial_hits([f for f in files if not TEST_RE.search(f)], config.get("nontrivial_globs") or [])
    added_loc = len(added)
    added_text = "\n".join(added)
    comment_lines = sum(1 for line in added if COMMENT_LINE_RE.match(line))
    deps_changed = any(DEPS_RE.search(f) for f in files)

    tracks: dict[str, str] = {}
    skipped: dict[str, str] = {}

    def take(track: str, cond: bool, why: str, why_not: str) -> None:
        if cond:
            tracks[track] = why
        else:
            skipped[track] = why_not

    if not code_files:
        return {
            "scope": scope if not base else f"base {base}",
            "changedFiles": files,
            "codeFiles": [],
            "addedLoc": added_loc,
            "nontrivialHits": hits,
            "zone": "trivial",
            "tracks": [],
            "verifiers": 1,
            "recommendation": "optout",
            "reasons": {},
            "skipped": {"*": "no code files changed"},
            "judgeQuestions": JUDGE_QUESTIONS,
        }

    zone = "high" if (hits or added_loc > LOC_HIGH_ZONE or len(code_files) > FILES_HIGH_ZONE) else "normal"

    if zone == "high":
        why = (
            f"non-trivial paths touched ({', '.join(hits[:3])}{'…' if len(hits) > 3 else ''})"
            if hits
            else f"large diff (+{added_loc} lines across {len(code_files)} code files)"
        )
        tracks = {t: why for t in ALL_TRACKS}
    else:
        take("correctness", True, "baseline for any code change", "")
        for track, rx, why in SIGNALS:
            take(track, bool(rx.search(added_text)), why, f"no matching pattern in the added lines ({why})")
        take(
            "tests",
            bool(src_files) and not test_files,
            f"{len(src_files)} source file(s) changed with no test file touched",
            "test files were touched alongside the source",
        )
        take(
            "comments",
            comment_lines >= COMMENT_LINES_MIN or "/**" in added_text or '"""' in added_text,
            f"{comment_lines} comment line(s) added",
            f"only {comment_lines} comment line(s) added",
        )
        take(
            "over-engineering",
            bool(new_code_files) or added_loc > LOC_OVERENGINEERING or deps_changed,
            "new files / sizeable addition / dependency change — room for speculative abstraction",
            f"+{added_loc} lines, no new files, no dependency change",
        )
        take(
            "simplify",
            bool(new_code_files) or added_loc >= LOC_SIMPLIFY,
            "enough new code for a simplification pass to pay off",
            f"+{added_loc} lines — too small for a simplifier pass to pay off",
        )

    return {
        "scope": scope if not base else f"base {base}",
        "changedFiles": files,
        "codeFiles": code_files,
        "newCodeFiles": new_code_files,
        "addedLoc": added_loc,
        "commentLinesAdded": comment_lines,
        "depsChanged": deps_changed,
        "nontrivialHits": hits,
        "zone": zone,
        "tracks": [t for t in ALL_TRACKS if t in tracks],
        "verifiers": 3 if zone == "high" else 1,
        "recommendation": "panel",
        "reasons": tracks,
        "skipped": skipped,
        "judgeQuestions": JUDGE_QUESTIONS,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="triage.py",
        description="Propose a review-track subset for a diff. Mechanical, deterministic, free.",
        epilog=(
            "SCOPE\n"
            "  --scope worktree   everything not in HEAD, staged or not, including untracked\n"
            "                     files. The default, and what a pre-commit panel always uses.\n"
            "  --scope staged     only the index.\n"
            "  --base <revision>  anything `git diff` accepts: main...HEAD, HEAD~3..HEAD, a sha.\n"
            "                     Overrides --scope.\n\n"
            "CONFIG (optional)\n"
            "  .claude/review-panel.json, else .claude/hooks/precommit-gate.json.\n"
            "  Only one key is read: nontrivial_globs — path patterns whose blast radius\n"
            "  justifies the full panel and three verifiers. Without it, zone is decided by\n"
            "  diff size alone.\n\n"
            "OUTPUT\n"
            "  recommendation=optout  no code files changed; record a reasoned skip instead\n"
            "                         of spending the panel on nothing.\n"
            "  recommendation=panel   tracks[] with a reason each in reasons{}, what was left\n"
            "                         out in skipped{}, verifiers (1 normally, 3 in the high\n"
            "                         zone), and judgeQuestions[] for the judge subagent.\n\n"
            "EXIT CODES\n"
            "  0  proposal printed\n"
            "  1  not a git repository, or git failed\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--repo", default=".", help="path inside the repository to triage (default: cwd)")
    parser.add_argument(
        "--scope", default="worktree", choices=["worktree", "staged"], help="what to diff (default: worktree)"
    )
    parser.add_argument("--base", help="diff against this revision instead of --scope")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    root = repo_root(args.repo)
    result = triage(root, load_config(root), args.scope, args.base)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"repo:        {root}")
    print(f"diff scope:  {result['scope']}")
    print(
        f"changed:     {len(result['changedFiles'])} file(s), "
        f"{len(result['codeFiles'])} code, +{result['addedLoc']} lines"
    )
    if result["nontrivialHits"]:
        print(f"non-trivial: {', '.join(result['nontrivialHits'])}")
    print(f"zone:        {result['zone']}")
    if result["recommendation"] == "optout":
        print("proposal:    SKIP the panel — no code changed. Record the skip with a reason instead.")
    else:
        print(f"proposal:    run {len(result['tracks'])}/{len(ALL_TRACKS)} tracks, verifiers={result['verifiers']}")
        if result["zone"] == "high":
            print(f"  all tracks — {result['reasons'][result['tracks'][0]]}")
            print("  the judge may only REMOVE tracks here, each with a stated reason")
        else:
            for t in result["tracks"]:
                print(f"  + {t:<17} {result['reasons'][t]}")
            for t, why in result["skipped"].items():
                if why:
                    print(f"  - {t:<17} {why}")
    print("\njudge must still decide (not mechanically detectable):")
    for q in result["judgeQuestions"]:
        print(f"  ? {q}")


if __name__ == "__main__":
    main()
