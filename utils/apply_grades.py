#!/usr/bin/env python3
"""
Direct Grades Applier - Applies grades.csv to gradebooks without LLM.

Uses direct name matching after fix_grades.py has standardized names.
Supports both email-based and name-based gradebook formats.
"""

import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path


def load_csv_with_bom(path, encoding='utf-8'):
    """Load CSV handling potential BOM characters."""
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(path, 'r', encoding='latin-1') as f:
            content = f.read()

    # Strip BOM if present
    if content.startswith('\ufeff'):
        content = content[1:]

    lines = content.split('\n')
    reader = csv.DictReader(lines)
    return list(reader), reader.fieldnames


def normalize_name(name):
    """Normalize a name for matching."""
    if not name:
        return ''
    # Remove extra whitespace
    name = ' '.join(name.split())
    # Remove common prefixes
    name = re.sub(r'^Lab\s*\d+[^a-zA-Z]*', '', name, flags=re.IGNORECASE)
    return name.strip().lower()


def get_gradebook_students(gradebook_path):
    """Get students from gradebook with their identifiers."""
    rows, fieldnames = load_csv_with_bom(gradebook_path)
    students = {}

    # Detect format - email-based or name-based
    has_email = 'Email address' in fieldnames or 'Email' in fieldnames
    has_first_last = 'First name' in fieldnames and 'Last name' in fieldnames

    for row in rows:
        if has_email:
            email_col = 'Email address' if 'Email address' in row else 'Email'
            email = row.get(email_col, '').strip()
            if email:
                # Extract name from first/last columns or email prefix
                if has_first_last:
                    first = row.get('First name', '').strip()
                    last = row.get('Last name', '').strip()
                    full_name = f"{first} {last}".strip()
                else:
                    full_name = email.split('@')[0]

                students[email] = {
                    'email': email,
                    'name': full_name,
                    'name_normalized': normalize_name(full_name),
                    'first': row.get('First name', '').strip() if has_first_last else '',
                    'last': row.get('Last name', '').strip() if has_first_last else '',
                    'row': row
                }
        elif has_first_last:
            first = row.get('First name', '').strip()
            last = row.get('Last name', '').strip()
            full_name = f"{first} {last}".strip()
            if full_name:
                students[full_name] = {
                    'name': full_name,
                    'name_normalized': normalize_name(full_name),
                    'first': first,
                    'last': last,
                    'row': row
                }

    return students, rows, fieldnames, has_email


def load_grades(grades_path):
    """Load grades from grades.csv."""
    rows, fieldnames = load_csv_with_bom(grades_path)
    grades = {}

    for row in rows:
        name = row.get('Student Name', '').strip()
        if not name or name.lower() == 'student name':
            continue

        total_mark = row.get('Total Mark', '')
        feedback = row.get('Feedback Card', '')

        grades[name] = {
            'name': name,
            'name_normalized': normalize_name(name),
            'total_mark': total_mark,
            'feedback': feedback,
            'row': row
        }

    return grades


def find_match(grades_name, gradebook_students, has_email):
    """Find matching gradebook student for a grades.csv name."""
    normalized = normalize_name(grades_name)

    # Skip invalid names
    if not normalized or normalized in ['student', 'student name']:
        return None

    for key, student in gradebook_students.items():
        # Try exact normalized match
        if normalized == student['name_normalized']:
            return key

        # Try first + last combined match
        first_last = normalize_name(f"{student['first']}{student['last']}")
        if normalized.replace(' ', '') == first_last.replace(' ', ''):
            return key

        # Try first name only match (for truncated names)
        first_norm = normalize_name(student['first'])
        if first_norm and len(first_norm) >= 4:
            if normalized == first_norm or normalized.startswith(first_norm):
                return key

        # Try partial match on name components
        name_parts = normalized.split()
        student_parts = student['name_normalized'].split()
        if len(name_parts) >= 2 and len(student_parts) >= 2:
            if name_parts[0] == student_parts[0] and name_parts[-1] == student_parts[-1]:
                return key

    return None


def apply_grades(assignment_dir, gradebook_paths, dry_run=False):
    """Apply grades from grades.csv to gradebooks."""
    assignment_name = os.path.basename(assignment_dir)
    grades_path = os.path.join(assignment_dir, 'processed', 'final', 'grades.csv')

    if not os.path.exists(grades_path):
        print(f"ERROR: grades.csv not found: {grades_path}")
        return None

    grades = load_grades(grades_path)
    print(f"\nAssignment: {assignment_name}")
    print(f"Loaded {len(grades)} students from grades.csv")

    results = {
        'assignment': assignment_name,
        'gradebooks': [],
        'total_matched': 0,
        'total_unmatched': 0,
        'unmatched_grades': [],
        'unmatched_gradebook': []
    }

    for gradebook_path in gradebook_paths:
        if not os.path.exists(gradebook_path):
            print(f"WARNING: Gradebook not found: {gradebook_path}")
            continue

        print(f"\nProcessing: {os.path.basename(gradebook_path)}")

        students, rows, fieldnames, has_email = get_gradebook_students(gradebook_path)
        print(f"  Found {len(students)} students in gradebook")

        # Track matches
        matched = 0
        unmatched_grades = []
        matched_gradebook = set()

        # Build mapping
        for grades_name, grade_info in grades.items():
            match_key = find_match(grades_name, students, has_email)

            if match_key:
                matched += 1
                matched_gradebook.add(match_key)
                students[match_key]['total_mark'] = grade_info['total_mark']
                students[match_key]['feedback'] = grade_info['feedback']
            else:
                unmatched_grades.append(grades_name)

        # Find unmatched gradebook students
        unmatched_gb = []
        for key, student in students.items():
            if key not in matched_gradebook:
                unmatched_gb.append(student['name'])

        print(f"  Matched: {matched}")
        print(f"  Unmatched (grades.csv): {len(unmatched_grades)}")
        print(f"  Unmatched (gradebook): {len(unmatched_gb)}")

        if unmatched_grades:
            print(f"  Unmatched grades names: {unmatched_grades[:5]}{'...' if len(unmatched_grades) > 5 else ''}")

        results['total_matched'] += matched
        results['total_unmatched'] += len(unmatched_grades)
        results['unmatched_grades'].extend(unmatched_grades)
        results['unmatched_gradebook'].extend(unmatched_gb)

        if not dry_run:
            # Write updated gradebook
            output_path = gradebook_path.replace('.csv', '_filled.csv')

            # Add new columns if needed
            new_fieldnames = list(fieldnames)
            if 'Total Mark' not in new_fieldnames:
                new_fieldnames.append('Total Mark')
            if 'Feedback Card' not in new_fieldnames:
                new_fieldnames.append('Feedback Card')

            with open(output_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=new_fieldnames)
                writer.writeheader()

                for row in rows:
                    # Find if this row has grades
                    if has_email:
                        email_col = 'Email address' if 'Email address' in row else 'Email'
                        key = row.get(email_col, '').strip()
                    else:
                        first = row.get('First name', '').strip()
                        last = row.get('Last name', '').strip()
                        key = f"{first} {last}".strip()

                    if key in students and key in matched_gradebook:
                        row['Total Mark'] = students[key].get('total_mark', '')
                        row['Feedback Card'] = students[key].get('feedback', '')
                    else:
                        row['Total Mark'] = ''
                        row['Feedback Card'] = ''

                    writer.writerow(row)

            print(f"  Written: {output_path}")

        results['gradebooks'].append({
            'path': gradebook_path,
            'matched': matched,
            'unmatched_grades': unmatched_grades,
            'unmatched_gradebook': unmatched_gb
        })

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Apply grades to gradebooks directly')
    parser.add_argument('--assignment-dir', required=True, help='Assignment directory')
    parser.add_argument('--gradebooks', nargs='+', required=True, help='Gradebook CSV files')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')

    args = parser.parse_args()

    results = apply_grades(args.assignment_dir, args.gradebooks, args.dry_run)

    if results:
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Total matched: {results['total_matched']}")
        print(f"Total unmatched: {results['total_unmatched']}")
        if results['unmatched_grades']:
            print(f"Unmatched names from grades.csv: {results['unmatched_grades']}")


if __name__ == '__main__':
    main()
