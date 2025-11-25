#!/usr/bin/env python3
"""
Overview Generator Utility

Checks if overview.md exists in the notebook's directory.
If not present, uses an LLM to analyze the notebook and generate overview.md.
If present, notifies user and exits.

Usage:
    python3 create_overview.py <notebook_path> --model <model_name>

Example:
    python3 create_overview.py assignments/lab1/notebook.ipynb --model claude-sonnet-4-5
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def load_notebook(notebook_path: Path) -> dict:
    """Load and parse a Jupyter notebook."""
    if not notebook_path.exists():
        raise FileNotFoundError(f"Notebook not found: {notebook_path}")

    if not notebook_path.suffix == '.ipynb':
        raise ValueError(f"Not a Jupyter notebook: {notebook_path}")

    with open(notebook_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_notebook_summary(notebook: dict) -> str:
    """Extract a summary of the notebook for the LLM prompt."""
    cells = notebook.get('cells', [])

    # Count cell types
    code_cells = sum(1 for cell in cells if cell.get('cell_type') == 'code')
    markdown_cells = sum(1 for cell in cells if cell.get('cell_type') == 'markdown')

    # Extract first few markdown cells as context
    markdown_content = []
    for cell in cells[:10]:  # Look at first 10 cells
        if cell.get('cell_type') == 'markdown':
            source = ''.join(cell.get('source', []))
            markdown_content.append(source)

    # Extract activity markers if present
    activities = []
    for cell in cells:
        if cell.get('cell_type') == 'markdown':
            source = ''.join(cell.get('source', []))
            if '**[A' in source or '*Start student input*' in source:
                # Found activity marker
                import re
                matches = re.findall(r'\*\*\[A\d+\]\*\*', source)
                activities.extend(matches)

    summary = f"""
Notebook Statistics:
- Total cells: {len(cells)}
- Code cells: {code_cells}
- Markdown cells: {markdown_cells}
- Activities detected: {len(set(activities))} ({', '.join(set(activities)) if activities else 'None'})

First Markdown Cells (for context):
{'=' * 70}
{chr(10).join(markdown_content[:3])}
{'=' * 70}
"""
    return summary


def create_prompt(notebook_path: Path, notebook_summary: str) -> str:
    """Create the prompt for the LLM to generate overview.md."""

    prompt = f"""You are analyzing a Jupyter notebook assignment to create an overview.md configuration file.

NOTEBOOK PATH: {notebook_path}

NOTEBOOK SUMMARY:
{notebook_summary}

Your task is to create an overview.md file with the following structure:

```markdown
---
default_provider: claude
default_model: claude-sonnet-4-5
max_parallel: 4
base_file: <notebook_filename>
assignment_type: <structured or freeform>
total_marks: <total_marks>
---

# <Assignment Title>

## Assignment Overview

<Brief description of what this assignment is about>

## Learning Objectives

<List the key learning objectives>

## Assignment Structure

<Describe the structure - is it structured with activities, or free-form?>

<If structured, list the activities>

## Grading Criteria

<Describe how the assignment should be graded>

## Notes

<Any additional notes about the assignment>
```

IMPORTANT INSTRUCTIONS:

1. **assignment_type**: Determine if this is "structured" (has activity markers like **[A1]**, **[A2]**, etc.) or "freeform" (no markers)

2. **base_file**: Use the notebook filename: {notebook_path.name}

3. **default_provider**: Keep as "claude" unless you have a reason to change

4. **default_model**: Use "claude-sonnet-4-5" as default

5. **max_parallel**: Keep as 4 (good default for most systems)

6. **total_marks**: Estimate based on the assignment complexity (typically 100)

7. **Assignment Overview**: Write a clear 2-3 sentence description

8. **Learning Objectives**: List 3-5 key learning objectives based on the notebook content

9. **Assignment Structure**: Describe whether it's structured or free-form, and list activities if applicable

10. **Grading Criteria**: Provide a breakdown of how marks should be distributed (e.g., 60% correctness, 20% code quality, 20% understanding)

Please analyze the notebook summary above and generate ONLY the overview.md content. Do not include any additional commentary or explanation - just output the markdown content that should go into overview.md.

Begin your response with the YAML front matter (the --- delimited section) and end with the last section of the markdown content.
"""
    return prompt


def call_llm(prompt: str, model: str) -> str:
    """Call the LLM via llm_caller.sh to generate the overview content."""

    # Get the path to llm_caller.sh
    script_dir = Path(__file__).parent
    llm_caller = script_dir / "llm_caller.sh"

    if not llm_caller.exists():
        raise FileNotFoundError(f"llm_caller.sh not found at {llm_caller}")

    # Determine provider from model name
    provider = None
    if model.startswith('claude-'):
        provider = 'claude'
    elif model.startswith('gemini-'):
        provider = 'gemini'
    elif model.startswith('gpt-'):
        provider = 'codex'
    else:
        # Default to claude
        provider = 'claude'

    # Call llm_caller.sh in headless mode
    cmd = [
        str(llm_caller),
        "--prompt", prompt,
        "--mode", "headless",
        "--provider", provider,
        "--model", model
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error calling LLM: {e}", file=sys.stderr)
        print(f"STDERR: {e.stderr}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Generate overview.md from a Jupyter notebook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s assignments/lab1/notebook.ipynb --model claude-sonnet-4-5
  %(prog)s path/to/notebook.ipynb --model gemini-2.5-pro
  %(prog)s notebook.ipynb --model gpt-5.1
        """
    )

    parser.add_argument(
        'notebook',
        type=Path,
        help='Path to the Jupyter notebook (.ipynb file)'
    )

    parser.add_argument(
        '--model',
        required=True,
        help='Model to use for generation (e.g., claude-sonnet-4-5, gemini-2.5-pro, gpt-5.1)'
    )

    args = parser.parse_args()

    # Validate notebook path
    notebook_path = args.notebook.resolve()
    if not notebook_path.exists():
        print(f"Error: Notebook not found: {notebook_path}", file=sys.stderr)
        sys.exit(1)

    if notebook_path.suffix != '.ipynb':
        print(f"Error: Not a Jupyter notebook (must end in .ipynb): {notebook_path}", file=sys.stderr)
        sys.exit(1)

    # Check if overview.md already exists in the notebook's directory
    notebook_dir = notebook_path.parent
    overview_path = notebook_dir / 'overview.md'

    if overview_path.exists():
        print(f"Error: overview.md already exists at: {overview_path}", file=sys.stderr)
        print("Remove the existing file if you want to regenerate it.", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing notebook: {notebook_path}")
    print(f"Using model: {args.model}")
    print()

    # Load and analyze the notebook
    try:
        notebook = load_notebook(notebook_path)
        notebook_summary = get_notebook_summary(notebook)
    except Exception as e:
        print(f"Error reading notebook: {e}", file=sys.stderr)
        sys.exit(1)

    print("Notebook loaded successfully")
    print(f"Detected {len(notebook.get('cells', []))} cells")
    print()

    # Create prompt
    prompt = create_prompt(notebook_path, notebook_summary)

    # Call LLM to generate overview
    print("Calling LLM to generate overview.md...")
    print("This may take a moment...")
    print()

    try:
        overview_content = call_llm(prompt, args.model)
    except Exception as e:
        print(f"Error generating overview: {e}", file=sys.stderr)
        sys.exit(1)

    # Save overview.md
    try:
        with open(overview_path, 'w', encoding='utf-8') as f:
            f.write(overview_content)

        print("✓ Successfully created overview.md")
        print(f"  Location: {overview_path}")
        print()
        print("Please review the generated overview.md and make any necessary adjustments.")
        print()

    except Exception as e:
        print(f"Error writing overview.md: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
