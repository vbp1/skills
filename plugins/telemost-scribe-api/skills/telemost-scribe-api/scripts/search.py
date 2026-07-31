#!/usr/bin/env python3
"""Small Telemost Scribe agent API client."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

JsonValue = None | bool | int | float | str | list['JsonValue'] | dict[str, 'JsonValue']


DEFAULT_BASE_URL = 'http://127.0.0.1:8765'


def main() -> int:
    parser = argparse.ArgumentParser(description='Query the local Telemost Scribe agent API.')
    parser.add_argument('--base-url', default=os.environ.get('TELEMOST_SCRIBE_API_URL', DEFAULT_BASE_URL))
    subparsers = parser.add_subparsers(dest='command', required=True)

    subparsers.add_parser('capabilities', help='Show API capabilities.')

    schedules = subparsers.add_parser('schedules', help='List scheduled meeting definitions.')
    schedules.add_argument('--json', action='store_true', help='Print raw JSON response.')

    schedule_meetings = subparsers.add_parser('schedule-meetings', help='List meetings created from a schedule.')
    schedule_meetings.add_argument('schedule_id')
    schedule_meetings.add_argument('--limit', type=int, default=50)
    schedule_meetings.add_argument('--json', action='store_true', help='Print raw JSON response.')

    search = subparsers.add_parser('search', help='Search transcript and summary data.')
    search.add_argument('query')
    search.add_argument('--meeting-id', action='append', default=[])
    search.add_argument('--source', action='append', choices=('segments', 'summary'), default=[])
    search.add_argument('--limit', type=int, default=10)
    search.add_argument('--context-segments', type=int, default=1)
    search.add_argument('--json', action='store_true', help='Print raw JSON response.')

    args = parser.parse_args()
    base_url = args.base_url.rstrip('/')
    try:
        if args.command == 'capabilities':
            _write_line(json.dumps(_get_json(f'{base_url}/api/agent/capabilities'), ensure_ascii=False, indent=2))
            return 0
        if args.command == 'schedules':
            response = _get_json(f'{base_url}/api/agent/schedules')
        elif args.command == 'schedule-meetings':
            params = urllib.parse.urlencode({'limit': args.limit})
            schedule_id = urllib.parse.quote(args.schedule_id, safe='')
            response = _get_json(f'{base_url}/api/agent/schedules/{schedule_id}/meetings?{params}')
        else:
            response = _post_json(
                f'{base_url}/api/agent/search',
                {
                    'query': args.query,
                    'meeting_ids': args.meeting_id,
                    'sources': args.source or ['segments', 'summary'],
                    'limit': args.limit,
                    'context_segments': args.context_segments,
                },
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        _write_error(f'HTTP {exc.code}: {body}')
        return 1
    except urllib.error.URLError as exc:
        _write_error(f'Connection failed: {exc.reason}')
        return 1

    if args.json:
        _write_line(json.dumps(response, ensure_ascii=False, indent=2))
    elif args.command == 'schedules':
        _print_schedules(response)
    elif args.command == 'schedule-meetings':
        _print_schedule_meetings(response)
    else:
        _print_results(response)
    return 0


def _get_json(url: str) -> JsonValue:
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode('utf-8'))


def _post_json(url: str, payload: Mapping[str, JsonValue]) -> JsonValue:
    request = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return json.loads(response.read().decode('utf-8'))


def _print_results(response: JsonValue) -> None:
    if not isinstance(response, dict):
        _write_line('Unexpected response.')
        return
    results = response.get('results', [])
    if not results:
        _write_line('No results.')
        return
    if not isinstance(results, list):
        _write_line('Unexpected results.')
        return
    for index, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            continue
        meeting = result.get('meeting_title') or result.get('meeting_id')
        _write_line(
            f'{index}. [{result.get("source")}] {meeting} | {result.get("timestamp")} | seg#{result.get("segment_id")} | {result.get("speaker")}'
        )
        _write_line(str(result.get('text', '')).strip())
        context = result.get('context') or []
        if context:
            _write_line('Context:')
            for item in context:
                if isinstance(item, dict):
                    _write_line(f'  - {item.get("timestamp")} | seg#{item.get("segment_id")} | {item.get("speaker")}: {item.get("text")}')
        _write_line('')


def _print_schedules(response: JsonValue) -> None:
    if not isinstance(response, dict):
        _write_line('Unexpected response.')
        return
    schedules = response.get('schedules', [])
    if not schedules:
        _write_line('No schedules.')
        return
    if not isinstance(schedules, list):
        _write_line('Unexpected schedules.')
        return
    for schedule in schedules:
        if not isinstance(schedule, dict):
            continue
        enabled = 'enabled' if schedule.get('enabled') else 'disabled'
        next_run = _next_run(schedule)
        meeting_count = schedule.get('meeting_count', 0)
        _write_line(
            f'{schedule.get("id")} | {schedule.get("title")} | {schedule.get("kind")} | {enabled} | meetings: {meeting_count} | next: {next_run}'
        )


def _print_schedule_meetings(response: JsonValue) -> None:
    if not isinstance(response, dict):
        _write_line('Unexpected response.')
        return
    schedule = response.get('schedule')
    if isinstance(schedule, dict):
        _write_line(f'Schedule: {schedule.get("title") or schedule.get("id")} ({schedule.get("id")})')
    meetings = response.get('meetings', [])
    if not meetings:
        _write_line('No meetings.')
        return
    if not isinstance(meetings, list):
        _write_line('Unexpected meetings.')
        return
    for meeting in meetings:
        if not isinstance(meeting, dict):
            continue
        occurrence = meeting.get('occurrence') if isinstance(meeting.get('occurrence'), dict) else {}
        scheduled = occurrence.get('scheduled_start_at') if isinstance(occurrence, dict) else None
        _write_line(
            f'{meeting.get("meeting_id")} | {meeting.get("title")} | scheduled: {scheduled} | '
            f'segments: {meeting.get("segment_count")} | protocol: {meeting.get("has_protocol")}'
        )


def _next_run(schedule: Mapping[str, JsonValue]) -> JsonValue:
    next_occurrence = schedule.get('next_occurrence')
    if not isinstance(next_occurrence, dict):
        return None
    return next_occurrence.get('scheduled_start_at')


def _write_line(text: str) -> None:
    sys.stdout.write(f'{text}\n')


def _write_error(text: str) -> None:
    sys.stderr.write(f'{text}\n')


if __name__ == '__main__':
    raise SystemExit(main())
