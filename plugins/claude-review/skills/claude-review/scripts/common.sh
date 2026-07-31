#!/bin/bash
# Common functions for the claude-review skill.

# shellcheck disable=SC2034
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

guard_recursion() {
    if [[ "${CLAUDE_REVIEWER:-}" == "1" ]]; then
        echo "ERROR: Recursion detected (CLAUDE_REVIEWER=1). Aborting." >&2
        exit 1
    fi
}

get_project_root() {
    git rev-parse --show-toplevel 2>/dev/null || {
        echo "ERROR: Not inside a git repository." >&2
        exit 1
    }
}

get_main_repo_root() {
    local git_common_dir
    git_common_dir="$(git rev-parse --git-common-dir 2>/dev/null)" || {
        echo "ERROR: Not inside a git repository." >&2
        exit 1
    }
    (cd "$git_common_dir/.." && pwd)
}

get_branch_slug() {
    local branch
    branch="$(git symbolic-ref --short HEAD 2>/dev/null)" \
        || branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" \
        || branch="detached"
    echo "$branch" | tr '/' '-'
}

get_review_root() {
    local root
    root="$(get_main_repo_root)"
    local review_root="$root/.claude-review"
    mkdir -p "$review_root"
    touch "$review_root/.gitkeep"
    echo "$review_root"
}

get_state_dir() {
    local review_root branch state_dir
    review_root="$(get_review_root)"
    branch="$(get_branch_slug)"
    state_dir="$review_root/$branch"
    mkdir -p "$state_dir/notes"
    touch "$state_dir/notes/.gitkeep"
    echo "$state_dir"
}

get_pid_file() {
    local state_dir
    state_dir="$(get_state_dir)"
    echo "$state_dir/claude.pid"
}

get_review_lock_file() {
    local state_dir
    state_dir="$(get_state_dir)"
    echo "$state_dir/review.lock"
}

get_review_lock_metadata_file() {
    local state_dir
    state_dir="$(get_state_dir)"
    echo "$state_dir/review.lock.json"
}

get_process_metadata_file() {
    local state_dir
    state_dir="$(get_state_dir)"
    echo "$state_dir/claude-process.json"
}

get_launcher_log_file() {
    local state_dir
    state_dir="$(get_state_dir)"
    echo "$state_dir/claude-launcher.log"
}

get_verdict_diagnostics_file() {
    local state_dir
    state_dir="$(get_state_dir)"
    echo "$state_dir/verdict-error.txt"
}

load_config() {
    local review_root config_file
    review_root="$(get_review_root)"
    config_file="$review_root/config.env"

    if [[ -f "$config_file" ]]; then
        # shellcheck disable=SC1090
        source "$config_file"
    fi

    CLAUDE_MODEL="${CLAUDE_MODEL:-}"
    CLAUDE_EFFORT="${CLAUDE_EFFORT:-high}"
    CLAUDE_MAX_ITERATIONS="${CLAUDE_MAX_ITERATIONS:-5}"
    CLAUDE_PERMISSION_MODE="${CLAUDE_PERMISSION_MODE:-default}"
    CLAUDE_ALLOWED_TOOLS="${CLAUDE_ALLOWED_TOOLS:-Read,Write,Glob,Grep,Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git show:*),Bash(rg:*),Bash(find:*),Bash(ls:*),Bash(pwd:*),Bash(sed:*),Bash(cat:*),Bash(wc:*)}"
    CLAUDE_REVIEWER_PROMPT="${CLAUDE_REVIEWER_PROMPT:-}"
    CLAUDE_PLAN_GUIDE="${CLAUDE_PLAN_GUIDE:-}"
    CLAUDE_CODE_GUIDE="${CLAUDE_CODE_GUIDE:-}"
}

read_state_field() {
    local field="$1"
    local state_dir state_file
    state_dir="$(get_state_dir)"
    state_file="$state_dir/state.json"

    if [[ ! -f "$state_file" ]]; then
        echo ""
        return
    fi

    grep -o "\"$field\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$state_file" \
        | head -1 \
        | sed 's/.*:[[:space:]]*"//' \
        | sed 's/"$//'
}

read_state_number() {
    local field="$1"
    local state_dir state_file val
    state_dir="$(get_state_dir)"
    state_file="$state_dir/state.json"

    if [[ ! -f "$state_file" ]]; then
        echo "0"
        return
    fi

    val=$(grep -o "\"$field\"[[:space:]]*:[[:space:]]*[0-9]*" "$state_file" \
        | head -1 \
        | sed 's/.*:[[:space:]]*//')
    echo "${val:-0}"
}

get_effective_session_id() {
    local sid="${CLAUDE_SESSION_ID:-}"
    if [[ -z "$sid" ]]; then
        sid="$(read_state_field "session_id")"
    fi
    echo "$sid"
}

json_escape() {
    local raw="$1"
    if command -v jq >/dev/null 2>&1; then
        jq -Rn --arg value "$raw" '$value'
    else
        printf '%s' "$raw" | sed 's/\\/\\\\/g; s/"/\\"/g; s/^/"/; s/$/"/'
    fi
}

write_state() {
    local session_id="$1"
    local phase_key="$2"
    local phase="$3"
    local iteration="$4"
    local max_iterations="$5"
    local status="$6"
    local timestamp="$7"
    local task_desc="$8"
    local state_dir
    state_dir="$(get_state_dir)"

    cat > "$state_dir/state.json" <<EOF_STATE
{
  "session_id": $(json_escape "$session_id"),
  "phase_key": $(json_escape "$phase_key"),
  "phase": $(json_escape "$phase"),
  "iteration": $iteration,
  "max_iterations": $max_iterations,
  "last_review_status": $(json_escape "$status"),
  "last_review_timestamp": $(json_escape "$timestamp"),
  "task_description": $(json_escape "$task_desc")
}
EOF_STATE
}

write_status() {
    local state_dir status_file task phase phase_key iteration max_iter review_status branch
    state_dir="$(get_state_dir)"
    status_file="$state_dir/STATUS.md"
    task="$(read_state_field "task_description")"
    phase_key="$(read_state_field "phase_key")"
    phase="$(read_state_field "phase")"
    iteration="$(read_state_number "iteration")"
    max_iter="$(read_state_number "max_iterations")"
    review_status="$(read_state_field "last_review_status")"
    branch="$(get_branch_slug)"

    {
        echo "# Active Claude Review"
        echo "- Task: ${task:-not set}"
        echo "- Branch: ${branch}"
        echo "- Phase key: ${phase_key:-not set}"
        echo "- Phase: ${phase:-initialized}"
        echo "- Iteration: ${iteration}/${max_iter}"
        echo "- Last status: ${review_status:-pending}"
        echo "- Journal: \`.claude-review/${branch}/notes/\`"
    } > "$status_file"
}

remove_status() {
    local state_dir
    state_dir="$(get_state_dir)"
    rm -f "$state_dir/STATUS.md"
}

write_claude_pid() {
    local pid="$1"
    local pid_file
    pid_file="$(get_pid_file)"
    printf '%s\n' "$pid" > "$pid_file"
}

read_claude_pid() {
    local pid_file
    pid_file="$(get_pid_file)"
    [[ -f "$pid_file" ]] || return 0
    tr -d '[:space:]' < "$pid_file"
}

clear_claude_pid() {
    local pid_file
    pid_file="$(get_pid_file)"
    rm -f "$pid_file"
}

describe_claude_pid_state() {
    local pid="$1"
    local comm args

    if [[ -z "$pid" ]]; then
        echo "pid_missing"
        return
    fi
    if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
        echo "pid_invalid"
        return
    fi

    comm="$(ps -p "$pid" -o comm= 2>/dev/null | tr -d '[:space:]')" || {
        echo "pid_not_found"
        return
    }
    if [[ -z "$comm" ]]; then
        echo "pid_not_found"
        return
    fi

    case "$comm" in
        claude|claude-*)
            echo "running"
            return
            ;;
    esac

    args="$(ps -p "$pid" -o args= 2>/dev/null)" || {
        echo "pid_not_found"
        return
    }
    if printf '%s\n' "$args" | grep -Eq '(^|[[:space:]])([^[:space:]]*/)?claude([[:space:]]|$)'; then
        echo "running"
    else
        echo "pid_not_claude"
    fi
}

describe_launcher_pid_state() {
    local pid="$1"
    local comm args

    if [[ -z "$pid" || "$pid" == "0" ]]; then
        echo "launcher_pid_missing"
        return
    fi
    if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
        echo "launcher_pid_invalid"
        return
    fi

    comm="$(ps -p "$pid" -o comm= 2>/dev/null | tr -d '[:space:]')" || {
        echo "launcher_pid_not_found"
        return
    }
    if [[ -z "$comm" ]]; then
        echo "launcher_pid_not_found"
        return
    fi

    args="$(ps -p "$pid" -o args= 2>/dev/null)" || {
        echo "launcher_pid_not_found"
        return
    }

    if printf '%s\n' "$args" | grep -Eq '(^|[[:space:]])([^[:space:]]*/)?claude-review\.sh([[:space:]]|$)'; then
        echo "running"
    else
        echo "launcher_pid_not_review"
    fi
}

write_process_metadata() {
    local session_id="$1"
    local phase="$2"
    local status="$3"
    local pid="$4"
    local last_pid="$5"
    local started_at="$6"
    local started_at_epoch="$7"
    local ended_at="$8"
    local exit_code="$9"
    local launcher_pid="${10}"
    local launcher_ppid="${11}"
    local launcher_pgid="${12}"
    local lifecycle_stage="${13}"
    local metadata_file
    metadata_file="$(get_process_metadata_file)"

    cat > "$metadata_file" <<EOF_METADATA
{
  "session_id": $(json_escape "$session_id"),
  "phase": $(json_escape "$phase"),
  "status": $(json_escape "$status"),
  "pid": $(json_escape "$pid"),
  "last_pid": $(json_escape "$last_pid"),
  "started_at": $(json_escape "$started_at"),
  "started_at_epoch": $started_at_epoch,
  "ended_at": $(json_escape "$ended_at"),
  "exit_code": $exit_code,
  "launcher_pid": $launcher_pid,
  "launcher_ppid": $launcher_ppid,
  "launcher_pgid": $launcher_pgid,
  "lifecycle_stage": $(json_escape "$lifecycle_stage")
}
EOF_METADATA
}

write_review_lock_metadata() {
    local pid="$1"
    local session_id="$2"
    local phase_key="$3"
    local command_name="$4"
    local started_at="$5"
    local metadata_file
    metadata_file="$(get_review_lock_metadata_file)"

    cat > "$metadata_file" <<EOF_METADATA
{
  "pid": $pid,
  "session_id": $(json_escape "$session_id"),
  "phase_key": $(json_escape "$phase_key"),
  "command": $(json_escape "$command_name"),
  "started_at": $(json_escape "$started_at")
}
EOF_METADATA
}

clear_review_lock_metadata() {
    local metadata_file
    metadata_file="$(get_review_lock_metadata_file)"
    rm -f "$metadata_file"
}

read_review_lock_metadata_field() {
    local field="$1"
    local metadata_file
    metadata_file="$(get_review_lock_metadata_file)"

    if [[ ! -f "$metadata_file" ]]; then
        echo ""
        return
    fi

    grep -o "\"$field\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$metadata_file" \
        | head -1 \
        | sed 's/.*:[[:space:]]*"//' \
        | sed 's/"$//'
}

read_review_lock_metadata_number() {
    local field="$1"
    local metadata_file val
    metadata_file="$(get_review_lock_metadata_file)"

    if [[ ! -f "$metadata_file" ]]; then
        echo "0"
        return
    fi

    val=$(grep -o "\"$field\"[[:space:]]*:[[:space:]]*-\?[0-9]*" "$metadata_file" \
        | head -1 \
        | sed 's/.*:[[:space:]]*//')
    echo "${val:-0}"
}

describe_review_lock_state() {
    local lock_file lock_fd
    lock_file="$(get_review_lock_file)"

    if [[ ! -e "$lock_file" ]]; then
        echo "unlocked"
        return
    fi

    exec {lock_fd}>"$lock_file"
    if flock -n "$lock_fd"; then
        flock -u "$lock_fd" 2>/dev/null || true
        eval "exec ${lock_fd}>&-"
        echo "unlocked"
    else
        eval "exec ${lock_fd}>&-"
        echo "locked"
    fi
}

read_process_metadata_field() {
    local field="$1"
    local metadata_file
    metadata_file="$(get_process_metadata_file)"

    if [[ ! -f "$metadata_file" ]]; then
        echo ""
        return
    fi

    grep -o "\"$field\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$metadata_file" \
        | head -1 \
        | sed 's/.*:[[:space:]]*"//' \
        | sed 's/"$//'
}

read_process_metadata_number() {
    local field="$1"
    local metadata_file val
    metadata_file="$(get_process_metadata_file)"

    if [[ ! -f "$metadata_file" ]]; then
        echo "0"
        return
    fi

    val=$(grep -o "\"$field\"[[:space:]]*:[[:space:]]*-\?[0-9]*" "$metadata_file" \
        | head -1 \
        | sed 's/.*:[[:space:]]*//')
    echo "${val:-0}"
}

write_launcher_log() {
    local message="$1"
    local launcher_log
    launcher_log="$(get_launcher_log_file)"
    printf '%s %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$message" >> "$launcher_log"
}

current_run_log_file() {
    local state_dir phase iteration
    state_dir="$(get_state_dir)"
    phase="$(read_state_field "phase")"
    iteration="$(read_state_number "iteration")"

    if [[ "$phase" == "initialized" || -z "$phase" || "$iteration" == "0" ]]; then
        echo "$state_dir/claude-init.log"
    else
        echo "$state_dir/claude-${phase}-${iteration}.log"
    fi
}

get_process_group_id() {
    local pid="$1"
    [[ -n "$pid" ]] || {
        echo "0"
        return
    }
    ps -p "$pid" -o pgid= 2>/dev/null | tr -d '[:space:]' || echo "0"
}

write_verdict_diagnostics() {
    local status="$1"
    local error_check="${2:-}"
    local diagnostics_file state_dir pid_file metadata_file verdict_file state_file launcher_log review_log lock_file
    local cwd branch repo_root main_repo_root pid phase phase_key iteration session_id pid_check process_status process_exit_code
    local lifecycle_stage launcher_pid launcher_ppid launcher_pgid launcher_check review_lock_check

    diagnostics_file="$(get_verdict_diagnostics_file)"
    state_dir="$(get_state_dir)"
    pid_file="$(get_pid_file)"
    lock_file="$(get_review_lock_file)"
    metadata_file="$(get_process_metadata_file)"
    verdict_file="$state_dir/verdict.txt"
    state_file="$state_dir/state.json"
    cwd="$(pwd)"
    branch="$(get_branch_slug)"
    repo_root="$(get_project_root 2>/dev/null || echo "")"
    main_repo_root="$(get_main_repo_root 2>/dev/null || echo "")"
    pid="$(read_claude_pid)"
    pid_check="$(describe_claude_pid_state "$pid")"
    process_status="$(read_process_metadata_field "status")"
    process_exit_code="$(read_process_metadata_number "exit_code")"
    lifecycle_stage="$(read_process_metadata_field "lifecycle_stage")"
    launcher_pid="$(read_process_metadata_number "launcher_pid")"
    launcher_ppid="$(read_process_metadata_number "launcher_ppid")"
    launcher_pgid="$(read_process_metadata_number "launcher_pgid")"
    launcher_check="$(describe_launcher_pid_state "$launcher_pid")"
    review_lock_check="$(describe_review_lock_state)"
    phase_key="$(read_state_field "phase_key")"
    phase="$(read_state_field "phase")"
    iteration="$(read_state_number "iteration")"
    session_id="$(get_effective_session_id)"

    launcher_log="$(get_launcher_log_file)"
    review_log="$(current_run_log_file)"

    {
        echo "# Verdict Diagnostics"
        echo "generated_at_utc: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
        echo "status: $status"
        echo "error_check: ${error_check:-unknown}"
        echo "cwd: $cwd"
        echo "branch: $branch"
        echo "repo_root: $repo_root"
        echo "main_repo_root: $main_repo_root"
        echo "state_dir: $state_dir"
        echo "session_id: $session_id"
        echo "phase_key: ${phase_key:-}"
        echo "phase: ${phase:-}"
        echo "iteration: $iteration"
        echo "review_lock_file: $lock_file"
        echo "review_lock_check: $review_lock_check"
        echo "pid_file: $pid_file"
        echo "pid: ${pid:-}"
        echo "pid_check: $pid_check"
        echo "pid_note: advisory only; sandboxed agents may see namespace-local PIDs"
        echo "process_status: ${process_status:-}"
        echo "process_exit_code: $process_exit_code"
        echo "lifecycle_stage: ${lifecycle_stage:-}"
        echo "launcher_pid: $launcher_pid"
        echo "launcher_ppid: $launcher_ppid"
        echo "launcher_pgid: $launcher_pgid"
        echo "launcher_check: $launcher_check"
        echo "launcher_pid_note: advisory only; sandboxed agents may see namespace-local PIDs"
        echo "verdict_file: $verdict_file"
        echo "state_file: $state_file"
        echo "process_metadata_file: $metadata_file"
        echo "launcher_log_file: $launcher_log"
        echo "review_log_file: $review_log"
        echo
        echo "## Files"
        for file in "$state_file" "$verdict_file" "$pid_file" "$metadata_file"; do
            echo "=== $file ==="
            if [[ -f "$file" ]]; then
                sed -n '1,200p' "$file"
            else
                echo "(missing)"
            fi
            echo
        done
        echo "## Process Check (Advisory Only)"
        if [[ -n "$pid" ]]; then
            ps -p "$pid" -o pid=,ppid=,comm=,args= 2>/dev/null || echo "(process not found)"
        else
            echo "(no pid recorded)"
        fi
        echo
        echo "## Launcher Check (Advisory Only)"
        if [[ "$launcher_pid" -gt 0 ]]; then
            ps -p "$launcher_pid" -o pid=,ppid=,comm=,args= 2>/dev/null || echo "(launcher not found)"
        else
            echo "(no launcher pid recorded)"
        fi
        echo
        echo "## Launcher Log Tail"
        echo "=== $launcher_log ==="
        if [[ -f "$launcher_log" ]]; then
            tail -n 80 "$launcher_log"
        else
            echo "(missing)"
        fi
        echo
        echo "## Review Log Tail"
        echo "=== $review_log ==="
        if [[ -f "$review_log" ]]; then
            tail -n 80 "$review_log"
        else
            echo "(missing)"
        fi
    } > "$diagnostics_file"
}

clear_verdict_diagnostics() {
    local diagnostics_file
    diagnostics_file="$(get_verdict_diagnostics_file)"
    rm -f "$diagnostics_file"
}

is_claude_pid_running() {
    local pid="$1"
    [[ "$(describe_claude_pid_state "$pid")" == "running" ]]
}

is_launcher_pid_running() {
    local pid="$1"
    [[ "$(describe_launcher_pid_state "$pid")" == "running" ]]
}

parse_verdict_file() {
    local file="$1"
    [[ -f "$file" ]] || return 0
    local raw
    raw="$(tr -d '[:space:]' < "$file")"
    case "$raw" in
        APPROVED|CHANGES_REQUESTED) echo "$raw" ;;
        *) : ;;
    esac
}

archive_previous_session() {
    local state_dir review_root has_artifacts timestamp archive_dir
    state_dir="$(get_state_dir)"
    review_root="$(get_review_root)"
    has_artifacts=false

    for file in "$state_dir"/state.json "$state_dir"/verdict.txt "$state_dir"/last_response.txt "$state_dir"/STATUS.md "$state_dir"/claude.pid "$state_dir"/claude-process.json "$state_dir"/claude-launcher.log "$state_dir"/verdict-error.txt; do
        if [[ -f "$file" ]]; then
            has_artifacts=true
            break
        fi
    done
    if compgen -G "$state_dir/notes/*.md" >/dev/null; then
        has_artifacts=true
    fi
    if compgen -G "$state_dir/claude-*.log" >/dev/null; then
        has_artifacts=true
    fi
    if compgen -G "$state_dir/claude-*.jsonl" >/dev/null; then
        has_artifacts=true
    fi

    if [[ "$has_artifacts" == "false" ]]; then
        return
    fi

    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    archive_dir="$review_root/archive/$timestamp"
    mkdir -p "$archive_dir/notes"
    generate_archive_summary "$state_dir" "$archive_dir" "$timestamp" || \
        echo "WARNING: Failed to generate archive summary." >&2

    for file in state.json verdict.txt last_response.txt STATUS.md claude.pid claude-process.json claude-launcher.log verdict-error.txt; do
        [[ -f "$state_dir/$file" ]] && mv "$state_dir/$file" "$archive_dir/"
    done
    mv "$state_dir"/claude-*.log "$archive_dir/" 2>/dev/null || true
    mv "$state_dir"/claude-*.jsonl "$archive_dir/" 2>/dev/null || true
    mv "$state_dir"/notes/*.md "$archive_dir/notes/" 2>/dev/null || true

    echo "Previous Claude review archived to: $archive_dir" >&2
}

generate_archive_summary() {
    local state_dir="$1"
    local archive_dir="$2"
    local archived_at="$3"
    local task_desc session_id final_verdict last_status plan_iters code_iters total_iters branch

    task_desc=""
    session_id=""
    final_verdict=""
    last_status=""
    if [[ -f "$state_dir/state.json" ]]; then
        task_desc="$(grep -o '"task_description"[[:space:]]*:[[:space:]]*"[^"]*"' "$state_dir/state.json" | head -1 | sed 's/.*:[[:space:]]*"//;s/"$//')"
        session_id="$(grep -o '"session_id"[[:space:]]*:[[:space:]]*"[^"]*"' "$state_dir/state.json" | head -1 | sed 's/.*:[[:space:]]*"//;s/"$//')"
        last_status="$(grep -o '"last_review_status"[[:space:]]*:[[:space:]]*"[^"]*"' "$state_dir/state.json" | head -1 | sed 's/.*:[[:space:]]*"//;s/"$//')"
    fi

    final_verdict="$(parse_verdict_file "$state_dir/verdict.txt")"
    if [[ -z "$final_verdict" ]]; then
        final_verdict="$last_status"
    fi

    plan_iters=$(find "$state_dir/notes" -maxdepth 1 -name 'plan-review-*.md' 2>/dev/null | wc -l)
    code_iters=$(find "$state_dir/notes" -maxdepth 1 -name 'code-review-*.md' 2>/dev/null | wc -l)
    total_iters=$((plan_iters + code_iters))
    branch="$(get_branch_slug)"

    cat > "$archive_dir/summary.json" <<EOF_SUMMARY
{
  "branch": $(json_escape "$branch"),
  "task_description": $(json_escape "$task_desc"),
  "session_id": $(json_escape "$session_id"),
  "plan_iterations": $plan_iters,
  "code_iterations": $code_iters,
  "total_iterations": $total_iters,
  "final_verdict": $(json_escape "$final_verdict"),
  "archived_at": $(json_escape "$archived_at")
}
EOF_SUMMARY
}

generate_uuid() {
    cat /proc/sys/kernel/random/uuid 2>/dev/null || uuidgen 2>/dev/null || {
        od -x /dev/urandom 2>/dev/null | head -1 | awk '{print $2$3"-"$4"-"$5"-"$6"-"$7$8$9}'
    }
}

check_claude_installed() {
    if ! command -v claude >/dev/null 2>&1; then
        echo "ERROR: 'claude' CLI not found in PATH." >&2
        exit 1
    fi
}

detect_network_preflight_failure() {
    local route_probe

    if ! command -v ip >/dev/null 2>&1; then
        return 1
    fi

    route_probe="$(LC_ALL=C ip route 2>&1 || true)"
    if ! printf '%s\n' "$route_probe" | grep -q "Operation not permitted"; then
        return 1
    fi

    echo "preflight: ip route failed: $route_probe"
    return 0
}

claude_base_flags() {
    local flags=()
    if [[ -n "$CLAUDE_MODEL" ]]; then
        flags+=("--model" "$CLAUDE_MODEL")
    fi
    if [[ -n "$CLAUDE_EFFORT" ]]; then
        flags+=("--effort" "$CLAUDE_EFFORT")
    fi
    if [[ -n "$CLAUDE_PERMISSION_MODE" ]]; then
        flags+=("--permission-mode" "$CLAUDE_PERMISSION_MODE")
    fi
    if [[ -n "$CLAUDE_ALLOWED_TOOLS" ]]; then
        flags+=("--allowedTools" "$CLAUDE_ALLOWED_TOOLS")
    fi
    printf '%s\n' "${flags[@]}"
}
