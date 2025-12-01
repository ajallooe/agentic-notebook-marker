#!/usr/bin/env bash
#
# Main Orchestrator - Free-form Assignments
# Coordinates the marking workflow for free-form notebook assignments built from scratch
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
CLEAN_ARTIFACTS=true  # Clean artifacts by default
STOP_AFTER_STAGE=""
PARALLEL_OVERRIDE=""
AUTO_APPROVE=false
FORCE_COMPLETE=false
PROVIDER_OVERRIDE=""
MODEL_OVERRIDE=""

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
        --no-clean-artifacts)
            CLEAN_ARTIFACTS=false
            shift
            ;;
        --stop-after)
            STOP_AFTER_STAGE="$2"
            shift 2
            ;;
        --parallel)
            PARALLEL_OVERRIDE="$2"
            shift 2
            ;;
        --auto-approve)
            AUTO_APPROVE=true
            shift
            ;;
        --force-complete)
            FORCE_COMPLETE=true
            shift
            ;;
        --provider)
            PROVIDER_OVERRIDE="$2"
            shift 2
            ;;
        --model)
            MODEL_OVERRIDE="$2"
            shift 2
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
    echo "Example: $0 assignments/project1"
    echo ""
    echo "Options:"
    echo "  --force-xargs         Force use of xargs instead of GNU parallel (for testing)"
    echo "  --no-resume           Start from scratch, don't resume from previous run"
    echo "  --clean               Remove processed directory and start fresh"
    echo "  --no-clean-artifacts  Skip cleaning LLM artifacts from output files"
    echo "  --stop-after N        Stop after completing stage N (1-8)"
    echo "  --parallel N          Override max parallel tasks (default from config)"
    echo "  --auto-approve        Skip interactive stages (pattern design, dashboard approval)"
    echo "  --force-complete      Generate zero-mark feedback for failed students and continue"
    echo "  --provider NAME       Override LLM provider (claude, gemini, or codex)"
    echo "  --model NAME          Override model name"
    exit 1
fi

# Validate assignment directory
if [[ ! -d "$ASSIGNMENT_DIR" ]]; then
    log_error "Assignment directory not found: $ASSIGNMENT_DIR"
    exit 1
fi

ASSIGNMENT_DIR="$(cd "$ASSIGNMENT_DIR" && pwd)"
ASSIGNMENT_NAME="$(basename "$ASSIGNMENT_DIR")"

log_info "Starting free-form assignment marking: $ASSIGNMENT_NAME"
log_info "Assignment directory: $ASSIGNMENT_DIR"

# Load overview.md and parse configuration
OVERVIEW_FILE="$ASSIGNMENT_DIR/overview.md"
if [[ ! -f "$OVERVIEW_FILE" ]]; then
    log_error "overview.md not found in assignment directory"
    exit 1
fi

# Parse configuration from overview.md
eval "$("$SRC_DIR/utils/config_parser.py" "$OVERVIEW_FILE" --bash)"

# Apply command-line overrides
if [[ -n "$PROVIDER_OVERRIDE" ]]; then
    DEFAULT_PROVIDER="$PROVIDER_OVERRIDE"
fi

if [[ -n "$MODEL_OVERRIDE" ]]; then
    DEFAULT_MODEL="$MODEL_OVERRIDE"
    # Clear stage-specific models when --model is passed
    unset STAGE_MODEL_PATTERN_DESIGNER
    unset STAGE_MODEL_MARKER
    unset STAGE_MODEL_NORMALIZER
    unset STAGE_MODEL_UNIFIER
    unset STAGE_MODEL_AGGREGATOR
fi

log_info "Configuration:"
log_info "  Provider: $DEFAULT_PROVIDER"
log_info "  Default model: ${DEFAULT_MODEL:-default}"
if [[ "$AUTO_APPROVE" == true ]]; then
    log_info "  Auto-approve: ENABLED (skipping interactive stages)"
fi

# Apply --parallel override if provided
if [[ -n "$PARALLEL_OVERRIDE" ]]; then
    MAX_PARALLEL="$PARALLEL_OVERRIDE"
    log_info "  Max parallel: $MAX_PARALLEL (overridden by --parallel)"
else
    log_info "  Max parallel: $MAX_PARALLEL"
fi

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
MARKINGS_DIR="$PROCESSED_DIR/markings"
NORMALIZED_DIR="$PROCESSED_DIR/normalized"
FINAL_DIR="$PROCESSED_DIR/final"
LOGS_DIR="$PROCESSED_DIR/logs"
SESSIONS_DIR="$PROCESSED_DIR/sessions"

mkdir -p "$MARKINGS_DIR" "$NORMALIZED_DIR" "$FINAL_DIR" "$LOGS_DIR" "$SESSIONS_DIR"

# Clean mode: remove processed directory
if [[ "${CLEAN_MODE:-false}" == true ]]; then
    log_warning "Clean mode: Removing processed directory..."
    rm -rf "$PROCESSED_DIR"
    mkdir -p "$MARKINGS_DIR" "$NORMALIZED_DIR" "$FINAL_DIR" "$LOGS_DIR" "$SESSIONS_DIR"
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
        --output "$SUBMISSIONS_MANIFEST" \
        --summary

    if [[ $? -ne 0 ]]; then
        log_error "Failed to find submissions"
        exit 1
    fi
fi

# Count submissions
NUM_STUDENTS=$(jq '.total_submissions' "$SUBMISSIONS_MANIFEST")
log_success "Found $NUM_STUDENTS student submissions"

# Stop after stage 1 if requested
if [[ "$STOP_AFTER_STAGE" == "1" ]]; then
    log_info "Stopping after stage 1 as requested (--stop-after 1)"
    exit 0
fi

# ============================================================================
# STAGE 1.5: Extract Problem Contexts (Different-Problem Assignments Only)
# ============================================================================

PROBLEM_CONTEXTS="$PROCESSED_DIR/problem_contexts.json"

if [[ "$DIFFERENT_PROBLEMS" == "true" ]]; then
    if [[ $RESUME == true && -f "$PROBLEM_CONTEXTS" ]]; then
        log_info "Stage 1.5: Skipping (problem contexts already extracted)"
    else
        log_info "Stage 1.5: Extracting problem contexts from group directories..."

        python3 "$SRC_DIR/extract_problem_context.py" \
            --manifest "$SUBMISSIONS_MANIFEST" \
            --output "$PROBLEM_CONTEXTS" \
            --verbose

        if [[ $? -ne 0 ]]; then
            log_error "Problem context extraction failed"
            exit 1
        fi

        log_success "Problem contexts extracted"
    fi
else
    log_info "Stage 1.5: Skipping (not a different-problems assignment)"
fi

# ============================================================================
# STAGE 2: Marking Pattern Designer (Interactive)
# ============================================================================

if [[ $RESUME == true && -f "$PROCESSED_DIR/rubric.md" && -f "$PROCESSED_DIR/marking_criteria.md" ]]; then
    log_info "Stage 2: Skipping (rubric and marking criteria already exist)"
    log_success "Pattern design complete"
else
    if [[ "$AUTO_APPROVE" == true ]]; then
        log_info "Stage 2: Running Marking Pattern Designer (Auto-approve mode)..."
    else
        log_info "Stage 2: Running Marking Pattern Designer (Interactive)..."
        log_warning "This stage requires instructor interaction"
    fi

    PATTERN_DESIGNER_SESSION="$SESSIONS_DIR/pattern_designer.log"

    python3 "$SRC_DIR/agents/pattern_designer.py" \
        --overview "$OVERVIEW_FILE" \
        --processed-dir "$PROCESSED_DIR" \
        --session-log "$PATTERN_DESIGNER_SESSION" \
        --provider "$DEFAULT_PROVIDER" \
        ${MODEL_PATTERN_DESIGNER:+--model "$MODEL_PATTERN_DESIGNER"} \
        --type freeform \
        $([[ "$DIFFERENT_PROBLEMS" == "true" ]] && echo "--different-problems") \
        $([[ "$AUTO_APPROVE" == "true" ]] && echo "--auto-approve")

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

    if [[ ! -f "$PROCESSED_DIR/marking_criteria.md" ]]; then
        log_error "Marking criteria file not created. Please ensure pattern designer completed successfully."
        exit 1
    fi
fi

# Stop after stage 2 if requested
if [[ "$STOP_AFTER_STAGE" == "2" ]]; then
    log_info "Stopping after stage 2 as requested (--stop-after 2)"
    exit 0
fi

# ============================================================================
# STAGE 3: Marker Agents (Parallel, Headless)
# ============================================================================

log_info "Stage 3: Running Marker Agents (Parallel)..."
log_info "This will process $NUM_STUDENTS students"

# Create task list for parallel execution
MARKER_TASKS="$PROCESSED_DIR/marker_tasks.txt"
> "$MARKER_TASKS"

# Generate marker tasks (one per student for free-form)
# In resume mode, skip tasks where output file already exists
jq -r '.submissions[] | .path + "|" + .student_name' "$SUBMISSIONS_MANIFEST" | while IFS='|' read -r submission_path student_name; do
    output_file="$MARKINGS_DIR/${student_name}.md"

    if [[ $RESUME == true && -f "$output_file" ]]; then
        # Skip this task - output already exists
        :
    else
        # Add task to list
        task_cmd="python3 '$SRC_DIR/agents/marker.py' --student '$student_name' --submission '$submission_path' --criteria '$PROCESSED_DIR/marking_criteria.md' --output '$output_file' --type freeform --provider '$DEFAULT_PROVIDER' ${MODEL_MARKER:+--model '$MODEL_MARKER'}"

        # For different-problems assignments, pass problem context
        if [[ "$DIFFERENT_PROBLEMS" == "true" && -f "$PROBLEM_CONTEXTS" ]]; then
            task_cmd="$task_cmd --problem-context '$PROBLEM_CONTEXTS'"
        fi

        echo "$task_cmd" >> "$MARKER_TASKS"
    fi
done

# Count tasks and report
TASKS_TO_RUN=$(wc -l < "$MARKER_TASKS" | tr -d ' ')

if [[ $TASKS_TO_RUN -eq 0 ]]; then
    log_success "All $NUM_STUDENTS marker tasks already completed"
else
    if [[ $RESUME == true ]]; then
        SKIPPED=$((NUM_STUDENTS - TASKS_TO_RUN))
        log_info "Generated $TASKS_TO_RUN marker tasks (skipped $SKIPPED already completed)"
    else
        log_info "Generated $TASKS_TO_RUN marker tasks"
    fi

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
fi

# Stop after stage 3 if requested
if [[ "$STOP_AFTER_STAGE" == "3" ]]; then
    log_info "Stopping after stage 3 as requested (--stop-after 3)"
    exit 0
fi

# ============================================================================
# STAGE 4: Normalizer Agent
# ============================================================================

SCORING_OUTPUT="$NORMALIZED_DIR/scoring.md"

if [[ $RESUME == true && -f "$SCORING_OUTPUT" ]]; then
    log_info "Stage 4: Skipping (scoring already exists)"
    log_success "Normalization complete"
else
    log_info "Stage 4: Running Normalizer Agent..."

    python3 "$SRC_DIR/agents/normalizer.py" \
        --markings-dir "$MARKINGS_DIR" \
        --processed-dir "$PROCESSED_DIR" \
        --output "$SCORING_OUTPUT" \
        --provider "$DEFAULT_PROVIDER" \
        ${MODEL_NORMALIZER:+--model "$MODEL_NORMALIZER"} \
        --type freeform

    if [[ $? -ne 0 ]]; then
        log_error "Normalizer failed"
        exit 1
    fi

    log_success "Normalization complete"
fi

# Stop after stage 4 if requested
if [[ "$STOP_AFTER_STAGE" == "4" ]]; then
    log_info "Stopping after stage 4 as requested (--stop-after 4)"
    exit 0
fi

# ============================================================================
# STAGE 5: Create Adjustment Dashboard
# ============================================================================

DASHBOARD_NOTEBOOK="$PROCESSED_DIR/adjustment_dashboard.ipynb"
APPROVED_SCHEME="$PROCESSED_DIR/approved_scheme.json"

if [[ $RESUME == true && -f "$APPROVED_SCHEME" ]]; then
    log_info "Stage 5: Skipping (approved scheme already exists)"
    log_success "Approved scheme loaded: $APPROVED_SCHEME"
else
    if [[ "$AUTO_APPROVE" == true ]]; then
        log_info "Stage 5: Creating adjustment dashboard (Auto-approve mode)..."
    else
        log_info "Stage 5: Creating adjustment dashboard..."
    fi

    python3 "$SRC_DIR/create_dashboard.py" \
        "$NORMALIZED_DIR/combined_scoring.json" \
        "$NORMALIZED_DIR/student_mappings.json" \
        --output "$DASHBOARD_NOTEBOOK" \
        --type freeform \
        $([[ "$AUTO_APPROVE" == "true" ]] && echo "--auto-approve")

    log_success "Dashboard created: $DASHBOARD_NOTEBOOK"

    if [[ "$AUTO_APPROVE" == true ]]; then
        log_info "Auto-approved marking scheme saved to: $APPROVED_SCHEME"
    else
        log_warning "Please open the dashboard in Jupyter and approve the marking scheme:"
        log_info "  jupyter notebook \"$DASHBOARD_NOTEBOOK\""
        log_info ""
        read -p "Press Enter when you have saved the approved scheme..."
    fi

    # Verify approved scheme exists
    if [[ ! -f "$APPROVED_SCHEME" ]]; then
        log_error "Approved scheme not found. Please run the dashboard and save the scheme."
        exit 1
    fi

    log_success "Approved scheme loaded"
fi

# Stop after stage 5 if requested
if [[ "$STOP_AFTER_STAGE" == "5" ]]; then
    log_info "Stopping after stage 5 as requested (--stop-after 5)"
    exit 0
fi

# ============================================================================
# STAGE 6: Unifier Agents (Parallel)
# ============================================================================

log_info "Stage 6: Running Unifier Agents (Parallel)..."

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
        echo "python3 '$SRC_DIR/agents/unifier.py' --student '$student_name' --submission '$submission_path' --scheme '$APPROVED_SCHEME' --markings-dir '$MARKINGS_DIR' --output '$output_file' --type freeform --provider '$DEFAULT_PROVIDER' ${MODEL_UNIFIER:+--model '$MODEL_UNIFIER'}" >> "$UNIFIER_TASKS"
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

# Check for missing feedback files and handle with --force-complete
FEEDBACK_COUNT=$(find "$FINAL_DIR" -maxdepth 1 -name "*_feedback.md" 2>/dev/null | wc -l | tr -d ' ')
if [[ $FEEDBACK_COUNT -lt $NUM_STUDENTS ]]; then
    MISSING_COUNT=$((NUM_STUDENTS - FEEDBACK_COUNT))
    log_warning "$MISSING_COUNT student(s) missing feedback files"

    if [[ "$FORCE_COMPLETE" == true ]]; then
        log_info "Force-completing: generating zero-mark feedback for failed students..."

        python3 "$SRC_DIR/utils/force_complete.py" \
            "$ASSIGNMENT_DIR" \
            --total-marks "$TOTAL_MARKS" \
            --type freeform

        if [[ $? -ne 0 ]]; then
            log_error "Force complete failed"
            exit 1
        fi

        log_success "Zero-mark feedback generated for $MISSING_COUNT student(s)"
        log_warning "These students require manual review!"
    else
        log_error "Cannot continue: $MISSING_COUNT student(s) failed to process"
        log_info "To see error details, run:"
        log_info "  ./review_errors.sh \"$ASSIGNMENT_DIR\""
        log_info ""
        log_info "Options:"
        log_info "  1. Fix the errors and re-run (resume will pick up where it left off)"
        log_info "  2. Use --force-complete to assign zero marks to failed students"
        exit 1
    fi
fi

# Stop after stage 6 if requested
if [[ "$STOP_AFTER_STAGE" == "6" ]]; then
    log_info "Stopping after stage 6 as requested (--stop-after 6)"
    exit 0
fi

# ============================================================================
# STAGE 6.5: Duplicate Group Feedback (Group Assignments Only)
# ============================================================================

GROUPS_CSV="$ASSIGNMENT_DIR/groups.csv"

if [[ "$GROUP_ASSIGNMENT" == "true" ]]; then
    if [[ -f "$GROUPS_CSV" ]]; then
        log_info "Stage 6.5: Duplicating group feedback to individual students..."

        python3 "$SRC_DIR/duplicate_group_feedback.py" \
            --groups "$GROUPS_CSV" \
            --feedback-dir "$FINAL_DIR" \
            --verbose

        if [[ $? -ne 0 ]]; then
            log_error "Group feedback duplication failed"
            exit 1
        fi

        log_success "Group feedback duplicated for individual students"
    else
        log_warning "Group assignment specified but groups.csv not found: $GROUPS_CSV"
        log_warning "Continuing with group submissions only"
    fi
else
    log_info "Stage 6.5: Skipping (not a group assignment)"
fi

# ============================================================================
# STAGE 7: Aggregator Agent (Interactive)
# ============================================================================

GRADES_CSV="$FINAL_DIR/grades.csv"

if [[ $RESUME == true && -f "$GRADES_CSV" ]]; then
    log_info "Stage 7: Skipping (grades already generated)"
    log_success "Grades CSV: $GRADES_CSV"
else
    log_info "Stage 7: Aggregating grades..."

    python3 "$SRC_DIR/aggregate_grades.py" \
        --feedback-dir "$FINAL_DIR" \
        --output "$GRADES_CSV" \
        --total-marks "$TOTAL_MARKS" \
        --type freeform

    if [[ $? -ne 0 ]]; then
        log_error "Grade aggregation failed"
        exit 1
    fi

    log_success "Aggregation complete"
fi

# ============================================================================
# STAGE 7.5: Clean Artifacts from grades.csv
# ============================================================================

if [[ $CLEAN_ARTIFACTS == true ]]; then
    log_info "Stage 7.5: Cleaning artifacts from grades.csv..."
    python3 "$SRC_DIR/clean_artifacts.py" "$GRADES_CSV" --in-place --verbose

    if [[ $? -ne 0 ]]; then
        log_warning "Artifact cleaning failed (non-critical)"
    else
        log_success "Artifacts cleaned from grades.csv"
    fi
else
    log_info "Stage 7.5: Skipping artifact cleaning (--no-clean-artifacts)"
fi

# Stop after stage 7 if requested
if [[ "$STOP_AFTER_STAGE" == "7" ]]; then
    log_info "Stopping after stage 7 as requested (--stop-after 7)"
    exit 0
fi

# ============================================================================
# STAGE 8: Gradebook Translation (Optional, Automatic)
# ============================================================================

GRADEBOOKS_DIR="$ASSIGNMENT_DIR/gradebooks"
TRANSLATION_DIR="$PROCESSED_DIR/translation"
TRANSLATION_MAPPING="$TRANSLATION_DIR/translation_mapping.json"

# Check if gradebook CSVs are provided
if [[ -d "$GRADEBOOKS_DIR" ]] && compgen -G "$GRADEBOOKS_DIR/*.csv" > /dev/null; then
    log_info "Stage 8: Gradebook translation (automatic)..."

    # Count gradebook files
    GRADEBOOK_FILES=("$GRADEBOOKS_DIR"/*.csv)
    NUM_GRADEBOOKS=${#GRADEBOOK_FILES[@]}
    log_info "Found $NUM_GRADEBOOKS gradebook CSV file(s) in $GRADEBOOKS_DIR"

    # Check if translation already complete
    if [[ $RESUME == true && -f "$TRANSLATION_MAPPING" && -d "$TRANSLATION_DIR" && -f "$TRANSLATION_DIR/translation_report.txt" ]]; then
        log_info "Translation already complete (mapping and report exist)"
        log_success "Translation results: $TRANSLATION_DIR"
    else
        mkdir -p "$TRANSLATION_DIR"

        # Build gradebook arguments
        GRADEBOOK_ARGS=()
        for gradebook in "${GRADEBOOK_FILES[@]}"; do
            GRADEBOOK_ARGS+=(--gradebooks "$gradebook")
        done

        log_info "Creating translation mapping..."

        python3 "$SRC_DIR/agents/translator.py" \
            --assignment-name "$ASSIGNMENT_NAME" \
            --total-marks "$TOTAL_MARKS" \
            --assignment-type freeform \
            --grades-csv "$GRADES_CSV" \
            "${GRADEBOOK_ARGS[@]}" \
            --output-path "$TRANSLATION_DIR" \
            --provider "$DEFAULT_PROVIDER" \
            ${MODEL_AGGREGATOR:+--model "$MODEL_AGGREGATOR"}

        if [[ $? -ne 0 ]]; then
            log_error "Translation mapping failed"
            log_warning "Continuing with marking complete, but gradebooks not updated"
        elif [[ ! -f "$TRANSLATION_MAPPING" ]]; then
            log_error "Translation mapping file not created"
            log_warning "Continuing with marking complete, but gradebooks not updated"
        else
            log_success "Translation mapping created"

            # Show mapping summary
            if command -v jq &> /dev/null; then
                echo ""
                echo "Translation Summary:"
                jq -r '.summary | to_entries | .[] | "  \(.key): \(.value)"' "$TRANSLATION_MAPPING"
                echo ""
            fi

            if [[ "$AUTO_APPROVE" == true ]]; then
                log_info "Auto-approve mode: applying translation automatically..."
            else
                log_warning "Review the mapping before applying:"
                log_info "  Mapping file: $TRANSLATION_MAPPING"
                log_info ""
                read -p "Press Enter to apply translation, or Ctrl+C to skip..."
            fi

            # Apply translation
            log_info "Applying translation to gradebooks..."

            python3 "$SRC_DIR/apply_translation.py" \
                --mapping "$TRANSLATION_MAPPING" \
                --output-dir "$TRANSLATION_DIR" \
                --apply

            if [[ $? -ne 0 ]]; then
                log_error "Translation application failed"
                log_warning "Original gradebooks unchanged"
            else
                log_success "Translation applied successfully"
                log_info "  Updated gradebooks: $TRANSLATION_DIR/*.csv"
                log_info "  Backups: $TRANSLATION_DIR/*_backup.csv"
            fi
        fi
    fi
else
    log_info "Stage 8: Skipping gradebook translation (no gradebooks provided)"
    log_info "To use automatic translation, place gradebook CSV files in:"
    log_info "  $GRADEBOOKS_DIR/"
    log_info "Or run translation manually later:"
    log_info "  ./utils/translate_grades.sh --assignment-dir \"$ASSIGNMENT_DIR\" --gradebooks <files>"
fi

# Stop after stage 8 if requested
if [[ "$STOP_AFTER_STAGE" == "8" ]]; then
    log_info "Stopping after stage 8 as requested (--stop-after 8)"
    exit 0
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
log_info "  Marking criteria: $PROCESSED_DIR/marking_criteria.md"
log_info "  Final grades: $FINAL_DIR/grades.csv"
log_info "  Student feedback: $FINAL_DIR/*_feedback.md"
log_info "  Logs: $LOGS_DIR/"

# Add translation results if completed
if [[ -f "$TRANSLATION_MAPPING" && -f "$TRANSLATION_DIR/translation_report.txt" ]]; then
    log_info "  Translation mapping: $TRANSLATION_MAPPING"
    log_info "  Updated gradebooks: $TRANSLATION_DIR/*.csv"
    log_info "  Translation report: $TRANSLATION_DIR/translation_report.txt"
fi

echo ""
log_success "All marking artifacts saved to: $PROCESSED_DIR"
echo "========================================================================"
