#!/usr/bin/env bash
#
# Batch Marking Script - Mark Multiple Assignments in Staged Rounds
#
# This script processes multiple assignments in batched rounds, running each
# stage for ALL assignments before moving to the next stage. This minimizes
# instructor waiting time by grouping interactive stages together.
#
# Usage:
#   batch_mark.sh ASSIGNMENTS_FILE --provider PROVIDER --model MODEL [OPTIONS]
#
# The script automatically runs 5 rounds:
#   Round 1: Stages 1-2 (Preparation) for ALL assignments
#   Round 2: Stage 3 (Pattern Design - INTERACTIVE) for ALL assignments
#   Round 3: Stages 4-5 (Marking + Normalization) for ALL assignments
#   Round 4: Stage 6 (Dashboard - INTERACTIVE) for ALL assignments
#   Round 5: Stages 7-9 (Completion) for ALL assignments
#

set -euo pipefail

# Determine script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$(basename "$SCRIPT_DIR")" == "utils" ]]; then
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
else
    PROJECT_ROOT="$SCRIPT_DIR"
fi

# Load batch_delay from config file (default: 2 seconds)
CONFIG_FILE="$PROJECT_ROOT/configs/config.yaml"
BATCH_DELAY=2
if [[ -f "$CONFIG_FILE" ]]; then
    BATCH_DELAY=$(grep -E "^batch_delay:" "$CONFIG_FILE" 2>/dev/null | sed 's/batch_delay:[[:space:]]*//' | tr -d ' ' || echo "2")
    if [[ -z "$BATCH_DELAY" || ! "$BATCH_DELAY" =~ ^[0-9]+$ ]]; then
        BATCH_DELAY=2
    fi
fi

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
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

log_round() {
    echo -e "${CYAN}${BOLD}$1${NC}"
}

# Models config for provider resolution
MODELS_CONFIG="$PROJECT_ROOT/configs/models.yaml"

# Resolve provider from model name (strict - must be in models.yaml)
resolve_provider_from_model() {
    local model_name="$1"

    # Only allow models explicitly listed in models.yaml
    if [[ -f "$MODELS_CONFIG" ]]; then
        local provider
        provider=$(grep -E "^[[:space:]]*${model_name}:" "$MODELS_CONFIG" 2>/dev/null | \
                   sed 's/.*:[[:space:]]*//' | tr -d '"' | tr -d "'" || true)
        if [[ -n "$provider" ]]; then
            echo "$provider"
            return 0
        fi
    fi

    # No fallback - model must be in models.yaml to catch typos
    return 1
}

# Show available models from models.yaml
show_available_models() {
    echo "Available models (from configs/models.yaml):"

    if [[ ! -f "$MODELS_CONFIG" ]]; then
        echo "  (models.yaml not found)"
        return
    fi

    local in_models=false
    local claude_models=""
    local gemini_models=""
    local codex_models=""

    while IFS= read -r line; do
        if [[ "$line" =~ ^models: ]]; then
            in_models=true
        elif [[ "$in_models" == true && "$line" =~ ^[a-z]+: && ! "$line" =~ ^[[:space:]] ]]; then
            break
        elif [[ "$in_models" == true && "$line" =~ ^[[:space:]]+([^:]+):[[:space:]]*(.+) ]]; then
            local model_name="${BASH_REMATCH[1]}"
            local provider="${BASH_REMATCH[2]}"
            model_name=$(echo "$model_name" | tr -d '"' | tr -d "'" | xargs)
            provider=$(echo "$provider" | tr -d '"' | tr -d "'" | xargs)

            case "$provider" in
                claude) claude_models="${claude_models:+$claude_models, }$model_name" ;;
                gemini) gemini_models="${gemini_models:+$gemini_models, }$model_name" ;;
                codex) codex_models="${codex_models:+$codex_models, }$model_name" ;;
            esac
        fi
    done < "$MODELS_CONFIG"

    echo "  claude: ${claude_models:-(none configured)}"
    echo "  gemini: ${gemini_models:-(none configured)}"
    echo "  codex:  ${codex_models:-(none configured)}"
    echo ""
    echo "To add a new model, update configs/models.yaml"
}

# Usage message
usage() {
    cat << EOF
Usage: $(basename "$0") ASSIGNMENTS_FILE [--model MODEL | --provider PROVIDER] [OPTIONS]

Batch process multiple assignments in staged rounds to optimize instructor workflow.
The script automatically runs all stages in the correct order, pausing for review
after interactive stages.

Arguments:
  ASSIGNMENTS_FILE    Text file with assignment paths (one per line)

Model/Provider (at least one required):
  --model NAME        Model name (e.g., claude-sonnet-4, gemini-2.5-pro, gpt-4o)
                      Provider is auto-resolved from model name
  --provider NAME     LLM provider (claude, gemini, or codex)
                      Only needed if model is not specified or unrecognized
  --api-model NAME    Use direct API calls for headless stages (requires API key)

Options:
  --parallel N        Override max parallel tasks for all assignments
  --no-resume         Start fresh, ignore previous progress (default: resume)
  --start-round N     Start from round N (1-5, default: 1)
  --auto-approve      Skip interactive stages (pattern design, dashboard approval)
  --force-complete    Generate zero-mark feedback for failed students and continue
  --help              Show this help message

Automatic Workflow (5 rounds - runs continuously):

  Round 1: Preparation (stages 1-2 for ALL assignments)
    → Finds submissions and extracts activity structure

  Round 2: Pattern Design (stage 3 - INTERACTIVE for ALL)
    → Instructor interacts with pattern designer for each assignment

  Round 3: Marking + Normalization (stages 4-5 for ALL)
    → Runs parallel markers and normalizers

  Round 4: Dashboard Review (stage 6 - INTERACTIVE for ALL)
    → Creates adjustment dashboards (instructor approves in Jupyter)

  Round 5: Completion (stages 7-9 for ALL assignments)
    → Generates final feedback, grades, and gradebook translation

Stage Reference (mark_structured.sh):
  1 = Submission discovery      5 = Normalization
  2 = Activity extraction       6 = Dashboard creation
  3 = Pattern design            7 = Unification
  4 = Marker agents             8 = Aggregation
                                9 = Gradebook translation

Assignment File Format:
  assignments/lab1
  assignments/lab2
  # This is a comment
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

PARALLEL_OVERRIDE=""
NO_RESUME=false
PROVIDER=""
MODEL=""
API_MODEL=""
START_ROUND=1
AUTO_APPROVE=false
FORCE_COMPLETE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --parallel)
            PARALLEL_OVERRIDE="$2"
            shift 2
            ;;
        --provider)
            PROVIDER="$2"
            shift 2
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --api-model)
            API_MODEL="$2"
            shift 2
            ;;
        --no-resume)
            NO_RESUME=true
            shift
            ;;
        --start-round)
            START_ROUND="$2"
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
        --help)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Resolve provider from model if not explicitly set
if [[ -z "$PROVIDER" && -n "$MODEL" ]]; then
    PROVIDER=$(resolve_provider_from_model "$MODEL" || true)
    if [[ -z "$PROVIDER" ]]; then
        log_error "Unknown model '$MODEL'"
        echo ""
        show_available_models
        exit 1
    fi
fi

# Validate we have at least provider, model, or api-model
# (if none specified, will fall back to per-assignment overview.md or project defaults)
if [[ -z "$PROVIDER" && -z "$MODEL" && -z "$API_MODEL" ]]; then
    log_error "--model, --provider, or --api-model is required"
    usage
fi

# If we have --api-model but no --provider/--model, that's fine for headless workflows
# The per-assignment overview.md will provide defaults for any CLI fallback
if [[ -z "$PROVIDER" && -z "$API_MODEL" ]]; then
    log_error "Could not determine provider"
    usage
fi

# Validate provider if specified
if [[ -n "$PROVIDER" ]]; then
    case "$PROVIDER" in
        claude|gemini|codex) ;;
        *)
            log_error "Invalid provider: $PROVIDER (must be claude, gemini, or codex)"
            exit 1
            ;;
    esac
fi

# Validate start round
if [[ "$START_ROUND" -lt 1 || "$START_ROUND" -gt 5 ]]; then
    log_error "Invalid start round: $START_ROUND (must be 1-5)"
    exit 1
fi

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

echo "=================================================================="
echo "              BATCH MARKING - STAGED WORKFLOW"
echo "=================================================================="
echo
log_info "Found ${#ASSIGNMENTS[@]} assignment(s) to process"
if [[ -n "$PROVIDER" ]]; then
    log_info "Provider: $PROVIDER"
fi
if [[ -n "$MODEL" ]]; then
    log_info "Model: $MODEL"
elif [[ -n "$PROVIDER" ]]; then
    log_info "Model: (provider default)"
fi
if [[ -n "$API_MODEL" ]]; then
    log_info "API Model: $API_MODEL (headless stages will use direct API calls)"
fi
if [[ -z "$PROVIDER" && -z "$MODEL" && -n "$API_MODEL" ]]; then
    log_info "CLI fallback: per-assignment overview.md defaults"
fi
if [[ "$START_ROUND" -gt 1 ]]; then
    log_info "Starting from round: $START_ROUND"
fi
if [[ "$AUTO_APPROVE" == true ]]; then
    log_info "Auto-approve mode: ENABLED (skipping interactive stages)"
fi
if [[ "$FORCE_COMPLETE" == true ]]; then
    log_info "Force-complete mode: ENABLED (zero marks for failed students)"
fi
echo

# ============================================================================
# CHECK FOR MISSING OVERVIEW FILES
# ============================================================================

echo "=================================================================="
log_info "Checking for missing overview.md files..."
echo "=================================================================="
echo

MISSING_OVERVIEWS=()

for assignment in "${ASSIGNMENTS[@]}"; do
    if [[ "$assignment" = /* ]]; then
        ASSIGNMENT_DIR="$assignment"
    else
        ASSIGNMENT_DIR="$PROJECT_ROOT/$assignment"
    fi

    OVERVIEW_FILE="$ASSIGNMENT_DIR/overview.md"
    if [[ ! -f "$OVERVIEW_FILE" ]]; then
        MISSING_OVERVIEWS+=("$assignment")
    fi
done

if [[ ${#MISSING_OVERVIEWS[@]} -gt 0 ]]; then
    log_warning "Found ${#MISSING_OVERVIEWS[@]} assignment(s) missing overview.md:"
    for assignment in "${MISSING_OVERVIEWS[@]}"; do
        echo "  - $assignment"
    done
    echo

    read -p "Generate overview.md for these assignments? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo
        for assignment in "${MISSING_OVERVIEWS[@]}"; do
            if [[ "$assignment" = /* ]]; then
                ASSIGNMENT_DIR="$assignment"
            else
                ASSIGNMENT_DIR="$PROJECT_ROOT/$assignment"
            fi

            log_info "Generating overview for: $assignment"

            # Find the base notebook (first .ipynb file in assignment dir)
            BASE_NOTEBOOK=$(find "$ASSIGNMENT_DIR" -maxdepth 1 -name "*.ipynb" -type f | head -1)

            if [[ -z "$BASE_NOTEBOOK" ]]; then
                log_warning "No .ipynb file found in $ASSIGNMENT_DIR, skipping..."
                continue
            fi

            log_info "Using notebook: $(basename "$BASE_NOTEBOOK")"

            # Run create_overview.sh
            if "$SCRIPT_DIR/create_overview.sh" "$BASE_NOTEBOOK" --provider "$PROVIDER" --model "$MODEL"; then
                log_success "Generated overview.md for $assignment"
            else
                log_error "Failed to generate overview.md for $assignment"
            fi
            echo
        done
    else
        log_info "Skipping overview generation"
        log_warning "Assignments without overview.md will fail during marking"
    fi
    echo
else
    log_success "All assignments have overview.md files"
    echo
fi

# ============================================================================
# HELPER FUNCTION: Run a stage for all assignments
# ============================================================================

run_stage_for_all() {
    local stop_after="$1"
    local stage_desc="$2"

    local total=${#ASSIGNMENTS[@]}
    local success_count=0
    local failed=()

    for i in "${!ASSIGNMENTS[@]}"; do
        local assignment="${ASSIGNMENTS[$i]}"
        local assignment_num=$((i + 1))

        echo "------------------------------------------------------------------"
        log_info "[$assignment_num/$total] Processing: $assignment"
        echo "------------------------------------------------------------------"

        # Resolve assignment path
        local assignment_dir
        if [[ "$assignment" = /* ]]; then
            assignment_dir="$assignment"
        else
            assignment_dir="$PROJECT_ROOT/$assignment"
        fi

        if [[ ! -d "$assignment_dir" ]]; then
            log_error "Assignment directory not found: $assignment_dir"
            failed+=("$assignment (directory not found)")
            continue
        fi

        local overview_file="$assignment_dir/overview.md"
        if [[ ! -f "$overview_file" ]]; then
            log_error "No overview.md found in $assignment_dir"
            failed+=("$assignment (missing overview.md)")
            continue
        fi

        # Check assignment_type in overview.md
        local assignment_type="structured"
        if grep -q "assignment_type:\s*freeform" "$overview_file" 2>/dev/null; then
            assignment_type="freeform"
        fi

        # Determine which script to run
        local mark_script
        if [[ "$assignment_type" == "freeform" ]]; then
            mark_script="$PROJECT_ROOT/mark_freeform.sh"
        else
            mark_script="$PROJECT_ROOT/mark_structured.sh"
        fi

        if [[ ! -x "$mark_script" ]]; then
            log_error "Marking script not found or not executable: $mark_script"
            failed+=("$assignment (missing script)")
            continue
        fi

        # Build command
        local cmd=("$mark_script" "$assignment_dir")
        if [[ -n "$PROVIDER" ]]; then
            cmd+=("--provider" "$PROVIDER")
        fi
        if [[ -n "$MODEL" ]]; then
            cmd+=("--model" "$MODEL")
        fi
        cmd+=("--stop-after" "$stop_after")

        if [[ -n "$PARALLEL_OVERRIDE" ]]; then
            cmd+=("--parallel" "$PARALLEL_OVERRIDE")
        fi

        if [[ -n "$API_MODEL" ]]; then
            cmd+=("--api-model" "$API_MODEL")
        fi

        if [[ "$NO_RESUME" == true ]]; then
            cmd+=("--no-resume")
        fi

        if [[ "$AUTO_APPROVE" == true ]]; then
            cmd+=("--auto-approve")
        fi

        if [[ "$FORCE_COMPLETE" == true ]]; then
            cmd+=("--force-complete")
        fi

        # Execute marking script
        if "${cmd[@]}"; then
            log_success "Completed: $assignment"
            success_count=$((success_count + 1))
        else
            log_error "Failed: $assignment"
            failed+=("$assignment (marking failed)")
        fi

        echo

        # Delay between assignments to avoid API session/rate issues
        sleep "$BATCH_DELAY"
    done

    # Report results
    echo
    log_info "Stage $stage_desc complete: $success_count/$total successful"

    if [[ ${#failed[@]} -gt 0 ]]; then
        log_warning "Failed assignments:"
        for f in "${failed[@]}"; do
            echo "  - $f"
        done
    fi

    return ${#failed[@]}
}

# ============================================================================
# ROUND 1: Preparation (Stages 1-2)
# ============================================================================

if [[ "$START_ROUND" -le 1 ]]; then
    echo
    echo "=================================================================="
    log_round "ROUND 1: PREPARATION (Stages 1-2 for ALL assignments)"
    echo "=================================================================="
    echo
    log_info "Running submission discovery and activity extraction..."
    echo

    run_stage_for_all 2 "1-2 (Preparation)" || true

    echo
    echo "=================================================================="
    log_success "ROUND 1 COMPLETE - Proceeding to Round 2"
    echo "=================================================================="
    echo
fi

# ============================================================================
# ROUND 2: Pattern Design (Stage 3 - INTERACTIVE)
# ============================================================================

if [[ "$START_ROUND" -le 2 ]]; then
    echo
    echo "=================================================================="
    log_round "ROUND 2: PATTERN DESIGN (Stage 3 - INTERACTIVE for ALL)"
    echo "=================================================================="
    echo
    log_warning "This round requires instructor interaction for each assignment."
    log_info "The pattern designer will run for each assignment in sequence."
    echo

    run_stage_for_all 3 "3 (Pattern Design)" || true

    echo
    echo "=================================================================="
    log_success "ROUND 2 COMPLETE - Proceeding to Round 3"
    echo "=================================================================="
    echo
fi

# ============================================================================
# ROUND 3: Marking + Normalization (Stages 4-5)
# ============================================================================

if [[ "$START_ROUND" -le 3 ]]; then
    echo
    echo "=================================================================="
    log_round "ROUND 3: MARKING + NORMALIZATION (Stages 4-5 for ALL)"
    echo "=================================================================="
    echo
    log_info "Running parallel marker agents and normalizers..."
    log_info "This may take a while depending on the number of submissions."
    echo

    run_stage_for_all 5 "4-5 (Marking + Normalization)" || true

    echo
    echo "=================================================================="
    log_success "ROUND 3 COMPLETE - Proceeding to Round 4"
    echo "=================================================================="
    echo
fi

# ============================================================================
# ROUND 4: Dashboard Review (Stage 6 - INTERACTIVE)
# ============================================================================

if [[ "$START_ROUND" -le 4 ]]; then
    echo
    echo "=================================================================="
    log_round "ROUND 4: DASHBOARD REVIEW (Stage 6 - INTERACTIVE for ALL)"
    echo "=================================================================="
    echo
    log_info "Creating adjustment dashboards..."
    echo

    run_stage_for_all 6 "6 (Dashboard Creation)" || true

    echo
    echo "=================================================================="
    log_success "ROUND 4 COMPLETE - Proceeding to Round 5"
    echo "=================================================================="
    echo
fi

# ============================================================================
# ROUND 5: Completion (Stages 7-9)
# ============================================================================

if [[ "$START_ROUND" -le 5 ]]; then
    echo
    echo "=================================================================="
    log_round "ROUND 5: COMPLETION (Stages 7-9 for ALL assignments)"
    echo "=================================================================="
    echo
    log_info "Running unification, aggregation, and gradebook translation..."
    echo

    # Run to completion (no --stop-after)
    total=${#ASSIGNMENTS[@]}
    success_count=0
    failed=()

    for i in "${!ASSIGNMENTS[@]}"; do
        assignment="${ASSIGNMENTS[$i]}"
        assignment_num=$((i + 1))

        echo "------------------------------------------------------------------"
        log_info "[$assignment_num/$total] Processing: $assignment"
        echo "------------------------------------------------------------------"

        # Resolve assignment path
        if [[ "$assignment" = /* ]]; then
            assignment_dir="$assignment"
        else
            assignment_dir="$PROJECT_ROOT/$assignment"
        fi

        if [[ ! -d "$assignment_dir" ]]; then
            log_error "Assignment directory not found: $assignment_dir"
            failed+=("$assignment (directory not found)")
            continue
        fi

        overview_file="$assignment_dir/overview.md"
        if [[ ! -f "$overview_file" ]]; then
            log_error "No overview.md found in $assignment_dir"
            failed+=("$assignment (missing overview.md)")
            continue
        fi

        # Check assignment_type
        assignment_type="structured"
        if grep -q "assignment_type:\s*freeform" "$overview_file" 2>/dev/null; then
            assignment_type="freeform"
        fi

        # Determine script
        if [[ "$assignment_type" == "freeform" ]]; then
            mark_script="$PROJECT_ROOT/mark_freeform.sh"
        else
            mark_script="$PROJECT_ROOT/mark_structured.sh"
        fi

        if [[ ! -x "$mark_script" ]]; then
            log_error "Marking script not found: $mark_script"
            failed+=("$assignment (missing script)")
            continue
        fi

        # Build command (NO --stop-after for completion)
        cmd=("$mark_script" "$assignment_dir")
        if [[ -n "$PROVIDER" ]]; then
            cmd+=("--provider" "$PROVIDER")
        fi
        if [[ -n "$MODEL" ]]; then
            cmd+=("--model" "$MODEL")
        fi

        if [[ -n "$PARALLEL_OVERRIDE" ]]; then
            cmd+=("--parallel" "$PARALLEL_OVERRIDE")
        fi

        if [[ -n "$API_MODEL" ]]; then
            cmd+=("--api-model" "$API_MODEL")
        fi

        if [[ "$AUTO_APPROVE" == true ]]; then
            cmd+=("--auto-approve")
        fi

        if [[ "$FORCE_COMPLETE" == true ]]; then
            cmd+=("--force-complete")
        fi

        # Always resume in round 5
        # (don't pass --no-resume even if it was set initially)

        if "${cmd[@]}"; then
            log_success "Completed: $assignment"
            success_count=$((success_count + 1))
        else
            log_error "Failed: $assignment"
            failed+=("$assignment (completion failed)")
        fi

        echo
    done
fi

# ============================================================================
# FINAL SUMMARY
# ============================================================================

echo
echo "=================================================================="
echo "              BATCH MARKING COMPLETE"
echo "=================================================================="
echo
log_info "All ${#ASSIGNMENTS[@]} assignments have been processed."
echo
echo "Final outputs for each assignment:"
echo
for assignment in "${ASSIGNMENTS[@]}"; do
    if [[ "$assignment" = /* ]]; then
        ASSIGNMENT_DIR="$assignment"
    else
        ASSIGNMENT_DIR="$PROJECT_ROOT/$assignment"
    fi
    echo "  📁 $assignment"
    echo "     • Grades: $ASSIGNMENT_DIR/processed/final/grades.csv"
    echo "     • Feedback: $ASSIGNMENT_DIR/processed/final/*_feedback.md"
    if [[ -d "$ASSIGNMENT_DIR/processed/translation" ]]; then
        echo "     • Gradebooks: $ASSIGNMENT_DIR/processed/translation/"
    fi
    echo
done

log_success "Batch marking workflow complete!"
echo

exit 0
