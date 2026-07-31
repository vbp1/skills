---
name: claude-review
description: |
  Cross-agent review workflow where Codex implements and Claude Code reviews.
  Use when the user asks for Claude review of Codex work, says "claude review",
  "ревью через claude", "пусть claude отревьювит", or wants a mirrored
  codex-review workflow for Codex.
metadata:
  short-description: Claude reviews Codex work
---

# Claude Review Workflow

Cross-agent review: Codex implements, Claude Code reviews. Claude runs in the same repository and can inspect the codebase independently.

## Script Location

Scripts live in `scripts/` next to this `SKILL.md`. Resolve the absolute paths from the file you just read:

- Main script: replace `SKILL.md` with `scripts/claude-review.sh`
- State helper: replace `SKILL.md` with `scripts/claude-state.sh`

Use those absolute paths when running commands.

## Runtime Requirements

`claude-review.sh` must run in an environment that has real network access to the Claude API. Do not run `init`, `plan`, `code`, or `reset --full` inside a network-restricted sandbox.

Operational rules:

- Run `claude-review.sh` outside sandbox, with network access available.
- If a previous sandboxed `init` or review attempt got stuck, run `bash scripts/claude-state.sh reset --full` outside sandbox before retrying.
- Do not interrupt `init` or `code review` mid-flight unless you are intentionally aborting the review.
- Do not start a second `init`, `plan`, or `code` while the first one is still active.

Typical sandbox failure signature:

- `ip route` in the sandbox fails with `Operation not permitted`
- preflight fails immediately with a message about missing network access to the Claude API
- or, on older runs, `claude-init.log` shows repeated `api retry ... error=unknown`
- `state.json` stays in `phase: initializing`
- `verdict.txt` never appears
- `get verdict` ends in `ERROR`

Treat that as an infrastructure failure caused by missing network access, not as a review-content failure. Reset outside sandbox and rerun outside sandbox.

## Project Setup

State is stored in `.claude-review/` at the main repository root. If the project is not configured yet, ask the user before changing project ignore files. Recommended ignore entry:

```gitignore
.claude-review/
```

## Workflow

Default path for new work when a real implementation plan exists:

```text
init -> plan review -> implementation -> code review
```

Allowed shortcut when plan review was skipped, no useful plan exists, or code already exists:

```text
init -> code review
```

Use the shortcut when you are reviewing already-written code, when the work did not have a separate plan artifact, or when the plan was not reviewed before implementation. Do not invent a synthetic "approved plan" after the fact.

### 1. Initialize A Claude Review Session

Create a Claude session with the task description and a stable work-phase identifier. Use the same `phase_key` for every review step in the same work phase, and start a new `init` when you move to a different work phase in the same branch.

```bash
bash scripts/claude-review.sh init --phase-key 02-01 "Implement JWT authentication for API"
```

Recommended `phase_key` source:

- Use the stable phase/task id from your workflow system, roadmap, or plan, for example `02-01`.
- Do not derive it from free-form task description text.

The session can also be set manually in `.claude-review/config.env`:

```bash
CLAUDE_SESSION_ID=00000000-0000-0000-0000-000000000000
```

If there is no active session and review returns `NO_SESSION`, ask the user whether to create one with `init` or reuse an existing Claude session id.

### 2. Plan Review

Plan review is recommended for normal forward workflow before implementation when a plan exists. It is optional when the code is already written, when the work was intentionally exploratory, or when there is no meaningful pre-implementation plan. In those cases, skip this step and go directly from `init` to `code review`.

Write the plan to a file, then submit the file path. Do not pass large plan text directly on the command line.

```bash
bash scripts/claude-review.sh plan --phase-key 02-01 --plan-file docs/plan.md
```

Recommended plan structure:

```text
What: [problem being solved]
Approach: [chosen approach and why]
Alternatives considered: [what was rejected and why]
Files to change: [list]
Addressed concerns: [if resubmitting, point-by-point from previous review]
```

### 3. Implementation

Before editing code after an approved plan, update the phase:

```bash
bash scripts/claude-state.sh set phase implementing
```

Implement the approved plan.

### 4. Code Review

If the phase is already in code-complete state and plan review was skipped in practice, start here immediately after `init`.

Code review does not require a previously approved plan. If a reviewed plan exists, Claude uses it as one input. If no reviewed plan exists, Claude must review against:

- the actual changed-code scope it can inspect;
- the description supplied by Codex;
- repository rules and project contracts;
- surrounding implementation context and tests.

Describe what changed and the important decisions. Do not pass a git diff; Claude can inspect the repository.

```bash
bash scripts/claude-review.sh code --phase-key 02-01 "What changed: JWT auth middleware and refresh endpoint. Key decisions: RS256 for key rotation. Files modified: auth/jwt.py, api/auth.py. Tests: added expired/invalid/valid token tests; all pass."
```

Recommended code review description:

```text
What changed: [summary]
Key decisions: [non-obvious implementation choices]
Files modified: [list with a brief description per file]
Tests: [what was added/run and results]
Addressed concerns: [if resubmitting, point-by-point from previous review]
```

Claude review uses this multi-track rubric:

- `code-reviewer` for project rules, correctness, maintainability, security, and merge readiness.
- `pr-test-analyzer` for behavior coverage, critical gaps, negative cases, concurrency/async behavior, and brittle tests.
- `silent-failure-hunter` for swallowed errors, weak logging, unjustified fallbacks, broad catches, retries, and hidden failures.
- `comment-analyzer` for changed comments, docs, TODOs, examples, and claims that can drift from implementation.
- `type-design-analyzer` for changed types, schemas, DTOs, APIs, persisted state, and domain invariants.

Claude should report only high-confidence actionable issues as blocking, but it must still state which review tracks were applicable, what it verified directly, what it only treats as claimed by Codex, and any residual risk from unavailable diffs or blocked validation commands.

### 5. State Management

```bash
bash scripts/claude-state.sh show
bash scripts/claude-state.sh dir
bash scripts/claude-state.sh reset
bash scripts/claude-state.sh reset --full
bash scripts/claude-state.sh get session_id
bash scripts/claude-state.sh get verdict
bash scripts/claude-state.sh set session_id <uuid>
bash scripts/claude-state.sh set phase_key 02-01
bash scripts/claude-state.sh set phase implementing
```

Use `claude-state.sh dir` to locate review notes and status files for the current branch.

Only one mutating `claude-review` command may run at a time for the same branch state. A second `init`, `plan`, or `code` is rejected while another one still holds the branch lock. The lock uses `flock`, so it is released automatically when the running process exits or dies. For diagnostics, inspect:

- `review.lock` - kernel-backed branch-local `flock` file used to prevent concurrent `init`/`plan`/`code`
- `review.lock.json` - best-effort metadata for the current lock holder such as `pid`, `command`, `session_id`, `phase_key`, and `started_at`

During `init`, `state.json` is now written immediately with `phase: initializing`, the new `session_id`, and the requested `phase_key`, then updated to `phase: initialized` only after `init` completes successfully. This makes in-progress init state visible and prevents empty-branch-state handoff races.

## Exit Codes

| Exit | Status | Action |
| --- | --- | --- |
| 0 | APPROVED | Continue |
| 0 | CHANGES_REQUESTED | Fix or argue, then resubmit |
| 1 | ERROR | Report the technical failure and inspect logs |
| 2 | ESCALATE | Summarize iterations and ask the user how to proceed |
| 3 | NO_SESSION | Ask whether to create a session via `init` |

## Verdict

Claude must write the latest verdict to `verdict.txt` inside the branch state directory. The review script reads status only from that file; response text is saved for notes but is not authoritative. Always read the current verdict through:

```bash
bash scripts/claude-state.sh get verdict
```

The helper returns one of these status values:

- `READY` - `init` completed successfully, the Claude session exists, and no plan/code review has started yet.
- `STARTING` - the branch `review.lock` is still held and the active command is still in `init`/startup state. This is a transitional state used to avoid false `ERROR` while `init` or a fresh review launch is still coming up.
- `APPROVED` - Claude finished the review and approved the current submission.
- `CHANGES_REQUESTED` - Claude finished the review and requested changes.
- `IN_PROGRESS` - `verdict.txt` is still empty, but the branch `review.lock` is still held by an active `claude-review` command for this branch state.
- `ERROR` - there is no valid verdict, and the branch `review.lock` is no longer held for the current review state. Treat this as a technical failure and inspect the diagnostics file first, then the logs.

If Claude does not write a valid verdict file, the review script treats that as a technical error.

Important operational note: a sandboxed run without network access can end in `ERROR` immediately from the network preflight, or on older/stale runs after retries. In that case, inspect `claude-init.log` or the active review log, then reset and rerun the workflow outside sandbox.

For process diagnostics, inspect the current branch state directory from `bash scripts/claude-state.sh dir` and look at:

- `review.lock` - authoritative writer lock for active `init`/`plan`/`code` commands on this branch state
- `review.lock.json` - advisory metadata for the current lock holder; useful for context, but PID values may be namespace-local under sandboxed agents
- `claude.pid` - advisory child PID while the process is running locally; do not treat it as a cross-sandbox source of truth
- `claude-process.json` - process metadata for the current or most recent launch, including `pid`, `phase`, `session_id`, launcher ids, lifecycle stage, `started_at`, `ended_at`, and exit status
- `claude-launcher.log` - launcher lifecycle log with stage-by-stage events such as queueing, coprocess start, stream processing, waiting, cleanup, and signal handling
- a held `review.lock` means the review command is still active even if PID fields look invalid from another sandbox namespace
- `verdict-error.txt` - extended diagnostics written automatically by `bash scripts/claude-state.sh get verdict` whenever it returns `ERROR`; check this first before reasoning about branch/worktree/session mismatches, then inspect `claude-launcher.log`

## Handling CHANGES_REQUESTED

When Claude requests changes:

1. Read the latest note from `$(bash scripts/claude-state.sh dir)/notes/{phase}-review-{N}.md`.
2. Critically evaluate every point. On resubmission, address every point explicitly:
   - Fixed: what changed and how.
   - Disagree: counterargument with project-specific reasoning.
   - Deferred: why, only with user approval.
3. If the same point repeats twice without new information, escalate to the user with your argument and the reviewer concern.

## Handling ESCALATE

When the iteration limit is reached:

1. Get the state directory with `bash scripts/claude-state.sh dir`.
2. Summarize review notes from `notes/`.
3. Ask the user whether to run one more iteration, remove the limit for this review, or stop the review.
4. Repeat with `--max-iter N` according to the user's choice.

## Rules

- Do not call `claude -p` directly for this workflow; use `claude-review.sh` and `claude-state.sh`.
- Do not run this workflow in a network-restricted sandbox. `claude-review.sh` needs live API access.
- `--phase-key` is required for `init`, `plan`, and `code`.
- Start a new `init` for every new work phase in the same git branch.
- `plan` and `code` must use the same `phase_key` that was used during `init`; the script rejects mismatches.
- Do not force a synthetic `plan` review if the code is already written and the real plan-review stage was skipped; in that case use `init -> code review`.
- Do not describe code review as being against a previously approved plan unless a reviewed plan actually exists.
- Explain what changed and why; Claude can inspect files and diffs by itself.
- Do not ask Claude to edit files. Claude is the reviewer in this workflow.
- Do not pass raw git diffs unless the reviewer explicitly asks for one after a failed inspection.
- Treat `APPROVED` as permission to continue, not as a substitute for required local tests and linters.
- State is isolated per git branch under `.claude-review/` in the main repository root.
