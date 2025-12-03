#!/bin/bash
#
# Clear API Caches Utility
#
# Clears any explicit caches that may be accumulating costs on API providers.
# Use when processes are interrupted before natural cache expiration.
#
# Usage:
#   ./utils/clear_caches.sh              # List all caches
#   ./utils/clear_caches.sh --delete     # Delete all explicit caches
#   ./utils/clear_caches.sh --dry-run    # Show what would be deleted
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment if it exists
if [[ -f "$PROJECT_ROOT/.venv/bin/activate" ]]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Load API keys if available
if [[ -f "$SCRIPT_DIR/load_api_keys.sh" ]]; then
    source "$SCRIPT_DIR/load_api_keys.sh"
fi

# Run the Python script
python3 "$SCRIPT_DIR/clear_caches.py" "$@"
