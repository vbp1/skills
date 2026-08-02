---
name: break-it-panel
description: "Settle the review panel's adversarial predictions with real tests. Takes the concrete breaks the adversary track predicted — file, line, triggering input — writes a focused test per prediction, runs it, and keeps only what caught a real defect or covers a genuinely valuable edge case. Use after a review-panel round when the adversary track left critical or important findings."
argument-hint: "[round number, or the predictions to attack]"
---

# break-it-panel — settle the panel's predictions

The `adversary` track of the review panel predicts breaks; it cannot run anything, so every
finding it files is a **hypothesis with a stated trigger**. This is the experiment that settles
them.

Target: **$ARGUMENTS** — a round number, or the predictions themselves. With neither, use the
latest round.

## Where this runs

In the main conversation, **after** a panel round, with the user's agreement. It writes test files
and runs a test command, so it is not a review track and never runs inside the panel: panel tracks
hold no `Write` and a read-only shell, and that is not relaxed for convenience.

Work from the repository root (`git rev-parse --show-toplevel`).

## 1. Collect the predictions

Read the round report — `"${CLAUDE_PLUGIN_ROOT}/scripts/review-round.sh" path <N>`, or `latest` for
the round number — and take the `adversary` items from `## Open items`. Each carries a file, a
line or range, the exact triggering input or state, expected behaviour versus predicted behaviour,
and often the run that would decide it.

Attack **critical and important** predictions. Minor ones are not worth a test file.

If the round has no `adversary` items, say so and stop. Do not invent an attack surface — the
manual `/break-it` is the tool for attacking a change from scratch, and it is a different job.

## 2. Judge each prediction before testing it

For each one, decide from the code whether it can be true at all. A prediction that a guard three
lines up already handles is dead on arrival — record that and move on rather than writing a test
that proves the guard works. Say which predictions you dropped this way and why; that is a finding
about the review, not wasted work.

Where a prediction targets something unit tests reach badly — a database, the network, IPC,
streaming, a framework render boundary — say so and skip it. An integration-shaped break dressed
as a unit test proves nothing.

Where the target has framework- or server-only dependencies that cannot be imported into a test,
the pure logic usually can be: extract it into a sibling helper module and test that. Propose the
extraction to the user before doing it — it changes production code.

## 3. Write and run one test per surviving prediction

- Colocate the test with its target, using the project's existing framework and conventions —
  mirror a neighbouring test file rather than inventing a style.
- Encode the prediction literally: the exact triggering input the track named, asserting the
  behaviour the track said *should* happen. The test fails if the track was right.
- Run **scoped to that file or area**, never the whole suite. If the project documents an exact
  single-file test command (CLAUDE.md, AGENTS.md, README, package scripts), use that; otherwise
  use the framework's filter flag.
- Tee output to a temp file and read it; do not re-run just to scroll.
- Phantom module-resolution errors mean a stale runner cache — clear it and re-run once.

## 4. Triage every result

- **Failed** → decide: real defect, or bad test with a wrong expectation?
  - Real defect → the track was right. **Stop and surface it** — the finding, the failing test,
    and the proposed fix — and wait for confirmation before touching production code. On approval:
    fix the code and keep the test as a regression that fails without the fix. That regression is
    what the `tests` track requires of every bug fix.
  - Bad test → fix the expectation or discard it. The prediction is refuted, and that is a real
    answer worth recording.
- **Passed** → the code already handles the case; the prediction is refuted. Keep at most one or
  two as edge-case coverage where the case is genuinely valuable, and discard the rest. Passing
  noise is bloat.

## 5. Leave the tree clean

Remove every throwaway candidate. Keep only regressions for confirmed defects plus the few
high-value edge cases. Re-run what you kept, scoped, to confirm green — or red-by-design until an
approved fix lands.

## 6. Report back to the round

Summarise per prediction: **confirmed** (with the failing test and `file:line`), **refuted** (with
what the passing test showed), or **not testable here** (with why). Name which tests you kept.

Confirmed predictions become open items the panel's next round must see — they are now findings
with evidence, not hypotheses. Refuted ones can be closed against the `adversary` track with the
test as the argument, which is a stronger answer than a rejection in prose.

Do **not** commit here — hand back to the caller's normal gated flow.
