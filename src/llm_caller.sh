#!/usr/bin/env bash
#
# Unified LLM Caller - Routes to appropriate CLI tool
# Usage: llm_caller.sh --prompt "text" [--mode interactive|headless] [--provider claude|gemini|openai] [--model model_name] [--output file]
#

set -euo pipefail

# Default values
MODE="interactive"
PROVIDER=""
MODEL=""
PROMPT=""
OUTPUT_FILE=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --prompt)
            PROMPT="$2"
            shift 2
            ;;
        --mode)
            MODE="$2"
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
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Validate prompt is provided
if [[ -z "$PROMPT" ]]; then
    echo "Error: --prompt is required" >&2
    exit 1
fi

# Infer provider from model if not specified
if [[ -z "$PROVIDER" && -n "$MODEL" ]]; then
    if [[ "$MODEL" == claude-* ]]; then
        PROVIDER="claude"
    elif [[ "$MODEL" == gemini-* ]]; then
        PROVIDER="gemini"
    elif [[ "$MODEL" == gpt-* || "$MODEL" == o1* ]]; then
        PROVIDER="codex"
    fi
fi

# Default from config.yaml if still not specified
if [[ -z "$PROVIDER" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    DEFAULT_PROVIDER=$(python3 "$SCRIPT_DIR/utils/get_default_provider.py" 2>/dev/null)
    if [[ -n "$DEFAULT_PROVIDER" ]]; then
        PROVIDER="$DEFAULT_PROVIDER"
    else
        # Final fallback
        PROVIDER="claude"
    fi
fi

# Function to call Claude Code CLI
call_claude() {
    local prompt="$1"
    local mode="$2"
    local output="$3"
    local model="${MODEL}"

    # Build model argument if specified
    local model_arg=""
    if [[ -n "$model" ]]; then
        model_arg="--model $model"
    fi

    if [[ "$mode" == "interactive" ]]; then
        # Interactive mode - pass prompt as argument to keep stdin open for user interaction
        # Use script command to capture output while maintaining TTY for true interactivity
        if [[ -n "$output" ]]; then
            if command -v script &> /dev/null; then
                # Use script for proper TTY handling and output capture
                # macOS and Linux have different script syntax
                if [[ "$(uname)" == "Darwin" ]]; then
                    script -q "$output" claude $model_arg "$prompt"
                else
                    script -q -c "claude $model_arg \"$prompt\"" "$output"
                fi
            else
                # Fallback: run without capture if script not available
                echo "Warning: 'script' command not found, session won't be captured" >&2
                claude $model_arg "$prompt"
            fi
        else
            # No output capture needed, just run interactively
            claude $model_arg "$prompt"
        fi
    else
        # Headless mode - use --print for non-interactive output
        # Bypass permissions for automated execution
        if [[ -n "$output" ]]; then
            claude --print --permission-mode bypassPermissions $model_arg "$prompt" > "$output" 2>&1
        else
            claude --print --permission-mode bypassPermissions $model_arg "$prompt"
        fi
    fi
}

# Function to call Gemini CLI
call_gemini() {
    local prompt="$1"
    local mode="$2"
    local output="$3"
    local model="${MODEL}"

    # Check if gemini CLI is available
    if ! command -v gemini &> /dev/null; then
        echo "Error: gemini CLI not found. Please install it first." >&2
        exit 1
    fi

    # Build model argument if specified
    local model_arg=""
    if [[ -n "$model" ]]; then
        model_arg="--model $model"
    fi

    if [[ "$mode" == "interactive" ]]; then
        # Interactive mode - use -i flag to start interactive session with initial prompt
        if [[ -n "$output" ]]; then
            gemini $model_arg -i "$prompt" 2>&1 | tee "$output"
        else
            gemini $model_arg -i "$prompt"
        fi
    else
        # Headless mode - use positional prompt for one-shot execution
        # Enable YOLO mode for automated execution (auto-approve all tools)
        if [[ -n "$output" ]]; then
            gemini --yolo $model_arg "$prompt" > "$output" 2>&1
        else
            gemini --yolo $model_arg "$prompt"
        fi
    fi
}

# Function to call Codex CLI
call_codex() {
    local prompt="$1"
    local mode="$2"
    local output="$3"
    local model="${MODEL}"

    # Check if codex CLI is available
    if ! command -v codex &> /dev/null; then
        echo "Error: codex CLI not found. Please install it first." >&2
        exit 1
    fi

    # Build model config if specified
    local model_arg=""
    if [[ -n "$model" ]]; then
        model_arg="-c model=$model"
    fi

    if [[ "$mode" == "interactive" ]]; then
        # Interactive mode - Codex requires a real TTY
        # We cannot capture output without breaking the TTY requirement
        # Enable workspace-write sandbox for file creation
        if [[ -n "$output" ]]; then
            echo "Note: Session will be saved to $output after completion" >&2
            # Run codex interactively with write permissions, then save output afterwards
            # Note: This won't capture the full session, just a marker
            echo "[Interactive session started at $(date)]" > "$output"
            codex --sandbox workspace-write $model_arg "$prompt"
            echo "[Interactive session ended at $(date)]" >> "$output"
        else
            codex --sandbox workspace-write $model_arg "$prompt"
        fi
    else
        # Headless mode - use 'exec' subcommand for non-interactive execution
        # Enable workspace-write sandbox for file creation
        if [[ -n "$output" ]]; then
            codex exec --sandbox workspace-write $model_arg "$prompt" > "$output" 2>&1
        else
            codex exec --sandbox workspace-write $model_arg "$prompt"
        fi
    fi
}

# Route to appropriate provider
case "$PROVIDER" in
    claude)
        call_claude "$PROMPT" "$MODE" "$OUTPUT_FILE"
        ;;
    gemini)
        call_gemini "$PROMPT" "$MODE" "$OUTPUT_FILE"
        ;;
    openai|codex)
        call_codex "$PROMPT" "$MODE" "$OUTPUT_FILE"
        ;;
    *)
        echo "Error: Unknown provider '$PROVIDER'. Supported: claude, gemini, codex" >&2
        exit 1
        ;;
esac

exit 0
