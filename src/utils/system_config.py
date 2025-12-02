#!/usr/bin/env python3
"""
System Configuration Loader

Loads system-wide defaults from config.yaml and models.yaml at the project root.
These are fallback values when not specified in assignment overview.md.

IMPORTANT: No model names or provider defaults are hardcoded here.
All defaults come from configs/config.yaml. If that file is missing,
the caller must provide explicit values.
"""

import sys
from pathlib import Path
import yaml


def get_project_root():
    """Get the project root directory."""
    # Assume this file is in src/utils/, so project root is 2 levels up
    return Path(__file__).parent.parent.parent


def get_config_path():
    """Get the path to the config.yaml file."""
    return get_project_root() / "configs" / "config.yaml"


def get_models_config_path():
    """Get the path to the models.yaml file."""
    return get_project_root() / "configs" / "models.yaml"


def load_system_config():
    """
    Load system-wide configuration from config.yaml.

    Returns:
        dict: Configuration dictionary with system defaults.
              Returns empty dict if config file doesn't exist.
    """
    config_file = get_config_path()

    if not config_file.exists():
        return {}

    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
            return config if config else {}
    except Exception as e:
        print(f"Warning: Failed to load config.yaml: {e}", file=sys.stderr)
        return {}


def get_default_provider():
    """
    Get the default LLM provider from system config.

    Returns:
        str or None: The default provider, or None if not configured.
    """
    config = load_system_config()
    return config.get("default_provider")


def get_default_model():
    """
    Get the default model from system config.

    Returns:
        str or None: The default model, or None if not configured.
    """
    config = load_system_config()
    return config.get("default_model")


def get_max_parallel():
    """
    Get the default max parallel workers from system config.

    Returns:
        int: The max parallel workers (defaults to 4 if not configured).
    """
    config = load_system_config()
    return config.get("max_parallel", 4)


def is_verbose():
    """
    Get the verbose setting from system config.

    Returns:
        bool: Whether verbose mode is enabled (defaults to True if not configured).
    """
    config = load_system_config()
    return config.get("verbose", True)


def load_models_config():
    """
    Load models configuration from models.yaml.

    Returns:
        dict: Configuration dictionary with models and defaults.
              Returns empty dict if config file doesn't exist.
    """
    config_file = get_models_config_path()

    if not config_file.exists():
        return {}

    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
            return config if config else {}
    except Exception as e:
        print(f"Warning: Failed to load models.yaml: {e}", file=sys.stderr)
        return {}


def get_available_models():
    """
    Get all available models grouped by provider.

    Returns:
        dict: Dictionary mapping provider names to lists of model names.
    """
    config = load_models_config()
    models = config.get('models', {})

    # Group models by provider
    by_provider = {'claude': [], 'gemini': [], 'codex': []}
    for model_name, provider in models.items():
        if provider in by_provider:
            by_provider[provider].append(model_name)

    return by_provider


def format_available_models():
    """
    Format available models for display in error messages.

    Returns:
        str: Formatted string listing all available models by provider.
    """
    by_provider = get_available_models()
    lines = ["Available models (from configs/models.yaml):"]

    for provider in ['claude', 'gemini', 'codex']:
        models = by_provider.get(provider, [])
        if models:
            lines.append(f"  {provider}: {', '.join(sorted(models))}")
        else:
            lines.append(f"  {provider}: (none configured)")

    lines.append("")
    lines.append("To add a new model, update configs/models.yaml")

    return '\n'.join(lines)


def resolve_provider_from_model(model_name: str) -> str | None:
    """
    Resolve provider from model name using models.yaml.

    Only returns a provider if the model is explicitly listed in models.yaml.
    This catches typos like 'gemini-pro-2.5' instead of 'gemini-2.5-pro'.

    Args:
        model_name: The model name to look up.

    Returns:
        str or None: The provider name, or None if model not found in models.yaml.
    """
    config = load_models_config()
    models = config.get('models', {})

    # Only allow models explicitly listed in models.yaml
    if model_name in models:
        return models[model_name]

    # No fallback inference - model must be in models.yaml
    return None


if __name__ == "__main__":
    # Test the configuration loader
    config = load_system_config()
    print("System configuration:")
    print(f"  config_path: {get_config_path()}")
    print(f"  default_provider: {config.get('default_provider', '(not set)')}")
    print(f"  default_model: {config.get('default_model', '(not set)')}")
    print(f"  max_parallel: {config.get('max_parallel', '(not set)')}")
    print(f"  verbose: {config.get('verbose', '(not set)')}")
    print()
    print(format_available_models())
