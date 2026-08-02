#!/usr/bin/env python3
"""Regenerate every plugin manifest and both marketplace manifests.

The catalogue lives in the PLUGINS table below: one row per plugin, holding the
plugin name, display name, one-line description, the category each agent uses,
keywords, and which agent the skill was written for. Two side tables carry what
does not fit a row:

    VERSIONS   one version per plugin, bumped independently. Required for every
               plugin — a missing entry stops the run rather than defaulting,
               because an unversioned publish fails silently at the user's end.
    EXTRAS     manifest fields only a few plugins need: a hook manifest path,
               plugin dependencies, and whether to leave the plugin out of the
               Codex catalogue because it is built on Claude Code components.

Usage:
    scripts/gen-manifests.py [--root DIR]

Writes:
    plugins/<name>/.claude-plugin/plugin.json   one per row (read by both agents)
    .claude-plugin/marketplace.json             catalogue for Claude Code
    .agents/plugins/marketplace.json            catalogue for Codex CLI

To add a skill: drop it into plugins/<name>/skills/<name>/, add a row to PLUGINS
and a version to VERSIONS, run this script, then verify with
`claude plugin validate . --strict`.

To release a change: bump that plugin's entry in VERSIONS. Users receive nothing
until the number moves.

Exit codes:
    0  manifests written
    1  a plugin listed in PLUGINS has no directory, or no version in VERSIONS
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from check_versions import format_report, stale_plugins  # noqa: E402

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--root", default=pathlib.Path(__file__).resolve().parent.parent,
                    type=pathlib.Path, help="repository root (default: parent of scripts/)")
parser.add_argument("--allow-stale", action="store_true",
                    help="write manifests even when a plugin changed without a version bump")
args = parser.parse_args()
ROOT = args.root
AUTHOR = {"name": "Vadim Ponomarev", "url": "https://github.com/vbp1"}
REPO = "https://github.com/vbp1/skills"
LICENSE = "Apache-2.0"
MARKETPLACE_VERSION = "1.1.0"  # the catalogue itself; bump when the plugin roster changes

# One version per plugin, bumped independently — bump only what you touched.
#
# Claude Code caches an installed plugin by this exact string: a user receives a change only
# after the number moves, and `claude plugin update` answers "already at the latest version"
# until it does. So a forgotten bump is a silent non-delivery, not an error. Follow semver:
# MAJOR for a breaking change, MINOR for new behaviour, PATCH for a fix.
#
# `claude plugin tag` cuts a {name}--v{version} tag per plugin and checks that plugin.json
# and the marketplace entry agree, which both come from here.
VERSIONS = {
    "audio-restore": "1.0.1",
    "break-it": "1.0.1",
    "claude-review": "1.0.1",
    "cloakbrowser": "1.0.1",
    "cloakbrowser-codex": "1.0.1",
    "codex-genimage": "1.0.1",
    "create-pr": "1.0.1",
    "create-pr-codex": "1.0.1",
    "decision-playground": "1.0.1",
    "feature-challenge-workflow": "1.0.1",
    "feature-plan-storyboard": "1.0.1",
    "langfuse-debug": "1.0.1",
    "phased-task-delivery": "1.0.1",
    "remote-ssh-workspace": "1.0.1",
    "review-panel": "1.0.2",
    "rust-code-review": "1.0.1",
    "simple-tech-writing": "1.0.1",
    "technical-premortem": "1.0.1",
    "user-clear-communication": "1.0.1",
    "youtube-transcript": "1.0.1",
}

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
    ("review-panel", "Review Panel",
     "Parallel read-only review tracks over a diff: mechanical triage, one agent per lens, adversarial verification, persisted rounds, re-review until clean.",
     "development", "Coding", ["code-review", "agents", "pre-commit", "quality"], "claude"),
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

# Manifest fields the PLUGINS table does not carry, for the few plugins that need them.
# Everything absent from here keeps the plain shape, so adding a field costs one entry
# rather than a column on all rows.
#   hooks         path to an ADDITIONAL hook manifest. The standard hooks/hooks.json is
#                 loaded on its own, so naming it here loads it twice and the plugin dies
#                 with "Duplicate hooks file detected".
#   dependencies  other plugins this one requires. An unresolved dependency disables the
#                 whole plugin, and a dependency in another marketplace is refused unless
#                 the root marketplace allowlists it — so this is for hard requirements
#                 only. An optional companion belongs in the documentation, degrading at
#                 runtime instead.
#   claudeOnly    leave out of the Codex catalogue — the plugin is built on Claude Code
#                 agents and hooks, which Codex has no equivalent for, so listing it
#                 there would offer an install that cannot work
EXTRAS = {
    "review-panel": {
        "claudeOnly": True,
    },
}

if not (ROOT / "plugins").is_dir():
    raise SystemExit(f"no plugins/ directory under {ROOT}; pass the repository root via --root")

# Before writing anything: a plugin whose files moved since its version was tagged would be
# published under a number users already hold, so the change would reach nobody and nothing
# would say so. Checked against VERSIONS rather than the manifests on disk, which still carry
# the previous number during a bump. Stop here, before any file is touched.
stale = stale_plugins(ROOT, VERSIONS)
if stale and not args.allow_stale:
    raise SystemExit(
        f"{len(stale)} plugin(s) changed without a version bump — nothing was written:\n"
        + format_report(stale)
        + "\n  Pass --allow-stale to write anyway (the change will not reach installed copies)."
    )
if stale:
    print(f"--allow-stale: writing with {len(stale)} unbumped plugin(s): "
          f"{', '.join(e['plugin'] for e in stale)}")

claude_entries, codex_entries = [], []

for name, display, desc, cat, codex_cat, keywords, agent in PLUGINS:
    pdir = ROOT / "plugins" / name
    if not pdir.is_dir():
        raise SystemExit(f"missing plugin directory: {pdir}")
    # A missing entry stops the run rather than defaulting: an unversioned plugin would be
    # published, and the omission would only show up as users never receiving its changes.
    if name not in VERSIONS:
        raise SystemExit(f"no version recorded for '{name}' — add it to VERSIONS. Nothing was written.")
    version = VERSIONS[name]

    manifest = {
        "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
        "name": name,
        "displayName": display,
        "version": version,
        "description": desc,
        "author": AUTHOR,
        "homepage": REPO,
        "repository": REPO,
        "license": LICENSE,
        "keywords": keywords,
    }
    extra = EXTRAS.get(name, {})
    for key in ("hooks", "dependencies"):
        if key in extra:
            manifest[key] = extra[key]
    (pdir / ".claude-plugin").mkdir(exist_ok=True)
    (pdir / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    claude_entries.append({
        "name": name,
        "source": f"./plugins/{name}",
        "description": desc,
        "version": version,
        "category": cat,
        "keywords": keywords,
        "license": LICENSE,
    })
    if not extra.get("claudeOnly"):
        codex_entries.append({
            "name": name,
            "source": {"source": "local", "path": f"./plugins/{name}"},
            "description": desc,
            "version": version,
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
    "metadata": {"description": MARKETPLACE_DESC, "version": MARKETPLACE_VERSION},
    "plugins": claude_entries,
}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

(ROOT / ".agents" / "plugins").mkdir(parents=True, exist_ok=True)
(ROOT / ".agents" / "plugins" / "marketplace.json").write_text(json.dumps({
    "name": "vbp1-skills",
    "interface": {"displayName": "vbp1 skills"},
    "metadata": {"description": MARKETPLACE_DESC, "version": MARKETPLACE_VERSION},
    "plugins": codex_entries,
}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(f"wrote {len(PLUGINS)} plugin manifests + 2 marketplace manifests")
