#!/usr/bin/env python3
"""
Clean outputs from Jupyter notebooks to reduce file size.

Removes cell outputs and execution counts from .ipynb files.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Tuple


def clean_notebook(notebook_path: Path, dry_run: bool = False) -> Tuple[int, int, int]:
    """
    Clean outputs from a notebook.

    Returns:
        (original_size, new_size, cells_cleaned)
    """
    original_size = notebook_path.stat().st_size

    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"  Error reading {notebook_path}: {e}", file=sys.stderr)
        return original_size, original_size, 0

    if 'cells' not in notebook:
        return original_size, original_size, 0

    cells_cleaned = 0
    for cell in notebook['cells']:
        had_output = False

        # Clear outputs
        if 'outputs' in cell and cell['outputs']:
            had_output = True
            cell['outputs'] = []

        # Clear execution count
        if 'execution_count' in cell and cell['execution_count'] is not None:
            had_output = True
            cell['execution_count'] = None

        if had_output:
            cells_cleaned += 1

    if cells_cleaned == 0:
        return original_size, original_size, 0

    if dry_run:
        # Estimate new size
        new_content = json.dumps(notebook, indent=1, ensure_ascii=False)
        return original_size, len(new_content.encode('utf-8')), cells_cleaned

    # Write cleaned notebook
    with open(notebook_path, 'w', encoding='utf-8') as f:
        json.dump(notebook, f, indent=1, ensure_ascii=False)
        f.write('\n')

    new_size = notebook_path.stat().st_size
    return original_size, new_size, cells_cleaned


def format_size(size_bytes: int) -> str:
    """Format size in human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


def main():
    parser = argparse.ArgumentParser(
        description='Clean outputs from Jupyter notebooks'
    )
    parser.add_argument(
        'path',
        type=Path,
        help='Directory or notebook file to clean'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be cleaned without modifying files'
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Only show summary'
    )
    parser.add_argument(
        '--submissions-only',
        action='store_true',
        help='Only clean files in submissions/ subdirectory'
    )

    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN - no files will be modified\n")

    # Find notebooks
    if args.path.is_file():
        notebooks = [args.path]
    else:
        pattern = "submissions/**/*.ipynb" if args.submissions_only else "**/*.ipynb"
        notebooks = list(args.path.glob(pattern))

    if not notebooks:
        print(f"No notebooks found in {args.path}")
        return 1

    total_original = 0
    total_new = 0
    total_cells = 0
    files_cleaned = 0

    for notebook in sorted(notebooks):
        original, new, cells = clean_notebook(notebook, dry_run=args.dry_run)
        total_original += original
        total_new += new
        total_cells += cells

        if cells > 0:
            files_cleaned += 1
            if not args.quiet:
                saved = original - new
                rel_path = notebook.relative_to(args.path) if args.path.is_dir() else notebook.name
                print(f"  {rel_path}: {format_size(original)} -> {format_size(new)} (-{format_size(saved)}, {cells} cells)")

    # Summary
    print(f"\nSummary:")
    print(f"  Files scanned: {len(notebooks)}")
    print(f"  Files with outputs: {files_cleaned}")
    print(f"  Cells cleaned: {total_cells}")
    print(f"  Size: {format_size(total_original)} -> {format_size(total_new)}")
    print(f"  Saved: {format_size(total_original - total_new)} ({100 * (total_original - total_new) / total_original:.1f}%)" if total_original > 0 else "")

    return 0


if __name__ == '__main__':
    sys.exit(main())
