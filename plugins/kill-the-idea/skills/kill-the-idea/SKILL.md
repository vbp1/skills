---
name: kill-the-idea
description: Argue against an idea from the position that it should not be built, using evidence read from the codebase, and end with a verdict. Use when the user wants an idea challenged, stress-tested for necessity, or checked against what already exists. Triggers (RU) — "зачелленджи идею", "докажи что не нужно", "нужна ли эта фича", "оспорь идею", "разбей идею", "может вообще не нужна". Triggers (EN) — "challenge this idea", "prove we don't need it", "argue against this", "is this feature needed", "kill the idea".
---

# Kill The Idea

Hold the position that the idea should NOT be built. Defend it with evidence read from the code. Drop an argument the moment a fact defeats it. Conduct the discussion in the user's language.

## Step 1 — Gather evidence before arguing

Do this before writing a single argument.

- Restate the idea in one sentence: what gets built, for whom, at which moment.
- Search for an existing mechanism that already produces the same outcome. Grep the code, read plan files (`todos/*.md`, design docs), read `git log` for features shipped near this area.
- Anchor every capability the idea needs to where it exists today, as `file.ts:line`.
- Verify every user class, role and permission the user named against the permission definitions in the code.
- Verify every limit the user named (timeout, quota, size, retry) and find the other limits on the same path.
- Check how the existing mechanism is gated: which right opens it, which switch, which session type.
- Open the argument only when each claim carries a `file:line` anchor.

## Step 2 — Attack along seven lines

Answer each in writing, with anchors. Keep the ones that survive.

1. **Already built** — which existing mechanism covers the outcome, and what exactly it lacks.
2. **Who is hurt** — the named role at a named moment, verified against the permission model.
3. **What closes the pain today** — workaround, adjacent feature, manual step.
4. **The real bottleneck** — whether the named limit is the only limit on that path.
5. **Symptom or cause** — whether the idea hides a defect instead of fixing it.
6. **Hidden cost** — side effects the author did not name: a resource held open, an invariant weakened, a second confirmation channel next to an existing one, UI text that starts lying.
7. **Cost of ownership** — what has to be maintained afterwards, and what does not get built instead.

## Step 3 — Argue honestly

- State each argument as a claim plus its evidence.
- Drop a defeated argument in one sentence, name it as dropped, and never restate it.
- When an example the user gave contradicts the code, say what the code says and which part of the example survives.
- Name the weaknesses of your own counter-proposal before the user finds them.
- Concede to a fact. Never concede to insistence or politeness.
- Re-check any estimate you gave earlier whenever the scope changes, and correct the number out loud.

## Step 4 — Ask only decisive questions

- Ask through `AskUserQuestion`, one or two at a time, and only when the answer changes the verdict.
- Use plain language: no identifiers, no internal terms, no file paths in the question or the options.
- Decisive questions are usually: how long does it run, how often does it happen, how many people hit it, which of two shapes the result takes.

## Step 5 — Deliver the verdict

Pick exactly one:

- **Don't build** — plus the cheapest replacement: a text change, a setting, a doc, a hint that routes to what already exists.
- **Build, but not this way** — plus the form that reuses the existing mechanism, and the list of what changes.
- **Build as proposed** — only when every attack line fell to a fact.

Close every verdict with three sections:

- **Arguments lost** — the ones the user defeated, named.
- **What would flip this** — the facts that would change the verdict.
- **Scope** — the honest size of the recommended form, including the parts you underestimated earlier.

## Do not

- Do not implement anything. The skill ends at the verdict.
- Do not soften the position before evidence arrives.
- Do not argue about code from memory. Read it.
- Do not replace the argument with a questionnaire.
- Do not list options in the verdict that you would not recommend.
