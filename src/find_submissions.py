#!/usr/bin/env python3
"""
Submission finder for Jupyter notebook assignments.

Recursively finds all .ipynb files in submission directories,
handles nested directories and spaces in filenames.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class SubmissionFinder:
    """Find and validate student submissions."""

    def __init__(self, submissions_dir: str, base_file: Optional[str] = None):
        """
        Initialize submission finder.

        Args:
            submissions_dir: Path to submissions directory
            base_file: Optional base filename to exclude (for structured assignments)
        """
        self.submissions_dir = Path(submissions_dir)
        self.base_file = base_file
        self.submissions = []
        self.errors = []

    def find_all_submissions(self) -> List[Dict[str, str]]:
        """
        Find all notebook submissions recursively.

        Returns:
            List of submission dictionaries with keys:
                - path: Full path to notebook file
                - student_name: Extracted student name
                - section: Section name (top-level directory)
                - relative_path: Path relative to submissions directory
        """
        if not self.submissions_dir.exists():
            self.errors.append(f"Submissions directory does not exist: {self.submissions_dir}")
            return []

        # Find all .ipynb files recursively
        notebook_files = list(self.submissions_dir.rglob("*.ipynb"))

        # Filter out base file if specified
        if self.base_file:
            notebook_files = [
                f for f in notebook_files
                if f.name != self.base_file
            ]

        # Process each file
        for notebook_path in notebook_files:
            try:
                # Get relative path from submissions directory
                rel_path = notebook_path.relative_to(self.submissions_dir)

                # Extract section (first directory level)
                parts = rel_path.parts
                section = parts[0] if len(parts) > 1 else "unknown"

                # Extract student name (prefer folder name, fallback to filename)
                student_name = self._extract_student_name(notebook_path.stem, rel_path)

                # Validate notebook
                is_valid, error = self._validate_notebook(notebook_path)
                if not is_valid:
                    self.errors.append(f"{rel_path}: {error}")
                    continue

                self.submissions.append({
                    'path': str(notebook_path),
                    'student_name': student_name,
                    'section': section,
                    'relative_path': str(rel_path),
                    'filename': notebook_path.name
                })

            except Exception as e:
                self.errors.append(f"Error processing {notebook_path}: {e}")

        # Sort by section then student name
        self.submissions.sort(key=lambda x: (x['section'], x['student_name']))

        return self.submissions

    def _extract_student_name(self, filename: str, rel_path: Path = None) -> str:
        """
        Extract student name from submission path.

        Extraction priority:
        1. Moodle folder structure: "Danny Radon_2150767_assignsubmission_file/"
        2. Parentheses in filename: "Lab 1 (John Doe).ipynb"
        3. Cleaned filename as fallback

        Args:
            filename: The notebook filename (without extension)
            rel_path: Relative path from submissions directory

        Returns:
            Extracted student name
        """
        folder_name = None

        # Try to extract from Moodle folder structure first
        if rel_path and len(rel_path.parts) >= 2:
            # Look for Moodle format: "StudentName_ID_assignsubmission_file"
            for part in rel_path.parts[1:]:  # Skip section folder
                moodle_match = re.match(r'^(.+?)_\d+_assignsubmission_file$', part)
                if moodle_match:
                    folder_name = moodle_match.group(1)
                    break

        # Try parentheses pattern in filename: "Lab 1 (John Doe)" -> "John Doe"
        paren_match = re.search(r'\(([^)]+)\)', filename)
        paren_name = None
        if paren_match:
            paren_name = paren_match.group(1).strip().replace('_', ' ')

        # Decision logic
        name = None

        # Check if parentheses name is a placeholder or generic
        placeholder_names = {'student', 'your name', 'name', 'student name', 'firstname lastname'}
        paren_is_placeholder = paren_name and paren_name.lower() in placeholder_names

        if paren_name and not paren_is_placeholder:
            # Prefer parentheses if it's a real name
            name = paren_name
        elif folder_name:
            # Use Moodle folder name
            name = folder_name
        elif paren_name:
            # Even if placeholder, use it if no folder name available
            # But try to extract from folder name as last resort
            name = folder_name if folder_name else paren_name
        else:
            # Fallback: try to extract name from filename
            name = self._extract_name_from_filename(filename)

        # Final cleanup
        name = name.strip() if name else filename
        name = name.replace('_', ' ')

        # If still empty or just numbers, use folder name or filename
        if not name or name.isdigit():
            name = folder_name if folder_name else filename

        return name

    def _extract_name_from_filename(self, filename: str) -> str:
        """
        Extract student name from filename when no parentheses or folder pattern.

        Handles patterns like:
        - "Lab_06_Logistic_Regression_MiriamObiajuru_3510F25"
        - "Lab06_LogisticRegression_Jagjiwan_3101036"
        """
        # Remove common assignment prefixes
        patterns_to_remove = [
            r'^(Copy_of_)?',  # Copy prefix
            r'Lab[_\s]?\d+[_\s]?',  # Lab numbers
            r'Logistic[_\s]?Regression[_\s]?',  # Assignment names
            r'[_\s]?3510F25[_\s]?',  # Course codes
            r'[_\s]?3520F25[_\s]?',
            r'[_\s]?\d{7}[_\s]?',  # Student IDs (7 digits)
            r'[_\s]?\(\d+\)[_\s]?',  # Numbers in parentheses like (2)
        ]

        name = filename
        for pattern in patterns_to_remove:
            name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)

        # Clean up multiple spaces and trim
        name = re.sub(r'\s+', ' ', name).strip()

        return name if name else filename

    def _validate_notebook(self, notebook_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Validate that file is a proper Jupyter notebook.

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check file size (notebooks shouldn't be too large)
            file_size = notebook_path.stat().st_size
            if file_size == 0:
                return False, "Empty file"

            if file_size > 50 * 1024 * 1024:  # 50 MB
                return False, f"File too large ({file_size / 1024 / 1024:.1f} MB)"

            # Try to parse as JSON
            with open(notebook_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Check basic notebook structure
            if not isinstance(data, dict):
                return False, "Not a valid notebook structure"

            if 'cells' not in data:
                return False, "Missing 'cells' field"

            if not isinstance(data['cells'], list):
                return False, "'cells' is not a list"

            return True, None

        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"

        except Exception as e:
            return False, f"Validation error: {e}"

    def get_sections(self) -> List[str]:
        """Get list of unique sections."""
        return sorted(set(s['section'] for s in self.submissions))

    def get_students_by_section(self) -> Dict[str, List[Dict]]:
        """Group submissions by section."""
        sections = {}
        for submission in self.submissions:
            section = submission['section']
            if section not in sections:
                sections[section] = []
            sections[section].append(submission)
        return sections

    def get_summary(self) -> Dict:
        """Get summary statistics."""
        sections = self.get_sections()
        return {
            'total_submissions': len(self.submissions),
            'total_sections': len(sections),
            'sections': {
                section: len([s for s in self.submissions if s['section'] == section])
                for section in sections
            },
            'errors': len(self.errors)
        }

    def save_manifest(self, output_file: str):
        """Save submissions manifest to JSON file."""
        manifest = {
            'submissions_directory': str(self.submissions_dir),
            'total_submissions': len(self.submissions),
            'submissions': self.submissions,
            'errors': self.errors,
            'summary': self.get_summary()
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)


def find_submissions(
    submissions_dir: str,
    base_file: Optional[str] = None,
    output_file: Optional[str] = None
) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    Find all notebook submissions.

    Args:
        submissions_dir: Path to submissions directory
        base_file: Optional base filename to exclude
        output_file: Optional file to save manifest

    Returns:
        Tuple of (submissions_list, errors_list)
    """
    finder = SubmissionFinder(submissions_dir, base_file)
    submissions = finder.find_all_submissions()
    errors = finder.errors

    if output_file:
        finder.save_manifest(output_file)

    return submissions, errors


def main():
    """CLI interface for submission finder."""
    parser = argparse.ArgumentParser(
        description="Find and validate student notebook submissions"
    )
    parser.add_argument(
        "submissions_dir",
        help="Path to submissions directory"
    )
    parser.add_argument(
        "-b", "--base-file",
        help="Base filename to exclude (for structured assignments)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file for submissions manifest (JSON)"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print summary statistics"
    )

    args = parser.parse_args()

    # Find submissions
    submissions, errors = find_submissions(
        args.submissions_dir,
        base_file=args.base_file,
        output_file=args.output
    )

    # Print errors
    if errors:
        print("Errors:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print()

    # Print summary
    if args.summary or not submissions:
        finder = SubmissionFinder(args.submissions_dir, args.base_file)
        finder.find_all_submissions()
        summary = finder.get_summary()

        print("Submission Summary:")
        print(f"  Total submissions: {summary['total_submissions']}")
        print(f"  Total sections: {summary['total_sections']}")
        print(f"  Total errors: {summary['errors']}")
        print("\nBy section:")
        for section, count in summary['sections'].items():
            print(f"  - {section}: {count} submissions")

    # Print list
    if submissions:
        print(f"\n✓ Found {len(submissions)} valid submissions")
        if args.output:
            print(f"✓ Manifest saved to {args.output}")
        sys.exit(0)
    else:
        print("\n✗ No valid submissions found")
        sys.exit(1)


if __name__ == "__main__":
    main()
