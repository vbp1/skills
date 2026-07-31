# Plan method — verify, write, cross-review

Detailed guidance for stages 1–4 of the skill. The goal is a plan that a
teammate (or an implementing agent) can trust line-for-line because every claim
about the code has been checked against the working tree and a second reviewer
has signed off.

## 1. Verifying the plan against current code

A plan rots silently: a refactor removes a table, renames a function, or
completes a dependency, and the plan keeps citing the old reality. Treat the
plan as a list of falsifiable claims and test each one.

### Extract the claims

Read the plan and pull out everything concrete:
- File paths, symbols, line references (`foo.ts:42`, `ClassName.method`).
- "X already works / is done / exists" statements about the code.
- Dependency/status assertions ("blocked on plan Y", "Y is merged").
- Data-model assumptions (a table/column the plan reads or writes).
- The named foundation the plan builds on (a bus, a registry, a transport).

### Fan out parallel research agents

Use the `Agent` tool with `Explore` or `general-purpose`, **one sweep per
subsystem**, launched in the same turn so they run concurrently. Give each a
tight brief: the exact claims to check, and a required output format — per claim,
a verdict **CONFIRMED / STALE / WRONG** with `file:line` evidence and the
*current* truth if it differs. Ask for actual line numbers, not paraphrase.

Tell the agents about known-suspicious areas up front (e.g. "commit Z removed
the old bus; grep finds none"), so they don't waste effort rediscovering it.

### Re-verify load-bearing facts yourself

For anything a decision hinges on (a missing table, an auth path, a race
window), open the file yourself and confirm. Subagents are fast but can
misreport a line; a wrong citation here propagates into the plan and the codex
review.

### Present before editing

Summarize findings as a **severity-ranked table** — Blocker / Important /
Cosmetic — each row: the claim, the verdict, the evidence (`file:line`), and the
fix. Blockers are claims whose falsehood breaks the plan's approach (e.g. the
storage the design assumes no longer exists). Surface this to the user before
rewriting, per the project's "present findings and proposed fix first" rule.

## 2. Resolving forks (AskUserQuestion, plain language)

Verification often turns up a genuine decision, not just a typo — for example,
"the place the plan wanted to store X is gone; do we add a durable store, keep it
in memory, or drop persistence?". These are the user's calls.

Question-writing rules (mirror the user's global style rule):
- The question text and **every option's label + description** must read to
  someone who has never seen the code.
- Forbidden in questions/options: class/method/function/type/field names, file
  paths, internal or jargon terms, spec/CI tags, line/PR numbers.
- Describe each option by its **consequence** in everyday words; recommended
  option first, labelled "(рекомендую)".
- Put the technical detail (names, paths) in your normal prose *after* the user
  has chosen — not in the question.

GATE before sending: re-read the question and options and strike every term a
"person off the street" wouldn't know. If a technicality remains, rewrite.

## 3. Writing the plan (prose + file:line, no code)

Plans describe **intent, architecture, and decisions in words**, with links to
concrete code locations — not code snippets. ASCII diagrams and tables are
allowed; pseudocode only when meaning is genuinely lost without it. If you need
to indicate an API/signature/type/format, link to the `file:line` where it's
defined and describe it in words.

Section template that has worked well:

- **Header**: type, status, related issues, prominent link to the storyboard page.
- **Dependencies**: each with current status + `file:line` proof it's done/exists.
- **What already works (don't rebuild)**: the verified foundation, with evidence.
- **What's genuinely new**: the actual scope.
- **Key decisions** (table): Aspect | Decision | Rationale — one row per
  load-bearing choice (transport, storage, routing, concurrency control, auth).
- **Architecture** (ASCII): the request/▸event flow; keep it consistent with the
  prose — reviewers flag any drift between diagram and text.
- **Data model**: schema changes, or an explicit note that none are needed and why.
- **Phases**: checklist per phase; first phase = the core mechanism.
- **Test strategy**: unit / regression / e2e, matched to the project's own test
  setup. For e2e, one entry per user story: target spec location, the project's
  test tags/lanes (if it has them), the invariant it asserts, and key checks.
- **Affected files** (orientation): reused vs new vs modified.
- **Security**: who-can-do-what; where enforcement lives (not just RLS/coarse).
- **Open decisions**: what's deferred and why; mark resolved ones as resolved.

Keep sections mutually consistent. The most common review bounce is a fix
applied in one section that now contradicts the ASCII diagram or the decisions
table elsewhere — change all of them together.

## 4. Cross-review with a second AI (codex), to APPROVED

A second independent reviewer catches races, missing contracts, and
self-contradiction that the author is blind to. Use the project's
`codex-review` skill (read its SKILL.md when it launches).

Loop:
1. `init` a fresh session for this plan (archives any stale one).
2. Submit the plan file for review.
3. On `CHANGES_REQUESTED`, read each finding and **critically** decide:
   - **Accept**: real gap → fix it in the plan, addressing the point precisely.
   - **Argue**: the reviewer is wrong/outdated → re-check the cited code via the
     project's library-docs tool or by reading it, then push back with reasoning.
     Reviewers err too; don't accept blindly (the project's review rule says so).
   - **Defer**: only with the user's agreement.
4. In the resubmission, address **every** finding point-by-point, and
   re-synchronize all sections so a fix doesn't introduce drift elsewhere.
5. Repeat until the **formal verdict** is `APPROVED` — check the verdict via the
   skill's helper, not by interpreting the review prose.

Recurring finding *classes* worth self-checking before submitting (illustrative,
not exhaustive — the exact set depends on the feature, and these happen to be the
ones that surfaced reviewing a realtime collaboration plan): in-memory state that
doesn't survive a restart; a queued/deferred action reusing a stale snapshot; a
lock/registration acquired at the wrong moment causing a race; an ambiguous
"how do clients catch up after a gap" story; coarse access control mistaken for
fine-grained; a wire/API contract too thin for the UI it must drive; the same
order of operations described two different ways in two sections. For a feature
of a different nature, expect a different list — the point is to read your own
plan adversarially, not to tick these specific boxes.

Commit the plan only after `APPROVED` (and only if the user asks). If the plan
directory is git-excluded, note that there's nothing to commit.
