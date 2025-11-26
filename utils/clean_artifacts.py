#!/usr/bin/env python3
"""
Artifact Cleaner - Remove LLM generation artifacts from files

Removes exact occurrences of textual artifacts (like "YOLO mode is enabled...")
from input files based on a list of known artifacts.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple


def load_artifacts(artifacts_file: Path) -> List[str]:
    """Load artifact strings from JSONL file."""

    if not artifacts_file.exists():
        print(f"Warning: Artifacts file not found: {artifacts_file}")
        return []

    artifacts = []
    try:
        with open(artifacts_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    if 'artifact' in data:
                        artifacts.append(data['artifact'])
                    else:
                        print(f"Warning: Line {line_num} missing 'artifact' field")
                except json.JSONDecodeError as e:
                    print(f"Warning: Invalid JSON at line {line_num}: {e}")

    except Exception as e:
        print(f"Error loading artifacts file: {e}")
        return []

    return artifacts


def clean_file(input_file: Path, artifacts: List[str], in_place: bool = False,
               output_file: Path = None) -> Tuple[int, int]:
    """
    Clean artifacts from a file.

    Returns:
        (removals_count, lines_cleaned)
    """

    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        return 0, 0

    # Read file
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return 0, 0

    original_content = content
    removals_count = 0

    # Remove each artifact (exact match)
    for artifact in artifacts:
        if artifact in content:
            # Count occurrences before removal
            count = content.count(artifact)
            removals_count += count
            # Remove all occurrences
            content = content.replace(artifact, '')

    # Check if any changes were made
    if content == original_content:
        return 0, 0

    # Count lines cleaned (lines that changed)
    original_lines = original_content.splitlines()
    new_lines = content.splitlines()
    lines_cleaned = sum(1 for old, new in zip(original_lines, new_lines) if old != new)

    # Write output
    try:
        if in_place:
            with open(input_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ Cleaned {input_file} in-place")
        elif output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ Cleaned version saved to {output_file}")
        else:
            # Output to stdout
            print(content, end='')
            return removals_count, lines_cleaned

    except Exception as e:
        print(f"Error writing output: {e}")
        return 0, 0

    return removals_count, lines_cleaned


def main():
    parser = argparse.ArgumentParser(
        description='Remove LLM generation artifacts from files',
        epilog='Example: clean_artifacts.py input.txt --in-place'
    )

    parser.add_argument('input_file', type=Path, help='File to clean')
    parser.add_argument('-o', '--output', type=Path, help='Output file (default: stdout)')
    parser.add_argument('-i', '--in-place', action='store_true',
                       help='Modify file in-place')
    parser.add_argument('-a', '--artifacts-file', type=Path,
                       help='Artifacts JSONL file (default: configs/processing_artifacts.jsonl)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be cleaned without modifying files')

    args = parser.parse_args()

    # Validate arguments
    if args.in_place and args.output:
        print("Error: Cannot use both --in-place and --output")
        return 1

    # Determine artifacts file path
    if args.artifacts_file:
        artifacts_file = args.artifacts_file
    else:
        # Default path relative to script location
        script_dir = Path(__file__).parent.parent
        artifacts_file = script_dir / 'configs' / 'processing_artifacts.jsonl'

    # Load artifacts
    if args.verbose:
        print(f"Loading artifacts from: {artifacts_file}")

    artifacts = load_artifacts(artifacts_file)

    if not artifacts:
        print("No artifacts loaded. Nothing to clean.")
        return 0

    if args.verbose:
        print(f"Loaded {len(artifacts)} artifact(s)")
        for i, artifact in enumerate(artifacts, 1):
            # Show first 50 chars of each artifact
            preview = artifact[:50] + '...' if len(artifact) > 50 else artifact
            preview = preview.replace('\n', '\\n')
            print(f"  {i}. {preview}")
        print()

    # Dry run mode
    if args.dry_run:
        print("DRY RUN MODE - No files will be modified\n")
        try:
            with open(args.input_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading file: {e}")
            return 1

        found_artifacts = []
        for artifact in artifacts:
            count = content.count(artifact)
            if count > 0:
                found_artifacts.append((artifact, count))

        if found_artifacts:
            print(f"Found {len(found_artifacts)} artifact(s) in {args.input_file}:")
            for artifact, count in found_artifacts:
                preview = artifact[:50] + '...' if len(artifact) > 50 else artifact
                preview = preview.replace('\n', '\\n')
                print(f"  - {count}x: {preview}")
        else:
            print(f"No artifacts found in {args.input_file}")

        return 0

    # Clean the file
    removals_count, lines_cleaned = clean_file(
        args.input_file,
        artifacts,
        in_place=args.in_place,
        output_file=args.output
    )

    if args.verbose and (removals_count > 0 or lines_cleaned > 0):
        print(f"\nCleaning summary:")
        print(f"  Artifacts removed: {removals_count}")
        print(f"  Lines affected: {lines_cleaned}")

    return 0


if __name__ == '__main__':
    exit(main())
