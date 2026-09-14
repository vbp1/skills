#!/usr/bin/env python3
"""Render an opponent's machine event stream as a readable progress log.

Reads JSONL on stdin and writes one human line per event on stdout, unbuffered, so
`tail -f` on the log shows what the opponent is doing while it works. Side files
carry the facts sparctl needs back:

    --session-file  the session id, written the moment the stream announces it,
                    so an interrupted turn still leaves a resumable session
    --answer-file   the final answer text (claude streams only; codex writes its
                    own answer file)
    --fail-file     one line describing the first terminal failure event

Usage:
    codex ... --json ... | tee raw.jsonl | render-events.py --stream codex --session-file s.id
    claude ... --output-format stream-json --verbose | tee raw.jsonl \\
        | render-events.py --stream claude --session-file s.id --answer-file a.txt
    render-events.py --help

Unrecognised or malformed lines are printed in a truncated raw form rather than
dropped. This filter never fails: any error becomes a printed line and the exit
code is always 0, so it cannot be mistaken for a provider failure in a pipeline
running under `set -o pipefail`.
"""
import argparse
import json
import sys
import time

MAX = 200


def clip(text, limit=MAX):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def unwrap(command):
    """Strip the `/bin/bash -lc "..."` wrapper Codex puts around shell calls."""
    if isinstance(command, list):
        command = " ".join(command)
    command = str(command)
    for prefix in ('/bin/bash -lc "', "/bin/bash -lc '", 'bash -lc "', "bash -lc '"):
        if command.startswith(prefix):
            command = command[len(prefix) :]
            if command.endswith(('"', "'")):
                command = command[:-1]
            break
    return command


class Sink:
    """Writes the side files once each, so a repeated event cannot overwrite them."""

    def __init__(self, args):
        self.args = args
        self.written = set()

    def put(self, which, text):
        path = getattr(self.args, which)
        if not path or which in self.written:
            return
        self.written.add(which)
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError as exc:
            emit("!", f"cannot write {which}: {exc}")


def emit(mark, text):
    print(f"{time.strftime('%H:%M:%S')} {mark} {text}", flush=True)


def render_codex(event, sink):
    kind = event.get("type")
    if kind == "thread.started":
        thread_id = event.get("thread_id", "")
        sink.put("session_file", thread_id)
        emit("==", f"session {thread_id or '?'}")
        return
    if kind == "turn.failed":
        sink.put("fail_file", clip(json.dumps(event.get("error", event), ensure_ascii=False)))
        emit("!", "turn failed: " + clip(json.dumps(event.get("error", ""), ensure_ascii=False)))
        return
    if kind == "error":
        sink.put("fail_file", clip(json.dumps(event, ensure_ascii=False)))
        emit("!", clip(json.dumps(event, ensure_ascii=False)))
        return
    if kind in ("turn.started", "turn.completed"):
        return

    item = event.get("item") or {}
    item_kind = item.get("type")
    started = kind == "item.started"

    if item_kind == "command_execution":
        if started:
            emit("$", clip(unwrap(item.get("command", ""))))
        elif item.get("exit_code") not in (0, None):
            emit("!", f"exit {item.get('exit_code')}")
        return
    if item_kind == "mcp_tool_call" and started:
        emit("~", clip(f"{item.get('server')}.{item.get('tool')} {item.get('arguments', '')}"))
        return
    if item_kind == "web_search" and not started:
        emit("?", "web search: " + clip(item.get("query") or "(query not reported)"))
        return
    if item_kind == "reasoning" and not started:
        text = clip(item.get("text") or item.get("summary") or "")
        if text:
            emit("*", text)
        return
    if item_kind == "agent_message" and not started:
        for line in (item.get("text") or "").splitlines():
            if line.strip():
                emit(">", clip(line, 400))
        return
    if started or item_kind is None:
        emit(".", clip(f"{kind} {item_kind or ''}"))


def render_claude(event, sink):
    kind = event.get("type")
    if kind == "system" and event.get("subtype") == "init":
        session_id = event.get("session_id", "")
        sink.put("session_file", session_id)
        emit("==", f"session {session_id or '?'} model {event.get('model', '?')}")
        return
    if kind == "system":
        return
    if kind == "rate_limit_event":
        return
    if kind == "assistant":
        for block in (event.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                for line in (block.get("text") or "").splitlines():
                    if line.strip():
                        emit(">", clip(line, 400))
            elif block.get("type") == "tool_use":
                emit("~", clip(f"{block.get('name')} {block.get('input', '')}"))
            elif block.get("type") == "thinking":
                text = clip(block.get("thinking") or "")
                if text:
                    emit("*", text)
        return
    if kind == "user":
        emit(".", "tool result")
        return
    if kind == "result":
        if event.get("is_error") or event.get("subtype") != "success":
            sink.put("fail_file", clip(json.dumps(event, ensure_ascii=False)))
            emit("!", "result: " + clip(str(event.get("result") or event.get("subtype"))))
            return
        sink.put("answer_file", str(event.get("result") or ""))
        emit("==", "answer received")
        return
    emit(".", clip(f"{kind}"))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--stream", choices=("codex", "claude"), required=True,
                        help="which opponent's event shape is on stdin")
    parser.add_argument("--session-file", help="write the session id here as soon as it appears")
    parser.add_argument("--answer-file", help="write the final answer text here (claude streams)")
    parser.add_argument("--fail-file", help="write the first terminal failure event here")
    args = parser.parse_args()

    sink = Sink(args)
    render = render_codex if args.stream == "codex" else render_claude
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            render(json.loads(line), sink)
        except Exception:
            emit(".", clip(line))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(0)
