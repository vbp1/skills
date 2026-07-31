#!/usr/bin/env python3
"""Analyze a Langfuse session: fetch traces, observations, detect issues."""

import sys
import os

# Allow importing lf_api from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lf_api import resolve_credentials, api_get, api_get_all, parse_session_id

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def fetch_session(session_id: str, creds: tuple) -> dict:
    return api_get(f"/sessions/{session_id}", credentials=creds)


def fetch_traces(session_id: str, creds: tuple) -> list[dict]:
    return api_get_all("/traces", {"sessionId": session_id, "limit": 50}, creds)


def fetch_observations(trace_id: str, creds: tuple) -> list[dict]:
    return api_get_all("/observations", {"traceId": trace_id, "limit": 100}, creds)


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------


def classify_observation(obs: dict) -> dict:
    """Add classification flags to an observation."""
    flags = []
    obs_type = obs.get("type", "")
    output = obs.get("output", "")
    level = obs.get("level", "DEFAULT")
    status_msg = obs.get("statusMessage") or ""
    usage = obs.get("usage") or {}
    model = obs.get("model")

    # Detect empty text in generations
    has_text = False
    has_tool_calls = False
    text_preview = ""

    if isinstance(output, list):
        for item in output:
            if isinstance(item, dict):
                if item.get("type") == "tool-call":
                    has_tool_calls = True
                elif item.get("type") == "text":
                    t = (item.get("text", "") or "").strip()
                    if t:
                        has_text = True
                        text_preview = t[:80]
    elif isinstance(output, str):
        if output.strip():
            has_text = True
            text_preview = output.strip()[:80]
    elif isinstance(output, dict):
        has_text = True
        text_preview = str(output)[:80]

    if obs_type == "GENERATION" and not has_text and not has_tool_calls:
        flags.append("EMPTY_TEXT")
    if has_tool_calls:
        flags.append("TOOL_CALLS")
    if level and level not in ("DEFAULT", "DEBUG"):
        flags.append(f"LEVEL:{level}")
    if status_msg and "error" in status_msg.lower():
        flags.append("ERROR_STATUS")

    return {
        "flags": flags,
        "has_text": has_text,
        "text_preview": text_preview,
        "input_tokens": usage.get("input", 0) or 0,
        "output_tokens": usage.get("output", 0) or 0,
        "model": model,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def format_timestamp(ts: str) -> str:
    if not ts:
        return "?"
    return ts[:19].replace("T", " ")


def generate_report(session_id: str, session: dict, traces: list[dict],
                    trace_observations: dict[str, list[dict]],
                    errors_only: bool = False, trace_index: int | None = None) -> str:
    lines = []
    lines.append(f"=== Session Analysis: {session_id} ===")
    lines.append(f"    Created: {format_timestamp(session.get('createdAt', ''))}")
    lines.append(f"    Traces:  {len(traces)}")
    lines.append("")

    # Compute totals
    total_in, total_out = 0, 0
    models_used: set[str] = set()
    all_issues: list[str] = []
    traces_with_issues: set[int] = set()

    trace_summaries = []
    for i, trace in enumerate(sorted(traces, key=lambda t: t.get("timestamp", ""))):
        tid = trace["id"]
        obs_list = trace_observations.get(tid, [])
        obs_sorted = sorted(obs_list, key=lambda o: o.get("startTime", ""))

        t_in, t_out = 0, 0
        t_issues = []
        obs_details = []

        for obs in obs_sorted:
            cls = classify_observation(obs)
            t_in += cls["input_tokens"]
            t_out += cls["output_tokens"]
            if cls["model"]:
                models_used.add(cls["model"])

            flag_str = " ".join(f"[{f}]" for f in cls["flags"]) if cls["flags"] else ""
            text_part = f' text="{cls["text_preview"]}"' if cls["text_preview"] else ""

            obs_details.append({
                "timestamp": format_timestamp(obs.get("startTime", "")),
                "name": obs.get("name", "?"),
                "type": obs.get("type", "?"),
                "model": cls["model"] or "",
                "in": cls["input_tokens"],
                "out": cls["output_tokens"],
                "flags": flag_str,
                "text": text_part,
                "has_issues": bool(cls["flags"]),
            })

            if "EMPTY_TEXT" in cls["flags"]:
                t_issues.append("EMPTY_TEXT")
                traces_with_issues.add(i)
            if "ERROR_STATUS" in cls["flags"]:
                t_issues.append("ERROR_STATUS")
                traces_with_issues.add(i)
            if "LEVEL:ERROR" in cls["flags"]:
                t_issues.append("LEVEL:ERROR")
                traces_with_issues.add(i)

        total_in += t_in
        total_out += t_out
        all_issues.extend(t_issues)

        trace_summaries.append({
            "index": i,
            "id": tid,
            "timestamp": format_timestamp(trace.get("timestamp", "")),
            "name": trace.get("name", "?"),
            "in": t_in,
            "out": t_out,
            "obs_count": len(obs_sorted),
            "issues": t_issues,
            "obs_details": obs_details,
        })

    # Overview
    models_str = ", ".join(sorted(models_used)) if models_used else "none"
    lines.append(f"--- Overview ---")
    lines.append(f"Total tokens: input={total_in:,}  output={total_out:,}")
    lines.append(f"Models used:  {models_str}")
    lines.append("")

    # Trace timeline
    lines.append("--- Trace Timeline ---")
    for ts in trace_summaries:
        issue_flag = f"  !! {len(ts['issues'])} issues" if ts["issues"] else ""
        lines.append(
            f"  #{ts['index']}  {ts['timestamp']} | {ts['name']} | "
            f"obs={ts['obs_count']} | in={ts['in']:,} out={ts['out']:,}{issue_flag}"
        )
    lines.append("")

    # Observations detail
    show_indices = range(len(trace_summaries))
    if trace_index is not None:
        show_indices = [trace_index] if 0 <= trace_index < len(trace_summaries) else []

    for idx in show_indices:
        ts = trace_summaries[idx]
        if errors_only and not ts["issues"]:
            continue
        lines.append(f"--- Trace #{ts['index']}: {ts['name']} (id={ts['id'][:16]}...) ---")
        for od in ts["obs_details"]:
            if errors_only and not od["has_issues"]:
                continue
            model_part = f" model={od['model']}" if od["model"] else ""
            tok_part = f" in={od['in']} out={od['out']}" if od["in"] or od["out"] else ""
            lines.append(
                f"  {od['timestamp']} | {od['name']} | {od['type']}"
                f"{model_part}{tok_part} {od['flags']}{od['text']}"
            )
        lines.append("")

    # Issues summary
    if all_issues:
        from collections import Counter
        issue_counts = Counter(all_issues)
        lines.append("--- Issues Found ---")
        for issue, count in issue_counts.most_common():
            lines.append(f"  {count}x {issue}")
        affected = ", ".join(f"#{i}" for i in sorted(traces_with_issues))
        lines.append(f"  Affected traces: {affected}")
        lines.append("")

    # Token usage table
    lines.append("--- Token Usage ---")
    lines.append(f"  {'Trace':<8} {'Model':<45} {'Input':>8} {'Output':>8} {'Total':>8}")
    lines.append(f"  {'─'*8} {'─'*45} {'─'*8} {'─'*8} {'─'*8}")
    for ts in trace_summaries:
        model = ""
        for od in ts["obs_details"]:
            if od["model"]:
                model = od["model"]
                break
        model_short = model.split("/")[-1][:45] if model else "?"
        lines.append(
            f"  #{ts['index']:<7} {model_short:<45} {ts['in']:>8,} {ts['out']:>8,} {ts['in']+ts['out']:>8,}"
        )
    lines.append(f"  {'─'*8} {'─'*45} {'─'*8} {'─'*8} {'─'*8}")
    lines.append(
        f"  {'TOTAL':<8} {'':<45} {total_in:>8,} {total_out:>8,} {total_in+total_out:>8,}"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

USAGE = """Usage: lf_session.py <session-url-or-id> [options]

Analyze a Langfuse session: fetch all traces and observations, detect issues.

Options:
  --errors-only       Show only observations with issues
  --trace-index N     Show detail for specific trace index only
  -h, --help          Show this help

Examples:
  lf_session.py f46a4722-c5d2-4e82-902b-867728ee1870
  lf_session.py https://langfuse.example.com/project/xxx/sessions/SESSION_ID
  lf_session.py SESSION_ID --errors-only
  lf_session.py SESSION_ID --trace-index 0
"""


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(USAGE)
        sys.exit(0)

    session_input = sys.argv[1]
    errors_only = "--errors-only" in sys.argv
    trace_index = None
    if "--trace-index" in sys.argv:
        idx = sys.argv.index("--trace-index")
        if idx + 1 < len(sys.argv):
            trace_index = int(sys.argv[idx + 1])

    session_id = parse_session_id(session_input)
    creds = resolve_credentials()

    print(f"Fetching session {session_id}...", file=sys.stderr)
    session = fetch_session(session_id, creds)

    print("Fetching traces...", file=sys.stderr)
    traces = fetch_traces(session_id, creds)
    print(f"Found {len(traces)} traces. Fetching observations...", file=sys.stderr)

    trace_observations: dict[str, list[dict]] = {}
    for t in traces:
        tid = t["id"]
        obs = fetch_observations(tid, creds)
        trace_observations[tid] = obs
        print(f"  Trace {tid[:12]}... → {len(obs)} observations", file=sys.stderr)

    report = generate_report(session_id, session, traces, trace_observations,
                             errors_only=errors_only, trace_index=trace_index)
    print(report)


if __name__ == "__main__":
    main()
