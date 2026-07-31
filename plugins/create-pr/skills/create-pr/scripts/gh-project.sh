#!/usr/bin/env bash
# Helper script for GitHub Projects V2 operations.
# Usage:
#   gh-project.sh list-projects              — list user's projects (JSON)
#   gh-project.sh get-fields <project-number> — get project fields with options (JSON)
#   gh-project.sh find-item <project-number> <pr-url> — find item ID for a PR in project
#   gh-project.sh add-item <project-number> <pr-url> — add PR to project, print item ID
#   gh-project.sh set-field <project-id> <item-id> <field-id> <option-id> — set single-select field

set -euo pipefail

get_owner() {
  gh repo view --json owner -q '.owner.login' 2>/dev/null
}

cmd="${1:-}"
shift || true

case "$cmd" in
  list-projects)
    owner=$(get_owner)
    gh project list --owner "$owner" --format json
    ;;

  get-fields)
    project_number="${1:?project number required}"
    owner=$(get_owner)
    gh project field-list "$project_number" --owner "$owner" --format json
    ;;

  find-item)
    project_number="${1:?project number required}"
    pr_url="${2:?PR URL required}"
    owner=$(get_owner)
    # Search through all items for matching PR URL. gh has no "no limit" flag (and --limit 0 silently
    # falls back to the default 30), so use a large sentinel to fetch every item — a freshly-added PR
    # lands at the end and would be missed by a small limit.
    gh project item-list "$project_number" --owner "$owner" --format json --limit 100000 | \
      python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data.get('items', []):
    url = item.get('content', {}).get('url', '')
    if url == '$pr_url':
        print(item['id'])
        sys.exit(0)
print('')
"
    ;;

  add-item)
    project_number="${1:?project number required}"
    pr_url="${2:?PR URL required}"
    owner=$(get_owner)
    gh project item-add "$project_number" --owner "$owner" --url "$pr_url" >/dev/null 2>&1
    # Now find the item ID
    exec "$0" find-item "$project_number" "$pr_url"
    ;;

  set-field)
    project_id="${1:?project ID required}"
    item_id="${2:?item ID required}"
    field_id="${3:?field ID required}"
    option_id="${4:?option ID required}"
    gh project item-edit --project-id "$project_id" --id "$item_id" \
      --field-id "$field_id" --single-select-option-id "$option_id"
    ;;

  list-labels)
    gh label list --limit 100 --json name -q '.[].name' | sort
    ;;

  *)
    echo "Unknown command: $cmd" >&2
    echo "Usage: gh-project.sh {list-projects|get-fields|find-item|add-item|set-field|list-labels}" >&2
    exit 1
    ;;
esac
