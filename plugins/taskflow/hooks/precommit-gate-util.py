#!/usr/bin/env python3
"""precommit-gate-util — companion CLI for the precommit-gate.py PreToolUse hook.

The hook (${CLAUDE_PLUGIN_ROOT}/hooks/precommit-gate.py) blocks a `git commit` that touches
non-trivial paths until every staged non-trivial file carries review credit for
every gate the project requires. This tool is how that credit gets recorded, how
a deliberate skip is recorded, and how you inspect the current state.

Credit is content-addressed PER FILE: `mark` stores the content hash of each
file the review covered, under the gate ids that review satisfies. Staging those
same files afterwards leaves their content identical, so the credit still
applies at commit time; editing a file after the review does not.

SUBCOMMANDS
  mark      Record review credit (verdict APPROVED) for the files a review
            covered, under its gate ids: `--gates 7,8` after the review panel,
            `--gates 11` after the cross-agent review. Entries accumulate.
            Call it only AFTER that review actually passed.
  optout    Record an explicit, reasoned skip for the current staged tree.
  status    Show the current fingerprint, staged non-trivial files, and what the
            barrier would decide right now.
  triage    Propose which review-panel tracks this diff actually needs, from
            mechanical signals only. Feeds the review panel.

Run `precommit-gate-util <subcommand> --help` for per-command options.

EXIT CODES
  0  success
  1  not a git repo / no project config / git failure / bad arguments
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_CONFIG_REL = Path(".claude") / "hooks" / "precommit-gate.json"
DEFAULT_MARKER_REL = ".claude-review/precommit-pass.json"
DEFAULT_OPTOUT_REL = ".claude-review/precommit-optout.json"
DEFAULT_VERDICT = "APPROVED"


def die(msg: str) -> None:
    sys.stderr.write(f"precommit-gate-util: {msg}\n")
    sys.exit(1)


def git(root: str, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", root, *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        die("git not found on PATH")
    except subprocess.CalledProcessError as exc:
        die(f"git {' '.join(args)} failed: {exc.stderr.strip() or exc}")
    return result.stdout


def repo_root(start: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", start, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        die(f"not inside a git repository: {start}")
    root = out.stdout.strip()
    if not root:
        die(f"not inside a git repository: {start}")
    return root


def config_root(root: str) -> str:
    """Root of the MAIN checkout — where the project config lives.

    A linked worktree has its own `--show-toplevel`, but `.claude/` is git-ignored
    and therefore exists only in the main checkout: a barrier keyed to the worktree
    finds no config and stands down exactly where isolated work happens.
    The review credit is the other way round — it stays in the working root, so
    two worktrees under review never overwrite each other's.
    `--git-common-dir` resolves to the main `.git` from every worktree of a repo,
    so its parent is the one root they all share. Anything that is not a `.git`
    directory (a bare repo, a custom layout) keeps the working root as it was.
    """
    try:
        out = subprocess.run(
            ["git", "-C", root, "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return root
    common = out.stdout.strip()
    if not common:
        return root
    path = Path(common) if os.path.isabs(common) else Path(root) / common
    if path.name != ".git":
        return root
    parent = path.parent
    return str(parent) if parent.is_dir() else root


def load_config(root: str) -> dict:
    path = Path(root) / PROJECT_CONFIG_REL
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        die(f"no project config at {path} — this repo has not opted into the barrier")
    except json.JSONDecodeError as exc:
        die(f"malformed config {path}: {exc}")
    return {}  # unreachable


def fingerprint(root: str) -> str:
    fp = git(root, "write-tree").strip()
    if not fp:
        die("git write-tree returned nothing (corrupt index?)")
    return fp


def staged_files(root: str) -> list[str]:
    out = git(root, "diff", "--cached", "--name-only", "-z")
    return [p for p in out.split("\0") if p]


def nontrivial_hits(files: list[str], globs: list[str]) -> list[str]:
    return [f for f in files if any(fnmatch.fnmatch(f, g) for g in globs)]


# --------------------------------------------------------------------------- #
# Per-file review coverage                                                    #
# --------------------------------------------------------------------------- #
# A marker records the content hash of every file a review covered, gate by
# gate. The barrier then asks, per staged file: is THIS blob proven for every
# required gate? Staging a reviewed file, or staging it in a different order,
# leaves its blob identical, so the credit survives `git add`; editing it after
# the review changes the blob, so the credit does not.
MARKER_VERSION = 2
DELETED = "deleted"
COVERAGE_EXCLUDES = (".precommit-review/", ".claude-review/")


def _covered_path(path: str) -> bool:
    return not any(path.startswith(prefix) for prefix in COVERAGE_EXCLUDES)


def reviewed_paths(root: str, scope: str, base: str | None) -> list[str]:
    """The files a review of `scope` looked at."""
    if base:
        out = git(root, "diff", "--name-only", "-z", base)
        paths = [p for p in out.split("\0") if p]
    elif scope == "staged":
        paths = staged_files(root)
    else:
        out = git(root, "diff", "HEAD", "--name-only", "-z")
        paths = [p for p in out.split("\0") if p] + untracked_files(root)
    return sorted({p for p in paths if _covered_path(p)})


def worktree_hashes(root: str, paths: list[str]) -> dict[str, str]:
    """Content hash of each path as it stands in the working tree."""
    hashes: dict[str, str] = {}
    for path in paths:
        full = Path(root) / path
        if full.is_file():
            hashes[path] = git(root, "hash-object", "--", path).strip()
        else:
            hashes[path] = DELETED
    return hashes


def index_hashes(root: str, paths: list[str]) -> dict[str, str]:
    """Content hash of each path as it stands in the index — what a commit would carry."""
    if not paths:
        return {}
    out = git(root, "ls-files", "-s", "-z", "--", *paths)
    staged: dict[str, str] = {}
    for record in out.split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        fields = meta.split()
        if len(fields) >= 2 and path:
            staged[path] = fields[1]
    return {p: staged.get(p, DELETED) for p in paths}


def marker_entries(marker: dict | None) -> list[dict]:
    if not marker or marker.get("version") != MARKER_VERSION:
        return []
    entries = marker.get("entries")
    return entries if isinstance(entries, list) else []


def gates_per_path(marker: dict | None, staged: dict[str, str], require_verdict: str) -> dict[str, set[str]]:
    """For each staged path: the gate ids proven for exactly that content."""
    entries = marker_entries(marker)
    proven: dict[str, set[str]] = {}
    for path, blob in staged.items():
        gates: set[str] = set()
        for entry in entries:
            if entry.get("verdict") != require_verdict:
                continue
            if (entry.get("files") or {}).get(path) == blob:
                gates.update(str(g) for g in entry.get("gates") or [])
        proven[path] = gates
    return proven


def missing_coverage(
    marker: dict | None,
    staged: dict[str, str],
    require_verdict: str,
    require_gates: list[str],
) -> dict[str, list[str]]:
    """gate id -> staged paths that gate does not cover. Empty dict = the barrier passes.

    With no `require_gates` configured, a single key `review` reports the paths no
    marker covers at all."""
    proven = gates_per_path(marker, staged, require_verdict)
    if not require_gates:
        uncovered = sorted(p for p, gates in proven.items() if not gates)
        return {"review": uncovered} if uncovered else {}
    missing: dict[str, list[str]] = {}
    for gate in require_gates:
        gap = sorted(p for p, gates in proven.items() if gate not in gates)
        if gap:
            missing[gate] = gap
    return missing


def load_config_soft(root: str) -> dict:
    """Like load_config, but a missing/broken config is not fatal — triage still works."""
    path = Path(root) / PROJECT_CONFIG_REL
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def marker_paths(root: str, config: dict) -> tuple[Path, Path]:
    marker = Path(root) / (config.get("marker_path") or DEFAULT_MARKER_REL)
    optout = Path(root) / (config.get("optout_path") or DEFAULT_OPTOUT_REL)
    return marker, optout


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def read_json(path: Path) -> dict | None:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Triage — mechanical track selection for the pre-commit review panel         #
# --------------------------------------------------------------------------- #
CODE_RE = re.compile(r"\.(ts|tsx|js|jsx|mjs|cjs)$")
TEST_RE = re.compile(r"\.(test|spec)\.(ts|tsx|js|jsx)$")
COMMENT_LINE_RE = re.compile(r"^\s*(//|/\*|\*|#)")

# Each signal turns ADDED diff lines into one review track. Deliberately
# syntactic: everything that needs judgment is left to the judge subagent (see
# JUDGE_QUESTIONS) rather than guessed at here with a fancier regex.
SIGNALS = [
    (
        "silent-failures",
        re.compile(r"\btry\b|\bcatch\b|\bfinally\b|\.catch\(|\?\?|console\.(error|warn)|\bthrow\b|Promise\.(all|allSettled|race)"),
        "error handling / fallback / rejection paths in the added lines",
    ),
    (
        "type-design",
        re.compile(r"\binterface\b|\btype\s+\w+\s*=|\benum\b|\bz\.[a-z]|\bsatisfies\b|as\s+unknown|export\s+(type|interface)|:\s*Promise<"),
        "types, zod schemas or exported signatures touched",
    ),
    (
        "adversary",
        re.compile(r"\bif\s*\(|\bfor\s*\(|\bwhile\s*\(|\bswitch\s*\(|\.map\(|\.filter\(|\.reduce\(|JSON\.parse|new RegExp|\.split\(|parseInt|Number\("),
        "branching / parsing logic in the added lines",
    ),
]

ALL_TRACKS = ["correctness", "silent-failures", "type-design", "tests", "comments", "adversary", "over-engineering", "simplify"]

# What the regexes structurally cannot decide — handed to the judge subagent.
JUDGE_QUESTIONS = [
    "Is this a BUG FIX? If so the tests track is mandatory (regression test that fails without the fix), even when tests were already touched.",
    "Does it change a contract other code depends on — exported signature, wire format at the shell<->Core boundary, provider option, DB column semantics? If so add type-design + correctness regardless of size.",
    "Is a SMALL diff sitting on a dangerous path (auth, permissions, migrations, scheduler, money/retry loops)? Size is not risk.",
    "Is a LARGE diff mechanical (rename, move, formatting, generated file)? Then most tracks are noise — say which to drop and why.",
    "Was a helper/factory extracted that many call sites now route through? That widens blast radius beyond the changed lines.",
]

LOC_OVERENGINEERING = 80  # added LOC above which the over-engineering lens earns its slot
LOC_SIMPLIFY = 100
LOC_HIGH_ZONE = 200
FILES_HIGH_ZONE = 10
COMMENT_LINES_MIN = 5


def diff_args(scope: str, base: str | None) -> list[str]:
    if base:
        return ["diff", base]
    if scope == "staged":
        return ["diff", "--cached"]
    return ["diff", "HEAD"]


def untracked_files(root: str) -> list[str]:
    out = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    return [p for p in out.split("\0") if p]


def collect_changes(root: str, scope: str, base: str | None) -> dict:
    """Changed paths + the ADDED text of the diff (untracked files count as fully added)."""
    name_out = git(root, *diff_args(scope, base), "--name-only", "-z")
    files = [p for p in name_out.split("\0") if p]
    new_out = git(root, *diff_args(scope, base), "--name-only", "--diff-filter=A", "-z")
    new_files = [p for p in new_out.split("\0") if p]

    untracked: list[str] = []
    if scope != "staged":
        untracked = untracked_files(root)
        files += untracked
        new_files += untracked

    added: list[str] = []
    patch = git(root, *diff_args(scope, base), "-U0")
    for line in patch.splitlines():
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
    # Zone is about production blast radius, so a *.test.ts sitting under lib/db or
    # src/core must not drag the whole panel in. The commit barrier itself still
    # counts every staged path — that is its job, not this one.
    hits = nontrivial_hits([f for f in files if not TEST_RE.search(f)], config.get("nontrivial_globs") or [])
    added_loc = len(added)
    added_text = "\n".join(added)
    comment_lines = sum(1 for l in added if COMMENT_LINE_RE.match(l))
    deps_changed = any(f.endswith("package.json") for f in files)

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
            comment_lines >= COMMENT_LINES_MIN or "/**" in added_text,
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
        "recommendation": "panel",
        "reasons": tracks,
        "skipped": skipped,
        "judgeQuestions": JUDGE_QUESTIONS,
    }


def cmd_triage(args: argparse.Namespace) -> None:
    root = repo_root(args.repo)
    config = load_config_soft(config_root(root))
    result = triage(root, config, args.scope, args.base)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"repo:        {root}")
    print(f"diff scope:  {result['scope']}")
    print(f"changed:     {len(result['changedFiles'])} file(s), {len(result['codeFiles'])} code, +{result['addedLoc']} lines")
    if result["nontrivialHits"]:
        print(f"non-trivial: {', '.join(result['nontrivialHits'])}")
    print(f"zone:        {result['zone']}")
    if result["recommendation"] == "optout":
        print("proposal:    SKIP the panel — no code changed. Record an opt-out with a reason instead.")
    else:
        print(f"proposal:    run {len(result['tracks'])}/{len(ALL_TRACKS)} tracks")
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


# --------------------------------------------------------------------------- #
# Subcommands                                                                 #
# --------------------------------------------------------------------------- #
MAX_MARKER_ENTRIES = 12


def barrier_gap_lines(root: str, config: dict, marker: dict | None) -> list[str]:
    """What the barrier would still be missing for the current staged tree."""
    globs = config.get("nontrivial_globs") or []
    require_gates = [str(g) for g in (config.get("require_gates") or [])]
    require_verdict = config.get("require_verdict") or DEFAULT_VERDICT
    hits = nontrivial_hits(staged_files(root), globs)
    if not hits:
        return ["nothing non-trivial staged — the barrier allows this commit as it stands"]
    missing = missing_coverage(marker, index_hashes(root, hits), require_verdict, require_gates)
    if not missing:
        return [f"all {len(hits)} staged non-trivial file(s) covered — the barrier allows this commit"]
    lines = []
    for gate, paths in missing.items():
        shown = ", ".join(paths[:4]) + (f" (+{len(paths) - 4} more)" if len(paths) > 4 else "")
        label = "no review recorded for" if gate == "review" else f"gate {gate} missing for"
        lines.append(f"{label} {len(paths)} staged file(s): {shown}")
    return lines


def cmd_mark(args: argparse.Namespace) -> None:
    root = repo_root(args.repo)
    croot = config_root(root)
    config = load_config(croot)
    marker, _ = marker_paths(root, config)
    gates = [g.strip() for g in (args.gates or "").split(",") if g.strip()]
    if not gates:
        die("--gates needs at least one gate id (e.g. --gates 7,8 for the review panel, --gates 11 for the cross-agent review)")

    scope = "base" if args.base else args.scope
    paths = reviewed_paths(root, args.scope, args.base)
    files = index_hashes(root, paths) if scope == "staged" else worktree_hashes(root, paths)

    entry = {
        "gates": gates,
        "verdict": args.verdict,
        "scope": args.base or scope,
        "ts": args.ts,  # caller supplies a timestamp string if desired
        "note": args.note or "",
        "files": files,
    }
    existing = read_json(marker)
    # One entry per gate set: re-running a review replaces its own credit and
    # leaves the other gates' credit standing.
    kept = [e for e in marker_entries(existing) if sorted(e.get("gates") or []) != sorted(gates)]
    record = {"version": MARKER_VERSION, "entries": (kept + [entry])[-MAX_MARKER_ENTRIES:]}
    write_json(marker, record)

    print(f"marked {marker} verdict={args.verdict} gates={','.join(gates)} files={len(files)} scope={entry['scope']}")
    for line in barrier_gap_lines(root, config, record):
        print(f"  {line}")


def cmd_optout(args: argparse.Namespace) -> None:
    root = repo_root(args.repo)
    croot = config_root(root)
    config = load_config(croot)
    _, optout = marker_paths(root, config)
    fp = fingerprint(root)
    record = {
        "fingerprint": fp,
        "reason": args.reason,
        "ts": args.ts,
    }
    write_json(optout, record)
    print(f"opt-out recorded {optout} fingerprint={fp[:10]} reason={args.reason!r}")


def cmd_status(args: argparse.Namespace) -> None:
    root = repo_root(args.repo)
    croot = config_root(root)
    config = load_config(croot)
    marker, optout = marker_paths(root, config)
    globs = config.get("nontrivial_globs") or []
    require_verdict = config.get("require_verdict") or DEFAULT_VERDICT
    mode = config.get("mode") or "ask"

    fp = fingerprint(root)
    files = staged_files(root)
    hits = nontrivial_hits(files, globs)

    require_gates = [str(g) for g in (config.get("require_gates") or [])]

    m = read_json(marker)
    o = read_json(optout)
    legacy_ok = bool(
        m and m.get("version") is None and m.get("fingerprint") == fp and m.get("verdict") == require_verdict
    )
    missing = missing_coverage(m, index_hashes(root, hits), require_verdict, require_gates) if hits else {}
    marker_ok = legacy_ok or (bool(hits) and not missing)
    optout_ok = bool(o and o.get("fingerprint") == fp)

    if not files:
        verdict = "allow (nothing staged)"
    elif not hits:
        verdict = "allow (trivial: no non-trivial paths staged)"
    elif marker_ok:
        verdict = "allow (review covers every staged non-trivial file)"
    elif optout_ok:
        verdict = "allow (explicit opt-out)"
    else:
        verdict = f"{mode.upper()} (non-trivial, review coverage incomplete)"

    print(f"repo:           {root}")
    print(f"mode:           {mode}")
    print(f"staged tree fp: {fp}")
    print(f"staged files:   {len(files)}")
    print(f"non-trivial:    {len(hits)}")
    for h in hits[:20]:
        print(f"  - {h}")
    if len(hits) > 20:
        print(f"  ... (+{len(hits) - 20} more)")
    print(f"required gates: {','.join(require_gates) or '- (any recorded review)'}")
    print(f"marker:         {'OK' if marker_ok else 'incomplete'} ({marker})")
    for entry in marker_entries(m):
        print(
            f"  gates={','.join(str(g) for g in entry.get('gates') or []) or '-'} "
            f"verdict={entry.get('verdict')} scope={entry.get('scope')} files={len(entry.get('files') or {})}"
            + (f" note={entry.get('note')!r}" if entry.get("note") else "")
        )
    if legacy_ok:
        print(f"  legacy tree-fingerprint marker accepted (fp={str(m.get('fingerprint'))[:10]})")
    for gate, paths in missing.items():
        shown = ", ".join(paths[:6]) + (f" (+{len(paths) - 6} more)" if len(paths) > 6 else "")
        label = "no review recorded" if gate == "review" else f"gate {gate} missing"
        print(f"  {label} for {len(paths)} staged file(s): {shown}")
    print(f"opt-out:        {'OK' if optout_ok else 'none/stale'} ({optout})")
    if o:
        print(f"  reason={o.get('reason')!r} fp={str(o.get('fingerprint'))[:10]}")
    print(f"barrier verdict: {verdict}")


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="precommit-gate-util",
        description=(
            "Companion CLI for the precommit-gate.py PreToolUse barrier. Records review "
            "credit per file and per gate (mark), records a deliberate skip (optout), and "
            "inspects the current barrier state (status). Credit is content-addressed per "
            "file, so it survives `git add` and expires the moment a file is edited again."
        ),
        epilog=(
            "Examples:\n"
            "  precommit-gate-util status --repo /path/to/repo\n"
            "  precommit-gate-util mark   --repo /path/to/repo --gates 7,8 --note 'panel: correctness, tests'\n"
            "  precommit-gate-util mark   --repo /path/to/repo --gates 11 --note 'codex APPROVED'\n"
            "  precommit-gate-util optout --repo /path/to/repo --reason 'mechanical rename, no logic change'\n"
            "\n"
            "Exit codes: 0 success; 1 not-a-repo / no-config / git-failure / bad-args."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_repo(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--repo",
            default=".",
            help="Path inside the target git repo (default: current directory). "
            "The repo root and its .claude/hooks/precommit-gate.json are resolved from here.",
        )

    p_mark = sub.add_parser(
        "mark",
        help="Record a passed review, gate by gate, against the reviewed file contents.",
        description="Record the content hash of every file the review covered, under the gate "
        "ids that review satisfies. The barrier allows a commit when every staged non-trivial "
        "file carries that credit for every required gate. Marks accumulate: `--gates 7,8` from "
        "the review panel and `--gates 11` from the cross-agent review sit side by side, and "
        "re-running one replaces only its own entry. Call it only after the review actually "
        "passed — the barrier trusts it.",
    )
    add_repo(p_mark)
    p_mark.add_argument("--verdict", default=DEFAULT_VERDICT, help=f"Verdict to record (default: {DEFAULT_VERDICT}; must match config require_verdict).")
    p_mark.add_argument("--gates", default="", required=True, help="Comma-separated gate ids this review satisfies: '7,8' for the review panel, '11' for the cross-agent review.")
    p_mark.add_argument(
        "--scope",
        choices=["worktree", "staged"],
        default="worktree",
        help="Which files the review covered: 'worktree' = everything not in HEAD incl. untracked, "
        "hashed from the working tree (default, matches the panel); 'staged' = the index only.",
    )
    p_mark.add_argument("--base", default=None, help="The review covered the diff against this ref (e.g. main...HEAD); overrides --scope.")
    p_mark.add_argument("--note", default="", help="Optional free-text note stored in the marker (e.g. which tracks ran).")
    p_mark.add_argument("--ts", default="", help="Optional timestamp string to store (caller-supplied; the tool does not read the clock).")
    p_mark.set_defaults(func=cmd_mark)

    p_opt = sub.add_parser(
        "optout",
        help="Record an explicit, reasoned skip for the current staged tree.",
        description="Write an opt-out marker for the CURRENT staged tree so the skip is "
        "recorded rather than silent (per feedback_precommit_gates.md Rule 3).",
    )
    add_repo(p_opt)
    p_opt.add_argument("--reason", required=True, help="Why the gates are being skipped for this diff (required).")
    p_opt.add_argument("--ts", default="", help="Optional timestamp string to store.")
    p_opt.set_defaults(func=cmd_optout)

    p_tr = sub.add_parser(
        "triage",
        help="Propose which review-panel tracks this diff needs (mechanical signals only).",
        description="Scan the diff for syntactic signals and propose a subset of review-panel "
        "tracks, with a reason per track kept and per track skipped. Decides nothing that needs "
        "judgment — it prints the open questions for a judge subagent instead. The --json output "
        "names the tracks to spawn.",
    )
    add_repo(p_tr)
    p_tr.add_argument(
        "--scope",
        choices=["worktree", "staged"],
        default="worktree",
        help="Which diff to triage: 'worktree' = everything not in HEAD incl. untracked (default, matches the panel's default); "
        "'staged' = the staged index only (use from /ship, matches the commit barrier).",
    )
    p_tr.add_argument("--base", default=None, help="Triage against a base ref instead (e.g. origin/main); overrides --scope.")
    p_tr.add_argument("--json", action="store_true", help="Machine-readable output for the review workflow.")
    p_tr.set_defaults(func=cmd_triage)

    p_st = sub.add_parser(
        "status",
        help="Show fingerprint, staged non-trivial files, and the barrier verdict.",
        description="Inspect what the barrier would decide for the current staged tree.",
    )
    add_repo(p_st)
    p_st.set_defaults(func=cmd_status)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
