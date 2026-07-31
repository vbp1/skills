# vbp1 skills

A plugin marketplace of agent skills for [Claude Code](https://code.claude.com/docs)
and [OpenAI Codex CLI](https://developers.openai.com/codex/cli). Every skill lives
in this repository — one plugin per skill, installed individually.

## Install

**Claude Code**

```bash
claude plugin marketplace add vbp1/skills
claude plugin install create-pr@vbp1-skills
```

**Codex CLI**

```bash
codex plugin marketplace add vbp1/skills
codex plugin add create-pr@vbp1-skills
```

Inside an interactive session use `/plugin marketplace add vbp1/skills` instead.

## Catalogue

Skills marked **Claude** were written against Claude Code, **Codex** against Codex
CLI. The `SKILL.md` format is shared, so either one loads in either agent, but the
wording and tooling assumptions follow the agent it was written for. Three skills
exist as two separate variants because the two versions diverged.

| Plugin | Written for | What it does |
| --- | --- | --- |
| `audio-restore` | Claude | Restore muffled or low-quality recordings: stem separation, EQ correction, high-frequency recovery. |
| `break-it` | Codex | Adversarial test pass: write tests that try to falsify a change, keep only the ones that catch real defects. |
| `claude-review` | Codex | Cross-agent review workflow: Codex implements, Claude Code reviews, findings loop back until resolved. |
| `cloakbrowser` | Claude | Inspect web pages in a local stealth Chromium: screenshots, client-side JS errors, failed requests, long-task timings. |
| `cloakbrowser-codex` | Codex | Same tool, Codex variant: screenshots and visual UI checks. |
| `codex-genimage` | Claude | Generate images through the Codex CLI built-in image tool, billed via existing Codex auth. |
| `create-pr` | Claude | Branch, commit, push, open the pull request, set labels and project fields in one pass. |
| `create-pr-codex` | Codex | Same workflow, Codex variant. |
| `decision-playground` | Codex | Turn a long list of choices into a self-contained interactive HTML page, read the answers back as structured data. |
| `feature-challenge-workflow` | Codex | Challenge a feature request before any code: real problem, existing capability, alternatives, decision gates. |
| `feature-plan-storyboard` | Claude | Plan a feature, verify every claim against the current code, build an interactive user-story storyboard page. |
| `langfuse-debug` | Claude | Investigate agent runs recorded in Langfuse: failed sessions, token usage, tool-call patterns. |
| `phased-task-delivery` | Codex | Run a complex task through explicit phases: plan documents, review gates, per-phase commits, final validation. |
| `remote-ssh-workspace` | Codex | Make a remote host behave like a local worktree: SSH multiplexing, sshfs mounts, detached long jobs. |
| `rust-code-review` | Codex | Review Rust for hazards that survive cargo build, cargo test and clippy: async, unsafe, lifetimes, locks. |
| `simple-tech-writing` | Claude | Rewrite technical text so a tired reader cannot misread it: ASD-STE100 rules plus a Russian rule set. |
| `technical-premortem` | Claude | Assess a planned change before it is written: blast radius, rollback plan, pre-flight checklist, go/no-go verdict. |
| `telemost-scribe-api` | Claude | Query the local Telemost Scribe API: schedules, meetings, transcripts, answers with citations. |
| `telemost-scribe-api-codex` | Codex | Same API, Codex variant. |
| `user-clear-communication` | Codex | Write user-facing replies, statuses and reports that stay readable: plain wording, explicit outcomes, no filler. |
| `youtube-transcript` | Claude | Pull the transcript of a YouTube video, with or without timestamps. |

Some skills need external tooling that is not bundled here: `cloakbrowser` expects
the CloakBrowser CLI on the machine, `telemost-scribe-api` expects a local Telemost
Scribe service, `langfuse-debug` expects Langfuse credentials, `codex-genimage`
expects an authenticated Codex CLI. Each `SKILL.md` states its prerequisites.

## Layout

```
.claude-plugin/marketplace.json   catalogue read by Claude Code
.agents/plugins/marketplace.json  catalogue read by Codex CLI
plugins/<name>/
    .claude-plugin/plugin.json    plugin manifest (both agents read it)
    skills/<name>/SKILL.md        the skill itself, plus its scripts and references
```

Both catalogues list the same plugins and point at the same directories, so a skill
is stored once and published to both agents.

## Develop locally

Point either agent at a working copy instead of GitHub:

```bash
claude plugin marketplace add /path/to/skills
codex plugin marketplace add /path/to/skills
```

Validate before publishing:

```bash
claude plugin validate . --strict              # the marketplace manifest
claude plugin validate ./plugins/create-pr --strict   # a single plugin
```

## License

Apache-2.0. See [LICENSE](LICENSE).
