#!/usr/bin/env python3
"""Deep-dive analysis of a single Langfuse trace with observation timeline."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lf_api import resolve_credentials, api_get, api_get_all, parse_trace_id


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def classify_observation(obs: dict) -> dict:
    """Classify an observation and extract key info."""
    output = obs.get("output", "")
    usage = obs.get("usage") or {}
    level = obs.get("level", "DEFAULT")
    status_msg = obs.get("statusMessage") or ""

    flags = []
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
                        text_preview = t[:100]
    elif isinstance(output, str):
        if output.strip():
            has_text = True
            text_preview = output.strip()[:100]
    elif isinstance(output, dict):
        has_text = True
        text_preview = str(output)[:100]

    obs_type = obs.get("type", "")
    if obs_type == "GENERATION" and not has_text and not has_tool_calls:
        flags.append("EMPTY_TEXT")
    if has_tool_calls:
        flags.append("TOOL_CALLS")
    if level and level not in ("DEFAULT", "DEBUG"):
        flags.append(f"LEVEL:{level}")
    if status_msg and "error" in status_msg.lower():
        flags.append("ERROR_STATUS")

    # Duration
    start = obs.get("startTime", "")
    end = obs.get("endTime", "")
    duration_ms = None
    if start and end:
        try:
            from datetime import datetime
            fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
            s = start.rstrip("Z") + "Z"
            e = end.rstrip("Z") + "Z"
            # Simple ISO parse
            s_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            e_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            duration_ms = int((e_dt - s_dt).total_seconds() * 1000)
        except (ValueError, TypeError):
            pass

    return {
        "flags": flags,
        "has_text": has_text,
        "text_preview": text_preview,
        "input_tokens": usage.get("input", 0) or 0,
        "output_tokens": usage.get("output", 0) or 0,
        "model": obs.get("model"),
        "duration_ms": duration_ms,
        "has_tool_calls": has_tool_calls,
    }


def format_ts(ts: str) -> str:
    return ts[:19].replace("T", " ") if ts else "?"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def generate_report(trace: dict, observations: list[dict],
                    generations_only: bool = False,
                    errors_only: bool = False) -> str:
    lines = []
    trace_id = trace.get("id", "?")
    lines.append(f"=== Trace Analysis: {trace_id} ===")
    lines.append("")

    # Metadata
    lines.append("--- Metadata ---")
    lines.append(f"  Name:      {trace.get('name', '?')}")
    lines.append(f"  Timestamp: {format_ts(trace.get('timestamp', ''))}")
    lines.append(f"  User:      {trace.get('userId', '?')}")
    lines.append(f"  Session:   {trace.get('sessionId', '?')}")
    tags = trace.get("tags", [])
    if tags:
        lines.append(f"  Tags:      {', '.join(tags)}")
    lines.append("")

    # Sort observations chronologically
    obs_sorted = sorted(observations, key=lambda o: o.get("startTime", ""))

    # Observation timeline
    lines.append("--- Observation Timeline ---")
    total_in, total_out = 0, 0
    gen_count, gen_empty = 0, 0
    span_count, span_error = 0, 0

    for i, obs in enumerate(obs_sorted):
        obs_type = obs.get("type", "?")

        if generations_only and obs_type != "GENERATION":
            continue

        cls = classify_observation(obs)

        if errors_only and not cls["flags"]:
            continue

        total_in += cls["input_tokens"]
        total_out += cls["output_tokens"]

        if obs_type == "GENERATION":
            gen_count += 1
            if "EMPTY_TEXT" in cls["flags"]:
                gen_empty += 1
        elif obs_type == "SPAN":
            span_count += 1
            if any("ERROR" in f for f in cls["flags"]):
                span_error += 1

        # Format observation line
        flag_str = " ".join(f"[{f}]" for f in cls["flags"]) if cls["flags"] else ""
        lines.append(f"  #{i+1:<3} {format_ts(obs.get('startTime', ''))} | {obs_type} | {obs.get('name', '?')}")

        detail_parts = []
        if cls["model"]:
            detail_parts.append(f"Model: {cls['model'].split('/')[-1]}")
        if cls["input_tokens"] or cls["output_tokens"]:
            detail_parts.append(f"Tokens: in={cls['input_tokens']} out={cls['output_tokens']}")
        if cls["duration_ms"] is not None:
            detail_parts.append(f"Duration: {cls['duration_ms']}ms")
        if detail_parts:
            lines.append(f"       {' | '.join(detail_parts)}")

        if flag_str:
            lines.append(f"       {flag_str}")
        if cls["text_preview"]:
            lines.append(f'       text="{cls["text_preview"]}"')
        lines.append("")

    # Summary
    lines.append("--- Summary ---")
    if not generations_only:
        lines.append(f"  Generations: {gen_count} ({gen_empty} empty)")
        lines.append(f"  Spans:       {span_count} ({span_error} with errors)")
    lines.append(f"  Total tokens: in={total_in:,}  out={total_out:,}")

    if obs_sorted:
        first_ts = obs_sorted[0].get("startTime", "")
        last_ts = obs_sorted[-1].get("startTime", "")
        try:
            from datetime import datetime
            s = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            e = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            dur = int((e - s).total_seconds() * 1000)
            lines.append(f"  Duration:     {format_ts(first_ts)} → {format_ts(last_ts)} = {dur}ms")
        except (ValueError, TypeError):
            pass

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

USAGE = """Usage: lf_trace.py <trace-url-or-id> [options]

Deep-dive analysis of a single Langfuse trace with observation timeline.

Options:
  --generations-only  Show only GENERATION observations
  --errors-only       Show only observations with issues
  -h, --help          Show this help

Examples:
  lf_trace.py 4a417130eeca9b6ca9918e1a9262ed53
  lf_trace.py https://langfuse.example.com/project/xxx/traces/TRACE_ID
  lf_trace.py TRACE_ID --generations-only
  lf_trace.py TRACE_ID --errors-only
"""


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(USAGE)
        sys.exit(0)

    trace_input = sys.argv[1]
    generations_only = "--generations-only" in sys.argv
    errors_only = "--errors-only" in sys.argv

    trace_id = parse_trace_id(trace_input)
    creds = resolve_credentials()

    print(f"Fetching trace {trace_id}...", file=sys.stderr)
    trace = api_get(f"/traces/{trace_id}", credentials=creds)

    print("Fetching observations...", file=sys.stderr)
    observations = api_get_all("/observations", {"traceId": trace_id, "limit": 100}, creds)
    print(f"Found {len(observations)} observations.", file=sys.stderr)

    report = generate_report(trace, observations,
                             generations_only=generations_only,
                             errors_only=errors_only)
    print(report)


if __name__ == "__main__":
    main()
