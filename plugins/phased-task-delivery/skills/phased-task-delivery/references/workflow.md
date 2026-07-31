# Phased Task Delivery Workflow

## Purpose

This reference normalizes the workflow extracted from the April 20, 2026 CSN port session into a reusable execution pattern for other tasks, including ports, net-new features, and greenfield builds.

## Delivery Modes

Choose the mode first and make it explicit in the plan.

### 1. Port / Migration

Use when there is an existing implementation, behavior, or source repo that must be reproduced or adapted in another codebase.

- Main planning focus:
  - source-of-truth hierarchy
  - compatibility boundaries
  - delta between source and target
  - staged risk reduction

### 2. Net-New Feature in an Existing Project

Use when the functionality is new but must fit an existing codebase.

- Main planning focus:
  - integration points
  - lifecycle hooks
  - data flow and invariants
  - test coverage for the touched subsystem

### 3. Greenfield Build

Use when the project or subsystem is created from scratch.

- Main planning focus:
  - architecture and module boundaries
  - acceptance criteria
  - scaffolding and repo layout
  - initial validation and bootstrap strategy

## Workflow

1. Investigate the problem and establish feasibility.
   Start with enough analysis to understand whether the task is tractable, which delivery mode applies, and what the likely implementation shape is.
   - In `port / migration`, map source and target repos.
   - In `net-new feature`, map the host project and target subsystem.
   - In `greenfield`, map the desired architecture, scaffold, repo, or bootstrap target.

2. Convert the work into explicit planning artifacts.
   Write the high-level plan, then stage-specific plans, then a checklist with task-level and milestone-level progress fields. Keep these under `.agents/` unless the user wants a different location.

3. Pressure-test the plan without code access.
   Use a subagent in a constrained mode:
   - give it only the plan document
   - forbid code reading
   - forbid internet access
   - ask for Socratic questions and critical objections
   Answer the questions yourself, update the plan, and repeat until the subagent has no critical objections.

4. Pressure-test the plan with code access.
   Run a fresh plan review against the relevant codebase.
   - In `port / migration`, make source and target mapping explicit in the prompt.
   - In `net-new feature`, review against the host codebase and real integration points.
   - In `greenfield`, review against the current scaffold, bootstrap code, or intended module layout.
   If path clarity matters, add a local symlink alias.

5. Run external review when part of the contract.
   If Claude review is requested, route the plan or the patch through the existing Claude review workflow. Respect its state machine:
   - initialize review
   - do not poll verdict while the state command reports `IN_PROGRESS`
   - act only on terminal review states

6. Create one implementation branch.
   Put all phases on a single branch. Use one commit per phase so the history aligns with the stage checklist and the review cadence.

7. Execute each phase with the same gate order.
   For each phase:
   - create or reuse a worker subagent for implementation
   - scope the worker to the phase responsibilities
   - review the result with a separate subagent
   - send the patch to external review if required
   - address findings
   - run the phase test gate
   - commit the phase
   - mark the checklist items done

8. Separate infrastructure breakage from patch regressions.
   If tests fail because the tree is misconfigured, stale, or version-mismatched, fix the environment and rerun. Do not record the phase as blocked by code until the infrastructure issue is cleared.

9. Keep subagent inventory under control.
   Close stale, dead, or no-longer-needed subagents. If UI state and API state disagree, trust the actual API status and tell the user exactly what remains.

10. Finish with the broadest validation gate.
    Run the full suite the user expects near the end. In systems like PostgreSQL, this includes `make check-world` and the relevant TAP families, not only targeted regress or isolation tests.

11. Report repository state precisely.
    Confirm:
    - current branch
    - latest commit(s)
    - whether code changes are committed
    - whether review artifacts remain untracked

## Invariants

- Planning comes before implementation.
- Critical plan objections are burned down before code.
- Each implementation phase has its own review and test gate.
- Commits happen only after passing the agreed gates.
- Checklist state is part of the deliverable, not an optional afterthought.
- Final reporting distinguishes committed code from untracked review artifacts.

## Operational Additions

### 1. Claude Review Integration

Use Claude review as an explicit gate after local review, not as a replacement for it.

- Default order:
  - local subagent review
  - `claude-review`
  - fix findings
  - rerun review if needed
  - commit
- Respect the external review state machine.
- Do not poll or re-check the process while `claude-state.sh get verdict` returns `IN_PROGRESS`.
- Only act on terminal outcomes such as approval or actionable findings.
- In summaries, report local review status and Claude review status separately.

### 2. Environment Recovery Protocol

If a gate fails because the environment is inconsistent, repair the environment before blaming the patch.

- Typical signals:
  - stale generated artifacts
  - mismatched build or install state
  - broken temp-install state
  - version skew between generated files and binaries
- Default recovery order:
  - determine whether the failure is outside the patch scope
  - clean the tree as needed
  - rerun configure if configuration state is stale
  - rebuild the relevant artifacts
  - rerun the failing gate
- Do not treat the phase as code-regressed until the environment is consistent again.
- In final reporting, call out infrastructure-only failures and the recovery steps that cleared them.

### 3. Validation Tiers

Treat validation as layered.

- Phase-local validation:
  - compile checks
  - focused tests for the touched subsystem
  - formatting or diff sanity checks
- Targeted subsystem validation:
  - the tests most likely to catch regressions introduced by the phase
  - rerun after review-driven fixes
- Final broad gate:
  - the broadest practical suite the user expects
  - TAP or integration-style suites when the project has them
- In reports, separate clearly:
  - what ran during the phase
  - what ran only at the end
  - what was intentionally not run

### 4. Subagent Hygiene

Treat subagent cleanup as part of the workflow.

- Close completed worker and reviewer agents once their output is integrated.
- Close stale or dead agents when the user points out lingering UI entries.
- If UI state and API state disagree, trust the actual API result and say so explicitly.
- Do not accumulate long-lived unused agents across phases.
- Before starting a new phase, check whether old worker or reviewer sessions should be closed first.

### 5. Repository State Closeout

Before declaring the work done, verify repository state precisely.

- Check:
  - current branch
  - latest relevant commits
  - `git status`
  - whether untracked review artifacts such as `.claude-review/` remain
  - whether runtime artifacts such as `.codex` remain
- Report code state separately from review-artifact state.
- Do not say "everything is committed" if only code is committed while review directories remain untracked.
- If the tree is not fully clean, say exactly what remains and whether it should be kept or removed.

## Recommended Subagent Prompts

### 1. Socratic Plan Reviewer

Use when the plan should be challenged before code access is allowed.

```text
Review the attached plan document only. Do not read code, do not browse the internet, and do not make assumptions from outside the document. Your job is to act as a Socratic reviewer: identify missing invariants, unsupported assumptions, ambiguous sequencing, missing test gates, missing acceptance criteria, and hidden blockers. Ask concrete questions and call out critical issues first. Stop once you have no critical objections left.
```

### 2. Code-Aware Plan Reviewer

Use after the document-only loop, when the relevant codebase may now be inspected.

```text
Review the plan against the current target codebase. The source implementation lives in <source-repo-or-main-repo>. The target integration repo is <target-repo>. Check whether the plan matches the actual code layout, extension points, lifecycle hooks, tests, and likely blockers. Focus on concrete mismatches between the plan and the codebase, not stylistic suggestions. Report critical and high-severity findings first.
```

Adapt the opening to the active mode:

- Port / migration:
  `Review the plan against the current target codebase. The source implementation lives in <source-repo-or-main-repo>. The target integration repo is <target-repo>.`
- Net-new feature:
  `Review the plan against the current host codebase in <target-repo>. Check whether the feature plan matches the real module layout, extension points, lifecycle hooks, tests, and likely blockers.`
- Greenfield:
  `Review the plan against the current scaffold, bootstrap code, or intended repo layout in <target-repo>. Check whether the proposed architecture, module boundaries, bootstrap sequence, and validation strategy are coherent and implementable.`

### 3. Phase Worker

Use for implementation of one bounded phase on the shared branch.

```text
Implement Phase <phase-id> of the plan in <target-repo>. You are not alone in the codebase. Do not revert unrelated changes, and adjust to existing work if the tree has moved. Your ownership is limited to: <files-or-subsystems>. Keep changes scoped to this phase. Run the phase-local validation you need, and report exactly which files you changed, which tests you ran, and any residual risks or blockers. Do not commit.
```

For greenfield work, add:

```text
If the project is still mostly empty, treat repo layout, scaffolding, bootstrap wiring, and initial validation setup as part of the phase scope, but keep the changes limited to the agreed phase boundaries.
```

### 4. Phase Reviewer

Use after a worker finishes a phase but before the external review gate or commit.

```text
Review the Phase <phase-id> implementation diff against the phase plan and current codebase. Focus on correctness, regressions, missing tests, broken invariants, and mismatches with the stated phase scope. Findings come first, ordered by severity. Ignore style unless it hides a bug. If there are no findings, say that explicitly and mention any remaining test gaps or assumptions.
```

For greenfield work, interpret "regressions" as:

- architecture mismatches against the agreed plan
- missing bootstrap or validation wiring
- acceptance criteria that are still uncovered

### 5. Final Gate Reviewer

Use before the final broad test gate or before declaring the whole effort done.

```text
Review the completed staged implementation as a final gate. Check whether every planned phase appears to be implemented, whether checklist state matches the code state, whether obvious coverage gaps remain, and whether the proposed final test matrix is sufficient for the touched subsystems. Call out blockers first, then medium-risk gaps, then any final questions.
```

## Good Fit

Use this workflow for:
- staged ports
- net-new features in existing systems
- greenfield subsystem or project builds
- risky refactors
- architecture migrations
- invasive core patches
- any task where the user wants visible planning, gate-based progress, and reproducible review steps

## Poor Fit

Do not use the full workflow for:
- tiny one-file fixes
- purely informational questions
- tasks where the user explicitly wants speed over structure
- work that does not justify plan docs and phase gates
