#!/usr/bin/env python3
"""
Unifier Agent Wrapper

Applies approved marking scheme and creates final feedback for a student.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

# Import utilities
sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))
from system_config import get_default_provider, get_default_model


def load_prompt_template() -> str:
    """Load the unifier prompt template."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_file = prompts_dir / "unifier.md"

    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_file}")

    with open(prompt_file, 'r') as f:
        return f.read()


def load_approved_scheme(scheme_path: str) -> Dict:
    """Load the instructor-approved marking scheme."""
    with open(scheme_path, 'r') as f:
        return json.load(f)


def load_previous_assessments(markings_dir: Path, student_name: str, assignment_type: str) -> str:
    """Load all previous marker and normalizer assessments for this student."""
    assessments = []

    if assignment_type == "structured":
        # Load all activity assessments for this student
        marker_files = sorted(markings_dir.glob(f"{student_name}_A*.md"))
        for file in marker_files:
            activity = file.stem.split('_')[1]  # Extract A1, A2, etc.
            with open(file, 'r') as f:
                assessments.append(f"### Marker Assessment - {activity}\n\n{f.read()}\n")
    else:
        # Load single assessment for free-form
        marker_file = markings_dir / f"{student_name}.md"
        if marker_file.exists():
            with open(marker_file, 'r') as f:
                assessments.append(f"### Marker Assessment\n\n{f.read()}\n")

    return "\n---\n\n".join(assessments) if assessments else "No previous assessments found."


def load_student_notebook(notebook_path: str) -> str:
    """Load and format student's complete notebook."""
    with open(notebook_path, 'r') as f:
        notebook = json.load(f)

    cells_text = []
    for i, cell in enumerate(notebook.get('cells', [])):
        cell_type = cell.get('cell_type', 'unknown')
        source = cell.get('source', '')
        if isinstance(source, list):
            source = ''.join(source)
        cells_text.append(f"Cell {i} [{cell_type}]:\n{source}\n")

    return "\n".join(cells_text)


def main():
    parser = argparse.ArgumentParser(
        description="Unifier agent for creating final student feedback"
    )
    parser.add_argument(
        "--student",
        required=True,
        help="Student name"
    )
    parser.add_argument(
        "--submission",
        required=True,
        help="Path to student submission notebook"
    )
    parser.add_argument(
        "--scheme",
        required=True,
        help="Path to approved marking scheme JSON"
    )
    parser.add_argument(
        "--markings-dir",
        required=True,
        help="Directory containing previous assessments"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file for final feedback"
    )
    default_provider = get_default_provider()
    default_model = get_default_model()
    parser.add_argument(
        "--provider",
        default=default_provider,
        required=default_provider is None,
        help=f"LLM provider: claude, gemini, or codex (default: {default_provider or 'required'})"
    )
    parser.add_argument(
        "--model",
        default=default_model,
        help=f"LLM model (default: {default_model or 'provider default'})"
    )
    parser.add_argument(
        "--type",
        choices=["structured", "freeform"],
        default="structured",
        help="Assignment type"
    )
    parser.add_argument(
        "--stats-file",
        help="Path to append token usage stats (JSONL format)"
    )

    args = parser.parse_args()

    try:
        # Load prompt template
        prompt_template = load_prompt_template()

        # Load approved marking scheme
        approved_scheme = load_approved_scheme(args.scheme)
        scheme_text = json.dumps(approved_scheme, indent=2)

        # Load previous assessments
        markings_dir = Path(args.markings_dir)
        previous_assessments = load_previous_assessments(markings_dir, args.student, args.type)

        # Load student's complete notebook
        student_notebook = load_student_notebook(args.submission)

        # Determine assignment-specific calculation format
        if args.type == "structured":
            calculation_format = """
Activity 1: [marks] / [total]
Activity 2: [marks] / [total]
...
Total: [sum] / [total_available]
"""
            structured_output = """
**Activity Breakdown**:
- Activity 1: [X] / [Total]
- Activity 2: [X] / [Total]
...
"""
        else:
            calculation_format = """
Component 1: [marks] / [total]
Component 2: [marks] / [total]
...
Total: [sum] / [total_available]
"""
            structured_output = """
**Component Breakdown**:
- Component 1: [X] / [Total]
- Component 2: [X] / [Total]
...
"""

        # Substitute variables in prompt
        prompt = prompt_template.format(
            student_name=args.student,
            submission_path=args.submission,
            approved_scheme=scheme_text,
            previous_assessments=previous_assessments,
            student_notebook=student_notebook,
            assignment_type_specific_calculation=calculation_format,
            structured_output=structured_output,
            marks_breakdown="[Activity/Component marks listed here]"
        )

        # Save prompt for debugging
        prompt_debug_file = Path(args.output).with_suffix('.prompt.txt')
        with open(prompt_debug_file, 'w') as f:
            f.write(prompt)

        print(f"Creating final feedback for {args.student}...")

        # Call LLM via unified caller
        llm_caller = Path(__file__).parent.parent / "llm_caller.sh"

        cmd = [
            str(llm_caller),
            "--prompt", prompt,
            "--mode", "headless",
            "--provider", args.provider,
            "--auto-approve"  # Skip permission prompts for automated operation
        ]

        if args.model:
            cmd.extend(["--model", args.model])

        if args.stats_file:
            cmd.extend([
                "--stats-file", args.stats_file,
                "--stats-stage", "unifier",
                "--stats-context", args.student
            ])

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"✗ Unifier failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        # Write output to file (Python handles file writing since shell redirection is unreliable)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result.stdout)

        print(f"✓ Final feedback created for {args.student}")
        print(f"  Output: {args.output}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
