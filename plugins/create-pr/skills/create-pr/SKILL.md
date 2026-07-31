---
name: create-pr
description: |
  Full PR workflow: create branch, commit, push, create PR, assign labels, add to GitHub Project with Status/Priority/Size.
  Auto-derives labels from the conventional-commit type and Size from diff LOC; asks the user only when context is ambiguous.
  Triggers: "/create-pr", "create PR", "make PR", "open pull request", "ship PR",
  "отведи ветку", "создай PR", "отправь PR".
---

# Create PR Workflow

Full-cycle PR creation: branch, commit, push, PR, labels, GitHub Project fields. The skill is biased toward acting on its own — it only asks the user when it cannot derive a safe answer from the context.

## Script Location

Helper script: replace `SKILL.md` in this file's path with `scripts/gh-project.sh`.

## Workflow

Execute steps sequentially. Each step depends on the previous.

### Step 1: Gather context

Run in parallel:
```
git status -u
git diff --stat
git log --oneline -5
```

If there are no changes (no modified/untracked files), inform the user and stop.

### Step 2: Determine branch name

If already on a feature branch (not `main`/`master`), use it.
Otherwise, derive a branch name from the commit message context (e.g., `feat/short-description`).
Create and checkout the branch:
```
git checkout -b <branch-name>
```

### Step 3: Commit

Analyze changes and draft a commit message following the repo's conventional commits style.
Stage relevant files (prefer specific files over `git add -A`).
Create the commit. Follow any CLAUDE.md git conventions (no Co-Authored-By, no "Generated with Claude", etc.).

### Step 4: Push and create PR

```
git push -u origin <branch-name>
```

Create PR with `gh pr create`. Draft a concise title (<70 chars) and body with Summary + Test plan sections.
Capture the PR URL and PR number from output.

Also resolve the default branch once (used by Step 6 size calculation):
```bash
default_branch=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo main)
```

### Step 5: Auto-apply labels

Goal: don't ask the user when the conventional-commit type maps unambiguously to an existing repo label.

**5a.** Take the HEAD commit subject (the same one used for the PR title) and detect its conventional-commit type with `type[scope]:` regex. The mapping below is the single source of truth — extend only with user permission.

| Commit prefix | Label(s) to apply |
| --- | --- |
| `fix:` / `fix(...)` | `type: bug` |
| `feat:` / `feat(...)` | `type: feature` |
| `chore(deps):` / `chore(deps-...)` / `fix(deps):` | `type: debt` + `dependencies` |
| `refactor:` / `chore:` / `perf:` / `style:` | `type: debt` |
| `docs:` | `type: docs` |
| `test:` | `type: test` |
| `revert:` | `type: bug` |

If the head commit has no conventional prefix OR the PR spans commits of multiple distinct types (e.g. `feat:` + `fix:`), treat it as ambiguous and ask.

**5b.** Fetch the repo's actual labels:
```bash
bash <scripts>/gh-project.sh list-labels
```

For each mapped label from 5a, check whether it appears in the list (case-insensitive exact match). Build two sets:
- `to_apply` — mapped labels that exist in the repo
- `missing` — mapped labels that do NOT exist in the repo

**5c.** Apply labels without asking when there is no ambiguity:
```bash
gh pr edit <number> --add-label "label1" --add-label "label2"
```

**5d.** Ask the user only in these cases (single `AskUserQuestion` call, `multiSelect: true`):
- The head commit has no conventional prefix.
- The PR mixes multiple types (`feat:` + `fix:` + …).
- The mapping yielded labels that don't exist in the repo (`missing` non-empty) — present the repo's label list (up to 4 most likely matches) and let the user pick.

When asking, list the repo's available labels in the message so the user can pick via "Other" if the 4 suggestions don't fit.

**5e.** Briefly print which labels were applied (`✓ type: bug, dependencies`) and which path was used (auto vs. asked). Do NOT show this as a separate question — it's part of the final report in Step 7.

### Step 6: GitHub Project fields

**6a. Find the project:**
```bash
bash <scripts>/gh-project.sh list-projects
```
If exactly one project, use it without asking. If multiple, ask user which one via `AskUserQuestion`.

**6b. Add PR to project and get item ID:**
```bash
bash <scripts>/gh-project.sh add-item <project-number> <pr-url>
```

**6c. Get project fields:**
```bash
bash <scripts>/gh-project.sh get-fields <project-number>
```

Parse the JSON to find `Status`, `Priority`, `Size` fields and their options.

**6d. Decide Status (auto when possible):**

Pick the first matching option (case-insensitive, exact name) in this order:
1. `In review`
2. `Review`
3. `In progress`
4. `Backlog`

Apply silently. Only ask if none of the four candidates exist in the project's Status options.

**6e. Decide Size (auto from LOC):**

Compute changed lines relative to the default branch:
```bash
git fetch origin "$default_branch" --quiet 2>/dev/null || true
shortstat=$(git diff --shortstat "origin/$default_branch...HEAD")
# Example output: " 3 files changed, 247 insertions(+), 12 deletions(-)"
loc=$(echo "$shortstat" | awk '{
  ins=0; del=0;
  for (i=1; i<=NF; i++) {
    if ($i ~ /insertion/) ins=$(i-1);
    if ($i ~ /deletion/)  del=$(i-1);
  }
  print ins + del;
}')
```

Bucket by LOC:

| Bucket | LOC range |
| --- | --- |
| XS | ≤ 30 |
| S  | 31 – 150 |
| M  | 151 – 500 |
| L  | 501 – 2000 |
| XL | > 2000 |

Find the project's Size option whose name matches the bucket (case-insensitive, exact match or starts-with — e.g. project may use `XS`, `S - Small`, etc.). Apply silently. Only ask if no project option matches the computed bucket.

**6f. Ask Priority (always):**

Priority is a business call; never auto-fill. Present up to 4 options (`Critical`, `High`, `Medium`, `Low` typically fits) via `AskUserQuestion`. If the project's Priority field has more than 4 options, present the 4 most common.

**6g. Set fields:**
For each field (Status, Size, Priority), extract the project ID, item ID, field ID, and option ID, then:
```bash
bash <scripts>/gh-project.sh set-field <project-id> <item-id> <field-id> <option-id>
```

### Step 7: Report

Output a single short summary:

- PR URL
- Labels (applied + how: `auto` or `asked`)
- Project fields:
  - Status: `<value>` (auto / asked)
  - Size: `<bucket>` from `<LOC>` LOC (auto / asked)
  - Priority: `<value>` (asked)

Example:
```
✓ PR opened: https://github.com/.../pull/123
✓ Labels (auto): type: feature
✓ Project "myorg/myrepo":
  · Status: In review (auto)
  · Size: M (auto, 247 LOC)
  · Priority: Medium (asked)
```

If anything fell back to "asked" because of ambiguity, mention the reason in one line so the user sees why the skill didn't auto-resolve it.
