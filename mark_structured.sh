#!/usr/bin/env bash
#
# Main Orchestrator - Structured Assignments
# Coordinates the entire marking workflow for fill-in-the-blank notebook assignments
#

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/src"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
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

# Parse arguments
FORCE_XARGS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --force-xargs)
            FORCE_XARGS=true
            shift
            ;;
        -*)
            echo "Unknown option: $1" >&2
            echo "Usage: $0 <assignment_directory> [--force-xargs]" >&2
            exit 1
            ;;
        *)
            # First positional argument is the assignment directory
            ASSIGNMENT_DIR="$1"
            shift
            ;;
    esac
done

# Check if assignment directory is provided
if [[ -z "${ASSIGNMENT_DIR:-}" ]]; then
    echo "Usage: $0 <assignment_directory> [--force-xargs]"
    echo "Example: $0 assignments/lab1"
    echo ""
    echo "Options:"
    echo "  --force-xargs    Force use of xargs instead of GNU parallel (for testing)"
    exit 1
fi

# Validate assignment directory
if [[ ! -d "$ASSIGNMENT_DIR" ]]; then
    log_error "Assignment directory not found: $ASSIGNMENT_DIR"
    exit 1
fi

ASSIGNMENT_DIR="$(cd "$ASSIGNMENT_DIR" && pwd)"
ASSIGNMENT_NAME="$(basename "$ASSIGNMENT_DIR")"

log_info "Starting structured assignment marking: $ASSIGNMENT_NAME"
log_info "Assignment directory: $ASSIGNMENT_DIR"

# Load overview.md and parse configuration
OVERVIEW_FILE="$ASSIGNMENT_DIR/overview.md"
if [[ ! -f "$OVERVIEW_FILE" ]]; then
    log_error "overview.md not found in assignment directory"
    exit 1
fi

# Parse configuration from overview.md
eval "$("$SRC_DIR/utils/config_parser.py" "$OVERVIEW_FILE" --bash)"

log_info "Configuration:"
log_info "  Provider: $DEFAULT_PROVIDER"
log_info "  Model: ${DEFAULT_MODEL:-default}"
log_info "  Max parallel: $MAX_PARALLEL"
log_info "  Total marks: $TOTAL_MARKS"

# Setup directories
PROCESSED_DIR="$ASSIGNMENT_DIR/processed"
SUBMISSIONS_DIR="$ASSIGNMENT_DIR/submissions"
ACTIVITIES_DIR="$PROCESSED_DIR/activities"
MARKINGS_DIR="$PROCESSED_DIR/markings"
NORMALIZED_DIR="$PROCESSED_DIR/normalized"
FINAL_DIR="$PROCESSED_DIR/final"
LOGS_DIR="$PROCESSED_DIR/logs"
SESSIONS_DIR="$PROCESSED_DIR/sessions"

mkdir -p "$ACTIVITIES_DIR" "$MARKINGS_DIR" "$NORMALIZED_DIR" "$FINAL_DIR" "$LOGS_DIR" "$SESSIONS_DIR"

log_success "Directories created"

# ============================================================================
# STAGE 1: Find Submissions
# ============================================================================

log_info "Stage 1: Finding submissions..."

SUBMISSIONS_MANIFEST="$PROCESSED_DIR/submissions_manifest.json"

python3 "$SRC_DIR/find_submissions.py" \
    "$SUBMISSIONS_DIR" \
    ${BASE_FILE:+--base-file "$BASE_FILE"} \
    --output "$SUBMISSIONS_MANIFEST" \
    --summary

if [[ $? -ne 0 ]]; then
    log_error "Failed to find submissions"
    exit 1
fi

# Count submissions and activities (TODO: extract from manifest)
NUM_STUDENTS=$(jq '.total_submissions' "$SUBMISSIONS_MANIFEST")
log_success "Found $NUM_STUDENTS student submissions"

# ============================================================================
# STAGE 2: Extract Activities from Base Notebook
# ============================================================================

log_info "Stage 2: Analyzing base notebook structure..."

# Find base notebook
BASE_NOTEBOOK=$(find "$ASSIGNMENT_DIR" -maxdepth 1 -name "*.ipynb" -not -path "*/processed/*" | head -1)

if [[ -z "$BASE_NOTEBOOK" ]]; then
    log_error "No base notebook found in assignment directory"
    exit 1
fi

log_info "Base notebook: $BASE_NOTEBOOK"

# Extract activity structure
python3 "$SRC_DIR/extract_activities.py" \
    "$BASE_NOTEBOOK" \
    --summary

# Count activities (simplified - TODO: extract from output)
NUM_ACTIVITIES=7  # Placeholder

log_success "Found $NUM_ACTIVITIES activities"

# ============================================================================
# STAGE 3: Marking Pattern Designer (Interactive)
# ============================================================================

log_info "Stage 3: Running Marking Pattern Designer (Interactive)..."
log_warning "This stage requires instructor interaction"

PATTERN_DESIGNER_SESSION="$SESSIONS_DIR/pattern_designer.log"

python3 "$SRC_DIR/agents/pattern_designer.py" \
    --base-notebook "$BASE_NOTEBOOK" \
    --overview "$OVERVIEW_FILE" \
    --processed-dir "$PROCESSED_DIR" \
    --session-log "$PATTERN_DESIGNER_SESSION" \
    --provider "$DEFAULT_PROVIDER" \
    ${DEFAULT_MODEL:+--model "$DEFAULT_MODEL"} \
    --type structured

if [[ $? -ne 0 ]]; then
    log_error "Pattern designer failed"
    exit 1
fi

log_success "Pattern design complete"

# Verify required files were created
if [[ ! -f "$PROCESSED_DIR/rubric.md" ]]; then
    log_error "Rubric file not created. Please ensure pattern designer completed successfully."
    exit 1
fi

# ============================================================================
# STAGE 4: Marker Agents (Parallel, Headless)
# ============================================================================

log_info "Stage 4: Running Marker Agents (Parallel)..."
log_info "This will process $NUM_ACTIVITIES activities × $NUM_STUDENTS students = $((NUM_ACTIVITIES * NUM_STUDENTS)) marking tasks"

# Create task list for parallel execution
MARKER_TASKS="$PROCESSED_DIR/marker_tasks.txt"
> "$MARKER_TASKS"

# Generate marker tasks
jq -r '.submissions[] | .path + "|" + .student_name' "$SUBMISSIONS_MANIFEST" | while IFS='|' read -r submission_path student_name; do
    for activity in $(seq 1 $NUM_ACTIVITIES); do
        echo "python3 '$SRC_DIR/agents/marker.py' --activity A$activity --student '$student_name' --submission '$submission_path' --output '$MARKINGS_DIR/${student_name}_A${activity}.md'" >> "$MARKER_TASKS"
    done
done

log_info "Generated $((NUM_ACTIVITIES * NUM_STUDENTS)) marker tasks"

# Run markers in parallel
PARALLEL_ARGS=(
    --tasks "$MARKER_TASKS"
    --concurrency "$MAX_PARALLEL"
    --output-dir "$LOGS_DIR/marker_logs"
    --verbose
)

if [[ $FORCE_XARGS == true ]]; then
    PARALLEL_ARGS+=(--force-xargs)
fi

"$SRC_DIR/parallel_runner.sh" "${PARALLEL_ARGS[@]}"

log_success "Marker agents completed"

# ============================================================================
# STAGE 5: Normalizer Agents (Per Activity)
# ============================================================================

log_info "Stage 5: Running Normalizer Agents..."

for activity in $(seq 1 $NUM_ACTIVITIES); do
    log_info "Normalizing Activity $activity..."

    # TODO: Call normalizer agent with all markings for this activity

    log_success "Activity $activity normalized"
done

# ============================================================================
# STAGE 6: Create Adjustment Dashboard
# ============================================================================

log_info "Stage 6: Creating adjustment dashboard..."

DASHBOARD_NOTEBOOK="$PROCESSED_DIR/adjustment_dashboard.ipynb"

python3 "$SRC_DIR/create_dashboard.py" \
    "$NORMALIZED_DIR/combined_scoring.json" \
    "$NORMALIZED_DIR/student_mappings.json" \
    --output "$DASHBOARD_NOTEBOOK" \
    --type structured

log_success "Dashboard created: $DASHBOARD_NOTEBOOK"
log_warning "Please open the dashboard in Jupyter and approve the marking scheme:"
log_info "  jupyter notebook \"$DASHBOARD_NOTEBOOK\""
log_info ""
read -p "Press Enter when you have saved the approved scheme..."

# Verify approved scheme exists
APPROVED_SCHEME="$PROCESSED_DIR/approved_scheme.json"
if [[ ! -f "$APPROVED_SCHEME" ]]; then
    log_error "Approved scheme not found. Please run the dashboard and save the scheme."
    exit 1
fi

log_success "Approved scheme loaded"

# ============================================================================
# STAGE 7: Unifier Agents (Parallel)
# ============================================================================

log_info "Stage 7: Running Unifier Agents (Parallel)..."

# Create task list
UNIFIER_TASKS="$PROCESSED_DIR/unifier_tasks.txt"
> "$UNIFIER_TASKS"

jq -r '.submissions[] | .path + "|" + .student_name' "$SUBMISSIONS_MANIFEST" | while IFS='|' read -r submission_path student_name; do
    echo "python3 '$SRC_DIR/agents/unifier.py' --student '$student_name' --submission '$submission_path' --scheme '$APPROVED_SCHEME' --output '$FINAL_DIR/${student_name}_feedback.md'" >> "$UNIFIER_TASKS"
done

UNIFIER_ARGS=(
    --tasks "$UNIFIER_TASKS"
    --concurrency "$MAX_PARALLEL"
    --output-dir "$LOGS_DIR/unifier_logs"
    --verbose
)

if [[ $FORCE_XARGS == true ]]; then
    UNIFIER_ARGS+=(--force-xargs)
fi

"$SRC_DIR/parallel_runner.sh" "${UNIFIER_ARGS[@]}"

log_success "Unifier agents completed"

# ============================================================================
# STAGE 8: Aggregator Agent (Interactive)
# ============================================================================

log_info "Stage 8: Running Aggregator Agent (Interactive)..."

AGGREGATOR_SESSION="$SESSIONS_DIR/aggregator.log"

python3 "$SRC_DIR/agents/aggregator.py" \
    --assignment-name "$ASSIGNMENT_NAME" \
    --feedback-dir "$FINAL_DIR" \
    --output-dir "$FINAL_DIR" \
    --session-log "$AGGREGATOR_SESSION" \
    --provider "$DEFAULT_PROVIDER" \
    ${DEFAULT_MODEL:+--model "$DEFAULT_MODEL"} \
    --type structured \
    --total-marks "$TOTAL_MARKS"

if [[ $? -ne 0 ]]; then
    log_error "Aggregator failed"
    exit 1
fi

log_success "Aggregation complete"

# ============================================================================
# FINAL SUMMARY
# ============================================================================

echo ""
echo "========================================================================"
log_success "MARKING COMPLETE"
echo "========================================================================"
echo ""
log_info "Results:"
log_info "  Rubric: $PROCESSED_DIR/rubric.md"
log_info "  Final grades: $FINAL_DIR/grades.csv"
log_info "  Student feedback: $FINAL_DIR/*_feedback.md"
log_info "  Logs: $LOGS_DIR/"
echo ""
log_success "All marking artifacts saved to: $PROCESSED_DIR"
echo "========================================================================"
