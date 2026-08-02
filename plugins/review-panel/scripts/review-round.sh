#!/usr/bin/env bash
# Round directory manager for the pre-commit review panel (CLAUDE.md gate 7).
#
# Rounds must survive the things that routinely lose them: a branch switch, a
# parallel worktree, and `git add`. So the store lives at the MAIN repository root
# (resolved through --git-common-dir, which points at the main .git even from a
# worktree), is keyed by branch, and is listed in .git/info/exclude — never staged,
# never shown by `git status`, never carried into a commit.
set -euo pipefail

STORE_NAME=".precommit-review"

usage() {
  cat <<'EOF'
review-round.sh — round directory manager for the pre-commit review panel

USAGE
  review-round.sh <command> [args]

COMMANDS
  dir                Print the round directory for the current branch, creating it
                     if needed. All worktrees of a repository share one store.
  latest             Print the highest existing round number, or 0 if none.
  next               Print the number the next round will take (latest + 1).
  open [--scope <spec>]
                     Claim the next round: snapshot the diff and the content hash of
                     every reviewed file, then print "<N> <dir>". Write the report to
                     <dir>/round-<N>.md yourself. <spec> is one of:
                       worktree   everything not in HEAD, staged or not, including
                                  untracked files. The default, and what the
                                  pre-commit panel always uses.
                       staged     only the index — exactly what a commit would contain.
                       <revision> anything `git diff` accepts: main...HEAD, HEAD~3..HEAD,
                                  a single sha, a tag.
                     An unusable spec fails before the round is claimed. The scope is
                     recorded, so `delta` and `check` compare like with like.
  path <N>           Print the path of round-<N>.md (whether or not it exists).
  diff <N>           Print the path of round-<N>.diff (whether or not it exists).
  delta <N>          List the files the fixes touched since round <N>, one per line as
                     "changed|added|gone<TAB>path". Empty output means nothing moved.
                     This is where defects introduced by the fixes themselves live.
  check <N>          Assert nothing moved since round <N> was opened — files OR stashes.
                     Run it the moment a read-only review panel returns. Exit 2 and a
                     list of violations if a track mutated the shared tree.
  list               List the rounds recorded for the current branch.

LAYOUT
  <main repo root>/.precommit-review/<branch with / replaced by ->/
      round-1.diff    the diff as it stood when that round ran ("open" writes this)
      round-1.files   content hash per reviewed file, for computing the delta
      round-1.stash   the stash list at that moment, so a stash by a track is visible
      round-1.md      the report: verdict, tracks, track agent names, open items
      round-2.diff    ...

WHY THE SNAPSHOT
  A fix can introduce a defect of its own. round-<N>.diff is the "before" a re-review
  track compares against, and `delta <N>` names exactly which files moved since — so
  the round can look at those directly instead of re-reading the whole change.

EXAMPLES
  read -r N DIR < <(./.claude/scripts/review-round.sh open)   # claim round N
  ./.claude/scripts/review-round.sh path 1                    # .../round-1.md
  ./.claude/scripts/review-round.sh delta 1                   # what the fixes touched

EXIT CODES
  0  success (for `check`: the tree is untouched)
  1  not a git repository, unknown command, or a missing/invalid round number
  2  `check` only: a track mutated the shared working tree or the stash list
EOF
}

die() {
  echo "review-round.sh: $*" >&2
  exit 1
}

main_repo_root() {
  local common
  common="$(git rev-parse --git-common-dir 2>/dev/null)" || die "not inside a git repository."
  (cd "$common/.." && pwd)
}

branch_slug() {
  local branch
  branch="$(git symbolic-ref --short HEAD 2>/dev/null)" || branch="detached"
  echo "$branch" | tr '/' '-'
}

round_dir() {
  local dir
  dir="$(main_repo_root)/$STORE_NAME/$(branch_slug)"
  mkdir -p "$dir"
  echo "$dir"
}

# A round is claimed by `open`, which writes round-<N>.diff. The report lands later,
# so counting reports would hand the next round the number this one is already using.
latest_round() {
  local dir n best=0
  dir="$(round_dir)"
  for f in "$dir"/round-*.diff; do
    [[ -e "$f" ]] || continue
    n="${f##*/round-}"
    n="${n%.diff}"
    [[ "$n" =~ ^[0-9]+$ ]] || continue
    ((n > best)) && best="$n"
  done
  echo "$best"
}

# In the main worktree the store sits inside the tree, so it would otherwise show up
# as changes of its own — every round would report the previous round's files.
# Excluding it here rather than relying on .git/info/exclude keeps the script correct
# in a repository that has not been set up yet.
# What a round covers is the caller's decision — uncommitted work, just the index, a
# branch against its base, a single commit. Rounds must not mix scopes, so it is recorded
# with the round and `delta`/`check` read it back rather than re-deriving it.
SCOPE="worktree"

scope_of_round() {
  local f="$(round_dir)/round-$1.scope"
  [[ -f "$f" ]] && cat "$f" || echo worktree
}

# An unusable scope stops the run here, before a round is claimed: a bad ref silently
# treated as "worktree" would produce a report about a change nobody asked to review.
validate_scope() {
  case "$1" in
    worktree | staged) return 0 ;;
  esac
  git diff --name-only "$1" -- . >/dev/null 2>&1 ||
    die "scope '$1' is not 'worktree', 'staged', or a revision git can diff (tried: git diff $1). Nothing was recorded."
}

changed_paths() {
  case "$SCOPE" in
    staged) git diff --cached --name-only -- . ":(exclude)$STORE_NAME" | sort -u ;;
    worktree)
      {
        git diff HEAD --name-only -- . ":(exclude)$STORE_NAME"
        git ls-files --others --exclude-standard -- . ":(exclude)$STORE_NAME"
      } | sort -u
      ;;
    *) git diff --name-only "$SCOPE" -- . ":(exclude)$STORE_NAME" | sort -u ;;
  esac
}

# The working-tree diff the panel actually reviews: tracked changes against HEAD plus
# every untracked, non-ignored file. `git diff HEAD` alone omits untracked files, and
# `git add -N` would make them visible only by mutating the caller's index — so each
# one is diffed against /dev/null instead, which touches nothing.
current_diff() {
  case "$SCOPE" in
    staged)
      git diff --cached -- . ":(exclude)$STORE_NAME"
      ;;
    worktree)
      git diff HEAD -- . ":(exclude)$STORE_NAME"
      local f
      while IFS= read -r f; do
        [[ -n "$f" ]] || continue
        git diff --no-index -- /dev/null "$f" || true
      done < <(git ls-files --others --exclude-standard -- . ":(exclude)$STORE_NAME")
      ;;
    *)
      git diff "$SCOPE" -- . ":(exclude)$STORE_NAME"
      ;;
  esac
}

# Content hash per reviewed file. Comparing two of these answers "which files did the
# fixes touch" exactly, and reads as a plain list — where comparing the two diffs
# themselves yields a diff-of-diffs nobody can act on.
current_manifest() {
  local f
  while IFS= read -r f; do
    [[ -n "$f" ]] || continue
    if [[ -f "$f" ]]; then
      printf '%s\t%s\n' "$(git hash-object -- "$f")" "$f"
    else
      printf 'deleted\t%s\n' "$f"
    fi
  done < <(changed_paths)
}

require_round() {
  local n="$1"
  [[ "$n" =~ ^[0-9]+$ ]] && ((n >= 1)) || die "round number must be a positive integer — got '${n}'."
  echo "$n"
}

cmd="${1:-}"
case "$cmd" in
  -h | --help | help | '')
    usage
    ;;
  dir)
    round_dir
    ;;
  latest)
    latest_round
    ;;
  next)
    echo $(($(latest_round) + 1))
    ;;
  open)
    case "${2:-}" in
      --scope)
        [[ -n "${3:-}" ]] || die "open --scope needs a value: 'worktree', 'staged', or a revision to diff."
        validate_scope "$3"
        SCOPE="$3"
        ;;
      '') ;;
      *) die "unknown option '${2}' for open. Only --scope <worktree|staged|revision> is accepted." ;;
    esac
    dir="$(round_dir)"
    n=$(($(latest_round) + 1))
    echo "$SCOPE" >"$dir/round-$n.scope"
    current_diff >"$dir/round-$n.diff"
    current_manifest >"$dir/round-$n.files"
    # A stash is the one mutation that leaves the tree looking merely "clean" rather
    # than wrong, so it hides work instead of corrupting it — worth its own baseline.
    git stash list >"$dir/round-$n.stash"
    echo "$n $dir"
    ;;
  path)
    n="$(require_round "${2:-}")"
    echo "$(round_dir)/round-$n.md"
    ;;
  diff)
    n="$(require_round "${2:-}")"
    echo "$(round_dir)/round-$n.diff"
    ;;
  delta)
    n="$(require_round "${2:-}")"
    manifest="$(round_dir)/round-$n.files"
    [[ -f "$manifest" ]] || die "no manifest for round $n at $manifest — that round was not opened through this script."
    SCOPE="$(scope_of_round "$n")"
    # One line per file the fixes touched, tagged with how. Empty output means nothing
    # changed since that round.
    join -t "$(printf '\t')" -j 2 -a 1 -a 2 -o '0,1.1,2.1' \
      <(sort -k2 "$manifest") <(current_manifest | sort -k2) |
      awk -F'\t' '$2 == "" { print "added\t" $1; next }
                  $3 == "" { print "gone\t" $1; next }
                  $2 != $3 { print "changed\t" $1 }'
    ;;
  check)
    # Review tracks are read-only by contract, but a contract is a request and the
    # tracks hold Bash. This is the part that does not depend on them complying:
    # anything that moved while a read-only panel was running gets named here.
    n="$(require_round "${2:-}")"
    dir="$(round_dir)"
    [[ -f "$dir/round-$n.files" ]] || die "no manifest for round $n — that round was not opened through this script."
    violations=0
    while IFS= read -r line; do
      [[ -n "$line" ]] || continue
      violations=$((violations + 1))
      echo "TREE $line"
    done < <("$0" delta "$n")
    if [[ -f "$dir/round-$n.stash" ]]; then
      while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        violations=$((violations + 1))
        echo "STASH $line"
      done < <(diff <(cat "$dir/round-$n.stash") <(git stash list) | sed -n 's/^> //p')
    fi
    if ((violations)); then
      echo "-- $violations mutation(s) since round $n was opened. A read-only panel must produce none." >&2
      exit 2
    fi
    ;;
  list)
    dir="$(round_dir)"
    found=0
    for f in "$dir"/round-*.diff; do
      [[ -e "$f" ]] || continue
      found=1
      n="${f##*/round-}"
      n="${n%.diff}"
      if [[ -f "$dir/round-$n.md" ]]; then
        printf 'round-%s\t%s\n' "$n" "$(head -1 "$dir/round-$n.md")"
      else
        printf 'round-%s\t(opened, no report written yet)\n' "$n"
      fi
    done
    ((found)) || echo "no rounds recorded for $(branch_slug) yet ($dir)"
    ;;
  *)
    die "unknown command '$cmd'. Run --help for usage."
    ;;
esac
