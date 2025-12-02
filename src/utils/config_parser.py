#!/usr/bin/env python3
"""
Configuration parser for overview.md files.

Supports YAML front matter and key-value pairs.
Falls back to configs/config.yaml for system defaults.
"""

import re
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path to support both script and module execution
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import system config loader
try:
    from .system_config import load_system_config
except ImportError:
    # When run as script, use absolute import
    from src.utils.system_config import load_system_config


def parse_overview(overview_path: str) -> Dict[str, Any]:
    """
    Parse overview.md file for configuration.

    Supports two formats:
    1. YAML front matter (between --- delimiters)
    2. Key: value pairs anywhere in the file

    Falls back to configs/config.yaml for unspecified values.

    Args:
        overview_path: Path to overview.md file

    Returns:
        Dictionary of configuration values with defaults
    """
    # Load system defaults from configs/config.yaml
    system_config = load_system_config()

    # Start with system defaults, then override with assignment-specific values
    # No hardcoded provider/model - must come from config.yaml or overview.md
    config = {
        'default_provider': system_config.get('default_provider', ''),
        'default_model': system_config.get('default_model', ''),
        'max_parallel': system_config.get('max_parallel', 4),
        'api_max_parallel': system_config.get('api_max_parallel', 32),
        'base_file': '',
        'assignment_type': 'structured',
        'total_marks': 100,
        'group_assignment': False,  # Whether this is a group assignment
        'different_problems': False,  # Whether groups solve different problems (requires group_assignment=true, assignment_type=freeform)
        'description': '',
        'stage_models': {}  # Per-stage model overrides
    }

    if not Path(overview_path).exists():
        return config

    with open(overview_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Try to parse YAML front matter first
    yaml_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)

    if yaml_match:
        yaml_content = yaml_match.group(1)
        description = yaml_match.group(2).strip()

        # Parse YAML-like content (simple key: value pairs and nested stage_models)
        in_stage_models = False
        for line in yaml_content.split('\n'):
            stripped_line = line.strip()

            # Skip comments and empty lines
            if not stripped_line or stripped_line.startswith('#'):
                continue

            # Check if we're entering/exiting stage_models section
            if stripped_line == 'stage_models:':
                in_stage_models = True
                continue

            if ':' in stripped_line:
                # Determine if this is an indented line (part of stage_models)
                is_indented = line.startswith((' ', '\t'))

                key, value = stripped_line.split(':', 1)
                key = key.strip()
                value = value.strip()

                # Remove quotes and comments from value
                if '#' in value and not (value.startswith(('"', "'"))):
                    value = value.split('#')[0].strip()
                if value.startswith(('"', "'")) and value.endswith(('"', "'")):
                    value = value[1:-1]

                if in_stage_models and is_indented:
                    # This is a stage model override
                    config['stage_models'][key] = value
                else:
                    # This is a top-level key
                    in_stage_models = False

                    # Try to convert to appropriate type
                    if key in config:
                        if isinstance(config[key], int):
                            try:
                                config[key] = int(value)
                            except ValueError:
                                config[key] = value
                        else:
                            config[key] = value

        config['description'] = description

    else:
        # Fallback: look for key-value pairs in the entire file
        config['description'] = content

        # Look for specific patterns
        patterns = {
            'default_provider': r'default_provider:\s*(.+)',
            'default_model': r'default_model:\s*(.+)',
            'max_parallel': r'max_parallel:\s*(\d+)',
            'base_file': r'base_file:\s*(.+)',
            'assignment_type': r'assignment_type:\s*(.+)',
            'total_marks': r'total_marks:\s*(\d+)',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                value = match.group(1).strip()

                # Remove quotes
                if value.startswith(('"', "'")) and value.endswith(('"', "'")):
                    value = value[1:-1]

                # Convert to int if needed
                if isinstance(config[key], int):
                    try:
                        config[key] = int(value)
                    except ValueError:
                        pass
                else:
                    config[key] = value

    # Validate configuration constraints
    if config['different_problems']:
        if not config['group_assignment']:
            print("Warning: different_problems=true requires group_assignment=true", file=sys.stderr)
        if config['assignment_type'] != 'freeform':
            print("Warning: different_problems=true requires assignment_type=freeform", file=sys.stderr)

    return config


def print_config(config: Dict[str, Any]):
    """Print configuration in a readable format."""
    print("Configuration:")
    for key, value in config.items():
        if key == 'description':
            continue
        elif key == 'stage_models' and value:
            print(f"  {key}:")
            for stage, model in value.items():
                print(f"    {stage}: {model}")
        else:
            print(f"  {key}: {value}")


def export_bash_vars(config: Dict[str, Any]) -> str:
    """
    Export configuration as bash variable assignments.

    Returns:
        String of bash export statements
    """
    bash_lines = []

    mapping = {
        'default_provider': 'DEFAULT_PROVIDER',
        'default_model': 'DEFAULT_MODEL',
        'max_parallel': 'MAX_PARALLEL',
        'api_max_parallel': 'API_MAX_PARALLEL',
        'base_file': 'BASE_FILE',
        'assignment_type': 'ASSIGNMENT_TYPE',
        'total_marks': 'TOTAL_MARKS',
        'group_assignment': 'GROUP_ASSIGNMENT',
        'different_problems': 'DIFFERENT_PROBLEMS'
    }

    for key, bash_var in mapping.items():
        value = config.get(key, '')
        if value is None:
            # Convert None to empty string for bash
            bash_lines.append(f'{bash_var}=""')
        elif isinstance(value, bool):
            # Convert Python bool to bash true/false
            bash_lines.append(f'{bash_var}={str(value).lower()}')
        elif isinstance(value, str):
            bash_lines.append(f'{bash_var}="{value}"')
        else:
            bash_lines.append(f'{bash_var}={value}')

    # Export per-stage model overrides
    stage_models = config.get('stage_models', {})
    for stage, model in stage_models.items():
        # Convert stage name to uppercase bash variable name
        # e.g., pattern_designer -> STAGE_MODEL_PATTERN_DESIGNER
        bash_var = f'STAGE_MODEL_{stage.upper()}'
        bash_lines.append(f'{bash_var}="{model}"')

    return '\n'.join(bash_lines)


def main():
    """CLI interface for configuration parser."""
    if len(sys.argv) < 2:
        print("Usage: config_parser.py <overview.md> [--bash]")
        print("  --bash: Output as bash variable assignments")
        sys.exit(1)

    overview_path = sys.argv[1]
    output_bash = '--bash' in sys.argv

    config = parse_overview(overview_path)

    if output_bash:
        print(export_bash_vars(config))
    else:
        print_config(config)
        if config['description']:
            print(f"\nDescription preview:")
            preview = config['description'][:200]
            if len(config['description']) > 200:
                preview += "..."
            print(f"  {preview}")


if __name__ == "__main__":
    main()
