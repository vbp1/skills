#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./feature-challenge-lib.sh
. "$SCRIPT_DIR/feature-challenge-lib.sh"

fc_read_payload

if ! fc_payload_is_valid_json; then
  printf '%s\n' "Feature Challenge hook could not parse the stop payload. Blocking fail-closed." >&2
  exit 2
fi

fc_workflow_active || exit 0

if fc_decision_allows_code; then
  if ! fc_state_put stage approved_for_implementation; then
    printf '%s\n' "Feature Challenge could not persist approved_for_implementation stage. Blocking fail-closed." >&2
    exit 2
  fi
  exit 0
fi

stage="$(fc_current_stage)"
feature_title="$(fc_active_feature_title 2>/dev/null || printf 'unknown')"
cat >&2 <<EOF
Feature Challenge is still incomplete.
Active feature: ${feature_title}.
Current stage: ${stage}.

Do not finish the turn yet. Continue the workflow:
1. Confirm the real problem with the user or record why it is already confirmed.
2. Check existing capabilities, similar mechanisms, and smaller extensions.
3. Check architecture and product fit.
4. Challenge the idea and record objections.
5. Ask non-obvious user questions only for unresolved decisions.
6. Record a final decision.decision in the active feature JSON file.
EOF
exit 2
