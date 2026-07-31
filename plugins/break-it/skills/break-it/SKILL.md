---
name: break-it
description: "Adversarial test workflow for trying to falsify changed code with focused tests. Use when the user asks for break-it, adversarial testing, falsification, test hardening, edge-case attack, or wants Codex to write tests that try to break a recent change before keeping only useful regressions or high-value edge cases."
---

# Break It

Use this skill to switch from "prove the change works" to "try to make the
change fail." A passing adversarial test is useful only if it protects an
important edge case. A failing test is useful only if it exposes a real defect
or a wrong assumption that should be discarded.

This skill can run standalone. During a broad PR review, prefer the existing
`pr-review-toolkit` `break-it` track for read-only adversarial hypotheses, then
use this skill for focused test implementation only after the review synthesis
is complete or when the user directly asked for executable tests.

## Workflow

1. Work from the repository root:

   ```sh
   git rev-parse --show-toplevel
   ```

2. Scope the attack surface.
   - If the user named a file, area, commit, or PR, use that scope.
   - Otherwise inspect changed code against `HEAD`, starting with
     `git diff HEAD --name-only`.
   - Read local instructions first: `AGENTS.md`, `CLAUDE.md`, README test notes,
     task files, and nearby test patterns.
   - Prefer pure logic that can be called directly.
   - If the target is bound to framework-only, server-only, auth, database,
     network, IPC, streaming, browser rendering, or other integration
     boundaries, say where focused unit tests are weak. Extract a small pure
     helper only when it matches local project style and materially improves the
     test.

3. State invariants before writing tests.
   - Name the behavior the changed code promises to preserve.
   - Derive concrete candidate inputs, states, sequences, or concurrency shapes
     that could violate those invariants.
   - For each candidate, state the expected correct behavior, the predicted
     failure, and why this specific implementation might permit it.
   - Avoid generic edge-case lists unless the code itself makes them relevant.

4. Write candidate tests.
   - Use the repository's existing test framework, file naming, fixtures, and
     assertions. Mirror neighboring tests.
   - Add the smallest real test that exercises the hypothesis.
   - Do not add new dependencies unless the user explicitly asked and the
     project rules support it.
   - Keep candidates easy to delete if they prove low value.

5. Run the smallest meaningful check.
   - Use the documented single-file or filtered test command when available.
   - Save output for commands expected to run longer than 10 seconds or produce
     large logs:

     ```sh
     <scoped test command> >/tmp/break-it.tmp 2>&1
     ```

   - Inspect the saved output with `tail`, `rg`, or `sed`.
   - If a failure is only test-runner cache or phantom module resolution, clear
     the relevant cache once and rerun the same scoped command.

6. Triage every result.
   - Real defect: report the bug with file and line evidence. Fix product code
     only when the user asked for fixes or the current task clearly includes
     fixing found bugs. Keep the failing test as a regression after the fix.
   - Bad expectation: fix or remove the test.
   - Passing probe: keep only high-value edge-case coverage; remove low-signal
     tests.
   - Integration-only uncertainty: report the residual risk and the real path
     that would need to be tested.

7. Leave the tree intentional.
   - Keep only real regressions and a small number of valuable edge-case tests.
   - Remove throwaway probes.
   - Rerun the kept scoped tests.
   - If product code or tests were edited, run the required linter or quality
     gate for changed files according to project instructions.

## Report

Lead with the result, then include:

- target attacked;
- invariants challenged;
- predicted breaks;
- what actually broke, with `file:line` evidence;
- what held;
- tests kept and why;
- tests or checks not run, with residual risk.

Do not commit unless the user separately asked for a commit.
