#!/usr/bin/env bash
#
# Artifact Cleaner - Shell Wrapper
# Removes LLM generation artifacts from files
#

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Activate virtual environment if it exists
if [[ -f "$PROJECT_ROOT/.venv/bin/activate" ]]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Call the Python implementation
python3 "$PROJECT_ROOT/src/clean_artifacts.py" "$@"
