#!/usr/bin/env python3
"""
Feedback Summarizer Utility

Takes a grades CSV file and summarizes each student's feedback card into
a single plain text paragraph suitable for gradebook comments.
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


SUMMARIZE_PROMPT = """You are a feedback summarizer. Your task is to condense the following detailed feedback into a single, concise plain text paragraph.

Requirements:
1. Write 3-4 sentences for most students
2. Focus primarily on MISTAKES and what they got wrong - be specific about the key issues
3. Also mention any notable POSITIVES or strengths (if any)
4. Start with the total mark
5. Use plain text only - no markdown, no bullet points, no special formatting
6. Be constructive and professional in tone
7. Do NOT include activity-by-activity breakdowns - summarize the overall patterns

IMPORTANT: For students with very low marks (below 40%), you may write 2-3 additional sentences to explain the major issues that caused the low score. This helps them understand what went wrong.

Student: {student_name}
Total Mark: {total_mark} / {total_possible}

Detailed Feedback:
{feedback}

Write a single paragraph summary (plain text only, 3-4 sentences, or 5-6 for very low marks):"""


def load_grades_csv(csv_path: Path) -> list:
    """Load grades CSV and return list of student records."""
    records = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
    return records


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


def summarize_feedback(student_name: str, total_mark: str, feedback: str,
                       provider: str, model: str = None, total_possible: int = 100) -> str:
    """Use LLM to summarize feedback into a single paragraph."""

    if not feedback or not feedback.strip():
        return f"{student_name} received {total_mark} marks. No detailed feedback available."

    prompt = SUMMARIZE_PROMPT.format(
        student_name=student_name,
        total_mark=total_mark,
        total_possible=total_possible,
        feedback=feedback
    )

    try:
        result = call_llm(
            prompt=prompt,
            provider=provider,
            model=model
        )

        # Clean up the result - remove any markdown or extra whitespace
        summary = result.strip()
        # Remove potential markdown artifacts
        summary = summary.replace('**', '').replace('*', '')
        summary = summary.replace('###', '').replace('##', '').replace('#', '')
        # Collapse multiple spaces/newlines into single spaces
        summary = ' '.join(summary.split())

        return summary
    except Exception as e:
        return f"{student_name} received {total_mark} marks. (Summary generation failed: {e})"


def get_student_name(row: dict) -> str:
    """Extract student name from row, handling various column formats."""
    # Try common column names
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


def get_feedback(row: dict) -> str:
    """Extract feedback from row."""
    for col in ['Feedback Card', 'Feedback', 'feedback', 'Comments', 'comments']:
        if col in row and row[col].strip():
            return row[col].strip()
    return ""


def main():
    parser = argparse.ArgumentParser(
        description='Summarize feedback cards into single paragraphs'
    )
    parser.add_argument(
        'csv_file',
        help='Path to the grades CSV file'
    )
    parser.add_argument(
        '--output',
        help='Output CSV file (default: <input>_summarized.csv)'
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
        '--total-marks',
        type=int,
        default=100,
        help='Total possible marks for the assignment (default: 100)'
    )
    parser.add_argument(
        '--feedback-col',
        help='Name of the feedback column (auto-detected if not specified)'
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
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = csv_path.parent / f"{csv_path.stem}_summarized{csv_path.suffix}"

    print(f"Loading grades from: {csv_path}")
    records = load_grades_csv(csv_path)
    print(f"Found {len(records)} students")

    if not records:
        print("No records found in CSV")
        sys.exit(1)

    # Process each student
    summaries = []

    for i, row in enumerate(records, 1):
        student_name = get_student_name(row)
        total_mark = get_total_mark(row)

        if args.feedback_col and args.feedback_col in row:
            feedback = row[args.feedback_col]
        else:
            feedback = get_feedback(row)

        print(f"[{i}/{len(records)}] Processing: {student_name} ({total_mark} marks)...", end=' ')

        if args.dry_run:
            summary = f"[DRY RUN] Would summarize {len(feedback)} chars of feedback"
            print("(dry run)")
        else:
            summary = summarize_feedback(
                student_name=student_name,
                total_mark=total_mark,
                feedback=feedback,
                provider=provider,
                model=model,
                total_possible=args.total_marks
            )
            print("done")

        summaries.append({
            'Student Name': student_name,
            'Total Mark': total_mark,
            'Summary': summary
        })

    # Write output CSV
    print(f"\nWriting summaries to: {output_path}")
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Student Name', 'Total Mark', 'Summary'],
                                quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(summaries)

    print(f"\n✓ Summarized {len(summaries)} feedback cards")
    print(f"✓ Output saved to: {output_path}")


if __name__ == '__main__':
    main()
