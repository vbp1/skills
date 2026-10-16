#!/usr/bin/env python3
"""Набор проверок для review-round.sh плагина review-panel.

Каждый случай поднимает игрушечный репозиторий во временном каталоге, гоняет
скрипт и сверяет напечатанное. Ничего за пределами временного каталога не
трогается.

USAGE
  review-round-selftest.py [--verbose] [--only SUBSTRING]...
  review-round-selftest.py --list

EXIT CODES
  0  все случаи прошли
  1  хотя бы один провалился
  2  ошибка вызова
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "review-round.sh"


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


def rr(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=str(cwd),
                          capture_output=True, text=True)


def build(tmp: str) -> Path:
    """Репозиторий с коммитом, подкаталогом и отслеживаемым файлом в нём."""
    root = Path(tmp) / "repo"
    (root / "apps" / "web" / "src").mkdir(parents=True)
    (root / "apps" / "web" / "src" / "kept.ts").write_text("одна строка\n", encoding="utf-8")
    (root / "README.md").write_text("описание\n", encoding="utf-8")
    git(root.parent, "init", "-q", "-b", "main", str(root))
    git(root, "config", "user.email", "selftest@example.com")
    git(root, "config", "user.name", "selftest")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "начало")
    return root


def opened(res: subprocess.CompletedProcess) -> tuple[str, str]:
    number, _, directory = res.stdout.strip().partition(" ")
    return number, directory


# ---------------------------------------------------------------- случаи ----


def case_paths_are_the_same_from_any_directory(tmp: str) -> tuple[str, str]:
    """Снимок, снятый из подкаталога, называет файлы так же, как снятый из корня:
    отслеживаемые и новые одинаково, от корня копии."""
    root = build(tmp)
    (root / "apps" / "web" / "src" / "kept.ts").write_text("другая строка\n", encoding="utf-8")
    (root / "apps" / "web" / "src" / "fresh.ts").write_text("новый\n", encoding="utf-8")

    from_root = rr(root, "open")
    number, directory = opened(from_root)
    at_root = sorted(
        line.split("\t")[1]
        for line in Path(directory, f"round-{number}.files").read_text(encoding="utf-8").splitlines()
        if line
    )
    shutil.rmtree(directory)

    from_deep = rr(root / "apps" / "web" / "src", "open")
    number, directory = opened(from_deep)
    at_deep = sorted(
        line.split("\t")[1]
        for line in Path(directory, f"round-{number}.files").read_text(encoding="utf-8").splitlines()
        if line
    )
    want = ["apps/web/src/fresh.ts", "apps/web/src/kept.ts"]
    ok = at_root == want and at_deep == want
    return "same paths, from the root", (
        "same paths, from the root" if ok else f"root={at_root} deep={at_deep}")


def case_nothing_moved_right_after_opening(tmp: str) -> tuple[str, str]:
    root = build(tmp)
    (root / "README.md").write_text("правка\n", encoding="utf-8")
    rr(root, "open")
    res = rr(root / "apps" / "web", "check", "1")
    ok = res.returncode == 0 and not res.stdout.strip()
    return "clean", "clean" if ok else f"rc={res.returncode} out={res.stdout.strip()[:80]!r}"


def case_a_touched_file_shows_up_in_the_delta(tmp: str) -> tuple[str, str]:
    root = build(tmp)
    (root / "README.md").write_text("правка\n", encoding="utf-8")
    rr(root, "open")
    (root / "README.md").write_text("ещё правка\n", encoding="utf-8")
    delta = rr(root / "apps", "delta", "1").stdout.strip()
    check = rr(root / "apps", "check", "1")
    ok = delta == "changed\tREADME.md" and check.returncode == 2
    return "named once, check fails", (
        "named once, check fails" if ok else f"delta={delta!r} rc={check.returncode}")


def case_a_round_of_another_copy_is_refused(tmp: str) -> tuple[str, str]:
    """Две копии на одном имени ветки делят каталог раундов. Раунд, открытый в
    одной, в другой не сверяется: скрипт называет обе и не сравнивает ничего."""
    root = build(tmp)
    first = Path(tmp) / "wt-one"
    second = Path(tmp) / "wt-two"
    git(root, "worktree", "add", "-q", "--detach", str(first))
    git(root, "worktree", "add", "-q", "--detach", str(second))
    (first / "README.md").write_text("работа первой копии\n", encoding="utf-8")
    rr(first, "open")
    res = rr(second, "check", "1")
    named = str(first) in res.stderr and str(second) in res.stderr
    ok = res.returncode == 1 and named and not res.stdout.strip()
    return "refused, both named", (
        "refused, both named" if ok else f"rc={res.returncode} err={res.stderr.strip()[:100]!r}")


def case_the_copy_can_be_named_explicitly(tmp: str) -> tuple[str, str]:
    """`-C` указывает копию, когда каталог вызывающего уехал."""
    root = build(tmp)
    work = Path(tmp) / "wt-one"
    git(root, "worktree", "add", "-q", "--detach", str(work))
    (work / "README.md").write_text("работа копии\n", encoding="utf-8")
    rr(work, "open")
    elsewhere = Path(tmp)
    res = rr(elsewhere, "-C", str(work), "check", "1")
    ok = res.returncode == 0
    return "checked in the named copy", (
        "checked in the named copy" if ok else f"rc={res.returncode} err={res.stderr.strip()[:100]!r}")


def case_a_missing_copy_is_an_error(tmp: str) -> tuple[str, str]:
    root = build(tmp)
    res = rr(root, "-C", str(Path(tmp) / "нет-такого"), "check", "1")
    ok = res.returncode == 1 and "no such directory" in res.stderr
    return "refused", "refused" if ok else f"rc={res.returncode} err={res.stderr.strip()[:80]!r}"


def case_the_round_records_where_it_was_opened(tmp: str) -> tuple[str, str]:
    root = build(tmp)
    (root / "README.md").write_text("правка\n", encoding="utf-8")
    number, directory = opened(rr(root, "open"))
    where = Path(directory, f"round-{number}.where").read_text(encoding="utf-8").splitlines()
    ok = where == [str(root.resolve()), "main"]
    return "copy and branch", "copy and branch" if ok else f"where={where}"


def case_open_says_where_it_opened(tmp: str) -> tuple[str, str]:
    """`open` и `check` печатают копию и ветку: расхождение видно сразу, без
    разбирательства."""
    root = build(tmp)
    (root / "README.md").write_text("правка\n", encoding="utf-8")
    said_open = rr(root, "open").stderr
    said_check = rr(root, "check", "1").stderr
    ok = str(root.resolve()) in said_open and "on main" in said_open \
        and str(root.resolve()) in said_check
    return "both name the copy", (
        "both name the copy" if ok else f"open={said_open.strip()[:60]!r} check={said_check.strip()[:60]!r}")


def case_the_next_round_takes_the_next_number(tmp: str) -> tuple[str, str]:
    root = build(tmp)
    (root / "README.md").write_text("правка\n", encoding="utf-8")
    first, _ = opened(rr(root, "open"))
    second, _ = opened(rr(root, "open"))
    ok = (first, second) == ("1", "2")
    return "1 then 2", "1 then 2" if ok else f"{first} then {second}"


def case_an_unusable_scope_claims_nothing(tmp: str) -> tuple[str, str]:
    root = build(tmp)
    res = rr(root, "open", "--scope", "нет-такой-ветки")
    left = rr(root, "latest").stdout.strip()
    ok = res.returncode == 1 and left == "0"
    return "refused, nothing claimed", (
        "refused, nothing claimed" if ok else f"rc={res.returncode} latest={left}")


def case_files_lists_the_checklist(tmp: str) -> tuple[str, str]:
    """`files` перечисляет каждый файл раунда — отслеживаемый, новый и удалённый,
    каждый со своим признаком."""
    root = build(tmp)
    (root / "README.md").write_text("правка\n", encoding="utf-8")
    (root / "apps" / "web" / "src" / "fresh.ts").write_text("новый\n", encoding="utf-8")
    (root / "apps" / "web" / "src" / "kept.ts").unlink()
    rr(root, "open")
    listed = sorted(rr(root / "apps", "files", "1").stdout.strip().splitlines())
    want = sorted([
        "present\tREADME.md",
        "present\tapps/web/src/fresh.ts",
        "deleted\tapps/web/src/kept.ts",
    ])
    ok = listed == want
    return "every file, with its state", (
        "every file, with its state" if ok else f"got={listed}")


def case_files_reads_from_another_copy(tmp: str) -> tuple[str, str]:
    """Чеклист читается из чужой рабочей копии: он ни с чем не сравнивает,
    в отличие от `delta` и `check`."""
    root = build(tmp)
    (root / "README.md").write_text("правка\n", encoding="utf-8")
    rr(root, "open")
    elsewhere = Path(tmp) / "elsewhere"
    elsewhere.mkdir()
    res = rr(elsewhere, "-C", str(root), "files", "1")
    ok = res.returncode == 0 and res.stdout.strip() == "present\tREADME.md"
    return "listed", "listed" if ok else f"rc={res.returncode} out={res.stdout.strip()[:80]!r}"


def case_files_of_an_unopened_round_is_an_error(tmp: str) -> tuple[str, str]:
    """Раунда нет — команда падает, а не отдаёт пустой чеклист, который читается
    как «проверять нечего»."""
    root = build(tmp)
    res = rr(root, "files", "1")
    ok = res.returncode == 1 and "no manifest" in res.stderr
    return "refused", "refused" if ok else f"rc={res.returncode} err={res.stderr.strip()[:80]!r}"


def case_a_clean_round_seals(tmp: str) -> tuple[str, str]:
    """Дорожки вернулись, дерево не тронуто — `seal` записывает момент и называет
    его. С этой отметки правки считаются работой ведущего."""
    root = build(tmp)
    (root / "README.md").write_text("правка\n", encoding="utf-8")
    number, directory = opened(rr(root, "open"))
    res = rr(root / "apps", "seal", number)
    stamp = Path(directory, f"round-{number}.sealed")
    recorded = stamp.read_text(encoding="utf-8").splitlines() if stamp.is_file() else []
    ok = res.returncode == 0 and not res.stdout.strip() \
        and len(recorded) == 2 and recorded[0].endswith("Z") \
        and recorded[1] == str(root.resolve()) and "sealed at" in res.stderr
    return "sealed and recorded", (
        "sealed and recorded" if ok else f"rc={res.returncode} recorded={recorded} err={res.stderr.strip()[:80]!r}")


def case_seal_refuses_a_moved_tree(tmp: str) -> tuple[str, str]:
    """Что-то изменилось, пока шла панель, — момент не записывается: иначе отметка
    накрыла бы чужую запись в общее дерево."""
    root = build(tmp)
    (root / "README.md").write_text("правка\n", encoding="utf-8")
    number, directory = opened(rr(root, "open"))
    (root / "README.md").write_text("ещё правка\n", encoding="utf-8")
    res = rr(root / "apps", "seal", number)
    sealed = Path(directory, f"round-{number}.sealed").is_file()
    ok = res.returncode == 2 and res.stdout.strip() == "TREE changed\tREADME.md" \
        and not sealed and "Nothing was sealed" in res.stderr
    return "refused, nothing recorded", (
        "refused, nothing recorded" if ok
        else f"rc={res.returncode} out={res.stdout.strip()[:60]!r} sealed={sealed}")


def case_check_after_the_seal_names_the_fixes_as_yours(tmp: str) -> tuple[str, str]:
    """После отметки правки ведущего перестают читаться как запись дорожки:
    `check` называет их числом и выходит с нулём."""
    root = build(tmp)
    (root / "README.md").write_text("правка\n", encoding="utf-8")
    number, _ = opened(rr(root, "open"))
    rr(root, "seal", number)
    (root / "README.md").write_text("правка по находке\n", encoding="utf-8")
    res = rr(root / "apps", "check", number)
    ok = res.returncode == 0 and not res.stdout.strip() \
        and "was sealed at" in res.stderr and "1 change(s)" in res.stderr
    return "own fixes, exit 0", (
        "own fixes, exit 0" if ok else f"rc={res.returncode} out={res.stdout.strip()[:60]!r} err={res.stderr.strip()[:110]!r}")


def case_a_second_seal_is_refused(tmp: str) -> tuple[str, str]:
    """Вторая отметка сдвинула бы границу за уже сделанные правки, поэтому раунд
    с отметкой её не принимает, а записанный момент остаётся прежним."""
    root = build(tmp)
    (root / "README.md").write_text("правка\n", encoding="utf-8")
    number, directory = opened(rr(root, "open"))
    rr(root, "seal", number)
    first = Path(directory, f"round-{number}.sealed").read_text(encoding="utf-8")
    (root / "README.md").write_text("правка по находке\n", encoding="utf-8")
    res = rr(root, "seal", number)
    kept = Path(directory, f"round-{number}.sealed").read_text(encoding="utf-8")
    ok = res.returncode == 1 and "already sealed" in res.stderr and kept == first
    return "refused, moment kept", (
        "refused, moment kept" if ok else f"rc={res.returncode} err={res.stderr.strip()[:80]!r} kept={kept == first}")


def build_wide(tmp: str) -> Path:
    """Репозиторий и раунд на 7 новых файлов: каталог `a` (код + тест), `a/deep`,
    `b` и один файл в корне."""
    root = build(tmp)
    for rel in ("a/one.ts", "a/one.test.ts", "a/deep/two.ts", "a/deep/three.ts",
                "b/four.ts", "b/five.ts", "top.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("новый\n", encoding="utf-8")
    rr(root, "open")
    return root


def part_paths(root: Path) -> dict[str, list[str]]:
    store = Path(rr(root, "dir").stdout.strip())
    return {p.name: [line.split("\t", 1)[1] for line in p.read_text(encoding="utf-8").splitlines()]
            for p in sorted(store.glob("round-1.part-*.files"))}


def case_parts_cover_every_file_once(tmp: str) -> tuple[str, str]:
    """Каждый файл раунда попадает ровно в одну часть, ни одна часть не больше
    --max, а тест остаётся в части своего кода."""
    root = build_wide(tmp)
    res = rr(root, "parts", "1", "--max", "3")
    parts = part_paths(root)
    every = sorted(p for paths in parts.values() for p in paths)
    want = sorted(line.split("\t", 1)[1] for line in rr(root, "files", "1").stdout.splitlines())
    together = any({"a/one.ts", "a/one.test.ts"} <= set(paths) for paths in parts.values())
    ok = (res.returncode == 0 and every == want and together
          and all(len(paths) <= 3 for paths in parts.values())
          and len(res.stdout.strip().splitlines()) == len(parts))
    return "covered once", "covered once" if ok else f"rc={res.returncode} parts={parts} err={res.stderr.strip()[:80]!r}"


def case_a_directory_that_fits_is_not_cut(tmp: str) -> tuple[str, str]:
    """Каталог, который помещается в часть целиком, не разрезается."""
    root = build_wide(tmp)
    rr(root, "parts", "1", "--max", "4")
    parts = part_paths(root)
    a_files = {"a/one.ts", "a/one.test.ts", "a/deep/two.ts", "a/deep/three.ts"}
    ok = any(a_files <= set(paths) for paths in parts.values())
    return "kept whole", "kept whole" if ok else f"parts={parts}"


def case_a_small_round_is_not_split(tmp: str) -> tuple[str, str]:
    """Раунд не больше --max не делится: ничего не записано, выход 1."""
    root = build_wide(tmp)
    res = rr(root, "parts", "1", "--max", "7")
    ok = res.returncode == 1 and "no split" in res.stderr and not part_paths(root)
    return "refused", "refused" if ok else f"rc={res.returncode} err={res.stderr.strip()[:80]!r}"


def case_a_second_split_is_refused(tmp: str) -> tuple[str, str]:
    """Повторное деление того же раунда отклоняется и не трогает первые части."""
    root = build_wide(tmp)
    rr(root, "parts", "1", "--max", "3")
    before = part_paths(root)
    res = rr(root, "parts", "1", "--max", "2")
    ok = res.returncode == 1 and "already split" in res.stderr and part_paths(root) == before
    return "refused", "refused" if ok else f"rc={res.returncode} err={res.stderr.strip()[:80]!r}"


def case_parts_reject_bad_input(tmp: str) -> tuple[str, str]:
    """Негодный --max и неоткрытый раунд — ошибка до записи."""
    root = build_wide(tmp)
    bad = [rr(root, "parts", "1", "--max", v) for v in ("0", "-3", "x", "")]
    missing = rr(root, "parts", "2", "--max", "3")
    ok = (all(r.returncode == 1 for r in bad) and missing.returncode == 1
          and "no manifest" in missing.stderr and not part_paths(root))
    return "refused", "refused" if ok else f"bad={[r.returncode for r in bad]} missing={missing.returncode}"


def case_help_works(tmp: str) -> tuple[str, str]:
    res = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True,
                         cwd=tempfile.gettempdir())
    ok = res.returncode == 0 and "USAGE" in res.stdout and "-C" in res.stdout
    return "printed", "printed" if ok else f"rc={res.returncode}"


CASES = [
    ("paths are the same from any directory", case_paths_are_the_same_from_any_directory),
    ("nothing moved right after opening", case_nothing_moved_right_after_opening),
    ("a touched file shows up in the delta", case_a_touched_file_shows_up_in_the_delta),
    ("a round of another copy is refused", case_a_round_of_another_copy_is_refused),
    ("the copy can be named explicitly", case_the_copy_can_be_named_explicitly),
    ("a missing copy is an error", case_a_missing_copy_is_an_error),
    ("the round records where it was opened", case_the_round_records_where_it_was_opened),
    ("open and check say where they are", case_open_says_where_it_opened),
    ("the next round takes the next number", case_the_next_round_takes_the_next_number),
    ("an unusable scope claims nothing", case_an_unusable_scope_claims_nothing),
    ("files lists the checklist", case_files_lists_the_checklist),
    ("files reads from another copy", case_files_reads_from_another_copy),
    ("files of an unopened round is an error", case_files_of_an_unopened_round_is_an_error),
    ("a clean round seals", case_a_clean_round_seals),
    ("seal refuses a moved tree", case_seal_refuses_a_moved_tree),
    ("check after the seal names the fixes as yours", case_check_after_the_seal_names_the_fixes_as_yours),
    ("a second seal is refused", case_a_second_seal_is_refused),
    ("parts cover every file once", case_parts_cover_every_file_once),
    ("a directory that fits is not cut", case_a_directory_that_fits_is_not_cut),
    ("a small round is not split", case_a_small_round_is_not_split),
    ("a second split is refused", case_a_second_split_is_refused),
    ("parts reject bad input", case_parts_reject_bad_input),
    ("--help works", case_help_works),
]


def main(argv: list[str]) -> int:
    verbose = False
    wanted: list[str] = []
    rest = argv[1:]
    while rest:
        flag = rest.pop(0)
        if flag in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        if flag == "--verbose":
            verbose = True
        elif flag == "--list":
            for name, _ in CASES:
                print(name)
            return 0
        elif flag == "--only":
            if not rest:
                print("--only нужен кусок имени случая", file=sys.stderr)
                return 2
            wanted.append(rest.pop(0))
        else:
            print(f"неизвестный флаг {flag}", file=sys.stderr)
            return 2

    selected = [(n, f) for n, f in CASES if not wanted or any(w in n for w in wanted)]
    if not selected:
        print(f"ни один случай не подошёл под {wanted}", file=sys.stderr)
        return 2

    failures = 0
    for name, func in selected:
        started = time.time()
        with tempfile.TemporaryDirectory(prefix="review-round-selftest-") as tmp:
            try:
                want, got = func(tmp)
            except Exception as exc:  # noqa: BLE001
                want, got = "без исключения", f"{type(exc).__name__}: {exc}"
        took = time.time() - started
        if want == got:
            if verbose:
                print(f"ok  {took:5.1f}s  {name} -> {got}")
            continue
        failures += 1
        print(f"FAIL{took:5.1f}s  {name}: ждали {want!r}, получили {got!r}")

    print(f"{len(selected) - failures}/{len(selected)} cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
