---
name: taskflow
description: >-
  Conductor that drives ONE small task per session end-to-end through a fixed
  10-step pipeline with human approval gates (other sessions drive their own
  tasks in parallel): reformulate → clarify in batches → user stories (+ UI
  mockup) → spec page → tech plan (grilled + risk pre-mortem + cross-reviewed) →
  plan page → TDD implementation + acceptance e2e green → review panel →
  cross-agent code review → live scenario pass + e2e re-run → commit + PR →
  summary page. State for each task lives in the frontmatter of
  `todos/NNN-slug.md` and is mirrored into an issue tracker when the project uses
  one. Use this when the user types /taskflow, or says "new task", "run this task
  through the process", "continue task", "task status", or otherwise asks to take
  a feature or fix from idea to PR with structured clarification, mockups, plan
  review and a final report. NOT for trivial one-off edits that need no ceremony,
  and NOT a generic code-review or planning helper (those are the individual
  skills this one orchestrates).
---

# /taskflow — conductor for small tasks

You are the **conductor**. You walk one task through 10 fixed steps, pausing at
approval gates. You do not invent process; you run the steps below and delegate
the heavy parts to existing skills and agents. Enforcement is **soft**: you never
silently skip a step, but you do not hard-block — if the user asks to jump ahead,
name the open gate and confirm first.

**One task per session, many tasks in flight.** Each session drives the task in
its own focus (`todos/.active.d/<session_id>`); other sessions drive theirs. Speak
about the focused task only — the full list comes from `/taskflow status` when the
user asks for it.

The **task file frontmatter is the single source of truth** for "where we are".
Update it the moment a step or gate changes. The bundled state-anchor hook
(`${CLAUDE_PLUGIN_ROOT}/hooks/taskflow-state.py`, wired by the plugin) re-injects
this session's task step on every turn, so state survives context compaction — but
the hook only *reports* frontmatter; keeping it correct is your job.

**Language.** Write every artifact — task file, questions, pages — in the language
the user writes to you in. Keep code identifiers, branch names, commit messages
and PR text in English. Keep every `AskUserQuestion` in plain language: no
identifiers, no file paths, no internal jargon in the question or the options.

---

## What the project must provide

Read these once, at step 1, and treat what you find as the project's law:

- **The task directory.** `todos/` at the repo root by default. Another name works
  when `TASKFLOW_DIR` carries it — the hook and this skill must agree.
- **The project's own rules file** (`CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`):
  its check commands, its test layout, its commit conventions. Never invent a
  build or test command — take it from there, or from `package.json` /
  `Makefile` / the equivalent, or ask.
- **The issue tracker, if any.** Ask once whether tasks get an issue and a board
  card; store the answer in the task frontmatter and stop asking.
- **Optional companion skills.** Use what is installed, skip what is not, and say
  out loud which of the two happened:
  `ui-mockup` (mockups), `review-panel` (the review panel), `technical-premortem`
  (risk pre-mortem), `create-pr` (opening the PR), `grill-me` (adversarial
  questioning), `visual-explainer` (diagrams), and any cross-agent review skill
  such as `codex-review` from <https://github.com/artwist-polyakov/polyakov-claude-skills>.

---

## Invocation

- `/taskflow <free-form description>` — start a NEW task at step 1 and put it in
  this session's focus.
- `/taskflow` (no args) or `/taskflow continue` — resume this session's focused
  task from its current `step`/`awaiting`. With no focus file for this session,
  print the `status` table and ask via `AskUserQuestion` which task to take.
- `/taskflow <NNN>` — put task NNN in this session's focus and resume it.
- `/taskflow status` (or `list`) — print a table of every `todos/*.md` task with
  id, title, step, awaiting, deps, status. (Scan frontmatter; no external call.)
  Mark the row this session holds, and the rows other sessions hold (scan
  `todos/.active.d/*`). This is the only place other tasks are listed.
- `/taskflow abandon` — mark the focused task `abandoned`, drop this session's
  focus file.

On resume, READ the task file first (frontmatter + body), restate "we are at step
K, waiting on X", then continue. Never assume context survived.

---

## The task file — `todos/NNN-slug.md`

Keep `todos/` out of version control unless the project says otherwise; task files
and pages are working material, not deliverables.

**Every document derived from the task lives in `todos/NNN-slug/`** — the task
directory, named after the task file without `.md`. Create it at step 1, next to
the task file. It holds the reviewer plan file (`plan.md`, step 4), the pre-mortem
report, the samples the scenario premortem gathers, and any other artifact a step
produces for this task. `todos/` itself carries only `NNN-slug.md` files and the
task directories. HTML pages stay in `todos/pages/`.

**Numbering:** scan `todos/` (incl. subdirs) for the highest `^(\d+)-` prefix, use
+1, zero-padded to 3. **slug:** short English kebab-case derived from the title.
**branch (step 4+):** `feat/NNN-slug`.

**Frontmatter (flat keys — the hook parses these; keep them top-level):**

```
---
id: 7
slug: export-csv
title: Export the report to CSV     # the user's language, human title
status: in_progress                 # planned|in_progress|blocked|review|done|abandoned
step: 4                             # 1..10, current step
step_label: Technical plan          # short label of the current step
awaiting:                           # empty = working; non-empty = paused for THIS approval
depends_on: [3]                     # task ids this one needs merged first
blocked_by: []                      # subset of depends_on not yet merged (you compute)
issue:                              # tracker id, when the project uses one
issue_url:
pr:
branch: feat/007-export-csv
created: 2026-01-31
page_spec:                          # todos/pages/NNN-spec.html once built
page_plan:
page_summary:
page_mockup:                        # NNN-mockup.html if UI
live_ui:                            # address of the running product (asked once at step 3)
---
```

Inline list syntax (`depends_on: [3]`) is required — the hook reads flat keys only,
and a block list parses as empty, so the blocked marker would silently not show.

**Body, append-only sections as steps complete:**

- `## Statement` — the structured reformulation (step 2).
- `## User stories` — stories + acceptance criteria (step 3).
- `## Mockups` — links to mockup HTML (step 3, if UI).
- `## Solution and plan` — approach, file-level plan with `file.ts:line`
  references, **`### Stages and tasks`** (the staged work breakdown), risks, test
  plan (step 4). Prose and references, no code blocks.
- `## Journal` — dated decision log: gate approvals, review verdicts, deviations.
  Holds `### Closed findings`, the review ledger (step 4).

Use the section names in the user's language; keep their order and their meaning.

**Session focus — `todos/.active.d/<session_id>`.** The file's only content is the
task filename (e.g. `007-export-csv.md`). Write it whenever you start, switch or
resume a task; delete it on done/abandon. Take `<session_id>` from the scratchpad
path in your system prompt (its last directory component before `scratchpad`), or
from the session id the harness gives you. While writing it, prune stale focus
files: `find todos/.active.d -type f -mtime +30 -delete`.

---

## The 10-step pipeline

For every gate: present, then PAUSE for explicit approval (`AskUserQuestion` or a
clear "approved?"). Set `awaiting` before pausing; clear it on approval and advance
`step`/`step_label`. Log the decision in `## Journal`.

**Step 1 — Capture.** User gives the task. Create the task file with frontmatter
(`step: 1`) and the task directory `todos/NNN-slug/`, write this session's focus
file. Read the project's rules file and record its check commands in `## Journal`.
Before anything else, read `depends_on` (ask the user if dependencies aren't
obvious), check each predecessor's state in the tracker; list any not-yet-merged in
`blocked_by`. If blocked, warn plainly and ask whether to proceed anyway (soft).
Then go to step 2.

**Step 2 — Reformulate.** Produce a **structured digest**:

- **Goal** — one sentence.
- **Context and constraints** — what exists, what must hold.
- **Done criteria** — what counts as finished.
- **Open questions** — unknowns to resolve in step 3.

Write it to `## Statement`. Gate: show it, `awaiting: statement approval`. On
approval → `step: 3`.

**Step 3 — Clarify → stories → spec page.**

- Ask clarifying questions in **batches of ≤4** (`AskUserQuestion`), repeating
  until residual uncertainty is low. Record answers in `## Journal`.
- Synthesize **user stories** (As a … / I want … / so that …) with acceptance
  criteria → `## User stories`. **Every acceptance criterion (including each done
  criterion) carries its own "how to check" line** — a user scenario in the form
  "do this — expect that", phrased as actions on the live product, not as code
  references. A criterion without such a line is not finished. Approval of the
  stories at this gate also approves running the derived checks throughout this
  task (no per-run question later); scenarios that write to a shared database
  still get a separate ask.
- If the task touches UI: build the realistic mockup with the **`ui-mockup`**
  skill → `NNN-mockup.html`; record the path in `page_mockup` and `## Mockups`. Without that skill installed, say so
  and either draw a static frame or skip the mockup with one declared sentence.
- **Live-UI reconciliation — the mockup does not reach the gate without it.** Ask
  the user once, with `AskUserQuestion`, where the running product is reachable;
  write the answer to `live_ui` and reuse it for the rest of the task, including
  step 8a. Then capture every surface the mockup draws from that address and
  reconcile the mockup against it. Record in `## Mockups` two lists:
  **"Differences"** — "in the product" / "in the mockup" / "fixed" — and
  **"Deliberately different"**, one line per deliberate departure, each shown to
  the user at the gate for confirmation. **These two lists are the only ones — do
  not add a third.** Every gap between the mockup and the live product belongs to
  one of them: a surface drawn simpler than the product, an element left out, the
  app frame drawn partially — all of it goes to "Deliberately different" and is
  shown at the gate, whatever its relation to the task. When the address does not answer, does
  not let you in, or lacks a surface you need: STOP and take it to the user — do
  not present a mockup that was never compared, and do not fall back to the
  component source alone.
- **Scenario premortem (before the gate).** The lens catalog is **project-level**:
  `<repo>/.agents/scenario-lenses.md` — a table of lenses, each with a "what to
  probe" column and a "grounding" section naming the real samples a reviewer needs.
  When the project has no such file, skip this sub-step with one declared sentence.
  Otherwise: gather the samples the catalog prescribes, put them in
  `todos/NNN-slug/` and link them from the task file; then spawn **one background
  agent per lens, all in a single message** — each agent reads only `## Statement`,
  `## User stories`, the mockup view and the samples, and returns candidate
  unwritten scenarios as "do this — expect that" lines tagged with its lens.
  Dedupe, then put **every** candidate to the user at the gate: accepted → an
  acceptance criterion with its "how to check" line; rejected → `## Out of scope`
  with the stated reason. No candidate is dropped silently.
- Build the **spec page** `NNN-spec.html` (see "Pages, the mockup and the feedback
  loop") with the interactive open-questions form and the mockup link → `page_spec`.
- Gate: serve the pages with the feedback helper, present them, and arm the waiter
  over `NNN-spec.answers.json,NNN-spec.notes.json,NNN-mockup.notes.json` before
  ending the turn (see "Pages, the mockup and the feedback loop"). Fold the batch it
  returns into `## Journal` / the next revision, and iterate until approved.
  `awaiting: spec approval`. On approval →
  create the tracker issue and card if the project uses one, stop the serving task,
  `step: 4`.

**Step 4 — Tech plan.**

- **Working branch — the first action of this step, before the plan file exists and
  before any review round.** Entry check: the working tree carries no other task's
  uncommitted work; when it does, finish that task's commit first. Then ask via
  `AskUserQuestion` where this task runs — first option "in the same folder",
  second "in a separate copy of the project", worded for a reader who has never
  seen the repo.
  - Same working copy → `git switch -c feat/NNN-slug`.
  - Separate working copy → `git worktree add .worktrees/NNN-slug -b feat/NNN-slug`,
    then link the task directory into it so both copies see one `todos/`
    (`ln -s <main-repo-root>/todos .worktrees/NNN-slug/todos`), then enter it.

  Write `branch: feat/NNN-slug` into the frontmatter and the chosen working copy
  into `## Journal`. Steps 4–9 run on this branch, plan review rounds included.

  Then bind this task's cross-agent review state to the branch, from inside the
  working copy the task runs in:

  ```
  bash "<skill-dir>/assets/codex-state-bind.sh" --task NNN-slug
  ```

  It carries the task's rounds and verdict over when the branch changes and moves
  another task's leftovers into `.codex-review/archive/`. Run it again whenever the
  task's branch changes — a rename, a move into a worktree — and at the start of
  step 7. Exit code 2 means two directories claim the task: keep one, remove
  `taskflow-task` from the rest, and re-run.
- **Reuse check, before the approach is written.** Establish whether a framework
  the project already depends on, or a mechanism already in the codebase, can carry
  the feature. Read the published docs and the installed version's own type
  declarations and changelog. Where reuse needs a version bump or a reasonable
  extension of an existing mechanism, put that option to the user via
  `AskUserQuestion` with its cost and follow their decision. A bespoke
  implementation enters the plan only with no reuse path, or on the user's
  instruction — record which, what was checked, and what it lacked.
- **Constraint check, before the approach is written.** Every statement the
  plan rests on of the form «the code does not do X / does not return X / does not
  support X» carries the `file:line` that creates the limit, what has to change to
  remove it, and the size of that change — the files touched, whether a data-schema
  change is involved, whether a public contract changes. Where removing the limit
  reaches past the place the task already changes, put the choice — extend the code
  or work around it — to the user via `AskUserQuestion` before it enters the plan,
  naming the measured cost of each side. A workaround (a marker inside text, a
  heuristic over content, a naming convention, a guess at a format) standing in for
  an explicit field, parameter or column enters the plan only on the user's
  decision, and leaves the plan the moment the direct path proves available — the
  two never stand side by side. Re-read the plan for such statements before the
  step-4 gate: each one carries its `file:line` and its cost, or it is removed.
- Write the technical solution and implementation plan into `## Solution and plan`
  (prose + `file:line` refs, no code blocks). It carries, in this order: the
  approach, what is taken ready-made, the file-level change table,
  `### Failure behaviour`, `### Stages and tasks`, risks, checks.
- **`### Failure behaviour` — the failure ledger, mandatory.** One entry per point
  where the feature meets a missing resource, a failed operation or absent data:
  what is unavailable, what happens then, what the user sees. The default entry is
  "the error goes up". Every entry that is not "the error goes up" — a substitute
  source or version, a partial result, a degraded mode, a swallowed error — goes to
  the user via `AskUserQuestion` before it is written here, and carries their
  decision in the line. Each surviving substitution names the field of the result
  that reports what was actually used. No such point in the task → write "none —
  every failure goes up". The step-4 gate does not close without this subsection.
- **`### Stages and tasks` — the staged work breakdown, mandatory.** Split the work
  into ordered stages, each ending in a working, verified piece. Per stage: a bold
  heading `**S1. <name>.**`, one sentence on what it lays down, a checkbox list
  `- [ ]` of its tasks, and a closing `Done when: …` line naming an observable
  result. Prose and references only, no code. The step-4 gate does not close
  without this subsection.
- **Build the reviewer plan file — `todos/NNN-slug/plan.md` — before the first
  review runs.** It is self-contained and it is the only artifact any reviewer
  receives. It carries, in this order: `## Goal` (one sentence), `## Constraints`
  (from `## Statement`), `## Acceptance criteria` (from `## User stories`, without
  the "how to check" lines), `## Solution and plan` (that section verbatim), and
  `## Already closed` (the review ledger, see below). Regenerate it from the task
  file before every review round. The task file stays the source; the plan file is
  a projection of it and nothing else is added to it by hand.
- **`### Closed findings` in `## Journal` — the review ledger.** One line per
  finding, in the order raised, self-contained enough that a reader who never saw
  the finding can check it:
  `round N · <who found it> · <title> · <scenario in one phrase> — fixed, see <plan section> | deferred to <where> | rejected: <reason>`.
  Write the line the moment the finding is closed, and close every finding a round
  raised — a finding with no line is an open finding. This ledger is the whole
  record of the review history: it is what `plan.md` carries into the next round as
  `## Already closed`, and what `NNN-plan.html` renders. Do not write a
  round-by-round narrative anywhere.
- Harden the plan with the **`grill-me`** skill when it is installed; revise the
  plan from the answers.
- Ask via `AskUserQuestion` whether to run the pre-mortem on this plan, naming what
  the change touches (data, DB schema, shared modules, external integrations,
  user-visible behaviour). On "yes", first confirm that `todos/NNN-slug/` exists and
  that `todos/NNN-slug/plan.md` holds the current plan — create the directory and
  regenerate the plan file when either is missing. Then invoke
  **`technical-premortem`** with the absolute path of `todos/NNN-slug/plan.md` as
  the plan — never the task file — plus the repo root and the decisions taken in
  the dialogue but absent from that file. Keep its report beside the plan file as
  `todos/NNN-slug/premortem-plan.md`; when it lands elsewhere, move it there and
  rewrite every reference. Fold the risks and the pre-flight checklist into
  `## Solution and plan`; carry the checklist into step 5 as entry conditions. A
  blocking risk without a mitigation holds the gate — revise the plan and re-run, or
  get the user's explicit decision to proceed. Record the verdict and the
  run-or-skip decision in `## Journal`.
- Cross-check the plan with a **cross-agent review skill** (plan phase) when one is
  installed, passing it `todos/NNN-slug/plan.md` and nothing else: the answers to
  the previous round are already in the file's `## Already closed`. With no such
  skill, say so in `## Journal` and rely on the pre-mortem and the panel.
  Non-blocking observations go into `### Stages and tasks` as tasks, into the checks
  section, or into a separate follow-up task.
- **Stopping rule for the plan phase.** Close it on either condition: a round
  returns no finding whose scenario normal operation reaches; or two consecutive
  rounds return only findings that need a sub-second window, a coincidence of
  independent failures, or inputs the running system cannot produce. On the second
  condition, move the remaining findings into the test plan as failing-first cases,
  ledger them as "deferred to the test plan", and say in `## Journal` which
  condition closed the phase. Hard cap 5 rounds; raising it takes the user's
  decision via `AskUserQuestion`, and on the cap put the open findings to the user —
  fold in / defer / drop — and record the decision.
- Build the **plan page** `NNN-plan.html` from the bundled template → `page_plan`.
  Optionally embed a `visual-explainer` diagram if one clarifies the approach.
- Gate: present the page (serve via the helper so the user can annotate it too) and
  arm the waiter over `NNN-plan.notes.json` before ending the turn; fold the batch
  it returns in.
  `awaiting: plan approval`. On approval → `step: 5`, move the board card to "in
  progress".

**Step 5 — Implement (TDD).** Entry check: `git rev-parse --abbrev-ref HEAD`
returns `feat/NNN-slug`, the branch step 4 created. On any other branch, stop and
close step 4's branch sub-step before writing code.

Walk `### Stages and tasks` in order, one stage at a time. Work in RED→GREEN: write
the failing test first, confirm it fails for the right reason, then the minimum code
to pass. Tick each `- [ ]` in the task file as its task lands; on a stage's
`Done when` line coming true, record the closed stage in `## Journal`. After each
batch of commits, add one line to `## Journal`: the date, the short hashes and what
they carry. A stage the work proves wrong is rewritten in the plan before it is
built, with the reason in `## Journal`. Follow the project's testing rules. Run the project's fast checks
(type-check plus the unit run scoped to the modules the stage touched) at each
stage; run the slower ones (lint, dependency and dead-code checks) once, after the
last stage closes, and only those whose triggers apply.

**Acceptance verification pass (entry condition for step 6).** Turn the "how to
check" scenarios from `## User stories` into e2e specs in the project's e2e
location, following its tagging rules. Automate every scenario the project's
browser driver can drive; a scenario it cannot drive goes to step 8a's manual list
with one declared sentence. Run the new specs green. In `## Journal` record the
mapping: criterion → spec (or → manual). Review gates open only after this pass is
green. `step: 6`.

**Minor fix — the definition steps 6, 7 and 9 use.** A fix is minor when both hold:
the finding that raised it carries minor / nice-to-have severity, and the change
alters no program behaviour — comments, documentation, naming, formatting,
dead-code removal. A fix that touches a condition, a branch, control flow, an API
shape, a runtime-relevant type, a dependency or a user-visible string is not minor.
When the classification is unclear, put that fix to the user via `AskUserQuestion` —
minor (close the phase) or behaviour-changing (another round); never open a round on
your own to settle the doubt.

**Step 6 — Review panel.** Run **`review-panel`** with no argument — that reviews
every uncommitted change in the tree, staged or not, which is the rule before a
commit. It triages the track subset with you, runs the read-only tracks in
parallel, verifies the criticals, writes the round file, and drives re-review
rounds until nothing must-fix or important survives. Keep the silent-failure track
in the subset whenever `### Failure behaviour` carries an entry other than "the
error goes up", or the diff adds a caught-and-continued error, a substitute value
or a default-on-failure. Critically assess findings — apply the real ones, reject
the rest with reasoning, and let the re-review round put your reasoning back to the
track that raised it (log the outcome). A finding about code this task did not
change goes to the tech-debt directory, not into the diff — see "Findings outside
this task" in Guardrails. After each round's fixes re-run the fast checks on the
final diff.

Without the panel skill installed, run the project's own review path instead —
its reviewer subagents or a manual pass over the diff against the acceptance
criteria — and say in `## Journal` which one ran.

When the repo enables the review barrier (see "The commit barrier"), the panel's
last step records its review credit; confirm that line appeared. A round whose
findings are **all minor** closes the panel: apply those fixes, open no further
round, and re-record the credit the fixes dropped:

```
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/precommit-gate-util.py" mark --repo <repo-root> \
  --gates <ids> --scope worktree --note "minor-only fixes after round N"
```

Ledger the applied findings in `### Closed findings` as usual. `step: 7` when clean.

**Step 7 — Cross-agent code review.** Entry: re-run
`bash "<skill-dir>/assets/codex-state-bind.sh" --task NNN-slug` so the code phase
reads the plan phase's rounds. Invoke the cross-agent review skill (code
phase) against the diff when one is installed. Address findings — a finding about
code this task did not change goes to the tech-debt directory under the same rule
as step 6; continue only after a formal **APPROVED**. Then record the credit for
the cross-agent gate:

```
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/precommit-gate-util.py" mark --repo <repo-root> \
  --gates <id> --note "cross-agent review APPROVED"
```

**Minor fixes made after APPROVED keep that approval** — no new cross-agent round,
and no panel round either; re-record the credit for the files they touched. A
behaviour-changing fix goes back for a new **APPROVED**. With no cross-agent
reviewer installed, say so in `## Journal` and go on.

`step: 8`, move the board card to "in review".

**Step 8 — live scenario pass + e2e.**

**8a — Live scenario pass (mandatory for tasks with a UI or conversational
surface; skip with one declared sentence otherwise).** Rebuild the dev environment
from the working tree, then drive the live product at the address the task recorded
in `live_ui` (confirm with the user when the working tree is served somewhere
else):

1. **Every scenario of `NNN-mockup.html` against the live UI.** Record the
   verdict as a three-column table in `## Journal`: "matches / differs / not done".
   Every "not done" row goes to the user for a decision (fix now / follow-up task /
   accept).
2. **Adversarial cases**, each on the live environment: two instances of the new
   interaction at once; page reload in **each** intermediate state of the new
   surface; the decline/cancel path; the slowest realistic backend. When the
   project has `.agents/scenario-lenses.md`, walk its probes for the lenses whose
   surfaces this task touches.
3. Where the feature displays raw external text (database output, logs), feed it
   text containing markup control characters (`#`, `*`, `|`, `<tag>`) and check the
   rendering.

Gate: present the verdict table via `AskUserQuestion`; proceed only on the user's
decision for every gap found.

**8b — e2e re-run + extras.** Re-run the acceptance specs (from step 5) whose
surface the review fixes touched — all of them when in doubt — and make them green;
the stories-gate approval covers these runs. Then decide whether the review rounds
or step 8a exposed an invariant the acceptance specs do not cover; propose any such
**additional** spec via `AskUserQuestion` with a concrete path, the project's tag
for it, and the invariant it asserts; implement only on approval, then run it green.
`step: 9`.

**Step 9 — Commit + PR.** taskflow is self-contained here — do not route the commit
through another shipping command.

1. Stage **per file** (`git add <path>`; never `-A`, `.` or `-u`). If unrelated
   files appear, ask the user what to do with them.
2. Re-run the deterministic checks whose inputs changed since step 6.
3. When the repo enables the barrier, steps 6 and 7 already recorded the credit it
   checks, and that credit is per file, so staging keeps it. Confirm with
   `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/precommit-gate-util.py" status --repo <repo-root>`.
   A file that lost its credit after a behaviour-changing fix goes back through
   steps 6 and 7 and is re-marked. A file whose only change since its review is
   minor is re-marked with a note naming that change, without a new round. Never
   opt out to get past the barrier.
4. Commit per file with a conventional-commit message, in English.
5. Run the pre-push check — the tests this branch affects, not the whole suite.
   Fix failures and re-commit before pushing.
6. Open the PR with the **`create-pr`** skill when it is installed, otherwise
   `gh pr create`. Record `pr` in frontmatter.
7. Watch the CI run to its verdict (`gh pr checks --watch`). Fix a red check on the
   branch and push again. Record in `## Journal` the verdict, and any check that was
   re-run rather than fixed together with what it failed on.

`step: 10`.

**Step 10 — Summary page, then archiving.** Entry condition: the CI run of step 9
is green. Build the **summary page** → `page_summary`, then **open it in the user's
browser** (`xdg-open` on Linux, `open` on macOS, `wslview` under WSL). Set
`status: done`, move the board card to "done", and log the close in `## Journal`.

Then set `awaiting: archiving` and ask via `AskUserQuestion`, in plain words,
whether to move this task's artifacts out of the active list. On yes:
`mv todos/NNN-slug.md todos/archived/` and `mv todos/NNN-slug/ todos/archived/`.
The HTML pages stay in `todos/pages/`. Record the answer in `## Journal` before the
move.

Finally clear `awaiting:` and delete this session's focus file.

---

## Dependencies between tasks

`depends_on` lists task ids that must be **merged** before this one starts. At step
1 (and on resume) compute `blocked_by` by checking each predecessor's PR or issue.
If non-empty: state it plainly, and ask whether to proceed anyway — soft, never a
hard stop. Keep `blocked_by` current so the hook surfaces the blocked marker. The
cross-task picture comes from scanning all `todos/*.md` frontmatter
(`/taskflow status`); no separate board file.

---

## Issue tracker lifecycle

Only when the project uses one, and only with the user's answer from step 1.
Create the card **early** (step 3, on spec approval) and move it as work progresses.
With GitHub:

- **Create issue:** `gh issue create --title "<title>" --body "<short summary + link
  to the spec page>"`. Store `issue` + `issue_url`. Put `depends_on` as a
  "Blocked by #N" line in the body — a link only, GitHub has no native blocking
  dependency.
- **Add to a board:** `gh project item-add <number> --owner <owner> --url <issue-url>`.
  Ask for the board number and owner once, store them in `## Journal`.
- **Move across columns:** discover the Status field and its option ids once with
  `gh project field-list <number> --owner <owner>`, then `gh project item-edit`.
  Steps 4–5 → an "in progress" column; steps 8–9 → "in review"; step 10 → "done".
  Match the nearest existing option name.
- **Link PR:** at step 9, reference the issue in the PR body (`Closes #N`).

If the tracker call fails, do not stall the task — log it and continue; the local
frontmatter remains the source of truth.

---

## Pages, the mockup and the feedback loop

Pages live in `todos/pages/` and share two files copied verbatim from
`<skill-dir>/assets/pages/`: **`taskflow.css`** (the blueprint look — dark default
plus a light theme via CSS variables) and **`taskflow.js`** (theme toggle, `tfSave`,
toast, and the shared annotation engine `tfAnnotate` with its `tfAnnotateDoc` /
`tfAnnotateMockup` wrappers — the floating notes panel is injected by these, not
hand-written per page). **Before writing any page, ensure both exist in
`todos/pages/`.** The bundled `example-*.html` set is the reference — model new
pages on it, keeping the shared chrome: a header with id / title / step / status
plus dependency chips, a three-tab nav with a theme toggle, and a footer. Each page
is a thin file: a `<link>` to the two shared files, a tiny no-flash theme-init
script, and its content.

**Three doc pages**, each recorded in its `page_*` key:

- **`NNN-spec.html` (step 3)** — goal, context and constraints, user stories with
  acceptance criteria, out of scope, dependencies, a link card to the mockup, and an
  **interactive open-questions form** (per question: agree / change, plus a
  free-text answer; "save" → `NNN-spec.answers.json`).
- **`NNN-plan.html` (step 4)** — technical approach (prose plus a boxes-and-arrows
  flow), file-level change table, the **stages block** mirroring `### Stages and
  tasks`, the failing-first test plan, and risks. When the pre-mortem ran, its risks
  and the pre-flight checklist go in the risks block. Review results take exactly
  two forms on this page: a verdict strip — one chip per reviewer with its verdict
  and finding count — and the ledger, rendered as the `### Closed findings` lines
  verbatim, each linking to the report it came from. Retelling what a reviewer
  found, or how the plan looked before a round, does not go on the page.
- **`NNN-summary.html` (step 10)** — done-vs-spec per story, changed files,
  RED→GREEN tests, review outcomes, e2e, deviations, PR/commit/issue links,
  follow-ups. Uses the green "done" chrome (`<body class="done">`).

Both doc pages carry the shared **notes panel** (wired by a one-line
`tfAnnotateDoc({task, kind, file})` call): the user turns on the mode, **selects any
text**, a numbered badge is pinned right after the fragment and the fragment is
tinted (CSS Custom Highlight API — no DOM rewrite), and a side field opens for the
comment. Saving writes `NNN-spec.notes.json` / `NNN-plan.notes.json` — each note
carries its quoted fragment and nearest section label. This is separate from the
spec's open-questions form; both can be used.

**The mockup is its own realistic page, not embedded in the spec.** For a UI task
at step 3 it is ONE file, **`NNN-mockup.html`**, built with the **`ui-mockup`**
skill and recorded in `page_mockup`; the spec page links to it (opens in a new
window). Model on `example-mockup.html`.

1. The window is split: the **review column** on the left (scenario list, step
   number and step buttons, reset / back / step / play, the per-step caption, the
   "under the hood" note, the theme toggle, the notes block) and the **mockup**
   filling the rest. The mockup area holds product UI and nothing else: the feature
   surface **inside the product's own frame** — left menu with its real items in
   their real order, top bar, project switcher, avatar — drawn from the live
   capture. The crossmark at the top of the column folds it into a rail, so the
   screen can be seen alone.
2. The notes block is wired by one call after `<script src="taskflow.js">`:
   `tfAnnotateMockup({ task, kind, file, frame: null, stage: 'mkStage', mount:
   'mkNotes' })`. It mounts into the column's `#mkNotes` slot: normal mode =
   interact with the mockup, notes mode = the element under the cursor is outlined
   and named and a click pins a numbered note to it, saving writes
   `NNN-mockup.notes.json`. **A note carries the element as well as the point**: its
   label lands in `quote` and a path to find it again in `el.path`, next to the
   `xPct`/`yPct` the user clicked. A click on empty space still makes a plain
   coordinate note. On the next visit an element-bound pin moves to wherever its
   element now is, and a note whose element is gone says so and keeps its place. The
   outlined unit is the nearest thing a person reads as one control (menu item,
   button, table cell) — mark a region `data-mk-el="Name"` to name it yourself and
   make it a target on its own. **Pins are scoped to the screen they were placed
   on** — the block listens for the page's `mk:scenario` events, so a pin only shows
   while its screen is displayed. `taskflow.css` is NOT linked from this page: its
   generic selectors would overwrite the mockup's own; the column and the notes
   block carry their styles inside the file.

**Feedback loop — how the user's answers and notes reach you.** A page opened as a
plain `file://` cannot write to disk, so to COLLECT feedback run the helper as two
background tasks — one serving, one waiting:

- Serve, on this task's own port — `8800 + NNN % 100`, so two tasks running side by
  side never reach for the same one:
  `python3 <skill-dir>/assets/feedback-server.py --root todos/pages --port <port>`.
  It serves the folder and turns each page's save POST into a JSON file written
  **next to the pages**.
- Check that saving works before the user is sent to the page — a server already on
  that port answers GET and drops every POST:

  ```
  curl -sS -X POST http://127.0.0.1:<port>/save -H 'Content-Type: application/json' \
    -d '{"file":"__probe__.json","data":{"probe":true}}'
  rm todos/pages/__probe__.json
  ```

  Continue on `{"ok": true, ...}`. On anything else, and on exit code 4 from the
  helper (the port is taken), stop: find the holder with `ss -ltnp | grep :<port>`,
  then stop it or start the helper on a free port and reopen the page there.
- Open the page through it: `xdg-open http://127.0.0.1:<port>/NNN-spec.html` (`open`
  on macOS, `wslview` under WSL).
- Wait, naming every file the pages you just presented can write:
  `python3 <skill-dir>/assets/feedback-server.py --root todos/pages --wait
  NNN-spec.answers.json,NNN-spec.notes.json,NNN-mockup.notes.json`. Then set
  `awaiting`, tell the user what is open, and END THE TURN. The waiter exits on the
  user's save and the harness wakes you with the batch on its stdout:
  `{"saved": [{"file": "…", "data": {…}}, …]}`.
- Read the batch, fold it into the task file, and STOP the serving task. Another
  round on the same page: start a new waiter over the same names.
- Exit code 2 means `--timeout` expired with nothing saved, 3 that a saved file is
  not readable JSON, 4 that the port is taken. Report each to the user as what it
  is; none of them is "no feedback".
- The helper copies the version it replaces into `todos/pages/.history/` and answers
  409 to a save that empties a file holding feedback until the page asks the user and
  resends. Try the saving machinery itself — a page's save button, the panel's
  restore, a probe — only on a copy in the scratchpad directory with its own file
  name, never on a file the user has written into.
- Plain `file://` (no helper) still works: the pages fall back to **downloading**
  the JSON — then read it from the downloads folder, and no waiter fires.

View-only pages (plan / summary) need no helper — just open the file. Record each
page's path in the matching `page_*` frontmatter key.

---

## The commit barrier

The plugin ships a review barrier that blocks `git commit` until every staged
non-trivial file carries review credit from steps 6 and 7. **It stays dormant until
the repo opts in** with `<repo>/.claude/hooks/precommit-gate.json`, which lists the
gate ids the project requires and the paths it treats as trivial. Run
`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/precommit-gate-util.py" --help` for the config
shape and the subcommands (`mark`, `optout`, `status`, `triage`).

Credit is content-addressed per file: a review marks the content hash of each file
it covered, so staging those same files keeps the credit, and editing a file after
its review drops it. Steps 6, 7 and 9 above are what record and check it. Never call
`optout` to get past the barrier on your own — that is the user's decision, with a
stated reason.

Already running the same barrier from your own settings? Do not register it twice —
keep one copy, or every commit asks twice.

---

## Skill and agent cheat-sheet

- `ui-mockup` — realistic, app-themed clickable mockup → `NNN-mockup.html`, one
  file carrying the review column and the mockup. It captures the running product
  at `live_ui` and reconciles the mockup against it.
- `grill-me` — adversarial questioning to harden the plan.
- `technical-premortem` — risk pre-mortem of the plan (step 4, on the user's yes).
  Fed `todos/NNN-slug/plan.md`, never the task file. Report →
  `todos/NNN-slug/premortem-plan.md`.
- `review-panel` — the parallel review panel (step 6). Read-only tracks,
  critical-only verify, round file, re-review rounds. Do not invoke its underlying
  reviewer agents directly — the panel owns them.
- a cross-agent review skill (plan phase at step 4, code phase at step 7) — for
  example `codex-review` from <https://github.com/artwist-polyakov/polyakov-claude-skills>. Optional:
  when it is not installed, say so and go on.
- `create-pr` — open the pull request (step 9).
- `visual-explainer` — OPTIONAL: a richer diagram to embed in the plan page.
- `<skill-dir>/assets/codex-state-bind.sh` — binds this task's cross-agent review
  state to the branch it runs on; `--help` for the details.
- `<skill-dir>/assets/feedback-server.py` — localhost helper that serves the pages
  and saves their answers and notes JSON next to them; `--wait <names>` blocks until
  one of those files is saved, prints the batch and exits. `--help` carries the
  options and exit codes.

Before writing code that uses a library or API surface, fetch its current docs
rather than working from memory.

---

## Guardrails

- One task in this session's focus; other sessions hold their own. Name only the
  focused task unless the user asks for the list (`/taskflow status`).
- Before taking task NNN into focus, check `todos/.active.d/*` for another session
  already holding it; when one does, say so and confirm before taking it.
- One task at a time writes code in one working copy: steps 5–9 require the tree
  free of other tasks' uncommitted work, or a separate working copy.
- Never advance a gate without explicit user approval. Set `awaiting` before every
  pause.
- Keep frontmatter and the session focus file accurate at all times — the hook
  trusts them.
- Minor fixes (see the definition above) earn no new panel round and no new
  cross-agent round — apply them, re-record the credit, go on.
- **Findings outside this task's changes.** A finding whose defect this task's diff
  did not introduce earns no fix here, whatever raised it. Fix one in this task only
  when the current change cannot merge without it, and say in `## Journal` what it
  blocks. File every critical and important one as a tech-debt note under
  `todos/techdebt/NNN-kebab-slug.md`, in the shape the project's existing notes use:
  a title naming the defect, the date, the severity, `path:line` anchors, then what
  was found, why it is debt, what it costs, and the proposed fix. Ledger it as
  "deferred to techdebt/NNN-…". A minor one gets a ledger line and no file.
- Run the project's scoped checks locally and leave the full suite to CI, unless the
  project says otherwise.
- Reuse the listed skills; do not reimplement review, mockup or PR logic.
- A reviewer of the plan gets `todos/NNN-slug/plan.md` and nothing else — not the
  task file, not an HTML page, not a hand-written round summary. HTML pages are for
  the user to read and annotate; no agent is ever fed one.
- **Every bug found by manual testing after the review gates, or reported after
  shipping, is mapped to a lens in the project's `.agents/scenario-lenses.md` as
  part of its fix** — add the case to an existing lens's probe column, or add a new
  lens row (create the file from the bug when the project has none). A fix without
  this mapping is not finished.
- Pages need `taskflow.css` and `taskflow.js` alongside them in `todos/pages/` —
  copy them from `<skill-dir>/assets/pages/` before writing the first page of a task.
- **Stop the serving feedback helper once feedback is collected** — by its
  background-task handle or `kill <pid>`, **not** by a pattern kill on the script
  name: that pattern also matches the shell command running it and kills your own
  command. Free the port before restarting. The `--wait` task ends on its own; stop
  it the same way when the user abandons the review.
- **Softening a failure is the user's decision, not yours.** Substituting another
  source or version, returning a partial result, dropping into a degraded mode,
  swallowing an error — ask before it enters the plan at step 4 or the code at step
  5, record the answer in `### Failure behaviour` and in `## Journal`, and make the
  result name what was actually used.
- `git add` per file only. Commit messages in English, following the project's
  convention.
- If a delegated skill, agent or CLI call fails, log it and ask the user — do not
  silently retry or fabricate a result.
