#!/usr/bin/env python3
"""
Group membership parser for group assignments.

Parses groups.csv to map group names to student members.
"""

import csv
import sys
from pathlib import Path
from typing import Dict, List
import json


def parse_groups(groups_csv_path: str) -> Dict[str, List[str]]:
    """
    Parse groups.csv file.

    Format:
        group_name,student_name
        Team Alpha,John Smith
        Team Alpha,Jane Doe
        Team Beta,Bob Johnson

    Args:
        groups_csv_path: Path to groups.csv file

    Returns:
        Dictionary mapping group names to lists of student names
        Example: {"Team Alpha": ["John Smith", "Jane Doe"], ...}
    """
    groups_path = Path(groups_csv_path)

    if not groups_path.exists():
        print(f"Error: groups.csv not found at {groups_csv_path}", file=sys.stderr)
        return {}

    groups = {}

    try:
        with open(groups_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            # Validate header
            if 'group_name' not in reader.fieldnames or 'student_name' not in reader.fieldnames:
                print("Error: groups.csv must have 'group_name' and 'student_name' columns", file=sys.stderr)
                return {}

            for row in reader:
                group_name = row['group_name'].strip()
                student_name = row['student_name'].strip()

                if not group_name or not student_name:
                    continue

                if group_name not in groups:
                    groups[group_name] = []

                groups[group_name].append(student_name)

    except Exception as e:
        print(f"Error parsing groups.csv: {e}", file=sys.stderr)
        return {}

    return groups


def get_group_for_student(groups: Dict[str, List[str]], student_name: str) -> str:
    """
    Find which group a student belongs to.

    Args:
        groups: Dictionary mapping group names to student lists
        student_name: Name of student to find

    Returns:
        Group name if found, empty string otherwise
    """
    for group_name, members in groups.items():
        if student_name in members:
            return group_name
    return ""


def validate_groups(groups: Dict[str, List[str]]) -> List[str]:
    """
    Validate group structure and return any warnings.

    Args:
        groups: Dictionary mapping group names to student lists

    Returns:
        List of warning messages
    """
    warnings = []

    # Check for duplicate students across groups
    all_students = []
    for group_name, members in groups.items():
        all_students.extend(members)

    seen = set()
    duplicates = set()
    for student in all_students:
        if student in seen:
            duplicates.add(student)
        seen.add(student)

    if duplicates:
        warnings.append(f"Students in multiple groups: {', '.join(duplicates)}")

    # Check for groups with only one member
    single_member_groups = [name for name, members in groups.items() if len(members) == 1]
    if single_member_groups:
        warnings.append(f"Groups with only one member: {', '.join(single_member_groups)}")

    return warnings


def main():
    """CLI interface for group parser."""
    if len(sys.argv) < 2:
        print("Usage: group_parser.py <groups.csv> [--json]")
        print("  --json: Output as JSON")
        sys.exit(1)

    groups_csv = sys.argv[1]
    output_json = '--json' in sys.argv

    groups = parse_groups(groups_csv)

    if not groups:
        print("No groups found or error parsing file", file=sys.stderr)
        sys.exit(1)

    # Validate
    warnings = validate_groups(groups)
    if warnings and not output_json:
        print("Warnings:", file=sys.stderr)
        for warning in warnings:
            print(f"  - {warning}", file=sys.stderr)
        print(file=sys.stderr)

    if output_json:
        print(json.dumps(groups, indent=2))
    else:
        print(f"Parsed {len(groups)} groups with {sum(len(m) for m in groups.values())} total students:")
        for group_name, members in sorted(groups.items()):
            print(f"\n{group_name} ({len(members)} members):")
            for member in sorted(members):
                print(f"  - {member}")


if __name__ == "__main__":
    main()
