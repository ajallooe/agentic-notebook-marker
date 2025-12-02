#!/usr/bin/env python3
"""
Extract text response and token stats from LLM CLI JSON output.

Supports Claude, Gemini, and Codex JSON formats.
Outputs text to stdout, appends stats to file if --stats-file provided.
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def extract_claude(data: dict) -> tuple[str, dict]:
    """Extract text and stats from Claude JSON output."""
    text = data.get('result', '')
    usage = data.get('usage', {})

    stats = {
        'input_tokens': usage.get('input_tokens', 0),
        'output_tokens': usage.get('output_tokens', 0),
        'cache_creation_tokens': usage.get('cache_creation_input_tokens', 0),
        'cache_read_tokens': usage.get('cache_read_input_tokens', 0),
        'cost_usd': data.get('total_cost_usd', 0),
    }
    return text, stats


def extract_gemini(data: dict) -> tuple[str, dict]:
    """Extract text and stats from Gemini JSON output."""
    text = data.get('response', '')

    # Aggregate stats across all models used
    total_input = 0
    total_output = 0
    models_stats = data.get('stats', {}).get('models', {})

    for model_name, model_stats in models_stats.items():
        tokens = model_stats.get('tokens', {})
        total_input += tokens.get('prompt', 0)
        total_output += tokens.get('candidates', 0)

    stats = {
        'input_tokens': total_input,
        'output_tokens': total_output,
        'cache_creation_tokens': 0,
        'cache_read_tokens': 0,
        'cost_usd': 0,  # Gemini doesn't report cost
    }
    return text, stats


def extract_codex(lines: list[str]) -> tuple[str, dict]:
    """Extract text and stats from Codex JSONL output."""
    text_parts = []
    total_input = 0
    total_output = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            event_type = data.get('type', '')

            # Extract text from agent messages
            if event_type == 'item.completed':
                item = data.get('item', {})
                if item.get('type') == 'agent_message':
                    text_parts.append(item.get('text', ''))

            # Extract usage from turn.completed
            elif event_type == 'turn.completed':
                usage = data.get('usage', {})
                total_input += usage.get('input_tokens', 0)
                total_output += usage.get('output_tokens', 0)
        except json.JSONDecodeError:
            continue

    stats = {
        'input_tokens': total_input,
        'output_tokens': total_output,
        'cache_creation_tokens': 0,
        'cache_read_tokens': 0,
        'cost_usd': 0,  # Codex doesn't report cost
    }
    return '\n'.join(text_parts), stats


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Extract LLM response text and stats')
    parser.add_argument('--provider', required=True, choices=['claude', 'gemini', 'codex'])
    parser.add_argument('--stats-file', help='Append stats to this file')
    parser.add_argument('--stats-stage', default='unknown', help='Stage name for stats')
    parser.add_argument('--stats-context', default='', help='Additional context (e.g., student name)')
    parser.add_argument('--model', default='', help='Model name used')
    args = parser.parse_args()

    # Read JSON from stdin
    raw_input = sys.stdin.read()

    try:
        if args.provider == 'codex':
            # Codex outputs JSONL (multiple lines)
            lines = raw_input.strip().split('\n')
            text, stats = extract_codex(lines)
        else:
            # Claude and Gemini output single JSON object
            data = json.loads(raw_input)
            if args.provider == 'claude':
                text, stats = extract_claude(data)
            else:
                text, stats = extract_gemini(data)
    except (json.JSONDecodeError, KeyError) as e:
        # If JSON parsing fails, output raw input as text
        print(raw_input, end='')
        print(f"Warning: Failed to parse JSON: {e}", file=sys.stderr)
        sys.exit(0)

    # Output text to stdout
    print(text, end='')

    # Append stats to file if requested
    if args.stats_file:
        stats_entry = {
            'timestamp': datetime.now().isoformat(),
            'provider': args.provider,
            'model': args.model,
            'stage': args.stats_stage,
            'context': args.stats_context,
            **stats
        }

        stats_path = Path(args.stats_file)
        stats_path.parent.mkdir(parents=True, exist_ok=True)

        with open(stats_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(stats_entry) + '\n')


if __name__ == '__main__':
    main()
