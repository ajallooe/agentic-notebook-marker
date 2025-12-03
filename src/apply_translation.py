#!/usr/bin/env python3
"""
Translation Applicator - Deterministic CSV Updates

Applies the translation mapping to update gradebook CSVs with grades and feedback.
"""

import argparse
import csv
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


def load_grades_csv(path: str) -> Dict[str, Dict[str, Any]]:
    """Load grades.csv and index by student name."""

    grades = {}
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            student_name = row['Student Name']
            grades[student_name] = row

    return grades


def detect_encoding(file_path: str) -> str:
    """Detect CSV file encoding."""

    # Try common encodings
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read()
            return encoding
        except UnicodeDecodeError:
            continue

    # Default to utf-8
    return 'utf-8'


def strip_bom(s: str) -> str:
    """Strip BOM (Byte Order Mark) from a string."""
    return s.lstrip('\ufeff')


def normalize_name(name: str) -> str:
    """Normalize a name for comparison.

    - Strips BOM
    - Replaces commas with spaces (LLM sometimes joins First,Last instead of First Last)
    - Normalizes whitespace
    - Case-insensitive (lowercased)
    """
    name = strip_bom(name)
    name = name.replace(',', ' ')  # Handle "First,Last" -> "First Last"
    name = ' '.join(name.split())  # Normalize whitespace
    return name.lower()


def get_student_name_from_row(row: Dict[str, str], student_col: str, fieldnames: List[str]) -> str:
    """Extract student name from a row, handling various column formats.

    Handles:
    - Single column with full name (e.g., "Student Name", "Name")
    - Separate first/last name columns (e.g., Moodle exports)
    - Various capitalizations
    - BOM characters in column names (common in Excel exports)
    """
    # Normalize row keys by stripping BOM
    normalized_row = {strip_bom(k): v for k, v in row.items()}

    # Check for separate first/last name columns FIRST (Moodle-style)
    # This is the most common case for gradebook exports
    first_name = ''
    last_name = ''

    for col in ['First name', 'First Name', 'first_name', 'FirstName', 'first name']:
        if col in normalized_row and normalized_row[col].strip():
            first_name = normalized_row[col].strip()
            break

    for col in ['Last name', 'Last Name', 'last_name', 'LastName', 'last name', 'Surname', 'surname']:
        if col in normalized_row and normalized_row[col].strip():
            last_name = normalized_row[col].strip()
            break

    if first_name and last_name:
        return f"{first_name} {last_name}"

    # Try the specified column (for joined name formats)
    normalized_student_col = strip_bom(student_col)
    if normalized_student_col in normalized_row and normalized_row[normalized_student_col].strip():
        # Only use this if it's not one of the first/last name columns
        if normalized_student_col not in ['First name', 'First Name', 'first_name', 'FirstName', 'first name',
                               'Last name', 'Last Name', 'last_name', 'LastName', 'last name', 'Surname', 'surname']:
            return normalized_row[normalized_student_col].strip()

    # Check for common single-name columns
    for col in ['Student Name', 'student_name', 'Name', 'name', 'Full Name', 'full_name']:
        if col in normalized_row and normalized_row[col].strip():
            return normalized_row[col].strip()

    # Fallback to individual names if only one is available
    if first_name:
        return first_name
    elif last_name:
        return last_name

    return ''


def apply_gradebook_updates(gradebook_config: Dict[str, Any], grades: Dict[str, Dict[str, Any]],
                           output_dir: Path, dry_run: bool = False) -> Dict[str, Any]:
    """Apply updates to a single gradebook CSV."""

    gradebook_path = Path(gradebook_config['path'])
    section_name = gradebook_config['section_name']

    print(f"\nProcessing: {section_name}")
    print(f"  File: {gradebook_path}")

    # Detect encoding
    encoding = gradebook_config.get('encoding', 'utf-8')
    if encoding == 'auto':
        encoding = detect_encoding(gradebook_path)
        print(f"  Detected encoding: {encoding}")

    # Load gradebook
    with open(gradebook_path, 'r', encoding=encoding) as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    # Prepare new columns
    columns_to_add = gradebook_config['columns_to_add']
    new_columns = sorted(columns_to_add.keys(), key=lambda x: columns_to_add[x]['position'])

    # Check for column conflicts
    conflicts = [col for col in new_columns if col in fieldnames]
    if conflicts:
        print(f"  WARNING: Columns already exist: {conflicts}")
        print(f"  These will be overwritten with new values")

    # Add new columns to fieldnames if needed
    updated_fieldnames = list(fieldnames)
    for col in new_columns:
        if col not in updated_fieldnames:
            updated_fieldnames.append(col)

    # Build student mapping lookup with normalized names for robust matching
    # Key: normalized gradebook name, Value: (original gradebook name, grades name)
    student_mapping = {normalize_name(m['gradebook_name']): m['grades_name']
                      for m in gradebook_config['student_mappings']}

    # Apply updates
    student_col = gradebook_config['student_column']
    updates_applied = 0
    rows_updated = []

    for row in rows:
        gradebook_name = get_student_name_from_row(row, student_col, fieldnames)
        normalized_gradebook_name = normalize_name(gradebook_name)

        if normalized_gradebook_name in student_mapping:
            grades_name = student_mapping[normalized_gradebook_name]

            if grades_name in grades:
                grade_data = grades[grades_name]

                # Update/add columns
                if 'Total Mark' in new_columns:
                    row['Total Mark'] = grade_data['Total Mark']

                if 'Feedback Card' in new_columns:
                    row['Feedback Card'] = grade_data['Feedback Card']

                # Add activity marks if present
                for col in new_columns:
                    if col.startswith('Activity ') and col in grade_data:
                        row[col] = grade_data[col]

                updates_applied += 1

        rows_updated.append(row)

    # Save updated gradebook
    if not dry_run:
        # Write filled gradebook to same directory as original, with _filled suffix
        filled_path = gradebook_path.parent / f"{gradebook_path.stem}_filled{gradebook_path.suffix}"
        with open(filled_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=updated_fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(rows_updated)

        print(f"  Filled gradebook saved: {filled_path}")

        # Also save a copy in the output directory for reference
        output_copy = output_dir / gradebook_path.name
        shutil.copy2(filled_path, output_copy)
        print(f"  Copy saved to: {output_copy}")
    else:
        print(f"  DRY RUN: Would update {updates_applied} students")

    return {
        'section': section_name,
        'total_students': len(rows),
        'updates_applied': updates_applied,
        'columns_added': [col for col in new_columns if col not in fieldnames]
    }


def generate_report(mapping: Dict[str, Any], results: List[Dict[str, Any]],
                   output_dir: Path, dry_run: bool):
    """Generate application report."""

    report_lines = [
        "GRADEBOOK TRANSLATION APPLICATION REPORT",
        "=" * 70,
        f"\nAssignment: {mapping['assignment_name']}",
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Mode: {'DRY RUN' if dry_run else 'APPLIED'}",
        "\nGRADEBOOKS UPDATED:",
        "-" * 70
    ]

    total_students = 0
    total_updates = 0

    for result in results:
        report_lines.append(f"\n{result['section']}:")
        report_lines.append(f"  Total students in gradebook: {result['total_students']}")
        report_lines.append(f"  Updates applied: {result['updates_applied']}")
        if result['columns_added']:
            report_lines.append(f"  Columns added: {', '.join(result['columns_added'])}")

        total_students += result['total_students']
        total_updates += result['updates_applied']

    report_lines.extend([
        f"\nSUMMARY:",
        "-" * 70,
        f"Total students across all gradebooks: {total_students}",
        f"Total updates applied: {total_updates}",
        f"Coverage: {total_updates/total_students*100:.1f}%" if total_students > 0 else "Coverage: N/A"
    ])

    # Add warnings about unmatched students
    summary = mapping['summary']
    if summary['unmatched_grades'] > 0:
        report_lines.extend([
            f"\nWARNING: {summary['unmatched_grades']} students in grades.csv not matched to any gradebook",
            "These students' grades were NOT added to gradebooks."
        ])

    if summary['unmatched_gradebook'] > 0:
        report_lines.extend([
            f"\nNOTE: {summary['unmatched_gradebook']} students in gradebooks not found in grades.csv",
            "These students may not have submitted the assignment."
        ])

    if summary.get('low_confidence_matches', 0) > 0:
        report_lines.extend([
            f"\nWARNING: {summary['low_confidence_matches']} low confidence matches",
            "Review the mapping file for details on these matches."
        ])

    report_lines.extend([
        "\n" + "=" * 70,
        "Application complete." if not dry_run else "Dry run complete. Use --apply to actually update gradebooks.",
        "=" * 70
    ])

    report = "\n".join(report_lines)
    print("\n" + report)

    # Save report
    report_path = output_dir / 'translation_report.txt'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n✓ Report saved to: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Apply translation mapping to update gradebook CSVs'
    )
    parser.add_argument('--mapping', required=True, help='Path to translation_mapping.json')
    parser.add_argument('--output-dir', help='Directory to save updated gradebooks (default: same as mapping)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without actually updating files (optional)')
    # Keep --apply for backwards compatibility but it's now the default
    parser.add_argument('--apply', action='store_true',
                       help='(deprecated) Apply is now the default behavior')

    args = parser.parse_args()

    # Load mapping
    mapping_path = Path(args.mapping)
    if not mapping_path.exists():
        print(f"Error: Mapping file not found: {mapping_path}")
        return 1

    with open(mapping_path, 'r', encoding='utf-8') as f:
        mapping = json.load(f)

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = mapping_path.parent

    output_dir.mkdir(parents=True, exist_ok=True)

    # Dry-run only if explicitly requested
    dry_run = args.dry_run

    if dry_run:
        print("\n" + "=" * 70)
        print("DRY RUN MODE - No files will be modified")
        print("=" * 70)

    # Load grades
    grades_csv_path = mapping['grades_csv']
    print(f"\nLoading grades from: {grades_csv_path}")
    grades = load_grades_csv(grades_csv_path)
    print(f"  Loaded {len(grades)} students")

    # Process each gradebook
    results = []
    for gradebook_config in mapping['gradebooks']:
        result = apply_gradebook_updates(gradebook_config, grades, output_dir, dry_run)
        results.append(result)

    # Generate report
    generate_report(mapping, results, output_dir, dry_run)

    if dry_run:
        print("\nTo apply these changes, run without --dry-run:")
        print(f"  python3 src/apply_translation.py --mapping {mapping_path}")

    return 0


if __name__ == '__main__':
    exit(main())
