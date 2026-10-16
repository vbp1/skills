---
name: review-panel
description: "Run a parallel panel of read-only review tracks over a scope of changes: mechanical triage, one agent per lens, every must-fix finding checked against the code before it is reported, a persisted round file, and re-review rounds until nothing must-fix or important survives. Use before committing, when the user asks for a thorough or multi-perspective review of a branch or diff, or when a review needs to be repeatable rather than a single opinion."
argument-hint: "[scope: worktree (default) | staged | <git revision>] [spec=<path to the task card>]"
---

# /review-panel — the review panel

Runs a panel of parallel, read-only review tracks over one scope of changes, then drives
re-review rounds until no must-fix or important finding survives.

This command **only reviews**. It runs no build, no test suite and no linter, touches no git
state, and never commits. A caller that also needs those runs them itself, around this.

## Scope

**Arguments: $ARGUMENTS**

A token of the form `spec=<path>` names the spec for the `spec` track (step 1c); every other
token is the scope.

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

It proposes a track subset with a reason per track kept and per track skipped, and prints
`judgeQuestions` — the things a regex structurally
cannot decide. If `recommendation` is `optout`, no code changed: say so and stop, rather than
spending the panel on nothing.

### 1b. Judge subagent (1 agent)

Spawn ONE subagent (`general-purpose`) with the triage JSON and this brief. Every agent runs in
the background — the Agent tool has no wait-in-place mode — so spawn this one alone and **stop
until its completion notification arrives**: no round opened, no tracks spawned, and never a
guess at what it would have said.

> You are triaging a review, not performing it. A mechanical pass already produced the JSON
> below. Answer only its `judgeQuestions` against the real diff and adjust the track list. Read
> the changed files and, where a contract may have moved, their direct callers — do NOT audit
> logic, do NOT report bugs, do NOT modify files. Return `add[]` / `remove[]` (each entry: track
> + one-sentence reason) and a one-line `riskNote`.
> Zone `high` means you may only REMOVE tracks, never fewer than `correctness`, each with a
> stated reason. Zone `normal` means you may both add and remove, each with a stated reason.

If the judge fails or times out, use the triage proposal unchanged and say so out loud.

### 1c. Find the spec (no agent)

The `spec` track checks the change against the task it was written for, so it runs only when
that task is written down. Take the first source that yields one:

1. The `spec=<path>` argument. A path that does not exist or is empty fails here, before a
   round is claimed: report the path and that nothing was reviewed.
2. A task card whose frontmatter carries `branch: <current branch>` — the layout the
   `taskflow` plugin writes:
   `rg -l --glob '!todos/archived/**' "^branch: $(git branch --show-current)$" todos/`.
3. This session's focus file `todos/.active.d/<session_id>`, naming a card under `todos/`.
4. Issue references in the commit messages of the scope (`#123`, `Closes #45`) — for
   `worktree` and `staged`, the commits on the branch since it left the default branch. Fetch
   each with `gh issue view <n> --comments` after the round is open, and save the text verbatim
   to `$DIR/spec-source.md`; that file is the spec the track reads. The track's shell cannot
   run `gh`.

Triage and the judge do not see this track: whether it runs depends only on this step. A spec
found here adds `spec` to the final set after the judge's `add[]`/`remove[]`, and the "full
panel" option includes it; the user may still drop it in step 2.

Two or more candidates at the same step: put them to the user in the step 2 question and run
the track on the one chosen — never pick one yourself. No source at all: the `spec` track does
not run, and the report says "no spec available" — never let the track infer requirements from
the code.

## 2. Confirm, open the round, run the tracks

If `over-engineering` is in the set, first check that its lens is actually available:

```
claude plugin list 2>/dev/null | grep -q ponytail && echo lens-ok || echo lens-missing
```

On `lens-missing` that track would run and report `LENS NOT LOADED`, so raise it **in the same
question** rather than discovering it in the report: say gate 8 is currently half-covered, offer
the two install commands from *The optional lens* below, and let the user choose to install, or to
proceed knowing `over-engineering` will not review anything. Do not install it for them — it comes
from a third-party marketplace, and a plugin that pulls in another author's plugin unasked is
exactly what Claude Code's cross-marketplace block exists to prevent.

Show the final set via `AskUserQuestion` — tracks to run, what was dropped and why, the judge's
`riskNote`, and the spec the `spec` track will read or "no spec available" — with options "run the proposed subset" / "run the full panel" / "skip the panel".
Then claim a round:

```
read -r N DIR < <("${CLAUDE_PLUGIN_ROOT}/scripts/review-round.sh" open --scope <the scope from the top>)
```

Pass the **same scope** the triage used — a round opened over a different set of changes than the
one that was triaged reports findings about code nobody asked about. That writes
`$DIR/round-$N.diff`, which is both the "before" for the next round **and the only thing the
tracks are given to review**. Open a fresh round the same way for every re-review round.

Then spawn **one `Agent` per selected track, all in a single message** so they run concurrently —
background is the only mode there is. **Record the identifier each spawn returns** — it is how you
reach that track in a later round, and it goes in the report. Wait for every track's completion
notification before checking findings or writing the report; a report written while a track is
still running describes a review that did not finish.

| Track | `subagent_type` | Focus |
| --- | --- | --- |
| `correctness` | `review-panel:review-correctness` | correctness bugs; adherence to the project's own conventions and lint rules as its CLAUDE.md states them |
| `silent-failures` | `review-panel:review-silent-failures` | swallowed errors, empty or over-broad catch blocks, inappropriate fallbacks |
| `type-design` | `review-panel:review-type-design` | encapsulation, invariants, nullability in the types the change introduces |
| `tests` | `review-panel:review-tests` | coverage gaps; every bug fix needs a regression test that fails without the fix |
| `comments` | `review-panel:review-comments` | comment accuracy vs code; stale or misleading docs the change introduced or left |
| `adversary` | `review-panel:review-adversary` | breaking it: inputs or states that make the changed code throw, return a wrong result, corrupt state, or violate an invariant |
| `over-engineering` | `review-panel:review-over-engineering` | reinvented stdlib or existing helpers, unneeded dependencies, speculative abstractions, dead flexibility |
| `simplify` | `review-panel:review-simplify` | advisory simplifications that preserve behaviour, including the Fowler smell list in its prompt |
| `spec` | `review-panel:review-spec` | the task the change was written for: requirements missing or partial, implemented wrongly, behaviour nobody asked for; every finding quotes the spec line. Runs only when step 1c found a spec |

**Use these agent types, not the `pr-review-toolkit:` ones** that six of them are derived from.
The upstream originals declare no `tools:` at all and therefore inherit everything, write tools
included. These forks keep the upstream prompts but are read-only two ways, both verified by
probe:

- `tools:` omits `Write` and `Edit`, and tool removal is enforced — a track reports "Write tool
  not in available functions".
- `Bash` stays (a reviewer needs `git log`, `git blame`), and this plugin's
  `hooks/review-agent-guard.py` restricts it **by `agent_type`**: reads pass, anything that
  writes, moves, deletes or changes git state is **denied** before it runs. Denied, not prompted —
  a background panel of nine tracks must not stop to interrogate the developer.

Do **not** try to scope the shell in frontmatter instead: `Bash(git diff:*)` in an agent's `tools:`
is silently ignored and yields unrestricted `Bash`. Extend the guard's allowlist rather than
loosening the agents.

Every track prompt gives the absolute path of `round-$N.diff` as the authoritative change under
review, and states: review **only** the changed lines/files; report concrete findings with file,
line/range in the source file as it stands after the change (never a line number of the diff
file), severity (`critical`/`important`/`minor`) and a precise detail — no generic advice. The
`spec` track's prompt also gives the absolute path of the spec from step 1c.

It also gives the absolute path of `$DIR/round-$N.files` as the track's **checklist**, with its
shape: one line per file, `<content hash or the word deleted><TAB>path`, so the paths are the
second field (`cut -f2`). Every track closes its report with a coverage block naming `<total>`
from that list and a `skipped:` line per file it did not review — the format sits in each agent
file, so the prompt names the checklist path and the count, and does not restate the block.
`"${CLAUDE_PLUGIN_ROOT}/scripts/review-round.sh" files $N` prints the same list with a
`present`/`deleted` tag instead of the hash; that form is for you, in step 3.

**A checklist longer than 25 files splits `correctness` and `adversary`.** Right after `open`,
run `"${CLAUDE_PLUGIN_ROOT}/scripts/review-round.sh" parts $N --max 25`: it writes
`$DIR/round-$N.part-<letter>.files`, each in the shape of `round-$N.files`, and prints one line
per part with its letter, file count and path. Spawn `correctness` and `adversary` once per
part, each prompt naming its part file as the checklist and that file's count as `<total>`;
the prompt also states the part's letter and that the other parts belong to other agents of
the same track. Every other track runs once over the full `round-$N.files`. Name the number of
parts and the resulting agent count in the step 2 question, next to the track list.

Each prompt carries a **turn budget**: the length of that track's checklist plus 10 tool calls,
and never fewer than 20. A split track counts its part file; every other track counts the full
checklist. Tell each track it is reviewing a diff, not surveying the repository — read what the
finding turns on and stop, and spend the budget on closing every file of the checklist.

## 3. Save the reports, assert the tree is untouched, check the findings, write the report

**Save each track's report when its completion notification arrives.** Tracks write no files;
the notification names the track's output file. Run
`"${CLAUDE_PLUGIN_ROOT}/scripts/review-round.sh" save $N <track> <output file>` (`<track>` is the
key from the table above, and `<track>-<letter>` for one part of a split track, e.g.
`correctness-b`): it copies the track's final message verbatim to `$DIR/round-$N-<track>.md`
and prints that path. Record the path per track in the round file's
`## Tracks` table, and refer to findings by that path from then on.

**Change nothing in the working copy while any track is still running** — not a fix, not a
format pass, not a scratch file. The seal below compares the tree against the snapshot taken
at `open`, so an edit made in the main loop mid-round reads as a track having mutated the tree.
Wait for the last track, seal the round, then start fixing.

Then, once every track is back and before the first fix:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/review-round.sh" seal $N
```

It must exit 0 with no output — apart from the lines it prints to stderr naming the working
copy and branch it sealed against, and the moment it recorded. Read them: they are what tells
you the seal ran where the round was opened. Run from another copy, the script names both and
compares nothing; pass `-C <the copy the round belongs to>` when your own directory has moved.

Any line on stdout means something mutated the shared tree or the stash list while a read-only
panel was running — nothing is sealed then; name it to the user as an incident and restore
before continuing; do not fold it into the review. The seal is the check that catches a write
if the read-only enforcement ever stops holding.

The seal is the boundary between the panel and the fixes: past it, `check $N` reports the files
the fixes touched and exits 0 instead of reading them as a track's writes. A round is sealed
once — the moment stands where the panel ended.

**Then check coverage, before the findings.** A track that reviewed four of fourteen files
reports as confidently as one that reviewed all fourteen; the counts are the only place that
difference shows.

```
"${CLAUDE_PLUGIN_ROOT}/scripts/review-round.sh" files $N | wc -l   # <total> every unsplit track was given
wc -l < "$DIR/round-$N.part-<letter>.files"                       # <total> of one part of a split track
```

Read each report's closing `reviewed: <n>/<total>` line and its `skipped:` lines, against the
checklist that report was given. A split track is complete only when every one of its parts
is. Three outcomes:

- **`<n>` plus the skipped lines equals `<total>`, and each skip names what the file holds** —
  the track is complete; carry its numbers into the round file.
- **The lines do not add up, or `<total>` disagrees with the list** — the track lost files
  silently. Reach it with `SendMessage` (the id from its spawn), naming the paths it left
  unaccounted for, and have it close each one. Do not fill the gap yourself.
- **A skip reads as "not relevant to my lens" with nothing behind it** — send the path back
  and ask what the file holds. A lens that genuinely has nothing to ask of a file can say so
  in a clause; one that never opened the file cannot.

A track that fails to close its checklist after that send is a partial track: name it in the
round file's `## Coverage` table with what it missed, and treat its lens as not run over those
files rather than folding the gap into a clean verdict.

**You check the findings yourself, against the code.** A track's `critical` is the report's
must-fix, and every one of them is settled in the main loop before it reaches the report: read
the lines the track names, follow the mechanism, and where a claim is mechanically decidable,
decide it by evidence — run the query, apply the migration chain, reproduce the loss. You hold
the diff already; a fresh session would have to boot and re-read a file you have open, and the
answer it most often returns is "the facts hold, but this is not worth fixing before commit" or
"not introduced by this diff" — a priority call, which is yours to make.

Each item in the report carries the outcome of that check: confirmed (with what settled it),
corrected (the mechanism differs from the claim — state how), or dropped (with the reason).
Findings you did not check go in **as the track raised them, marked unchecked** — never relay one
to the user as confirmed. Where the evidence runs long, put it in `$DIR/round-$N-verify.md` and
link it from the report rather than inlining it.

**Write `$DIR/round-$N.md` before touching any code.** Nothing else holds this report.

```markdown
# Review — round <N> — <verdict: ready | needs-fixes | blocked>
Branch: <branch>   Tracks: correctness, tests, …
Spec: <path the spec track read | no spec available>

## Tracks
| track | part | agent id | report |    # the identifier each spawn returned — how round N+1 reaches it
| correctness | b | <id> | round-<N>-correctness-b.md |   # part "—" for a track that ran over the whole checklist
| tests | — | <id> | round-<N>-tests.md |

## Coverage                      # files on the checklist: <total>; parts: <letter>=<count>, …
| track | part | reviewed | skipped, and why |
| correctness | b | 24/24 | — |
| tests | — | 11/14 | src/ui/*.tsx — presentation only, no test surface |
| comments | — | 9/14 | 5 files unaccounted for — partial track |   # a gap it never closed

## Open items
Count: <N>                       # must-fix + important only; what the next round must answer
1. [critical][correctness] path/file.ts:120 — title
2. [important][tests] path/file.test.ts:44 — title

## Nice-to-have                  # for the record; earns no round
- [minor][comments] …

## Dropped                       # checked against the code and not upheld
- <title> — <one-line reason, and what settled it>
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
`## Tracks` table** — for a split track, the agent of the part that raised the item. Re-review
rounds run over the delta and are not split: when the parts of a split track own no open item,
none of them is reached. A send resumes that agent from its transcript, so the track still holds its
own findings and the reasoning behind them; you are continuing a conversation, not briefing a
stranger. Say to each:

- **its own items only**, one per line, each with the outcome — for a fix, what changed and where;
  for a rejection, **the reasoning, addressed to it**, so it can accept or push back with
  evidence. Handing every track the whole report invites `comments` to re-litigate a correctness
  rejection it never made;
- **what the fixes touched**: `"${CLAUDE_PLUGIN_ROOT}/scripts/review-round.sh" delta <N-1>` names
  every file that changed since, `changed`/`added`/`gone`. The `before` is `round-<N-1>.diff`. Tell
  the track to review those through its own lens — a fix is new code and nobody has reviewed it;
- to **answer every item** and open no unrelated new ground unless a fix created it;
- that its checklist for this round is the delta, not the full file list — a re-review closes
  the files the fixes touched plus its own items, and its coverage block counts against that.
  Round 1 is the round where a track accounts for every changed file.

Also spawn **one broad-lens `Agent` over the delta alone** — no track lens, no prior items, just
"here are the files the fixes touched, what breaks?". A fix in `correctness`'s area can break
something only `type-design` would have noticed, and that track is not in this round. The delta is
small, so this costs one agent.

If an id no longer resolves, spawn that track fresh and hand it its own `Open items` lines from the
round file plus its saved report `round-<N-1>-<track>.md`, verbatim, plus the delta. That is the degraded path — say so in the report, since a
fresh track re-derives reasoning the resumed one remembers.

Cross-check the items you send against the previous round's `Count`: every must-fix and important
finding earns an outcome. A track whose findings were all nice-to-have gets no round, and
`simplify` never does — it produces no severities.

Repeat until no must-fix or important finding survives. If a track answers your rejection with
evidence, the finding stands — fix it or take the disagreement to the user; do not reject it a
second time on the same grounds.

Then state the verdict explicitly, **naming which tracks ran and what round 1 covered** — a clean
verdict from 2 tracks is not the same claim as one from the full panel, and neither is a verdict
from a panel that reviewed nine files out of fourteen. Where the `## Coverage` table holds a
partial track, say which files no lens reached. Name the spec the `spec` track checked against, or
say "no spec available"; a `spec` report that opens with `SPEC NOT READABLE` reviewed nothing —
report the track as not run. If `over-engineering` opened its report with
`LENS NOT LOADED`, its preloaded lens is missing and it reviewed nothing: say so rather than
counting it clean, and fix the `skills:` entry in
`${CLAUDE_PLUGIN_ROOT}/agents/review-over-engineering.md`.

## The optional lens

The `over-engineering` track applies the `ponytail-review` lens, preloaded from the ponytail
plugin. That plugin is an optional companion rather than a declared dependency — the other eight
tracks do not need it, and a dependency that cannot be resolved would disable this plugin
entirely. Install it to get the `over-engineering` track:

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
