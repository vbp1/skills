# Third-party ruleset

`rule_docs/` and `mapping.json` come from
[alibaba/open-code-review](https://github.com/alibaba/open-code-review),
licensed under the Apache License 2.0 — the same licence this repository
carries (see `LICENSE` at the repository root).

- `rule_docs/*.md` — 52 review checklists, copied verbatim from
  `internal/config/rules/rule_docs/` at commit `main`, fetched 2026-09-14.
- `mapping.json` — copied verbatim from `internal/config/rules/system_rules.json`.
  It holds an ordered `path_rule_map` (glob pattern → checklist file, first match
  wins) plus `default_rule` for paths nothing else matches.

Neither file is modified here. `../rules-for-diff.py` reimplements the upstream
path-to-checklist resolution in Python, including the case-insensitive glob match
and the content sniff that tells an Objective-C `.m` file from a MATLAB one.

To refresh the ruleset, replace both from upstream and run
`python3 ../rules-for-diff-selftest.py` — one of its cases asserts that every
checklist named in `mapping.json` exists on disk and that no checklist on disk
goes unnamed.
