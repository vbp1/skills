#!/usr/bin/env python3
"""Small Telemost Scribe agent API client."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
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
            f"{index}. [{result.get('source')}] {meeting} | "
            f"{result.get('timestamp')} | seg#{result.get('segment_id')} | {result.get('speaker')}"
        )
        _write_line(str(result.get('text', '')).strip())
        context = result.get('context') or []
        if context:
            _write_line('Context:')
            for item in context:
                if isinstance(item, dict):
                    _write_line(
                        f"  - {item.get('timestamp')} | seg#{item.get('segment_id')} | "
                        f"{item.get('speaker')}: {item.get('text')}"
                    )
        _write_line('')


def _write_line(text: str) -> None:
    sys.stdout.write(f'{text}\n')


def _write_error(text: str) -> None:
    sys.stderr.write(f'{text}\n')


if __name__ == '__main__':
    raise SystemExit(main())
