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
  review-round.sh [-C <working copy>] <command> [args]

  Every command acts on the root of the working copy it is given, or of the one the
  caller stands in. `-C` names it explicitly, for a caller whose current directory
  may have moved.

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
  save <N> <track> <output file>
                     Copy a track's final message verbatim to round-<N>-<track>.md and
                     print that path. <output file> is the one the track's completion
                     notification names (the track's transcript, one JSON record per
                     line). <track> is lowercase letters and dashes. Refuses an existing
                     report and a transcript with no final text; nothing is written then.
  path <N>           Print the path of round-<N>.md (whether or not it exists).
  diff <N>           Print the path of round-<N>.diff (whether or not it exists).
  files <N>          List the files round <N> covers, one per line as "present|deleted<TAB>path".
                     This is the checklist a review track must account for: every path here
                     ends its report either reviewed or explicitly skipped. Readable from any
                     working copy — it reads the recorded snapshot and compares nothing.
  delta <N>          List the files the fixes touched since round <N>, one per line as
                     "changed|added|gone<TAB>path". Empty output means nothing moved.
                     This is where defects introduced by the fixes themselves live.
  seal <N>           Close round <N>: assert nothing moved since it was opened, then
                     record that moment. Run it once, when the last track has returned
                     and before the first fix. Exit 2 and a list of violations if a
                     track mutated the shared tree — nothing is sealed then. A round
                     that carries a seal refuses a second one.
  check <N>          Assert nothing moved since round <N> was opened — files OR stashes.
                     Exit 2 and a list of violations if a track mutated the shared tree.
                     Once the round carries a seal, the read-only assertion is already
                     recorded: it then names how many files moved after the seal — the
                     main loop's own fixes — and exits 0. Run from another working copy
                     than the one the round was opened in, it names both and compares
                     nothing.
  list               List the rounds recorded for the current branch.

LAYOUT
  <main repo root>/.precommit-review/<branch with / replaced by ->/
      round-1.diff    the diff as it stood when that round ran ("open" writes this)
      round-1.files   content hash per reviewed file, for computing the delta
      round-1.stash   the stash list at that moment, so a stash by a track is visible
      round-1.where   the working copy and branch the round was opened in
      round-1.sealed  the moment the panel returned with the tree untouched ("seal")
      round-1.md      the report: verdict, tracks, track agent names, open items
      round-2.diff    ...

WHY THE SNAPSHOT
  A fix can introduce a defect of its own. round-<N>.diff is the "before" a re-review
  track compares against, and `delta <N>` names exactly which files moved since — so
  the round can look at those directly instead of re-reading the whole change.

EXAMPLES
  read -r N DIR < <(review-round.sh open)   # claim round N
  review-round.sh path 1                    # .../round-1.md
  review-round.sh files 1                   # the checklist a track must close
  review-round.sh seal 1                    # last track back, before the first fix
  review-round.sh delta 1                   # what the fixes touched

EXIT CODES
  0  success (for `check`: the tree is untouched, or the round is sealed)
  1  not a git repository, unknown command, a missing/invalid round number, a round
     belonging to another working copy, or a second `seal` on the same round
  2  `check` and `seal`: a track mutated the shared working tree or the stash list
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

# Every listing below is taken from the root of the working copy, never from wherever
# the caller happened to stand: `git diff --name-only` prints paths from the root while
# `git ls-files --others` prints them from the current directory, so a run started in a
# subdirectory recorded the same file under two names and read every tracked file as
# deleted. `-C <path>` names the copy explicitly, for a caller whose directory may have
# moved out from under it.
worktree_root() {
  git rev-parse --show-toplevel 2>/dev/null || die "not inside a git repository."
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

# A round is claimed by `open`, which writes round-<N>.diff, and reported in round-<N>.md,
# which may be written by hand without a claim. Counting every round-<N>.* covers both, so
# the next round can never land on a number one of them already holds.
latest_round() {
  local dir f n best=0
  dir="$(round_dir)"
  for f in "$dir"/round-*.*; do
    [[ -e "$f" ]] || continue
    n="${f##*/round-}"
    n="${n%%.*}"
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

# Which copy and which branch the round was opened on. The store is keyed by branch, so
# a caller whose directory drifted into another checkout resolves a round directory that
# holds someone else's manifest and reads their work as mutations of its own. The round
# carries its origin, and a command run anywhere else stops instead of comparing.
where_of_round() {
  local f="$(round_dir)/round-$1.where"
  [[ -f "$f" ]] && head -1 "$f" || true
}

require_same_copy() {  # require_same_copy <round number>
  local opened here
  opened="$(where_of_round "$1")"
  [[ -n "$opened" ]] || return 0
  here="$(worktree_root)"
  [[ "$opened" == "$here" ]] && return 0
  die "round $1 was opened in $opened on branch $(sed -n 2p "$(round_dir)/round-$1.where"), and you are in $here on branch $(git symbolic-ref --short HEAD 2>/dev/null || echo detached). Nothing was compared — run it from the copy the round belongs to, or pass -C $opened."
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

# Everything that moved since round <N> was opened, one line per mutation, tagged by
# where it moved. `check` and `seal` both read this — one to assert, one to assert and
# then record that the assertion passed.
moved_since() {  # moved_since <round number>
  local n="$1" dir line
  dir="$(round_dir)"
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    echo "TREE $line"
  done < <("$SELF" delta "$n")
  if [[ -f "$dir/round-$n.stash" ]]; then
    while IFS= read -r line; do
      [[ -n "$line" ]] || continue
      echo "STASH $line"
    done < <(diff <(cat "$dir/round-$n.stash") <(git stash list) | sed -n 's/^> //p')
  fi
}

seal_of_round() {  # seal_of_round <round number>
  local f="$(round_dir)/round-$1.sealed"
  [[ -f "$f" ]] && head -1 "$f" || true
}

# `check` and `seal` re-enter this script for `delta`, so they need a path that still
# resolves after the moves below.
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

# `-C <path>` names the working copy to act in. Without it the copy is the one the
# caller stands in — and every listing below is still taken from its root.
if [[ "${1:-}" == "-C" ]]; then
  [[ -n "${2:-}" ]] || die "-C needs a path to a working copy."
  [[ -d "$2" ]] || die "-C $2: no such directory. Nothing was done."
  cd "$2" || die "cannot enter $2. Nothing was done."
  shift 2
fi
case "${1:-}" in
  -h | --help | help | '') ;;
  *) cd "$(worktree_root)" ;;
esac

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
    for f in "$dir/round-$n."*; do
      [[ -e "$f" ]] || continue
      die "round $n already has $f — refusing to claim a number that is in use. Nothing was recorded."
    done
    echo "$SCOPE" >"$dir/round-$n.scope"
    printf '%s\n%s\n' "$(worktree_root)" "$(git symbolic-ref --short HEAD 2>/dev/null || echo detached)" >"$dir/round-$n.where"
    current_diff >"$dir/round-$n.diff"
    current_manifest >"$dir/round-$n.files"
    # A stash is the one mutation that leaves the tree looking merely "clean" rather
    # than wrong, so it hides work instead of corrupting it — worth its own baseline.
    git stash list >"$dir/round-$n.stash"
    echo "$n $dir"
    echo "opened in $(worktree_root) on $(git symbolic-ref --short HEAD 2>/dev/null || echo detached), scope $SCOPE" >&2
    ;;
  save)
    # Tracks write no files; their report is the last message of their run. Copied
    # here by program, so the round holds what the track wrote, not a retelling.
    n="$(require_round "${2:-}")"
    track="${3:-}"
    src="${4:-}"
    [[ "$track" =~ ^[a-z][a-z-]*$ ]] || die "save needs a track key of lowercase letters and dashes, got '${track}'. Nothing was written."
    [[ -f "$src" ]] || die "save needs the track's output file, '${src}' is not a file. Nothing was written."
    target="$(round_dir)/round-$n-$track.md"
    [[ ! -e "$target" ]] || die "$target already exists. Nothing was written."
    text="$(python3 -I - "$src" <<'PY'
import json, sys

last_id, parts = None, {}
with open(sys.argv[1], encoding="utf-8") as fh:
    for number, line in enumerate(fh, 1):
        try:
            record = json.loads(line)
        except ValueError as exc:
            sys.exit(f"line {number} of {sys.argv[1]} is not JSON: {exc}")
        if record.get("type") != "assistant":
            continue
        message = record.get("message") or {}
        texts = [c.get("text", "") for c in message.get("content") or []
                 if isinstance(c, dict) and c.get("type") == "text" and c.get("text", "").strip()]
        if texts:
            key = message.get("id") or number
            if key != last_id:
                last_id, parts[key] = key, []
            parts[key].extend(texts)
if last_id is None:
    sys.exit(f"{sys.argv[1]} holds no assistant text: the track returned no report")
print("\n\n".join(parts[last_id]))
PY
)" || die "cannot read the report out of $src (above). Nothing was written."
    printf '%s\n' "$text" >"$target"
    echo "$target"
    ;;
  path)
    n="$(require_round "${2:-}")"
    echo "$(round_dir)/round-$n.md"
    ;;
  diff)
    n="$(require_round "${2:-}")"
    echo "$(round_dir)/round-$n.diff"
    ;;
  files)
    # The manifest as a checklist: no comparison against the current tree, so unlike
    # `delta` and `check` this answers the same from any working copy.
    n="$(require_round "${2:-}")"
    manifest="$(round_dir)/round-$n.files"
    [[ -f "$manifest" ]] || die "no manifest for round $n at $manifest — that round was not opened through this script."
    awk -F'\t' 'NF == 0 { next }
                $1 == "deleted" { print "deleted\t" $2; next }
                { print "present\t" $2 }' "$manifest"
    ;;
  delta)
    n="$(require_round "${2:-}")"
    require_same_copy "$n"
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
    require_same_copy "$n"
    dir="$(round_dir)"
    [[ -f "$dir/round-$n.files" ]] || die "no manifest for round $n — that round was not opened through this script."
    # Past the seal the panel is over and the main loop is fixing, so what moved is
    # its own work. The assertion this command makes was made at the seal; repeating
    # it here would read every fix as a track having written to the tree.
    sealed="$(seal_of_round "$n")"
    if [[ -n "$sealed" ]]; then
      moved="$(moved_since "$n" | wc -l)"
      echo "round $n was sealed at $sealed with the tree untouched — the read-only assertion belongs to that moment. $moved change(s) since are the main loop's own fixes; 'delta $n' lists them." >&2
      exit 0
    fi
    echo "checking $(worktree_root) on $(git symbolic-ref --short HEAD 2>/dev/null || echo detached) against round $n" >&2
    violations=0
    while IFS= read -r line; do
      [[ -n "$line" ]] || continue
      violations=$((violations + 1))
      echo "$line"
    done < <(moved_since "$n")
    if ((violations)); then
      echo "-- $violations mutation(s) since round $n was opened. A read-only panel must produce none." >&2
      exit 2
    fi
    ;;
  seal)
    # The boundary between the panel and the fixes. Recording it is what lets a later
    # command tell a track that wrote to the shared tree from the main loop's own edits.
    n="$(require_round "${2:-}")"
    require_same_copy "$n"
    dir="$(round_dir)"
    [[ -f "$dir/round-$n.files" ]] || die "no manifest for round $n — that round was not opened through this script."
    sealed="$(seal_of_round "$n")"
    [[ -z "$sealed" ]] || die "round $n was already sealed at $sealed. Nothing was recorded — a second seal would move the boundary past the fixes it exists to separate."
    echo "sealing $(worktree_root) on $(git symbolic-ref --short HEAD 2>/dev/null || echo detached) against round $n" >&2
    violations=0
    while IFS= read -r line; do
      [[ -n "$line" ]] || continue
      violations=$((violations + 1))
      echo "$line"
    done < <(moved_since "$n")
    if ((violations)); then
      echo "-- $violations mutation(s) since round $n was opened. A read-only panel must produce none. Nothing was sealed — restore the tree, then seal." >&2
      exit 2
    fi
    stamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf '%s\n%s\n' "$stamp" "$(worktree_root)" >"$dir/round-$n.sealed"
    echo "round $n sealed at $stamp — the panel left the tree untouched. Changes from here on are yours." >&2
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
