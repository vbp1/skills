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

The opponent runs in plan permission mode and with its own sparring skill switched
off, so it reads the working directory, edits nothing, and answers instead of starting
a debate of its own.

## Prerequisites

Check before the first turn:

```bash
command -v claude
command -v timeout
command -v python3
```

Any one missing → report which one and stop. Do not substitute another agent.

The harness is `<skill-dir>/scripts/sparctl`, where `<skill-dir>` is the directory this
SKILL.md was read from. Read `scripts/sparctl --help` when an option is unclear. No
executable `sparctl` under that path → report `SPARRING_HARNESS_MISSING` with the path
checked, and stop.

The opponent's access to the web and to documentation servers comes from its own
configuration, not from this skill. When a claim depends on freshness, ask the
opponent in the prompt to name the source it checked.

## Files for one debate

Pick one slug per debate (for example `spar-auth`) and keep these paths in `/tmp` for
its whole length:

| Path | Holds |
|---|---|
| `/tmp/<slug>.prompt` | the prompt for the current turn |
| `/tmp/<slug>.session` | the session; reuse it for every turn of this debate |
| `/tmp/<slug>.turnN.txt` | the opponent's answer for turn N |
| `/tmp/<slug>.log` | the opponent's progress log for the current turn |

The harness keeps two more files next to the session: `.id` (the session id, written
the moment the opponent announces it) and `.transcript` (the readable record of every
turn). A new debate gets a new slug. Never reuse a `.session` file across unrelated
debates, and never run two turns against one session at the same time.

## Running one turn

Write the prompt to `/tmp/<slug>.prompt` with a quoted heredoc. Run every turn
detached, so the shell call returns immediately:

```bash
setsid nohup <skill-dir>/scripts/sparctl ask \
  --state /tmp/<slug>.session \
  --prompt-file /tmp/<slug>.prompt \
  --out /tmp/<slug>.turn1.txt > /tmp/<slug>.log 2>&1 &
```

Then poll the log every 60–90 seconds:

```bash
tail -n 5 /tmp/<slug>.log
```

The log carries the opponent's actions as they happen — shell commands, tool calls,
web searches, interim messages — and ends with exactly one terminal line:

- `wrote answer:` → the turn succeeded; read `--out`.
- a line starting with `SPAR_` → the turn failed; report that line to the user
  verbatim and stop.

Match the terminal line at the start of a line: the opponent quotes these words in
its own text, and those lines carry a timestamp in front.

Neither line present → ask the harness whether the turn is still alive:

```bash
<skill-dir>/scripts/sparctl status --state /tmp/<slug>.session
```

- `running` → poll again.
- `abandoned` → the turn was killed outright and left no terminal line. Report that
  and rerun the same turn; the session survives.
- `idle` → no turn is running; rerun.

One turn at a time per session: a second turn against a session already in use is
refused. The transcript records failed turns as well as answered ones.

Pass the prompt through `--prompt-file`. Use `--prompt "<text>"` only for a one-line
follow-up. Raise `SPAR_TIMEOUT` (seconds, default 3600) only when a turn is expected
to run longer than an hour.

## The loop

1. Write the opening prompt from the template below, in the user's language, and run it.
2. Read the answer. Set your own position against it: what you accept, what you reject,
   what stays disputed, what new question appeared.
3. Verify every factual claim the opponent makes about the code against the code itself
   before accepting it. An unverified blocker is not a blocker.
4. Required user data is missing → stop the debate and return the question list to the
   user. Do not invent the missing data.
5. Send a follow-up turn while the continue gate below says yes. Name the exact
   disagreement and ask the opponent to defend it, revise it, or propose a synthesis.
6. Delete `/tmp/<slug>.prompt`, `/tmp/<slug>.turn*.txt`, `/tmp/<slug>.log`,
   `/tmp/<slug>.session` and its `.id` and `.transcript` companions after the final
   synthesis, unless the user asked to keep them.
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

Answer by yourself. Do not start a sparring session of your own, do not call another
CLI agent, and do not delegate this to a sub-agent: you are the second opinion here.

Work in this order:
1. Restate the task as you understood it: the goal, the constraints that matter, and
   the assumptions being made.
2. Check the framing: is this the right problem, is the direction necessary, is there
   unnecessary complexity, a duplicated concept, or a simpler model?
3. Check freshness: are the proposed approaches, patterns, libraries, APIs and tools
   current? Use web search or current documentation before recommending a solution,
   and name the source you checked.
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
