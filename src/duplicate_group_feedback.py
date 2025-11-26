#!/usr/bin/env python3
"""
Duplicate Group Feedback to Individual Students

For group assignments, this script creates individual feedback files
for each group member by symlinking or copying the group's feedback.
"""

import argparse
import sys
import os
from pathlib import Path
import shutil
import json

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.group_parser import parse_groups


def duplicate_feedback(groups_file: str, feedback_dir: str, use_symlinks: bool = True, verbose: bool = False):
    """
    Duplicate group feedback files for individual group members.

    Args:
        groups_file: Path to groups.csv
        feedback_dir: Directory containing group feedback files (processed/final/)
        use_symlinks: If True, create symlinks; if False, copy files
        verbose: Print detailed progress
    """
    # Parse groups
    groups = parse_groups(groups_file)
    if not groups:
        print("Error: No groups found", file=sys.stderr)
        return False

    feedback_path = Path(feedback_dir)
    if not feedback_path.exists():
        print(f"Error: Feedback directory not found: {feedback_dir}", file=sys.stderr)
        return False

    total_students = 0
    total_groups = len(groups)
    created_count = 0
    skipped_count = 0

    if verbose:
        print(f"Processing {total_groups} groups...")

    for group_name, members in groups.items():
        total_students += len(members)

        # Find group feedback file
        group_feedback = feedback_path / f"{group_name}_feedback.md"

        if not group_feedback.exists():
            print(f"Warning: Group feedback not found: {group_feedback}", file=sys.stderr)
            continue

        if verbose:
            print(f"\nGroup: {group_name} ({len(members)} members)")

        for student_name in members:
            student_feedback = feedback_path / f"{student_name}_feedback.md"

            # Skip if already exists (don't overwrite)
            if student_feedback.exists():
                if verbose:
                    print(f"  - {student_name}: already exists, skipping")
                skipped_count += 1
                continue

            try:
                if use_symlinks:
                    # Create relative symlink
                    os.symlink(group_feedback.name, student_feedback)
                    if verbose:
                        print(f"  - {student_name}: created symlink")
                else:
                    # Copy file
                    shutil.copy2(group_feedback, student_feedback)
                    if verbose:
                        print(f"  - {student_name}: copied feedback")

                created_count += 1

            except Exception as e:
                print(f"Error creating feedback for {student_name}: {e}", file=sys.stderr)

    # Summary
    print(f"\nSummary:")
    print(f"  Groups processed: {total_groups}")
    print(f"  Total students: {total_students}")
    print(f"  Feedback files created: {created_count}")
    if skipped_count > 0:
        print(f"  Files skipped (already exist): {skipped_count}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Duplicate group feedback to individual group members"
    )
    parser.add_argument(
        '--groups',
        required=True,
        help='Path to groups.csv file'
    )
    parser.add_argument(
        '--feedback-dir',
        required=True,
        help='Directory containing feedback files (processed/final/)'
    )
    parser.add_argument(
        '--copy',
        action='store_true',
        help='Copy files instead of creating symlinks'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print detailed progress'
    )

    args = parser.parse_args()

    use_symlinks = not args.copy

    success = duplicate_feedback(
        args.groups,
        args.feedback_dir,
        use_symlinks=use_symlinks,
        verbose=args.verbose
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
