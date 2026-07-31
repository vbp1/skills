#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./feature-challenge-lib.sh
. "$SCRIPT_DIR/feature-challenge-lib.sh"

fc_read_payload

if ! fc_payload_is_valid_json; then
  printf '%s\n' "Feature Challenge hook could not parse the tool payload. Blocking write-like tool fail-closed." >&2
  exit 2
fi

fc_workflow_active || exit 0
fc_tool_is_write_like || exit 0

if ! fc_claim_active_feature; then
  printf '%s\n' "${FC_CLAIM_CONFLICT:-Feature Challenge state is locked by another Codex. Try another feature or wait.}" >&2
  exit 2
fi

fc_tool_updates_feature_challenge_state && exit 0

if fc_decision_allows_code; then
  if ! fc_state_put stage approved_for_implementation; then
    printf '%s\n' "Feature Challenge could not persist approved_for_implementation stage. Blocking fail-closed." >&2
    exit 2
  fi
  exit 0
fi

fc_block_reason >&2
exit 2
