---
name: review-panel
description: "Run a parallel panel of read-only review tracks over a scope of changes: mechanical triage, one agent per lens, adversarial verification of critical findings, a persisted round file, and re-review rounds until nothing must-fix or important survives. Use before committing, when the user asks for a thorough or multi-perspective review of a branch or diff, or when a review needs to be repeatable rather than a single opinion."
argument-hint: "[scope: worktree (default) | staged | <git revision>]"
---

# /review-panel — the review panel

Runs a panel of parallel, read-only review tracks over one scope of changes, then drives
re-review rounds until no must-fix or important finding survives.

This command **only reviews**. It runs no build, no test suite and no linter, touches no git
state, and never commits. A caller that also needs those runs them itself, around this.

## Scope

**Scope requested: $ARGUMENTS**

- **Empty — the default, and the rule for a pre-commit review: `worktree`.** Every uncommitted
  change, staged or not, including untracked files. Before a commit the panel reviews *all* the
  work in the tree, not a hand-picked subset — a caller asking to review less before committing
  should be told so.
- `staged` — only the index.
- Any git revision `git diff` accepts: `main...HEAD` for a whole branch against its base,
  `HEAD~3..HEAD`, a single sha, a tag. Use this for reviewing already-committed work.

An unusable scope fails before a round is claimed — report the error as-is; nothing was reviewed.

## 1. Size the panel

The full panel is ~10–30 agents. Size it to the diff first — in three steps, in this order.

### 1a. Mechanical triage (no tokens)

Point it at the same scope the panel will review, from the repository root:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/triage.py" --scope worktree --json
#   staged      → --scope staged
#   a revision  → --base <revision>
```

It proposes a track subset with a reason per track kept and per track skipped, sets `verifiers`
(1 normally, 3 in the high zone), and prints `judgeQuestions` — the things a regex structurally
cannot decide. If `recommendation` is `optout`, no code changed: say so and stop, rather than
spending the panel on nothing.

### 1b. Judge subagent (1 agent)

Spawn ONE subagent (`general-purpose`, `run_in_background: false`) with the triage JSON and this
brief:

> You are triaging a review, not performing it. A mechanical pass already produced the JSON
> below. Answer only its `judgeQuestions` against the real diff and adjust the track list. Read
> the changed files and, where a contract may have moved, their direct callers — do NOT audit
> logic, do NOT report bugs, do NOT modify files. Return `add[]` / `remove[]` (each entry: track
> + one-sentence reason), `verifiers`, and a one-line `riskNote`.
> Zone `high` means you may only REMOVE tracks, never fewer than `correctness`, each with a
> stated reason. Zone `normal` means you may both add and remove, each with a stated reason.
> `verifiers` must be an odd integer between 1 and 5 — a majority decides each finding, so an
> even panel would let one sceptic veto a real one, and the count multiplies by the number of
> critical findings.

If the judge fails or times out, use the triage proposal unchanged and say so out loud.

## 2. Confirm, open the round, run the tracks

Show the final set via `AskUserQuestion` — tracks to run, what was dropped and why, the judge's
`riskNote` — with options "run the proposed subset" / "run the full panel" / "skip the panel".
Then claim a round:

```
read -r N DIR < <("${CLAUDE_PLUGIN_ROOT}/scripts/review-round.sh" open --scope <the scope from the top>)
```

Pass the **same scope** the triage used — a round opened over a different set of changes than the
one that was triaged reports findings about code nobody asked about. That writes
`$DIR/round-$N.diff`, which is both the "before" for the next round **and the only thing the
tracks are given to review**. Open a fresh round the same way for every re-review round.

Then spawn **one `Agent` per selected track, all in a single message** so they run concurrently,
`run_in_background: true`. **Record the identifier each spawn returns** — it is how you reach that
track in a later round, and it goes in the report.

| Track | `subagent_type` | Focus |
| --- | --- | --- |
| `correctness` | `review-panel:review-correctness` | correctness bugs; adherence to the project's own conventions and lint rules as its CLAUDE.md states them |
| `silent-failures` | `review-panel:review-silent-failures` | swallowed errors, empty or over-broad catch blocks, inappropriate fallbacks |
| `type-design` | `review-panel:review-type-design` | encapsulation, invariants, nullability in the types the change introduces |
| `tests` | `review-panel:review-tests` | coverage gaps; every bug fix needs a regression test that fails without the fix |
| `comments` | `review-panel:review-comments` | comment accuracy vs code; stale or misleading docs the change introduced or left |
| `adversary` | `review-panel:review-adversary` | breaking it: inputs or states that make the changed code throw, return a wrong result, corrupt state, or violate an invariant |
| `over-engineering` | `review-panel:review-over-engineering` | reinvented stdlib or existing helpers, unneeded dependencies, speculative abstractions, dead flexibility |
| `simplify` | `review-panel:review-simplify` | advisory simplifications that preserve behaviour |

**Use these agent types, not the `pr-review-toolkit:` ones** that six of them are derived from.
The upstream originals declare no `tools:` at all and therefore inherit everything — that is how a
review track came to run `git stash` on a live worktree and another to drop a scratch test file
into `src/`, which broke the unit suite. These forks keep the upstream prompts but are read-only
two ways, both verified by probe:

- `tools:` omits `Write` and `Edit`, and tool removal is enforced — a track reports "Write tool
  not in available functions".
- `Bash` stays (a reviewer needs `git log`, `git blame`), and this plugin's
  `hooks/review-agent-guard.py` restricts it **by `agent_type`**: reads pass, anything that
  writes, moves, deletes or changes git state is **denied** before it runs. Denied, not prompted —
  a background panel of eight tracks must not stop to interrogate the developer.

Do **not** try to scope the shell in frontmatter instead: `Bash(git diff:*)` in an agent's `tools:`
is silently ignored and yields unrestricted `Bash`. Extend the guard's allowlist rather than
loosening the agents.

Every track prompt gives the absolute path of `round-$N.diff` as the authoritative change under
review, and states: review **only** the changed lines/files; report concrete findings with file,
line/range, severity (`critical`/`important`/`minor`) and a precise detail — no generic advice.

## 3. Assert the tree is untouched, verify the criticals, write the report

The moment the tracks return:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/review-round.sh" check $N
```

It must exit 0 with no output. Any line means something mutated the shared tree or the stash list
while a read-only panel was running — name it to the user as an incident and restore before
continuing; do not fold it into the review. The tracks cannot cause this any more, but the check
costs nothing and is the only thing that would catch it if that ever stops holding.

**Verify `critical` findings only.** Spawn one verifier `Agent` per critical finding (`verifiers`
from triage: 1 normally, 3 on a fragile path — odd, so a majority decides), each told to
adversarially check the claim against the real code and answer *does this hold*.

Everything below `critical` goes into the report **as its track raised it**. Measured over a real
141-agent run, 19 of 22 verifier rejections were "the facts hold, but this is not worth fixing
before commit" or "not introduced by this diff" — a priority call you make for free with the diff
already in context, where a fresh verifier session costs ~25k tokens just to boot and re-read a
file you have open. So **triage the unverified findings yourself**, and never relay them to the
user as confirmed.

**Write `$DIR/round-$N.md` before touching any code.** Nothing else holds this report.

```markdown
# Review — round <N> — <verdict: ready | needs-fixes | blocked>
Branch: <branch>   Tracks: correctness, tests, …   Verifiers: <N>

## Tracks
| track | agent id |            # the identifier each spawn returned — how round N+1 reaches it
| correctness | <id> |

## Open items
Count: <N>                       # must-fix + important only; what the next round must answer
1. [critical][correctness] path/file.ts:120 — title
2. [important][tests] path/file.test.ts:44 — title

## Nice-to-have                  # for the record; earns no round
- [minor][comments] …

## Rejected by verify
- <title> — <one-line reason>
```

Then act on it: apply must-fix and important findings, reject the rest **with reasoning** — the
re-review round below is where a rejection gets answered. Fixing code is the caller's work, not
the panel's.

**When `adversary` leaves critical or important predictions**, remember they are hypotheses: that
track cannot run anything. `break-it-panel`, the sibling skill in this plugin, is what settles them
with real tests. Offer it to the user; never run it inside the panel.

## 4. Re-review round

A finding you acted on has not been reviewed in its fixed form; a finding you rejected has only
heard one side; and a fix can introduce a defect of its own. So run another round.

**Open it first**, over the same scope as round 1 —
`read -r N DIR < <("${CLAUDE_PLUGIN_ROOT}/scripts/review-round.sh" open --scope <the scope from the top>)`
— then reach each track that owns an open item **with `SendMessage`, using the id from round N−1's
`## Tracks` table**. A send resumes that agent from its transcript, so the track still holds its
own findings and the reasoning behind them; you are continuing a conversation, not briefing a
stranger. Say to each:

- **its own items only**, one per line, each with the outcome — for a fix, what changed and where;
  for a rejection, **the reasoning, addressed to it**, so it can accept or push back with
  evidence. Handing every track the whole report invites `comments` to re-litigate a correctness
  rejection it never made;
- **what the fixes touched**: `"${CLAUDE_PLUGIN_ROOT}/scripts/review-round.sh" delta <N-1>` names
  every file that changed since, `changed`/`added`/`gone`. The `before` is `round-<N-1>.diff`. Tell
  the track to review those through its own lens — a fix is new code and nobody has reviewed it;
- to **answer every item** and open no unrelated new ground unless a fix created it.

Also spawn **one broad-lens `Agent` over the delta alone** — no track lens, no prior items, just
"here are the files the fixes touched, what breaks?". A fix in `correctness`'s area can break
something only `type-design` would have noticed, and that track is not in this round. The delta is
small, so this costs one agent.

If an id no longer resolves, spawn that track fresh and hand it its own `Open items` lines from the
round file, verbatim, plus the delta. That is the degraded path — say so in the report, since a
fresh track re-derives reasoning the resumed one remembers.

Cross-check the items you send against the previous round's `Count`: every must-fix and important
finding earns an outcome. A track whose findings were all nice-to-have gets no round, and
`simplify` never does — it produces no severities.

Repeat until no must-fix or important finding survives. If a track answers your rejection with
evidence, the finding stands — fix it or take the disagreement to the user; do not reject it a
second time on the same grounds.

Then state the verdict explicitly, **naming which tracks ran** — a clean verdict from 2 tracks is
not the same claim as one from the full panel. If `over-engineering` opened its report with
`LENS NOT LOADED`, its preloaded lens is missing and it reviewed nothing: say so rather than
counting it clean, and fix the `skills:` entry in
`${CLAUDE_PLUGIN_ROOT}/agents/review-over-engineering.md`.

## The optional lens

The `over-engineering` track applies the `ponytail-review` lens, preloaded from the ponytail
plugin. That plugin is an optional companion rather than a declared dependency — the other seven
tracks do not need it, and a dependency that cannot be resolved would disable this plugin
entirely. Install it to get the eighth track:

```
claude plugin marketplace add DietrichGebert/ponytail
claude plugin install ponytail@ponytail
```

Without it the track reports `LENS NOT LOADED` and returns nothing, which is a declared gap
rather than a clean verdict.

## Maintenance

Six tracks are forks of Anthropic's `pr-review-toolkit` agents, copied rather than referenced
because the upstream originals hold `Write`, `Edit` and an unrestricted shell. The cost of copying
is staleness, so after updating plugins, or before a panel run on a project that matters:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-forks.py"
```

Exit 3 with a `DRIFTED` line means upstream changed that prompt — read their diff and decide
whether to carry the change over, then re-record the baseline with `--update`. Exit 2 means the
upstream plugin is not installed and nothing was checked; that is reported, never treated as
"nothing drifted".
