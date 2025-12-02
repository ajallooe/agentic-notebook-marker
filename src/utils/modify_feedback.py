#!/usr/bin/env python3
"""
Feedback Modifier Utility

Takes an instruction prompt and applies it to modify feedback in a CSV file.
Only makes the specific changes requested - preserves everything else.
"""

import argparse
import csv
import subprocess
import sys
import tempfile
from pathlib import Path

from system_config import resolve_provider_from_model, format_available_models

# Project root for finding llm_caller.sh
PROJECT_ROOT = Path(__file__).parent.parent.parent
LLM_CALLER = PROJECT_ROOT / "src" / "llm_caller.sh"


MODIFY_PROMPT = """You are a precise feedback editor. Your task is to apply ONE specific modification to the feedback below.

INSTRUCTION: {instruction}

CRITICAL RULES:
1. ONLY make changes that directly address the instruction above
2. Do NOT change anything else - preserve all other content exactly
3. Do NOT add new content unless the instruction explicitly asks for it
4. Do NOT remove content unless the instruction explicitly asks for it
5. Do NOT change formatting, structure, or style unless instructed
6. Do NOT fix typos, grammar, or improve wording unless instructed
7. If the instruction doesn't apply to this feedback, return it UNCHANGED

Student: {student_name}
Total Mark: {total_mark}

ORIGINAL FEEDBACK:
{feedback}

OUTPUT the modified feedback below. If no changes are needed, output the original feedback exactly as-is:"""


def call_llm(prompt: str, provider: str, model: str = None) -> str:
    """Call LLM via llm_caller.sh and return the response."""

    # Write prompt to temp file to handle special characters
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        cmd = [
            str(LLM_CALLER),
            '--provider', provider,
            '--mode', 'headless',
            '--prompt-file', prompt_file,
        ]
        if model:
            cmd.extend(['--model', model])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(PROJECT_ROOT)
        )

        if result.returncode != 0:
            raise RuntimeError(f"LLM call failed: {result.stderr}")

        return result.stdout.strip()
    finally:
        # Clean up temp file
        Path(prompt_file).unlink(missing_ok=True)


def modify_feedback(student_name: str, total_mark: str, feedback: str,
                    instruction: str, provider: str, model: str = None) -> str:
    """Use LLM to apply a specific modification to feedback."""

    if not feedback or not feedback.strip():
        return feedback  # Nothing to modify

    prompt = MODIFY_PROMPT.format(
        instruction=instruction,
        student_name=student_name,
        total_mark=total_mark,
        feedback=feedback
    )

    try:
        result = call_llm(
            prompt=prompt,
            provider=provider,
            model=model
        )
        return result.strip()
    except Exception as e:
        print(f"  WARNING: Modification failed for {student_name}: {e}", file=sys.stderr)
        return feedback  # Return original on failure


def load_csv(csv_path: Path) -> tuple:
    """Load CSV and return fieldnames and records."""
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        records = list(reader)
    return fieldnames, records


def get_student_name(row: dict) -> str:
    """Extract student name from row, handling various column formats."""
    for col in ['Student Name', 'student_name', 'Name', 'name', 'Full Name']:
        if col in row and row[col].strip():
            return row[col].strip()

    # Try First + Last name
    first_name = ''
    last_name = ''
    for col in ['First name', 'First Name', 'first_name']:
        if col in row and row[col].strip():
            first_name = row[col].strip()
            break
    for col in ['Last name', 'Last Name', 'last_name', 'Surname']:
        if col in row and row[col].strip():
            last_name = row[col].strip()
            break

    if first_name and last_name:
        return f"{first_name} {last_name}"
    elif first_name:
        return first_name
    elif last_name:
        return last_name

    return "Unknown Student"


def get_total_mark(row: dict) -> str:
    """Extract total mark from row."""
    for col in ['Total Mark', 'total_mark', 'Mark', 'Grade', 'Score', 'Total']:
        if col in row and row[col].strip():
            return row[col].strip()
    return "N/A"


def find_feedback_column(fieldnames: list) -> str:
    """Find the feedback column name."""
    for col in ['Feedback Card', 'Feedback', 'feedback', 'Comments', 'comments']:
        if col in fieldnames:
            return col
    return None


def main():
    parser = argparse.ArgumentParser(
        description='Apply a specific modification to feedback in a CSV file'
    )
    parser.add_argument(
        'csv_file',
        help='Path to the CSV file with feedback'
    )
    parser.add_argument(
        '--instruction', '-i',
        required=True,
        help='The modification instruction to apply (e.g., "Remove all mentions of random_state")'
    )
    parser.add_argument(
        '--output',
        help='Output CSV file (default: <input>_modified.csv)'
    )
    parser.add_argument(
        '--provider',
        help='LLM provider (claude, gemini, codex). Auto-resolved from --model if not specified.'
    )
    parser.add_argument(
        '--model',
        help='Model to use (provider auto-resolved from model name)'
    )
    parser.add_argument(
        '--feedback-col',
        help='Name of the feedback column (auto-detected if not specified)'
    )
    parser.add_argument(
        '--in-place',
        action='store_true',
        help='Modify the file in-place (creates backup as <file>.bak)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without calling LLM'
    )

    args = parser.parse_args()

    # Resolve provider from model if not specified
    provider = args.provider
    model = args.model

    if not provider and model:
        provider = resolve_provider_from_model(model)
        if not provider:
            print(f"Error: Unknown model '{model}'", file=sys.stderr)
            print("", file=sys.stderr)
            print(format_available_models(), file=sys.stderr)
            sys.exit(1)

    # Default to claude if neither specified
    if not provider:
        provider = 'claude'

    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args.in_place:
        output_path = csv_path
        backup_path = csv_path.with_suffix(csv_path.suffix + '.bak')
    elif args.output:
        output_path = Path(args.output)
        backup_path = None
    else:
        output_path = csv_path.parent / f"{csv_path.stem}_modified{csv_path.suffix}"
        backup_path = None

    print(f"Loading CSV from: {csv_path}")
    fieldnames, records = load_csv(csv_path)
    print(f"Found {len(records)} records")

    # Find feedback column
    if args.feedback_col:
        feedback_col = args.feedback_col
    else:
        feedback_col = find_feedback_column(fieldnames)

    if not feedback_col or feedback_col not in fieldnames:
        print(f"Error: Could not find feedback column in CSV", file=sys.stderr)
        print(f"Available columns: {fieldnames}", file=sys.stderr)
        sys.exit(1)

    print(f"Feedback column: {feedback_col}")
    print(f"Instruction: {args.instruction}")
    print()

    # Process each record
    modified_count = 0

    for i, row in enumerate(records, 1):
        student_name = get_student_name(row)
        total_mark = get_total_mark(row)
        original_feedback = row.get(feedback_col, '')

        print(f"[{i}/{len(records)}] Processing: {student_name}...", end=' ')

        if not original_feedback.strip():
            print("(no feedback)")
            continue

        if args.dry_run:
            print("(dry run)")
            continue

        modified_feedback = modify_feedback(
            student_name=student_name,
            total_mark=total_mark,
            feedback=original_feedback,
            instruction=args.instruction,
            provider=provider,
            model=model
        )

        if modified_feedback != original_feedback:
            row[feedback_col] = modified_feedback
            modified_count += 1
            print("modified")
        else:
            print("unchanged")

    # Create backup if in-place
    if args.in_place and not args.dry_run:
        import shutil
        shutil.copy2(csv_path, backup_path)
        print(f"\nBackup created: {backup_path}")

    # Write output
    if not args.dry_run:
        print(f"\nWriting to: {output_path}")
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(records)

    print(f"\n✓ Processed {len(records)} records")
    print(f"✓ Modified {modified_count} feedback entries")
    if not args.dry_run:
        print(f"✓ Output saved to: {output_path}")


if __name__ == '__main__':
    main()
