#!/usr/bin/env python3
"""Selftest for precommit-gate.py + precommit-gate-util.py.

Builds a throwaway git repo in a temp dir, drives the hook exactly the way Claude
Code does (a PreToolUse JSON payload on stdin) and asserts the decision for every
case the barrier has to get right: review credit surviving `git add`, credit
expiring when a file is edited again, a missing gate blocking on its own, the
legacy single-fingerprint marker, opt-out, trivial diffs, and `git commit -a`.

USAGE
  python3 ~/.claude/hooks/precommit-gate-selftest.py [--verbose]

  --verbose   print passing cases too (failures always print)

EXIT CODES
  0  every case passed
  1  at least one case failed
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
GATE = HOOKS / "precommit-gate.py"
UTIL = HOOKS / "precommit-gate-util.py"

CONFIG = {
    "mode": "ask",
    "label": "selftest gates",
    "require_verdict": "APPROVED",
    "require_gates": ["7", "8", "11"],
    "nontrivial_globs": ["*lib/db/*"],
}


def run(*args: str, cwd: str) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def git(repo: str, *args: str) -> str:
    return run("git", "-C", repo, *args, cwd=repo)


def util(repo: str, subcommand: str, *args: str) -> str:
    return run(sys.executable, str(UTIL), subcommand, "--repo", repo, *args, cwd=repo)


def decide(repo: str, command: str = "git commit -m x") -> str:
    """'allow' or the hook's permissionDecision for this command."""
    payload = json.dumps({"tool_name": "Bash", "cwd": repo, "tool_input": {"command": command}})
    result = subprocess.run(
        [sys.executable, str(GATE)], input=payload, capture_output=True, text=True, cwd=repo
    )
    if result.returncode != 0:
        raise RuntimeError(f"hook exited {result.returncode}: {result.stderr.strip()}")
    if not result.stdout.strip():
        return "allow"
    return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]


def fresh_repo(tmp: str) -> str:
    repo = str(Path(tmp) / "repo")
    Path(repo, ".claude", "hooks").mkdir(parents=True)
    Path(repo, "src", "lib", "db").mkdir(parents=True)
    run("git", "init", "-q", repo, cwd=tmp)
    git(repo, "config", "user.email", "selftest@example.com")
    git(repo, "config", "user.name", "selftest")
    Path(repo, ".git", "info", "exclude").write_text(".claude/\n.claude-review/\n", encoding="utf-8")
    Path(repo, ".claude", "hooks", "precommit-gate.json").write_text(json.dumps(CONFIG), encoding="utf-8")
    Path(repo, "src", "lib", "db", "schema.ts").write_text("v1\n", encoding="utf-8")
    Path(repo, "README.md").write_text("docs\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    return repo


def marker(repo: str) -> Path:
    return Path(repo, ".claude-review", "precommit-pass.json")


def add_worktree(repo: str) -> str:
    """A linked worktree of `repo`, the way an isolated task runs. It carries no
    `.claude/` of its own — that directory is git-ignored and lives in the main
    checkout only."""
    return add_named_worktree(repo, "wt", "task/selftest")


def add_named_worktree(repo: str, name: str, branch: str) -> str:
    wt = str(Path(repo).parent / name)
    git(repo, "worktree", "add", "-q", wt, "-b", branch)
    return wt


# --------------------------------------------------------------------------- #
# Cases: each returns (name, expected, actual)                                #
# --------------------------------------------------------------------------- #
def case_credit_survives_staging(repo: str) -> tuple[str, str]:
    Path(repo, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    util(repo, "mark", "--gates", "7,8")
    util(repo, "mark", "--gates", "11")
    git(repo, "add", "src/lib/db/schema.ts")  # the step that used to invalidate it
    return "allow", decide(repo)


def case_missing_gate_blocks(repo: str) -> tuple[str, str]:
    Path(repo, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    util(repo, "mark", "--gates", "7,8")
    git(repo, "add", "src/lib/db/schema.ts")
    return "ask", decide(repo)


def case_edit_after_review_expires(repo: str) -> tuple[str, str]:
    Path(repo, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    util(repo, "mark", "--gates", "7,8")
    util(repo, "mark", "--gates", "11")
    Path(repo, "src/lib/db/schema.ts").write_text("v3-unreviewed\n", encoding="utf-8")
    git(repo, "add", "src/lib/db/schema.ts")
    return "ask", decide(repo)


def case_new_file_not_covered(repo: str) -> tuple[str, str]:
    Path(repo, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    util(repo, "mark", "--gates", "7,8")
    util(repo, "mark", "--gates", "11")
    Path(repo, "src/lib/db/other.ts").write_text("unreviewed\n", encoding="utf-8")
    git(repo, "add", "src/lib/db/schema.ts", "src/lib/db/other.ts")
    return "ask", decide(repo)


def case_untracked_then_staged(repo: str) -> tuple[str, str]:
    Path(repo, "src/lib/db/fresh.ts").write_text("brand new\n", encoding="utf-8")
    util(repo, "mark", "--gates", "7,8")
    util(repo, "mark", "--gates", "11")
    git(repo, "add", "src/lib/db/fresh.ts")
    return "allow", decide(repo)


def case_deletion_covered(repo: str) -> tuple[str, str]:
    Path(repo, "src/lib/db/schema.ts").unlink()
    util(repo, "mark", "--gates", "7,8")
    util(repo, "mark", "--gates", "11")
    git(repo, "add", "-A", "src/lib/db/schema.ts")
    return "allow", decide(repo)


def case_legacy_marker_accepted(repo: str) -> tuple[str, str]:
    Path(repo, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    git(repo, "add", "src/lib/db/schema.ts")
    fp = git(repo, "write-tree").strip()
    marker(repo).parent.mkdir(parents=True, exist_ok=True)
    marker(repo).write_text(json.dumps({"fingerprint": fp, "verdict": "APPROVED", "gates": ["7", "8", "11"]}), encoding="utf-8")
    return "allow", decide(repo)


def case_legacy_marker_stale(repo: str) -> tuple[str, str]:
    Path(repo, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    git(repo, "add", "src/lib/db/schema.ts")
    marker(repo).parent.mkdir(parents=True, exist_ok=True)
    marker(repo).write_text(json.dumps({"fingerprint": "deadbeef", "verdict": "APPROVED", "gates": ["7"]}), encoding="utf-8")
    return "ask", decide(repo)


def case_optout(repo: str) -> tuple[str, str]:
    Path(repo, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    git(repo, "add", "src/lib/db/schema.ts")
    util(repo, "optout", "--reason", "mechanical rename")
    return "allow", decide(repo)


def case_trivial_diff(repo: str) -> tuple[str, str]:
    Path(repo, "README.md").write_text("docs\nmore\n", encoding="utf-8")
    git(repo, "add", "README.md")
    return "allow", decide(repo)


def case_commit_all_asks(repo: str) -> tuple[str, str]:
    Path(repo, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    util(repo, "mark", "--gates", "7,8")
    util(repo, "mark", "--gates", "11")
    git(repo, "add", "src/lib/db/schema.ts")
    return "ask", decide(repo, "git commit -am x")


def case_non_commit_untouched(repo: str) -> tuple[str, str]:
    Path(repo, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    git(repo, "add", "src/lib/db/schema.ts")
    return "allow", decide(repo, "git log --oneline")


def case_no_require_gates(repo: str) -> tuple[str, str]:
    """A repo that lists no required gates: any recorded review credit is enough."""
    config = dict(CONFIG)
    config.pop("require_gates")
    Path(repo, ".claude", "hooks", "precommit-gate.json").write_text(json.dumps(config), encoding="utf-8")
    Path(repo, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    util(repo, "mark", "--gates", "7")
    git(repo, "add", "src/lib/db/schema.ts")
    return "allow", decide(repo)


def case_no_require_gates_unreviewed(repo: str) -> tuple[str, str]:
    config = dict(CONFIG)
    config.pop("require_gates")
    Path(repo, ".claude", "hooks", "precommit-gate.json").write_text(json.dumps(config), encoding="utf-8")
    Path(repo, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    git(repo, "add", "src/lib/db/schema.ts")
    return "ask", decide(repo)


def case_no_project_config(repo: str) -> tuple[str, str]:
    Path(repo, ".claude", "hooks", "precommit-gate.json").unlink()
    Path(repo, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    git(repo, "add", "src/lib/db/schema.ts")
    return "allow", decide(repo)


def case_worktree_barrier_active(repo: str) -> tuple[str, str]:
    """The barrier holds in a linked worktree: the config lives in the main
    checkout, and an unreviewed commit from the worktree is still stopped."""
    wt = add_worktree(repo)
    Path(wt, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    git(wt, "add", "src/lib/db/schema.ts")
    return "ask", decide(wt)


def case_worktree_credit_allows(repo: str) -> tuple[str, str]:
    """Credit earned in the worktree is recorded and read back, so a reviewed
    commit from there goes through."""
    wt = add_worktree(repo)
    Path(wt, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    util(wt, "mark", "--gates", "7,8")
    util(wt, "mark", "--gates", "11")
    git(wt, "add", "src/lib/db/schema.ts")
    return "allow", decide(wt)


def case_worktree_credit_stays_local(repo: str) -> tuple[str, str]:
    """Credit belongs to the working copy that earned it: a mark from the
    worktree writes there, and leaves the main checkout's store alone."""
    wt = add_worktree(repo)
    Path(wt, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    util(wt, "mark", "--gates", "7,8")
    where = "worktree" if marker(wt).is_file() else "nowhere"
    if marker(repo).is_file():
        where = where + "+main"
    return "worktree", where


def case_two_worktrees_keep_their_credit(repo: str) -> tuple[str, str]:
    """Two tasks in parallel: the second review does not delete the first one's
    credit, so the first can still commit what it had reviewed."""
    a = add_named_worktree(repo, "wt-a", "task/a")
    b = add_named_worktree(repo, "wt-b", "task/b")
    for wt in (a, b):
        Path(wt, "src/lib/db/schema.ts").write_text(f"from {Path(wt).name}\n", encoding="utf-8")
        util(wt, "mark", "--gates", "7,8")
        util(wt, "mark", "--gates", "11")
    # B reviewed last; A must still hold the credit it earned for its own file.
    git(a, "add", "src/lib/db/schema.ts")
    return "allow", decide(a)


def case_worktree_status_reads_config(repo: str) -> tuple[str, str]:
    """`status` run from the worktree finds the project config instead of dying
    with "this repo has not opted into the barrier"."""
    wt = add_worktree(repo)
    Path(wt, "src/lib/db/schema.ts").write_text("v2\n", encoding="utf-8")
    git(wt, "add", "src/lib/db/schema.ts")
    out = util(wt, "status")
    mode = next((l.split(":", 1)[1].strip() for l in out.splitlines() if l.startswith("mode:")), "")
    return "ask", mode or out.strip()[:80]


CASES = [
    ("review credit survives `git add`", case_credit_survives_staging),
    ("a missing gate blocks on its own", case_missing_gate_blocks),
    ("editing a file after the review expires its credit", case_edit_after_review_expires),
    ("an unreviewed file blocks even beside reviewed ones", case_new_file_not_covered),
    ("an untracked file reviewed in the worktree stays covered", case_untracked_then_staged),
    ("a staged deletion stays covered", case_deletion_covered),
    ("a legacy tree-fingerprint marker is accepted", case_legacy_marker_accepted),
    ("a stale legacy marker blocks", case_legacy_marker_stale),
    ("a recorded opt-out allows", case_optout),
    ("a trivial diff needs no review", case_trivial_diff),
    ("`git commit -a` always asks", case_commit_all_asks),
    ("a non-commit git command is untouched", case_non_commit_untouched),
    ("with no required gates, any recorded credit allows", case_no_require_gates),
    ("with no required gates, an unreviewed file still blocks", case_no_require_gates_unreviewed),
    ("a repo without the project config is untouched", case_no_project_config),
    ("the barrier holds in a linked worktree", case_worktree_barrier_active),
    ("credit earned in a worktree allows its commit", case_worktree_credit_allows),
    ("a worktree keeps its credit to itself", case_worktree_credit_stays_local),
    ("two worktrees do not erase each other's credit", case_two_worktrees_keep_their_credit),
    ("`status` from a worktree finds the project config", case_worktree_status_reads_config),
]


def main() -> int:
    verbose = "--verbose" in sys.argv
    failures = 0
    for name, case in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            repo = fresh_repo(tmp)
            try:
                expected, actual = case(repo)
            except Exception as exc:  # a case that cannot run is a failure
                print(f"FAIL  {name}\n      {type(exc).__name__}: {exc}")
                failures += 1
                continue
        if expected == actual:
            if verbose:
                print(f"ok    {name} -> {actual}")
        else:
            print(f"FAIL  {name}: expected {expected}, got {actual}")
            failures += 1

    total = len(CASES)
    print(f"\n{total - failures}/{total} cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
