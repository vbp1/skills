#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./feature-challenge-lib.sh
. "$SCRIPT_DIR/feature-challenge-lib.sh"

fc_read_payload

if ! fc_payload_is_valid_json; then
  printf '%s\n' "Feature Challenge hook could not parse the user prompt payload." >&2
  exit 0
fi

if fc_workflow_active; then
  if fc_select_feature_from_prompt; then
    :
  elif [ "$?" -eq 2 ]; then
    fc_json_additional_context \
      "UserPromptSubmit" \
      "Feature Challenge found multiple matching features. Ask the user to choose by title from this list:\n${FC_MATCH_CONFLICT:-}"
    exit 0
  fi
  stage="$(fc_current_stage)"
  feature_title="$(fc_active_feature_title 2>/dev/null || printf 'unknown')"
  feature_list="$(fc_feature_list_summary 2>/dev/null || true)"
  claim_note=""
  if ! fc_claim_active_feature; then
    claim_note=" Claim conflict: ${FC_CLAIM_CONFLICT:-this feature is claimed by another Codex.}"
  fi
  fc_json_additional_context \
    "UserPromptSubmit" \
    "Feature Challenge is active for: ${feature_title}. Current stage: ${stage}.${claim_note} Route this user message by feature title or summary, not by featureId. If the user is switching topics, set index.json.activeByOwner for this Codex to the matching feature. If multiple features match, ask the user to choose from this list by title:\n${feature_list}"
  exit 0
fi

if fc_select_feature_from_prompt; then
  if ! fc_claim_active_feature; then
    fc_json_additional_context \
      "UserPromptSubmit" \
      "Feature Challenge matched an existing feature, but it is already claimed. ${FC_CLAIM_CONFLICT:-Ask the user whether to switch to another feature, wait, or hand over ownership.}"
    exit 0
  fi
  stage="$(fc_current_stage)"
  feature_title="$(fc_active_feature_title 2>/dev/null || printf 'unknown')"
  fc_json_additional_context \
    "UserPromptSubmit" \
    "Feature Challenge selected existing feature: ${feature_title}. Current stage: ${stage}. Continue that feature instead of creating a new workflow."
  exit 0
elif [ "$?" -eq 2 ]; then
  fc_json_additional_context \
    "UserPromptSubmit" \
    "Feature Challenge found multiple matching features. Ask the user to choose by title from this list:\n${FC_MATCH_CONFLICT:-}"
  exit 0
fi

if fc_prompt_looks_like_feature_request; then
  if ! fc_set_required; then
    fc_json_additional_context \
      "UserPromptSubmit" \
      "Feature Challenge could not claim this feature. ${FC_CLAIM_CONFLICT:-Another Codex is updating or working on the matching feature. Ask the user whether to switch to another feature, wait, or hand over ownership.}"
    exit 0
  fi
  if ! fc_claim_active_feature; then
    fc_json_additional_context \
      "UserPromptSubmit" \
      "Feature Challenge matched an existing feature, but it is already claimed. ${FC_CLAIM_CONFLICT:-Ask the user whether to switch to another feature, wait, or hand over ownership.}"
    exit 0
  fi
  feature_title="$(fc_active_feature_title 2>/dev/null || printf 'unknown')"
  fc_json_additional_context \
    "UserPromptSubmit" \
    "Feature Challenge is required for: ${feature_title}. Do not implement yet. Update the active JSON file under .agents/feature-challenges/. Start with Problem Gate: separate the requested solution from the user-confirmed problem, then proceed gate by gate. Refer to this feature by title in user-facing messages."
  exit 0
fi

exit 0
