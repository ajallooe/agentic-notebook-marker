#!/usr/bin/env python3
"""
System Configuration Loader

Loads system-wide defaults from config.yaml at the project root.
These are fallback values when not specified in assignment overview.md.
"""

import os
import sys
from pathlib import Path
import yaml


def get_project_root():
    """Get the project root directory."""
    # Assume this file is in src/utils/, so project root is 2 levels up
    return Path(__file__).parent.parent.parent


def load_system_config():
    """
    Load system-wide configuration from config.yaml.

    Returns:
        dict: Configuration dictionary with system defaults
    """
    config_file = get_project_root() / "configs" / "config.yaml"

    if not config_file.exists():
        # Fallback to hardcoded defaults if config.yaml is missing
        return {
            "default_provider": "claude",
            "default_model": None,
            "max_parallel": 4,
            "verbose": True
        }

    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
            return config if config else {}
    except Exception as e:
        print(f"Warning: Failed to load config.yaml: {e}", file=sys.stderr)
        print("Using fallback defaults", file=sys.stderr)
        return {
            "default_provider": "claude",
            "default_model": None,
            "max_parallel": 4,
            "verbose": True
        }


def get_default_provider():
    """Get the default LLM provider from system config."""
    config = load_system_config()
    return config.get("default_provider", "claude")


def get_default_model():
    """Get the default model from system config (may be None)."""
    config = load_system_config()
    return config.get("default_model")


def get_max_parallel():
    """Get the default max parallel workers from system config."""
    config = load_system_config()
    return config.get("max_parallel", 4)


if __name__ == "__main__":
    # Test the configuration loader
    config = load_system_config()
    print("System configuration:")
    print(f"  default_provider: {config.get('default_provider')}")
    print(f"  default_model: {config.get('default_model')}")
    print(f"  max_parallel: {config.get('max_parallel')}")
    print(f"  verbose: {config.get('verbose')}")
