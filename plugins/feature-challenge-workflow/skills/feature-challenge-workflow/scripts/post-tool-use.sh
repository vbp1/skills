#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./feature-challenge-lib.sh
. "$SCRIPT_DIR/feature-challenge-lib.sh"

fc_read_payload

if ! fc_payload_is_valid_json; then
  printf '%s\n' "Feature Challenge hook could not parse the tool payload. Blocking fail-closed." >&2
  exit 2
fi

fc_workflow_active || exit 0

if fc_tool_updates_feature_challenge_state; then
  if fc_claim_active_feature; then
    if ! fc_index_sync_active_feature; then
      fc_json_block_decision \
        "Feature Challenge state was edited, but index synchronization failed. Fix .agents/feature-challenges/index.json before continuing."
      exit 0
    fi
    exit 0
  fi
  fc_json_block_decision \
    "${FC_CLAIM_CONFLICT:-Feature Challenge state is claimed by another Codex. Do not edit this feature from the current Codex.}"
  exit 0
fi

if fc_decision_allows_code; then
  exit 0
fi

stage="$(fc_current_stage)"
feature_title="$(fc_active_feature_title 2>/dev/null || printf 'unknown')"
fc_json_block_decision \
  "Feature Challenge is active for: ${feature_title}. It is not approved for implementation. Current stage: ${stage}. Keep working on the active JSON file under .agents/feature-challenges/ instead of proceeding with code changes."
