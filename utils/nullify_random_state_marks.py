#!/usr/bin/env python3
"""
Nullify random_state related marks in approved_scheme.json files.

This script:
1. Finds all approved_scheme.json files
2. Identifies mistake/positive codes related to random_state
3. Sets their values to 0.0 (nullifying the impact)
4. Updates the scheme files
"""

import json
import os
import re
from pathlib import Path


def find_random_state_codes(normalized_dir):
    """Find mistake and positive codes related to random_state in scoring files."""
    random_state_codes = {'mistakes': set(), 'positives': set()}

    for scoring_file in normalized_dir.glob("*_scoring.md"):
        with open(scoring_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find table rows mentioning random_state
        for line in content.split('\n'):
            if 'random_state' in line.lower() and '|' in line:
                # Extract code from table row (format: | CODE | description | ...)
                parts = line.split('|')
                if len(parts) >= 2:
                    code = parts[1].strip()
                    # Match codes like M001, M002, P001, P002 etc.
                    if re.match(r'^[MP]\d+$', code):
                        activity = scoring_file.stem.replace('_scoring', '')  # e.g., A1
                        full_code = f"{activity}_{code}"  # e.g., A1_M001

                        if code.startswith('M'):
                            random_state_codes['mistakes'].add(full_code)
                        elif code.startswith('P'):
                            random_state_codes['positives'].add(full_code)

    return random_state_codes


def nullify_codes_in_scheme(scheme_path, random_state_codes, dry_run=False):
    """Set random_state related codes to 0.0 in the approved scheme."""
    with open(scheme_path, 'r', encoding='utf-8') as f:
        scheme = json.load(f)

    changes = []

    mistakes = scheme.get('mistakes', {})
    positives = scheme.get('positives', {})

    # Handle dict format (older style)
    if isinstance(mistakes, dict):
        for code in list(mistakes.keys()):
            normalized_code = code.replace('`', '')
            is_random_state = any(
                normalized_code == rs_code or code == rs_code
                for rs_code in random_state_codes['mistakes']
            )
            if is_random_state and mistakes[code] != 0.0:
                changes.append(f"  mistake {code}: {mistakes[code]} -> 0.0")
                if not dry_run:
                    scheme['mistakes'][code] = 0.0

    # Handle list format (newer style)
    elif isinstance(mistakes, list):
        for i, item in enumerate(mistakes):
            code = item.get('id', '')
            normalized_code = code.replace('`', '')
            # Also check description for random_state
            desc = item.get('description', '').lower()
            is_random_state = (
                any(normalized_code == rs_code or code == rs_code for rs_code in random_state_codes['mistakes'])
                or 'random_state' in desc
            )
            deduction = item.get('suggested_deduction', 0.0)
            if is_random_state and deduction != 0.0:
                changes.append(f"  mistake {code}: {deduction} -> 0.0")
                if not dry_run:
                    scheme['mistakes'][i]['suggested_deduction'] = 0.0

    # Handle dict format for positives
    if isinstance(positives, dict):
        for code in list(positives.keys()):
            normalized_code = code.replace('`', '')
            is_random_state = any(
                normalized_code == rs_code or code == rs_code
                for rs_code in random_state_codes['positives']
            )
            if is_random_state and positives[code] != 0.0:
                changes.append(f"  positive {code}: {positives[code]} -> 0.0")
                if not dry_run:
                    scheme['positives'][code] = 0.0

    # Handle list format for positives
    elif isinstance(positives, list):
        for i, item in enumerate(positives):
            code = item.get('id', '')
            normalized_code = code.replace('`', '')
            desc = item.get('description', '').lower()
            is_random_state = (
                any(normalized_code == rs_code or code == rs_code for rs_code in random_state_codes['positives'])
                or 'random_state' in desc
            )
            bonus = item.get('suggested_bonus', 0.0)
            if is_random_state and bonus != 0.0:
                changes.append(f"  positive {code}: {bonus} -> 0.0")
                if not dry_run:
                    scheme['positives'][i]['suggested_bonus'] = 0.0

    if changes and not dry_run:
        with open(scheme_path, 'w', encoding='utf-8') as f:
            json.dump(scheme, f, indent=2)

    return changes


def main():
    import sys
    dry_run = '--dry-run' in sys.argv

    if dry_run:
        print("DRY RUN - No changes will be made\n")

    assignments_dir = Path(__file__).parent.parent / "assignments"
    total_changes = 0

    for assignment_dir in sorted(assignments_dir.iterdir()):
        if not assignment_dir.is_dir() or assignment_dir.name == "sample-assignment":
            continue

        scheme_path = assignment_dir / "processed" / "approved_scheme.json"
        normalized_dir = assignment_dir / "processed" / "normalized"

        if not scheme_path.exists() or not normalized_dir.exists():
            continue

        # Find random_state codes in this assignment's scoring files
        random_state_codes = find_random_state_codes(normalized_dir)

        if not random_state_codes['mistakes'] and not random_state_codes['positives']:
            continue

        # Nullify them in the approved scheme
        changes = nullify_codes_in_scheme(scheme_path, random_state_codes, dry_run)

        if changes:
            print(f"=== {assignment_dir.name} ===")
            print(f"  Found {len(random_state_codes['mistakes'])} mistake codes, {len(random_state_codes['positives'])} positive codes")
            for change in changes:
                print(change)
            print()
            total_changes += len(changes)

    print(f"\nTotal: {total_changes} codes nullified")

    if not dry_run and total_changes > 0:
        print("\nNOTE: You need to re-run the unifier and aggregator stages to apply these changes to student grades.")
        print("      Or use the recalculate_grades.py script to update grades without full re-processing.")


if __name__ == '__main__':
    main()
