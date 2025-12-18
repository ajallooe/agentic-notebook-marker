#!/usr/bin/env bash
#
# Clean outputs from Jupyter notebooks (like "Edit > Clear All Outputs")
#
# Usage:
#   ./utils/clean_notebook_outputs.sh <path> [options]
#
# Examples:
#   # Preview what would be cleaned (dry run)
#   ./utils/clean_notebook_outputs.sh "assignments/Lab 01" --dry-run
#
#   # Clean only submissions (not base notebook)
#   ./utils/clean_notebook_outputs.sh "assignments/Lab 01" --submissions-only
#
#   # Clean all notebooks in assignment
#   ./utils/clean_notebook_outputs.sh "assignments/Lab 01"
#
#   # Clean a single notebook
#   ./utils/clean_notebook_outputs.sh "path/to/notebook.ipynb"
#
# Options:
#   --dry-run          Show what would be cleaned without modifying files
#   --submissions-only Only clean files in submissions/ subdirectory
#   -q, --quiet        Only show summary
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Check for required argument
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <path> [options]"
    echo ""
    echo "Clean outputs from Jupyter notebooks."
    echo ""
    echo "Options:"
    echo "  --dry-run          Preview changes without modifying files"
    echo "  --submissions-only Only clean files in submissions/ subdirectory"
    echo "  -q, --quiet        Only show summary"
    echo ""
    echo "Examples:"
    echo "  $0 \"assignments/Lab 01\" --dry-run"
    echo "  $0 \"assignments/Lab 01\" --submissions-only"
    exit 1
fi

# Run the Python script with all arguments
python3 "$PROJECT_ROOT/src/clean_notebook_outputs.py" "$@"
