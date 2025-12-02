#!/usr/bin/env bash
#
# Gradebook Translator - Transfer grades to section gradebooks
# Uses LLM for intelligent name matching, then applies updates deterministically
#

set -euo pipefail

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$PROJECT_ROOT/src"

# Activate virtual environment if it exists
if [[ -f "$PROJECT_ROOT/.venv/bin/activate" ]]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
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
DRY_RUN=false
APPLY=true  # Default to apply
SKIP_MAPPING=false

GRADEBOOK_PATHS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --assignment-dir)
            ASSIGNMENT_DIR="$2"
            shift 2
            ;;
        --gradebooks)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
                GRADEBOOK_PATHS+=("$1")
                shift
            done
            ;;
        --dry-run)
            DRY_RUN=true
            APPLY=false
            shift
            ;;
        --skip-mapping)
            SKIP_MAPPING=true
            shift
            ;;
        --provider)
            PROVIDER="$2"
            shift 2
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Usage: $0 --assignment-dir <dir> --gradebooks <csv1> <csv2> ... [OPTIONS]" >&2
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "${ASSIGNMENT_DIR:-}" ]]; then
    cat << EOF
Usage: $0 --assignment-dir <dir> --gradebooks <csv1> <csv2> ... [OPTIONS]

Required:
  --assignment-dir <dir>         Assignment directory with processed/final/grades.csv
  --gradebooks <csv1> <csv2> ... One or more gradebook CSV files to update

Options:
  --dry-run                      Preview changes without updating files (optional)
  --skip-mapping                 Skip mapping creation, use existing mapping file
  --provider <provider>          LLM provider (claude, gemini, codex)
  --model <model>                Specific model to use

Example:
  $0 --assignment-dir "assignments/Lab 02" \\
     --gradebooks section1.csv section2.csv
EOF
    exit 1
fi

if [[ ${#GRADEBOOK_PATHS[@]} -eq 0 ]]; then
    log_error "At least one gradebook CSV must be specified with --gradebooks"
    exit 1
fi

# Validate assignment directory
if [[ ! -d "$ASSIGNMENT_DIR" ]]; then
    log_error "Assignment directory not found: $ASSIGNMENT_DIR"
    exit 1
fi

ASSIGNMENT_DIR="$(cd "$ASSIGNMENT_DIR" && pwd)"
ASSIGNMENT_NAME="$(basename "$ASSIGNMENT_DIR")"

# Validate grades.csv exists
GRADES_CSV="$ASSIGNMENT_DIR/processed/final/grades.csv"
if [[ ! -f "$GRADES_CSV" ]]; then
    log_error "Grades CSV not found: $GRADES_CSV"
    log_error "Run marking workflow first to generate grades.csv"
    exit 1
fi

# Validate gradebook files
for gradebook in "${GRADEBOOK_PATHS[@]}"; do
    if [[ ! -f "$gradebook" ]]; then
        log_error "Gradebook CSV not found: $gradebook"
        exit 1
    fi
done

# Load configuration from overview.md
OVERVIEW_FILE="$ASSIGNMENT_DIR/overview.md"
if [[ ! -f "$OVERVIEW_FILE" ]]; then
    log_error "overview.md not found in assignment directory"
    exit 1
fi

eval "$("$SRC_DIR/utils/config_parser.py" "$OVERVIEW_FILE" --bash)"

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

# Set provider and model defaults
PROVIDER="${PROVIDER:-$DEFAULT_PROVIDER}"
MODEL="${MODEL:-${DEFAULT_MODEL:-}}"

# Resolve provider from model if not set
if [[ -z "$PROVIDER" && -n "$MODEL" ]]; then
    PROVIDER=$(resolve_provider_from_model "$MODEL" || true)
    if [[ -z "$PROVIDER" ]]; then
        log_error "Unknown model '$MODEL'"
        echo ""
        show_available_models
        exit 1
    fi
fi

if [[ -z "$PROVIDER" && -z "$MODEL" ]]; then
    log_error "--model or --provider is required (or set default_provider in overview.md)"
    exit 1
fi

log_info "Starting gradebook translation: $ASSIGNMENT_NAME"
log_info "Assignment directory: $ASSIGNMENT_DIR"
log_info "Grades CSV: $GRADES_CSV"
log_info "Gradebook CSVs: ${#GRADEBOOK_PATHS[@]} files"
log_info "Provider: $PROVIDER"
[[ -n "$MODEL" ]] && log_info "Model: $MODEL"

# Create translation output directory
TRANSLATION_DIR="$ASSIGNMENT_DIR/processed/translation"
mkdir -p "$TRANSLATION_DIR"

MAPPING_FILE="$TRANSLATION_DIR/translation_mapping.json"

# ============================================================================
# STAGE 1: Create Mapping (LLM Agent)
# ============================================================================

if [[ $SKIP_MAPPING == true && -f "$MAPPING_FILE" ]]; then
    log_info "Stage 1: Skipping mapping creation (using existing mapping)"
    log_success "Mapping loaded: $MAPPING_FILE"
else
    # Fresh run - clean up translation directory
    if [[ -d "$TRANSLATION_DIR" ]]; then
        log_info "Cleaning translation directory for fresh run..."
        rm -f "$TRANSLATION_DIR"/*.json "$TRANSLATION_DIR"/*.csv "$TRANSLATION_DIR"/*.txt "$TRANSLATION_DIR"/*.log 2>/dev/null || true
    fi
    log_info "Stage 1: Creating translation mapping (LLM Agent)..."
    log_warning "This stage requires LLM interaction for fuzzy name matching"

    GRADEBOOK_ARGS=()
    for gradebook in "${GRADEBOOK_PATHS[@]}"; do
        GRADEBOOK_ARGS+=(--gradebooks "$(cd "$(dirname "$gradebook")" && pwd)/$(basename "$gradebook")")
    done

    python3 "$SRC_DIR/agents/translator.py" \
        --assignment-name "$ASSIGNMENT_NAME" \
        --total-marks "$TOTAL_MARKS" \
        --assignment-type "${ASSIGNMENT_TYPE:-structured}" \
        --grades-csv "$GRADES_CSV" \
        "${GRADEBOOK_ARGS[@]}" \
        --output-path "$TRANSLATION_DIR" \
        ${PROVIDER:+--provider "$PROVIDER"} \
        ${MODEL:+--model "$MODEL"}

    if [[ $? -ne 0 ]]; then
        log_error "Translation mapping failed"
        exit 1
    fi

    if [[ ! -f "$MAPPING_FILE" ]]; then
        log_error "Mapping file was not created"
        exit 1
    fi

    log_success "Mapping created: $MAPPING_FILE"
fi

# ============================================================================
# STAGE 2: Review Mapping
# ============================================================================

log_info "Stage 2: Review mapping..."
log_warning "Please review the mapping file before applying:"
log_info "  File: $MAPPING_FILE"
echo ""

# Show summary
if command -v jq &> /dev/null; then
    echo "Mapping Summary:"
    jq -r '.summary | to_entries | .[] | "  \(.key): \(.value)"' "$MAPPING_FILE"
    echo ""
fi

read -p "Press Enter to continue with $([ "$DRY_RUN" = true ] && echo "DRY RUN" || echo "APPLY") mode, or Ctrl+C to cancel..."

# ============================================================================
# STAGE 3: Apply Translation (Deterministic)
# ============================================================================

log_info "Stage 3: Applying translation..."

APPLY_ARGS=(
    --mapping "$MAPPING_FILE"
    --output-dir "$TRANSLATION_DIR"
)

if [[ $DRY_RUN == true ]]; then
    APPLY_ARGS+=(--dry-run)
elif [[ $APPLY == true ]]; then
    APPLY_ARGS+=(--apply)
fi

python3 "$SRC_DIR/apply_translation.py" "${APPLY_ARGS[@]}"

if [[ $? -ne 0 ]]; then
    log_error "Translation application failed"
    exit 1
fi

log_success "Translation complete"

# ============================================================================
# FINAL SUMMARY
# ============================================================================

echo ""
echo "========================================================================"
log_success "GRADEBOOK TRANSLATION COMPLETE"
echo "========================================================================"
echo ""
log_info "Results:"
log_info "  Mapping file: $MAPPING_FILE"
log_info "  Translation report: $TRANSLATION_DIR/translation_report.txt"

if [[ $DRY_RUN == true ]]; then
    log_warning "DRY RUN completed - no files were modified"
    log_info "To apply changes, run without --dry-run:"
    log_info "  ./utils/translate_grades.sh --assignment-dir \"$ASSIGNMENT_DIR\" \\"
    log_info "    --gradebooks ${GRADEBOOK_PATHS[@]} \\"
    log_info "    --skip-mapping"
else
    log_info "  Filled gradebooks created in original gradebook directories:"
    for gradebook in "${GRADEBOOK_PATHS[@]}"; do
        gradebook_name="$(basename "$gradebook" .csv)"
        gradebook_dir="$(dirname "$gradebook")"
        log_info "    - $gradebook_dir/${gradebook_name}_filled.csv"
    done
    log_info "  Copies also saved to: $TRANSLATION_DIR/"
fi

echo ""
log_success "All translation artifacts saved to: $TRANSLATION_DIR"
echo "========================================================================"
