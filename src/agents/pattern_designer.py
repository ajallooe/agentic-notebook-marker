#!/usr/bin/env python3
"""
Pattern Designer Agent Wrapper

Interactive agent that creates marking criteria and rubric.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def load_prompt_template(assignment_type: str) -> str:
    """Load the appropriate pattern designer prompt template."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_file = prompts_dir / f"pattern_designer_{assignment_type}.md"

    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_file}")

    with open(prompt_file, 'r') as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser(
        description="Pattern Designer agent for creating marking criteria"
    )
    parser.add_argument(
        "--base-notebook",
        help="Path to base notebook (structured assignments)"
    )
    parser.add_argument(
        "--overview",
        required=True,
        help="Path to assignment overview file"
    )
    parser.add_argument(
        "--processed-dir",
        required=True,
        help="Processed directory for output files"
    )
    parser.add_argument(
        "--session-log",
        required=True,
        help="Path to save session transcript"
    )
    parser.add_argument(
        "--provider",
        default="claude",
        help="LLM provider"
    )
    parser.add_argument(
        "--model",
        help="LLM model"
    )
    parser.add_argument(
        "--type",
        choices=["structured", "freeform"],
        default="structured",
        help="Assignment type"
    )

    args = parser.parse_args()

    try:
        # Load prompt template
        prompt_template = load_prompt_template(args.type)

        # Load assignment overview
        with open(args.overview, 'r') as f:
            overview_content = f.read()

        # Check for existing rubric
        rubric_file = Path(args.processed_dir) / "rubric.md"
        if rubric_file.exists():
            with open(rubric_file, 'r') as f:
                existing_rubric = f"Existing rubric:\n\n{f.read()}"
            rubric_status = "Rubric exists - please review and validate"
        else:
            existing_rubric = ""
            rubric_status = "No rubric provided - you must create one"

        # Substitute variables in prompt
        prompt = prompt_template.format(
            base_notebook_path=args.base_notebook or "N/A (free-form assignment)",
            assignment_overview=overview_content,
            rubric_status=rubric_status,
            existing_rubric=existing_rubric,
            additional_materials="" if args.type == "structured" else "See overview file above",
            processed_dir=args.processed_dir
        )

        # Save prompt for debugging
        prompt_debug_file = Path(args.session_log).with_suffix('.prompt.txt')
        with open(prompt_debug_file, 'w') as f:
            f.write(prompt)

        print("="*70)
        print("PATTERN DESIGNER - INTERACTIVE SESSION")
        print("="*70)
        print(f"Assignment type: {args.type}")
        print(f"Output directory: {args.processed_dir}")
        print(f"Session will be logged to: {args.session_log}")
        print()
        print("This agent will:")
        print("1. Analyze the assignment")
        print("2. Create or validate the rubric")
        print("3. Create detailed marking criteria")
        print()
        print("Please interact with the agent to complete the design process.")
        print("The agent will tell you when it's complete.")
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
            print(f"\n✗ Pattern design session ended with errors", file=sys.stderr)
            sys.exit(1)

        # Workaround: Codex workspace-write may create files in project root's processed/ dir
        # Move them to the correct assignment processed/ dir if needed
        import shutil
        import os

        project_root = Path(__file__).parent.parent.parent
        alt_processed = project_root / "processed"
        target_processed = Path(args.processed_dir)

        files_moved = []

        if alt_processed.exists() and alt_processed != target_processed:
            print("\nChecking for files created in alternate location...")

            # Move rubric.md if exists
            alt_rubric = alt_processed / "rubric.md"
            if alt_rubric.exists():
                target_rubric = target_processed / "rubric.md"
                shutil.move(str(alt_rubric), str(target_rubric))
                files_moved.append("rubric.md")
                print(f"  Moved: rubric.md")

            # Move activity criteria files if exist
            alt_activities = alt_processed / "activities"
            if alt_activities.exists():
                target_activities = target_processed / "activities"
                target_activities.mkdir(exist_ok=True)

                for criteria_file in alt_activities.glob("A*_criteria.md"):
                    target_file = target_activities / criteria_file.name
                    shutil.move(str(criteria_file), str(target_file))
                    files_moved.append(f"activities/{criteria_file.name}")
                    print(f"  Moved: activities/{criteria_file.name}")

            # Move marking_criteria.md for free-form assignments
            alt_marking = alt_processed / "marking_criteria.md"
            if alt_marking.exists():
                target_marking = target_processed / "marking_criteria.md"
                shutil.move(str(alt_marking), str(target_marking))
                files_moved.append("marking_criteria.md")
                print(f"  Moved: marking_criteria.md")

            if files_moved:
                print(f"\n✓ Moved {len(files_moved)} file(s) to correct location")

        print("\n" + "="*70)
        print("✓ Pattern design session complete")
        print("="*70)
        print()
        print("Please verify the following files were created:")
        print(f"  - {args.processed_dir}/rubric.md")
        if args.type == "structured":
            print(f"  - {args.processed_dir}/activities/A*_criteria.md")
        else:
            print(f"  - {args.processed_dir}/marking_criteria.md")
        print()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
