#!/usr/bin/env bash
#
# Batch Marking Script - Mark Multiple Assignments in Stages
#
# This script processes multiple assignments in batches, grouping interactive
# stages together to minimize instructor waiting time.
#
# Usage:
#   batch_mark.sh ASSIGNMENTS_FILE [--stop-after STAGE] [--parallel N]
#
# Workflow:
#   Round 1: ./batch_mark.sh assignments.txt --stop-after 2
#            (All assignments stop after pattern design)
#            → Instructor reviews all patterns in one session
#
#   Round 2: ./batch_mark.sh assignments.txt --stop-after 4
#            (All assignments stop after normalization)
#            → Instructor reviews all dashboards in one session
#
#   Round 3: ./batch_mark.sh assignments.txt --stop-after 6
#            (All assignments complete unification)
#
#   Round 4: ./batch_mark.sh assignments.txt
#            (All assignments run to completion)
#

set -euo pipefail

# Determine script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$(basename "$SCRIPT_DIR")" == "utils" ]]; then
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
else
    PROJECT_ROOT="$SCRIPT_DIR"
fi

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Usage message
usage() {
    cat << EOF
Usage: $(basename "$0") ASSIGNMENTS_FILE [OPTIONS]

Batch process multiple assignments in stages to optimize instructor workflow.

Arguments:
  ASSIGNMENTS_FILE    Text file with assignment paths (one per line)

Options:
  --stop-after N      Stop after stage N (1-9 for structured, 1-8 for freeform)
  --parallel N        Override max parallel tasks for all assignments
  --resume            Resume from last checkpoint (default: true)
  --no-resume         Start fresh, ignore previous progress
  --help              Show this help message

Recommended Workflow:
  Round 1: Submission Discovery
    $ $(basename "$0") assignments.txt --stop-after 1
    → Verify all submissions were found correctly

  Round 2: Pattern Design
    $ $(basename "$0") assignments.txt --stop-after 2
    → Review all rubrics and marking criteria

  Round 3: Normalization
    $ $(basename "$0") assignments.txt --stop-after 4
    → Review normalized scoring schemes

  Round 4: Dashboard Review
    $ $(basename "$0") assignments.txt --stop-after 5
    → Review and approve all marking schemes in dashboards

  Round 5: Completion
    $ $(basename "$0") assignments.txt
    → Generate final grades and optional utilities

Assignment File Format:
  assignments/lab1
  assignments/lab2
  assignments/project-phase1

Notes:
  - Blank lines and lines starting with # are ignored
  - Paths can be absolute or relative to project root
  - Script auto-detects structured vs freeform assignments
  - Uses --resume by default to skip completed stages

EOF
    exit 1
}

# Parse arguments
if [[ $# -lt 1 ]]; then
    usage
fi

# Check for --help first
if [[ "$1" == "--help" ]]; then
    usage
fi

ASSIGNMENTS_FILE="$1"
shift

STOP_AFTER=""
PARALLEL_OVERRIDE=""
RESUME_FLAG="--resume"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --stop-after)
            STOP_AFTER="$2"
            shift 2
            ;;
        --parallel)
            PARALLEL_OVERRIDE="$2"
            shift 2
            ;;
        --resume)
            RESUME_FLAG="--resume"
            shift
            ;;
        --no-resume)
            RESUME_FLAG=""
            shift
            ;;
        --help)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Validate assignments file
if [[ ! -f "$ASSIGNMENTS_FILE" ]]; then
    log_error "Assignments file not found: $ASSIGNMENTS_FILE"
    exit 1
fi

# Read assignments from file
ASSIGNMENTS=()
while IFS= read -r line; do
    # Skip blank lines and comments
    line=$(echo "$line" | sed 's/#.*//' | xargs)
    if [[ -n "$line" ]]; then
        ASSIGNMENTS+=("$line")
    fi
done < "$ASSIGNMENTS_FILE"

if [[ ${#ASSIGNMENTS[@]} -eq 0 ]]; then
    log_error "No assignments found in $ASSIGNMENTS_FILE"
    exit 1
fi

log_info "Found ${#ASSIGNMENTS[@]} assignment(s) to process"
echo

# Display stage information
if [[ -n "$STOP_AFTER" ]]; then
    STAGE_DESC=""
    case "$STOP_AFTER" in
        1) STAGE_DESC="Submission discovery (VERIFY)" ;;
        2) STAGE_DESC="Pattern design (INTERACTIVE)" ;;
        3) STAGE_DESC="Marker agents" ;;
        4) STAGE_DESC="Normalization (REVIEW)" ;;
        5) STAGE_DESC="Dashboard review (INTERACTIVE)" ;;
        6) STAGE_DESC="Unification" ;;
        7|8|9) STAGE_DESC="Near completion" ;;
    esac
    log_info "Will stop after stage $STOP_AFTER: $STAGE_DESC"
    echo
fi

# Process each assignment
TOTAL=${#ASSIGNMENTS[@]}
SUCCESS_COUNT=0
FAILED_ASSIGNMENTS=()

for i in "${!ASSIGNMENTS[@]}"; do
    ASSIGNMENT="${ASSIGNMENTS[$i]}"
    ASSIGNMENT_NUM=$((i + 1))

    echo "=================================================================="
    log_info "Processing assignment $ASSIGNMENT_NUM/$TOTAL: $ASSIGNMENT"
    echo "=================================================================="
    echo

    # Resolve assignment path
    if [[ "$ASSIGNMENT" = /* ]]; then
        # Absolute path
        ASSIGNMENT_DIR="$ASSIGNMENT"
    else
        # Relative to project root
        ASSIGNMENT_DIR="$PROJECT_ROOT/$ASSIGNMENT"
    fi

    if [[ ! -d "$ASSIGNMENT_DIR" ]]; then
        log_error "Assignment directory not found: $ASSIGNMENT_DIR"
        FAILED_ASSIGNMENTS+=("$ASSIGNMENT (directory not found)")
        echo
        continue
    fi

    # Detect assignment type by checking for base notebook and overview.md
    OVERVIEW_FILE="$ASSIGNMENT_DIR/overview.md"

    if [[ ! -f "$OVERVIEW_FILE" ]]; then
        log_error "No overview.md found in $ASSIGNMENT_DIR"
        FAILED_ASSIGNMENTS+=("$ASSIGNMENT (missing overview.md)")
        echo
        continue
    fi

    # Check assignment_type in overview.md
    ASSIGNMENT_TYPE="structured"  # default
    if grep -q "assignment_type:\s*freeform" "$OVERVIEW_FILE" 2>/dev/null; then
        ASSIGNMENT_TYPE="freeform"
    fi

    log_info "Detected assignment type: $ASSIGNMENT_TYPE"

    # Determine which script to run
    if [[ "$ASSIGNMENT_TYPE" == "freeform" ]]; then
        MARK_SCRIPT="$PROJECT_ROOT/mark_freeform.sh"
    else
        MARK_SCRIPT="$PROJECT_ROOT/mark_structured.sh"
    fi

    if [[ ! -x "$MARK_SCRIPT" ]]; then
        log_error "Marking script not found or not executable: $MARK_SCRIPT"
        FAILED_ASSIGNMENTS+=("$ASSIGNMENT (missing script)")
        echo
        continue
    fi

    # Build command
    CMD=("$MARK_SCRIPT" "$ASSIGNMENT_DIR")

    if [[ -n "$STOP_AFTER" ]]; then
        CMD+=("--stop-after" "$STOP_AFTER")
    fi

    if [[ -n "$PARALLEL_OVERRIDE" ]]; then
        CMD+=("--parallel" "$PARALLEL_OVERRIDE")
    fi

    if [[ -n "$RESUME_FLAG" ]]; then
        CMD+=("$RESUME_FLAG")
    fi

    log_info "Running: ${CMD[*]}"
    echo

    # Execute marking script
    if "${CMD[@]}"; then
        log_success "Assignment completed successfully: $ASSIGNMENT"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        log_error "Assignment failed: $ASSIGNMENT"
        FAILED_ASSIGNMENTS+=("$ASSIGNMENT (marking failed)")
    fi

    echo
    echo
done

# Summary
echo "=================================================================="
echo "                    BATCH MARKING SUMMARY"
echo "=================================================================="
echo
log_info "Total assignments: $TOTAL"
log_success "Successful: $SUCCESS_COUNT"

if [[ ${#FAILED_ASSIGNMENTS[@]} -gt 0 ]]; then
    log_error "Failed: ${#FAILED_ASSIGNMENTS[@]}"
    echo
    echo "Failed assignments:"
    for failed in "${FAILED_ASSIGNMENTS[@]}"; do
        echo "  - $failed"
    done
    echo
    exit 1
else
    log_success "All assignments processed successfully!"
fi

# Next steps guidance
if [[ -n "$STOP_AFTER" ]]; then
    echo
    echo "=================================================================="
    echo "                       NEXT STEPS"
    echo "=================================================================="
    echo
    case "$STOP_AFTER" in
        1)
            log_info "✓ Stage 1 (Submission Discovery) complete for all assignments"
            echo
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            log_warning "VERIFY: Submissions found correctly"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo
            echo "Check submission manifests for each assignment:"
            for assignment in "${ASSIGNMENTS[@]}"; do
                if [[ "$assignment" = /* ]]; then
                    ASSIGNMENT_DIR="$assignment"
                else
                    ASSIGNMENT_DIR="$PROJECT_ROOT/$assignment"
                fi
                echo
                echo "📁 $assignment"
                echo "  • Manifest: $ASSIGNMENT_DIR/processed/submissions_manifest.json"
                echo "    Verify all expected students/groups were found"
            done
            echo
            log_info "When submissions look correct, continue with Round 2:"
            echo "  $(basename "$0") $ASSIGNMENTS_FILE --stop-after 2"
            ;;
        2)
            log_info "✓ Stage 2 (Pattern Design) complete for all assignments"
            echo
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            log_warning "REVIEW REQUIRED: Marking criteria and rubrics"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo
            echo "Please review the following files for each assignment:"
            for assignment in "${ASSIGNMENTS[@]}"; do
                if [[ "$assignment" = /* ]]; then
                    ASSIGNMENT_DIR="$assignment"
                else
                    ASSIGNMENT_DIR="$PROJECT_ROOT/$assignment"
                fi
                echo
                echo "📁 $assignment"
                echo "  • Rubric: $ASSIGNMENT_DIR/processed/rubric.md"
                if [[ -f "$ASSIGNMENT_DIR/processed/marking_criteria.md" ]]; then
                    echo "  • Criteria: $ASSIGNMENT_DIR/processed/marking_criteria.md"
                elif [[ -d "$ASSIGNMENT_DIR/processed/activities" ]]; then
                    echo "  • Criteria: $ASSIGNMENT_DIR/processed/activities/A*_criteria.md"
                fi
            done
            echo
            log_info "When criteria look good, continue with Round 3:"
            echo "  $(basename "$0") $ASSIGNMENTS_FILE --stop-after 4"
            ;;
        4)
            log_info "✓ Stage 4 (Normalization) complete for all assignments"
            echo
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            log_warning "REVIEW REQUIRED: Normalized scoring schemes"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo
            echo "Review normalized scoring for each assignment:"
            for assignment in "${ASSIGNMENTS[@]}"; do
                if [[ "$assignment" = /* ]]; then
                    ASSIGNMENT_DIR="$assignment"
                else
                    ASSIGNMENT_DIR="$PROJECT_ROOT/$assignment"
                fi
                echo
                echo "📁 $assignment"
                if [[ -d "$ASSIGNMENT_DIR/processed/normalized" ]]; then
                    echo "  • Scoring: $ASSIGNMENT_DIR/processed/normalized/"
                    echo "    Review scoring schemes before dashboard adjustment"
                fi
            done
            echo
            log_info "When scoring schemes look reasonable, continue with Round 4:"
            echo "  $(basename "$0") $ASSIGNMENTS_FILE --stop-after 5"
            ;;
        5)
            log_info "✓ Stage 5 (Dashboard Review) complete for all assignments"
            echo
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            log_warning "REVIEW REQUIRED: Adjustment dashboards and approve schemes"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo
            echo "Open and approve marking schemes in Jupyter:"
            for assignment in "${ASSIGNMENTS[@]}"; do
                if [[ "$assignment" = /* ]]; then
                    ASSIGNMENT_DIR="$assignment"
                else
                    ASSIGNMENT_DIR="$PROJECT_ROOT/$assignment"
                fi
                echo
                echo "📁 $assignment"
                echo "  jupyter notebook \"$ASSIGNMENT_DIR/processed/adjustment_dashboard.ipynb\""
            done
            echo
            log_info "After approving all schemes, complete with Round 5:"
            echo "  $(basename "$0") $ASSIGNMENTS_FILE"
            ;;
    esac
    echo
fi

exit 0
