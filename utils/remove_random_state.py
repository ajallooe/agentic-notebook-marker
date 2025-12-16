#!/usr/bin/env python3
"""
Remove random_state related content from feedback in grades.csv files.

This script removes all mentions of random_state (both positive and negative)
from the Feedback Card column in grades.csv files.
"""

import csv
import re
import sys
from pathlib import Path


def remove_random_state_content(text):
    """Remove random_state related content from feedback text."""
    if not text:
        return text

    # Patterns to remove (sentences/clauses mentioning random_state)
    patterns = [
        # Deduction lines like "- `A1_M002` (Reproducibility Issue): -1 point. The... random_state."
        r'-\s*`A\d+_M\d+`[^.]*random_state[^.]*\.\s*',
        # Lines like "A 1-mark deduction was applied for `A1_M002` because `random_state`..."
        r'A \d+-mark deduction was applied for `A\d+_M\d+` because `random_state`[^.]*\.\s*',
        # Sentences about using random_state being good
        r'[^.]*correctly\s+(?:implemented|used|includes?)\s+[^.]*random_state[^.]*\.\s*',
        r'[^.]*using\s+`random_state`\s+for\s+reproducibility[^.]*\.\s*',
        r'[^.]*setting\s+a?\s*`?random_state`?\s+for\s+reproducibility[^.]*\.\s*',
        # Bullet points about random_state
        r'[•\-\*]\s*[^•\-\*\n]*random_state[^•\-\*\n]*\n?',
        # "Gained X mark for using random_state"
        r'[Gg]ained\s+\d+\s+marks?\s+for\s+(?:using\s+)?`?random_state`?[^,.]*[,.]?\s*',
        # Activity breakdowns mentioning random_state deductions
        r'-\s*\d+\s*\([^)]*random_state[^)]*\)\s*',
        # No random_state deductions
        r'-\s*\d+\s*\(A\d+_M\d+:\s*[Nn]o\s+random_state\)\s*',
        # "The `train_test_split` call was missing `random_state`."
        r'The\s+`train_test_split`\s+call\s+was\s+missing\s+`random_state`\.\s*',
        # "because you didn't set a `random_state`..."
        r"because\s+you\s+didn't\s+set\s+a\s+`random_state`[^.]*\.?\s*",
        # Recommendations about random_state
        r'[Aa]lways\s+include\s+`random_state`[^.]*\.\s*',
        r'[Aa]lways\s+set\s+`random_state`[^.]*\.\s*',
        # Generic sentences containing random_state as a best practice
        r'[^.]*`random_state`[^.]*reproducib[^.]*\.\s*',
    ]

    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    # Clean up artifacts
    # Remove empty bullet points
    text = re.sub(r'[•\-\*]\s*\n', '\n', text)
    # Remove multiple consecutive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove empty parentheses
    text = re.sub(r'\(\s*\)', '', text)
    # Clean up double spaces
    text = re.sub(r'  +', ' ', text)

    return text


def process_grades_csv(grades_path, dry_run=False):
    """Process a grades.csv file to remove random_state content."""
    with open(grades_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'random_state' not in content.lower():
        return 0

    # Read CSV
    lines = content.split('\n')
    reader = csv.DictReader(lines)
    fieldnames = reader.fieldnames
    rows = list(reader)

    changes = 0
    for row in rows:
        feedback = row.get('Feedback Card', '')
        if feedback and 'random_state' in feedback.lower():
            new_feedback = remove_random_state_content(feedback)
            if new_feedback != feedback:
                changes += 1
                if not dry_run:
                    row['Feedback Card'] = new_feedback

    if changes > 0 and not dry_run:
        # Write back
        with open(grades_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    return changes


def main():
    dry_run = '--dry-run' in sys.argv

    if dry_run:
        print("DRY RUN - No changes will be made\n")

    # Process all assignments
    assignments_dir = Path(__file__).parent.parent / "assignments"
    total_changes = 0

    for assignment_dir in sorted(assignments_dir.iterdir()):
        if not assignment_dir.is_dir() or assignment_dir.name == "sample-assignment":
            continue

        grades_csv = assignment_dir / "processed" / "final" / "grades.csv"
        if not grades_csv.exists():
            continue

        changes = process_grades_csv(grades_csv, dry_run)
        if changes > 0:
            print(f"{assignment_dir.name}: {changes} feedback entries modified")
            total_changes += changes

    print(f"\nTotal: {total_changes} feedback entries modified")


if __name__ == '__main__':
    main()
