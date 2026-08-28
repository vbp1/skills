#!/usr/bin/env python3
"""Claude Code PreToolUse hook: proof-of-review barrier on `git commit`.

Sits alongside danger-guard.py on the Bash matcher. Turns the CLAUDE.md
pre-commit review gates (7 = pr-review-toolkit, 8 = code-simplifier,
11 = codex-review) from a prose instruction the agent has to *remember* into a
physical barrier on the act of committing.

Design:
  * NO-OP unless the repo being committed to has a project config at
    <main-checkout>/.claude/hooks/precommit-gate.json. This keeps the global
    engine inert in every repo except the ones that opt in (the "hybrid"
    placement). `.claude/` is git-ignored, so it exists in the main checkout
    only: config, credit and opt-out are all keyed to the root that
    `--git-common-dir` resolves to, and every worktree of a repo shares them,
    while the staged diff is always read from the working copy being committed.
  * Only ever intervenes on `git commit`. Anything else -> exit 0 immediately,
    so a bug here can never turn arbitrary Bash calls into permission prompts.
  * Review credit is content-addressed PER FILE and recorded PER GATE by
    precommit-gate-util.py `mark`: the review panel records gates 7,8 over the
    files it reviewed, the cross-agent review records gate 11 over the same
    content. Staging a reviewed file leaves its blob identical, so the credit
    still applies at commit time; editing it after the review does not, and a
    stale approval can never be replayed against changed content.
  * If the staged diff touches "non-trivial" paths (globs from the project
    config) and any of them lacks credit for a gate in config `require_gates`,
    emit permissionDecision = ask|deny (per config `mode`).
  * A marker written by an older version of the util (a single `git write-tree`
    fingerprint for the whole staged tree) is still honored as-is.
  * Honors an explicit opt-out marker (same fingerprint) so a deliberate skip is
    *recorded*, never silent — exactly the rule from feedback_precommit_gates.md.
  * `git commit -a/--all` bypasses the staged index, so it cannot be classified
    reliably; it is always asked, which also nudges toward the per-file staging
    that per-file staging already requires.

Output protocol matches danger-guard.py: a hookSpecificOutput JSON on stdout
with permissionDecision, then exit 0.

Within the commit check the hook fails CLOSED (ask) on any git/parse error — a
commit that cannot be verified should be confirmed by a human, not waved
through. Outside `git commit` it fails OPEN.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

PROJECT_CONFIG_REL = Path(".claude") / "hooks" / "precommit-gate.json"

# Subcommand splitting — same approach danger-guard.py uses, so a commit hidden
# inside a `&&` chain or a $(...) is still caught.
SHELL_SEPARATORS = re.compile(r"&&|\|\||\|&|;|\||&|\n")
SUBSHELL_RE = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")

DEFAULT_MARKER_REL = ".claude-review/precommit-pass.json"
DEFAULT_OPTOUT_REL = ".claude-review/precommit-optout.json"
DEFAULT_VERDICT = "APPROVED"


# --------------------------------------------------------------------------- #
# Output                                                                       #
# --------------------------------------------------------------------------- #
def emit(decision: str, reason: str) -> None:
    """Print a PreToolUse decision and exit. decision is 'ask' or 'deny'."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    json.dump(output, sys.stdout)
    sys.stdout.write("\n")
    sys.exit(0)


def allow() -> None:
    """Stay out of the way: no decision, normal flow continues."""
    sys.exit(0)


# --------------------------------------------------------------------------- #
# Command parsing                                                             #
# --------------------------------------------------------------------------- #
def expand_subshells(chunk: str) -> Iterable[str]:
    yield chunk
    stack = [chunk]
    while stack:
        current = stack.pop()
        for match in SUBSHELL_RE.finditer(current):
            inner = match.group(1) if match.group(1) is not None else match.group(2)
            if inner:
                yield inner
                stack.append(inner)


def split_subcommands(command: str) -> list[str]:
    parts: list[str] = []
    for chunk in expand_subshells(command):
        for segment in SHELL_SEPARATORS.split(chunk):
            segment = segment.strip()
            if segment:
                parts.append(segment)
    return parts


def is_git_commit(sub: str) -> bool:
    """True if the subcommand creates a commit (excludes log/show/dry-run/etc.)."""
    if not re.search(r"\bgit\b", sub):
        return False
    if not re.search(r"\bcommit\b", sub):
        return False
    if re.search(r"\bcommit-tree\b", sub):
        return False
    if "--dry-run" in sub:
        return False
    # Other git subcommands that merely contain the word "commit" in an arg.
    if re.search(r"\bgit\b\s+(?:-\S+\s+)*(log|show|rev-list|rev-parse|cherry|describe|tag|branch|diff)\b", sub):
        return False
    return True


def commit_stages_all(sub: str) -> bool:
    """True for `git commit -a` / `-am` / `--all`, which bypass the staged index."""
    for token in sub.split():
        if token == "--all":
            return True
        # short flag cluster containing 'a', e.g. -a, -am, -av  (but not --amend)
        if re.fullmatch(r"-[a-z]*a[a-z]*", token):
            return True
    return False


# --------------------------------------------------------------------------- #
# Repo / config                                                               #
# --------------------------------------------------------------------------- #
def git(root: str, *args: str) -> str:
    """Run a git command in `root`, return stdout (raises on failure)."""
    result = subprocess.run(
        ["git", "-C", root, *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def repo_root(cwd: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def config_root(root: str) -> str:
    """Root of the MAIN checkout — where the project config lives.

    A linked worktree has its own `--show-toplevel`, but `.claude/` is git-ignored
    and therefore exists only in the main checkout: a barrier keyed to the worktree
    finds no config and stands down exactly where isolated work happens.
    The review credit is the other way round — it stays in the working root, so
    two worktrees under review never overwrite each other's.
    `--git-common-dir` resolves to the main `.git` from every worktree of a repo,
    so its parent is the one root they all share. Anything else — a bare repo, a
    custom layout, a git that will not answer — keeps the working root, which lands
    on the pre-existing behaviour for that repo.
    """
    try:
        common = git(root, "rev-parse", "--git-common-dir").strip()
    except Exception:
        return root
    if not common:
        return root
    path = Path(common) if os.path.isabs(common) else Path(root) / common
    if path.name != ".git":
        return root
    parent = path.parent
    return str(parent) if parent.is_dir() else root


def load_config(root: str) -> dict | None:
    path = Path(root) / PROJECT_CONFIG_REL
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except Exception:
        # A malformed config in a repo that opted in: fail closed so the user
        # notices, but only because we already know this is a git commit.
        return {"__error__": f"unreadable {path}"}


def read_marker(path: Path) -> dict | None:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Coverage engine (shared with precommit-gate-util.py)                        #
# --------------------------------------------------------------------------- #
# `mark` writes the credit and this hook reads it, so both sides must agree on
# what a marker means. They share one implementation: the util module, loaded
# from this same directory. The functions used here are pure — they take the
# staged hashes and the marker and return the gap.
UTIL_PATH = Path(__file__).resolve().parent / "precommit-gate-util.py"


def load_util():
    import importlib.util as importlib_util

    spec = importlib_util.spec_from_file_location("precommit_gate_util", UTIL_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {UTIL_PATH}")
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def staged_blob_hashes(root: str, paths: list[str]) -> dict[str, str]:
    """Content hash of each path as the commit would carry it ('deleted' when staged for removal).

    The util has the same reader, but its git wrapper exits the process on failure —
    which for a CLI is right and for a hook is not. This one raises, so a git failure
    reaches the fail-closed handler and the user gets a prompt instead of a stack trace."""
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
    return {p: staged.get(p, "deleted") for p in paths}


# --------------------------------------------------------------------------- #
# Review-round store                                                          #
# --------------------------------------------------------------------------- #
# Mirrors .claude/scripts/review-round.sh: reports live beside the main checkout
# (resolved through --git-common-dir, so worktrees share one store) under the
# branch slug. Reading it lets the barrier tell "no review happened" apart from
# "the review happened and the marker step was skipped".
REVIEW_STORE_NAME = ".precommit-review"


ROUND_REPORT_RE = re.compile(r"^round-(\d+)\.md$")


def review_round_reports(root: str) -> tuple[str | None, list[str]]:
    """(store path, round report filenames in round order) for the branch being
    committed. Empty list when the store holds nothing for this branch."""
    try:
        common = git(root, "rev-parse", "--git-common-dir").strip()
    except Exception:
        return None, []
    if not common:
        return None, []
    common_path = Path(common) if os.path.isabs(common) else Path(root) / common
    try:
        branch = git(root, "symbolic-ref", "--short", "HEAD").strip() or "detached"
    except Exception:
        branch = "detached"
    store = common_path.parent / REVIEW_STORE_NAME / branch.replace("/", "-")
    try:
        numbered = [
            (int(m.group(1)), p.name)
            for p in store.glob("round-*.md")
            if (m := ROUND_REPORT_RE.match(p.name))
        ]
    except Exception:
        return None, []
    return str(store), [name for _, name in sorted(numbered)]


# --------------------------------------------------------------------------- #
# Classification                                                              #
# --------------------------------------------------------------------------- #
def staged_files(root: str) -> list[str]:
    out = git(root, "diff", "--cached", "--name-only", "-z")
    return [p for p in out.split("\0") if p]


def nontrivial_hits(files: list[str], globs: list[str]) -> list[str]:
    hits: list[str] = []
    for f in files:
        if any(fnmatch.fnmatch(f, g) for g in globs):
            hits.append(f)
    return hits


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #
def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # Can't tell what this is -> not our concern, stay open.
        allow()

    if payload.get("tool_name") != "Bash":
        allow()

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") or ""
    if not command.strip():
        allow()

    commit_subs = [s for s in split_subcommands(command) if is_git_commit(s)]
    if not commit_subs:
        allow()

    # From here on we know this is a git commit -> fail CLOSED on any trouble.
    cwd = payload.get("cwd") or os.getcwd()
    root = repo_root(cwd)
    if not root:
        # commit outside a detectable repo: not ours to police.
        allow()

    croot = config_root(root)
    config = load_config(croot)
    if config is None:
        # Repo did not opt in -> barrier inactive here.
        allow()
    if config.get("__error__"):
        emit("ask", f"[precommit-gate] {config['__error__']} — fix the project config or stage manually.")

    mode = config.get("mode") if config.get("mode") in ("ask", "deny") else "ask"
    globs = config.get("nontrivial_globs") or []
    label = config.get("label") or "pre-commit review gates"
    # Credit belongs to the working root, not the shared one: two worktrees are
    # two independent pieces of work, and one entry per gate set means a shared
    # store would let each new credit delete the other's.
    marker_path = Path(root) / (config.get("marker_path") or DEFAULT_MARKER_REL)
    optout_path = Path(root) / (config.get("optout_path") or DEFAULT_OPTOUT_REL)
    require_verdict = config.get("require_verdict") or DEFAULT_VERDICT

    # `git commit -a` bypasses the staged index we inspect -> always confirm,
    # and steer toward per-file staging.
    if any(commit_stages_all(s) for s in commit_subs):
        emit(
            mode,
            f"[precommit-gate] `git commit -a/--all` bypasses staged-diff inspection for {label}. "
            "Stage per file (`git add <path>`), then commit without -a so the review barrier can verify it.",
        )

    try:
        files = staged_files(root)
    except Exception as exc:
        emit("ask", f"[precommit-gate] could not read staged diff ({type(exc).__name__}); confirm manually.")

    if not files:
        # Nothing staged (e.g. an empty/--amend-only commit) -> not our call.
        allow()

    hits = nontrivial_hits(files, globs)
    if not hits:
        # Trivial diff (docs / formatting / dep-bump / paths outside the zones).
        allow()

    try:
        fingerprint = git(root, "write-tree").strip()
    except Exception as exc:
        emit("ask", f"[precommit-gate] could not fingerprint staged tree ({type(exc).__name__}); confirm manually.")

    # Explicit, recorded opt-out for exactly this staged content.
    optout = read_marker(optout_path)
    if optout and optout.get("fingerprint") == fingerprint:
        allow()

    marker = read_marker(marker_path)

    # A marker from an older util: one fingerprint for the whole staged tree.
    if marker and marker.get("version") is None:
        if marker.get("fingerprint") == fingerprint and marker.get("verdict") == require_verdict:
            allow()

    require_gates = [str(g) for g in (config.get("require_gates") or [])]
    try:
        util = load_util()
        staged_hashes = staged_blob_hashes(root, hits)
        missing = util.missing_coverage(marker, staged_hashes, require_verdict, require_gates)
    except Exception as exc:
        emit("ask", f"[precommit-gate] could not evaluate review coverage ({type(exc).__name__}: {exc}); confirm manually.")

    if not missing:
        allow()

    shown = hits[:6]
    more = f" (+{len(hits) - len(shown)} more)" if len(hits) > len(shown) else ""

    # Name the gap per gate: which review is missing, and for how many staged
    # files — "the panel ran but codex did not" and "the panel ran before you
    # edited this file again" are different problems with different next steps.
    gaps = []
    for gate, paths in missing.items():
        head = ", ".join(paths[:3]) + (f" (+{len(paths) - 3} more)" if len(paths) > 3 else "")
        gaps.append(("no review recorded" if gate == "review" else f"gate {gate} missing") + f" for {head}")
    gap_text = "; ".join(gaps)

    evidence = ""
    covered_gates = sorted({str(g) for e in (marker.get("entries") or []) if isinstance(e, dict) for g in e.get("gates") or []}) if marker else []
    if covered_gates:
        evidence = f" Credit already recorded on this branch for gate(s) {','.join(covered_gates)}."
    else:
        store, reports = review_round_reports(root)
        if reports:
            evidence = (
                f" Review rounds are already written for this branch: {len(reports)}, latest "
                f"{reports[-1]} in {store}. If that review covers this diff, the missing step is `mark`."
            )

    reason = (
        f"[precommit-gate] {label} not proven for this staged diff. "
        f"Non-trivial paths staged: {', '.join(shown)}{more}. {gap_text}.{evidence} "
        "After a clean review panel run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/precommit-gate-util.py mark --repo "
        f"{root} --gates 7,8`; after a codex APPROVED verdict the same with `--gates 11`; /ship does "
        "both for you. To skip deliberately: "
        "`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/precommit-gate-util.py optout --repo "
        f"{root} --reason \"...\"`."
    )
    emit(mode, reason)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        # Unknown failure: we only reach deep logic once a commit is confirmed,
        # so fail closed.
        emit("ask", f"[precommit-gate] runtime error: {type(exc).__name__}: {exc}")
