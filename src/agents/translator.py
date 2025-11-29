#!/usr/bin/env python3
"""
Translator Agent - Gradebook CSV Mapping

Creates a mapping between grades.csv and section gradebook CSVs using LLM for
intelligent fuzzy name matching and column identification.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def read_csv_content(csv_path: str, max_lines: int = None) -> str:
    """Read CSV file content, optionally limiting lines."""
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            if max_lines:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"... ({i} more lines)")
                        break
                    lines.append(line.rstrip())
                return '\n'.join(lines)
            else:
                return f.read()
    except UnicodeDecodeError:
        # Try with different encoding
        with open(csv_path, 'r', encoding='latin-1') as f:
            if max_lines:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"... (more lines)")
                        break
                    lines.append(line.rstrip())
                return '\n'.join(lines)
            else:
                return f.read()


def load_prompt_template(assignment_name: str, total_marks: int, assignment_type: str,
                         grades_csv_path: str, gradebook_paths: list,
                         output_path: str) -> str:
    """Load and fill the translator prompt template."""

    script_dir = Path(__file__).parent.parent
    template_path = script_dir / 'prompts' / 'translator.md'

    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()

    # Read grades.csv content
    grades_csv_content = read_csv_content(grades_csv_path)

    # Build gradebook info with content and full paths
    gradebooks_content = ""
    for i, path in enumerate(gradebook_paths, 1):
        filename = Path(path).name
        content = read_csv_content(path)
        gradebooks_content += f"### Gradebook {i}: `{filename}`\n\n**Full path**: `{path}`\n\n```csv\n{content}\n```\n\n"

    # Fill template
    prompt = template.format(
        assignment_name=assignment_name,
        total_marks=total_marks,
        assignment_type=assignment_type,
        grades_csv_path=grades_csv_path,
        grades_csv_content=grades_csv_content,
        gradebooks_content=gradebooks_content,
        output_path=output_path
    )

    return prompt


def extract_json_from_output(output_text: str) -> str:
    """Extract JSON from between the markers in agent output."""
    import re

    # Look for JSON between markers
    pattern = r'===MAPPING_JSON_START===\s*(.*?)\s*===MAPPING_JSON_END==='
    match = re.search(pattern, output_text, re.DOTALL)

    if match:
        return match.group(1).strip()

    # Fallback: try to find a JSON object that looks like our mapping
    # Look for JSON starting with {"assignment_name"
    json_pattern = r'(\{[^{}]*"assignment_name"[^{}]*\{.*?\}\s*\})'
    match = re.search(json_pattern, output_text, re.DOTALL)

    if match:
        return match.group(1).strip()

    return None


def run_translator(assignment_name: str, total_marks: int, assignment_type: str,
                   grades_csv_path: str, gradebook_paths: list, output_path: str,
                   provider: str, model: str = None):
    """Run the translator agent via LLM CLI."""
    import subprocess
    import json

    # Build prompt
    prompt = load_prompt_template(
        assignment_name, total_marks, assignment_type,
        grades_csv_path, gradebook_paths, output_path
    )

    # Prepare LLM caller command with session capture
    script_dir = Path(__file__).parent.parent
    llm_caller = script_dir / 'llm_caller.sh'
    session_log = Path(output_path) / 'translator_session.log'

    cmd = [
        'bash',
        str(llm_caller),
        '--prompt', prompt,
        '--mode', 'interactive',
        '--provider', provider,
        '--output', str(session_log)
    ]

    if model:
        cmd.extend(['--model', model])

    # Run the interactive agent session - inherit stdin/stdout/stderr for TTY access
    result = subprocess.run(cmd, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)

    if result.returncode != 0:
        print(f"\nError: Translator agent failed with exit code {result.returncode}")
        return False

    # Check if mapping file was directly created by agent (Claude can do this)
    mapping_file = Path(output_path) / 'translation_mapping.json'
    if mapping_file.exists():
        print(f"\n✓ Translation mapping saved to: {mapping_file}")
        return True

    # Otherwise, parse the session log to extract JSON
    if not session_log.exists():
        print(f"\nError: Session log not found at {session_log}")
        return False

    print("\nParsing session output for mapping JSON...")

    with open(session_log, 'r', encoding='utf-8', errors='ignore') as f:
        session_output = f.read()

    json_content = extract_json_from_output(session_output)

    if not json_content:
        print("\nError: Could not find mapping JSON in agent output.")
        print("The agent should output JSON between ===MAPPING_JSON_START=== and ===MAPPING_JSON_END=== markers.")
        return False

    # Validate JSON
    try:
        mapping_data = json.loads(json_content)
    except json.JSONDecodeError as e:
        print(f"\nError: Invalid JSON in agent output: {e}")
        print("JSON content found:")
        print(json_content[:500] + "..." if len(json_content) > 500 else json_content)
        return False

    # Save the mapping file
    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump(mapping_data, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Translation mapping saved to: {mapping_file}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Create gradebook translation mapping using LLM agent'
    )
    parser.add_argument('--assignment-name', required=True, help='Assignment name')
    parser.add_argument('--total-marks', type=int, required=True, help='Total marks')
    parser.add_argument('--assignment-type', choices=['structured', 'freeform'],
                       required=True, help='Assignment type')
    parser.add_argument('--grades-csv', required=True, help='Path to grades.csv')
    parser.add_argument('--gradebooks', required=True, nargs='+',
                       help='Paths to gradebook CSVs')
    parser.add_argument('--output-path', required=True,
                       help='Directory to save mapping file')
    parser.add_argument('--provider', required=True,
                       choices=['claude', 'gemini', 'codex'], help='LLM provider')
    parser.add_argument('--model', help='Specific model to use')

    args = parser.parse_args()

    # Validate inputs
    grades_csv = Path(args.grades_csv)
    if not grades_csv.exists():
        print(f"Error: Grades CSV not found: {grades_csv}")
        return 1

    for gradebook in args.gradebooks:
        if not Path(gradebook).exists():
            print(f"Error: Gradebook CSV not found: {gradebook}")
            return 1

    output_path = Path(args.output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # Run translator
    success = run_translator(
        args.assignment_name,
        args.total_marks,
        args.assignment_type,
        str(grades_csv.absolute()),
        [str(Path(g).absolute()) for g in args.gradebooks],
        str(output_path.absolute()),
        args.provider,
        args.model
    )

    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
