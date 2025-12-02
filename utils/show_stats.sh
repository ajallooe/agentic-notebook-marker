#!/usr/bin/env bash
#
# Show Token Usage Statistics
#
# Displays aggregated token usage for an assignment from the stats file.
#
# Usage:
#   ./utils/show_stats.sh <assignment_dir>
#   ./utils/show_stats.sh <assignment_dir> --json
#

set -euo pipefail

# Color codes
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

usage() {
    cat << EOF
Usage: $(basename "$0") <assignment_dir> [OPTIONS]

Display token usage statistics for an assignment.

Arguments:
  assignment_dir    Path to assignment directory

Options:
  --json            Output raw JSON data
  --help            Show this help message

Example:
  $(basename "$0") "assignments/Lab 01"
  $(basename "$0") "assignments/Lab 01" --json
EOF
    exit 1
}

# Parse arguments
if [[ $# -lt 1 ]]; then
    usage
fi

ASSIGNMENT_DIR="$1"
JSON_OUTPUT=false

shift
while [[ $# -gt 0 ]]; do
    case $1 in
        --json)
            JSON_OUTPUT=true
            shift
            ;;
        --help|-h)
            usage
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            ;;
    esac
done

# Validate assignment directory
if [[ ! -d "$ASSIGNMENT_DIR" ]]; then
    # Try with assignments/ prefix
    if [[ -d "$PROJECT_ROOT/assignments/$ASSIGNMENT_DIR" ]]; then
        ASSIGNMENT_DIR="$PROJECT_ROOT/assignments/$ASSIGNMENT_DIR"
    else
        echo "Error: Assignment directory not found: $ASSIGNMENT_DIR" >&2
        exit 1
    fi
fi

ASSIGNMENT_DIR="$(cd "$ASSIGNMENT_DIR" && pwd)"
ASSIGNMENT_NAME="$(basename "$ASSIGNMENT_DIR")"
STATS_FILE="$ASSIGNMENT_DIR/processed/stats/token_usage.jsonl"

if [[ ! -f "$STATS_FILE" ]]; then
    echo "No token usage stats found for: $ASSIGNMENT_NAME"
    echo "Stats file: $STATS_FILE"
    exit 0
fi

if [[ "$JSON_OUTPUT" == true ]]; then
    cat "$STATS_FILE"
    exit 0
fi

# Aggregate stats using Python
python3 << EOF
import json
import sys
from collections import defaultdict
from datetime import datetime

stats_file = "$STATS_FILE"
assignment_name = "$ASSIGNMENT_NAME"

# Read all stats
stats = []
try:
    with open(stats_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                stats.append(json.loads(line))
except Exception as e:
    print(f"Error reading stats file: {e}", file=sys.stderr)
    sys.exit(1)

if not stats:
    print(f"No token usage stats found for: {assignment_name}")
    sys.exit(0)

# Aggregate totals
total_input = sum(s.get('input_tokens', 0) for s in stats)
total_output = sum(s.get('output_tokens', 0) for s in stats)
total_cache_creation = sum(s.get('cache_creation_tokens', 0) for s in stats)
total_cache_read = sum(s.get('cache_read_tokens', 0) for s in stats)
total_cost = sum(s.get('cost_usd', 0) for s in stats)

# By stage
by_stage = defaultdict(lambda: {'input': 0, 'output': 0, 'count': 0})
for s in stats:
    stage = s.get('stage', 'unknown')
    by_stage[stage]['input'] += s.get('input_tokens', 0)
    by_stage[stage]['output'] += s.get('output_tokens', 0)
    by_stage[stage]['count'] += 1

# By provider
by_provider = defaultdict(lambda: {'input': 0, 'output': 0, 'count': 0})
for s in stats:
    provider = s.get('provider', 'unknown')
    by_provider[provider]['input'] += s.get('input_tokens', 0)
    by_provider[provider]['output'] += s.get('output_tokens', 0)
    by_provider[provider]['count'] += 1

# Print report
print()
print(f"\033[1;36m{'='*70}\033[0m")
print(f"\033[1;36m  Token Usage Statistics: {assignment_name}\033[0m")
print(f"\033[1;36m{'='*70}\033[0m")
print()

print(f"\033[1mOverall Totals:\033[0m")
print(f"  Total LLM Calls:     {len(stats):,}")
print(f"  Input Tokens:        {total_input:,}")
print(f"  Output Tokens:       {total_output:,}")
if total_cache_creation > 0:
    print(f"  Cache Creation:      {total_cache_creation:,}")
if total_cache_read > 0:
    print(f"  Cache Read:          {total_cache_read:,}")
if total_cost > 0:
    print(f"  Estimated Cost:      \${total_cost:.4f}")
print()

print(f"\033[1mBy Stage:\033[0m")
for stage in ['marker', 'normalizer', 'unifier', 'pattern_designer', 'aggregator', 'unknown']:
    if stage in by_stage:
        s = by_stage[stage]
        print(f"  {stage:20s}  {s['count']:4d} calls  |  {s['input']:>10,} in  |  {s['output']:>8,} out")
print()

print(f"\033[1mBy Provider:\033[0m")
for provider, p in sorted(by_provider.items()):
    print(f"  {provider:10s}  {p['count']:4d} calls  |  {p['input']:>10,} in  |  {p['output']:>8,} out")
print()

# Time range
timestamps = [s.get('timestamp') for s in stats if s.get('timestamp')]
if timestamps:
    first = min(timestamps)
    last = max(timestamps)
    print(f"\033[1mTime Range:\033[0m")
    print(f"  First call: {first}")
    print(f"  Last call:  {last}")
    print()

print(f"\033[1;36m{'='*70}\033[0m")
print()
EOF
