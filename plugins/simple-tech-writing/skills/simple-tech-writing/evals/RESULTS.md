# Measured results

Model `claude-sonnet-5`, 8 tasks per language, 2 runs per cell, 48 generations, $2.54.
Every call ran with a substituted `HOME`, so the user's `CLAUDE.md` and plugin hooks
stayed out of the context. Counters: `ru_lint.py` for Russian, `ste_lint.py` (from the
SimpleEnglish repo) for English.

| language | condition | n | violations per 100 words | mean sentence, words | words per text |
|---|---|---|---|---|---|
| Russian | no skill | 16 | 3.05 | 15.2 | 88.6 |
| Russian | skill | 16 | **0.65** (−79%) | 6.9 | 82.7 |
| English | skill | 16 | **0.22** | 9.4 | 89.3 |

English reference points from the same counter, same model, same clean environment:
3.72 without any rules, 0.52 with the single-language SimpleEnglish skill. The
bilingual rules do not damage English text.

## Russian violations by kind, summed over 16 generations per condition

| kind | no skill | skill |
|---|---|---|
| sentence over limit | 11 | 0 |
| synonym rotation | 10 | 6 |
| "-ся" passive | 8 | 4 |
| gerund clause | 8 | 0 |
| participle clause | 6 | 1 |
| trailing condition | 4 | 0 |
| hedge ("следует", "рекомендуется") | 3 | 0 |
| filler word | 2 | 0 |
| nominalization | 0 | 0 |

Sentence length, gerunds, participles, trailing conditions, hedges and filler go to
zero or near zero. Two categories survive: synonym rotation (10 → 6) and the "-ся"
passive (8 → 4). Both need the writer to hold the whole document in view, which a
single generation does not do well.

## What the numbers do not say

- The counter is a regular-expression pass, not a morphological parser. It undercounts
  (no genitive-chain detection, no agreement checks) and it fires on legitimate terms
  such as "подключение". It counts the same way in both conditions, so the comparison
  holds even where the absolute value is rough.
- Output tokens go up with the skill (280 → 2067 on Russian tasks): the model reasons
  more. Delivered texts get shorter (88.6 → 82.7 words), the reasoning does not.
- Two runs per cell. Re-run the matrix for tighter numbers; existing raw files are
  skipped, so delete `raw/` to start fresh.
- No blind quality judging in this run. The predecessor skill was judged that way and
  the coverage score went up, not down; that result is not transferred here.

Reproduce:

```
STW_CLEAN_HOME=/path/to/clean/home python3 run_bench.py ru
STW_CLEAN_HOME=/path/to/clean/home python3 run_bench.py en
```

`STW_CLEAN_HOME` must contain `.claude/.credentials.json`. Delete that directory when
the run is over.
