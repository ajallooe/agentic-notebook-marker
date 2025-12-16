#!/usr/bin/env python3
"""
Recalculate grades to reverse random_state related deductions and bonuses.

This script:
1. Finds original deduction/bonus values from normalized scoring files
2. Parses each student's feedback to identify which random_state codes were applied
3. Reverses those deductions/bonuses in the marks
4. Updates grades.csv and feedback files
"""

import csv
import json
import re
import sys
from pathlib import Path


def find_random_state_codes_in_scoring(normalized_dir):
    """Find random_state related codes and their values from scoring files."""
    codes = {}  # code -> {'type': 'mistake'|'positive', 'value': float, 'activity': str}

    for scoring_file in normalized_dir.glob("*_scoring.md"):
        activity = scoring_file.stem.replace('_scoring', '')  # e.g., A1

        with open(scoring_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find table rows - format: | CODE | description | frequency | severity | points |
        for line in content.split('\n'):
            if '|' not in line:
                continue

            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 4:
                continue

            code = parts[1].strip()

            # Match codes like M001, M002, P001, P002 etc.
            if not re.match(r'^[MP]\d+$', code):
                continue

            # Get description from column 2
            description = parts[2].strip().lower() if len(parts) > 2 else ''

            # Only include if the DESCRIPTION mentions random_state
            # (not just if random_state appears somewhere in the line)
            if 'random_state' not in description and 'random state' not in description:
                continue

            full_code = f"{activity}_{code}"

            # Try to find the points value in column 5 (suggested deduction/bonus)
            # Handle formats like: "2", "-5", "2 points", "3.5 marks"
            value = 0
            if len(parts) > 5:
                points_str = parts[5].strip()
                # Extract number from string like "2 points" or "-5"
                points_match = re.search(r'[-+]?(\d+\.?\d*)', points_str)
                if points_match:
                    value = float(points_match.group(1))

            # If value is 0, try to find it in the markdown section below
            if value == 0:
                # Look for patterns like: **M002 (No `random_state`)**: -10 points
                pattern = rf'\*\*{code}[^*]*\*\*[^-+\d]*([+-]?\d+\.?\d*)\s*(?:points?|bonus|marks?)'
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    value = abs(float(match.group(1).replace('+', '')))

            code_type = 'mistake' if code.startswith('M') else 'positive'
            codes[full_code] = {
                'type': code_type,
                'value': value,
                'activity': activity,
                'code': code,
                'description': description
            }

    return codes


def find_applied_codes_in_feedback(feedback_text, random_state_codes):
    """Find which random_state codes were applied to a student."""
    applied = []

    for full_code, info in random_state_codes.items():
        # Look for the code in the feedback
        # Patterns: `A1_M002`, A1_M002, (A1_M002), Mistake A1_M002
        patterns = [
            rf'`{full_code}`',
            rf'\b{full_code}\b',
            rf'\({full_code}\)',
            rf'{info["activity"]}_{info["code"]}',
        ]

        for pattern in patterns:
            if re.search(pattern, feedback_text, re.IGNORECASE):
                applied.append(full_code)
                break

    return applied


def adjust_marks(row, applied_codes, random_state_codes):
    """Adjust marks by reversing random_state deductions/bonuses."""
    adjustments = {'total': 0, 'by_activity': {}}

    for code in applied_codes:
        if code not in random_state_codes:
            continue

        info = random_state_codes[code]
        activity = info['activity']
        value = abs(info['value'])  # Use absolute value since sign varies in source
        code_type = info['type']

        if code_type == 'mistake':
            # Deduction was applied (student lost marks), reverse it (add back)
            # Student originally had marks deducted, so we ADD them back
            adjustment = value
        else:
            # Bonus was given (student gained marks), reverse it (subtract)
            # Student originally got bonus, so we SUBTRACT it
            adjustment = -value

        adjustments['total'] += adjustment
        if activity not in adjustments['by_activity']:
            adjustments['by_activity'][activity] = 0
        adjustments['by_activity'][activity] += adjustment

    return adjustments


def update_feedback_marks(feedback, adjustments, old_total, new_total):
    """Update marks in feedback text."""
    if not feedback:
        return feedback

    # Update Total Mark patterns
    # Pattern: **Total Mark**: 83 / 100
    # Pattern: Total Mark: 83 / 100
    # Pattern: Total Mark: 83/100
    patterns = [
        (rf'(\*\*Total Mark\*\*:\s*)(\d+\.?\d*)(\s*/\s*100)', r'\g<1>' + str(new_total) + r'\g<3>'),
        (rf'(Total Mark:\s*)(\d+\.?\d*)(\s*/\s*100)', r'\g<1>' + str(new_total) + r'\g<3>'),
        (rf'(Total Mark:\s*)(\d+\.?\d*)(/100)', r'\g<1>' + str(new_total) + r'\g<3>'),
    ]

    for pattern, replacement in patterns:
        feedback = re.sub(pattern, replacement, feedback, flags=re.IGNORECASE)

    # Update activity marks if we know them
    for activity, adjustment in adjustments.get('by_activity', {}).items():
        # Pattern: Activity 1: 6 / 20 or - Activity 1: 6 / 20
        activity_num = activity.replace('A', '')
        pattern = rf'(Activity\s*{activity_num}:\s*)(\d+\.?\d*)(\s*/\s*\d+)'

        def update_activity_mark(match):
            prefix = match.group(1)
            old_mark = float(match.group(2))
            suffix = match.group(3)
            max_mark = float(suffix.replace('/', '').strip())
            new_mark = min(max_mark, max(0, old_mark + adjustment))
            return f"{prefix}{new_mark}{suffix}"

        feedback = re.sub(pattern, update_activity_mark, feedback, flags=re.IGNORECASE)

    return feedback


def process_assignment(assignment_dir, dry_run=False):
    """Process an assignment to recalculate grades."""
    normalized_dir = assignment_dir / 'processed' / 'normalized'
    final_dir = assignment_dir / 'processed' / 'final'
    grades_csv = final_dir / 'grades.csv'

    if not normalized_dir.exists() or not grades_csv.exists():
        return 0, []

    # Find random_state codes
    random_state_codes = find_random_state_codes_in_scoring(normalized_dir)
    if not random_state_codes:
        return 0, []

    # Read grades.csv
    with open(grades_csv, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    reader = csv.DictReader(lines)
    fieldnames = reader.fieldnames
    rows = list(reader)

    changes = []

    for row in rows:
        student = row.get('Student Name', 'Unknown')
        feedback = row.get('Feedback Card', '')
        old_total = float(row.get('Total Mark', 0) or 0)

        if not feedback:
            continue

        # Find which random_state codes were applied
        applied_codes = find_applied_codes_in_feedback(feedback, random_state_codes)

        if not applied_codes:
            continue

        # Calculate adjustments
        adjustments = adjust_marks(row, applied_codes, random_state_codes)

        if adjustments['total'] == 0:
            continue

        # Calculate new total
        new_total = round(min(100, max(0, old_total + adjustments['total'])), 1)

        changes.append({
            'student': student,
            'old_total': old_total,
            'new_total': new_total,
            'adjustment': adjustments['total'],
            'codes': applied_codes,
        })

        if not dry_run:
            # Update row
            row['Total Mark'] = new_total

            # Update activity marks
            for activity, adj in adjustments['by_activity'].items():
                activity_col = f"Activity {activity.replace('A', '')}"
                if activity_col in row and row[activity_col]:
                    old_activity = float(row[activity_col])
                    # Get max marks for activity (usually 20)
                    new_activity = round(min(20, max(0, old_activity + adj)), 1)
                    row[activity_col] = new_activity

            # Update feedback
            row['Feedback Card'] = update_feedback_marks(
                feedback, adjustments, old_total, new_total
            )

            # Also update the feedback file
            feedback_file = final_dir / f"{student}_feedback.md"
            if feedback_file.exists():
                with open(feedback_file, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                new_content = update_feedback_marks(
                    file_content, adjustments, old_total, new_total
                )
                with open(feedback_file, 'w', encoding='utf-8') as f:
                    f.write(new_content)

    if changes and not dry_run:
        with open(grades_csv, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    return len(changes), changes


def main():
    dry_run = '--dry-run' in sys.argv
    verbose = '-v' in sys.argv or '--verbose' in sys.argv

    if dry_run:
        print("DRY RUN - No changes will be made\n")

    assignments_dir = Path(__file__).parent.parent / "assignments"
    total_changes = 0
    all_changes = []

    for assignment_dir in sorted(assignments_dir.iterdir()):
        if not assignment_dir.is_dir() or assignment_dir.name == "sample-assignment":
            continue

        count, changes = process_assignment(assignment_dir, dry_run)

        if count > 0:
            print(f"\n=== {assignment_dir.name} ===")
            print(f"  {count} students adjusted")

            if verbose:
                for change in changes:
                    print(f"    {change['student']}: {change['old_total']} -> {change['new_total']} ({change['adjustment']:+.1f})")
                    print(f"      Applied codes: {', '.join(change['codes'])}")

            total_changes += count
            all_changes.extend(changes)

    print(f"\n{'='*60}")
    print(f"Total: {total_changes} students had marks adjusted")

    if all_changes:
        total_adjustment = sum(c['adjustment'] for c in all_changes)
        avg_adjustment = total_adjustment / len(all_changes)
        print(f"Average adjustment: {avg_adjustment:+.1f} marks")

        # Count adjustments by direction
        increases = sum(1 for c in all_changes if c['adjustment'] > 0)
        decreases = sum(1 for c in all_changes if c['adjustment'] < 0)
        print(f"Mark increases: {increases}, Mark decreases: {decreases}")


if __name__ == '__main__':
    main()
