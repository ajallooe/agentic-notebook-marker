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

Prompt Caching:
  For repeated prompts with shared prefixes (e.g., same rubric, different students),
  use --system-prompt to provide the cacheable static content:

  python3 caller.py --model claude-sonnet-4-5 \\
      --system-prompt "You are a grading assistant..." \\
      --prompt "Grade this student: ..."

  Claude: Uses explicit cache_control markers (min 1024 tokens, 5 min TTL)
  Gemini 2.5: Implicit caching automatic (min 1024-4096 tokens, 60 min TTL)
  OpenAI: Automatic caching (min 1024 tokens, 5-10 min TTL)

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
    """Resolve provider from model name using models.yaml.

    Checks both api_models and cli_models sections.
    """
    if not models_config.exists():
        return None

    with open(models_config, 'r') as f:
        content = f.read()

    # Simple YAML parsing - check both api_models and cli_models sections
    for section in ['api_models', 'cli_models']:
        in_section = False
        for line in content.split('\n'):
            if line.strip() == f'{section}:':
                in_section = True
                continue
            if in_section:
                if line and not line.startswith(' ') and not line.startswith('#'):
                    in_section = False  # New top-level section
                    continue
                if model + ':' in line:
                    # Extract provider
                    parts = line.split(':')
                    if len(parts) >= 2:
                        return parts[-1].strip().strip('"').strip("'")

    return None


def call_anthropic(model: str, prompt: str, max_tokens: int = 8192,
                   system_prompt: str | None = None) -> tuple[str, dict]:
    """Call Anthropic/Claude API with optional prompt caching.

    Args:
        model: Model name (e.g., claude-sonnet-4-5)
        prompt: User prompt (variable content)
        max_tokens: Maximum output tokens
        system_prompt: Optional system prompt to cache (static content, min 1024 tokens)

    Claude prompt caching:
        - System prompt is marked with cache_control for automatic caching
        - Cached content expires after 5 minutes (default TTL)
        - Minimum 1024 tokens required for caching
        - Cache writes cost +25%, cache reads cost only 10% of base price
    """
    try:
        import anthropic
    except ImportError:
        print("Error: anthropic package not installed. Run: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    # Check CLAUDE_API_KEY first, fall back to ANTHROPIC_API_KEY for compatibility
    api_key = os.environ.get('CLAUDE_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("Error: CLAUDE_API_KEY (or ANTHROPIC_API_KEY) environment variable not set", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Build request with optional caching
    request_kwargs = {
        'model': model,
        'max_tokens': max_tokens,
        'messages': [
            {"role": "user", "content": prompt}
        ]
    }

    # Add system prompt with cache_control if provided
    if system_prompt:
        # Use cache_control to enable prompt caching
        # The "ephemeral" type uses default 5-minute TTL
        request_kwargs['system'] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}
            }
        ]

    response = client.messages.create(**request_kwargs)

    # Extract text from response
    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text

    # Extract usage stats including cache info
    stats = {
        'input_tokens': response.usage.input_tokens,
        'output_tokens': response.usage.output_tokens,
        'cache_creation_tokens': getattr(response.usage, 'cache_creation_input_tokens', 0) or 0,
        'cache_read_tokens': getattr(response.usage, 'cache_read_input_tokens', 0) or 0,
        'cost_usd': 0,  # Could calculate from token counts and model pricing
    }

    return text, stats


def call_google(model: str, prompt: str, system_prompt: str | None = None) -> tuple[str, dict]:
    """Call Google Generative AI API with optional system instruction.

    Args:
        model: Model name (e.g., gemini-2.5-pro)
        prompt: User prompt (variable content)
        system_prompt: Optional system instruction (for Gemini's implicit caching)

    Gemini caching (2.5 models):
        - Implicit caching is automatic (no API changes needed)
        - System instructions at start of prompt help cache hit rate
        - Min tokens: 1024 (Flash), 4096 (Pro)
        - 90% discount on cache hits
    """
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

    # Create model with system instruction if provided
    # This helps with implicit caching - static content goes in system_instruction
    if system_prompt:
        gen_model = genai.GenerativeModel(model, system_instruction=system_prompt)
    else:
        gen_model = genai.GenerativeModel(model)

    response = gen_model.generate_content(prompt)

    text = response.text

    # Extract usage stats including cache info (Gemini 2.5 reports cached_content_token_count)
    usage_metadata = getattr(response, 'usage_metadata', None)
    if usage_metadata:
        # Gemini reports cached tokens when implicit caching hits
        cached_tokens = getattr(usage_metadata, 'cached_content_token_count', 0) or 0
        stats = {
            'input_tokens': getattr(usage_metadata, 'prompt_token_count', 0) or 0,
            'output_tokens': getattr(usage_metadata, 'candidates_token_count', 0) or 0,
            'cache_creation_tokens': 0,  # Gemini doesn't differentiate creation vs read
            'cache_read_tokens': cached_tokens,
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


def call_openai(model: str, prompt: str, system_prompt: str | None = None) -> tuple[str, dict]:
    """Call OpenAI API with optional system message.

    Args:
        model: Model name (e.g., gpt-5.1)
        prompt: User prompt (variable content)
        system_prompt: Optional system message (helps with automatic caching)

    OpenAI caching:
        - Automatic for prompts > 1024 tokens
        - System message at start helps cache hit rate
        - 50% discount on cached input tokens
        - Cache cleared after 5-10 min inactivity
    """
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

    # Build messages with optional system prompt
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages
    )

    text = response.choices[0].message.content or ""

    # Extract usage stats including cache info
    usage = response.usage
    if usage:
        # OpenAI reports cached tokens in prompt_tokens_details
        prompt_details = getattr(usage, 'prompt_tokens_details', None)
        cached_tokens = 0
        if prompt_details:
            cached_tokens = getattr(prompt_details, 'cached_tokens', 0) or 0

        stats = {
            'input_tokens': usage.prompt_tokens,
            'output_tokens': usage.completion_tokens,
            'cache_creation_tokens': 0,  # OpenAI doesn't differentiate
            'cache_read_tokens': cached_tokens,
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


def main():
    parser = argparse.ArgumentParser(description='Direct LLM API caller')
    parser.add_argument('--model', required=True, help='Model name (provider auto-resolved)')
    parser.add_argument('--prompt', help='Prompt text')
    parser.add_argument('--prompt-file', help='Read prompt from file')
    parser.add_argument('--system-prompt', help='System prompt (cacheable static content)')
    parser.add_argument('--system-prompt-file', help='Read system prompt from file')
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

    # Get system prompt (for caching)
    system_prompt = None
    if args.system_prompt_file:
        with open(args.system_prompt_file, 'r') as f:
            system_prompt = f.read()
    elif args.system_prompt:
        system_prompt = args.system_prompt

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

    # Call appropriate API with system prompt for caching
    try:
        if provider == 'claude':
            text, stats = call_anthropic(args.model, prompt, args.max_tokens, system_prompt)
        elif provider == 'gemini':
            text, stats = call_google(args.model, prompt, system_prompt)
        elif provider == 'openai':
            text, stats = call_openai(args.model, prompt, system_prompt)
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
