#!/usr/bin/env python3
"""Selftest for rules-for-diff.py — the pattern resolver and the CLI contract.

Run it after editing rules-for-diff.py or assets/rules/mapping.json:

  python3 rules-for-diff-selftest.py [--verbose] [--only <substring>] [--list]

--verbose prints the passing cases too. Exit 1 when any case fails.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "rules-for-diff.py"

spec = importlib.util.spec_from_file_location("rules_for_diff", SCRIPT)
assert spec and spec.loader
rfd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rfd)

MAPPING = json.loads(rfd.MAPPING.read_text(encoding="utf-8"))
MATCHER = rfd.Matcher(MAPPING)


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          capture_output=True, text=True)


# ------------------------------------------------------------------ случаи ----

def case_extension_at_any_depth(_: str) -> tuple[str, str]:
    """`**/*.go` покрывает и корень, и вложенный каталог — «ноль каталогов» тоже
    совпадение."""
    got = [MATCHER.resolve(p)[0] for p in ("main.go", "a/b/main.go")]
    ok = got == ["go.md", "go.md"]
    return "go.md, both depths", ("go.md, both depths" if ok else f"got={got}")


def case_brace_alternatives(_: str) -> tuple[str, str]:
    """Каждое расширение из фигурных скобок ведёт к одной памятке."""
    got = {MATCHER.resolve(f"src/x.{ext}")[0] for ext in ("ts", "js", "tsx", "jsx", "mjs", "cjs")}
    ok = got == {"ts_js_tsx_jsx.md"}
    return "one rule for all six", ("one rule for all six" if ok else f"got={sorted(got)}")


def case_specific_beats_generic(_: str) -> tuple[str, str]:
    """Объявленный раньше конкретный образец выигрывает у общего: package.json
    не должен уехать в json.md, а рабочий процесс GitHub — в yaml.md."""
    got = (
        MATCHER.resolve("package.json")[0],
        MATCHER.resolve("app/config.json")[0],
        MATCHER.resolve(".github/workflows/ci.yaml")[0],
        MATCHER.resolve(".github/dependabot.yml")[0],
        MATCHER.resolve("deploy/values.yaml")[0],
    )
    want = ("package_json.md", "json.md", "github_workflows.md", "github_config.md", "yaml.md")
    ok = got == want
    return "first match wins", ("first match wins" if ok else f"got={got}")


def case_infix_wildcards(_: str) -> tuple[str, str]:
    """`**/*{mapper,dao}*.xml` ловит подстроку в имени, а прочий xml — нет."""
    got = (
        MATCHER.resolve("src/UserMapper.xml")[0],
        MATCHER.resolve("src/order-dao-v2.xml")[0],
        MATCHER.resolve("src/beans.xml")[0],
    )
    ok = got == ("mapper_dao_xml.md", "mapper_dao_xml.md", "default.md")
    return "two hits, one default", ("two hits, one default" if ok else f"got={got}")


def case_case_insensitive(_: str) -> tuple[str, str]:
    """Сопоставление не зависит от регистра — как в исходном движке."""
    got = (MATCHER.resolve("stats.R")[0], MATCHER.resolve("stats.r")[0],
           MATCHER.resolve("POM.XML")[0])
    ok = got == ("r.md", "r.md", "pom_xml.md")
    return "same rule either way", ("same rule either way" if ok else f"got={got}")


def case_unmatched_falls_back(_: str) -> tuple[str, str]:
    """Неизвестный тип файла получает общую памятку, а не пропускается."""
    got = [MATCHER.resolve(p)[0] for p in ("Makefile", "docs/readme.md", "bin/run.sh")]
    ok = got == ["default.md"] * 3
    return "default.md", ("default.md" if ok else f"got={got}")


def case_star_does_not_cross_slash(_: str) -> tuple[str, str]:
    """`*` не перепрыгивает через разделитель каталогов."""
    ok = (rfd.glob_to_regex("a/*.go") == "a/[^/]*\\.go"
          and __import__("re").match(rfd.glob_to_regex("a/*.go") + r"\Z", "a/b/x.go") is None)
    return "stays in one segment", ("stays in one segment" if ok else "crossed a slash")


def case_every_rule_file_exists(_: str) -> tuple[str, str]:
    """Каждая памятка из файла соответствий лежит на диске, и наоборот."""
    named = set(MAPPING["path_rule_map"].values()) | {MAPPING["default_rule"]}
    on_disk = {p.name for p in rfd.RULE_DOCS.glob("*.md")}
    missing, orphan = sorted(named - on_disk), sorted(on_disk - named - {"objc.md"})
    ok = not missing and not orphan
    return "all present", ("all present" if ok else f"missing={missing} orphan={orphan}")


def case_objc_sniffed_by_content(tmp: str) -> tuple[str, str]:
    """`.m` с си-подобной первой строкой — Objective-C; обычный — MATLAB."""
    root = Path(tmp)
    (root / "a.m").write_text("#import <Foundation/Foundation.h>\n", encoding="utf-8")
    (root / "b.m").write_text("% plot the thing\nx = 1;\n", encoding="utf-8")
    (root / "c.m").write_text("\n\n// leading blank lines\n", encoding="utf-8")
    got = tuple(rfd.sniffs_as_objc(root, name) for name in ("a.m", "b.m", "c.m", "missing.m"))
    ok = got == (True, False, True, False)
    return "told apart", ("told apart" if ok else f"got={got}")


def case_explicit_paths_group(tmp: str) -> tuple[str, str]:
    """Переданные пути группируются по памяткам, без обращения к git."""
    res = run("--format", "json", "src/a.ts", "src/b.tsx", "main.go", "Makefile",
              cwd=Path(tmp))
    if res.returncode != 0:
        return "3 groups", f"rc={res.returncode} err={res.stderr.strip()[:80]!r}"
    data = json.loads(res.stdout)
    rules = sorted(Path(g["rule"]).name for g in data["groups"])
    ok = data["total_files"] == 4 and rules == ["default.md", "go.md", "ts_js_tsx_jsx.md"]
    return "3 groups", ("3 groups" if ok else f"files={data['total_files']} rules={rules}")


def case_paths_and_refs_are_exclusive(tmp: str) -> tuple[str, str]:
    """Пути и указание ветки вместе — ошибка, а не тихий выбор одного из них."""
    res = run("src/a.ts", "--from", "main", "--to", "HEAD", cwd=Path(tmp))
    ok = res.returncode == 1 and "alternatives" in res.stderr
    return "refused", ("refused" if ok else f"rc={res.returncode} err={res.stderr.strip()[:80]!r}")


def case_half_a_range_is_refused(tmp: str) -> tuple[str, str]:
    """`--from` без `--to` — ошибка, а не молчаливый разбор рабочей копии."""
    res = run("--from", "main", cwd=Path(tmp))
    ok = res.returncode == 1 and "--from and --to" in res.stderr
    return "refused", ("refused" if ok else f"rc={res.returncode} err={res.stderr.strip()[:80]!r}")


def case_missing_repo_is_an_error(tmp: str) -> tuple[str, str]:
    res = run("--repo", str(Path(tmp) / "nowhere"), cwd=Path(tmp))
    ok = res.returncode == 1 and "no such directory" in res.stderr
    return "refused", ("refused" if ok else f"rc={res.returncode} err={res.stderr.strip()[:80]!r}")


def case_git_failure_is_reported(tmp: str) -> tuple[str, str]:
    """Каталог без репозитория: команда падает с текстом от git, а не отдаёт
    пустой список, который прочитался бы как «менять нечего»."""
    res = run("--repo", tmp, cwd=Path(tmp))
    ok = res.returncode == 1 and "git" in res.stderr and not res.stdout.strip()
    return "refused, nothing printed", (
        "refused, nothing printed" if ok else f"rc={res.returncode} out={res.stdout[:60]!r}")


def case_workspace_mode_reads_git(tmp: str) -> tuple[str, str]:
    """В настоящем репозитории разбирается вся незакоммиченная работа —
    изменённое, в индексе и новое."""
    root = Path(tmp) / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "kept.go").write_text("package main\n", encoding="utf-8")
    for args in (("init", "-q", "-b", "main", str(root)),):
        subprocess.run(["git", *args], capture_output=True, check=True)
    for args in (("config", "user.email", "s@e.com"), ("config", "user.name", "s"),
                 ("add", "-A"), ("commit", "-qm", "start")):
        subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)
    (root / "src" / "kept.go").write_text("package main // touched\n", encoding="utf-8")
    (root / "src" / "fresh.ts").write_text("export const a = 1;\n", encoding="utf-8")
    res = run("--format", "json", cwd=root)
    if res.returncode != 0:
        return "2 files, 2 rules", f"rc={res.returncode} err={res.stderr.strip()[:80]!r}"
    data = json.loads(res.stdout)
    rules = sorted(Path(g["rule"]).name for g in data["groups"])
    ok = data["total_files"] == 2 and rules == ["go.md", "ts_js_tsx_jsx.md"]
    return "2 files, 2 rules", ("2 files, 2 rules" if ok else f"{data['total_files']} {rules}")


def case_help_works(tmp: str) -> tuple[str, str]:
    res = run("--help", cwd=Path(tmp))
    ok = (res.returncode == 0 and "Usage:" in res.stdout and "Exit codes:" in res.stdout
          and "--format" in res.stdout)
    return "printed", ("printed" if ok else f"rc={res.returncode}")


CASES = [
    ("an extension matches at any depth", case_extension_at_any_depth),
    ("brace alternatives share one rule", case_brace_alternatives),
    ("a specific pattern beats a generic one", case_specific_beats_generic),
    ("wildcards inside a filename", case_infix_wildcards),
    ("matching ignores case", case_case_insensitive),
    ("an unmatched path falls back", case_unmatched_falls_back),
    ("a star does not cross a slash", case_star_does_not_cross_slash),
    ("every named rule file exists", case_every_rule_file_exists),
    ("objc is sniffed by content", case_objc_sniffed_by_content),
    ("explicit paths group by rule", case_explicit_paths_group),
    ("paths and refs are exclusive", case_paths_and_refs_are_exclusive),
    ("half a range is refused", case_half_a_range_is_refused),
    ("a missing repo is an error", case_missing_repo_is_an_error),
    ("a git failure is reported", case_git_failure_is_reported),
    ("workspace mode reads git", case_workspace_mode_reads_git),
    ("--help works", case_help_works),
]


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    if "--list" in argv:
        for name, _ in CASES:
            print(name)
        return 0
    wanted = None
    if "--only" in argv:
        index = argv.index("--only") + 1
        if index >= len(argv):
            print("--only нужен кусок имени случая", file=sys.stderr)
            return 1
        wanted = argv[index]

    selected = [c for c in CASES if wanted is None or wanted in c[0]]
    if not selected:
        print(f"ни один случай не подошёл под {wanted}", file=sys.stderr)
        return 1

    failures = 0
    for name, fn in selected:
        with tempfile.TemporaryDirectory() as tmp:
            want, got = fn(tmp)
        if want == got:
            if verbose:
                print(f"ok    {name} -> {got}")
        else:
            failures += 1
            print(f"FAIL  {name}\n        want: {want}\n        got:  {got}")
    print(f"{len(selected) - failures}/{len(selected)} cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
