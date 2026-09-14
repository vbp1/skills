#!/usr/bin/env bash
# Bind this task's cross-agent review state to the branch the task runs on.
#
# The codex-review plugin keeps its rounds, notes and verdict under
# <main repo root>/.codex-review/<branch with / turned into ->. The path is built from
# whatever branch is checked out at the moment of the call, so a branch created,
# renamed or moved to a worktree part-way through a task leaves the earlier rounds in a
# directory nothing reads again, and the base branch doubles as a shared bin where the
# next task overwrites the previous one. The plugin knows nothing about tasks; the
# caller holds the binding, and this is the caller's side of it.
#
# It marks the task's state directory with the task id (`taskflow-task`), carries that
# directory over when the branch changes, and moves another task's leftovers out of the
# way into .codex-review/archive/ before a round can mix into them.
#
# Run it before the first review round of a task and again at the start of the code
# phase, from inside the task's working copy.
set -euo pipefail

SELF=$(basename "$0")
TASK=
REPO=
DRY=0

usage() {
  cat <<'EOF'
codex-state-bind.sh — bind this task's cross-agent review state to its branch

USAGE
  codex-state-bind.sh --task NNN-slug [--repo DIR] [--dry-run]
  codex-state-bind.sh --help

WHAT IT DOES
  Reads the branch checked out in --repo (default: the working copy you are in) and
  makes .codex-review/<branch> the state directory of this task:

    - the task's state directory is found by its `taskflow-task` marker and moved to
      the current branch's name when the branch has changed;
    - a directory already standing there that belongs to another task, or carries no
      marker, is moved to .codex-review/archive/<name>.<timestamp>/;
    - the marker is written, so the next call finds the directory again.

  Everything is checked before anything is moved. Nothing is deleted.

OPTIONS
  --task NNN-slug   the task this state belongs to; the id used in todos/NNN-slug.md
  --repo DIR        a path inside the working copy (default: the current directory)
  --dry-run         print what would be done and change nothing
  -h, --help        this text

OUTPUT
  One line per action, and a final line naming the state directory in use.

EXIT CODES
  0  the state directory is bound to this task
  1  bad usage, or not inside a git repository
  2  refused: more than one directory claims this task — name the one to keep by
     removing the marker from the others
EOF
}

die() { echo "$SELF: $*" >&2; exit "${2:-1}"; }
need() { [ -n "${2:-}" ] || die "$1 requires a value"; }

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0;;
    --task) need "$1" "${2:-}"; TASK=$2; shift 2;;
    --repo) need "$1" "${2:-}"; REPO=$2; shift 2;;
    --dry-run) DRY=1; shift;;
    *) die "unknown option: $1 (see --help)";;
  esac
done

[ -n "$TASK" ] || die "--task is required (see --help)"
case "$TASK" in
  */*|.|..|"") die "--task must be a task id such as 114-export-csv, got: $TASK";;
esac

cd "${REPO:-.}" 2>/dev/null || die "no such directory: $REPO"
git rev-parse --git-common-dir >/dev/null 2>&1 || die "not inside a git repository: $(pwd)"

# .codex-review lives in the main repo even when the task runs in a worktree.
root=$(cd "$(git rev-parse --git-common-dir)/.." && pwd)
review_root="$root/.codex-review"
branch=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --abbrev-ref HEAD 2>/dev/null || echo detached)
slug=${branch//\//-}
[ -n "$slug" ] && [ "$slug" != "detached" ] ||
  die "HEAD is not on a branch, so there is no directory to bind; check the task's branch out first"

want="$review_root/$slug"
stamp=$(date +%Y%m%d-%H%M%S)

# --- look before touching anything ------------------------------------------------
mine=()
if [ -d "$review_root" ]; then
  for dir in "$review_root"/*/; do
    [ -d "$dir" ] || continue
    name=$(basename "$dir")
    [ "$name" = "archive" ] && continue
    [ -f "$dir/taskflow-task" ] || continue
    [ "$(cat "$dir/taskflow-task")" = "$TASK" ] || continue
    mine+=("$name")
  done
fi

if [ "${#mine[@]}" -gt 1 ]; then
  die "these directories all claim task $TASK: ${mine[*]} — keep one and remove the marker from the rest; nothing was moved" 2
fi

occupied=0
if [ -d "$want" ] && [ -n "$(ls -A "$want" 2>/dev/null)" ]; then
  if [ ! -f "$want/taskflow-task" ] || [ "$(cat "$want/taskflow-task")" != "$TASK" ]; then
    occupied=1
  fi
fi

carry=
if [ "${#mine[@]}" -eq 1 ] && [ "${mine[0]}" != "$slug" ]; then
  carry=${mine[0]}
fi

run() {
  if [ "$DRY" = "1" ]; then
    echo "  would: $*"
  else
    "$@"
  fi
}

# --- act ---------------------------------------------------------------------------
if [ "$occupied" = "1" ]; then
  other=$( [ -f "$want/taskflow-task" ] && cat "$want/taskflow-task" || echo "no task" )
  echo "$slug/ holds state of another task ($other) — moving it to archive/$slug.$stamp/"
  run mkdir -p "$review_root/archive"
  run mv "$want" "$review_root/archive/$slug.$stamp"
fi

if [ -n "$carry" ]; then
  echo "task $TASK ran on $carry/ — carrying its review state over to $slug/"
  run mv "$review_root/$carry" "$want"
fi

run mkdir -p "$want/notes"
if [ "$DRY" = "1" ]; then
  echo "  would: write $want/taskflow-task = $TASK"
else
  printf '%s\n' "$TASK" > "$want/taskflow-task"
fi

echo "review state of $TASK: $want"
