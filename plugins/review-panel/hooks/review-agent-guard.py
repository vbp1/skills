#!/usr/bin/env python3
"""PreToolUse hook: review tracks get a read-only shell.

Registered by the review-panel plugin on the Bash matcher. It concerns itself
only with subagents whose `agent_type` names one of the panel tracks — bare
`review-*` for a project-local copy, or `<plugin>:review-*` for the installed
plugin. For every other caller it stays silent and lets the normal rules apply,
so it composes with whatever other Bash hooks a project already has.

python3 is a hard requirement. If it is missing the hook command itself fails,
which surfaces as a visible error on every Bash call — deliberately noisy,
because a guard that quietly does not run is the failure this file exists to
prevent.

WHY THIS EXISTS, and why the obvious alternatives do not work — all measured on
2026-08-01, not assumed:

  * Listing `Bash(git diff:*)` in an agent's `tools:` does NOT restrict it. A
    track so configured ran `git stash list` and `rm --help` with no gate; its
    own tool list came back as plain `Bash`. Argument scoping is honoured in
    settings permissions, not in agent frontmatter.
  * Dropping `Bash` from `tools:` DOES work — tool removal is enforced (a track
    without `Write` reports "Write tool not in available functions"). But a
    reviewer with no shell loses `git log`/`git blame`, which is real evidence.
  * danger-guard DOES reach subagent Bash (a track's `rm --help` raised a
    prompt), but it returns "ask", and a background panel of eight tracks must
    not stop to interrogate the developer. It also only knows destructive verbs,
    so `echo x > src/probe.ts` sails past it.

So: keep the shell, and deny — not ask — anything that is not a read. The
concrete incident this prevents: a review track ran `git stash` on the live
worktree mid-review and hid the developer's uncommitted work; another wrote a
scratch test file into src/ and broke the unit suite.

Fails CLOSED: any parse or runtime error denies, because a review that did not
happen is recoverable and a mutated working tree may not be.
"""

from __future__ import annotations

import json
import re
import sys

# Read-only commands a reviewer has a legitimate use for. Anchored at the start of
# each pipeline segment. Anything absent from this list is denied — the list is
# meant to grow by deliberate addition, never by guessing at intent. `sed` and `cd`
# entered the list from the 2026-08-03 false-positive corpus (tracks paging a file
# with `sed -n '1,40p'` and cd-ing before an `ls`); the mutating forms of sed are
# still denied below.
READ_ONLY = [
    r"git\s+(diff|log|show|blame|status|ls-files|rev-parse|describe|shortlog|cat-file|merge-base|name-rev|for-each-ref|branch\s+(-l|--list|--show-current)|stash\s+(list|show)|worktree\s+list|config\s+--get)",
    r"(rg|grep|egrep|fgrep)\b",
    r"(ls|cat|head|tail|wc|file|stat|realpath|basename|dirname|nl|sort|uniq|cut|tr|column|jq|yq|awk|sed)\b",
    r"(cd|find)\b",
    r"(echo|printf|true|pwd|date|which|type|env)\b",
    r"(node|python3?)\s+--version",
    r"(pnpm|npm|npx)\s+(ls|list|why|view|--version)",
]
READ_ONLY_RE = re.compile(r"^\s*(?:" + "|".join(READ_ONLY) + r")", re.I)

# `find -delete` / `find -exec rm` read like `find`; the same trick works for awk
# and jq, which can open files for writing. Anything in here is denied even when
# the segment starts with an allowed command.
#
# Two shapes here are precision-tuned against the 2026-08-03 false-positive corpus:
#   * File redirects deny only real file targets — `2>/dev/null`, `>/dev/null` and
#     fd dups (`2>&1`) are how read-only commands silence noise, so they pass.
#   * Command words carry a `(?<![-\w])` guard so option clusters (`rg -ln`) and
#     flag names never collide with the mutating command of the same spelling;
#     path-prefixed forms (`/bin/rm`) still match.
MUTATING_ANYWHERE = re.compile(
    r"(-delete\b|-exec\b|-execdir\b|-fprint\b"
    r"|\d*>>?\s*(?!&|/dev/null(?:\s|$))\S"
    r"|(?<![-\w])(?:tee|mkdir|touch|cp|mv|rm|rmdir|ln|chmod|chown|truncate|dd)\b"
    r"|\bsed\b[^|;&\n]*\s(?:-[a-z]*i[a-z]*|--in-place)\b|\bsed\b[^|;&\n]*['\"/;]\s*[wWe]\s|\bperl\b\s+-[a-z]*i"
    r"|\bgit\s+(add|commit|stash\s+(push|save|pop|apply|drop|clear|store|create|branch)|stash\s*$|checkout|switch|restore|reset|clean|merge|rebase|cherry-pick|revert|apply|am|push|pull|fetch|worktree\s+(add|remove|prune)|config\s+(?!--get))"
    r"|\bnpm\s+(i\b|install|uninstall|update)|\bpnpm\s+(i\b|install|add|remove|update)"
    r"|\bopen\s*\([^)]*['\"][wax]|\bwriteFile|\bwriteFileSync)",
    re.I,
)

SUBSHELL = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")

# Two-character separators first so `&&` never reads as two `&`.
SEPARATOR_TOKENS = ("&&", "||", "|&", ";", "|", "&", "\n")


def split_outside_quotes(text: str):
    """Split on shell separators, but never inside '…' or "…" spans.

    Search patterns routinely carry `|` inside quotes (`rg 'vitest|vite'`); a
    quote-blind split shredded them into fragments that failed the allowlist.
    Quote state follows shell rules: backslash escapes the next character except
    inside single quotes; an unbalanced quote swallows the rest of the string,
    which keeps the whole tail in one segment for the checks (fail closed).
    """
    parts, current, i = [], [], 0
    in_single = in_double = False
    while i < len(text):
        ch = text[i]
        if not in_single and ch == "\\" and i + 1 < len(text):
            current.append(text[i : i + 2])
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            token = next((t for t in SEPARATOR_TOKENS if text.startswith(t, i)), None)
            # `>&` (fd dup, as in 2>&1) and `&>` (redirect-all) are redirection
            # operators, not command separators — keep them inside the segment.
            if token == "&" and ((i > 0 and text[i - 1] == ">") or text.startswith("&>", i)):
                token = None
            if token:
                parts.append("".join(current))
                current = []
                i += len(token)
                continue
        current.append(ch)
        i += 1
    parts.append("".join(current))
    return parts


def deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    sys.exit(0)


def segments(command: str):
    """Every executable fragment: pipeline segments plus substitution contents.

    Substitution extraction stays quote-blind on purpose: a `$(…)` inside quotes
    yields an extra segment to check, which can only over-deny, never under-deny.
    """
    pending = [command]
    while pending:
        chunk = pending.pop()
        for found in SUBSHELL.findall(chunk):
            pending.extend(part for part in found if part)
        stripped = SUBSHELL.sub(" ", chunk)
        for seg in split_outside_quotes(stripped):
            seg = seg.strip()
            if seg:
                yield seg


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001 — the decision is the same either way
        deny(f"[review-agent-guard] unreadable hook payload: {exc}")

    if payload.get("tool_name") != "Bash":
        return
    # A plugin agent arrives namespaced ("review-panel:review-correctness"); a project-local
    # copy of the same agent arrives bare ("review-correctness"). Strip the plugin prefix and
    # test what is left, so both installations are covered and someone else's plugin agent
    # (e.g. "pr-review-toolkit:code-reviewer") is not silently swept in.
    agent_type = payload.get("agent_type") or ""
    if not agent_type.rsplit(":", 1)[-1].startswith("review-"):
        return  # not a review track — the usual permission rules apply

    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command.strip():
        return

    def refuse(seg: str, why: str) -> None:
        deny(
            f"[review-agent-guard] {agent_type} is a read-only review track and may not run: {seg}\n"
            f"{why}\n"
            f"Report what you would have run and what result would settle the finding, and continue reviewing. "
            f"The change under review is the diff file named in your prompt; use your file-reading tools and `rg` for the code."
        )

    for seg in segments(command):
        if MUTATING_ANYWHERE.search(seg):
            refuse(seg, "It writes, moves, deletes, or changes git state.")
        if not READ_ONLY_RE.match(seg):
            refuse(seg, "Only read-only inspection commands are allowed for review tracks.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        deny(f"[review-agent-guard] runtime error: {type(exc).__name__}: {exc}")
