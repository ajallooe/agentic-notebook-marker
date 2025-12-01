#!/usr/bin/env python3
"""
Force Complete Utility

Generates zero-mark feedback cards for students whose marking failed,
allowing the marking process to complete despite errors.

This is useful when:
- You need to submit grades by a deadline
- Some students had errors that can't be quickly resolved
- You want to continue with aggregation for successful students
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional


def load_manifest(manifest_path: Path) -> Dict:
    """Load the submissions manifest."""
    if not manifest_path.exists():
        return {"submissions": []}
    with open(manifest_path) as f:
        return json.load(f)


def get_completed_students(final_dir: Path) -> Set[str]:
    """Get set of students who have completed feedback files."""
    completed = set()
    if final_dir.exists():
        for f in final_dir.glob("*_feedback.md"):
            # Extract student name from filename
            name = f.stem.replace("_feedback", "")
            completed.add(name)
    return completed


def get_error_info(logs_dir: Path, student_name: str) -> str:
    """Try to extract error information for a student from logs."""
    error_info = []

    # Check unifier logs
    unifier_logs = logs_dir / "unifier_logs"
    if unifier_logs.exists():
        for results_dir in unifier_logs.iterdir():
            if not results_dir.is_dir():
                continue
            for task_dir in results_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                # Check if this task is for our student
                if student_name.lower() in task_dir.name.lower():
                    stderr_file = task_dir / "stderr"
                    if stderr_file.exists() and stderr_file.stat().st_size > 0:
                        content = stderr_file.read_text(errors='replace')
                        # Extract meaningful error messages
                        for line in content.split('\n'):
                            line_lower = line.lower()
                            if 'yolo mode' in line_lower or 'cached credentials' in line_lower:
                                continue
                            if any(p in line_lower for p in ['error', 'failed', 'quota', 'limit', 'timeout']):
                                error_info.append(line.strip())

    # Check marker logs
    marker_logs = logs_dir / "marker_logs"
    if marker_logs.exists():
        for results_dir in marker_logs.iterdir():
            if not results_dir.is_dir():
                continue
            for task_dir in results_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                if student_name.lower() in task_dir.name.lower():
                    stderr_file = task_dir / "stderr"
                    if stderr_file.exists() and stderr_file.stat().st_size > 0:
                        content = stderr_file.read_text(errors='replace')
                        for line in content.split('\n'):
                            line_lower = line.lower()
                            if 'yolo mode' in line_lower or 'cached credentials' in line_lower:
                                continue
                            if any(p in line_lower for p in ['error', 'failed', 'quota', 'limit', 'timeout']):
                                error_info.append(line.strip())

    if error_info:
        # Deduplicate and limit
        unique_errors = list(dict.fromkeys(error_info))[:5]
        return "\n".join(f"  - {e}" for e in unique_errors)

    return "  - Error details not available (check logs manually)"


def generate_zero_feedback(
    student_name: str,
    assignment_name: str,
    total_marks: float,
    error_reason: str,
    assignment_type: str = "structured"
) -> str:
    """Generate a zero-mark feedback card for a failed student."""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    feedback = f"""# ASSIGNMENT FEEDBACK - {student_name}

## Assignment: {assignment_name}

---

## ⚠️ MARKING ERROR - REQUIRES MANUAL REVIEW

**Total Mark: 0 / {total_marks}**

This submission could not be automatically marked due to system errors.
The student's work has NOT been evaluated.

### Error Information

**Timestamp:** {timestamp}
**Reason:** Marking system encountered errors during processing

**Error Details:**
{error_reason}

---

## IMPORTANT NOTICE FOR INSTRUCTOR

This feedback card was auto-generated because the marking system failed
to process this student's submission. Please:

1. **Review the submission manually** at your earliest convenience
2. **Update the grade** once manual review is complete
3. **Replace this feedback** with proper assessment comments

The zero mark is a placeholder and should be updated after manual review.

---

## Student Information

- **Student Name:** {student_name}
- **Assignment:** {assignment_name}
- **Auto-Generated:** {timestamp}
- **Status:** REQUIRES MANUAL REVIEW

---

*This feedback was auto-generated by the force-complete process.*
*The submission was not evaluated due to marking system errors.*
"""

    return feedback


def force_complete_marking(
    assignment_dir: Path,
    total_marks: float = 100,
    assignment_type: str = "structured",
    dry_run: bool = False
) -> Dict:
    """
    Generate zero-mark feedback for all students missing feedback files.

    Returns:
        Dict with results: created files, skipped students, errors
    """
    processed_dir = assignment_dir / "processed"
    final_dir = processed_dir / "final"
    logs_dir = processed_dir / "logs"
    manifest_path = processed_dir / "submissions_manifest.json"

    assignment_name = assignment_dir.name

    results = {
        "created": [],
        "skipped": [],
        "errors": [],
        "total_marks": total_marks,
        "assignment_name": assignment_name,
    }

    # Load manifest
    manifest = load_manifest(manifest_path)
    all_students = {s["student_name"] for s in manifest.get("submissions", [])}

    if not all_students:
        results["errors"].append("No students found in manifest")
        return results

    # Get already completed students
    completed = get_completed_students(final_dir)

    # Find missing students
    missing = all_students - completed

    if not missing:
        print("All students have feedback files. Nothing to force-complete.")
        return results

    print(f"\nFound {len(missing)} student(s) missing feedback:")
    for name in sorted(missing):
        print(f"  - {name}")
    print()

    # Create final directory if needed
    if not dry_run:
        final_dir.mkdir(parents=True, exist_ok=True)

    # Generate feedback for each missing student
    for student_name in sorted(missing):
        # Get error info
        error_reason = get_error_info(logs_dir, student_name)

        # Generate feedback
        feedback = generate_zero_feedback(
            student_name=student_name,
            assignment_name=assignment_name,
            total_marks=total_marks,
            error_reason=error_reason,
            assignment_type=assignment_type
        )

        # Write feedback file
        feedback_path = final_dir / f"{student_name}_feedback.md"

        if dry_run:
            print(f"[DRY RUN] Would create: {feedback_path}")
            results["created"].append(str(feedback_path))
        else:
            try:
                feedback_path.write_text(feedback)
                print(f"✓ Created zero-mark feedback: {feedback_path.name}")
                results["created"].append(str(feedback_path))
            except Exception as e:
                error_msg = f"Failed to create {feedback_path}: {e}"
                print(f"✗ {error_msg}")
                results["errors"].append(error_msg)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Generate zero-mark feedback for students with marking errors"
    )
    parser.add_argument(
        "assignment_dir",
        help="Path to the assignment directory"
    )
    parser.add_argument(
        "--total-marks",
        type=float,
        default=100,
        help="Total marks for the assignment (default: 100)"
    )
    parser.add_argument(
        "--type",
        choices=["structured", "freeform"],
        default="structured",
        help="Assignment type (default: structured)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without creating files"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    assignment_dir = Path(args.assignment_dir)
    if not assignment_dir.exists():
        print(f"Error: Assignment directory not found: {assignment_dir}", file=sys.stderr)
        sys.exit(1)

    print("=" * 70)
    print("FORCE COMPLETE - Generating Zero-Mark Feedback")
    print("=" * 70)
    print(f"\nAssignment: {assignment_dir.name}")
    print(f"Total Marks: {args.total_marks}")
    if args.dry_run:
        print("Mode: DRY RUN (no files will be created)")
    print()

    results = force_complete_marking(
        assignment_dir=assignment_dir,
        total_marks=args.total_marks,
        assignment_type=args.type,
        dry_run=args.dry_run
    )

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Feedback files created: {len(results['created'])}")
    print(f"  Errors: {len(results['errors'])}")

    if results['created']:
        print("\n⚠️  These students received ZERO marks and require manual review:")
        for f in results['created']:
            print(f"    - {Path(f).stem.replace('_feedback', '')}")

    if args.json:
        print("\n" + json.dumps(results, indent=2))

    if results['errors']:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
