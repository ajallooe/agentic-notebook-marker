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

# Add src/utils to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))
from system_config import resolve_provider_from_model, format_available_models


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


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape codes from text."""
    import re
    # Pattern matches ANSI escape sequences
    ansi_pattern = r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[PX^_][^\x1b]*\x1b\\|\x1b\[[\?]?[0-9;]*[hl]'
    return re.sub(ansi_pattern, '', text)


def strip_line_numbers(text: str) -> str:
    """Remove line number prefixes from text (e.g., '  1 {' -> '{')."""
    import re
    # Pattern matches line numbers at start of lines (with optional leading spaces)
    # Handles formats like "  1 {", "  2   ", " 10 ", "277 }"
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        # Remove leading line number pattern (spaces + digits + space)
        cleaned = re.sub(r'^\s*\d+\s', '', line)
        cleaned_lines.append(cleaned)
    return '\n'.join(cleaned_lines)


def extract_json_from_output(output_text: str) -> str:
    """Extract JSON from between the markers in agent output."""
    import re

    # Strip ANSI escape codes first (from script command output)
    clean_text = strip_ansi_codes(output_text)

    # Find the LAST occurrence of the markers (the final output, not earlier redraws)
    last_start = clean_text.rfind('===MAPPING_JSON_START===')
    last_end = clean_text.rfind('===MAPPING_JSON_END===')

    best_match = None
    if last_start > 0 and last_end > last_start:
        # Extract content between last markers
        best_match = clean_text[last_start + 24:last_end].strip()

    # Fallback: if no markers found or content is too small, try regex
    if not best_match or len(best_match) < 100:
        pattern = r'===MAPPING_JSON_START===\s*(.*?)\s*===MAPPING_JSON_END==='
        matches = re.findall(pattern, clean_text, re.DOTALL)

        # Find valid matches (skip examples)
        for match in reversed(matches):  # Check from last to first
            content = match.strip()
            if '...full JSON here...' in content:
                continue
            if len(content) < 100:
                continue
            best_match = content
            break

    if best_match:
        # Strip line numbers if present (from Gemini TUI display)
        cleaned = strip_line_numbers(best_match)

        # Aggressive cleaning for TUI artifacts
        # Remove box-drawing characters
        cleaned = re.sub(r'[╭╮╯╰│─┬┴┼├┤]', '', cleaned)
        # Remove spinner/loading characters
        cleaned = re.sub(r'[⠼⠋⠹⠸⠴⠦⠧⠇⠏]', '', cleaned)

        # Filter lines to keep only JSON-like content
        lines = []
        for line in cleaned.split('\n'):
            stripped = line.strip()
            # Skip empty lines
            if not stripped:
                continue
            # Skip TUI status lines and notifications
            if any(skip in line for skip in [
                'Gemini CLI update', 'brew upgrade', 'Installed via',
                'Generating', 'esc to cancel', 'open files', 'ctrl+g',
                'Type your message', '@path/to/file', 'Using:',
                'GEMINI.md', '>', '|'
            ]):
                continue
            # Skip lines with arrows (usually status indicators)
            if '→' in line and len(stripped) < 100:
                continue
            lines.append(line)

        cleaned = '\n'.join(lines)

        # Extract JSON by finding matching braces
        import json

        # Find the actual JSON start - look for {"assignment_name"
        json_start_pattern = r'\{\s*"assignment_name"'
        start_match = re.search(json_start_pattern, cleaned)
        if not start_match:
            # Fallback: just find first {
            start_idx = cleaned.find('{')
            if start_idx == -1:
                return None
        else:
            start_idx = start_match.start()

        # Count braces to find the end
        brace_count = 0
        end_idx = start_idx
        for i, char in enumerate(cleaned[start_idx:], start_idx):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break

        if end_idx > start_idx:
            candidate = cleaned[start_idx:end_idx + 1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                # Try to repair common issues
                # Remove any remaining control characters
                candidate = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', candidate)
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    pass

        # Return best effort
        json_match = re.search(r'(\{.*\})', cleaned, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
        return cleaned

    # Fallback: look for a large JSON object with assignment_name
    # This pattern finds JSON objects that span multiple lines
    json_pattern = r'(\{\s*"assignment_name"\s*:.*?"summary"\s*:\s*\{[^}]+\}\s*\})'
    match = re.search(json_pattern, clean_text, re.DOTALL)

    if match:
        return match.group(1).strip()

    # Last resort: find any JSON object starting with {"assignment_name"
    simple_pattern = r'(\{"assignment_name".*\})\s*(?:===|$|\n\n)'
    match = re.search(simple_pattern, clean_text, re.DOTALL)

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
    parser.add_argument('--provider',
                       choices=['claude', 'gemini', 'codex'],
                       help='LLM provider (optional if --model is specified)')
    parser.add_argument('--model', help='Model to use (provider auto-resolved)')

    args = parser.parse_args()

    # Resolve provider from model if not specified
    provider = args.provider
    model = args.model

    if not provider and model:
        provider = resolve_provider_from_model(model)
        if not provider:
            print(f"Error: Unknown model '{model}'")
            print("")
            print(format_available_models())
            return 1

    if not provider and not model:
        print("Error: --model or --provider is required")
        return 1

    if not provider:
        print("Error: Could not determine provider")
        return 1

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
        provider,
        model
    )

    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
