---
name: create-pr
description: |
  Full PR workflow for Codex: inspect changes, create or reuse a branch, commit, push, open a GitHub pull request, assign labels, and add it to a GitHub Project with Status/Priority/Size fields. Use when the user asks "/create-pr", "create PR", "make PR", "open pull request", "ship PR", "отведи ветку", "создай PR", or "отправь PR".
metadata:
  short-description: Create a GitHub PR end to end
---

# Create PR Workflow

Full-cycle PR creation: branch, commit, push, PR, labels, and GitHub Project fields.

Use repo instructions first. In particular, preserve ignored files, avoid staging unrelated artifacts, and follow the repo's commit/PR language rules.

## Script Location

Helper script: replace `SKILL.md` in this file's path with `scripts/gh-project.sh`.

## Workflow

Execute steps sequentially. Each step depends on the previous.

### Step 1: Gather context

Run in parallel:

```bash
git status -u
git diff --stat
git log --oneline -5
```

If there are no changes, inform the user and stop.

### Step 2: Determine branch name

If already on a feature branch, not `main` or `master`, use it.

Otherwise, derive a branch name from the commit message context, for example `feat/short-description`, and create it:

```bash
git checkout -b <branch-name>
```

### Step 3: Commit

Analyze changes and draft a commit message following the repo's conventional commits style.

Stage relevant files explicitly. Prefer path-specific `git add` over `git add -A`. Do not force-add ignored files unless the user explicitly asks for that exact file.

Create the commit. Follow repository git conventions, including any rules that forbid AI signatures such as `Co-Authored-By`, "Generated with Claude", or similar text.

### Step 4: Push and create PR

```bash
git push -u origin <branch-name>
```

Create the PR with `gh pr create`. Draft a concise title under 70 characters and a body with `Summary` and `Test plan` sections. Capture the PR URL from output.

### Step 5: Ask for labels

Fetch available labels:

```bash
bash <scripts>/gh-project.sh list-labels
```

`request_user_input` supports up to 3 questions and 2-3 options per question. Labels often exceed this.

Strategy:

1. Print the full list of available labels as text output so the user can see all of them.
2. Use `request_user_input` with the 2-3 most relevant labels as options.
3. The client adds an `Other` option automatically; if the user enters label names manually, parse them as comma-separated names and trim whitespace.

Apply selected labels:

```bash
gh pr edit <number> --add-label "label1" --add-label "label2"
```

### Step 6: Ask for GitHub Project fields

Find projects:

```bash
bash <scripts>/gh-project.sh list-projects
```

If exactly one project is available, use it. If multiple projects are available, ask the user which project to use via `request_user_input` with up to 3 likely choices.

Add the PR to the project and get the item ID:

```bash
bash <scripts>/gh-project.sh add-item <project-number> <pr-url>
```

Get project fields:

```bash
bash <scripts>/gh-project.sh get-fields <project-number>
```

Parse the JSON to find `Status`, `Priority`, and `Size` fields and their options.

Ask for project fields via `request_user_input`. Because a single call supports up to 3 questions, ask `Status`, `Priority`, and `Size` together. For each field, present 2-3 likely options and rely on the automatic `Other` option for less common values.

Set each selected field:

```bash
bash <scripts>/gh-project.sh set-field <project-id> <item-id> <field-id> <option-id>
```

### Step 7: Report

Output final summary:

- PR URL
- labels applied
- project fields set: Status, Priority, Size
