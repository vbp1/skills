#!/usr/bin/env python3
"""Замер скилла simple-tech-writing.

Русская часть: 8 задач x 2 условия (без скилла / со скиллом) x N проходов,
счёт промахов через ru_lint.py.
Английская часть (регрессия): те же 8 английских задач, что у скилла-предка
SimpleEnglish, счёт через его ste_lint.py — чтобы двуязычные правила не
испортили английский текст.

Каждый вызов идёт с подменённым HOME: иначе `claude -p` подтягивает
пользовательский CLAUDE.md и хуки плагинов, и замер меряет их, а не скилл.
Нужен каталог с копией `~/.claude/.credentials.json` — путь задаётся
переменной STW_CLEAN_HOME. Удалите каталог после прогона.

Использование:
  STW_CLEAN_HOME=/tmp/clean python3 run_bench.py ru      # русская матрица
  STW_CLEAN_HOME=/tmp/clean python3 run_bench.py en      # английская регрессия
  python3 run_bench.py report
"""
import concurrent.futures as cf
import json
import os
import pathlib
import subprocess
import sys

import ru_lint

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent / "SKILL.md"
RAW = HERE / "raw"
MODEL = "claude-sonnet-5"
RUNS = 2
EN_REPO = pathlib.Path.home() / "SimpleEnglish" / "evals"


def clean_home():
    h = os.environ.get("STW_CLEAN_HOME")
    if not h or not (pathlib.Path(h) / ".claude" / ".credentials.json").exists():
        sys.exit("STW_CLEAN_HOME must point at a directory holding "
                 ".claude/.credentials.json (copy of your own). Nothing was run.")
    return h


def call_claude(prompt, model=MODEL, timeout=420):
    env = dict(os.environ, HOME=clean_home())
    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "json",
           "--disallowedTools", "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd="/tmp", env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"claude rc={proc.returncode}: {proc.stderr[:200]}")
    out = json.loads(proc.stdout)
    if isinstance(out, list):
        out = next(m for m in out if m.get("type") == "result")
    if out.get("is_error"):
        raise RuntimeError(str(out.get("result"))[:200])
    u = out.get("usage", {})
    return {"text": out.get("result", ""),
            "input_tokens": (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0),
            "output_tokens": u.get("output_tokens"),
            "cost_usd": out.get("total_cost_usd")}


def build_prompt(scenario, arm):
    if arm == "baseline":
        return scenario["prompt"]
    return ("Follow these writing instructions exactly:\n\n" + SKILL.read_text()
            + "\n\n---\n\nTask: " + scenario["prompt"])


def one(lang, arm, sc, run, linter):
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / f"{lang}__{arm}__{sc['id']}__r{run}.json"
    if out.exists():
        return "skip"
    try:
        res = call_claude(build_prompt(sc, arm))
    except Exception as e:
        return f"FAIL {lang} {arm} {sc['id']} r{run}: {e}"
    res.update(lang=lang, arm=arm, scenario=sc["id"], type=sc["type"], run=run)
    res["lint"] = linter.lint(res["text"], sc["type"])
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    return f"ok {lang} {arm} {sc['id']} r{run} viol/100w={res['lint']['violations_per_100w']}"


def run_matrix(lang, scenarios, linter, arms=("baseline", "skill")):
    jobs = [(lang, a, s, r, linter) for a in arms for s in scenarios for r in range(1, RUNS + 1)]
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for f in cf.as_completed([ex.submit(one, *j) for j in jobs]):
            print(f.result(), flush=True)


def report():
    rows = [json.loads(p.read_text()) for p in sorted(RAW.glob("*.json"))]
    if not rows:
        sys.exit("no results in " + str(RAW))
    agg = {}
    for r in rows:
        a = agg.setdefault((r["lang"], r["arm"]), {"v": [], "s": [], "w": [], "o": [], "c": []})
        a["v"].append(r["lint"]["violations_per_100w"])
        a["s"].append(r["lint"]["mean_sentence_words"])
        a["w"].append(r["lint"]["words"])
        a["o"].append(r["output_tokens"] or 0)
        a["c"].append(r["cost_usd"] or 0)
    mean = lambda xs: round(sum(xs) / max(1, len(xs)), 2)
    print("| lang | arm | n | viol/100w | mean sent | words | out tok |")
    print("|---|---|---|---|---|---|---|")
    for (lang, arm), a in sorted(agg.items()):
        print(f"| {lang} | {arm} | {len(a['v'])} | {mean(a['v'])} | {mean(a['s'])} "
              f"| {mean(a['w'])} | {round(mean(a['o']))} |")
    kinds = {}
    for r in rows:
        if r["lang"] != "ru":
            continue
        for k, v in r["lint"]["violations"].items():
            kinds.setdefault(k, {"baseline": 0, "skill": 0})[r["arm"]] += v
    print("\n| промах (ru) | без скилла | со скиллом |")
    print("|---|---|---|")
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]["baseline"]):
        print(f"| {k} | {v['baseline']} | {v['skill']} |")
    print(f"\nspend: ${round(sum(r['cost_usd'] or 0 for r in rows), 2)} over {len(rows)} generations")


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "report"
    if what == "ru":
        run_matrix("ru", json.loads((HERE / "scenarios_ru.json").read_text()), ru_lint)
    elif what == "en":
        if not (EN_REPO / "ste_lint.py").exists():
            sys.exit(f"English regression needs {EN_REPO}/ste_lint.py and scenarios.json. Nothing was run.")
        sys.path.insert(0, str(EN_REPO))
        import ste_lint
        run_matrix("en", json.loads((EN_REPO / "scenarios.json").read_text()), ste_lint, arms=("skill",))
    report()


if __name__ == "__main__":
    main()
