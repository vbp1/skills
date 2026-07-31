---
name: phased-task-delivery
description: "Structured plan-first execution for complex engineering tasks with explicit phases, document-backed plans, checklists, subagent implementation, iterative review gates, per-phase commits, and final full-suite validation. Use when a user wants work handled end-to-end through a repeatable workflow rather than ad hoc edits: porting features, large refactors, staged migrations, risky infrastructure changes, greenfield builds, or net-new feature development in an existing or new project."
---

# Phased Task Delivery

## Overview

Use this skill to run a complex task through the same delivery loop that proved effective in the CSN port session: investigate, write planning artifacts, pressure-test the plan, implement in phases, run review gates after each phase, commit intentionally, and finish with a broad test gate.

This workflow supports three modes:

- `Port / migration`
  There is an existing source implementation or behavior to preserve while integrating into a target codebase.
- `Net-new feature in an existing project`
  The behavior is new, but it must fit an existing architecture, lifecycle, and test matrix.
- `Greenfield build`
  The project or subsystem is created from scratch, so the plan must define structure, acceptance criteria, and validation strategy before implementation.

Keep the skill body procedural. Load the reference files only when needed:

- Read [references/workflow.md](references/workflow.md) for the normalized workflow and gate order.
- Read [references/session-user-message-chain.md](references/session-user-message-chain.md) if you need the original user-driven chain that this skill was derived from.
- Use the prompt templates in [references/workflow.md](references/workflow.md#recommended-subagent-prompts) when launching subagents for plan review, implementation, and phase review.
- Use the operational guidance in [references/workflow.md](references/workflow.md#operational-additions) for Claude review orchestration, environment recovery, validation layering, subagent cleanup, and repository closeout.

## Runbook

1. Reconstruct the task and the repos.
   Identify the delivery mode, current branch state, expected deliverable, and whether the user wants plan-first execution.
   - In `port / migration`, identify source-of-truth repo or implementation and target integration repo.
   - In `net-new feature`, identify the host project and the subsystem boundaries the feature must fit into.
   - In `greenfield`, identify whether there is an empty repo, scaffold, or only a desired architecture and acceptance target.

2. Create planning artifacts before implementation.
   Put reusable artifacts under `.agents/` in the working repo unless the user explicitly wants another location. For multi-phase work, create at least:
   - a high-level plan
   - a stage-specific plan for the active stage
   - a checklist with progress fields

3. Run a Socratic plan review loop before code.
   Start with a restricted subagent that sees only the planning document, cannot browse the internet, and cannot read code unless the user later expands scope. Have it ask questions, answer them yourself from available context, update the plan, and repeat until there are no critical objections.

4. Run a code-aware plan review.
   After the document-only loop, run a fresh review pass that can inspect the relevant codebase.
   - In `port / migration`, make both source and target repos explicit.
   - In `net-new feature`, review against the existing host project.
   - In `greenfield`, review against the intended repo layout, scaffold, or architecture documents if the codebase is still minimal.
   If path clarity matters, create a symlink alias to make prompts unambiguous.

5. Use external review gates carefully.
   If Claude review is part of the workflow and the `claude-review` skill is available, use it after the local review pass. Do not poll the review process while its state command reports `IN_PROGRESS`.

6. Implement in phases on one branch.
   For execution, use one branch for the whole effort and one commit per phase. For each phase:
   - assign implementation to a worker subagent with explicit ownership
   - review the result with a separate subagent
   - run the external review gate if required
   - fix findings
   - run the phase test gate
   - commit only after reviews pass
   - update the checklist immediately after the commit

7. Treat infrastructure failures separately from code failures.
   If a test fails because the tree is misconfigured, version-mismatched, or otherwise broken outside the patch, fix the environment first, rerun the failing tests, then continue the phase gate.

8. Keep agent hygiene.
   Close stale or unnecessary subagents when they are no longer useful, especially after phase completion or when the user calls out stale UI state.

9. Finish with the broadest meaningful test gate.
   Run the full suite the user expects at the end, not just the targeted per-phase tests. If the project has TAP or similar integration suites, ensure the relevant ones are covered and say explicitly what was and was not run.

10. Confirm repository state before closing.
    Report whether code changes are committed, call out any remaining untracked review artifacts, and avoid claiming the tree is fully clean if review directories still exist.

## Default Decisions

- Default to a plan-first workflow for large or risky tasks.
- Default planning artifacts to `.agents/`.
- Default implementation to one branch for the whole effort and one commit per phase.
- Default review order to: worker output review -> external review -> commit.
- Default final gate to the broadest practical test suite.
- Default the plan to state explicitly which mode is active: `port / migration`, `net-new feature`, or `greenfield`.

## Guardrails

- Do not skip the plan review loop on complex work just because implementation looks straightforward.
- Do not commit a phase before its tests and reviews pass.
- Do not claim a suite was run if only targeted subsets were run.
- Do not leave checklist state behind the actual code state.
- Do not keep polling or reopening external review state when the review system explicitly says it is still in progress.

## Output Expectations

- Keep user-facing progress updates short and factual.
- In final summaries, group by outcome and gates rather than by every file touched.
- When you derive this workflow for another task, explain any deviations from the default sequence.
