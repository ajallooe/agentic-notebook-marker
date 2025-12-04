#!/usr/bin/env python3
"""
Pattern Designer Agent Wrapper

Interactive agent that creates marking criteria and rubric.
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Import utilities
sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))
from system_config import get_default_provider, get_default_model


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
        "--different-problems",
        action="store_true",
        help="Groups solve different problems (abstract criteria needed)"
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve proposals without instructor interaction (headless mode)"
    )
    parser.add_argument(
        "--api-model",
        help="Model for direct API calls (uses API instead of CLI for headless)"
    )

    args = parser.parse_args()

    try:
        # Load prompt template
        prompt_template = load_prompt_template(args.type)

        # Load assignment overview
        with open(args.overview, 'r') as f:
            overview_content = f.read()

        # Load base notebook content if provided (structured assignments)
        base_notebook_content = ""
        if args.base_notebook and Path(args.base_notebook).exists():
            with open(args.base_notebook, 'r') as f:
                base_notebook_content = f.read()

        # Check for existing rubric
        rubric_file = Path(args.processed_dir) / "rubric.md"
        if rubric_file.exists():
            with open(rubric_file, 'r') as f:
                existing_rubric = f"Existing rubric:\n\n{f.read()}"
            rubric_status = "Rubric exists - please review and validate"
        else:
            existing_rubric = ""
            rubric_status = "No rubric provided - you must create one"

        # Determine if this is a different-problems assignment
        different_problems_note = ""
        if args.different_problems:
            different_problems_note = """
## IMPORTANT: Different-Problems Assignment

This is a **different-problems** assignment where each group solves a different problem.

**Your criteria MUST be abstract and problem-independent:**
- Focus on skills, techniques, and approaches (not specific problem details)
- Create criteria that can apply to ANY problem in this domain
- Examples of abstract criteria:
  - "Correctly applied data preprocessing techniques"
  - "Demonstrated understanding of model evaluation"
  - "Implemented appropriate error handling"
- Avoid problem-specific criteria like:
  - "Correctly predicted housing prices" (too specific)
  - "Used the Titanic dataset appropriately" (too specific)

The marker agents will receive each group's specific problem description along with your abstract criteria.
"""

        # Substitute variables in prompt
        prompt = prompt_template.format(
            base_notebook_path=args.base_notebook or "N/A (free-form assignment)",
            base_notebook_content=base_notebook_content if base_notebook_content else "N/A (free-form assignment)",
            assignment_overview=overview_content,
            rubric_status=rubric_status,
            existing_rubric=existing_rubric,
            additional_materials="" if args.type == "structured" else "See overview file above",
            processed_dir=args.processed_dir,
            different_problems_note=different_problems_note
        )

        # If auto-approve mode, modify prompt to not ask for approval
        if args.auto_approve:
            auto_approve_note = """

## AUTO-APPROVE MODE

**IMPORTANT**: This is running in AUTO-APPROVE mode. Do NOT wait for instructor approval.
- Create the rubric based on your best judgment
- Proceed immediately to create all activity criteria files
- Do NOT ask clarifying questions - make reasonable assumptions
- Complete ALL tasks and create ALL files without stopping
"""
            # Insert after the CRITICAL CONSTRAINTS section
            prompt = prompt.replace(
                "## Assignment Context",
                auto_approve_note + "\n## Assignment Context"
            )

        # Save prompt for debugging
        prompt_debug_file = Path(args.session_log).with_suffix('.prompt.txt')
        with open(prompt_debug_file, 'w') as f:
            f.write(prompt)

        # Pattern designer always uses interactive mode because it needs Write tools
        # to create rubric and criteria files. Auto-approve just skips permission prompts.
        mode = "interactive"

        print("="*70)
        if args.auto_approve:
            print("PATTERN DESIGNER - AUTO-APPROVE MODE")
        else:
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
        if not args.auto_approve:
            print("Please interact with the agent to complete the design process.")
            print("The agent will tell you when it's complete.")
        else:
            print("Running in auto-approve mode - no interaction required.")
        print("="*70)
        print()

        # Call LLM via unified caller
        llm_caller = Path(__file__).parent.parent / "llm_caller.sh"

        cmd = [
            str(llm_caller),
            "--prompt", prompt,
            "--mode", mode,
            "--provider", args.provider,
            "--output", args.session_log
        ]

        if args.model:
            cmd.extend(["--model", args.model])

        # NOTE: Pattern designer does NOT use --api-model even if provided.
        # The API caller is text-only and cannot create files.
        # Pattern designer needs CLI tools (Write) to create rubric and criteria files.

        # Pass --auto-approve to CLI for non-interactive permission handling
        if args.auto_approve:
            cmd.extend(["--auto-approve"])

        # Always use interactive TTY (pattern designer needs Write tools)
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
