#!/usr/bin/env python3
"""
Extract Problem Context for Different-Problem Group Assignments

For assignments where each group solves a different problem, this utility
extracts problem.md and related context files from each group's submission directory.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional


def find_problem_description(group_dir: Path) -> Optional[str]:
    """
    Find and read problem.md in a group's submission directory.

    Args:
        group_dir: Path to group's submission directory

    Returns:
        Content of problem.md if found, None otherwise
    """
    problem_file = group_dir / "problem.md"

    if not problem_file.exists():
        return None

    try:
        with open(problem_file, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading {problem_file}: {e}", file=sys.stderr)
        return None


def find_supplementary_files(group_dir: Path, exclude_patterns: List[str] = None) -> List[str]:
    """
    Find supplementary files in group directory (excluding notebooks and problem.md).

    Args:
        group_dir: Path to group's submission directory
        exclude_patterns: List of file patterns to exclude (default: ['.ipynb', 'problem.md'])

    Returns:
        List of supplementary file paths relative to group_dir
    """
    if exclude_patterns is None:
        exclude_patterns = ['.ipynb', 'problem.md', '__pycache__', '.DS_Store']

    supplementary = []

    for item in group_dir.iterdir():
        if item.is_file():
            # Check if should be excluded
            should_exclude = False
            for pattern in exclude_patterns:
                if pattern in item.name:
                    should_exclude = True
                    break

            if not should_exclude:
                supplementary.append(str(item.relative_to(group_dir)))

    return sorted(supplementary)


def extract_all_problems(submissions_manifest: str, output_json: str, verbose: bool = False):
    """
    Extract problem contexts for all groups from submissions manifest.

    Args:
        submissions_manifest: Path to submissions_manifest.json
        output_json: Path to output JSON file with problem contexts
        verbose: Print detailed progress
    """
    manifest_path = Path(submissions_manifest)

    if not manifest_path.exists():
        print(f"Error: Submissions manifest not found: {submissions_manifest}", file=sys.stderr)
        return False

    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"Error reading manifest: {e}", file=sys.stderr)
        return False

    problem_contexts = {}
    total_groups = 0
    found_problems = 0

    for section, submissions in manifest.get('sections', {}).items():
        for submission in submissions:
            student_name = submission['student_name']
            submission_path = Path(submission['submission_path'])

            # For different-problem assignments, the submission path should be a directory
            # containing the notebook and problem files
            submission_dir = submission_path.parent

            total_groups += 1

            # Extract problem description
            problem_desc = find_problem_description(submission_dir)

            if problem_desc:
                found_problems += 1

                # Find supplementary files
                supplementary = find_supplementary_files(submission_dir)

                problem_contexts[student_name] = {
                    'problem_description': problem_desc,
                    'supplementary_files': supplementary,
                    'submission_dir': str(submission_dir)
                }

                if verbose:
                    print(f"Found problem for {student_name}:")
                    print(f"  - Problem description: {len(problem_desc)} chars")
                    print(f"  - Supplementary files: {len(supplementary)}")
                    if supplementary:
                        for supp in supplementary:
                            print(f"    - {supp}")
            else:
                if verbose:
                    print(f"Warning: No problem.md found for {student_name} in {submission_dir}", file=sys.stderr)

    # Save to JSON
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(output_path, 'w') as f:
            json.dump(problem_contexts, f, indent=2)

        print(f"\nExtracted problem contexts:")
        print(f"  Total groups: {total_groups}")
        print(f"  Problems found: {found_problems}")
        print(f"  Output: {output_json}")

        if found_problems < total_groups:
            print(f"\nWarning: Missing problem descriptions for {total_groups - found_problems} group(s)", file=sys.stderr)

        return True

    except Exception as e:
        print(f"Error writing output: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Extract problem contexts for different-problem group assignments"
    )
    parser.add_argument(
        '--manifest',
        required=True,
        help='Path to submissions_manifest.json'
    )
    parser.add_argument(
        '--output',
        required=True,
        help='Path to output JSON file'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print detailed progress'
    )

    args = parser.parse_args()

    success = extract_all_problems(
        args.manifest,
        args.output,
        verbose=args.verbose
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
