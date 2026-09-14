#!/usr/bin/env bash
# Contract tests for sparctl, run against a fake opponent CLI.
#
# The fake stands in for the real CLI so every failure path is reachable without
# spending a real turn: a clean answer, a provider crash, a time cap, a failed turn,
# a turn that never reports finishing, an empty answer, an unusable side file, a
# signal, a busy session and a stale lock.
#
# Usage:
#   tests/sparctl-test.sh           run every case
#   tests/sparctl-test.sh --verbose print each case as it passes
#
# Exit codes:
#   0  every case passed
#   1  a case failed; the failure is printed with what was expected and what came back

set -uo pipefail

VERBOSE=0
[ "${1:-}" = "--verbose" ] && VERBOSE=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$HERE/../skills/sparring"
SPARCTL="$SKILL/scripts/sparctl"
[ -x "$SPARCTL" ] || { echo "no executable sparctl at $SPARCTL" >&2; exit 1; }
OPPONENT="$(sed -n 's/^OPPONENT_CMD="\(.*\)"$/\1/p' "$SPARCTL" | head -1)"
[ -n "$OPPONENT" ] || { echo "cannot read OPPONENT_CMD from $SPARCTL" >&2; exit 1; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/sparctl-test.XXXXXX")"
BIN="$WORK/bin"
mkdir -p "$BIN"
trap 'rm -rf "$WORK"' EXIT

PASS=0
FAIL=0

# --- the fake opponent ---------------------------------------------------------------
# Behaviour is picked by CASE; every invocation records its own argv for assertions.
cat > "$BIN/$OPPONENT" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_ARGV"
answer_file=""
prev=""
for arg in "$@"; do
  [ "$prev" = "--output-last-message" ] && answer_file="$arg"
  prev="$arg"
done
cat > /dev/null   # drain the prompt on stdin

emit() { printf '%s\n' "$1"; }

case "$FAKE_STREAM" in
  codex)
    started='{"type":"thread.started","thread_id":"11111111-2222-3333-4444-555555555555"}'
    message='{"type":"item.completed","item":{"type":"agent_message","text":"fake answer"}}'
    completed='{"type":"turn.completed"}'
    failed='{"type":"turn.failed","error":{"message":"fake turn failure"}}'
    empty_completed="$completed"
    ;;
  claude)
    started='{"type":"system","subtype":"init","session_id":"11111111-2222-3333-4444-555555555555","model":"fake"}'
    message='{"type":"assistant","message":{"content":[{"type":"text","text":"fake answer"}]}}'
    completed='{"type":"result","subtype":"success","is_error":false,"result":"fake answer"}'
    failed='{"type":"result","subtype":"error_during_execution","is_error":true,"result":"fake turn failure"}'
    empty_completed='{"type":"result","subtype":"success","is_error":false,"result":""}'
    ;;
esac

write_answer() { [ -n "$answer_file" ] && printf 'fake answer\n' > "$answer_file"; return 0; }

case "$CASE" in
  ok)          emit "$started"; emit "$message"; emit "$completed"; write_answer ;;
  crash)       emit "$started"; echo "fake stderr detail" >&2; exit 3 ;;
  hang)        emit "$started"; sleep 30 ;;
  turnfail)    emit "$started"; emit "$failed" ;;
  incomplete)  emit "$started"; emit "$message"; write_answer ;;
  empty)       emit "$started"; emit "$empty_completed"; [ -n "$answer_file" ] && : > "$answer_file" ;;
  noid)        emit "$message"; emit "$completed"; write_answer ;;
esac
exit 0
FAKE
chmod +x "$BIN/$OPPONENT"

export PATH="$BIN:$PATH"
export FAKE_STREAM="$OPPONENT"
export FAKE_ARGV="$WORK/argv.log"
: > "$FAKE_ARGV"

# For the claude build the answer arrives inside the stream, so the fake's own
# answer file is unused; both builds are driven by the same cases.

run() {   # run <case> <state> <out> [extra sparctl args...]
  local case_name="$1" state="$2" out="$3"; shift 3
  CASE="$case_name" "$SPARCTL" ask --state "$state" --out "$out" --prompt "question" "$@" \
    > "$WORK/stdout" 2> "$WORK/stderr"
  echo $?
}

check() {  # check <name> <expected exit> <expected text in output> <actual exit>
  local name="$1" want_code="$2" want_text="$3" got_code="$4"
  local output; output="$(cat "$WORK/stdout" "$WORK/stderr" 2>/dev/null)"
  if [ "$got_code" != "$want_code" ]; then
    printf 'FAIL %s: exit %s, expected %s\n----- output -----\n%s\n------------------\n' \
      "$name" "$got_code" "$want_code" "$output" >&2
    FAIL=$((FAIL + 1)); return 1
  fi
  if [ -n "$want_text" ] && ! printf '%s' "$output" | grep -qF "$want_text"; then
    printf 'FAIL %s: output does not contain %s\n----- output -----\n%s\n------------------\n' \
      "$name" "$want_text" "$output" >&2
    FAIL=$((FAIL + 1)); return 1
  fi
  PASS=$((PASS + 1))
  [ "$VERBOSE" = 1 ] && printf 'ok   %s\n' "$name"
  return 0
}

state="$WORK/a.session"
out="$WORK/a.turn"

# 1. A clean turn.
code="$(run ok "$state" "$out")"
check "clean turn exits 0" 0 "wrote answer:" "$code"
grep -q "fake answer" "$out" || { echo "FAIL: answer not written to --out" >&2; FAIL=$((FAIL + 1)); }
grep -q "session_id=11111111-2222-3333-4444-555555555555" "$state" \
  || { echo "FAIL: session id not recorded in the state file" >&2; FAIL=$((FAIL + 1)); }
grep -q "(answered)" "$state.transcript" \
  || { echo "FAIL: the answered turn is not in the transcript" >&2; FAIL=$((FAIL + 1)); }
[ -d "$state.lock" ] && { echo "FAIL: the lock survived a finished turn" >&2; FAIL=$((FAIL + 1)); }

# 2. The next turn resumes the recorded session rather than opening a new one.
: > "$FAKE_ARGV"
code="$(run ok "$state" "$out")"
check "second turn exits 0" 0 "wrote answer:" "$code"
grep -q "11111111-2222-3333-4444-555555555555" "$FAKE_ARGV" \
  || { echo "FAIL: the second turn did not pass the session id to the opponent" >&2; FAIL=$((FAIL + 1)); }

# 3. A provider crash: real exit code, provider stderr, failure kept in the transcript.
code="$(run crash "$WORK/b.session" "$WORK/b.turn")"
check "provider crash exits 2" 2 "SPAR_PROVIDER_FAILED" "$code"
grep -q "fake stderr detail" "$WORK/stderr" \
  || { echo "FAIL: the provider's stderr was not reproduced" >&2; FAIL=$((FAIL + 1)); }
grep -qv "SPAR_FAILED: exit 0" "$WORK/stderr" \
  || { echo "FAIL: the terminal line reports exit 0 for a failed run" >&2; FAIL=$((FAIL + 1)); }
grep -q "SPAR_PROVIDER_FAILED" "$WORK/b.session.transcript" \
  || { echo "FAIL: the failed turn is not in the transcript" >&2; FAIL=$((FAIL + 1)); }
[ -f "$WORK/b.turn" ] && { echo "FAIL: --out was written for a failed turn" >&2; FAIL=$((FAIL + 1)); }
markers="$(grep -c '^SPAR_' "$WORK/stderr")"
[ "$markers" = 1 ] || { echo "FAIL: $markers lines start with SPAR_, expected exactly 1" >&2; FAIL=$((FAIL + 1)); }
tail -n 1 "$WORK/stderr" | grep -q '^SPAR_' \
  || { echo "FAIL: the SPAR_ line is not the last line of the run" >&2; FAIL=$((FAIL + 1)); }

# 4. The time cap.
code="$(SPAR_TIMEOUT=1 SPAR_KILL_AFTER=1 run hang "$WORK/c.session" "$WORK/c.turn")"
check "time cap exits 4" 4 "SPAR_TIMEOUT" "$code"

# 5. The opponent reports a failed turn.
code="$(run turnfail "$WORK/d.session" "$WORK/d.turn")"
check "reported failure exits 5" 5 "SPAR_TURN_FAILED" "$code"

# 6. The stream never reports a finished turn.
code="$(run incomplete "$WORK/e.session" "$WORK/e.turn")"
check "unfinished turn exits 5" 5 "SPAR_TURN_INCOMPLETE" "$code"

# 7. A finished turn with nothing in it.
code="$(run empty "$WORK/f.session" "$WORK/f.turn")"
check "empty answer exits 3" 3 "SPAR_EMPTY_ANSWER" "$code"

# 8. A side file that cannot be written.
mkdir -p "$WORK/g.session.id"
code="$(run ok "$WORK/g.session" "$WORK/g.turn")"
check "unusable side file exits 6" 6 "SPAR_READER_FAILED" "$code"

# 9. An option without its value.
"$SPARCTL" ask --state > "$WORK/stdout" 2> "$WORK/stderr"; code=$?
check "option without a value exits 1" 1 "SPAR_BAD_ARGS" "$code"

# 10. A session already in use.
mkdir -p "$WORK/h.session.lock"
printf '%s\n' "$$" > "$WORK/h.session.lock/pid"
code="$(run ok "$WORK/h.session" "$WORK/h.turn")"
check "busy session exits 7" 7 "SPAR_SESSION_BUSY" "$code"

# 11. A lock left behind by a process that is gone.
mkdir -p "$WORK/i.session.lock"
printf '999999\n' > "$WORK/i.session.lock/pid"
code="$(run ok "$WORK/i.session" "$WORK/i.turn")"
check "stale lock is taken over" 0 "wrote answer:" "$code"

# 12. A turn killed by a signal still prints a terminal line.
CASE=hang "$SPARCTL" ask --state "$WORK/j.session" --out "$WORK/j.turn" --prompt q \
  > "$WORK/j.log" 2>&1 &
killer_pid=$!
sleep 2
kill -TERM "$killer_pid" 2>/dev/null
wait "$killer_pid" 2>/dev/null
if grep -q "^SPAR_" "$WORK/j.log"; then
  PASS=$((PASS + 1)); [ "$VERBOSE" = 1 ] && printf 'ok   %s\n' "signal leaves a terminal line"
else
  printf 'FAIL signal leaves a terminal line\n----- log -----\n%s\n---------------\n' \
    "$(cat "$WORK/j.log")" >&2
  FAIL=$((FAIL + 1))
fi

# 13. status reports what is running.
"$SPARCTL" status --state "$WORK/k.session" > "$WORK/stdout" 2> "$WORK/stderr"; code=$?
check "status of an unused session is idle" 0 "idle" "$code"
mkdir -p "$WORK/k.session.lock"; printf '%s\n' "$$" > "$WORK/k.session.lock/pid"
"$SPARCTL" status --state "$WORK/k.session" > "$WORK/stdout" 2> "$WORK/stderr"; code=$?
check "status of a live turn is running" 0 "running" "$code"
printf '999999\n' > "$WORK/k.session.lock/pid"
"$SPARCTL" status --state "$WORK/k.session" > "$WORK/stdout" 2> "$WORK/stderr"; code=$?
check "status of a dead turn is abandoned" 0 "abandoned" "$code"
rm -rf "$WORK/k.session.lock"

# 14. A session that belongs to the other agent.
printf 'provider=someone-else\n' > "$WORK/l.session"
code="$(run ok "$WORK/l.session" "$WORK/l.turn")"
check "foreign session exits 1" 1 "SPAR_SESSION_PROVIDER_MISMATCH" "$code"

# 15. A stream that announces no session id.
code="$(run noid "$WORK/m.session" "$WORK/m.turn")"
check "missing session id exits 1" 1 "SPAR_SESSION_ID_MISSING" "$code"

printf '\n%s: %s passed, %s failed\n' "$(basename "$SPARCTL") [$OPPONENT]" "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
