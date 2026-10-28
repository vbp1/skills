---
name: create-pr
description: |
  Full PR workflow: create branch, commit, push, create PR, assign labels, add to GitHub Project with Status/Priority/Size.
  Sets every field on its own: labels from the commit type and the linked task card, Priority from the card's
  project field or its own assessment, Size from diff LOC; asks only when no rule yields an answer.
  Triggers: "/create-pr", "create PR", "make PR", "open pull request", "ship PR",
  "отведи ветку", "создай PR", "отправь PR".
---

# Create PR Workflow

Full-cycle PR creation: branch, commit, push, PR, labels, GitHub Project fields. The skill decides labels and every project field on its own and reports where each value came from. It asks the user only in the cases each step lists explicitly.

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

Also resolve the default branch once (used by Step 7 size calculation):
```bash
default_branch=$(git symbolic-ref --short refs/remotes/origin/HEAD) \
  || { echo "origin/HEAD is not set; run: git remote set-head origin --auto" >&2; exit 1; }
default_branch=${default_branch#origin/}
```

### Step 5: Collect the task card

The task card is the issue (or issues) the PR implements, plus the local card file when the repo keeps one.

**5a.** Issues the PR closes:
```bash
gh pr view <number> --json closingIssuesReferences -q '[.closingIssuesReferences[].number]'
```

**5b.** Local card file: when the repo root has a `todos/` directory, find the `*.md` whose frontmatter line is `branch: <branch-name>`:
```bash
grep -lE "^branch: <branch-name>$" todos/*.md
```
Read the file. Add its `github_issue` number to the issue list from 5a. Note its `depends_on`/`blocked_by` lines and whether other cards list this card's `id` in their `depends_on`.

**5c. Find the project:**
```bash
bash <scripts>/gh-project.sh list-projects
```
If exactly one project, use it without asking. If multiple, ask user which one via `AskUserQuestion`.

**5d.** Read every issue from 5a–5b:
```bash
bash <scripts>/gh-project.sh issue-cards <project-number> <issue-number>...
```
Each output line is JSON: `number`, `title`, `body`, `labels`, `fields` (the issue's single-select values in that project, e.g. `{"Priority": "High"}`).

No issue and no card file → the card is empty; Steps 6 and 7 work from the commits, PR title and diff.

### Step 6: Labels (always automatic)

**6a.** Pick the PR type:
- the PR title has a conventional-commit prefix → its type (the title covers the whole PR, so it decides when commits mix `feat:` + `fix:`);
- no prefix → the type label on the card's issues (`type: bug` → `fix`, `type: feature` → `feat`, …);
- neither → judge from the diff: new behaviour → `feat`, a corrected defect → `fix`, only docs → `docs`, only tests → `test`, restructuring without behaviour change → `refactor`.

**6b.** Map the type to labels. The mapping below is the single source of truth — extend only with user permission.

| Commit prefix | Label(s) to apply |
| --- | --- |
| `fix:` / `fix(...)` | `type: bug` |
| `feat:` / `feat(...)` | `type: feature` |
| `chore(deps):` / `chore(deps-...)` / `fix(deps):` | `type: debt` + `dependencies` |
| `refactor:` / `chore:` / `perf:` / `style:` | `type: debt` |
| `docs:` | `type: docs` |
| `test:` | `type: test` |
| `revert:` | `type: bug` |

**6c.** Add the card issues' labels except workflow-state labels (`agent: …`, `planned`, `pause`, `not sure`, `duplicate` and the like) and type labels that contradict 6a.

**6d.** Fetch the repo's labels and match each wanted label case-insensitively:
```bash
bash <scripts>/gh-project.sh list-labels
```
A wanted label missing from the repo → take the existing label with the same meaning (`documentation` for `type: docs`, `bug` for `type: bug`). No label with that meaning → skip it and name it in the report. Never create labels.

**6e.** Apply:
```bash
gh pr edit <number> --add-label "label1" --add-label "label2"
```

### Step 7: GitHub Project fields

**7a. Add PR to project and get item ID** (project from 5c):
```bash
bash <scripts>/gh-project.sh add-item <project-number> <pr-url>
```

**7b. Get project fields:**
```bash
bash <scripts>/gh-project.sh get-fields <project-number>
```

Parse the JSON to find `Status`, `Priority`, `Size` fields and their options.

**7c. Decide Status (auto when possible):**

Pick the first matching option (case-insensitive, exact name) in this order:
1. `In review`
2. `Review`
3. `In progress`
4. `Backlog`

Apply silently. Only ask if none of the four candidates exist in the project's Status options.

**7d. Decide Size (auto from LOC):**

Compute changed lines relative to the default branch:
```bash
git fetch origin "$default_branch" --quiet
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

**7e. Decide Priority (card first, then own assessment):**

1. A card issue has `Priority` in `fields` → use it. Several issues with different values → the highest.
2. Otherwise assess from the card text, its issue labels and the diff; the first matching row wins:

| Priority | When |
| --- | --- |
| Critical | outage, data loss or corruption, security hole, broken default branch, hotfix |
| High | defect a user sees, regression, a fix for a broken release; or other cards `depends_on` this one / it unblocks `blocked_by` cards |
| Low | only docs, tests, refactoring, cleanup, style, or a dependency bump without a security fix |
| Medium | everything else: a regular feature or improvement |

3. Map the level to the project's Priority option by name (case-insensitive, exact or starts-with: `High`, `P1 - High`).
4. Ask via `AskUserQuestion` only when the project's Priority options do not correspond to the four levels (e.g. a custom scale) and no card issue carries a value. Put the recommended option first.

**7f. Set fields:**
For each field (Status, Size, Priority), extract the project ID, item ID, field ID, and option ID, then:
```bash
bash <scripts>/gh-project.sh set-field <project-id> <item-id> <field-id> <option-id>
```

### Step 8: Report

Output a single short summary:

- PR URL
- Labels: each applied label with its source (`commit type`, `card #<n>`, `nearest repo label for <wanted>`); skipped labels with the reason
- Project fields:
  - Status: `<value>` (auto / asked)
  - Size: `<bucket>` from `<LOC>` LOC (auto / asked)
  - Priority: `<value>` with its source — `card #<n>` or `assessed: <one-line reason>` (or `asked` with the reason)

Example:
```
✓ PR opened: https://github.com/.../pull/123
✓ Labels: type: feature (commit type), dependencies (card #879)
✓ Project "myorg/myrepo":
  · Status: In review (auto)
  · Size: M (auto, 247 LOC)
  · Priority: High (assessed: other cards depend on #879)
```
