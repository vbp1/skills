#!/usr/bin/env python3
"""UserPromptSubmit + SessionStart hook: taskflow state anchor.

Re-injects the step of the task THIS SESSION is focused on (and nothing about any
other task) on every prompt, plus on session start / resume / compact, so the
conductor never loses track of where its task is after a context compaction.

Focus is per session: <root>/<tasks-dir>/.active.d/<session_id> holds the filename
of the task file this session is driving. Several sessions can therefore drive
several tasks at once, each seeing only its own. A session with no focus file gets
no line; the whole cross-task picture comes from `/taskflow status` on request.

The task directory is `todos/` by default. Set TASKFLOW_DIR to another name (a
single path component, e.g. `tasks`) to move it; the skill and this hook must
agree on the value.

Pure stdlib, fail-OPEN: any error, or no focus for this session, -> no output,
exit 0. The hook only ever ADDS a short context line; it never blocks a prompt.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

STEP_TOTAL = 10
SESSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
DIR_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def tasks_dir_name() -> str:
    name = (os.environ.get("TASKFLOW_DIR") or "todos").strip()
    return name if DIR_RE.match(name) else "todos"


def find_root(start: Path, tasks_dir: str) -> Path | None:
    """Walk up from `start` until a directory holding the task directory is found."""
    cur = start
    for _ in range(40):
        if (cur / tasks_dir).is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def parse_frontmatter(text: str) -> dict:
    """Minimal flat-key parser for the `---` fenced YAML header. Top-level keys
    only; nested/indented lines are ignored on purpose (the hook needs the flat
    fields the conductor maintains: id, title, status, step, step_label,
    awaiting, blocked_by). List fields MUST be inline (`blocked_by: [64]`) — a
    block-style list under the key parses as empty here, so the blocked marker
    would silently not show; SKILL.md mandates the inline form for this reason."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line or line[:1] in (" ", "\t") or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        fm[key.strip()] = val.strip()
    return fm


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    session = str(payload.get("session_id") or "").strip()
    if not SESSION_RE.match(session):
        return

    tasks_dir = tasks_dir_name()
    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    root = find_root(Path(cwd), tasks_dir)
    if root is None:
        return

    focus_file = root / tasks_dir / ".active.d" / session
    if not focus_file.is_file():
        return

    try:
        active = focus_file.read_text(encoding="utf-8").strip()
    except Exception:
        return
    if not active or "/" in active or active.startswith("."):
        return

    task_file = root / tasks_dir / active
    if not task_file.is_file():
        return

    try:
        fm = parse_frontmatter(task_file.read_text(encoding="utf-8"))
    except Exception:
        return

    status = strip_quotes(fm.get("status", ""))
    if status in ("done", "abandoned") or not fm.get("step"):
        return

    tid = strip_quotes(fm.get("id", "?"))
    title = strip_quotes(fm.get("title", active))
    step = strip_quotes(fm.get("step", "?"))
    label = strip_quotes(fm.get("step_label", ""))
    awaiting = strip_quotes(fm.get("awaiting", ""))
    blocked = strip_quotes(fm.get("blocked_by", "[]"))

    line = f"[taskflow] This session drives task #{tid} «{title}», step {step}/{STEP_TOTAL}"
    if label:
        line += f": {label}"
    line += "."
    if awaiting:
        line += f" Paused for the user's approval: {awaiting}."
    if blocked and blocked.replace(" ", "") not in ("[]", ""):
        line += f" BLOCKED by unfinished dependencies: {blocked}."
    line += (
        f" The source of truth for the state is {tasks_dir}/{active} (frontmatter). "
        "Drive the task with the taskflow skill; update step/awaiting as they change. "
        "Other tasks are not shown in this line — `/taskflow status` lists them."
    )
    sys.stdout.write(line + "\n")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # non-ASCII titles, regardless of locale
    except Exception:
        pass
    try:
        main()
    except Exception:
        # Anchor must never break a prompt: swallow everything, exit 0.
        pass
