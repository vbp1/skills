#!/usr/bin/env python3
"""Self-test corpus for review-agent-guard.py.

Run: python3 .claude/hooks/review-agent-guard-selftest.py   (exit 0 = all pass)

Two sources of truth, both from live incidents:
  * ALLOW — read-only commands review tracks actually ran and were wrongly
    denied on 2026-08-03 (quote-blind splitting, `2>/dev/null` matching the
    file-redirect pattern, `-ln` matching the `ln` command, sed/cd missing
    from the allowlist), plus baseline reads that must keep working.
  * DENY — the mutations the guard exists to stop, including the original
    `git stash` / scratch-file-in-src incidents; these must stay denied no
    matter how the allowlist grows.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).with_name("review-agent-guard.py")

ALLOW = [
    # 2026-08-03 false-positive corpus, verbatim from track transcripts.
    "sed -n '1,40p' /home/u/agent/apps/dbagent/src/lib/db/chats.ts",
    'rg -n "vitest" apps/dbagent/package.json; ls apps/dbagent/vitest*.ts apps/dbagent/vitest*.mts 2>/dev/null',
    'rg -ln "chat-handler.test" apps/dbagent/src | head; ls apps/dbagent/src/core/routes/',
    'cd /home/u/agent/apps/dbagent && ls vitest*.ts 2>/dev/null; echo "--- config ---"; cat vitest.config.ts 2>/dev/null | head -80',
    "ls -1 apps/dbagent/ | rg -i 'vitest|vite'",
    'rg -n "makeSqlGuardApp|chats-vote|chats-update-schema|chat-sql-guard" apps/dbagent/src -l',
    'rg -n "^import|^export \\{|^const |^let |^var " apps/dbagent/src/lib/db/chats.ts --max-count=60',
    "cat /home/u/agent/.prettierrc 2>/dev/null",
    # Baseline reads that must keep working.
    'git log -S "inArray" -- apps/dbagent/src/lib/db/chats.ts',
    'git log -G "voteMessage" --oneline -- apps/dbagent/src/lib/db/chats.ts',
    "git blame -L 10,20 apps/dbagent/src/lib/db/chats.ts",
    "git diff HEAD~1 -- apps/dbagent/src",
    "git config --get user.name",
    "ls > /dev/null 2>&1",
    "sed -E 's/foo/i/' file.ts | head",
    "sed 's/a/w/' file.ts",
    "sed -n '/we do/p' file.ts",
    "ls -ln apps/dbagent",
    'rg "say \\"a|b\\"" src',
    "find . -name '*.test.ts'",
]

DENY = [
    # The incidents the guard exists for.
    "git stash",
    "git stash push -m wip",
    "echo x > src/probe.ts",
    # Mutations that must never ride an allowlisted prefix.
    "rm -rf /tmp/x",
    "/bin/rm -rf /tmp/x",
    "sed -i 's/a/b/' file.ts",
    "sed --in-place 's/a/b/' file.ts",
    "sed -ri 's/a/b/' file.ts",
    "sed -n 'w /tmp/x' file.ts",
    "sed -n '/foo/w /tmp/out' file.ts",
    "awk '{print > \"/tmp/x\"}' file.ts",
    "cat x | tee /tmp/f",
    "find . -name '*.ts' -delete",
    "find . -name '*.ts' -exec rm {} \\;",
    "git checkout -- file.ts",
    "git add .",
    "git config user.name x",
    "bash -c 'rm x'",
    "mv a b",
    "cp a b",
    "touch /tmp/x",
    "ln -s a b",
    "dd if=/dev/zero of=/tmp/x",
    "rg foo > /tmp/out",
    "git log --oneline >> /tmp/log",
    "pnpm install",
    "npm install left-pad",
    "python3 script.py",
    "echo hi && rm -rf /tmp/y",
    "ls $(rm -rf /tmp/z)",
]


def run(agent_type: str, command: str) -> str | None:
    payload = {"tool_name": "Bash", "agent_type": agent_type, "tool_input": {"command": command}}
    proc = subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, check=False
    )
    out = proc.stdout.strip()
    if not out:
        return None
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"]


def main() -> int:
    failures = []
    # Both installation shapes guard the same way: bare agent types for a
    # project-local copy, plugin-namespaced ones for the installed plugin.
    for agent in ("review-correctness", "review-panel:review-correctness"):
        for cmd in ALLOW:
            verdict = run(agent, cmd)
            if verdict is not None:
                failures.append(f"ALLOW expected for {agent}, got {verdict}: {cmd}")
        for cmd in DENY:
            verdict = run(agent, cmd)
            if verdict != "deny":
                failures.append(f"DENY expected for {agent}, got {verdict}: {cmd}")
    # Non-review agents must pass through untouched, whatever the command —
    # including other plugins' namespaced agents.
    passthrough = ("general-purpose", "pr-review-toolkit:code-reviewer")
    for agent in passthrough:
        verdict = run(agent, "git stash")
        if verdict is not None:
            failures.append(f"silent pass-through expected for {agent}, got {verdict}")

    total = 2 * (len(ALLOW) + len(DENY)) + len(passthrough)
    if failures:
        print(f"{len(failures)}/{total} FAILED:")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
