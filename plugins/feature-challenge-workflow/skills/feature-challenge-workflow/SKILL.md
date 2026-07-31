---
name: feature-challenge-workflow
description: "Challenge requested features before implementation. Use when a user asks to add a new feature, change product behavior, expand scope, perform a risky refactor, or make an architectural change, especially when the request states a solution before confirming the real problem. The workflow verifies the user-confirmed problem, existing capabilities, architectural and product fit, alternatives, risks, and decision gates before code changes."
metadata:
  short-description: Challenge features before coding
---

# Feature Challenge Workflow

Use this skill before implementing a requested feature or substantial behavior
change. The goal is not to write a plan first. The goal is to prove that the
feature is needed, not already covered, compatible with the product, and worth
building in the proposed shape.

This workflow may stop implementation. Valid outcomes include rejecting the
feature, documenting an existing capability, reducing scope, or asking the user
for a decision.

## Core Rule

Proceed one gate at a time. Do not move to the next gate until the current gate
is explicitly complete.

A gate can pass without extra user interaction if the required evidence is
already available, but the check must still be performed and recorded.

Do not write code until the final decision allows implementation.

## State Artifacts

Use strict JSON as the authoritative workflow state. Do not track status,
current gate, decisions, or active feature selection in Markdown.

Default paths in the current repository:

- `.agents/feature-challenges/index.json` - registry of known feature
  challenges and the currently active feature;
- `.agents/feature-challenges/<featureId>.json` - complete workflow state for
  one feature challenge.

Markdown may be used only as supplementary human notes when explicitly useful.
It must not be the source of truth for workflow status.

Minimum feature state shape:

```json
{
  "schemaVersion": 1,
  "featureId": "feature-YYYYMMDDTHHMMSSZ",
  "title": "Human-readable feature title",
  "summary": "Short feature summary",
  "aliases": [],
  "workClaim": {
    "ownerId": "host:codex-session",
    "ownerLabel": "Codex host:codex-session",
    "claimedAt": "YYYY-MM-DDTHH:MM:SSZ",
    "updatedAt": "YYYY-MM-DDTHH:MM:SSZ",
    "expiresAtEpoch": 1770000000
  },
  "status": "in_progress",
  "required": true,
  "stage": "problem_gate",
  "createdAt": "YYYY-MM-DDTHH:MM:SSZ",
  "updatedAt": "YYYY-MM-DDTHH:MM:SSZ",
  "requestedSolution": {
    "statement": "",
    "sourcePrompt": ""
  },
  "problem": {
    "status": "not_confirmed",
    "confirmedByUser": false,
    "statement": "",
    "questions": []
  },
  "existingCapabilityCheck": {
    "status": "not_started",
    "findings": [],
    "conclusion": ""
  },
  "fitCheck": {
    "status": "not_started",
    "architectureFit": "",
    "productFit": "",
    "constraints": []
  },
  "challenge": {
    "status": "not_started",
    "objections": [],
    "alternatives": []
  },
  "interview": {
    "status": "not_started",
    "openQuestions": [],
    "answers": []
  },
  "decision": {
    "status": "not_started",
    "decision": null,
    "reason": "",
    "allowedNextStep": ""
  }
}
```

Minimum index shape:

```json
{
  "schemaVersion": 1,
  "activeFeatureId": "feature-YYYYMMDDTHHMMSSZ",
  "activeByOwner": {
    "host:codex-session": "feature-YYYYMMDDTHHMMSSZ"
  },
  "features": [
    {
      "featureId": "feature-YYYYMMDDTHHMMSSZ",
      "title": "Human-readable feature title",
      "summary": "Short feature summary",
      "aliases": [],
      "status": "in_progress",
      "stage": "problem_gate",
      "workOwner": "Codex host:codex-session",
      "createdAt": "YYYY-MM-DDTHH:MM:SSZ",
      "updatedAt": "YYYY-MM-DDTHH:MM:SSZ"
    }
  ],
  "createdAt": "YYYY-MM-DDTHH:MM:SSZ",
  "updatedAt": "YYYY-MM-DDTHH:MM:SSZ"
}
```

Keep `updatedAt` current whenever a gate, status, question, answer, objection,
or decision changes.

`featureId` is an internal file key. Do not ask the user to remember it and do
not use it as the primary way to discuss work. User-facing selection must use
`title`, `summary`, or a short numbered list derived from `index.json.features`.
The initial title may be derived from the user's request, but after the Problem
Gate it should be rewritten into a concise neutral title that a user can
recognize later.

## Multiple Feature Challenges

The workflow supports multiple feature challenges in one repository.

Each feature has its own JSON file under `.agents/feature-challenges/`. Do not
merge unrelated features into one file.

`index.json.activeByOwner` is the primary routing map. It lets multiple Codex
instances keep different active features in the same repository. Keep
`index.json.activeFeatureId` only as a compatibility fallback and "last active"
hint; do not treat it as exclusive global state.

When the user starts a separate feature request while another challenge is
active:

1. create a new `<featureId>.json`;
2. add an object with `featureId`, `title`, `summary`, `status`, and `stage` to
   `index.json.features`;
3. set `index.json.activeByOwner[ownerId]` to the feature currently being
   discussed;
4. keep the previous feature state unchanged.

When selecting which feature to work on:

1. Match the user message against `title`, `summary`, and `aliases`.
2. If exactly one feature matches, set `index.json.activeByOwner[ownerId]` to that
   feature and continue.
3. If multiple features match, ask the user to choose from a short numbered
   list showing `title`, `status`, and `stage`.
4. If no feature matches but the message is clearly a new feature request,
   create a new feature state with a concise title and summary.
5. Never ask the user for `featureId` unless they explicitly mention one from
   the JSON file.

## Concurrent Codex Work

Multiple Codex instances may work in the same repository at the same time only
when they work on different feature challenges.

Use these coordination rules:

- Use `.agents/feature-challenges/index.lock` with `flock -n` only for short
  critical sections that read or write `index.json`.
- Do not rely on `flock` as a long-lived feature ownership marker. The lock is
  released when the hook shell process exits.
- Store the current feature per Codex owner in `index.json.activeByOwner`.
- Store long-lived feature ownership in `<featureId>.json.workClaim`.
  Claims expire after `FEATURE_CHALLENGE_CLAIM_TTL_SECONDS`, defaulting to
  86400 seconds, and are refreshed when the owning Codex touches the feature.
- Before creating a new feature, hold the index lock and check existing
  `title`, `summary`, and `aliases`. If the same feature already exists, route
  to it instead of creating a duplicate.
- Before editing code or workflow JSON for a feature, check and refresh that
  feature's `workClaim` while holding the short index lock. If another owner
  already holds a non-expired `workClaim`, stop and ask the user whether to
  wait, switch to another feature, or explicitly hand over ownership.
- Do not allow approval, state updates, or code changes for one feature to
  apply to another feature.

This prevents two Codex instances from independently starting the same new
feature while still allowing parallel work on separate features in the same
repository.

Parallel work is allowed only when every feature being implemented has its own
approved decision. If two features are independent, they may progress through
the gates independently. If they touch the same files, schema, user workflow, or
runtime behavior, record the conflict in both JSON files and choose one of:

- serialize the work and keep only one feature active;
- reduce the scope of one feature;
- stop and ask the user for priority.

Do not let approval for one feature authorize implementation for another
feature. The allowed implementation scope is always limited to the
`decision.allowedNextStep` of that feature's JSON file.

## Gates

### 1. Problem Gate

Separate the user's requested solution from the underlying problem.

The user owns the problem statement. You may propose a problem hypothesis, but
you must not treat it as confirmed unless the user confirms it or it follows
unambiguously from prior context.

Record:

- requested solution;
- problem hypothesis;
- confirmed problem;
- whether the confirmation came from the user or prior context;
- questions required to confirm the problem.

Do not continue if the real problem is unknown.

### 2. Existing Capability Gate

Check whether the problem is already solved or nearly solved.

Look for:

- exact existing feature;
- similar feature;
- different product path that solves the same problem;
- existing mechanism that needs only a small extension;
- configuration-only solution;
- documentation-only solution;
- process-only solution;
- prior implementation in git history if not present in `HEAD`.

Prefer improving or documenting existing behavior over adding a parallel feature.

### 3. Fit Gate

Check whether the requested solution fits the current system.

Evaluate:

- architecture compatibility;
- product ideology and expected user model;
- module ownership boundaries;
- operational behavior;
- testing surface;
- support cost;
- runtime consistency risks;
- fields or states that cannot be safely changed live;
- whether the feature creates two competing ways to do the same thing.

If the solution does not fit, choose `Reject`, `Reduce Scope`, or
`Research Required` instead of proceeding.

### 4. Challenge Gate

Argue against the feature before accepting it.

Ask:

- What breaks if we do nothing?
- Who benefits from this feature?
- What hidden maintenance cost appears?
- What new failure modes appear?
- Does it make the product less predictable?
- Does it create false confidence?
- Is there a smaller intervention?
- Would documentation, configuration, or process solve the real problem?
- Is the requested solution broader than the confirmed problem?

Record objections and alternatives in the active feature JSON file. Do not hide
weak assumptions.

### 5. Interview Gate

Ask the user only for decisions that cannot be answered from code,
documentation, logs, or repository history.

Questions should be non-obvious and should affect the decision. Prefer one
question or a small related group at a time. Include a recommended answer when
possible, and explain what risk the question closes.

Cover relevant topics:

- real user problem;
- expected outcome;
- technical boundary;
- behavior on errors;
- compatibility expectations;
- user experience;
- operations;
- risks;
- tradeoffs;
- criteria for rejecting the feature.

If `request_user_input` is available, use it for user-facing clarification
questions. If it is not available, ask concise plain-text questions.

### 6. Decision Gate

Choose one decision:

- `Already Exists` - no code; point to existing behavior or add docs if asked.
- `Use Existing With Small Extension` - code allowed only for the extension.
- `Docs Or Config Only` - no product code; update docs or configuration.
- `Reject` - no code; explain why the feature is harmful or unnecessary.
- `Research Required` - no implementation until research is complete.
- `Reduce Scope` - code allowed only for the reduced scope.
- `Proceed` - code allowed for the proposed scope.

Only `Use Existing With Small Extension`, `Reduce Scope`, and `Proceed` allow
implementation.

Code changes are allowed only when the active feature JSON also has:

- `decision.status: "approved"`;
- non-empty `decision.allowedNextStep`;
- `problem.confirmedByUser: true`;
- `problem.status: "confirmed"` or `"complete"`;
- `existingCapabilityCheck.status: "complete"`;
- `fitCheck.status: "complete"`;
- `challenge.status: "complete"`;
- `interview.status: "complete"` or `"skipped"`.

## State Machine

Track the workflow as a state machine:

```text
idle
candidate_detected
problem_gate
existing_capability_gate
fit_gate
challenge_gate
interview_gate
decision_gate
approved_for_implementation
implementation
done
cancelled
```

User messages during an active workflow are routed by feature title, summary,
and aliases. If the message belongs to the current active feature, continue
using `index.json.activeByOwner[ownerId]`. Switch that owner-specific active
feature only when the user explicitly changes topic, asks to resume another
feature by name, or starts a distinct feature request.

Restart or rewind only when the user changes one of the foundations:

- real problem;
- target user;
- expected outcome;
- feature scope;
- architecture constraint;
- product constraint;
- risk tolerance;
- selected solution.

If scope expands during implementation, return to `fit_gate` or
`challenge_gate` before continuing.

## Hook-Aware Enforcement Model

This skill describes the workflow and bundles prototype hook scripts. Read
[references/hook-setup.md](references/hook-setup.md) before enabling hooks.

Recommended command to install and trust the hook enforcement (`<skill-dir>` is the
directory that holds this SKILL.md):

```sh
<skill-dir>/scripts/enable-hooks.sh
```

To remove the hook enforcement block:

```sh
<skill-dir>/scripts/enable-hooks.sh disable
```

Recommended Codex hook roles:

- `UserPromptSubmit`: route each user message, create or update workflow state,
  and avoid starting a new workflow for normal answers.
- `PreToolUse`: allow read-only investigation, but block code-writing tools
  until the decision allows implementation. Writes to
  `.agents/feature-challenges/*.json` are allowed so the workflow can record
  gate progress before implementation is approved.
- `Stop`: prevent the agent from ending a turn while the current gate is still
  incomplete; return a continuation prompt for the missing gate.
- `PostToolUse`: provide secondary feedback if the agent bypasses the expected
  sequence.

Do not use `PermissionRequest` as the primary enforcement point. It only runs
on approval paths and may not cover already-allowed actions.

The bundled scripts are intentionally conservative:

- they require `jq`;
- they store local workflow state in
  `.agents/feature-challenges/index.json` and
  `.agents/feature-challenges/<featureId>.json`;
- they protect `index.json` changes with `flock -n` on
  `.agents/feature-challenges/index.lock`; this lock is intentionally
  short-lived and ends when the hook script exits;
- they use `activeByOwner` so separate Codex instances can work on separate
  features in one repository;
- they persist feature ownership in `workClaim` before workflow-state or code
  writes, and block a different Codex from working on the same feature at the
  same time;
- they refresh ownership until `workClaim.expiresAtEpoch`; expired claims may
  be taken over by another Codex;
- they create a separate JSON state file when a distinct feature-like request
  is detected;
- they expose feature titles and summaries in hook messages so the agent can
  route user messages without asking for `featureId`;
- they allow read-only investigation;
- they allow only isolated updates to the active feature JSON file while gates
  are incomplete; edits to another feature JSON, `index.json`, or product code
  remain blocked;
- they block write-like tools until the recorded decision and required gate
  statuses allow code changes.

## Output Expectations

Before implementation, report the current gate and the next required action.

When asking the user a question, separate the verified facts from the unresolved
decision.

When rejecting or reducing scope, be direct and evidence-based.

When implementation becomes allowed, state the exact allowed scope and keep code
changes inside that scope.
