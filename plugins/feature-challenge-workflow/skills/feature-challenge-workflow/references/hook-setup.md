# Hook Setup

This skill is separate from Codex hook activation.

The skill can be disabled while the hook scripts still exist on disk. Hook
scripts run only if they are configured under `[hooks]` in Codex config and
trusted or managed by the runtime.

## Scripts

Bundled scripts:

- `scripts/enable-hooks.sh` installs or removes the managed user-config hook
  block and can write trusted hashes for the bundled hook handlers.
- `scripts/user-prompt-submit.sh` routes new feature-like user messages into
  strict JSON workflow state.
- `scripts/pre-tool-use.sh` claims the active feature and blocks write-like
  tools until the Feature Challenge decision allows implementation.
- `scripts/stop.sh` prevents the agent from ending a turn while the current
  workflow is incomplete.
- `scripts/post-tool-use.sh` gives secondary feedback if a tool ran while the
  workflow is still not approved.
- `scripts/feature-challenge-lib.sh` contains shared JSON state helpers.

The scripts require `jq` and `flock`. `scripts/enable-hooks.sh` also requires
`sha256sum`, which is part of GNU coreutils on Linux.

## Enable Hooks

Use the bundled installer for user-level configuration:

```sh
~/.codex/skills/feature-challenge-workflow/scripts/enable-hooks.sh
```

The installer:

- sets `features.hooks = true`;
- appends a marked Feature Challenge hook block to `~/.codex/config.toml`;
- computes the same normalized `sha256:` values Codex uses for hook trust;
- writes matching `hooks.state."<key>".trusted_hash` entries;
- creates a timestamped backup next to the edited config.

Use `--dry-run` to preview the resulting config:

```sh
~/.codex/skills/feature-challenge-workflow/scripts/enable-hooks.sh --dry-run
```

Use `--no-trust` to install hooks without trust entries:

```sh
~/.codex/skills/feature-challenge-workflow/scripts/enable-hooks.sh --no-trust
```

The manual equivalent is to add this to the effective Codex config layer where
you want the hooks to run, for example `~/.codex/config.toml` or a
project-level Codex config.

```toml
[features]
hooks = true

[hooks]

[[hooks.UserPromptSubmit]]

[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "<SKILL_DIR>/scripts/user-prompt-submit.sh"
timeout = 5
statusMessage = "routing feature challenge"

[[hooks.PreToolUse]]
matcher = "apply_patch|Write|Edit|MultiEdit|Bash|mcp__.*(create|update|delete|write|patch).*"

[[hooks.PreToolUse.hooks]]
type = "command"
command = "<SKILL_DIR>/scripts/pre-tool-use.sh"
timeout = 5
statusMessage = "checking feature challenge"

[[hooks.Stop]]

[[hooks.Stop.hooks]]
type = "command"
command = "<SKILL_DIR>/scripts/stop.sh"
timeout = 5
statusMessage = "checking feature challenge completion"

[[hooks.PostToolUse]]
matcher = "apply_patch|Write|Edit|MultiEdit|Bash|mcp__.*(create|update|delete|write|patch).*"

[[hooks.PostToolUse.hooks]]
type = "command"
command = "<SKILL_DIR>/scripts/post-tool-use.sh"
timeout = 5
statusMessage = "checking feature challenge after tool use"
```

After adding unmanaged hooks, Codex may require reviewing and trusting them
before they run. The TUI hook review screen can trust new or modified hooks.
App-server clients can use `hooks/list` to get `key` and `currentHash`, then
write `hooks.state` with the trusted hash.

## Disable All Hook Enforcement

For the installer-managed user-level block:

```sh
~/.codex/skills/feature-challenge-workflow/scripts/enable-hooks.sh disable
```

For manual configuration, remove or comment out the hook sections from the
effective config.

For a temporary state-only disable, mark the workflow as cancelled:

```sh
mkdir -p .agents
OWNER_ID="host:codex-session"
FEATURE_ID="$(jq -r --arg owner "$OWNER_ID" '.activeByOwner[$owner] // .activeFeatureId' .agents/feature-challenges/index.json)"
jq '.status = "cancelled" | .stage = "cancelled"' \
  ".agents/feature-challenges/${FEATURE_ID}.json" \
  > /tmp/feature-challenge-cancelled.json
mv /tmp/feature-challenge-cancelled.json \
  ".agents/feature-challenges/${FEATURE_ID}.json"
```

This does not disable the hook handlers themselves; it only makes the bundled
scripts treat the current repository workflow as inactive.

## Concurrent Codex Sessions

The hook scripts support multiple Codex sessions in one repository.

- `index.json.activeByOwner` stores the active feature per Codex owner.
- `.agents/feature-challenges/index.lock` protects only short `index.json`
  read/write sections with `flock -n`. The lock is released when the hook shell
  process exits.
- `<featureId>.json.workClaim` is the long-lived ownership marker that records
  which Codex owns the current work on a feature. Claims expire after
  `FEATURE_CHALLENGE_CLAIM_TTL_SECONDS`, defaulting to 86400 seconds.
- A second Codex may work on another feature in the same repository.
- A second Codex must not edit the same feature while `workClaim.ownerId`
  belongs to another owner.

If a feature is claimed by another Codex, switch to another feature, wait, or
ask the user to hand over ownership explicitly.

## Disable Individual Hook Handlers

Codex stores user-controlled hook state under `hooks.state`. Hook keys include
the hook source path, event name, matcher-group index, and handler index.

Example shape:

```toml
[hooks.state."~/.codex/config.toml:pre_tool_use:0:0"]
enabled = false
```

Use `hooks/list` or the TUI hooks browser to get the exact key for the active
config layer. Positional indexes change if hook blocks are reordered.

## Trust Individual Hook Handlers

Unmanaged hooks run only when trusted. The trust state has this shape:

```toml
[hooks.state."~/.codex/config.toml:pre_tool_use:0:0"]
trusted_hash = "sha256:..."
```

Get the exact `trusted_hash` value from `hooks/list` as `currentHash`, or trust
the hook through the TUI hook review screen.

Managed hooks do not use user trust state.

## Skill Disablement

The skill itself is currently disabled via:

```toml
[[skills.config]]
path = "<SKILL_DIR>/SKILL.md"
enabled = false
```

Changing this controls skill discovery only. It does not enable or disable the
hook scripts.
