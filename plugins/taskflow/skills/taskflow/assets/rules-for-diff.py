#!/usr/bin/env python3
"""taskflow rule picker — names the review checklists that apply to a change,
and nothing else.

`assets/rules/rule_docs/` holds 52 language and file-type checklists totalling
~240 KB. Handing all of them to a reviewer would cost more context than the diff
itself, so this script answers the only question that matters: for THESE changed
files, which checklists are worth opening?

It resolves each path through `assets/rules/mapping.json` — an ordered list of
glob patterns, first match wins, `default.md` when none match — then groups the
paths by the checklist they landed on. The reviewer opens the handful of files
named in the output; the other forty-odd are never read.

One file type needs content, not just its name: `.m` belongs to both MATLAB and
Objective-C. A `.m` file whose first non-blank line opens with a C-style comment,
a preprocessor directive or an Objective-C keyword resolves to `objc.md`; every
other `.m` file stays MATLAB.

Usage:
  rules-for-diff.py                          # uncommitted work: staged, unstaged, untracked
  rules-for-diff.py --staged                 # the index alone
  rules-for-diff.py --from main --to HEAD    # a branch against its merge-base with main
  rules-for-diff.py --commit <sha>           # one commit against its parent
  rules-for-diff.py src/a.ts docs/b.md       # these paths, no git involved
  rules-for-diff.py --repo <path> ...        # act on another working copy
  rules-for-diff.py --format json ...        # same answer, machine-readable

Output (text): one block per checklist — its absolute path, the pattern that
selected it, and the changed files it covers.

Exit codes: 0 ok, 1 bad arguments or a git failure, 2 the bundled ruleset is
missing or unreadable.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

RULES_DIR = Path(__file__).resolve().parent / "rules"
MAPPING = RULES_DIR / "mapping.json"
RULE_DOCS = RULES_DIR / "rule_docs"

# First-line signals that a ".m" file is Objective-C rather than MATLAB. MATLAB
# comments start with "%" and a MATLAB file cannot legally begin with "/", so a
# C-style comment opener is itself a reliable signal — and the Xcode template
# puts a comment, not a directive, on line 1. A bare "#" is deliberately absent:
# Octave also uses ".m" and treats "#" as a comment character.
OBJC_PREFIXES = (
    "#import", "#include", "#pragma", "#if", "#define",
    "@import", "@interface", "@implementation", "@class", "@protocol",
    "//", "/*",
)


def die(message: str, code: int = 1) -> NoReturn:
    print(f"rules-for-diff: {message}", file=sys.stderr)
    raise SystemExit(code)


# ------------------------------------------------------------------ globbing --

def _translate_class(pattern: str, i: int, out: list[str]) -> int:
    """Translate a [...] character class starting at pattern[i] == '['."""
    j = i + 1
    negate = False
    if j < len(pattern) and pattern[j] in "^!":
        negate = True
        j += 1
    start = j
    if j < len(pattern) and pattern[j] == "]":  # a leading ']' is a literal
        j += 1
    while j < len(pattern) and pattern[j] != "]":
        j += 1
    if j >= len(pattern):  # unterminated: the '[' was a literal
        out.append(re.escape("["))
        return i + 1
    body = pattern[start:j].replace("\\", "\\\\")
    out.append("[" + ("^" if negate else "") + body + "]")
    return j + 1


def _split_alternatives(body: str) -> list[str]:
    """Split a brace body on top-level commas, keeping nested braces intact."""
    parts, depth, current = [], 0, []
    for ch in body:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    parts.append("".join(current))
    return parts


def _find_closing_brace(pattern: str, i: int) -> int:
    """Index of the '}' closing the '{' at pattern[i], or -1 when unbalanced."""
    depth = 0
    for j in range(i, len(pattern)):
        if pattern[j] == "{":
            depth += 1
        elif pattern[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return -1


def glob_to_regex(pattern: str) -> str:
    """Translate a doublestar-style glob into a regex matching a whole path.

    `**` as a full path segment matches zero or more directories, so `**/*.go`
    covers `main.go` as well as `a/b/main.go`. `*` and `?` never cross `/`.
    Braces expand to alternatives and may nest; a backslash escapes the next
    character.
    """
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "\\" and i + 1 < n:
            out.append(re.escape(pattern[i + 1]))
            i += 2
        elif ch == "*":
            double = i + 1 < n and pattern[i + 1] == "*"
            if double:
                at_segment_start = i == 0 or pattern[i - 1] == "/"
                after = i + 2
                if at_segment_start and after < n and pattern[after] == "/":
                    out.append("(?:[^/]*/)*")  # zero or more directories
                    i = after + 1
                    continue
                if at_segment_start and after == n:
                    out.append(".*")
                    i = after
                    continue
                out.append("[^/]*")  # a `**` inside a segment is just a `*`
                i = after
                continue
            out.append("[^/]*")
            i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        elif ch == "[":
            i = _translate_class(pattern, i, out)
        elif ch == "{":
            close = _find_closing_brace(pattern, i)
            if close < 0:  # unbalanced: the '{' was a literal
                out.append(re.escape("{"))
                i += 1
                continue
            alternatives = _split_alternatives(pattern[i + 1 : close])
            out.append("(?:" + "|".join(glob_to_regex(a) for a in alternatives) + ")")
            i = close + 1
        else:
            out.append(re.escape(ch))
            i += 1
    return "".join(out)


class Matcher:
    """The ordered pattern list, compiled once. First match wins."""

    def __init__(self, mapping: dict) -> None:
        self.default = mapping["default_rule"]
        self.rules: list[tuple[str, re.Pattern, str]] = []
        for pattern, rule in mapping["path_rule_map"].items():
            # Both sides are lowercased before matching, as the upstream
            # resolver does, so `**/*.R` covers `.r` too.
            compiled = re.compile(glob_to_regex(pattern.lower()) + r"\Z")
            self.rules.append((pattern, compiled, rule))

    def resolve(self, path: str) -> tuple[str, str]:
        """Return (rule file name, the pattern that selected it)."""
        lowered = path.lower()
        for pattern, compiled, rule in self.rules:
            if compiled.match(lowered):
                return rule, pattern
        return self.default, "default"


# --------------------------------------------------------------- .m sniffing --

def sniffs_as_objc(repo: Path, path: str) -> bool:
    if not path.lower().endswith(".m"):
        return False
    try:
        with open(repo / path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    return stripped.startswith(OBJC_PREFIXES)
    except OSError:
        return False  # unreadable: the name-based answer (MATLAB) stands
    return False


# ---------------------------------------------------------------------- git --

def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    if done.returncode != 0:
        die(f"git {' '.join(args)} failed: {done.stderr.strip() or 'no output'}")
    return done.stdout


def changed_paths(repo: Path, opts: argparse.Namespace) -> list[str]:
    if opts.commit:
        out = git(repo, "show", "--name-only", "--format=", opts.commit)
    elif opts.from_ref or opts.to_ref:
        if not (opts.from_ref and opts.to_ref):
            die("--from and --to go together; pass both or neither.")
        base = git(repo, "merge-base", opts.from_ref, opts.to_ref).strip()
        if not base:
            die(f"no merge-base between {opts.from_ref} and {opts.to_ref}.")
        out = git(repo, "diff", "--name-only", base, opts.to_ref)
    elif opts.staged:
        out = git(repo, "diff", "--cached", "--name-only")
    else:
        out = git(repo, "diff", "HEAD", "--name-only")
        out += git(repo, "ls-files", "--others", "--exclude-standard")
    return sorted({line.strip() for line in out.splitlines() if line.strip()})


# -------------------------------------------------------------------- output --

def group(repo: Path, paths: list[str], matcher: Matcher) -> list[dict]:
    groups: dict[tuple[str, str], list[str]] = {}
    for path in paths:
        rule, pattern = matcher.resolve(path)
        if sniffs_as_objc(repo, path):
            rule, pattern = "objc.md", pattern + " (sniffed as Objective-C)"
        groups.setdefault((rule, pattern), []).append(path)
    return [
        {"rule": str(RULE_DOCS / rule), "pattern": pattern, "files": files}
        for (rule, pattern), files in sorted(groups.items())
    ]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="rules-for-diff.py",
        description="Name the review checklists that apply to a change.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("paths", nargs="*", help="explicit paths; skips git entirely")
    parser.add_argument("--repo", default=".", help="working copy to act on (default: .)")
    parser.add_argument("--from", dest="from_ref", help="source ref of a range")
    parser.add_argument("--to", dest="to_ref", help="target ref of a range")
    parser.add_argument("--commit", help="one commit, against its parent")
    parser.add_argument("--staged", action="store_true", help="the index alone")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    opts = parser.parse_args(argv)

    if not MAPPING.is_file() or not RULE_DOCS.is_dir():
        die(f"bundled ruleset missing: expected {MAPPING} and {RULE_DOCS}/", 2)
    try:
        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        die(f"cannot read {MAPPING}: {exc}", 2)

    repo = Path(opts.repo).resolve()
    if not repo.is_dir():
        die(f"--repo {opts.repo}: no such directory. Nothing was resolved.")

    if opts.paths:
        for flag, value in (("--from", opts.from_ref), ("--to", opts.to_ref),
                            ("--commit", opts.commit)):
            if value:
                die(f"explicit paths and {flag} are alternatives; pass one or the other.")
        if opts.staged:
            die("explicit paths and --staged are alternatives; pass one or the other.")
        paths = sorted({p.strip() for p in opts.paths if p.strip()})
    else:
        paths = changed_paths(repo, opts)

    groups = group(repo, paths, Matcher(mapping))

    if opts.format == "json":
        json.dump({"total_files": len(paths), "groups": groups}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if not paths:
        print("no changed files — no checklist applies.")
        return 0
    print(f"{len(paths)} changed file(s), {len(groups)} checklist(s) to read:\n")
    for entry in groups:
        print(f"{entry['rule']}   [{entry['pattern']}]")
        for path in entry["files"]:
            print(f"    {path}")
        print()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise SystemExit(130)
