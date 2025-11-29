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
from typing import Dict, List, Any


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
        fieldnames = reader.fieldnames
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

    # Build student mapping lookup
    student_mapping = {m['gradebook_name']: m['grades_name']
                      for m in gradebook_config['student_mappings']}

    # Apply updates
    student_col = gradebook_config['student_column']
    updates_applied = 0
    rows_updated = []

    for row in rows:
        gradebook_name = row.get(student_col, '')

        if gradebook_name in student_mapping:
            grades_name = student_mapping[gradebook_name]

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
        # Create backup
        backup_path = output_dir / f"{gradebook_path.stem}_backup{gradebook_path.suffix}"
        shutil.copy2(gradebook_path, backup_path)
        print(f"  Backup created: {backup_path}")

        # Write updated gradebook
        output_path = output_dir / gradebook_path.name
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=updated_fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(rows_updated)

        print(f"  Updated gradebook saved: {output_path}")
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
