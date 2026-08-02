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
wording and tooling assumptions follow the agent it was written for. Two skills
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
| `user-clear-communication` | Codex | Write user-facing replies, statuses and reports that stay readable: plain wording, explicit outcomes, no filler. |
| `youtube-transcript` | Claude | Pull the transcript of a YouTube video, with or without timestamps. |

Some skills need external tooling that is not bundled here: `cloakbrowser` expects
the CloakBrowser CLI on the machine, `langfuse-debug` expects Langfuse credentials,
`codex-genimage` expects an authenticated Codex CLI. Each `SKILL.md` states its
prerequisites.

Commands inside a `SKILL.md` refer to bundled scripts as `<skill-dir>/scripts/…`.
`<skill-dir>` is the directory that holds that `SKILL.md`, wherever the agent
installed it.

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
claude plugin validate . --strict                     # the marketplace manifest
claude plugin validate ./plugins/create-pr --strict   # a single plugin
```

## Add a skill

1. Put it in `plugins/<name>/skills/<name>/`.
2. Add a row to the `PLUGINS` table in [`scripts/gen-manifests.py`](scripts/gen-manifests.py):
   name, display name, one-line description, a category for each agent, keywords,
   and which agent it was written for.
3. Add its starting version to the `VERSIONS` table in the same file. A plugin missing
   from it stops the generator rather than defaulting.
4. Run `./scripts/gen-manifests.py`. It rewrites every plugin manifest and both
   catalogues, so the two never drift apart. See `--help` for details.
5. Validate, commit, push, then `claude plugin tag ./plugins/<name> --push`.

## Release a change

Both agents cache a plugin under its pinned version and skip an update while the version
string is unchanged, so an edit without a bump never reaches installed copies — and nothing
reports an error, because as far as the agent is concerned there is nothing new. The cycle:

1. Edit the plugin.
2. Bump its entry in the `VERSIONS` table — only that plugin's, the numbers are independent.
3. `./scripts/gen-manifests.py`, which refuses to write while any plugin's files have moved
   since its version was tagged.
4. Commit, then `claude plugin tag ./plugins/<name> --push` to cut `<name>--v<version>`.

Three things watch for a forgotten bump. The generator checks before it writes.
[`scripts/check_versions.py`](scripts/check_versions.py) does the same on demand, and exits 3
when something is stale. A `pre-push` hook blocks the push itself — enable it once per clone:

```bash
git config core.hooksPath hooks
```

CI runs both the version check and a regeneration diff on every push, so a clone without the
hook is still covered.

## License

Apache-2.0. See [LICENSE](LICENSE).
