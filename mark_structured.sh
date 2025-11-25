#!/usr/bin/env bash
#
# Main Orchestrator - Structured Assignments
# Coordinates the entire marking workflow for fill-in-the-blank notebook assignments
#

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/src"

# Activate virtual environment if it exists
if [[ -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

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
RESUME=true  # Always resume by default

while [[ $# -gt 0 ]]; do
    case $1 in
        --force-xargs)
            FORCE_XARGS=true
            shift
            ;;
        --no-resume)
            RESUME=false
            shift
            ;;
        --clean)
            # Clean mode: remove processed directory and start fresh
            RESUME=false
            CLEAN_MODE=true
            shift
            ;;
        -*)
            echo "Unknown option: $1" >&2
            echo "Usage: $0 <assignment_directory> [OPTIONS]" >&2
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
    echo "Usage: $0 <assignment_directory> [OPTIONS]"
    echo "Example: $0 assignments/lab1"
    echo ""
    echo "Options:"
    echo "  --force-xargs    Force use of xargs instead of GNU parallel (for testing)"
    echo "  --no-resume      Start from scratch, don't resume from previous run"
    echo "  --clean          Remove processed directory and start fresh"
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
log_info "  Default model: ${DEFAULT_MODEL:-default}"
log_info "  Max parallel: $MAX_PARALLEL"
log_info "  Total marks: $TOTAL_MARKS"

# Function to get model for a specific stage
# Priority: stage-specific > assignment default > none (use provider default)
get_stage_model() {
    local stage="$1"
    local stage_var="STAGE_MODEL_${stage^^}"  # Convert to uppercase

    # Check if stage-specific model is set (use :- to handle unset variables)
    if [[ -n "${!stage_var:-}" ]]; then
        echo "${!stage_var}"
    elif [[ -n "${DEFAULT_MODEL:-}" ]]; then
        echo "$DEFAULT_MODEL"
    else
        echo ""
    fi
}

# Determine models for each stage
MODEL_PATTERN_DESIGNER=$(get_stage_model "pattern_designer")
MODEL_MARKER=$(get_stage_model "marker")
MODEL_NORMALIZER=$(get_stage_model "normalizer")
MODEL_UNIFIER=$(get_stage_model "unifier")
MODEL_AGGREGATOR=$(get_stage_model "aggregator")

# Log stage-specific models if any are set
if [[ -n "$MODEL_PATTERN_DESIGNER" || -n "$MODEL_MARKER" || -n "$MODEL_NORMALIZER" || -n "$MODEL_UNIFIER" || -n "$MODEL_AGGREGATOR" ]]; then
    log_info "Stage-specific models:"
    [[ -n "$MODEL_PATTERN_DESIGNER" ]] && log_info "  Pattern Designer: $MODEL_PATTERN_DESIGNER"
    [[ -n "$MODEL_MARKER" ]] && log_info "  Marker: $MODEL_MARKER"
    [[ -n "$MODEL_NORMALIZER" ]] && log_info "  Normalizer: $MODEL_NORMALIZER"
    [[ -n "$MODEL_UNIFIER" ]] && log_info "  Unifier: $MODEL_UNIFIER"
    [[ -n "$MODEL_AGGREGATOR" ]] && log_info "  Aggregator: $MODEL_AGGREGATOR"
fi

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

# Clean mode: remove processed directory
if [[ "${CLEAN_MODE:-false}" == true ]]; then
    log_warning "Clean mode: Removing processed directory..."
    rm -rf "$PROCESSED_DIR"
    mkdir -p "$ACTIVITIES_DIR" "$MARKINGS_DIR" "$NORMALIZED_DIR" "$FINAL_DIR" "$LOGS_DIR" "$SESSIONS_DIR"
    log_success "Cleaned and recreated directories"
else
    log_success "Directories created"
fi

# Resume mode notification
if [[ $RESUME == true ]]; then
    log_info "Resume mode: Will skip completed stages and tasks"
fi

# ============================================================================
# STAGE 1: Find Submissions
# ============================================================================

SUBMISSIONS_MANIFEST="$PROCESSED_DIR/submissions_manifest.json"

if [[ $RESUME == true && -f "$SUBMISSIONS_MANIFEST" ]]; then
    log_info "Stage 1: Skipping (submissions manifest already exists)"
else
    log_info "Stage 1: Finding submissions..."

    python3 "$SRC_DIR/find_submissions.py" \
        "$SUBMISSIONS_DIR" \
        ${BASE_FILE:+--base-file "$BASE_FILE"} \
        --output "$SUBMISSIONS_MANIFEST" \
        --summary

    if [[ $? -ne 0 ]]; then
        log_error "Failed to find submissions"
        exit 1
    fi
fi

# Count submissions and activities (TODO: extract from manifest)
NUM_STUDENTS=$(jq '.total_submissions' "$SUBMISSIONS_MANIFEST")
log_success "Found $NUM_STUDENTS student submissions"

# ============================================================================
# STAGE 2: Extract Activities from Base Notebook
# ============================================================================

# Find base notebook
BASE_NOTEBOOK=$(find "$ASSIGNMENT_DIR" -maxdepth 1 -name "*.ipynb" -not -path "*/processed/*" | head -1)

if [[ -z "$BASE_NOTEBOOK" ]]; then
    log_error "No base notebook found in assignment directory"
    exit 1
fi

# Check if activities already extracted
ACTIVITIES_JSON="$PROCESSED_DIR/activities.json"
if [[ $RESUME == true && -f "$ACTIVITIES_JSON" ]]; then
    log_info "Stage 2: Skipping (activities already extracted)"
else
    log_info "Stage 2: Analyzing base notebook structure..."
    log_info "Base notebook: $BASE_NOTEBOOK"
fi

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

# Check if pattern design already complete
RUBRIC_FILE="$PROCESSED_DIR/rubric.md"
ACTIVITIES_DIR="$PROCESSED_DIR/activities"

if [[ $RESUME == true && -f "$RUBRIC_FILE" && -d "$ACTIVITIES_DIR" ]]; then
    CRITERIA_COUNT=$(find "$ACTIVITIES_DIR" -name "A*_criteria.md" 2>/dev/null | wc -l | tr -d ' ')
    if [[ $CRITERIA_COUNT -ge $NUM_ACTIVITIES ]]; then
        log_info "Stage 3: Skipping (rubric and $CRITERIA_COUNT activity criteria files already exist)"
    else
        log_info "Stage 3: Running Marking Pattern Designer (Interactive)..."
        log_warning "This stage requires instructor interaction (found only $CRITERIA_COUNT/$NUM_ACTIVITIES criteria files)"

        PATTERN_DESIGNER_SESSION="$SESSIONS_DIR/pattern_designer.log"

        python3 "$SRC_DIR/agents/pattern_designer.py" \
            --base-notebook "$BASE_NOTEBOOK" \
            --overview "$OVERVIEW_FILE" \
            --processed-dir "$PROCESSED_DIR" \
            --session-log "$PATTERN_DESIGNER_SESSION" \
            --provider "$DEFAULT_PROVIDER" \
            ${MODEL_PATTERN_DESIGNER:+--model "$MODEL_PATTERN_DESIGNER"} \
            --type structured

        if [[ $? -ne 0 ]]; then
            log_error "Pattern designer failed"
            exit 1
        fi

        log_success "Pattern design complete"
    fi
else
    log_info "Stage 3: Running Marking Pattern Designer (Interactive)..."
    log_warning "This stage requires instructor interaction"

    PATTERN_DESIGNER_SESSION="$SESSIONS_DIR/pattern_designer.log"

    python3 "$SRC_DIR/agents/pattern_designer.py" \
        --base-notebook "$BASE_NOTEBOOK" \
        --overview "$OVERVIEW_FILE" \
        --processed-dir "$PROCESSED_DIR" \
        --session-log "$PATTERN_DESIGNER_SESSION" \
        --provider "$DEFAULT_PROVIDER" \
        ${MODEL_PATTERN_DESIGNER:+--model "$MODEL_PATTERN_DESIGNER"} \
        --type structured

    if [[ $? -ne 0 ]]; then
        log_error "Pattern designer failed"
        exit 1
    fi

    log_success "Pattern design complete"
fi

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

# Generate marker tasks (one per activity per student)
# In resume mode, skip tasks where output file already exists
jq -r '.submissions[] | .path + "|" + .student_name' "$SUBMISSIONS_MANIFEST" | while IFS='|' read -r submission_path student_name; do
    for activity in $(seq 1 $NUM_ACTIVITIES); do
        output_file="$MARKINGS_DIR/${student_name}_A${activity}.md"

        if [[ $RESUME == true && -f "$output_file" ]]; then
            # Skip this task - output already exists
            :
        else
            # Add task to list
            echo "python3 '$SRC_DIR/agents/marker.py' --activity A$activity --student '$student_name' --submission '$submission_path' --output '$output_file' --provider '$DEFAULT_PROVIDER' ${MODEL_MARKER:+--model '$MODEL_MARKER'}" >> "$MARKER_TASKS"
        fi
    done
done

# Count tasks and report
TASKS_TO_RUN=$(wc -l < "$MARKER_TASKS" | tr -d ' ')
EXPECTED_TOTAL=$((NUM_ACTIVITIES * NUM_STUDENTS))

if [[ $TASKS_TO_RUN -eq 0 ]]; then
    log_success "All $EXPECTED_TOTAL marker tasks already completed"
else
    if [[ $RESUME == true ]]; then
        SKIPPED=$((EXPECTED_TOTAL - TASKS_TO_RUN))
        log_info "Generated $TASKS_TO_RUN marker tasks (skipped $SKIPPED already completed)"
    else
        log_info "Generated $TASKS_TO_RUN marker tasks"
    fi
fi

# Run markers in parallel
if [[ $TASKS_TO_RUN -gt 0 ]]; then
    # Clear marker_logs to avoid counting old stdout files in progress calculation
    if [[ $RESUME == true ]]; then
        rm -rf "$LOGS_DIR/marker_logs"
        mkdir -p "$LOGS_DIR/marker_logs"
    fi

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
else
    log_info "No marker tasks to run"
fi

# ============================================================================
# STAGE 5: Normalizer Agents (Per Activity)
# ============================================================================

log_info "Stage 5: Running Normalizer Agents..."

for activity in $(seq 1 $NUM_ACTIVITIES); do
    SCORING_OUTPUT="$NORMALIZED_DIR/A${activity}_scoring.md"

    if [[ $RESUME == true && -f "$SCORING_OUTPUT" ]]; then
        log_info "Activity $activity: Skipping (scoring already exists)"
    else
        log_info "Normalizing Activity $activity..."

        # Call normalizer agent to aggregate all markings for this activity
        python3 "$SRC_DIR/agents/normalizer.py" \
            --activity "A$activity" \
            --markings-dir "$MARKINGS_DIR" \
            --processed-dir "$PROCESSED_DIR" \
            --output "$SCORING_OUTPUT" \
            --provider "$DEFAULT_PROVIDER" \
            ${MODEL_NORMALIZER:+--model "$MODEL_NORMALIZER"} \
            --type structured

        if [[ $? -ne 0 ]]; then
            log_error "Normalizer failed for Activity $activity"
            exit 1
        fi

        log_success "Activity $activity normalized"
    fi
done

# Create combined scoring file for dashboard
log_info "Creating combined scoring data..."
python3 "$SRC_DIR/utils/combine_normalized.py" \
    --normalized-dir "$NORMALIZED_DIR" \
    --output "$NORMALIZED_DIR/combined_scoring.json"

if [[ $? -ne 0 ]]; then
    log_error "Failed to create combined scoring data"
    exit 1
fi

log_success "Stage 5 complete"

# ============================================================================
# STAGE 6: Create Adjustment Dashboard
# ============================================================================

DASHBOARD_NOTEBOOK="$PROCESSED_DIR/adjustment_dashboard.ipynb"
APPROVED_SCHEME="$PROCESSED_DIR/approved_scheme.json"

if [[ $RESUME == true && -f "$APPROVED_SCHEME" ]]; then
    log_info "Stage 6: Skipping (approved scheme already exists)"
    log_success "Approved scheme loaded: $APPROVED_SCHEME"
else
    log_info "Stage 6: Creating adjustment dashboard..."

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
    if [[ ! -f "$APPROVED_SCHEME" ]]; then
        log_error "Approved scheme not found. Please run the dashboard and save the scheme."
        exit 1
    fi

    log_success "Approved scheme loaded"
fi

# ============================================================================
# STAGE 7: Unifier Agents (Parallel)
# ============================================================================

log_info "Stage 7: Running Unifier Agents (Parallel)..."

# Create task list
UNIFIER_TASKS="$PROCESSED_DIR/unifier_tasks.txt"
> "$UNIFIER_TASKS"

# Generate unifier tasks (one per student)
# In resume mode, skip tasks where output file already exists
jq -r '.submissions[] | .path + "|" + .student_name' "$SUBMISSIONS_MANIFEST" | while IFS='|' read -r submission_path student_name; do
    output_file="$FINAL_DIR/${student_name}_feedback.md"

    if [[ $RESUME == true && -f "$output_file" ]]; then
        # Skip this task - output already exists
        :
    else
        # Add task to list
        echo "python3 '$SRC_DIR/agents/unifier.py' --student '$student_name' --submission '$submission_path' --scheme '$APPROVED_SCHEME' --markings-dir '$MARKINGS_DIR' --output '$output_file' --type structured --provider '$DEFAULT_PROVIDER' ${MODEL_UNIFIER:+--model '$MODEL_UNIFIER'}" >> "$UNIFIER_TASKS"
    fi
done

# Count tasks and report
UNIFIER_TASKS_TO_RUN=$(wc -l < "$UNIFIER_TASKS" | tr -d ' ')

if [[ $UNIFIER_TASKS_TO_RUN -eq 0 ]]; then
    log_success "All $NUM_STUDENTS unifier tasks already completed"
else
    if [[ $RESUME == true ]]; then
        UNIFIER_SKIPPED=$((NUM_STUDENTS - UNIFIER_TASKS_TO_RUN))
        log_info "Generated $UNIFIER_TASKS_TO_RUN unifier tasks (skipped $UNIFIER_SKIPPED already completed)"

        # Clear unifier_logs to avoid counting old stdout files in progress calculation
        rm -rf "$LOGS_DIR/unifier_logs"
        mkdir -p "$LOGS_DIR/unifier_logs"
    else
        log_info "Generated $UNIFIER_TASKS_TO_RUN unifier tasks"
    fi

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
fi

# ============================================================================
# STAGE 8: Aggregator Agent (Interactive)
# ============================================================================

GRADES_CSV="$FINAL_DIR/grades.csv"

if [[ $RESUME == true && -f "$GRADES_CSV" ]]; then
    log_info "Stage 8: Skipping (grades already generated)"
    log_success "Grades CSV: $GRADES_CSV"
else
    log_info "Stage 8: Running Aggregator Agent (Interactive)..."

    AGGREGATOR_SESSION="$SESSIONS_DIR/aggregator.log"

    python3 "$SRC_DIR/agents/aggregator.py" \
        --assignment-name "$ASSIGNMENT_NAME" \
        --feedback-dir "$FINAL_DIR" \
        --output-dir "$FINAL_DIR" \
        --session-log "$AGGREGATOR_SESSION" \
        --provider "$DEFAULT_PROVIDER" \
        ${MODEL_AGGREGATOR:+--model "$MODEL_AGGREGATOR"} \
        --type structured \
        --total-marks "$TOTAL_MARKS"

    if [[ $? -ne 0 ]]; then
        log_error "Aggregator failed"
        exit 1
    fi

    log_success "Aggregation complete"
fi

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
