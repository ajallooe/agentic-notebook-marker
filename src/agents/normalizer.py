#!/usr/bin/env python3
"""
Normalizer Agent Wrapper

Aggregates marker assessments and creates unified scoring scheme.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Dict

# Import utilities
sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))
from system_config import get_default_provider, get_default_model


def load_prompt_template(assignment_type: str) -> str:
    """Load the appropriate normalizer prompt template."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_file = prompts_dir / f"normalizer_{assignment_type}.md"

    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_file}")

    with open(prompt_file, 'r') as f:
        return f.read()


def load_marker_assessments(markings_dir: Path, activity_id: str = None, pattern: str = "*.md") -> List[Dict]:
    """Load all marker assessments."""
    assessments = []

    if activity_id:
        # Load assessments for specific activity
        files = list(markings_dir.glob(f"*_{activity_id}.md"))
    else:
        # Load all assessments (free-form)
        files = list(markings_dir.glob(pattern))

    for file in sorted(files):
        # Extract student name from filename (handle names with spaces/underscores)
        # For structured: "Student Name_A1.md" -> "Student Name"
        # For free-form: "Student Name.md" -> "Student Name"
        stem = file.stem
        if activity_id:
            # Remove activity suffix: "Student Name_A1" -> "Student Name"
            student_name = stem.rsplit('_', 1)[0]
        else:
            student_name = stem

        with open(file, 'r') as f:
            content = f.read()

        assessments.append({
            'student_name': student_name,
            'file': str(file),
            'content': content
        })

    return assessments


def load_rubric(processed_dir: Path, activity_id: str = None) -> str:
    """Load rubric section."""
    rubric_file = processed_dir / "rubric.md"

    if not rubric_file.exists():
        return "No rubric file found."

    with open(rubric_file, 'r') as f:
        rubric_content = f.read()

    # For structured assignments, could extract activity-specific section
    # For now, return full rubric
    return rubric_content


def main():
    parser = argparse.ArgumentParser(
        description="Normalizer agent for aggregating marker assessments"
    )
    parser.add_argument(
        "--activity",
        help="Activity ID (e.g., A1) for structured assignments"
    )
    parser.add_argument(
        "--markings-dir",
        required=True,
        help="Directory containing marker assessments"
    )
    parser.add_argument(
        "--processed-dir",
        required=True,
        help="Processed directory for output files"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file for normalized scoring"
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
    parser.add_argument(
        "--api-model",
        help="Model for direct API calls (uses API instead of CLI for headless)"
    )

    args = parser.parse_args()

    try:
        # Load prompt template
        prompt_template = load_prompt_template(args.type)

        # Load marker assessments
        markings_dir = Path(args.markings_dir)
        assessments = load_marker_assessments(markings_dir, args.activity)

        if not assessments:
            print(f"✗ No marker assessments found in {markings_dir}", file=sys.stderr)
            sys.exit(1)

        print(f"Loaded {len(assessments)} marker assessments")

        # Format assessments for prompt
        assessments_text = []
        for i, assessment in enumerate(assessments, 1):
            assessments_text.append(f"## Student {i}: {assessment['student_name']}\n\n{assessment['content']}\n")

        marker_assessments = "\n---\n\n".join(assessments_text)

        # Load rubric
        processed_dir = Path(args.processed_dir)
        rubric = load_rubric(processed_dir, args.activity)

        # Substitute variables in prompt
        prompt = prompt_template.format(
            activity_id=args.activity or "N/A",
            num_students=len(assessments),
            marker_assessments=marker_assessments,
            rubric=rubric,
            rubric_section=rubric  # Same as rubric for now
        )

        # Save prompt for debugging
        prompt_debug_file = Path(args.output).with_suffix('.prompt.txt')
        with open(prompt_debug_file, 'w') as f:
            f.write(prompt)

        print(f"Normalizing assessments for {args.activity or 'entire assignment'}...")

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

        if args.api_model:
            cmd.extend(["--api-model", args.api_model])

        if args.stats_file:
            cmd.extend([
                "--stats-file", args.stats_file,
                "--stats-stage", "normalizer",
                "--stats-context", args.activity or "full"
            ])

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"✗ Normalization failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        # Write output to file (Python handles file writing since shell redirection is unreliable)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result.stdout)

        print(f"✓ Normalization complete for {args.activity or 'assignment'}")
        print(f"  Output: {args.output}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
