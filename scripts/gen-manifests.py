#!/usr/bin/env python3
"""Regenerate every plugin manifest and both marketplace manifests.

The catalogue lives in the PLUGINS table below: one row per plugin, holding the
plugin name, display name, one-line description, the category each agent uses,
keywords, and which agent the skill was written for. Everything else is derived.

Usage:
    scripts/gen-manifests.py [--root DIR]

Writes:
    plugins/<name>/.claude-plugin/plugin.json   one per row (read by both agents)
    .claude-plugin/marketplace.json             catalogue for Claude Code
    .agents/plugins/marketplace.json            catalogue for Codex CLI

To add a skill: drop it into plugins/<name>/skills/<name>/, add a row to PLUGINS,
run this script, then verify with `claude plugin validate . --strict`.

Exit codes:
    0  manifests written
    1  a plugin listed in PLUGINS has no directory under plugins/
"""
import argparse
import json
import pathlib

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--root", default=pathlib.Path(__file__).resolve().parent.parent,
                    type=pathlib.Path, help="repository root (default: parent of scripts/)")
ROOT = parser.parse_args().root
AUTHOR = {"name": "Vadim Ponomarev", "url": "https://github.com/vbp1"}
REPO = "https://github.com/vbp1/skills"
LICENSE = "Apache-2.0"
VERSION = "1.0.1"  # bump on every published change; agents keep a pinned version cached

# name, displayName, description, claude category, codex category, keywords, agent
PLUGINS = [
    ("audio-restore", "Audio Restore",
     "Restore muffled or low-quality recordings: stem separation, EQ correction, high-frequency recovery.",
     "media", "Productivity", ["audio", "restoration", "ffmpeg", "eq"], "claude"),
    ("break-it", "Break It",
     "Adversarial test pass: write tests that try to falsify a change, keep only the ones that catch real defects.",
     "testing", "Coding", ["testing", "adversarial", "regression"], "codex"),
    ("claude-review", "Claude Review",
     "Cross-agent review workflow: Codex implements, Claude Code reviews, findings loop back until resolved.",
     "development", "Coding", ["code-review", "cross-agent", "workflow"], "codex"),
    ("cloakbrowser", "CloakBrowser (Claude Code)",
     "Inspect web pages in a local stealth Chromium: screenshots, client-side JS errors, failed requests, long-task timings. Claude Code variant.",
     "development", "Coding", ["browser", "screenshots", "devtools", "debugging"], "claude"),
    ("cloakbrowser-codex", "CloakBrowser (Codex CLI)",
     "Inspect web pages in a local stealth Chromium: screenshots and visual UI checks. Codex CLI variant.",
     "development", "Coding", ["browser", "screenshots", "devtools"], "codex"),
    ("codex-genimage", "Codex Image Generation",
     "Generate images through the Codex CLI built-in image tool, billed via existing Codex auth instead of a separate API key.",
     "media", "Productivity", ["images", "codex", "generation"], "claude"),
    ("create-pr", "Create PR (Claude Code)",
     "Branch, commit, push, open the pull request, then set labels and project fields in one pass. Claude Code variant.",
     "development", "Coding", ["git", "github", "pull-request", "workflow"], "claude"),
    ("create-pr-codex", "Create PR (Codex CLI)",
     "Branch, commit, push, open the pull request, then set labels and project fields in one pass. Codex CLI variant.",
     "development", "Coding", ["git", "github", "pull-request", "workflow"], "codex"),
    ("decision-playground", "Decision Playground",
     "Turn a long list of choices into a self-contained interactive HTML page and read the answers back as structured data.",
     "planning", "Productivity", ["html", "decisions", "interactive"], "codex"),
    ("feature-challenge-workflow", "Feature Challenge Workflow",
     "Challenge a feature request before any code: confirm the real problem, check existing capability, weigh alternatives, pass decision gates.",
     "planning", "Productivity", ["product", "planning", "hooks", "gates"], "codex"),
    ("feature-plan-storyboard", "Feature Plan Storyboard",
     "Plan a feature, verify every claim against the current code, then build an interactive user-story storyboard page.",
     "planning", "Productivity", ["planning", "storyboard", "html", "review"], "claude"),
    ("langfuse-debug", "Langfuse Debug",
     "Investigate agent runs recorded in Langfuse: failed sessions, token usage, tool-call patterns.",
     "observability", "Ops", ["langfuse", "tracing", "llm", "debugging"], "claude"),
    ("phased-task-delivery", "Phased Task Delivery",
     "Run a complex task through explicit phases: plan documents, checklists, review gates, per-phase commits, final full-suite validation.",
     "workflow", "Coding", ["workflow", "planning", "delivery"], "codex"),
    ("remote-ssh-workspace", "Remote SSH Workspace",
     "Make a remote host behave like a local worktree: SSH multiplexing, sshfs mounts, detached long jobs with logs.",
     "ops", "Ops", ["ssh", "remote", "sshfs", "ops"], "codex"),
    ("rust-code-review", "Rust Code Review",
     "Review Rust for hazards that survive cargo build, cargo test and clippy: async, unsafe, lifetimes, lock and transaction flows.",
     "development", "Coding", ["rust", "code-review", "async", "unsafe"], "codex"),
    ("simple-tech-writing", "Simple Technical Writing",
     "Rewrite technical text so a tired reader cannot misread it: ASD-STE100 structural rules plus a Russian rule set.",
     "writing", "Productivity", ["writing", "documentation", "ste", "russian"], "claude"),
    ("technical-premortem", "Technical Pre-Mortem",
     "Assess a planned change before it is written: blast radius, rollback plan, pre-flight checklist, go/no-go verdict.",
     "planning", "Productivity", ["risk", "planning", "premortem"], "claude"),
    ("user-clear-communication", "User-Clear Communication",
     "Write user-facing replies, statuses and reports that stay readable: plain wording, explicit outcomes, no filler.",
     "writing", "Productivity", ["communication", "writing", "russian"], "codex"),
    ("youtube-transcript", "YouTube Transcript",
     "Pull the transcript of a YouTube video, with or without timestamps.",
     "media", "Productivity", ["youtube", "transcript", "subtitles"], "claude"),
]

if not (ROOT / "plugins").is_dir():
    raise SystemExit(f"no plugins/ directory under {ROOT}; pass the repository root via --root")

claude_entries, codex_entries = [], []

for name, display, desc, cat, codex_cat, keywords, agent in PLUGINS:
    pdir = ROOT / "plugins" / name
    if not pdir.is_dir():
        raise SystemExit(f"missing plugin directory: {pdir}")

    manifest = {
        "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
        "name": name,
        "displayName": display,
        "version": VERSION,
        "description": desc,
        "author": AUTHOR,
        "homepage": REPO,
        "repository": REPO,
        "license": LICENSE,
        "keywords": keywords,
    }
    (pdir / ".claude-plugin").mkdir(exist_ok=True)
    (pdir / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    claude_entries.append({
        "name": name,
        "source": f"./plugins/{name}",
        "description": desc,
        "version": VERSION,
        "category": cat,
        "keywords": keywords,
        "license": LICENSE,
    })
    codex_entries.append({
        "name": name,
        "source": {"source": "local", "path": f"./plugins/{name}"},
        "description": desc,
        "version": VERSION,
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": codex_cat,
        "license": LICENSE,
    })

MARKETPLACE_DESC = "Vadim Ponomarev's agent skills for Claude Code and OpenAI Codex CLI."

(ROOT / ".claude-plugin").mkdir(exist_ok=True)
(ROOT / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
    "$schema": "https://json.schemastore.org/claude-code-marketplace.json",
    "name": "vbp1-skills",
    "description": MARKETPLACE_DESC,
    "owner": AUTHOR,
    "metadata": {"description": MARKETPLACE_DESC, "version": VERSION},
    "plugins": claude_entries,
}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

(ROOT / ".agents" / "plugins").mkdir(parents=True, exist_ok=True)
(ROOT / ".agents" / "plugins" / "marketplace.json").write_text(json.dumps({
    "name": "vbp1-skills",
    "interface": {"displayName": "vbp1 skills"},
    "metadata": {"description": MARKETPLACE_DESC, "version": VERSION},
    "plugins": codex_entries,
}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(f"wrote {len(PLUGINS)} plugin manifests + 2 marketplace manifests")
