#!/usr/bin/env bash
set -euo pipefail

BEGIN_MARKER="# BEGIN feature-challenge-workflow hooks"
END_MARKER="# END feature-challenge-workflow hooks"
WRITE_TOOL_MATCHER='apply_patch|Write|Edit|MultiEdit|Bash|mcp__.*(create|update|delete|write|patch).*'

ACTION="enable"
TRUST_HOOKS=1
DRY_RUN=0

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SKILL_DIR="$(CDPATH='' cd -- "${SCRIPT_DIR}/.." && pwd -P)"
CONFIG_FILE="${CODEX_HOME:-${HOME}/.codex}/config.toml"

usage() {
  cat <<'EOF'
Usage:
  enable-hooks.sh [enable] [--config PATH] [--skill-dir PATH] [--no-trust] [--dry-run]
  enable-hooks.sh disable [--config PATH] [--dry-run]
  enable-hooks.sh status [--config PATH]

Commands:
  enable    Add Feature Challenge hooks and trusted hashes. This is the default.
  disable   Remove the managed Feature Challenge hook block.
  status    Print whether the managed block is present.

Options:
  --config PATH     Codex config file to edit. Default: $CODEX_HOME/config.toml or ~/.codex/config.toml.
  --skill-dir PATH  Feature Challenge skill directory. Default: parent of this script directory.
  --no-trust        Add hooks without hooks.state trusted_hash entries.
  --dry-run         Print the resulting config instead of writing it.
  -h, --help        Show this help.
EOF
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

require_tool() {
  command -v "$1" >/dev/null 2>&1 || die "required tool is missing: $1"
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      enable|disable|status)
        ACTION="$1"
        ;;
      --config)
        [ "$#" -ge 2 ] || die "--config requires a path"
        CONFIG_FILE="$2"
        shift
        ;;
      --skill-dir)
        [ "$#" -ge 2 ] || die "--skill-dir requires a path"
        SKILL_DIR="$2"
        shift
        ;;
      --no-trust)
        TRUST_HOOKS=0
        ;;
      --dry-run)
        DRY_RUN=1
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "unknown argument: $1"
        ;;
    esac
    shift
  done
}

real_dir_path() {
  local path
  path="$1"
  CDPATH='' cd -- "$path" && pwd -P
}

real_file_path() {
  local path dir base
  path="$1"
  dir="$(dirname -- "$path")"
  base="$(basename -- "$path")"
  printf '%s/%s\n' "$(real_dir_path "$dir")" "$base"
}

normalize_paths() {
  mkdir -p -- "$(dirname -- "$CONFIG_FILE")"
  [ -f "$CONFIG_FILE" ] || : >"$CONFIG_FILE"
  CONFIG_FILE="$(real_file_path "$CONFIG_FILE")"
  SKILL_DIR="$(real_dir_path "$SKILL_DIR")"
}

script_path() {
  printf '%s/scripts/%s\n' "$SKILL_DIR" "$1"
}

validate_skill_scripts() {
  local script
  for script in \
    user-prompt-submit.sh \
    pre-tool-use.sh \
    stop.sh \
    post-tool-use.sh
  do
    [ -x "$(script_path "$script")" ] || die "hook script is missing or not executable: $(script_path "$script")"
  done
}

strip_managed_block() {
  awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" '
    $0 == begin { skip = 1; next }
    $0 == end { skip = 0; next }
    !skip { print }
  ' "$1"
}

set_hooks_feature_true() {
  awk '
    BEGIN {
      in_features = 0
      seen_features = 0
      seen_hooks = 0
    }
    /^\[features\][[:space:]]*$/ {
      in_features = 1
      seen_features = 1
      print
      next
    }
    in_features && /^\[/ {
      if (!seen_hooks) {
        print "hooks = true"
        seen_hooks = 1
      }
      in_features = 0
    }
    in_features && /^[[:space:]]*hooks[[:space:]]*=/ {
      print "hooks = true"
      seen_hooks = 1
      next
    }
    { print }
    END {
      if (!seen_features) {
        print ""
        print "[features]"
        print "hooks = true"
      } else if (in_features && !seen_hooks) {
        print "hooks = true"
      }
    }
  ' "$1"
}

count_event_groups() {
  local file event
  file="$1"
  event="$2"
  grep -Ec "^\\[\\[hooks\\.${event}\\]\\][[:space:]]*$" "$file" || true
}

hook_hash() {
  local event_key matcher command timeout status json hash
  event_key="$1"
  matcher="$2"
  command="$3"
  timeout="$4"
  status="$5"

  if [ -n "$matcher" ]; then
    json="$(
      jq -cnS \
        --arg event_name "$event_key" \
        --arg matcher "$matcher" \
        --arg command "$command" \
        --arg status "$status" \
        --argjson timeout "$timeout" \
        '{event_name:$event_name, hooks:[{async:false, command:$command, statusMessage:$status, timeout:$timeout, type:"command"}], matcher:$matcher}'
    )"
  else
    json="$(
      jq -cnS \
        --arg event_name "$event_key" \
        --arg command "$command" \
        --arg status "$status" \
        --argjson timeout "$timeout" \
        '{event_name:$event_name, hooks:[{async:false, command:$command, statusMessage:$status, timeout:$timeout, type:"command"}]}'
    )"
  fi

  hash="$(printf '%s' "$json" | sha256sum | awk '{print $1}')"
  printf 'sha256:%s\n' "$hash"
}

append_trust_state() {
  local key hash
  key="$1"
  hash="$2"

  [ "$TRUST_HOOKS" -eq 1 ] || return 0

  cat <<EOF

[hooks.state."${key}"]
trusted_hash = "${hash}"
EOF
}

write_hook_block() {
  local base user_index pre_index stop_index post_index
  local user_cmd pre_cmd stop_cmd post_cmd
  local user_hash pre_hash stop_hash post_hash
  local user_key pre_key stop_key post_key

  base="$1"

  user_index="$(count_event_groups "$base" UserPromptSubmit)"
  pre_index="$(count_event_groups "$base" PreToolUse)"
  stop_index="$(count_event_groups "$base" Stop)"
  post_index="$(count_event_groups "$base" PostToolUse)"

  user_cmd="$(script_path user-prompt-submit.sh)"
  pre_cmd="$(script_path pre-tool-use.sh)"
  stop_cmd="$(script_path stop.sh)"
  post_cmd="$(script_path post-tool-use.sh)"

  user_hash="$(hook_hash user_prompt_submit "" "$user_cmd" 5 "routing feature challenge")"
  pre_hash="$(hook_hash pre_tool_use "$WRITE_TOOL_MATCHER" "$pre_cmd" 5 "checking feature challenge")"
  stop_hash="$(hook_hash stop "" "$stop_cmd" 5 "checking feature challenge completion")"
  post_hash="$(hook_hash post_tool_use "$WRITE_TOOL_MATCHER" "$post_cmd" 5 "checking feature challenge after tool use")"

  user_key="${CONFIG_FILE}:user_prompt_submit:${user_index}:0"
  pre_key="${CONFIG_FILE}:pre_tool_use:${pre_index}:0"
  stop_key="${CONFIG_FILE}:stop:${stop_index}:0"
  post_key="${CONFIG_FILE}:post_tool_use:${post_index}:0"

  cat <<EOF

${BEGIN_MARKER}
# Generated by ${SCRIPT_DIR}/enable-hooks.sh.

[[hooks.UserPromptSubmit]]

[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "${user_cmd}"
timeout = 5
statusMessage = "routing feature challenge"

[[hooks.PreToolUse]]
matcher = "${WRITE_TOOL_MATCHER}"

[[hooks.PreToolUse.hooks]]
type = "command"
command = "${pre_cmd}"
timeout = 5
statusMessage = "checking feature challenge"

[[hooks.Stop]]

[[hooks.Stop.hooks]]
type = "command"
command = "${stop_cmd}"
timeout = 5
statusMessage = "checking feature challenge completion"

[[hooks.PostToolUse]]
matcher = "${WRITE_TOOL_MATCHER}"

[[hooks.PostToolUse.hooks]]
type = "command"
command = "${post_cmd}"
timeout = 5
statusMessage = "checking feature challenge after tool use"
EOF

  append_trust_state "$user_key" "$user_hash"
  append_trust_state "$pre_key" "$pre_hash"
  append_trust_state "$stop_key" "$stop_hash"
  append_trust_state "$post_key" "$post_hash"

  cat <<EOF

${END_MARKER}
EOF
}

write_config() {
  local new_config backup
  new_config="$1"

  if [ "$DRY_RUN" -eq 1 ]; then
    cat -- "$new_config"
    return 0
  fi

  backup="${CONFIG_FILE}.bak.$(date +%Y%m%d%H%M%S)"
  cp -p -- "$CONFIG_FILE" "$backup"
  cat -- "$new_config" >"$CONFIG_FILE"
  printf 'updated %s\nbackup %s\n' "$CONFIG_FILE" "$backup"
}

enable_hooks() {
  local stripped with_feature final_config
  require_tool jq
  require_tool sha256sum
  require_tool awk
  validate_skill_scripts

  stripped="$(mktemp)"
  with_feature="$(mktemp)"
  final_config="$(mktemp)"
  trap 'rm -f -- "${stripped:-}" "${with_feature:-}" "${final_config:-}"' EXIT

  strip_managed_block >"$stripped" "$CONFIG_FILE"
  set_hooks_feature_true >"$with_feature" "$stripped"
  cat -- "$with_feature" >"$final_config"
  write_hook_block "$with_feature" >>"$final_config"
  write_config "$final_config"
}

disable_hooks() {
  local stripped
  require_tool awk

  stripped="$(mktemp)"
  trap 'rm -f -- "${stripped:-}"' EXIT

  strip_managed_block >"$stripped" "$CONFIG_FILE"
  write_config "$stripped"
}

status_hooks() {
  printf 'config: %s\n' "$CONFIG_FILE"
  if grep -Fqx "$BEGIN_MARKER" "$CONFIG_FILE"; then
    printf 'feature-challenge hooks: installed\n'
  else
    printf 'feature-challenge hooks: not installed\n'
  fi
  if awk '
    /^\[features\][[:space:]]*$/ { in_features = 1; next }
    in_features && /^\[/ { in_features = 0 }
    in_features && /^[[:space:]]*hooks[[:space:]]*=[[:space:]]*true[[:space:]]*$/ { found = 1 }
    END { exit found ? 0 : 1 }
  ' "$CONFIG_FILE"; then
    printf 'features.hooks: true\n'
  else
    printf 'features.hooks: not true\n'
  fi
}

parse_args "$@"
normalize_paths

case "$ACTION" in
  enable) enable_hooks ;;
  disable) disable_hooks ;;
  status) status_hooks ;;
  *) die "unsupported action: $ACTION" ;;
esac
