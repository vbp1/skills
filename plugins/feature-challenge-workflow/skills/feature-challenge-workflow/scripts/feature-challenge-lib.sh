#!/usr/bin/env bash
set -u

FEATURE_CHALLENGE_STATE_DIR_REL=".agents/feature-challenges"
FEATURE_CHALLENGE_INDEX_REL=".agents/feature-challenges/index.json"
FEATURE_CHALLENGE_INDEX_LOCK_REL=".agents/feature-challenges/index.lock"
FEATURE_CHALLENGE_DEFAULT_CLAIM_TTL_SECONDS=86400

fc_read_payload() {
  FC_PAYLOAD="$(cat)"
}

fc_require_jq() {
  command -v jq >/dev/null 2>&1
}

fc_payload_is_valid_json() {
  fc_require_jq || return 1
  jq -e 'type == "object"' >/dev/null 2>&1 <<<"$FC_PAYLOAD"
}

fc_now() {
  date -u '+%Y-%m-%dT%H:%M:%SZ'
}

fc_epoch() {
  date -u '+%s'
}

fc_claim_ttl_seconds() {
  case "${FEATURE_CHALLENGE_CLAIM_TTL_SECONDS:-$FEATURE_CHALLENGE_DEFAULT_CLAIM_TTL_SECONDS}" in
    ''|*[!0-9]*) printf '%s\n' "$FEATURE_CHALLENGE_DEFAULT_CLAIM_TTL_SECONDS" ;;
    *) printf '%s\n' "${FEATURE_CHALLENGE_CLAIM_TTL_SECONDS:-$FEATURE_CHALLENGE_DEFAULT_CLAIM_TTL_SECONDS}" ;;
  esac
}

fc_claim_expires_epoch() {
  local now ttl
  now="$(fc_epoch)"
  ttl="$(fc_claim_ttl_seconds)"
  printf '%s\n' "$((now + ttl))"
}

fc_state_path_is_feature_json() {
  local path base
  path="$1"
  case "$path" in
    .agents/feature-challenges/*.json)
      base="$(basename -- "$path")"
      [ "$base" != "index.json" ]
      ;;
    *) return 1 ;;
  esac
}

fc_active_state_rel_file() {
  local feature_id
  feature_id="$(fc_active_feature_id)" || return 1
  printf '%s/%s.json\n' "$FEATURE_CHALLENGE_STATE_DIR_REL" "$feature_id"
}

fc_json_field() {
  fc_require_jq || return 1
  jq -r --arg key "$1" '.[$key] // empty' <<<"$FC_PAYLOAD"
}

fc_cwd() {
  local cwd
  cwd="$(fc_json_field cwd)"
  if [ -n "$cwd" ]; then
    printf '%s\n' "$cwd"
  else
    pwd
  fi
}

fc_agents_dir() {
  printf '%s/.agents\n' "$(fc_cwd)"
}

fc_state_dir() {
  printf '%s/%s\n' "$(fc_cwd)" "$FEATURE_CHALLENGE_STATE_DIR_REL"
}

fc_index_file() {
  printf '%s/%s\n' "$(fc_cwd)" "$FEATURE_CHALLENGE_INDEX_REL"
}

fc_index_lock_file() {
  printf '%s/%s\n' "$(fc_cwd)" "$FEATURE_CHALLENGE_INDEX_LOCK_REL"
}

fc_ensure_agents_dir() {
  mkdir -p "$(fc_state_dir)"
}

fc_require_flock() {
  command -v flock >/dev/null 2>&1
}

fc_lock_index() {
  fc_require_flock || return 73
  fc_ensure_agents_dir
  exec 9>"$(fc_index_lock_file)"
  flock -n -E 75 9
}

fc_unlock_index() {
  flock -u 9 2>/dev/null || true
}

fc_owner_id() {
  local host session
  host="$(hostname 2>/dev/null || printf 'unknown-host')"
  session="$(fc_json_field session_id 2>/dev/null || true)"
  if [ -z "$session" ]; then
    session="$(fc_json_field conversation_id 2>/dev/null || true)"
  fi
  if [ -z "$session" ]; then
    session="ppid-${PPID}"
  fi
  printf '%s:%s\n' "$host" "$session"
}

fc_owner_label() {
  printf 'Codex %s\n' "$(fc_owner_id)"
}

fc_feature_id_from_prompt() {
  local now
  now="$(date -u '+%Y%m%dT%H%M%S%NZ')"
  printf 'feature-%s-%s-%s\n' "$now" "$PPID" "$RANDOM"
}

fc_squash_text() {
  tr '\n' ' ' | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//'
}

fc_feature_title_from_prompt() {
  local title
  title="$(fc_prompt_text 2>/dev/null | fc_squash_text | cut -c 1-80)"
  if [ -n "$title" ]; then
    printf '%s\n' "$title"
  else
    printf 'Untitled feature challenge\n'
  fi
}

fc_feature_summary_from_prompt() {
  local summary
  summary="$(fc_prompt_text 2>/dev/null | fc_squash_text | cut -c 1-200)"
  printf '%s\n' "$summary"
}

fc_state_file_for_id() {
  local feature_id
  feature_id="$1"
  case "$feature_id" in
    *[!A-Za-z0-9._-]*|'') return 1 ;;
    *) printf '%s/%s.json\n' "$(fc_state_dir)" "$feature_id" ;;
  esac
}

fc_index_create_if_missing() {
  local index now
  index="$(fc_index_file)"
  [ -f "$index" ] && return 0
  now="$(fc_now)"
  fc_ensure_agents_dir
  jq -n --arg now "$now" \
    '{schemaVersion:1, activeFeatureId:null, activeByOwner:{}, features:[], createdAt:$now, updatedAt:$now}' >"$index"
}

fc_active_feature_id() {
  local index active owner has_owner_map
  index="$(fc_index_file)"
  [ -f "$index" ] || return 1
  owner="$(fc_owner_id)"
  active="$(jq -r --arg owner "$owner" '.activeByOwner[$owner] // .activeFeatureId // empty' "$index" 2>/dev/null || true)"
  has_owner_map="$(jq -r '((.activeByOwner // {}) | length) > 0' "$index" 2>/dev/null || true)"
  if [ -z "$active" ] && [ "$has_owner_map" != "true" ]; then
    active="$(jq -r '.activeFeatureId // empty' "$index" 2>/dev/null || true)"
  elif [ "$has_owner_map" = "true" ]; then
    active="$(jq -r --arg owner "$owner" '.activeByOwner[$owner] // empty' "$index" 2>/dev/null || true)"
  fi
  [ -n "$active" ] || return 1
  printf '%s\n' "$active"
}

fc_state_file() {
  local feature_id
  feature_id="$(fc_active_feature_id)" || return 1
  fc_state_file_for_id "$feature_id"
}

fc_state_exists() {
  local state
  state="$(fc_state_file 2>/dev/null)" || return 1
  [ -f "$state" ]
}

fc_state_get() {
  local key file
  key="$1"
  file="$(fc_state_file)" || return 1
  [ -f "$file" ] || return 1
  jq -r --arg key "$key" '.[$key] // empty' "$file"
}

fc_state_put() {
  local key value file tmp now
  key="$1"
  value="$2"
  file="$(fc_state_file)" || return 1
  tmp="${file}.tmp.$$"
  now="$(fc_now)"
  if ! jq --arg key "$key" --arg value "$value" --arg now "$now" \
    '.[$key] = $value | .updatedAt = $now' "$file" >"$tmp"; then
    rm -f -- "$tmp"
    return 1
  fi
  if ! mv "$tmp" "$file"; then
    rm -f -- "$tmp"
    return 1
  fi
  case "$key" in
    status|stage) fc_index_sync_active_feature ;;
  esac
}

fc_current_stage() {
  fc_state_get stage 2>/dev/null || printf 'none\n'
}

fc_workflow_active() {
  local status
  fc_state_exists || return 1
  status="$(fc_state_get status 2>/dev/null || true)"
  case "$status" in
    done|cancelled) return 1 ;;
    *) return 0 ;;
  esac
}

fc_decision() {
  local file
  file="$(fc_state_file)" || return 1
  [ -f "$file" ] || return 1
  jq -r '.decision.decision // empty' "$file"
}

fc_decision_allows_code() {
  local file
  file="$(fc_state_file)" || return 1
  [ -f "$file" ] || return 1
  jq -e '
    (.decision.decision == "Use Existing With Small Extension"
      or .decision.decision == "Reduce Scope"
      or .decision.decision == "Proceed")
    and .decision.status == "approved"
    and ((.decision.allowedNextStep // "") != "")
    and .problem.confirmedByUser == true
    and (.problem.status == "confirmed" or .problem.status == "complete")
    and .existingCapabilityCheck.status == "complete"
    and .fitCheck.status == "complete"
    and .challenge.status == "complete"
    and (.interview.status == "complete" or .interview.status == "skipped")
  ' "$file" >/dev/null
}

fc_artifact_has_confirmed_problem() {
  local file
  file="$(fc_state_file)" || return 1
  [ -f "$file" ] || return 1
  jq -e '.problem.confirmedByUser == true' "$file" >/dev/null
}

fc_create_state_if_missing() {
  local feature_id state index tmp now prompt title summary owner owner_label existing_feature_id
  feature_id="$1"
  state="$(fc_state_file_for_id "$feature_id")" || return 1
  index="$(fc_index_file)"
  tmp="${index}.tmp.$$"
  now="$(fc_now)"
  prompt="$(fc_prompt_text 2>/dev/null || true)"
  title="$(fc_feature_title_from_prompt)"
  summary="$(fc_feature_summary_from_prompt)"
  owner="$(fc_owner_id)"
  owner_label="$(fc_owner_label)"
  fc_ensure_agents_dir
  fc_lock_index || return $?
  fc_index_create_if_missing
  existing_feature_id="$(jq -r --arg title "$title" --arg summary "$summary" '
    [
      (.features // [])
      | map(if type == "string" then {featureId: ., title: ., summary: ""} else . end)
      | .[]
      | select(
          (.title // "") == $title
          or ((.summary // "") != "" and (.summary // "") == $summary)
          or any((.aliases // [])[]; . == $title or . == $summary)
        )
      | .featureId
    ][0] // empty
  ' "$index")"
  if [ -n "$existing_feature_id" ]; then
    if ! jq --arg featureId "$existing_feature_id" --arg owner "$owner" --arg now "$now" \
      '.activeFeatureId = $featureId
       | .activeByOwner[$owner] = $featureId
       | .updatedAt = $now' "$index" >"$tmp"; then
      rm -f -- "$tmp"
      fc_unlock_index
      return 1
    fi
    if ! mv "$tmp" "$index"; then
      rm -f -- "$tmp"
      fc_unlock_index
      return 1
    fi
    fc_unlock_index
    return 0
  fi
  if [ -f "$state" ]; then
    if ! jq --arg featureId "$feature_id" --arg owner "$owner" --arg now "$now" \
      '.activeFeatureId = $featureId
       | .activeByOwner[$owner] = $featureId
       | .updatedAt = $now' "$index" >"$tmp"; then
      rm -f -- "$tmp"
      fc_unlock_index
      return 1
    fi
    if ! mv "$tmp" "$index"; then
      rm -f -- "$tmp"
      fc_unlock_index
      return 1
    fi
    fc_unlock_index
    return 0
  fi
  if ! jq -n \
    --arg featureId "$feature_id" \
    --arg now "$now" \
    --argjson claimExpiresEpoch "$(fc_claim_expires_epoch)" \
    --arg prompt "$prompt" \
    --arg title "$title" \
    --arg summary "$summary" \
    --arg owner "$owner" \
    --arg ownerLabel "$owner_label" \
    '{
      schemaVersion: 1,
      featureId: $featureId,
      title: $title,
      summary: $summary,
      aliases: [],
      workClaim: {
        ownerId: $owner,
        ownerLabel: $ownerLabel,
        claimedAt: $now,
        updatedAt: $now,
        expiresAtEpoch: $claimExpiresEpoch
      },
      status: "in_progress",
      required: true,
      stage: "problem_gate",
      createdAt: $now,
      updatedAt: $now,
      requestedSolution: {statement: "", sourcePrompt: $prompt},
      problem: {status: "not_confirmed", confirmedByUser: false, statement: "", questions: []},
      existingCapabilityCheck: {status: "not_started", findings: [], conclusion: ""},
      fitCheck: {status: "not_started", architectureFit: "", productFit: "", constraints: []},
      challenge: {status: "not_started", objections: [], alternatives: []},
      interview: {status: "not_started", openQuestions: [], answers: []},
      decision: {status: "not_started", decision: null, reason: "", allowedNextStep: ""}
    }' >"$state"; then
    rm -f -- "$state"
    fc_unlock_index
    return 1
  fi
  if ! jq \
    --arg featureId "$feature_id" \
    --arg title "$title" \
    --arg summary "$summary" \
    --arg owner "$owner" \
    --arg ownerLabel "$owner_label" \
    --arg now "$now" \
    '.activeFeatureId = $featureId
     | .activeByOwner[$owner] = $featureId
     | .updatedAt = $now
     | .features = ((.features // []) | map(
         if type == "string" then
           {
             featureId: .,
             title: .,
             summary: "",
             aliases: [],
             status: "unknown",
             stage: "unknown",
             updatedAt: $now
           }
         else . end
       ))
     | if any(.features[]; .featureId == $featureId) then
         .features |= map(
           if .featureId == $featureId then
             . + {
               title: $title,
               summary: $summary,
               status: "in_progress",
               stage: "problem_gate",
               workOwner: $ownerLabel,
               updatedAt: $now
             }
           else . end
         )
       else
         .features += [{
           featureId: $featureId,
           title: $title,
           summary: $summary,
           aliases: [],
           status: "in_progress",
           stage: "problem_gate",
           workOwner: $ownerLabel,
           createdAt: $now,
           updatedAt: $now
         }]
       end' \
    "$index" >"$tmp"; then
    rm -f -- "$tmp" "$state"
    fc_unlock_index
    return 1
  fi
  if ! mv "$tmp" "$index"; then
    rm -f -- "$tmp" "$state"
    fc_unlock_index
    return 1
  fi
  fc_unlock_index
}

fc_set_required() {
  local feature_id
  feature_id="$(fc_feature_id_from_prompt)"
  fc_create_state_if_missing "$feature_id"
}

fc_active_feature_title() {
  local index feature_id
  index="$(fc_index_file)"
  feature_id="$(fc_active_feature_id)" || return 1
  [ -f "$index" ] || return 1
  jq -r --arg featureId "$feature_id" '
    (.features // [])
    | map(if type == "string" then {featureId: ., title: .} else . end)
    | map(select(.featureId == $featureId))
    | .[0].title // $featureId
  ' "$index"
}

fc_feature_list_summary() {
  local index
  index="$(fc_index_file)"
  [ -f "$index" ] || return 1
  jq -r '
    (.features // [])
    | map(if type == "string" then {featureId: ., title: ., summary: "", status: "unknown", stage: "unknown"} else . end)
    | map("- " + (.title // .featureId) + " [" + (.status // "unknown") + "/" + (.stage // "unknown") + "]" + (if (.summary // "") != "" then ": " + .summary else "" end))
    | join("\n")
  ' "$index"
}

fc_matching_feature_ids_for_prompt() {
  local index text
  index="$(fc_index_file)"
  [ -f "$index" ] || return 1
  text="$(fc_prompt_text 2>/dev/null | fc_squash_text)"
  [ -n "$text" ] || return 1
  jq -r --arg text "$text" '
    def normalize: ascii_downcase;
    def tokens:
      normalize
      | gsub("[^[:alnum:]_]+"; " ")
      | split(" ")
      | map(select(length >= 4))
      | map(select(. != "добавь" and . != "сделай" and . != "вернись" and . != "продолжи" and . != "реализуй"));
    ($text | normalize) as $needle |
    ($text | tokens) as $tokens |
    (.features // [])
    | map(if type == "string" then {featureId: ., title: ., summary: "", aliases: []} else . end)
    | .[]
    | . as $feature |
    (([($feature.title // ""), ($feature.summary // "")] + ($feature.aliases // [])) | map(normalize)) as $haystacks |
    select(
      any($haystacks[]; . as $haystack | $haystack != "" and ($needle == $haystack or ($haystack | contains($needle)) or ($needle | contains($haystack))))
      or (
        ($tokens | length) > 0
        and any($tokens[]; . as $token | any($haystacks[]; . as $haystack | $haystack | contains($token)))
      )
    )
    | .featureId
  ' "$index"
}

fc_set_active_feature_id() {
  local feature_id index tmp now owner
  feature_id="$1"
  index="$(fc_index_file)"
  [ -f "$index" ] || return 1
  tmp="${index}.tmp.$$"
  now="$(fc_now)"
  owner="$(fc_owner_id)"
  fc_lock_index || return $?
  if ! jq -e --arg featureId "$feature_id" 'any((.features // [])[]; (if type == "string" then . else .featureId end) == $featureId)' "$index" >/dev/null; then
    fc_unlock_index
    return 1
  fi
  if ! jq --arg featureId "$feature_id" --arg owner "$owner" --arg now "$now" \
    '.activeFeatureId = $featureId
     | .activeByOwner[$owner] = $featureId
     | .updatedAt = $now' "$index" >"$tmp"; then
    rm -f -- "$tmp"
    fc_unlock_index
    return 1
  fi
  if ! mv "$tmp" "$index"; then
    rm -f -- "$tmp"
    fc_unlock_index
    return 1
  fi
  fc_unlock_index
}

fc_select_feature_from_prompt() {
  local matches count selected
  matches="$(fc_matching_feature_ids_for_prompt 2>/dev/null || true)"
  count="$(printf '%s\n' "$matches" | sed '/^$/d' | wc -l | tr -d ' ')"
  case "$count" in
    0) return 1 ;;
    1)
      selected="$(printf '%s\n' "$matches" | sed '/^$/d' | head -n 1)"
      fc_set_active_feature_id "$selected"
      ;;
    *)
      # shellcheck disable=SC2034 # Read by hook entrypoints after sourcing this library.
      FC_MATCH_CONFLICT="$(fc_feature_list_summary 2>/dev/null || true)"
      return 2
      ;;
  esac
}

fc_index_sync_active_feature() {
  local index state feature_id tmp now owner_label
  index="$(fc_index_file)"
  state="$(fc_state_file)" || return 1
  feature_id="$(fc_active_feature_id)" || return 1
  [ -f "$index" ] || return 1
  [ -f "$state" ] || return 1
  tmp="${index}.tmp.$$"
  now="$(fc_now)"
  owner_label="$(jq -r '.workClaim.ownerLabel // empty' "$state")"
  fc_lock_index || return $?
  if ! jq \
    --arg featureId "$feature_id" \
    --arg now "$now" \
    --arg ownerLabel "$owner_label" \
    --slurpfile state "$state" \
    '.updatedAt = $now
     | .features = ((.features // []) | map(
         if type == "string" then
           {featureId: ., title: ., summary: "", aliases: [], status: "unknown", stage: "unknown", updatedAt: $now}
         else . end
       ))
     | .features |= map(
         if .featureId == $featureId then
           . + {
             title: ($state[0].title // .title // $featureId),
             summary: ($state[0].summary // .summary // ""),
             aliases: ($state[0].aliases // .aliases // []),
             status: ($state[0].status // .status // "unknown"),
             stage: ($state[0].stage // .stage // "unknown"),
             workOwner: (if $ownerLabel == "" then (.workOwner // "") else $ownerLabel end),
             updatedAt: $now
           }
         else . end
       )' \
    "$index" >"$tmp"; then
    rm -f -- "$tmp"
    fc_unlock_index
    return 1
  fi
  if ! mv "$tmp" "$index"; then
    rm -f -- "$tmp"
    fc_unlock_index
    return 1
  fi
  fc_unlock_index
}

fc_claim_active_feature() {
  local index state feature_id tmp_state tmp_index now owner owner_label existing_owner existing_label existing_expires claim_expires
  index="$(fc_index_file)"
  state="$(fc_state_file)" || return 1
  feature_id="$(fc_active_feature_id)" || return 1
  [ -f "$index" ] || return 1
  [ -f "$state" ] || return 1
  tmp_state="${state}.tmp.$$"
  tmp_index="${index}.tmp.$$"
  now="$(fc_now)"
  owner="$(fc_owner_id)"
  owner_label="$(fc_owner_label)"
  claim_expires="$(fc_claim_expires_epoch)"
  fc_lock_index || return $?
  existing_owner="$(jq -r '.workClaim.ownerId // empty' "$state")"
  existing_label="$(jq -r '.workClaim.ownerLabel // .workClaim.ownerId // empty' "$state")"
  existing_expires="$(jq -r '.workClaim.expiresAtEpoch // empty' "$state")"
  if [ -n "$existing_owner" ] && [ "$existing_owner" != "$owner" ]; then
    if [ -z "$existing_expires" ]; then
      # shellcheck disable=SC2034 # Read by hook entrypoints after sourcing this library.
      FC_CLAIM_CONFLICT="Feature is already claimed by ${existing_label} and has no expiry metadata. Ask the user to hand it over explicitly."
      fc_unlock_index
      return 76
    elif [ "$existing_expires" -le "$(fc_epoch)" ] 2>/dev/null; then
      :
    else
      # shellcheck disable=SC2034 # Read by hook entrypoints after sourcing this library.
      FC_CLAIM_CONFLICT="Feature is already claimed by ${existing_label}. Choose another feature or ask the user to hand it over."
      fc_unlock_index
      return 76
    fi
  fi
  if ! jq --arg owner "$owner" --arg ownerLabel "$owner_label" --arg now "$now" --argjson claimExpiresEpoch "$claim_expires" \
    '.workClaim = {
       ownerId: $owner,
       ownerLabel: $ownerLabel,
       claimedAt: (if (.workClaim.ownerId // "") == $owner then (.workClaim.claimedAt // $now) else $now end),
       updatedAt: $now,
       expiresAtEpoch: $claimExpiresEpoch
     }
     | .updatedAt = $now' "$state" >"$tmp_state"; then
    rm -f -- "$tmp_state"
    fc_unlock_index
    return 1
  fi
  if ! mv "$tmp_state" "$state"; then
    rm -f -- "$tmp_state"
    fc_unlock_index
    return 1
  fi
  if ! jq --arg featureId "$feature_id" --arg ownerLabel "$owner_label" --arg now "$now" \
    '.updatedAt = $now
     | .features = ((.features // []) | map(
         if type == "string" then
           {featureId: ., title: ., summary: "", aliases: [], status: "unknown", stage: "unknown", updatedAt: $now}
         else . end
       ))
     | .features |= map(
         if .featureId == $featureId then
           . + {workOwner: $ownerLabel, updatedAt: $now}
         else . end
       )' "$index" >"$tmp_index"; then
    rm -f -- "$tmp_index"
    fc_unlock_index
    return 1
  fi
  if ! mv "$tmp_index" "$index"; then
    rm -f -- "$tmp_index"
    fc_unlock_index
    return 1
  fi
  fc_unlock_index
}

fc_prompt_text() {
  fc_require_jq || return 1
  jq -r '.prompt // ""' <<<"$FC_PAYLOAD"
}

fc_prompt_looks_like_feature_request() {
  local text
  text="$(fc_prompt_text | tr '[:upper:]' '[:lower:]')"
  printf '%s' "$text" | grep -Eiq \
    'добавь|реализуй|сделай поддержку|добавить поддержку|нов(ая|ую) фич|нов(ая|ую) возможност|измен(и|ить).*поведен|миграц|рефактор|архитектур|add .*support|implement|new feature|change .*behavior|migration|refactor|architecture'
}

fc_tool_name() {
  fc_json_field tool_name
}

fc_tool_command() {
  fc_require_jq || return 1
  jq -r '.tool_input.command // ""' <<<"$FC_PAYLOAD"
}

fc_tool_input_text() {
  fc_require_jq || return 1
  jq -r '.tool_input | tostring' <<<"$FC_PAYLOAD"
}

fc_patch_paths_are_only_feature_challenge_state() {
  local patch records action path active_rel
  active_rel="$(fc_active_state_rel_file)" || return 1
  patch="$(jq -r '.tool_input.patch // empty' <<<"$FC_PAYLOAD")"
  [ -n "$patch" ] || return 1
  records="$(
    printf '%s\n' "$patch" |
      sed -n -E 's/^\*\*\* (Add|Update|Delete) File: (.*)$/\1\t\2/p; s/^\*\*\* Move to: (.*)$/Move\t\1/p'
  )"
  [ -n "$records" ] || return 1
  printf '%s\n' "$records" | while IFS="$(printf '\t')" read -r action path; do
    case "$action" in
      Update) ;;
      *) return 1 ;;
    esac
    [ "$path" = "$active_rel" ] || return 1
    fc_state_path_is_feature_json "$path" || return 1
  done
}

fc_direct_path_is_only_feature_challenge_state() {
  local path active_rel
  active_rel="$(fc_active_state_rel_file)" || return 1
  path="$(jq -r '.tool_input.file_path // .tool_input.path // empty' <<<"$FC_PAYLOAD")"
  [ "$path" = "$active_rel" ] || return 1
  fc_state_path_is_feature_json "$path"
}

fc_tool_updates_feature_challenge_state() {
  local tool
  tool="$(fc_tool_name)"
  case "$tool" in
    apply_patch) fc_patch_paths_are_only_feature_challenge_state ;;
    Write|Edit|MultiEdit) fc_direct_path_is_only_feature_challenge_state ;;
    *) return 1 ;;
  esac
}

fc_bash_command_is_read_only() {
  local command
  command="$(fc_tool_command | sed 's/^[[:space:]]*//')"
  [ -n "$command" ] || return 1
  # shellcheck disable=SC2016 # Literal shell metacharacter denylist.
  printf '%s' "$command" | grep -Eq '[;&|<>`$(){}]' && return 1
  printf '%s' "$command" | grep -Eq '(^|[[:space:]])--output(=|[[:space:]]|$)' && return 1
  printf '%s' "$command" | grep -Eq '[[:space:]](-exec|-delete|-ok|-fprint)([[:space:]]|$)' && return 1
  case "$command" in
    pwd|true|false) return 0 ;;
    ls|ls\ *|rg\ *|grep\ *|cat\ *|nl\ *|head\ *|tail\ *|wc\ *|stat\ *|file\ *|find\ *) return 0 ;;
    git\ status|git\ status\ *|git\ diff|git\ diff\ *|git\ show|git\ show\ *|git\ log|git\ log\ *|git\ branch|git\ branch\ *|git\ rev-parse|git\ rev-parse\ *|git\ ls-files|git\ ls-files\ *|git\ grep|git\ grep\ *) return 0 ;;
    *) return 1 ;;
  esac
}

fc_tool_is_write_like() {
  local tool
  tool="$(fc_tool_name)"
  case "$tool" in
    apply_patch|Write|Edit|MultiEdit) return 0 ;;
    Bash)
      fc_bash_command_is_read_only && return 1
      return 0
      ;;
    mcp__*create*|mcp__*update*|mcp__*delete*|mcp__*write*|mcp__*patch*)
      return 0
      ;;
    "") return 0 ;;
    *) return 0 ;;
  esac
}

fc_block_reason() {
  local stage feature_id title
  stage="$(fc_current_stage)"
  feature_id="$(fc_active_feature_id 2>/dev/null || printf 'unknown')"
  title="$(fc_active_feature_title 2>/dev/null || printf '%s' "$feature_id")"
  cat <<EOF
Feature Challenge is required before code changes.
Active feature: ${title}.
Current stage: ${stage}.
Complete the active feature JSON gate by gate and set decision.decision to one of:
Use Existing With Small Extension, Reduce Scope, Proceed.
EOF
}

fc_json_additional_context() {
  local event_name text
  event_name="$1"
  text="$2"
  jq -cn \
    --arg event "$event_name" \
    --arg text "$text" \
    '{hookSpecificOutput:{hookEventName:$event,additionalContext:$text}}'
}

fc_json_block_decision() {
  local reason
  reason="$1"
  jq -cn --arg reason "$reason" '{decision:"block",reason:$reason}'
}
