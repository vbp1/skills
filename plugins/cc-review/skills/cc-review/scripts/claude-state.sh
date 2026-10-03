#!/bin/bash
# State management for the claude-review skill.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_config

STATE_DIR="$(get_state_dir)"
STATE_FILE="$STATE_DIR/state.json"
STATE_WRITE_LOCK_FD=""

timestamp_to_epoch() {
    local ts="$1"
    [[ -n "$ts" ]] || {
        echo "0"
        return
    }
    date -u -d "$ts" +%s 2>/dev/null || echo "0"
}

cmd_show() {
    local effective_sid
    effective_sid="$(get_effective_session_id)"

    if [[ -f "$STATE_FILE" ]]; then
        sed "s|\"session_id\"[[:space:]]*:[[:space:]]*\"[^\"]*\"|\"session_id\": \"$effective_sid\"|" "$STATE_FILE"
    else
        echo "{\"session_id\":\"$effective_sid\",\"phase_key\":\"\",\"phase\":\"\",\"iteration\":0,\"max_iterations\":$CLAUDE_MAX_ITERATIONS,\"last_review_status\":\"\",\"last_review_timestamp\":\"\",\"task_description\":\"\"}"
    fi
}

acquire_state_write_lock() {
    local action_name="$1"
    local lock_file owner_pid owner_session_id owner_phase_key owner_command owner_started_at
    lock_file="$(get_review_lock_file)"
    exec {STATE_WRITE_LOCK_FD}>"$lock_file"
    if ! flock -n "$STATE_WRITE_LOCK_FD"; then
        owner_pid="$(read_review_lock_metadata_number "pid")"
        owner_session_id="$(read_review_lock_metadata_field "session_id")"
        owner_phase_key="$(read_review_lock_metadata_field "phase_key")"
        owner_command="$(read_review_lock_metadata_field "command")"
        owner_started_at="$(read_review_lock_metadata_field "started_at")"
        echo "ERROR: Cannot $action_name while another claude-review command is running for this branch state." >&2
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
}

release_state_write_lock() {
    if [[ -n "${STATE_WRITE_LOCK_FD:-}" ]]; then
        flock -u "$STATE_WRITE_LOCK_FD" 2>/dev/null || true
        eval "exec ${STATE_WRITE_LOCK_FD}>&-"
        STATE_WRITE_LOCK_FD=""
    fi
}

cmd_reset() {
    acquire_state_write_lock "reset state"
    if [[ "${1:-}" == "--full" ]]; then
        archive_previous_session
        clear_verdict_diagnostics
        clear_review_lock_metadata
        mkdir -p "$STATE_DIR/notes"
        touch "$STATE_DIR/notes/.gitkeep"
        release_state_write_lock
        echo "Full reset complete."
    else
        local session_id phase_key task_desc timestamp
        session_id="$(get_effective_session_id)"
        phase_key="$(read_state_field "phase_key")"
        task_desc="$(read_state_field "task_description")"
        timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
        write_state "$session_id" "$phase_key" "" 0 "$CLAUDE_MAX_ITERATIONS" "" "$timestamp" "$task_desc"
        write_status
        clear_claude_pid
        release_state_write_lock
        echo "Reset complete (session_id preserved)."
    fi
}

cmd_get() {
    local field="${1:?Usage: claude-state.sh get <field>}"
    if [[ "$field" == "session_id" ]]; then
        get_effective_session_id
        return
    fi
    if [[ "$field" == "verdict" ]]; then
        local verdict phase iteration session_id process_status process_exit_code process_lifecycle now_epoch state_status state_ts state_ts_epoch error_check review_lock_check
        verdict="$(parse_verdict_file "$STATE_DIR/verdict.txt")"
        if [[ -n "$verdict" ]]; then
            clear_verdict_diagnostics
            echo "$verdict"
            return
        fi

        phase="$(read_state_field "phase")"
        iteration="$(read_state_number "iteration")"
        session_id="$(get_effective_session_id)"
        state_status="$(read_state_field "last_review_status")"
        state_ts="$(read_state_field "last_review_timestamp")"
        state_ts_epoch="$(timestamp_to_epoch "$state_ts")"
        now_epoch="$(date -u +%s)"
        process_status="$(read_process_metadata_field "status")"
        process_exit_code="$(read_process_metadata_number "exit_code")"
        process_lifecycle="$(read_process_metadata_field "lifecycle_stage")"
        review_lock_check="$(describe_review_lock_state)"
        if [[ "$review_lock_check" == "locked" ]]; then
            clear_verdict_diagnostics
            if [[ "$phase" == "initializing" || "$process_status" == "starting" ]]; then
                echo "STARTING"
            elif [[ "$state_status" == "pending" && "$state_ts_epoch" -gt 0 && $((now_epoch - state_ts_epoch)) -le 15 ]]; then
                echo "STARTING"
            else
                echo "IN_PROGRESS"
            fi
            return
        fi

        if [[ -n "$session_id" && "$phase" == "initialized" && "$iteration" == "0" ]]; then
            clear_verdict_diagnostics
            echo "READY"
        else
            error_check=""
            if [[ "$process_status" == "finished" && "$process_lifecycle" == "network-preflight-failed" ]]; then
                error_check="network_unavailable"
            elif [[ "$phase" == "initializing" && "$state_status" == "ERROR" ]]; then
                error_check="init_failed"
            elif [[ "$process_status" == "finished" && "$process_exit_code" -ne 0 ]]; then
                error_check="review_process_failed"
            elif [[ "$process_status" == "finished" && "$process_exit_code" -eq 0 ]]; then
                error_check="command_finished_without_verdict"
            elif [[ "$phase" == "initializing" ]]; then
                error_check="init_not_running"
            elif [[ "$state_status" == "pending" ]]; then
                error_check="review_not_running"
            else
                error_check="not_ready_context"
            fi
            write_verdict_diagnostics "ERROR" "$error_check"
            echo "ERROR"
        fi
        return
    fi

    local val
    val="$(read_state_field "$field")"
    if [[ -z "$val" ]]; then
        val="$(read_state_number "$field")"
    fi
    echo "$val"
}

cmd_set() {
    acquire_state_write_lock "update state"
    local field="${1:?Usage: claude-state.sh set <field> <value>}"
    local value="${2:?Usage: claude-state.sh set <field> <value>}"
    local session_id phase_key phase iteration max_iterations status timestamp task_desc

    session_id="$(get_effective_session_id)"
    phase_key="$(read_state_field "phase_key")"
    phase="$(read_state_field "phase")"
    iteration="$(read_state_number "iteration")"
    max_iterations="$(read_state_number "max_iterations")"
    status="$(read_state_field "last_review_status")"
    task_desc="$(read_state_field "task_description")"
    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    [[ -z "$max_iterations" || "$max_iterations" == "0" ]] && max_iterations="$CLAUDE_MAX_ITERATIONS"

    case "$field" in
        session_id) session_id="$value" ;;
        phase_key) phase_key="$value" ;;
        phase) phase="$value" ;;
        last_review_status) status="$value" ;;
        task_description) task_desc="$value" ;;
        max_iterations) max_iterations="$value" ;;
        iteration) iteration="$value" ;;
        *)
            echo "ERROR: Unsupported field: $field" >&2
            exit 1
            ;;
    esac

    write_state "$session_id" "$phase_key" "$phase" "$iteration" "$max_iterations" "$status" "$timestamp" "$task_desc"
    write_status
    release_state_write_lock
    echo "Set $field = $value"
}

case "${1:-}" in
    show) cmd_show ;;
    dir) echo "$STATE_DIR" ;;
    reset) cmd_reset "${2:-}" ;;
    get) cmd_get "${2:-}" ;;
    set) cmd_set "${2:-}" "${3:-}" ;;
    *)
        echo "Usage: claude-state.sh {show|reset|dir|get|set} [args]"
        echo "  show              Current state (JSON)"
        echo "  dir               Print state directory path for current branch"
        echo "  reset             Reset iterations/phase (keep session_id)"
        echo "  reset --full      Full reset + archive notes"
        echo "  get <field>       Get a field (special: verdict)"
        echo "  set <field> <val> Set session_id, phase_key, phase, task_description, iteration, max_iterations, or last_review_status"
        exit 1
        ;;
esac
