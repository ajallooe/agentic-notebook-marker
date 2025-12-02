#!/usr/bin/env bash
#
# Unified LLM CLI Bridge
#
# A portable, future-proof bridge providing a consistent interface across
# Claude Code, Gemini CLI, and Codex CLI for both interactive and headless modes.
#
# This script is designed to be standalone and reusable across projects.
# No model names or provider defaults are baked in - all configuration
# comes from command-line arguments or an optional config file.
#
# Usage:
#   llm_caller.sh --model <model_name> --prompt "text" [OPTIONS]
#   llm_caller.sh --provider <claude|gemini|codex> --prompt "text" [OPTIONS]
#   llm_caller.sh --config <config.yaml> --prompt "text" [OPTIONS]
#
# Provider Resolution (in order of precedence):
#   1. --provider explicitly specified
#   2. --model specified → provider auto-resolved from configs/models.yaml
#   3. --config file with default_provider
#
# Model Resolution:
#   1. --model explicitly specified
#   2. Default model from configs/models.yaml for the resolved provider
#   3. No model passed to CLI (uses CLI's built-in default)
#
# Prompt (one required):
#   --prompt <text>         Prompt text
#   --prompt-file <file>    Read prompt from file
#
# Optional:
#   --model <name>          Model to use (passed directly to CLI, no validation)
#   --mode <mode>           interactive or headless (default: interactive)
#   --output <file>         Capture output to file
#   --working-dir <dir>     Set working directory for file operations
#   --auto-approve          Skip all permission prompts (use with caution)
#   --write-dirs <dirs>     Space-separated list of directories to allow writes
#   --help                  Show this help message
#
# Config File Format (YAML):
#   default_provider: claude
#   default_model: claude-sonnet-4
#   # or per-provider defaults:
#   providers:
#     claude:
#       model: claude-sonnet-4
#     gemini:
#       model: gemini-2.5-pro
#     codex:
#       model: gpt-4o
#

set -euo pipefail

# ============================================================================
# Defaults - No hardcoded model names or provider preferences
# ============================================================================
PROVIDER=""
MODEL=""
MODE="interactive"
PROMPT=""
PROMPT_FILE=""
OUTPUT_FILE=""
WORKING_DIR=""
AUTO_APPROVE=false
WRITE_DIRS=""
CONFIG_FILE=""
STATS_FILE=""
STATS_STAGE="unknown"
STATS_CONTEXT=""

# Script directory for finding models.yaml
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MODELS_CONFIG="$PROJECT_ROOT/configs/models.yaml"

# ============================================================================
# Help
# ============================================================================
show_help() {
    sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
    exit 0
}

# ============================================================================
# Resolve provider from model name using models.yaml (strict validation)
# ============================================================================
resolve_provider_from_model() {
    local model_name="$1"

    # Only allow models explicitly listed in models.yaml
    # This catches typos like 'gemini-pro-2.5' instead of 'gemini-2.5-pro'
    if [[ -f "$MODELS_CONFIG" ]]; then
        local provider
        provider=$(grep -E "^[[:space:]]*${model_name}:" "$MODELS_CONFIG" 2>/dev/null | \
                   sed 's/.*:[[:space:]]*//' | tr -d '"' | tr -d "'" || true)
        if [[ -n "$provider" ]]; then
            echo "$provider"
            return 0
        fi
    fi

    # No fallback - model must be in models.yaml
    return 1
}

# ============================================================================
# Get default model for a provider from models.yaml
# ============================================================================
get_default_model_for_provider() {
    local provider="$1"

    if [[ -f "$MODELS_CONFIG" ]]; then
        # Look in defaults section
        local in_defaults=false
        while IFS= read -r line; do
            if [[ "$line" =~ ^defaults: ]]; then
                in_defaults=true
            elif [[ "$in_defaults" == true && "$line" =~ ^[[:space:]]+${provider}: ]]; then
                local model
                model=$(echo "$line" | sed "s/.*${provider}:[[:space:]]*//" | tr -d '"' | tr -d "'")
                if [[ -n "$model" ]]; then
                    echo "$model"
                fi
                return 0
            elif [[ "$in_defaults" == true && "$line" =~ ^[a-z]+: ]]; then
                # New top-level section, stop looking
                break
            fi
        done < "$MODELS_CONFIG"
    fi
}

# ============================================================================
# Show available models from models.yaml
# ============================================================================
show_available_models() {
    echo "Available models (from configs/models.yaml):" >&2

    if [[ ! -f "$MODELS_CONFIG" ]]; then
        echo "  (models.yaml not found)" >&2
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
            # New top-level section, stop
            break
        elif [[ "$in_models" == true && "$line" =~ ^[[:space:]]+([^:]+):[[:space:]]*(.+) ]]; then
            local model_name="${BASH_REMATCH[1]}"
            local provider="${BASH_REMATCH[2]}"
            # Clean up whitespace and quotes
            model_name=$(echo "$model_name" | tr -d '"' | tr -d "'" | xargs)
            provider=$(echo "$provider" | tr -d '"' | tr -d "'" | xargs)

            case "$provider" in
                claude)
                    claude_models="${claude_models:+$claude_models, }$model_name"
                    ;;
                gemini)
                    gemini_models="${gemini_models:+$gemini_models, }$model_name"
                    ;;
                codex)
                    codex_models="${codex_models:+$codex_models, }$model_name"
                    ;;
            esac
        fi
    done < "$MODELS_CONFIG"

    echo "  claude: ${claude_models:-(none configured)}" >&2
    echo "  gemini: ${gemini_models:-(none configured)}" >&2
    echo "  codex:  ${codex_models:-(none configured)}" >&2
    echo "" >&2
    echo "To add a new model, update configs/models.yaml" >&2
}

# ============================================================================
# Config file parsing (simple YAML - supports basic key: value)
# ============================================================================
parse_config() {
    local config_file="$1"

    if [[ ! -f "$config_file" ]]; then
        echo "Error: Config file not found: $config_file" >&2
        exit 1
    fi

    # Extract default_provider if not already set
    if [[ -z "$PROVIDER" ]]; then
        PROVIDER=$(grep -E "^default_provider:" "$config_file" 2>/dev/null | sed 's/default_provider:[[:space:]]*//' | tr -d '"' | tr -d "'" || true)
    fi

    # Extract default_model if not already set
    if [[ -z "$MODEL" ]]; then
        MODEL=$(grep -E "^default_model:" "$config_file" 2>/dev/null | sed 's/default_model:[[:space:]]*//' | tr -d '"' | tr -d "'" || true)
    fi

    # If still no model but we have a provider, try provider-specific model
    if [[ -z "$MODEL" && -n "$PROVIDER" ]]; then
        # Look for providers.<provider>.model pattern (simplified parsing)
        local in_provider_section=false
        while IFS= read -r line; do
            if [[ "$line" =~ ^[[:space:]]*${PROVIDER}: ]]; then
                in_provider_section=true
            elif [[ "$in_provider_section" == true && "$line" =~ ^[[:space:]]+model: ]]; then
                MODEL=$(echo "$line" | sed 's/.*model:[[:space:]]*//' | tr -d '"' | tr -d "'")
                break
            elif [[ "$in_provider_section" == true && "$line" =~ ^[[:space:]]*[a-z]+: && ! "$line" =~ ^[[:space:]]+model: ]]; then
                # New section started, stop looking
                break
            fi
        done < "$config_file"
    fi
}

# ============================================================================
# Parse arguments
# ============================================================================
while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            ;;
        --provider)
            PROVIDER="$2"
            shift 2
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --mode)
            MODE="$2"
            shift 2
            ;;
        --prompt)
            PROMPT="$2"
            shift 2
            ;;
        --prompt-file)
            PROMPT_FILE="$2"
            shift 2
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --working-dir)
            WORKING_DIR="$2"
            shift 2
            ;;
        --auto-approve)
            AUTO_APPROVE=true
            shift
            ;;
        --write-dirs)
            WRITE_DIRS="$2"
            shift 2
            ;;
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --stats-file)
            STATS_FILE="$2"
            shift 2
            ;;
        --stats-stage)
            STATS_STAGE="$2"
            shift 2
            ;;
        --stats-context)
            STATS_CONTEXT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Use --help for usage information" >&2
            exit 1
            ;;
    esac
done

# ============================================================================
# Load config file if specified
# ============================================================================
if [[ -n "$CONFIG_FILE" ]]; then
    parse_config "$CONFIG_FILE"
fi

# ============================================================================
# Load prompt from file if specified
# ============================================================================
if [[ -n "$PROMPT_FILE" ]]; then
    if [[ ! -f "$PROMPT_FILE" ]]; then
        echo "Error: Prompt file not found: $PROMPT_FILE" >&2
        exit 1
    fi
    PROMPT="$(cat "$PROMPT_FILE")"
fi

# ============================================================================
# Validate required arguments
# ============================================================================
if [[ -z "$PROMPT" ]]; then
    echo "Error: --prompt or --prompt-file is required" >&2
    exit 1
fi

# ============================================================================
# Resolve provider from model if not explicitly set
# ============================================================================
if [[ -z "$PROVIDER" && -n "$MODEL" ]]; then
    PROVIDER=$(resolve_provider_from_model "$MODEL" || true)
    if [[ -z "$PROVIDER" ]]; then
        echo "Error: Unknown model '$MODEL'" >&2
        echo "" >&2
        show_available_models
        exit 1
    fi
fi

# If we have a provider but no model, try to get the default model
if [[ -n "$PROVIDER" && -z "$MODEL" ]]; then
    MODEL=$(get_default_model_for_provider "$PROVIDER")
    # MODEL can be empty - that's fine, CLI will use its default
fi

if [[ -z "$PROVIDER" ]]; then
    echo "Error: --provider or --model is required (or use --config with default_provider)" >&2
    exit 1
fi

# ============================================================================
# Change to working directory if specified
# ============================================================================
if [[ -n "$WORKING_DIR" ]]; then
    cd "$WORKING_DIR"
fi

# ============================================================================
# Claude Code
# ============================================================================
call_claude() {
    local cmd_args=()

    # Model (passed through without validation)
    if [[ -n "$MODEL" ]]; then
        cmd_args+=(--model "$MODEL")
    fi

    # Auto-approve permissions
    if [[ "$AUTO_APPROVE" == true ]]; then
        cmd_args+=(--dangerously-skip-permissions)
    else
        # Allow basic file operations
        cmd_args+=(--allowedTools "Read,Write,Edit,Bash")
    fi

    if [[ "$MODE" == "interactive" ]]; then
        # Interactive mode: prompt as positional argument
        if [[ -n "$OUTPUT_FILE" ]]; then
            # Use script command to preserve TTY while capturing output
            # -q for quiet mode, -F for flush after each write
            if [[ "$(uname)" == "Darwin" ]]; then
                # macOS script syntax
                script -q "$OUTPUT_FILE" claude "${cmd_args[@]}" "$PROMPT"
            else
                # Linux script syntax
                script -q -c "claude ${cmd_args[*]} \"$PROMPT\"" "$OUTPUT_FILE"
            fi
        else
            claude "${cmd_args[@]}" "$PROMPT"
        fi
    else
        # Headless mode: use -p/--print flag
        cmd_args+=(--print)
        if [[ "$AUTO_APPROVE" != true ]]; then
            cmd_args+=(--permission-mode bypassPermissions)
        fi

        if [[ -n "$STATS_FILE" ]]; then
            # Stats tracking: use JSON output and extract text/stats
            cmd_args+=(--output-format json)
            local extract_script="$SCRIPT_DIR/utils/extract_llm_stats.py"

            if [[ -n "$OUTPUT_FILE" ]]; then
                claude "${cmd_args[@]}" "$PROMPT" 2>/dev/null | \
                    python3 "$extract_script" --provider claude \
                        --stats-file "$STATS_FILE" \
                        --stats-stage "$STATS_STAGE" \
                        --stats-context "$STATS_CONTEXT" \
                        --model "$MODEL" > "$OUTPUT_FILE"
            else
                claude "${cmd_args[@]}" "$PROMPT" 2>/dev/null | \
                    python3 "$extract_script" --provider claude \
                        --stats-file "$STATS_FILE" \
                        --stats-stage "$STATS_STAGE" \
                        --stats-context "$STATS_CONTEXT" \
                        --model "$MODEL"
            fi
        else
            # No stats tracking: plain text output
            if [[ -n "$OUTPUT_FILE" ]]; then
                claude "${cmd_args[@]}" "$PROMPT" > "$OUTPUT_FILE" 2>&1
            else
                claude "${cmd_args[@]}" "$PROMPT"
            fi
        fi
    fi
}

# ============================================================================
# Gemini CLI
# ============================================================================
call_gemini() {
    local cmd_args=()

    # Model (passed through without validation)
    if [[ -n "$MODEL" ]]; then
        cmd_args+=(--model "$MODEL")
    fi

    # Auto-approve (YOLO mode)
    if [[ "$AUTO_APPROVE" == true ]]; then
        cmd_args+=(--yolo)
    fi

    # Include directories for file access
    if [[ -n "$WRITE_DIRS" ]]; then
        for dir in $WRITE_DIRS; do
            cmd_args+=(--include-directories "$dir")
        done
    fi

    if [[ "$MODE" == "interactive" ]]; then
        # Interactive mode: use -i flag
        if [[ -n "$OUTPUT_FILE" ]]; then
            # Use script command to preserve TTY while capturing output
            if [[ "$(uname)" == "Darwin" ]]; then
                script -q "$OUTPUT_FILE" gemini "${cmd_args[@]}" -i "$PROMPT"
            else
                script -q -c "gemini ${cmd_args[*]} -i \"$PROMPT\"" "$OUTPUT_FILE"
            fi
        else
            gemini "${cmd_args[@]}" -i "$PROMPT"
        fi
    else
        # Headless mode: use -p flag (or positional with --yolo)
        local prompt_args=()
        if [[ "$AUTO_APPROVE" == true ]]; then
            prompt_args=("$PROMPT")
        else
            prompt_args=(-p "$PROMPT")
        fi

        if [[ -n "$STATS_FILE" ]]; then
            # Stats tracking: use JSON output and extract text/stats
            cmd_args+=(--output-format json)
            local extract_script="$SCRIPT_DIR/utils/extract_llm_stats.py"

            if [[ -n "$OUTPUT_FILE" ]]; then
                gemini "${cmd_args[@]}" "${prompt_args[@]}" 2>/dev/null | \
                    python3 "$extract_script" --provider gemini \
                        --stats-file "$STATS_FILE" \
                        --stats-stage "$STATS_STAGE" \
                        --stats-context "$STATS_CONTEXT" \
                        --model "$MODEL" > "$OUTPUT_FILE"
            else
                gemini "${cmd_args[@]}" "${prompt_args[@]}" 2>/dev/null | \
                    python3 "$extract_script" --provider gemini \
                        --stats-file "$STATS_FILE" \
                        --stats-stage "$STATS_STAGE" \
                        --stats-context "$STATS_CONTEXT" \
                        --model "$MODEL"
            fi
        else
            # No stats tracking: plain text output
            if [[ -n "$OUTPUT_FILE" ]]; then
                gemini "${cmd_args[@]}" "${prompt_args[@]}" > "$OUTPUT_FILE" 2>&1
            else
                gemini "${cmd_args[@]}" "${prompt_args[@]}"
            fi
        fi
    fi
}

# ============================================================================
# Codex CLI (OpenAI)
# ============================================================================
call_codex() {
    local cmd_args=()

    # Model (passed through without validation)
    if [[ -n "$MODEL" ]]; then
        cmd_args+=(--model "$MODEL")
    fi

    # Additional directories
    if [[ -n "$WRITE_DIRS" ]]; then
        for dir in $WRITE_DIRS; do
            cmd_args+=(--add-dir "$dir")
        done
    fi

    if [[ "$MODE" == "interactive" ]]; then
        # Interactive mode: prompt as positional argument
        if [[ "$AUTO_APPROVE" == true ]]; then
            cmd_args+=(--dangerously-bypass-approvals-and-sandbox)
        else
            cmd_args+=(--sandbox workspace-write)
            cmd_args+=(--ask-for-approval on-request)
        fi

        if [[ -n "$OUTPUT_FILE" ]]; then
            # Use script command to preserve TTY while capturing output
            if [[ "$(uname)" == "Darwin" ]]; then
                script -q "$OUTPUT_FILE" codex "${cmd_args[@]}" "$PROMPT"
            else
                script -q -c "codex ${cmd_args[*]} \"$PROMPT\"" "$OUTPUT_FILE"
            fi
        else
            codex "${cmd_args[@]}" "$PROMPT"
        fi
    else
        # Headless mode: use 'exec' subcommand
        if [[ "$AUTO_APPROVE" == true ]]; then
            cmd_args+=(--dangerously-bypass-approvals-and-sandbox)
        else
            cmd_args+=(--sandbox workspace-write)
        fi

        if [[ -n "$STATS_FILE" ]]; then
            # Stats tracking: use JSON output and extract text/stats
            cmd_args+=(--json)
            local extract_script="$SCRIPT_DIR/utils/extract_llm_stats.py"

            if [[ -n "$OUTPUT_FILE" ]]; then
                codex exec "${cmd_args[@]}" "$PROMPT" 2>/dev/null | \
                    python3 "$extract_script" --provider codex \
                        --stats-file "$STATS_FILE" \
                        --stats-stage "$STATS_STAGE" \
                        --stats-context "$STATS_CONTEXT" \
                        --model "$MODEL" > "$OUTPUT_FILE"
            else
                codex exec "${cmd_args[@]}" "$PROMPT" 2>/dev/null | \
                    python3 "$extract_script" --provider codex \
                        --stats-file "$STATS_FILE" \
                        --stats-stage "$STATS_STAGE" \
                        --stats-context "$STATS_CONTEXT" \
                        --model "$MODEL"
            fi
        else
            # No stats tracking: plain text output
            if [[ -n "$OUTPUT_FILE" ]]; then
                # Codex has -o for output file
                codex exec "${cmd_args[@]}" -o "$OUTPUT_FILE" "$PROMPT"
            else
                codex exec "${cmd_args[@]}" "$PROMPT"
            fi
        fi
    fi
}

# ============================================================================
# Route to provider
# ============================================================================
case "$PROVIDER" in
    claude)
        if ! command -v claude &> /dev/null; then
            echo "Error: claude CLI not found. Install from: https://claude.ai/code" >&2
            exit 1
        fi
        call_claude
        ;;
    gemini)
        if ! command -v gemini &> /dev/null; then
            echo "Error: gemini CLI not found. Install from: https://github.com/google-gemini/gemini-cli" >&2
            exit 1
        fi
        call_gemini
        ;;
    codex|openai)
        if ! command -v codex &> /dev/null; then
            echo "Error: codex CLI not found. Install from: https://github.com/openai/codex" >&2
            exit 1
        fi
        call_codex
        ;;
    *)
        echo "Error: Unknown provider '$PROVIDER'" >&2
        echo "Supported providers: claude, gemini, codex" >&2
        exit 1
        ;;
esac

exit 0
