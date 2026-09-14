#!/usr/bin/env python3
"""Render an opponent's machine event stream as a readable progress log.

Reads JSONL on stdin and writes one human line per event on stdout, unbuffered, so
`tail -f` on the log shows what the opponent is doing while it works. Side files
carry the facts sparctl needs back:

    --session-file  the session id, written the moment the stream announces it,
                    so an interrupted turn still leaves a resumable session
    --answer-file   the final answer text (claude streams only; codex writes its
                    own answer file)
    --done-file     written when the stream reports the turn finished cleanly
    --fail-file     the first terminal failure event

Usage:
    codex ... --json ... | render-events.py --stream codex --session-file s.id \\
        --done-file s.done --fail-file s.fail
    claude ... --output-format stream-json --verbose \\
        | render-events.py --stream claude --session-file s.id --answer-file a.txt \\
          --done-file s.done --fail-file s.fail
    render-events.py --help

Display is best effort: an unreadable or unknown line is printed truncated rather
than dropped, and never fails the run. The side files are not display — they carry
the turn's result, so a side file that cannot be written is a failure of this
filter, reported with exit code 6.

EXIT CODES
    0  stream consumed
    6  a side file could not be written; the caller must not treat the turn as done
"""
import argparse
import json
import os
import sys
import time

MAX = 200
SIDE_FILE_ERROR = 6


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


def emit(mark, text):
    print(f"{time.strftime('%H:%M:%S')} {mark} {text}", flush=True)


class Sink:
    """Writes each side file once, atomically. A write that fails fails the run."""

    def __init__(self, args):
        self.args = args
        self.written = set()
        self.broken = False

    def put(self, which, text):
        path = getattr(self.args, which)
        if not path or which in self.written:
            return
        tmp = f"{path}.partial"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except OSError as exc:
            self.broken = True
            emit("!", f"cannot write {which}: {exc}")
            return
        self.written.add(which)


def render_codex(event, sink):
    kind = event.get("type")
    if kind == "thread.started":
        thread_id = event.get("thread_id", "")
        sink.put("session_file", thread_id)
        emit("==", f"session {thread_id or '?'}")
        return
    if kind == "turn.completed":
        sink.put("done_file", "completed")
        return
    if kind == "turn.failed":
        sink.put("fail_file", clip(json.dumps(event.get("error", event), ensure_ascii=False)))
        emit("!", "turn failed: " + clip(json.dumps(event.get("error", ""), ensure_ascii=False)))
        return
    if kind == "error":
        sink.put("fail_file", clip(json.dumps(event, ensure_ascii=False)))
        emit("!", clip(json.dumps(event, ensure_ascii=False)))
        return
    if kind == "turn.started":
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
    if kind in ("system", "rate_limit_event"):
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
        sink.put("done_file", "completed")
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
    parser.add_argument("--done-file", help="write here when the turn finished cleanly")
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
    return SIDE_FILE_ERROR if sink.broken else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(0)
