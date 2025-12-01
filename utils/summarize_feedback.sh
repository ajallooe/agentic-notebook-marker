#!/usr/bin/env bash
#
# Feedback Summarizer - Condense detailed feedback into single paragraphs
#
# Usage:
#   ./utils/summarize_feedback.sh <grades.csv> [OPTIONS]
#
# This script takes a grades CSV with detailed feedback cards and uses an LLM
# to summarize each student's feedback into a single plain text paragraph
# suitable for gradebook comments.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$PROJECT_ROOT/src"

# Activate virtual environment if it exists
if [[ -f "$PROJECT_ROOT/.venv/bin/activate" ]]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

usage() {
    cat << EOF
Usage: $(basename "$0") <grades.csv> [OPTIONS]

Summarize detailed feedback cards into single plain text paragraphs.
Creates 3-4 sentence summaries focusing on mistakes and positives.
For very low marks (<40%), provides more detailed explanations.

Arguments:
  grades.csv              Path to the grades CSV file (with Feedback Card column)

Options:
  --output <file>         Output CSV file (default: <input>_summarized.csv)
  --provider <provider>   LLM provider: claude, gemini, codex (default: claude)
  --model <model>         Specific model to use (optional)
  --total-marks <n>       Total possible marks (default: 100)
  --feedback-col <name>   Name of feedback column (auto-detected if not specified)
  --dry-run               Preview without calling LLM
  --help                  Show this help message

Examples:
  # Summarize feedback from grades.csv
  ./utils/summarize_feedback.sh assignments/lab1/processed/final/grades.csv

  # Use Gemini with specific model
  ./utils/summarize_feedback.sh grades.csv --provider gemini --model gemini-2.5-pro

  # Specify total marks if not 100
  ./utils/summarize_feedback.sh grades.csv --total-marks 50

  # Specify output file
  ./utils/summarize_feedback.sh grades.csv --output summaries.csv

  # Preview what would be done
  ./utils/summarize_feedback.sh grades.csv --dry-run

EOF
    exit 1
}

if [[ $# -lt 1 ]]; then
    usage
fi

# Parse arguments
CSV_FILE=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --help)
            usage
            ;;
        --output|--provider|--model|--feedback-col|--total-marks)
            EXTRA_ARGS+=("$1" "$2")
            shift 2
            ;;
        --dry-run)
            EXTRA_ARGS+=("$1")
            shift
            ;;
        -*)
            echo -e "${RED}[ERROR]${NC} Unknown option: $1" >&2
            usage
            ;;
        *)
            if [[ -z "$CSV_FILE" ]]; then
                CSV_FILE="$1"
            else
                echo -e "${RED}[ERROR]${NC} Unexpected argument: $1" >&2
                usage
            fi
            shift
            ;;
    esac
done

# Validate CSV file
if [[ -z "$CSV_FILE" ]]; then
    echo -e "${RED}[ERROR]${NC} CSV file is required" >&2
    usage
fi

if [[ ! -f "$CSV_FILE" ]]; then
    echo -e "${RED}[ERROR]${NC} CSV file not found: $CSV_FILE" >&2
    exit 1
fi

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                    FEEDBACK SUMMARIZER${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════════${NC}"
echo ""

# Run the Python script
python3 "$SRC_DIR/utils/summarize_feedback.py" "$CSV_FILE" "${EXTRA_ARGS[@]}"

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}                    SUMMARIZATION COMPLETE${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════════${NC}"
