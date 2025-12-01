#!/usr/bin/env bash
#
# Review Errors - Display consolidated error report for a marking run
#
# Usage:
#   ./review_errors.sh <assignment_directory> [OPTIONS]
#
# This script provides a central place to review all errors that occurred
# during marking, making it easy to diagnose issues after a failed run.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

usage() {
    cat << EOF
Usage: $(basename "$0") <assignment_directory> [OPTIONS]

Display a consolidated error report for a marking run.

This script shows:
  - Which students/tasks failed and why
  - Error categorization (quota, timeout, network, etc.)
  - Missing output files
  - Actionable recommendations

Arguments:
  assignment_directory    Path to the assignment directory

Options:
  --stage STAGE           Show errors for specific stage only
                          (marker, unifier, all). Default: all
  --json                  Also output JSON format for programmatic use
  --quiet                 Only show output if there are errors
  --summary               Show only the summary, not individual errors
  --help                  Show this help message

Examples:
  # Review all errors after a failed marking run
  ./review_errors.sh assignments/lab1

  # Check only unifier stage errors
  ./review_errors.sh assignments/lab1 --stage unifier

  # Export errors to JSON
  ./review_errors.sh assignments/lab1 --json

  # Quick check if there are errors
  ./review_errors.sh assignments/lab1 --quiet && echo "No errors"

EOF
    exit 1
}

# Parse arguments
if [[ $# -lt 1 ]]; then
    usage
fi

ASSIGNMENT_DIR=""
STAGE="all"
JSON_FLAG=""
QUIET_FLAG=""
SUMMARY_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --stage)
            STAGE="$2"
            shift 2
            ;;
        --json)
            JSON_FLAG="--json"
            shift
            ;;
        --quiet)
            QUIET_FLAG="--quiet"
            shift
            ;;
        --summary)
            SUMMARY_ONLY=true
            shift
            ;;
        --help)
            usage
            ;;
        -*)
            echo -e "${RED}[ERROR]${NC} Unknown option: $1" >&2
            usage
            ;;
        *)
            if [[ -z "$ASSIGNMENT_DIR" ]]; then
                ASSIGNMENT_DIR="$1"
            else
                echo -e "${RED}[ERROR]${NC} Unexpected argument: $1" >&2
                usage
            fi
            shift
            ;;
    esac
done

# Validate assignment directory
if [[ -z "$ASSIGNMENT_DIR" ]]; then
    echo -e "${RED}[ERROR]${NC} Assignment directory is required" >&2
    usage
fi

if [[ ! -d "$ASSIGNMENT_DIR" ]]; then
    echo -e "${RED}[ERROR]${NC} Assignment directory not found: $ASSIGNMENT_DIR" >&2
    exit 1
fi

# Resolve to absolute path
ASSIGNMENT_DIR="$(cd "$ASSIGNMENT_DIR" && pwd)"
ASSIGNMENT_NAME="$(basename "$ASSIGNMENT_DIR")"
PROCESSED_DIR="$ASSIGNMENT_DIR/processed"
LOGS_DIR="$PROCESSED_DIR/logs"
MANIFEST="$PROCESSED_DIR/submissions_manifest.json"
FINAL_DIR="$PROCESSED_DIR/final"

# Header
if [[ -z "$QUIET_FLAG" ]]; then
    echo ""
    echo -e "${BOLD}════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}                    ERROR REVIEW: $ASSIGNMENT_NAME${NC}"
    echo -e "${BOLD}════════════════════════════════════════════════════════════════════${NC}"
    echo ""
fi

if [[ ! -d "$PROCESSED_DIR" ]]; then
    echo -e "${YELLOW}[INFO]${NC} No processed directory found. Has marking been run?"
    exit 0
fi

# Track if we found any errors
FOUND_ERRORS=false

# Function to run error summary for a stage
run_summary() {
    local stage_name="$1"
    local logs_subdir="$2"
    local stage_logs="$LOGS_DIR/$logs_subdir"

    if [[ -d "$stage_logs" ]]; then
        if [[ "$SUMMARY_ONLY" == true ]]; then
            # Just count errors
            local result
            # Only check final dir for unifier stage (marker doesn't produce final files)
            if [[ "$stage_name" == "unifier" ]]; then
                result=$(python3 "$SCRIPT_DIR/src/utils/error_summary.py" \
                    --logs-dir "$stage_logs" \
                    --stage "$stage_name" \
                    --manifest "$MANIFEST" \
                    --final-dir "$FINAL_DIR" \
                    --quiet 2>&1) || true
            else
                result=$(python3 "$SCRIPT_DIR/src/utils/error_summary.py" \
                    --logs-dir "$stage_logs" \
                    --stage "$stage_name" \
                    --quiet 2>&1) || true
            fi

            if [[ -n "$result" ]]; then
                FOUND_ERRORS=true
                # Extract just the summary line
                echo "$result" | grep -E "^SUMMARY:" || true
            fi
        else
            local result
            # Only check final dir for unifier stage (marker doesn't produce final files)
            if [[ "$stage_name" == "unifier" ]]; then
                result=$(python3 "$SCRIPT_DIR/src/utils/error_summary.py" \
                    --logs-dir "$stage_logs" \
                    --stage "$stage_name" \
                    --manifest "$MANIFEST" \
                    --final-dir "$FINAL_DIR" \
                    $JSON_FLAG \
                    $QUIET_FLAG 2>&1) || true
            else
                result=$(python3 "$SCRIPT_DIR/src/utils/error_summary.py" \
                    --logs-dir "$stage_logs" \
                    --stage "$stage_name" \
                    $JSON_FLAG \
                    $QUIET_FLAG 2>&1) || true
            fi

            if [[ -n "$result" ]]; then
                FOUND_ERRORS=true
                echo "$result"
            fi
        fi
    fi
}

# Run for requested stages
case "$STAGE" in
    marker)
        run_summary "marker" "marker_logs"
        ;;
    unifier)
        run_summary "unifier" "unifier_logs"
        ;;
    all)
        # Check marker logs
        if [[ -d "$LOGS_DIR/marker_logs" ]]; then
            run_summary "marker" "marker_logs"
        fi

        # Check unifier logs
        if [[ -d "$LOGS_DIR/unifier_logs" ]]; then
            run_summary "unifier" "unifier_logs"
        fi

        # If no logs found
        if [[ ! -d "$LOGS_DIR/marker_logs" && ! -d "$LOGS_DIR/unifier_logs" ]]; then
            if [[ -z "$QUIET_FLAG" ]]; then
                echo -e "${GREEN}[INFO]${NC} No parallel task logs found in $LOGS_DIR"
                echo "This may mean:"
                echo "  - Marking hasn't reached the parallel stages yet"
                echo "  - All tasks completed successfully"
                echo "  - Logs were cleaned up"
            fi
        fi
        ;;
    *)
        echo -e "${RED}[ERROR]${NC} Invalid stage: $STAGE (must be: marker, unifier, all)" >&2
        exit 1
        ;;
esac

# Footer with next steps
if [[ -z "$QUIET_FLAG" && "$FOUND_ERRORS" == true ]]; then
    echo ""
    echo -e "${BOLD}════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}                         NEXT STEPS${NC}"
    echo -e "${BOLD}════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Options:"
    echo ""
    echo "  1. ${BOLD}Retry failed tasks${NC} (recommended for quota/timeout errors):"
    echo "     ./mark_structured.sh \"$ASSIGNMENT_DIR\""
    echo ""
    echo "  2. ${BOLD}Force complete${NC} (assign zero to failed students and finish):"
    echo "     ./mark_structured.sh \"$ASSIGNMENT_DIR\" --force-complete"
    echo ""
    echo "  3. ${BOLD}Export errors to JSON${NC} for further analysis:"
    echo "     ./review_errors.sh \"$ASSIGNMENT_DIR\" --json"
    echo ""
fi

# Exit with error code if errors were found (useful for scripting)
if [[ "$FOUND_ERRORS" == true ]]; then
    exit 1
fi

exit 0
