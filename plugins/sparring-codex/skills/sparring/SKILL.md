---
name: sparring
description: |
  Debate a plan, an idea, an architecture or a risky change with Claude Code as the
  opponent, then return a synthesis instead of a transcript. Use for a second opinion
  before implementing, for stress-testing your own conclusion, and for comparing
  alternatives.
  Triggers (RU): "спарринг", "спарринг с claude", "поспорь с claude", "обсуди с claude",
  "второе мнение", "второе мнение от claude", "оспорь план с claude".
  Triggers (EN): "sparring", "spar with claude", "second opinion", "second opinion from
  claude", "discuss this with claude", "challenge this plan with claude".
---

# Sparring

The opponent is Claude Code CLI, always. Never open a second Codex for sparring; a
debate with the same model returns the same blind spots.

## Prerequisites

Check before the first turn:

```bash
command -v claude
command -v timeout
```

Either one missing → report which one and stop. Do not substitute another agent.

The harness is `<skill-dir>/scripts/sparctl`, where `<skill-dir>` is the directory this
SKILL.md was read from. Read `scripts/sparctl --help` when an option is unclear. No
executable `sparctl` under that path → report `SPARRING_HARNESS_MISSING` with the path
checked, and stop.

The opponent runs in plan permission mode: it reads the working directory and edits
nothing.

## Files for one debate

Pick one slug per debate (for example `spar-auth`) and keep these four paths in
`/tmp` for its whole length:

| Path | Holds |
|---|---|
| `/tmp/<slug>.prompt` | the prompt for the current turn |
| `/tmp/<slug>.session` | the Claude session; reuse it for every turn of this debate |
| `/tmp/<slug>.turnN.txt` | the opponent's answer for turn N |
| `/tmp/<slug>.log` | the harness output when the turn runs detached |

A new debate gets a new slug. Never reuse a `.session` file across unrelated debates.

## Running one turn

Write the prompt to `/tmp/<slug>.prompt` with a quoted heredoc, then pick one of the
two forms below. Both write the answer to `--out` and print `wrote answer: ...` when
done.

**Short turn** — a focused rebuttal, a single clarifying question, anything expected
under nine minutes. Run it directly and wait:

```bash
SPAR_TIMEOUT=570 <skill-dir>/scripts/sparctl ask \
  --state /tmp/<slug>.session \
  --prompt-file /tmp/<slug>.prompt \
  --out /tmp/<slug>.turn2.txt
```

**Long turn** — the opening turn of any debate, a full plan or code review, or a turn
that asks the opponent to check freshness against the web. Run it detached, so the
shell call returns immediately:

```bash
setsid nohup env SPAR_TIMEOUT=3600 <skill-dir>/scripts/sparctl ask \
  --state /tmp/<slug>.session \
  --prompt-file /tmp/<slug>.prompt \
  --out /tmp/<slug>.turn1.txt > /tmp/<slug>.log 2>&1 &
```

Then poll the log every 60–90 seconds:

```bash
tail -n 3 /tmp/<slug>.log
```

- Log ends with `wrote answer:` → read `--out`.
- Log holds a line starting with `SPAR_` → the turn failed; report that line to the
  user verbatim and stop.
- Neither → the opponent is still working; poll again.

Pass the prompt through `--prompt-file`. Use `--prompt "<text>"` only for a one-line
follow-up.

## The loop

1. Write the opening prompt from the template below, in the user's language. Run it as
   a long turn.
2. Read the answer. Set your own position against it: what you accept, what you reject,
   what stays disputed, what new question appeared.
3. Verify every factual claim the opponent makes about the code against the code itself
   before accepting it. An unverified blocker is not a blocker.
4. Required user data is missing → stop the debate and return the question list to the
   user. Do not invent the missing data.
5. Send a follow-up turn while the continue gate below says yes. Name the exact
   disagreement and ask the opponent to defend it, revise it, or propose a synthesis.
6. Delete `/tmp/<slug>.prompt`, `/tmp/<slug>.turn*.txt`, `/tmp/<slug>.log` and
   `/tmp/<slug>.session` after the final synthesis, unless the user asked to keep them.
7. Answer the user with a synthesis, not a transcript.

## Continue gate

Send another turn when any of these holds:

- The opponent stated a fact that conflicts with what you read in the code.
- The opponent named a blocker or a high-severity risk that nobody verified.
- The opponent skipped a disputed point, answered evasively, or answered too shallowly
  for the stakes.
- Your own check after the answer produced evidence the opponent has not seen.
- A material trade-off is still open.

Stop when the key claims are verified or marked unverified, the high-impact
disagreements are either resolved or recorded as explicit trade-offs, and another turn
would not change the recommendation.

## Prompt template

Write the opening prompt in the user's language — a Russian task gets a Russian prompt
and a Russian answer. Adapt this shape:

```text
<the user's task, plan, diff or question, in the original language>

You are the second participant in a sparring session. Do not accept the framing
automatically. Answer in the same language as the task above.

Work in this order:
1. Restate the task as you understood it: the goal, the constraints that matter, and
   the assumptions being made.
2. Check the framing: is this the right problem, is the direction necessary, is there
   unnecessary complexity, a duplicated concept, or a simpler model?
3. Check freshness: are the proposed approaches, patterns, libraries, APIs and tools
   current? Use web search or current documentation before recommending a solution.
4. List the disputed points: what is weak, where alternatives exist, what must be
   decided before a final answer.
5. Then answer the concrete request.

Put the whole answer in this response. Do not create files, plans or notes, and do not
edit anything. Quote or summarise evidence here instead of writing it elsewhere.

If required data is missing, say exactly what is missing and which decision it blocks.
Do not invent it and do not continue on a hidden assumption.

Models tend to agree in order to please. Counterbalance that: test the assumptions,
name the weak points directly, and do not agree with a position that is incomplete,
overcomplicated, outdated or wrong. Do not argue artificially when the arguments are
genuinely strong.

If my next turn objects to your position, do not fold automatically: defend what is
strong, clarify what is weak, and say explicitly what you would reconsider.
```

## Reporting back

Answer in the user's language, in this order:

1. The recommendation, first and in one or two sentences.
2. What changed in your position because of the debate, and what did not.
3. Agreements, then disputed points that survived, each as an explicit trade-off with
   its reason.
4. Alternatives compared, when the debate compared any.
5. Next steps.
6. One line naming the opponent (Claude Code) and the number of turns.

Missing user data stopped the debate → return a table of question, why it is needed,
and which decision it blocks.
