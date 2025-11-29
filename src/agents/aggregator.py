#!/usr/bin/env python3
"""
Aggregator Agent Wrapper

Interactive agent that creates final CSV from all feedback cards.
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Import utilities
sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))
from system_config import get_default_provider, get_default_model


def load_prompt_template() -> str:
    """Load the aggregator prompt template."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_file = prompts_dir / "aggregator.md"

    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_file}")

    with open(prompt_file, 'r') as f:
        return f.read()


def load_feedback_cards(feedback_dir: Path) -> tuple:
    """Load all feedback card files and return (count, content)."""
    cards = []
    for card_file in sorted(feedback_dir.glob("*_feedback.md")):
        try:
            with open(card_file, 'r', encoding='utf-8') as f:
                content = f.read()
            student_name = card_file.stem.replace('_feedback', '')
            cards.append(f"### {student_name}\n\n```\n{content}\n```")
        except Exception as e:
            print(f"Warning: Could not read {card_file}: {e}")

    return len(cards), "\n\n---\n\n".join(cards)


def read_csv_content(csv_path: str) -> str:
    """Read CSV file content with encoding fallback."""
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        with open(csv_path, 'r', encoding='latin-1') as f:
            return f.read()


def main():
    parser = argparse.ArgumentParser(
        description="Aggregator agent for creating final grades CSV"
    )
    parser.add_argument(
        "--assignment-name",
        required=True,
        help="Name of the assignment"
    )
    parser.add_argument(
        "--feedback-dir",
        required=True,
        help="Directory containing student feedback cards"
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for CSV and reports"
    )
    parser.add_argument(
        "--base-csv",
        help="Optional base CSV file (e.g., Moodle gradebook export)"
    )
    parser.add_argument(
        "--session-log",
        required=True,
        help="Path to save session transcript"
    )
    parser.add_argument(
        "--provider",
        default=get_default_provider(),
        help=f"LLM provider (default: {get_default_provider()} from config.yaml)"
    )
    parser.add_argument(
        "--model",
        default=get_default_model(),
        help="LLM model (default from config.yaml)"
    )
    parser.add_argument(
        "--type",
        choices=["structured", "freeform"],
        default="structured",
        help="Assignment type"
    )
    parser.add_argument(
        "--total-marks",
        type=int,
        default=100,
        help="Total marks for the assignment"
    )

    args = parser.parse_args()

    try:
        # Load prompt template
        prompt_template = load_prompt_template()

        # Load all feedback cards
        feedback_dir = Path(args.feedback_dir)
        total_students, feedback_cards_content = load_feedback_cards(feedback_dir)

        if total_students == 0:
            print(f"✗ No feedback cards found in {feedback_dir}", file=sys.stderr)
            sys.exit(1)

        # Check for base CSV and load content if provided
        base_csv_info = ""
        if args.base_csv and Path(args.base_csv).exists():
            base_csv_content = read_csv_content(args.base_csv)
            base_csv_info = f"Base CSV provided. Please merge student data with this file.\n\n```csv\n{base_csv_content}\n```"
        else:
            base_csv_info = "No base CSV provided. Create a new CSV from scratch."

        # Substitute variables in prompt
        prompt = prompt_template.format(
            assignment_name=args.assignment_name,
            assignment_type=args.type,
            total_students=total_students,
            total_marks=args.total_marks,
            feedback_cards_content=feedback_cards_content,
            base_csv_info=base_csv_info,
            output_path=args.output_dir
        )

        # Save prompt for debugging
        prompt_debug_file = Path(args.session_log).with_suffix('.prompt.txt')
        with open(prompt_debug_file, 'w') as f:
            f.write(prompt)

        print("="*70)
        print("AGGREGATOR - INTERACTIVE SESSION")
        print("="*70)
        print(f"Assignment: {args.assignment_name}")
        print(f"Students: {total_students}")
        print(f"Total marks: {args.total_marks}")
        print(f"Feedback cards: {feedback_dir}")
        print(f"Output directory: {args.output_dir}")
        if args.base_csv:
            print(f"Base CSV: {args.base_csv}")
        print()
        print("This agent will:")
        print("1. Read all feedback cards")
        print("2. Extract marks and feedback")
        print("3. Create properly formatted CSV")
        print("4. Generate statistics and reports")
        if args.base_csv:
            print("5. Merge with base CSV")
        print()
        print("Session will be logged to:", args.session_log)
        print("="*70)
        print()

        # Call LLM via unified caller in INTERACTIVE mode
        llm_caller = Path(__file__).parent.parent / "llm_caller.sh"

        cmd = [
            str(llm_caller),
            "--prompt", prompt,
            "--mode", "interactive",
            "--provider", args.provider,
            "--output", args.session_log
        ]

        if args.model:
            cmd.extend(["--model", args.model])

        # Inherit stdin/stdout/stderr to preserve TTY access for interactive CLI
        result = subprocess.run(cmd, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)

        if result.returncode != 0:
            print(f"\n✗ Aggregation session ended with errors", file=sys.stderr)
            sys.exit(1)

        print("\n" + "="*70)
        print("✓ Aggregation complete")
        print("="*70)
        print()
        print("Please verify the following files were created:")
        print(f"  - {args.output_dir}/grades.csv")
        print(f"  - {args.output_dir}/summary_report.txt (optional)")
        print(f"  - {args.output_dir}/discrepancies.txt (if base CSV provided)")
        print()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
