#!/usr/bin/env python3
"""
Fix grades.csv files across all assignments:
1. Correct student name mismatches to match gradebook names
2. Remove random_state related marks (both positive and negative)
"""

import csv
import os
import re
import sys
from pathlib import Path


def load_gradebook_names(gradebook_path):
    """Load student names from gradebook (First name + Last name)."""
    names = []
    with open(gradebook_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            first = row.get('First name', '').strip()
            last = row.get('Last name', '').strip()
            if first:
                full_name = f"{first} {last}".strip()
                names.append({
                    'full': full_name,
                    'first': first,
                    'last': last,
                    'first_lower': first.lower(),
                    'last_lower': last.lower(),
                    'full_lower': full_name.lower(),
                    'full_nospace': full_name.replace(' ', '').lower(),
                })
    return names


def normalize_name(name):
    """Normalize a name for matching."""
    # Remove common prefixes like "Lab XX - Name"
    name = re.sub(r'^Lab\s*\d+[^a-zA-Z]*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'Decision Tree Classifier\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'Hyperparameter Tuning\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'Linear Regression\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'Random Forests?\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'Linear and Logistic Regression\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'Hard Margin SVMs?\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'Soft Margin SVMs? and Kernels?\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'Neural Networks? with NumPy\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'Neural Networks? using PyTorch\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'Natural Language Processing\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'Computer Vision\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'Clustering\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'3510F25\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'3520F25\s*', '', name, flags=re.IGNORECASE)
    # Remove ID numbers
    name = re.sub(r'\s*\d{7}\s*', ' ', name)
    # Remove parentheses content
    name = re.sub(r'\([^)]*\)', '', name)
    # Clean up
    name = ' '.join(name.split()).strip()
    return name


def find_best_match(grades_name, gradebook_names):
    """Find the best matching gradebook name for a grades.csv name."""
    # Manual overrides for known problematic cases
    manual_mappings = {
        'inderjeetsingh': 'Inderjeet Singh LNU',
        'christinem': 'Christine Joyce Moraleja',
        'christine': 'Christine Joyce Moraleja',
        'jaspinder': 'Jaspinderjit Singh',
        'aquiles escarra': 'Aquiles Jose Escarra Ruiz',
        'emem antia': 'Emem Antia',
        'geetika': 'Geetika LNU',
        'yungvir singh': 'Yungvir Singh',
        'student': None,  # Skip generic "Student" entries
        # 3510 specific mappings
        'fateh brar singh': 'Fateh Singh Brar',
        'fateh brar': 'Fateh Singh Brar',
        'farhan mohammaed': 'Farhan Ur Rahman Mohammed',
        'farhan mohammed 3090164': 'Farhan Ur Rahman Mohammed',
        'farhan mohammed': 'Farhan Ur Rahman Mohammed',
        'ollanagonzalez': 'Ollana Jewel Gonzalez',
        'ollana gonzalez': 'Ollana Jewel Gonzalez',
        'lab 05 random forest cmpt 3510 dharmnder': 'Dharminder Singh',
        # 3520 specific mappings
        'cmpt3520 lab 1: linear and logistic regression': None,  # Invalid entry
        'lab 01 linear and logistic regression': None,  # Invalid entry
        'lab 03 soft margin svms and kernels': None,  # Invalid entry
        'rakshti bhrdwaj lab 03 soft margin svms and kernels': 'Rakshit Bhardwaj',
        'cmpt 3520 lab5 deep neural network[christinem]': 'Christine Joyce Moraleja',
        'lab 5 neural networks using pytorch (yuvraj lal)': 'Yuvraj Lal',
        'navroo kaur': 'Navroop Kaur',
    }

    # Also check original name in manual mappings (before normalization)
    original_lower = grades_name.lower().strip()
    original_nospace = original_lower.replace(' ', '')

    # Check manual mappings against original name first
    if original_lower in manual_mappings:
        return manual_mappings[original_lower]
    if original_nospace in manual_mappings:
        return manual_mappings[original_nospace]

    normalized = normalize_name(grades_name)
    normalized_lower = normalized.lower()
    normalized_nospace = normalized.replace(' ', '').lower()

    # Check manual mappings against normalized name
    if normalized_lower in manual_mappings:
        return manual_mappings[normalized_lower]
    if normalized_nospace in manual_mappings:
        return manual_mappings[normalized_nospace]

    # Skip header row or invalid names
    if grades_name.lower() in ['student name', 'student', 'first last', '']:
        return None

    # Try exact match first
    for gb in gradebook_names:
        if normalized_lower == gb['full_lower']:
            return gb['full']

    # Try no-space match
    for gb in gradebook_names:
        if normalized_nospace == gb['full_nospace']:
            return gb['full']

    # Try first name only match (for truncated names like "Christine" -> "Christine Joyce Moraleja")
    for gb in gradebook_names:
        if normalized_lower == gb['first_lower']:
            return gb['full']
        # Match if normalized starts with first name
        if normalized_lower.startswith(gb['first_lower']) and len(gb['first_lower']) >= 3:
            # Check if this could be the person
            rest = normalized_lower[len(gb['first_lower']):].strip()
            if not rest or rest[0] in 'mlkjsbnatvpgw':  # Common last name starts
                return gb['full']

    # Try partial match - first name contained
    for gb in gradebook_names:
        if gb['first_lower'] in normalized_lower and len(gb['first_lower']) >= 4:
            # Also check if last name is there
            if gb['last_lower'] and gb['last_lower'] in normalized_lower:
                return gb['full']

    # Try matching with common variations
    # Handle "InderjeetSingh" -> "Inderjeet Singh LNU"
    for gb in gradebook_names:
        combined = (gb['first'] + gb['last']).lower()
        if normalized_nospace == combined:
            return gb['full']
        # Also try first name only without space
        first_nospace = gb['first'].replace(' ', '').lower()
        if normalized_nospace == first_nospace:
            return gb['full']

    # Try matching first name that contains the search term
    for gb in gradebook_names:
        # Handle "InderjeetSingh" matching "Inderjeet Singh LNU" (first name is "Inderjeet Singh")
        first_nospace = gb['first'].replace(' ', '').lower()
        if first_nospace and normalized_nospace.startswith(first_nospace):
            return gb['full']
        if first_nospace and first_nospace.startswith(normalized_nospace) and len(normalized_nospace) >= 5:
            return gb['full']

    # Handle special case: "ChristineM" type truncations
    for gb in gradebook_names:
        if len(normalized_lower) >= 4:
            # Check if it's a truncated version of first name + start of last
            if gb['first_lower'].startswith(normalized_lower[:len(gb['first_lower'])]):
                rest = normalized_lower[len(gb['first_lower']):]
                if rest and gb['last_lower'].startswith(rest):
                    return gb['full']

    return None


def remove_random_state_marks(feedback):
    """Remove random_state related positive and negative marks from feedback."""
    if not feedback:
        return feedback

    # Patterns to remove (lines mentioning random_state as positive or negative)
    patterns = [
        r'.*random_state.*bonus.*\n?',
        r'.*bonus.*random_state.*\n?',
        r'.*random_state.*positive.*\n?',
        r'.*positive.*random_state.*\n?',
        r'.*random_state.*deduction.*\n?',
        r'.*deduction.*random_state.*\n?',
        r'.*random_state.*penalty.*\n?',
        r'.*penalty.*random_state.*\n?',
        r'.*\+\s*\d+\.?\d*.*random_state.*\n?',
        r'.*-\s*\d+\.?\d*.*random_state.*\n?',
        r'.*random_state.*\+\s*\d+\.?\d*.*\n?',
        r'.*random_state.*-\s*\d+\.?\d*.*\n?',
        r'.*[Uu]sing random_state.*\n?',
        r'.*[Nn]ot using random_state.*\n?',
        r'.*[Mm]issing random_state.*\n?',
        r'.*[Ss]et random_state.*\n?',
        r'.*random_state=42.*reproducibility.*\n?',
        r'.*reproducibility.*random_state.*\n?',
        r'• .*random_state.*\n?',
        r'- .*random_state.*\n?',
        r'\* .*random_state.*\n?',
    ]

    for pattern in patterns:
        feedback = re.sub(pattern, '', feedback, flags=re.IGNORECASE)

    return feedback


def process_grades_csv(grades_path, gradebook_names, dry_run=False):
    """Process a grades.csv file to fix names and remove random_state marks."""
    changes = []

    with open(grades_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse the CSV
    lines = content.split('\n')
    if not lines:
        return changes

    # Find all student entries
    result_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Check if this is a student row (starts with quoted name)
        if line.startswith('"') and '","' in line:
            # Extract the student name (first field)
            match = re.match(r'^"([^"]*)"', line)
            if match:
                old_name = match.group(1)

                # Skip header
                if old_name.lower() == 'student name':
                    result_lines.append(line)
                    i += 1
                    continue

                # Find best match
                new_name = find_best_match(old_name, gradebook_names)

                if new_name and new_name != old_name:
                    changes.append(f"  {old_name} -> {new_name}")
                    line = line.replace(f'"{old_name}"', f'"{new_name}"', 1)

                # Also check for random_state in the feedback column
                if 'random_state' in line.lower():
                    original_line = line
                    # The feedback is in the last field - need to handle multiline
                    # Collect all lines until next student entry
                    full_entry = [line]
                    j = i + 1
                    while j < len(lines) and not (lines[j].startswith('"') and '","' in lines[j] and not lines[j].startswith('"ASSIGNMENT')):
                        if lines[j].startswith('"Student Name"'):
                            break
                        full_entry.append(lines[j])
                        j += 1

                    full_text = '\n'.join(full_entry)
                    cleaned_text = remove_random_state_marks(full_text)

                    if cleaned_text != full_text:
                        changes.append(f"  Removed random_state references for {new_name or old_name}")
                        result_lines.append(cleaned_text)
                        i = j
                        continue

        result_lines.append(line)
        i += 1

    if changes and not dry_run:
        with open(grades_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(result_lines))

    return changes


def get_gradebook_for_assignment(assignment_dir):
    """Find the original gradebook for an assignment."""
    gradebooks_dir = assignment_dir / 'gradebooks'
    if not gradebooks_dir.exists():
        return None

    for f in gradebooks_dir.iterdir():
        if f.suffix == '.csv' and '_filled' not in f.name and '_summarized' not in f.name and '_corrected' not in f.name:
            return f
    return None


def main():
    base_dir = Path('/Volumes/Mac Storage/workspace/NorQuest Admin/agentic-notebook-marker/assignments')

    dry_run = '--dry-run' in sys.argv
    if dry_run:
        print("DRY RUN - No changes will be made\n")

    all_changes = {}

    for assignment_dir in sorted(base_dir.iterdir()):
        if not assignment_dir.is_dir():
            continue
        if assignment_dir.name == 'sample-assignment':
            continue

        grades_csv = assignment_dir / 'processed' / 'final' / 'grades.csv'
        if not grades_csv.exists():
            continue

        gradebook = get_gradebook_for_assignment(assignment_dir)
        if not gradebook:
            print(f"WARNING: No gradebook found for {assignment_dir.name}")
            continue

        print(f"\n{'='*60}")
        print(f"Processing: {assignment_dir.name}")
        print(f"{'='*60}")
        print(f"Gradebook: {gradebook.name}")
        print(f"Grades CSV: {grades_csv}")

        gradebook_names = load_gradebook_names(gradebook)
        print(f"Loaded {len(gradebook_names)} students from gradebook")

        changes = process_grades_csv(grades_csv, gradebook_names, dry_run)

        if changes:
            all_changes[assignment_dir.name] = changes
            print(f"\nChanges {'(would be)' if dry_run else ''} made:")
            for change in changes[:20]:  # Limit output
                print(change)
            if len(changes) > 20:
                print(f"  ... and {len(changes) - 20} more changes")
        else:
            print("No changes needed")

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Assignments processed: {len(all_changes)}")
    total_changes = sum(len(c) for c in all_changes.values())
    print(f"Total changes: {total_changes}")


if __name__ == '__main__':
    main()
