#!/usr/bin/env python3
"""
Direct LLM API Caller

Provides direct API access to Anthropic, Google, and OpenAI models.
Used by llm_caller.sh when --api-model is specified in headless mode.

Environment variables for API keys:
  - ANTHROPIC_API_KEY
  - GOOGLE_API_KEY (or GEMINI_API_KEY)
  - OPENAI_API_KEY

Usage:
  python3 caller.py --model <model> --prompt "text" [OPTIONS]
  python3 caller.py --model claude-sonnet-4 --prompt "Hello"
  python3 caller.py --model gemini-2.5-pro --prompt-file prompt.txt

Output:
  - Response text to stdout
  - Stats appended to --stats-file if provided (JSONL format)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def resolve_provider(model: str, models_config: Path) -> str | None:
    """Resolve provider from model name using models.yaml."""
    if not models_config.exists():
        return None

    with open(models_config, 'r') as f:
        content = f.read()

    # Simple YAML parsing for model: provider lines
    in_models = False
    for line in content.split('\n'):
        if line.strip() == 'models:':
            in_models = True
            continue
        if in_models:
            if line and not line.startswith(' '):
                break  # New top-level section
            if model + ':' in line:
                # Extract provider
                parts = line.split(':')
                if len(parts) >= 2:
                    return parts[-1].strip().strip('"').strip("'")

    return None


def call_anthropic(model: str, prompt: str, max_tokens: int = 8192) -> tuple[str, dict]:
    """Call Anthropic API."""
    try:
        import anthropic
    except ImportError:
        print("Error: anthropic package not installed. Run: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    # Extract text from response
    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text

    # Extract usage stats
    stats = {
        'input_tokens': response.usage.input_tokens,
        'output_tokens': response.usage.output_tokens,
        'cache_creation_tokens': getattr(response.usage, 'cache_creation_input_tokens', 0) or 0,
        'cache_read_tokens': getattr(response.usage, 'cache_read_input_tokens', 0) or 0,
        'cost_usd': 0,  # Could calculate from token counts and model pricing
    }

    return text, stats


def call_google(model: str, prompt: str) -> tuple[str, dict]:
    """Call Google Generative AI API."""
    try:
        import google.generativeai as genai
    except ImportError:
        print("Error: google-generativeai package not installed. Run: pip install google-generativeai", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("Error: GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    genai.configure(api_key=api_key)

    gen_model = genai.GenerativeModel(model)
    response = gen_model.generate_content(prompt)

    text = response.text

    # Extract usage stats if available
    usage_metadata = getattr(response, 'usage_metadata', None)
    if usage_metadata:
        stats = {
            'input_tokens': getattr(usage_metadata, 'prompt_token_count', 0) or 0,
            'output_tokens': getattr(usage_metadata, 'candidates_token_count', 0) or 0,
            'cache_creation_tokens': 0,
            'cache_read_tokens': 0,
            'cost_usd': 0,
        }
    else:
        stats = {
            'input_tokens': 0,
            'output_tokens': 0,
            'cache_creation_tokens': 0,
            'cache_read_tokens': 0,
            'cost_usd': 0,
        }

    return text, stats


def call_openai(model: str, prompt: str) -> tuple[str, dict]:
    """Call OpenAI API."""
    try:
        import openai
    except ImportError:
        print("Error: openai package not installed. Run: pip install openai", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    client = openai.OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    text = response.choices[0].message.content or ""

    # Extract usage stats
    usage = response.usage
    stats = {
        'input_tokens': usage.prompt_tokens if usage else 0,
        'output_tokens': usage.completion_tokens if usage else 0,
        'cache_creation_tokens': 0,
        'cache_read_tokens': 0,
        'cost_usd': 0,
    }

    return text, stats


def main():
    parser = argparse.ArgumentParser(description='Direct LLM API caller')
    parser.add_argument('--model', required=True, help='Model name (provider auto-resolved)')
    parser.add_argument('--prompt', help='Prompt text')
    parser.add_argument('--prompt-file', help='Read prompt from file')
    parser.add_argument('--provider', help='Override provider (claude, gemini, openai)')
    parser.add_argument('--stats-file', help='Append stats to this file (JSONL)')
    parser.add_argument('--stats-stage', default='unknown', help='Stage name for stats')
    parser.add_argument('--stats-context', default='', help='Additional context')
    parser.add_argument('--max-tokens', type=int, default=8192, help='Max output tokens')
    args = parser.parse_args()

    # Get prompt
    if args.prompt_file:
        with open(args.prompt_file, 'r') as f:
            prompt = f.read()
    elif args.prompt:
        prompt = args.prompt
    else:
        print("Error: --prompt or --prompt-file required", file=sys.stderr)
        sys.exit(1)

    # Resolve provider
    if args.provider:
        provider = args.provider
    else:
        script_dir = Path(__file__).parent.parent.parent
        models_config = script_dir / "configs" / "models.yaml"
        provider = resolve_provider(args.model, models_config)

        if not provider:
            print(f"Error: Cannot resolve provider for model '{args.model}'", file=sys.stderr)
            print("Add it to configs/models.yaml or use --provider", file=sys.stderr)
            sys.exit(1)

    # Normalize provider name
    provider = provider.lower()
    if provider in ('anthropic', 'claude'):
        provider = 'claude'
    elif provider in ('google', 'gemini'):
        provider = 'gemini'
    elif provider in ('openai', 'codex'):
        provider = 'openai'

    # Call appropriate API
    try:
        if provider == 'claude':
            text, stats = call_anthropic(args.model, prompt, args.max_tokens)
        elif provider == 'gemini':
            text, stats = call_google(args.model, prompt)
        elif provider == 'openai':
            text, stats = call_openai(args.model, prompt)
        else:
            print(f"Error: Unknown provider '{provider}'", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Error: API call failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Output text to stdout
    print(text, end='')

    # Append stats if requested
    if args.stats_file:
        stats_entry = {
            'timestamp': datetime.now().isoformat(),
            'provider': provider,
            'model': args.model,
            'stage': args.stats_stage,
            'context': args.stats_context,
            'interface': 'api',
            **stats
        }

        stats_path = Path(args.stats_file)
        stats_path.parent.mkdir(parents=True, exist_ok=True)

        with open(stats_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(stats_entry) + '\n')


if __name__ == '__main__':
    main()
