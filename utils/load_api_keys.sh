#!/usr/bin/env bash
#
# Load API keys from .secrets/ directory into environment variables
#
# Usage: source utils/load_api_keys.sh
#
# NOTE: This file must be SOURCED, not executed, for the exports to persist:
#   source utils/load_api_keys.sh   # correct
#   ./utils/load_api_keys.sh        # wrong - exports won't persist
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SECRETS_DIR="$PROJECT_ROOT/.secrets"

if [[ ! -d "$SECRETS_DIR" ]]; then
    echo "Warning: .secrets/ directory not found at $SECRETS_DIR"
    return 1 2>/dev/null || exit 1
fi

# Load Anthropic API key
if [[ -f "$SECRETS_DIR/ANTHROPIC_API_KEY" ]]; then
    export ANTHROPIC_API_KEY="$(cat "$SECRETS_DIR/ANTHROPIC_API_KEY" | tr -d '\n')"
    echo "Loaded ANTHROPIC_API_KEY"
fi

# Load Google/Gemini API key
if [[ -f "$SECRETS_DIR/GEMINI_API_KEY" ]]; then
    export GEMINI_API_KEY="$(cat "$SECRETS_DIR/GEMINI_API_KEY" | tr -d '\n')"
    export GOOGLE_API_KEY="$GEMINI_API_KEY"  # Alias for compatibility
    echo "Loaded GEMINI_API_KEY (also set as GOOGLE_API_KEY)"
elif [[ -f "$SECRETS_DIR/GOOGLE_API_KEY" ]]; then
    export GOOGLE_API_KEY="$(cat "$SECRETS_DIR/GOOGLE_API_KEY" | tr -d '\n')"
    export GEMINI_API_KEY="$GOOGLE_API_KEY"  # Alias for compatibility
    echo "Loaded GOOGLE_API_KEY (also set as GEMINI_API_KEY)"
fi

# Load OpenAI API key
if [[ -f "$SECRETS_DIR/OPENAI_API_KEY" ]]; then
    export OPENAI_API_KEY="$(cat "$SECRETS_DIR/OPENAI_API_KEY" | tr -d '\n')"
    echo "Loaded OPENAI_API_KEY"
fi

echo "API keys loaded from $SECRETS_DIR"
