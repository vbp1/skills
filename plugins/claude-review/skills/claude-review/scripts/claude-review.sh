#!/bin/bash
# Main claude-review script: init, plan, code.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

guard_recursion

COMMAND="${1:-}"
if [[ -z "$COMMAND" ]]; then
    echo "Usage: claude-review.sh <init|plan|code> <args> [--max-iter N]" >&2
    exit 1
fi
shift

DESCRIPTION=""
PLAN_FILE=""
MAX_ITER=""
PHASE_KEY=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --plan-file)
            PLAN_FILE="${2:-}"
            shift 2
            ;;
        --max-iter)
            MAX_ITER="${2:-}"
            shift 2
            ;;
        --phase-key)
            PHASE_KEY="${2:-}"
            shift 2
            ;;
        *)
            DESCRIPTION="$1"
            shift
            ;;
    esac
done

if [[ -z "$PHASE_KEY" ]]; then
    echo "ERROR: --phase-key is required. Use a stable workflow phase id such as 02-01." >&2
    exit 1
fi

if [[ "$COMMAND" == "plan" ]]; then
    if [[ -z "$PLAN_FILE" ]]; then
        echo "ERROR: --plan-file is required for plan review." >&2
        exit 1
    fi
    if [[ ! -f "$PLAN_FILE" ]]; then
        echo "ERROR: Plan file not found: $PLAN_FILE" >&2
        exit 1
    fi
    DESCRIPTION="$(cat "$PLAN_FILE")"
    if [[ -z "$DESCRIPTION" ]]; then
        echo "ERROR: Plan file is empty: $PLAN_FILE" >&2
        exit 1
    fi
elif [[ -z "$DESCRIPTION" ]]; then
    echo "ERROR: Description is required." >&2
    exit 1
fi

load_config
check_claude_installed

STATE_DIR="$(get_state_dir)"
MAX_ITERATIONS="${MAX_ITER:-$CLAUDE_MAX_ITERATIONS}"
SESSION_ID="$(get_effective_session_id)"
REVIEW_LOCK_FD=""

acquire_review_lock() {
    local command_name="$1"
    local lock_file lock_started_at
    lock_file="$(get_review_lock_file)"
    lock_started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    exec {REVIEW_LOCK_FD}>"$lock_file"
    if ! flock -n "$REVIEW_LOCK_FD"; then
        local owner_pid owner_session_id owner_phase_key owner_command owner_started_at
        owner_pid="$(read_review_lock_metadata_number "pid")"
        owner_session_id="$(read_review_lock_metadata_field "session_id")"
        owner_phase_key="$(read_review_lock_metadata_field "phase_key")"
        owner_command="$(read_review_lock_metadata_field "command")"
        owner_started_at="$(read_review_lock_metadata_field "started_at")"
        echo "ERROR: Another claude-review command is already running for this branch state." >&2
        echo "Lock file: $lock_file" >&2
        if [[ "$owner_pid" -gt 0 ]]; then
            echo "Owner PID: $owner_pid" >&2
            echo "Owner PID note: advisory only under sandboxed agents; PID may be namespace-local." >&2
        fi
        if [[ -n "$owner_command" ]]; then
            echo "Owner command: $owner_command" >&2
        fi
        if [[ -n "$owner_session_id" ]]; then
            echo "Owner session_id: $owner_session_id" >&2
        fi
        if [[ -n "$owner_phase_key" ]]; then
            echo "Owner phase_key: $owner_phase_key" >&2
        fi
        if [[ -n "$owner_started_at" ]]; then
            echo "Owner started_at: $owner_started_at" >&2
        fi
        echo "Wait for the current claude-review command to finish, then retry." >&2
        exit 1
    fi
    write_review_lock_metadata "${BASHPID:-$$}" "$SESSION_ID" "$PHASE_KEY" "$command_name" "$lock_started_at"
}

release_review_lock() {
    if [[ -n "${REVIEW_LOCK_FD:-}" ]]; then
        flock -u "$REVIEW_LOCK_FD" 2>/dev/null || true
        eval "exec ${REVIEW_LOCK_FD}>&-"
        REVIEW_LOCK_FD=""
    fi
    clear_review_lock_metadata
}

reviewer_role_prompt() {
    cat <<'ROLE'
You are a code reviewer for this project.
You will review plans and code changes submitted by another AI agent (Codex).
Your job is to find material defects, not to rubber-stamp Codex's work.

Focus areas:
- Code quality, readability, maintainability
- Bugs, edge cases, error handling
- Security vulnerabilities
- Architecture and design decisions
- Test coverage adequacy
- Silent failures, weak fallbacks, and hidden operational risks
- Type/API/domain invariants when changed
- Comment and documentation accuracy when changed

When reviewing:
- Inspect the repository yourself; you are in the same working directory
- Review only; do not edit files
- Do not run scripts from .claude-review/
- Do not inspect .claude-review/archive/
- Never ask for confirmation, permission, or clarification; provide the best review from available context
- Do not treat Codex's claims as verified unless you inspected the relevant files, diff, or command output yourself
- Write the final verdict to the exact verdict file path provided in each review prompt
ROLE
}

default_reviewer_prompt() {
    local task_desc="$1"
    local role
    role="$(reviewer_role_prompt)"
    cat <<PROMPT
$role

Task: $task_desc

This message sets up your reviewer role. Plan and code reviews will arrive as follow-up messages.
For now, confirm you are ready by responding with "Ready for review".
PROMPT
}

custom_init_prompt() {
    local custom_instructions="$1"
    local task_desc="$2"
    local role
    role="$(reviewer_role_prompt)"
    cat <<PROMPT
$role

$custom_instructions

Task: $task_desc
PROMPT
}

build_review_prompt() {
    local phase="$1"
    local description="$2"
    local skill_path phase_instructions guide guide_section review_tracks_section
    skill_path="$(cd "$SCRIPT_DIR/.." && pwd)"

    if [[ "$phase" == "plan" ]]; then
        phase_instructions="You are reviewing a proposed implementation plan.
The full plan text is provided above in 'Description from Codex'. Do not read plan files from disk; use the text above as the source of truth.

Focus areas:
- Correctness: does the approach solve the stated problem?
- Completeness: are requirements and edge cases covered?
- Architecture: are there risks or better alternatives?
- Scope: not too broad, not too narrow?
- Clarity: is the implementation strategy clear and unambiguous?
- Readiness: is the plan specific enough to start coding?"
        guide="$CLAUDE_PLAN_GUIDE"
        review_tracks_section=""
    else
        phase_instructions="You are reviewing code changes by Codex.

Important plan-context rule:
- A previously reviewed implementation plan may not exist.
- Do not assume there is an approved plan unless you can verify one from the current review context.
- If a reviewed plan exists, use it as one review input.
- If no reviewed plan exists, review against the actual changed-code scope, Codex's description, repository rules, surrounding implementation context, and tests.
- If the changed-code scope is unclear, empty, already committed, or different from Codex's description, call that out as a review limitation and decide whether it blocks approval.

Required initial scope checks:
- Inspect repository instructions such as CLAUDE.md, AGENTS.md, local style guides, and test guidelines when present.
- Determine the changed-code scope using git status and git diff. If no unstaged diff exists, inspect staged changes and recent commits or branch comparison as available.
- Keep findings focused on changed or requested code unless unchanged context is needed to prove a regression.
- Distinguish what you directly verified from what Codex merely claimed.

Merge-readiness rule:
- APPROVED means no high-confidence blocking issue remains in the verified scope.
- CHANGES_REQUESTED is required for real correctness, security, data-loss, hidden-failure, project-rule, or critical-test-gap issues.
- If a critical validation command is blocked or unavailable, do not claim it passed. Treat that as residual risk, and make it blocking when the unverified behavior is central to the change."
        review_tracks_section='
Multi-track review rubric:

1. code-reviewer
- Always run this track.
- Check explicit project rules, imports, framework conventions, language style, error handling, logging, tests, platform compatibility, naming, maintainability, and security.
- Identify real bugs: logic errors, null/undefined handling, races, leaks, injection/auth/data exposure, performance regressions, accessibility defects, and missing critical error handling.
- Filter aggressively: report only high-confidence actionable issues.

2. pr-test-analyzer
- Run when behavior changed, tests changed, or merge readiness is being evaluated.
- Review behavioral coverage rather than line coverage.
- Look for missing critical paths, negative cases, boundary conditions, error handling, concurrency/async behavior, and integration points.
- Identify brittle tests coupled to implementation details.
- Treat missing tests as blocking when they would catch data loss, security issues, system failures, important user-facing regressions, or central business behavior.

3. silent-failure-hunter
- Run when error handling, fallbacks, optional/null handling, retries, logging, external IO, persistence, or process control changed.
- Look for empty or broad catch blocks, swallowed errors, generic user messages, logging-only paths, hidden fallback behavior, mock/stub fallbacks in production code, retry exhaustion without actionable feedback, and default values that mask failures.
- For each issue, explain the hidden error, user impact, and concrete fix.

4. comment-analyzer
- Run when comments, docs, TODOs, examples, or behavioral claims changed.
- Verify factual accuracy against implementation.
- Flag comments that merely restate code, mislead future maintainers, reference temporary states, or describe behavior the code does not implement.

5. type-design-analyzer
- Run when types, schemas, models, DTOs, APIs, persistence shapes, or domain state changed.
- Identify implicit and explicit invariants.
- Check encapsulation, invalid states, constructor or mutation validation, exposed mutable internals, and documentation-only invariants.
- Prefer pragmatic improvements that match the project and avoid unnecessary complexity.

Required review output:
- Start with blocking findings, if any, grouped by severity and labeled with the track name.
- Include file paths and line numbers when available.
- If there are no blocking findings, say that explicitly.
- Include "Tracks run" and "Validation gaps" sections.
- Mention non-blocking observations separately from blocking findings.
- Do not let positive observations replace the negative review tracks.'
        guide="$CLAUDE_CODE_GUIDE"
    fi

    guide_section=""
    if [[ -n "$guide" ]]; then
        guide_section="
Additional review guidance from project maintainer:
$guide
"
    fi

    cat <<PROMPT
You are reviewing work by Codex on this project.
Phase: $phase

Description from Codex:
$description

$phase_instructions
$review_tracks_section
$guide_section
General instructions:
- If acceptable, respond with actionable notes
- If changes are needed, provide specific actionable feedback
- You can inspect the code yourself; you are in the same directory
- Review only; do not edit files
- Exception: you must write the final verdict to $STATE_DIR/verdict.txt
- Write exactly one word to that file: APPROVED or CHANGES_REQUESTED
- The verdict file is the only authoritative verdict source; do not rely on response text for status
- The claude-review skill is at: $skill_path
PROMPT
}

save_note() {
    local phase="$1"
    local iteration="$2"
    local content="$3"
    local note_file="$STATE_DIR/notes/${phase}-review-${iteration}.md"
    {
        echo "# ${phase^} Review #${iteration}"
        echo "Date: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
        echo ""
        echo "$content"
    } > "$note_file"
}

update_state() {
    local phase="$1"
    local iteration="$2"
    local status="$3"
    local timestamp phase_key task_desc
    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    phase_key="$(read_state_field "phase_key")"
    task_desc="$(read_state_field "task_description")"
    write_state "$SESSION_ID" "$phase_key" "$phase" "$iteration" "$MAX_ITERATIONS" "$status" "$timestamp" "$task_desc"
}

print_result() {
    local phase="$1"
    local iteration="$2"
    local max="$3"
    local session="$4"
    local response="$5"
    local status="$6"

    echo ""
    echo "=== CLAUDE REVIEW ==="
    echo "Phase: $phase"
    echo "Iteration: ${iteration}/${max}"
    echo "Session: $session"
    echo ""
    echo "$response"
    echo ""
    echo "=== END REVIEW ==="
    echo "Status: $status"
}

claude_review_cleanup_run() {
    local exit_code="${1:-1}"
    local ended_at

    if [[ "${CLAUDE_REVIEW_RUN_ACTIVE:-0}" != "1" ]]; then
        return
    fi

    write_launcher_log "cleanup exit_code=$exit_code child_pid=${CLAUDE_REVIEW_CHILD_PID:-}"
    clear_claude_pid
    ended_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    write_process_metadata \
        "$SESSION_ID" \
        "${CLAUDE_REVIEW_RUN_PHASE:-}" \
        "finished" \
        "" \
        "${CLAUDE_REVIEW_CHILD_PID:-}" \
        "${CLAUDE_REVIEW_RUN_STARTED_AT:-}" \
        "${CLAUDE_REVIEW_RUN_STARTED_AT_EPOCH:-0}" \
        "$ended_at" \
        "$exit_code" \
        "${CLAUDE_REVIEW_LAUNCHER_PID:-0}" \
        "${CLAUDE_REVIEW_LAUNCHER_PPID:-0}" \
        "${CLAUDE_REVIEW_LAUNCHER_PGID:-0}" \
        "finished"
    CLAUDE_REVIEW_RUN_ACTIVE=0
}

claude_review_handle_signal() {
    local signal="$1"
    local exit_code="$2"
    write_launcher_log "received signal=$signal exit_code=$exit_code"
    claude_review_cleanup_run "$exit_code"
    trap - "$signal"
    kill -s "$signal" "$$"
}

process_stream_json() {
    local raw_file="$1"
    local log_file="$2"
    local output_file="$3"

    # shellcheck disable=SC2016
    node -e '
const fs = require("fs");
const readline = require("readline");

const [rawFile, logFile, outputFile] = process.argv.slice(1);
const rawStream = fs.createWriteStream(rawFile, { flags: "a" });
const logStream = fs.createWriteStream(logFile, { flags: "a" });
const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

const blockKinds = new Map();
const openBlocks = new Map();

function closeOpenBlocks() {
  if (openBlocks.size === 0) {
    return;
  }
  for (const key of openBlocks.keys()) {
    logStream.write("\n");
    openBlocks.delete(key);
  }
}

function logLine(line) {
  closeOpenBlocks();
  logStream.write(`${line}\n`);
}

function writeChunk(key, prefix, text) {
  if (!text) {
    return;
  }
  if (!openBlocks.has(key)) {
    logStream.write(prefix);
    openBlocks.set(key, prefix);
  }
  logStream.write(text);
}

function writeLastResponse(text) {
  if (!text) {
    return;
  }
  fs.writeFileSync(outputFile, text.endsWith("\n") ? text : `${text}\n`);
}

function extractAssistantText(message) {
  if (!message || !Array.isArray(message.content)) {
    return "";
  }
  return message.content
    .filter(block => block && block.type === "text")
    .map(block => block.text || "")
    .join("");
}

rl.on("line", line => {
  rawStream.write(`${line}\n`);

  let parsed;
  try {
    parsed = JSON.parse(line);
  } catch {
    logLine(`[raw] ${line}`);
    return;
  }

  switch (parsed.type) {
    case "system": {
      switch (parsed.subtype) {
        case "init":
          logLine(
            `session init: model=${parsed.model || "unknown"} session=${parsed.session_id || "unknown"}`
          );
          break;
        case "status":
          logLine(`status: ${parsed.status || "unknown"}`);
          break;
        case "api_retry":
          logLine(
            `api retry: ${parsed.attempt || 0}/${parsed.max_retries || 0} delay=${parsed.retry_delay_ms || 0}ms error=${parsed.error || "unknown"}`
          );
          break;
        case "hook_started":
          logLine(`hook started: ${parsed.hook_name || "unknown"} (${parsed.hook_event || "unknown"})`);
          break;
        case "hook_progress":
          if (parsed.stdout) {
            logLine(`hook stdout: ${String(parsed.stdout).trimEnd()}`);
          }
          if (parsed.stderr) {
            logLine(`hook stderr: ${String(parsed.stderr).trimEnd()}`);
          }
          break;
        case "hook_response":
          logLine(
            `hook response: ${parsed.hook_name || "unknown"} exit=${parsed.exit_code ?? "?"} outcome=${parsed.outcome || "unknown"}`
          );
          if (parsed.stdout) {
            logLine(`hook stdout: ${String(parsed.stdout).trimEnd()}`);
          }
          if (parsed.stderr) {
            logLine(`hook stderr: ${String(parsed.stderr).trimEnd()}`);
          }
          break;
        default:
          logLine(`system: ${parsed.subtype || "unknown"}`);
          break;
      }
      break;
    }
    case "rate_limit_event":
      logLine(`rate limit: ${parsed.rate_limit_info?.status || "unknown"}`);
      break;
    case "stream_event": {
      const event = parsed.event || {};
      switch (event.type) {
        case "message_start":
          logLine(
            `assistant start: model=${event.message?.model || "unknown"} ttft_ms=${parsed.ttft_ms ?? "unknown"}`
          );
          break;
        case "content_block_start":
          blockKinds.set(event.index, event.content_block?.type || "");
          break;
        case "content_block_delta": {
          const kind = blockKinds.get(event.index) || "";
          if (event.delta?.type === "text_delta" && kind === "text") {
            writeChunk(`text:${event.index}`, "assistant> ", event.delta.text || "");
          } else if (
            event.delta?.type === "thinking_delta" &&
            kind === "thinking"
          ) {
            writeChunk(`thinking:${event.index}`, "thinking> ", event.delta.thinking || "");
          } else if (
            event.delta?.type === "input_json_delta" &&
            (kind === "tool_use" || kind === "server_tool_use")
          ) {
            writeChunk(`tool:${event.index}`, "tool input> ", event.delta.partial_json || "");
          }
          break;
        }
        case "content_block_stop":
          closeOpenBlocks();
          break;
        case "message_delta":
          if (event.delta?.stop_reason) {
            logLine(`assistant stop: ${event.delta.stop_reason}`);
          }
          break;
        case "message_stop":
          closeOpenBlocks();
          break;
        default:
          break;
      }
      break;
    }
    case "assistant": {
      const text = extractAssistantText(parsed.message);
      if (text) {
        writeLastResponse(text);
      }
      break;
    }
    case "result":
      if (typeof parsed.result === "string" && parsed.result.length > 0) {
        writeLastResponse(parsed.result);
      }
      logLine(`result: ${parsed.subtype || "unknown"}`);
      break;
    default:
      break;
  }
});

rl.on("close", () => {
  closeOpenBlocks();
  rawStream.end();
  logStream.end();
});
' "$raw_file" "$log_file" "$output_file"
}

run_claude() {
    local run_phase="$1"
    shift
    local prompt="$1"
    shift
    local output_file="$1"
    shift
    local log_file="$1"
    shift
    local raw_file="$1"
    shift
    local base_flags=()
    mapfile -t base_flags < <(claude_base_flags)

    : > "$output_file"
    : > "$log_file"
    : > "$raw_file"
    clear_claude_pid
    local started_at started_at_epoch
    started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    started_at_epoch="$(date -u +%s)"

    if detect_network_preflight_failure > >(tee -a "$log_file" >&2); then
        local ended_at
        ended_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
        write_launcher_log "network preflight failed phase=$run_phase"
        write_process_metadata "$SESSION_ID" "$run_phase" "finished" "" "" "$started_at" "$started_at_epoch" "$ended_at" 125 0 0 0 "network-preflight-failed"
        echo "ERROR: No network access to Claude API detected." >&2
        echo "Run claude-review outside a network-restricted sandbox or enable network access." >&2
        return 125
    fi

    CLAUDE_REVIEW_LAUNCHER_PID="${BASHPID:-$$}"
    CLAUDE_REVIEW_LAUNCHER_PPID="${PPID:-0}"
    CLAUDE_REVIEW_LAUNCHER_PGID="$(get_process_group_id "${CLAUDE_REVIEW_LAUNCHER_PID}")"
    write_launcher_log "run start phase=$run_phase launcher_pid=$CLAUDE_REVIEW_LAUNCHER_PID launcher_ppid=$CLAUDE_REVIEW_LAUNCHER_PPID launcher_pgid=$CLAUDE_REVIEW_LAUNCHER_PGID"
    write_process_metadata "$SESSION_ID" "$run_phase" "starting" "" "" "$started_at" "$started_at_epoch" "" -1 "$CLAUDE_REVIEW_LAUNCHER_PID" "$CLAUDE_REVIEW_LAUNCHER_PPID" "$CLAUDE_REVIEW_LAUNCHER_PGID" "pre-coproc"
    CLAUDE_REVIEW_RUN_ACTIVE=1
    CLAUDE_REVIEW_RUN_PHASE="$run_phase"
    CLAUDE_REVIEW_RUN_STARTED_AT="$started_at"
    CLAUDE_REVIEW_RUN_STARTED_AT_EPOCH="$started_at_epoch"
    CLAUDE_REVIEW_CHILD_PID=""
    trap 'claude_review_cleanup_run $?' EXIT
    trap 'claude_review_handle_signal INT 130' INT
    trap 'claude_review_handle_signal TERM 143' TERM

    local claude_pid claude_stream_fd claude_status=0 parser_status=0 final_exit_code=0 ended_at

    coproc CLAUDE_STREAM {
        CLAUDE_REVIEWER=1 exec claude -p \
            "${base_flags[@]}" \
            --verbose \
            --output-format stream-json \
            --include-partial-messages \
            "$@" \
            "$prompt" \
            < /dev/null \
            2> >(tee -a "$log_file" >&2)
    }
    write_launcher_log "coproc created pid=${CLAUDE_STREAM_PID:-}"

    claude_pid="$CLAUDE_STREAM_PID"
    claude_stream_fd="${CLAUDE_STREAM[0]-}"
    if [[ -z "$claude_pid" || -z "$claude_stream_fd" ]]; then
        write_launcher_log "coproc startup failed pid=${claude_pid:-} fd=${claude_stream_fd:-missing}"
        echo "ERROR: Failed to start Claude coprocess." >> "$log_file"
        claude_review_cleanup_run 1
        trap - EXIT INT TERM
        return 1
    fi
    CLAUDE_REVIEW_CHILD_PID="$claude_pid"
    write_claude_pid "$claude_pid"
    write_launcher_log "child running pid=$claude_pid fd=$claude_stream_fd"
    write_process_metadata "$SESSION_ID" "$run_phase" "running" "$claude_pid" "$claude_pid" "$started_at" "$started_at_epoch" "" -1 "$CLAUDE_REVIEW_LAUNCHER_PID" "$CLAUDE_REVIEW_LAUNCHER_PPID" "$CLAUDE_REVIEW_LAUNCHER_PGID" "stream-open"

    write_launcher_log "process_stream_json start"
    process_stream_json "$raw_file" "$log_file" "$output_file" <&"$claude_stream_fd" || parser_status=$?
    write_launcher_log "process_stream_json done parser_status=$parser_status"
    write_process_metadata "$SESSION_ID" "$run_phase" "running" "$claude_pid" "$claude_pid" "$started_at" "$started_at_epoch" "" -1 "$CLAUDE_REVIEW_LAUNCHER_PID" "$CLAUDE_REVIEW_LAUNCHER_PPID" "$CLAUDE_REVIEW_LAUNCHER_PGID" "waiting-for-child"
    write_launcher_log "wait start child_pid=$claude_pid"
    wait "$claude_pid" || claude_status=$?
    write_launcher_log "wait done child_pid=$claude_pid claude_status=$claude_status"

    if [[ $claude_status -ne 0 ]]; then
        final_exit_code=$claude_status
    elif [[ $parser_status -ne 0 ]]; then
        final_exit_code=$parser_status
    fi
    claude_review_cleanup_run "$final_exit_code"
    trap - EXIT INT TERM
    return "$final_exit_code"
}

cmd_init() {
    local task_desc="$DESCRIPTION"
    local prompt output_file log_file raw_file timestamp

    SESSION_ID="$(generate_uuid)"
    acquire_review_lock "init"
    archive_previous_session
    rm -f "$STATE_DIR/verdict.txt"

    if [[ -n "${CLAUDE_SESSION_ID:-}" ]]; then
        release_review_lock
        echo "ERROR: CLAUDE_SESSION_ID is set in .claude-review/config.env or the environment: $CLAUDE_SESSION_ID" >&2
        echo "Refusing to create a new session because config.env takes precedence over state.json." >&2
        echo "Remove or update CLAUDE_SESSION_ID, or use claude-state.sh set session_id <uuid> to reuse an existing session." >&2
        exit 1
    fi

    if [[ -n "$CLAUDE_REVIEWER_PROMPT" ]]; then
        prompt="$(custom_init_prompt "$CLAUDE_REVIEWER_PROMPT" "$task_desc")"
    else
        prompt="$(default_reviewer_prompt "$task_desc")"
    fi

    output_file="$STATE_DIR/last_response.txt"
    log_file="$STATE_DIR/claude-init.log"
    raw_file="$STATE_DIR/claude-init.jsonl"
    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    write_state "$SESSION_ID" "$PHASE_KEY" "initializing" 0 "$MAX_ITERATIONS" "pending" "$timestamp" "$task_desc"
    write_status

    echo "Creating Claude review session..." >&2
    printf '\033[1;33m>>> Monitor: tail -f %s\033[0m\n' "$log_file" >&2

    local exit_code=0
    run_claude "init" "$prompt" "$output_file" "$log_file" "$raw_file" --session-id "$SESSION_ID" || exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
        write_state "$SESSION_ID" "$PHASE_KEY" "initializing" 0 "$MAX_ITERATIONS" "ERROR" "$timestamp" "$task_desc"
        write_status
        release_review_lock
        echo "ERROR: Failed to create Claude session." >&2
        cat "$log_file" >&2
        exit 1
    fi

    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    write_state "$SESSION_ID" "$PHASE_KEY" "initialized" 0 "$MAX_ITERATIONS" "" "$timestamp" "$task_desc"
    write_status
    release_review_lock
    echo "Session created: $SESSION_ID"
}

cmd_review() {
    local phase="$1"
    local previous_phase stored_phase_key current_iteration next_iteration prompt output_file log_file raw_file output status task_desc timestamp starting_at starting_at_epoch

    acquire_review_lock "$phase"

    if [[ -z "$SESSION_ID" ]]; then
        release_review_lock
        echo ""
        echo "=== CLAUDE REVIEW ==="
        echo "Phase: $phase"
        echo ""
        echo "No active Claude session found."
        echo ""
        echo "=== END REVIEW ==="
        echo "Status: NO_SESSION"
        exit 3
    fi

    stored_phase_key="$(read_state_field "phase_key")"
    if [[ -z "$stored_phase_key" ]]; then
        release_review_lock
        echo "ERROR: Active Claude review session is missing phase_key metadata." >&2
        echo "Run a new init for this work phase: bash $SCRIPT_DIR/claude-review.sh init --phase-key \"$PHASE_KEY\" \"...\"" >&2
        exit 1
    fi
    if [[ "$stored_phase_key" != "$PHASE_KEY" ]]; then
        release_review_lock
        echo "ERROR: phase_key mismatch for active Claude review session." >&2
        echo "Active session phase_key: $stored_phase_key" >&2
        echo "Requested phase_key: $PHASE_KEY" >&2
        echo "Start a new init for each new work phase in the same branch." >&2
        exit 1
    fi

    previous_phase="$(read_state_field "phase")"
    current_iteration="$(read_state_number "iteration")"
    if [[ "$current_iteration" == "0" && "$previous_phase" != "initialized" ]]; then
        release_review_lock
        echo "ERROR: Active Claude review session is not initialized yet." >&2
        echo "Current phase: ${previous_phase:-unknown}" >&2
        echo "Wait for init to finish successfully, or rerun init if it failed." >&2
        exit 1
    fi
    if [[ -n "$previous_phase" && "$previous_phase" != "$phase" ]]; then
        task_desc="${DESCRIPTION:-$(read_state_field "task_description")}"
        write_state "$SESSION_ID" "$PHASE_KEY" "$phase" 0 "$MAX_ITERATIONS" "pending" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$task_desc"
        echo "Phase changed ($previous_phase -> $phase), iteration counter reset." >&2
    fi

    next_iteration=$((current_iteration + 1))

    if [[ $next_iteration -gt $MAX_ITERATIONS ]]; then
        release_review_lock
        echo ""
        echo "=== CLAUDE REVIEW ==="
        echo "Phase: $phase"
        echo "Iteration: ${next_iteration}/${MAX_ITERATIONS}"
        echo "Session: $SESSION_ID"
        echo ""
        echo "Maximum iterations ($MAX_ITERATIONS) reached."
        echo "Review notes are in: $STATE_DIR/notes/"
        echo ""
        echo "=== END REVIEW ==="
        echo "Status: ESCALATE"
        exit 2
    fi

    if [[ "$phase" == "plan" && -n "$PLAN_FILE" ]]; then
        cp "$PLAN_FILE" "$STATE_DIR/plan.md"
        echo "Plan saved to: $STATE_DIR/plan.md" >&2
    fi

    prompt="$(build_review_prompt "$phase" "$DESCRIPTION")"
    rm -f "$STATE_DIR/verdict.txt"

    task_desc="${DESCRIPTION:-$(read_state_field "task_description")}"
    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    starting_at="$timestamp"
    starting_at_epoch="$(date -u +%s)"
    clear_claude_pid
    write_process_metadata "$SESSION_ID" "$phase" "starting" "" "" "$starting_at" "$starting_at_epoch" "" -1 0 0 0 "queued"
    write_launcher_log "review queued phase=$phase iteration=$next_iteration phase_key=$PHASE_KEY"
    write_state "$SESSION_ID" "$PHASE_KEY" "$phase" "$next_iteration" "$MAX_ITERATIONS" "pending" "$timestamp" "$task_desc"
    write_status

    output_file="$STATE_DIR/last_response.txt"
    log_file="$STATE_DIR/claude-${phase}-${next_iteration}.log"
    raw_file="$STATE_DIR/claude-${phase}-${next_iteration}.jsonl"

    echo "Sending $phase for Claude review (iteration ${next_iteration}/${MAX_ITERATIONS})..." >&2
    printf '\033[1;33m>>> Monitor: tail -f %s\033[0m\n' "$log_file" >&2

    local exit_code=0
    run_claude "$phase" "$prompt" "$output_file" "$log_file" "$raw_file" --resume "$SESSION_ID" || exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        echo "ERROR: Claude review failed (exit $exit_code)." >&2
        cat "$log_file" >&2
        update_state "$phase" "$next_iteration" "ERROR"
        write_status
        release_review_lock
        exit 1
    fi

    output="$(cat "$output_file" 2>/dev/null || echo "")"
    status="$(parse_verdict_file "$STATE_DIR/verdict.txt")"
    if [[ "$status" != "APPROVED" && "$status" != "CHANGES_REQUESTED" ]]; then
        save_note "$phase" "$next_iteration" "$output"
        update_state "$phase" "$next_iteration" "ERROR"
        write_status
        release_review_lock
        echo "ERROR: Claude did not write a valid verdict to $STATE_DIR/verdict.txt." >&2
        echo "Expected exactly one word: APPROVED or CHANGES_REQUESTED." >&2
        exit 1
    fi

    save_note "$phase" "$next_iteration" "$output"
    update_state "$phase" "$next_iteration" "$status"

    if [[ "$phase" == "code" && "$status" == "APPROVED" ]]; then
        remove_status
    else
        write_status
    fi

    release_review_lock
    print_result "$phase" "$next_iteration" "$MAX_ITERATIONS" "$SESSION_ID" "$output" "$status"
}

case "$COMMAND" in
    init) cmd_init ;;
    plan) cmd_review "plan" ;;
    code) cmd_review "code" ;;
    *)
        echo "Usage: claude-review.sh <init|plan|code> <args> [--max-iter N]" >&2
        echo "  init --phase-key <phase-id> \"task\""
        echo "  plan --phase-key <phase-id> --plan-file <path>"
        echo "  code --phase-key <phase-id> \"description\""
        exit 1
        ;;
esac
