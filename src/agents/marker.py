#!/usr/bin/env python3
"""
Marker Agent Wrapper

Loads student work, applies marker prompt, and saves assessment.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Import utilities
sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))
from quota_detector import is_quota_error, print_quota_warning
from system_config import get_default_provider, get_default_model


def load_prompt_template(assignment_type: str) -> str:
    """Load the appropriate marker prompt template."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_file = prompts_dir / f"marker_{assignment_type}.md"

    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_file}")

    with open(prompt_file, 'r') as f:
        return f.read()


def load_notebook(notebook_path: str) -> dict:
    """Load and return notebook JSON."""
    with open(notebook_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_student_work(notebook_path: str, activity_id: str = None) -> str:
    """
    Extract student work from notebook.

    For structured assignments with activity_id, extracts only that activity.
    For free-form, returns entire notebook.
    """
    notebook = load_notebook(notebook_path)

    if activity_id:
        # Use activity extractor for structured assignments
        extractor_path = Path(__file__).parent.parent / "extract_activities.py"
        result = subprocess.run([
            sys.executable,
            str(extractor_path),
            notebook_path,
            "--output", "/tmp/extracted_activities"
        ], capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"Activity extraction failed: {result.stderr}")

        # Load extracted activity
        activity_file = Path(f"/tmp/extracted_activities/{activity_id}.json")
        if activity_file.exists():
            with open(activity_file, 'r') as f:
                activity_data = json.load(f)
                # Format cells for display
                cells_text = []
                for cell in activity_data['cells']:
                    cell_type = cell['cell_type']
                    source = cell['source']
                    cells_text.append(f"[{cell_type}]\n{source}\n")
                return "\n".join(cells_text)
        else:
            raise FileNotFoundError(f"Activity {activity_id} not found in submission")
    else:
        # Return entire notebook formatted for display
        cells_text = []
        for i, cell in enumerate(notebook.get('cells', [])):
            cell_type = cell.get('cell_type', 'unknown')
            source = cell.get('source', '')
            if isinstance(source, list):
                source = ''.join(source)
            cells_text.append(f"Cell {i} [{cell_type}]:\n{source}\n")
        return "\n".join(cells_text)


def load_marking_criteria(criteria_path: str) -> str:
    """Load marking criteria for this activity."""
    if Path(criteria_path).exists():
        with open(criteria_path, 'r') as f:
            return f.read()
    return "No specific criteria provided."


def load_problem_context(problem_contexts_path: str, student_name: str) -> str:
    """
    Load problem-specific context for different-problem assignments.

    Args:
        problem_contexts_path: Path to problem_contexts.json
        student_name: Student/group name

    Returns:
        Formatted problem context string or empty if not found
    """
    if not Path(problem_contexts_path).exists():
        return ""

    try:
        with open(problem_contexts_path, 'r') as f:
            contexts = json.load(f)

        if student_name in contexts:
            ctx = contexts[student_name]
            problem_desc = ctx.get('problem_description', '')
            supplementary = ctx.get('supplementary_files', [])

            context_parts = [
                "## Problem-Specific Context",
                "",
                "This group was assigned the following problem:",
                "",
                problem_desc
            ]

            if supplementary:
                context_parts.extend([
                    "",
                    "### Supplementary Files",
                    "The following supplementary files were provided with the problem:",
                    ""
                ])
                for supp_file in supplementary:
                    context_parts.append(f"- {supp_file}")

            return "\n".join(context_parts)
        else:
            return ""
    except Exception as e:
        print(f"Warning: Failed to load problem context: {e}", file=sys.stderr)
        return ""


def main():
    parser = argparse.ArgumentParser(
        description="Marker agent for evaluating student submissions"
    )
    parser.add_argument(
        "--activity",
        help="Activity ID (e.g., A1) for structured assignments"
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
        "--criteria",
        help="Path to marking criteria file"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file for marking assessment"
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
        "--problem-context",
        help="Path to problem_contexts.json for different-problem assignments"
    )
    parser.add_argument(
        "--stats-file",
        help="Path to append token usage stats (JSONL format)"
    )

    args = parser.parse_args()

    try:
        # Load prompt template
        prompt_template = load_prompt_template(args.type)

        # Extract student work
        student_work = extract_student_work(args.submission, args.activity)

        # Load marking criteria if provided
        if args.criteria and Path(args.criteria).exists():
            criteria = load_marking_criteria(args.criteria)
        else:
            # Try to find criteria file based on activity
            if args.activity:
                processed_dir = Path(args.submission).parent.parent / "processed"
                criteria_file = processed_dir / "activities" / f"{args.activity}_criteria.md"
                if criteria_file.exists():
                    criteria = load_marking_criteria(str(criteria_file))
                else:
                    criteria = f"No criteria file found for {args.activity}"
            else:
                criteria = "No marking criteria provided."

        # Load problem context for different-problem assignments
        problem_context = ""
        if args.problem_context:
            problem_context = load_problem_context(args.problem_context, args.student)

        # Substitute variables in prompt
        prompt = prompt_template.format(
            activity_id=args.activity or "N/A",
            student_name=args.student,
            submission_path=args.submission,
            student_work=student_work,
            marking_criteria=criteria,
            problem_context=problem_context
        )

        # Save prompt for debugging
        prompt_debug_file = Path(args.output).with_suffix('.prompt.txt')
        with open(prompt_debug_file, 'w') as f:
            f.write(prompt)

        # Call LLM via unified caller
        llm_caller = Path(__file__).parent.parent / "llm_caller.sh"

        cmd = [
            str(llm_caller),
            "--prompt", prompt,
            "--mode", "headless",
            "--provider", args.provider,
            "--auto-approve"  # Skip permission prompts for automated marking
        ]

        if args.model:
            cmd.extend(["--model", args.model])

        if args.stats_file:
            context = f"{args.student}"
            if args.activity:
                context += f"/{args.activity}"
            cmd.extend([
                "--stats-file", args.stats_file,
                "--stats-stage", "marker",
                "--stats-context", context
            ])

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            # Check if this is a quota/rate limit error
            error_output = result.stderr + result.stdout
            quota_detected = is_quota_error(error_output, args.provider)

            if quota_detected:
                print_quota_warning(args.provider, error_output)
            else:
                print(f"Error: LLM call failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        # Write output to file (Python handles file writing since shell redirection is unreliable)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result.stdout)

        print(f"✓ Marking complete for {args.student} ({args.activity or 'full submission'})")
        print(f"  Output: {args.output}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
