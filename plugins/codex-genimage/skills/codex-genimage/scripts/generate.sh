#!/usr/bin/env bash
# Generate an image via codex CLI and save it to a target absolute path.
#
# Strategy: codex calls image_gen and stops. The wrapper extracts codex's
# session id from its stdout, looks up the resulting *.png in that session's
# directory under ~/.codex/generated_images/, and copies it to $OUTPUT.
# Codex never touches the local filesystem itself, so this is race-safe with
# concurrent generate.sh invocations — each codex exec has its own session
# uuid and writes to its own directory.
#
# The pickup matches any *.png in the session directory rather than a fixed
# filename prefix: codex names image_gen output differently per version and
# per mode (`exec-<uuid>.png` under `codex exec`, `ig_<hash>.png` in the TUI),
# and the session directory holds nothing but that run's image_gen output.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: generate.sh --prompt TEXT --output ABS_PATH [--ref FILE ...] [--model MODEL]

Required:
  --prompt TEXT     Image description prompt sent to codex
  --output PATH     Absolute output path including filename and extension
                    (.png recommended)

Optional (repeatable):
  --ref FILE        Local reference image attached via codex -i (repeat for
                    multiple references)

Optional:
  --model MODEL     Override codex --model (default: codex config)
  -h, --help        Show this help

Exit codes:
  0  image saved at --output
  1  invalid arguments
  2  could not pick up the image (session id missing, or no PNG produced)
EOF
}

PROMPT=""
OUTPUT=""
MODEL=""
REFS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt) PROMPT="${2-}"; shift 2;;
    --output) OUTPUT="${2-}"; shift 2;;
    --ref)    REFS+=("${2-}"); shift 2;;
    --model)  MODEL="${2-}"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1;;
  esac
done

[[ -z "$PROMPT" ]] && { echo "error: --prompt is required" >&2; exit 1; }
[[ -z "$OUTPUT" ]] && { echo "error: --output is required" >&2; exit 1; }
[[ "$OUTPUT" != /* ]] && { echo "error: --output must be an absolute path (got: $OUTPUT)" >&2; exit 1; }

for ref in "${REFS[@]}"; do
  if [[ ! -f "$ref" ]]; then
    echo "error: reference image not found: $ref" >&2
    exit 1
  fi
done

mkdir -p "$(dirname "$OUTPUT")"

command -v codex >/dev/null 2>&1 || { echo "error: codex CLI not found in PATH" >&2; exit 1; }

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
GEN_DIR="$CODEX_HOME/generated_images"

# Tightly scoped prompt: only image_gen, then stop. The model sees the
# image_gen result as a sandbox path (e.g. /mnt/data/0.png) and cannot
# reliably translate that to a host path, so we don't ask it to copy —
# the wrapper does that part using the session id.
FULL_PROMPT="Use only the built-in image_gen tool to produce one image for the prompt below. Do not call any other tools. Do not run shell commands. Do not plan, research, read files, browse the web, or call MCP tools. After image_gen returns, just stop — the wrapper will pick up the file. Reply with the single word: done.

Image prompt:
$PROMPT"

# --ignore-user-config disables the user's MCP servers (context7 etc.) and
# web_search/personality from ~/.codex/config.toml. Auth still loads from
# CODEX_HOME. reasoning=low is the API minimum allowed with image_gen.
CMD=(codex exec
  --skip-git-repo-check
  --dangerously-bypass-approvals-and-sandbox
  --ignore-user-config
  -c model_reasoning_effort=low)
[[ -n "$MODEL" ]] && CMD+=(--model "$MODEL")
for ref in "${REFS[@]}"; do CMD+=(--image "$ref"); done
# `--` closes the option list before the positional prompt. codex declares
# `-i, --image <FILE>...` as variadic, so without the separator the prompt
# following a `--image` is swallowed as another image path — codex then finds
# no prompt argument, falls back to stdin, and exits with
# "No prompt provided via stdin".
CMD+=(-- "$FULL_PROMPT")

# Tee codex output to a tempfile so we can extract `session id: <uuid>`
# from its startup banner. Each session writes to its own dir under
# generated_images, so scoping the pickup by uuid (not by mtime) makes
# parallel invocations safe.
LOG=$(mktemp -t codex-genimage.XXXXXX.log)
trap 'rm -f "$LOG"' EXIT

echo "→ codex exec ${REFS[*]:+(refs: ${#REFS[@]})}" >&2
set +e
"${CMD[@]}" 2>&1 | tee "$LOG"
CODEX_RC=${PIPESTATUS[0]}
set -e

SESSION_ID=$(grep -m1 -oE 'session id: [0-9a-fA-F-]{36}' "$LOG" | awk '{print $3}')

if [[ -z "${SESSION_ID:-}" ]]; then
  echo "✗ could not determine codex session id from stdout" >&2
  echo "  (codex exit code: $CODEX_RC — check the transcript above)" >&2
  exit 2
fi

SESSION_DIR="$GEN_DIR/$SESSION_ID"

if [[ ! -d "$SESSION_DIR" ]]; then
  echo "✗ codex produced no image: $SESSION_DIR was never created" >&2
  echo "  image_gen was not called at all in session $SESSION_ID (codex exit code: $CODEX_RC)." >&2
  echo "  Check the transcript above for a refusal, and check that the model in use offers image_gen." >&2
  exit 2
fi

FRESH=$(find "$SESSION_DIR" -maxdepth 1 -type f -name '*.png' -printf '%T@ %p\n' 2>/dev/null \
  | sort -nr | head -1 | awk '{print $2}')

if [[ -z "${FRESH:-}" ]]; then
  echo "✗ codex created $SESSION_DIR but left no .png in it" >&2
  echo "  (codex session $SESSION_ID exited with code $CODEX_RC)" >&2
  echo "  Directory contents:" >&2
  ls -la "$SESSION_DIR" >&2
  exit 2
fi

cp "$FRESH" "$OUTPUT"
echo "✓ saved: $OUTPUT"
file "$OUTPUT"
