#!/usr/bin/env python3
"""
Overview Generator Utility

Checks if overview.md exists in the notebook's directory.
If not present, uses an LLM to analyze the notebook and generate overview.md.
If present, notifies user and exits.

Usage:
    python3 create_overview.py <notebook_path> --model <model_name>
    python3 create_overview.py <notebook_path> --provider <provider>
    python3 create_overview.py <notebook_path> --api-model <model_name>

Example:
    python3 create_overview.py assignments/lab1/notebook.ipynb --model claude-sonnet-4
    python3 create_overview.py assignments/lab1/notebook.ipynb --model gemini-2.5-pro
    python3 create_overview.py assignments/lab1/notebook.ipynb --provider claude
    python3 create_overview.py assignments/lab1/notebook.ipynb --api-model gemini-2.5-flash
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Add src/utils to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'utils'))
from system_config import resolve_provider_from_model, format_available_models


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


def create_prompt(notebook_path: Path, notebook_summary: str, provider: str, model: str) -> str:
    """Create the prompt for the LLM to generate overview.md."""

    prompt = f"""You are analyzing a Jupyter notebook assignment to create an overview.md configuration file.

NOTEBOOK PATH: {notebook_path}

NOTEBOOK SUMMARY:
{notebook_summary}

Your task is to create an overview.md file with the following structure:

```markdown
---
default_provider: {provider}
default_model: {model}
max_parallel: 4
base_file: <notebook_filename>
assignment_type: <structured or freeform>
total_marks: <total_marks>

# Per-stage model overrides (optional - use assignment default_model for all stages)
stage_models:
  pattern_designer: {model}
  marker: {model}
  normalizer: {model}
  unifier: {model}
  aggregator: {model}
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

3. **default_provider**: Use "{provider}" (the provider you're currently running on)

4. **default_model**: Use "{model}" (the model you're currently running on)

5. **stage_models**: Set all stages to use "{model}" (the same model)

6. **max_parallel**: Keep as 4 (good default for most systems)

7. **total_marks**: Estimate based on the assignment complexity (typically 100)

8. **Assignment Overview**: Write a clear 2-3 sentence description

9. **Learning Objectives**: List 3-5 key learning objectives based on the notebook content

10. **Assignment Structure**: Describe whether it's structured or free-form, and list activities if applicable

11. **Grading Criteria**: Provide a breakdown of how marks should be distributed (e.g., 60% correctness, 20% code quality, 20% understanding)

CRITICAL OUTPUT INSTRUCTIONS:
- Output ONLY the raw markdown content for overview.md
- Do NOT write to any files yourself - just output the content
- Do NOT include any conversational text like "Here is the overview" or "I have created..."
- Do NOT ask follow-up questions like "What's next?"
- Start your response IMMEDIATELY with the "---" YAML delimiter
- End with the Notes section content (no closing remarks)

Your entire response should be valid markdown that can be directly saved as overview.md.
"""
    return prompt


def call_llm(prompt: str, provider: str, model: str = None, api_model: str = None) -> str:
    """Call the LLM via llm_caller.sh to generate the overview content."""

    # Get the path to llm_caller.sh
    script_dir = Path(__file__).parent
    llm_caller = script_dir / "llm_caller.sh"

    if not llm_caller.exists():
        raise FileNotFoundError(f"llm_caller.sh not found at {llm_caller}")

    # Call llm_caller.sh in headless mode
    cmd = [
        str(llm_caller),
        "--prompt", prompt,
        "--mode", "headless",
        "--provider", provider,
        "--auto-approve"  # Skip permission prompts for automated operation
    ]

    if model:
        cmd.extend(["--model", model])

    if api_model:
        cmd.extend(["--api-model", api_model])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=300  # 5-minute timeout to prevent hanging
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        print("Error: LLM call timed out after 5 minutes", file=sys.stderr)
        sys.exit(1)
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
  %(prog)s assignments/lab1/notebook.ipynb --model claude-sonnet-4
  %(prog)s path/to/notebook.ipynb --model gemini-2.5-pro
  %(prog)s notebook.ipynb --provider claude
        """
    )

    parser.add_argument(
        'notebook',
        type=Path,
        help='Path to the Jupyter notebook (.ipynb file)'
    )

    parser.add_argument(
        '--model',
        help='Model to use (provider auto-resolved from model name)'
    )

    parser.add_argument(
        '--provider',
        choices=['claude', 'gemini', 'codex'],
        help='LLM provider (optional if --model is specified)'
    )

    parser.add_argument(
        '--api-model',
        dest='api_model',
        help='Model for direct API calls (headless only, requires API key)'
    )

    args = parser.parse_args()

    # Resolve provider from model if not specified
    provider = args.provider
    model = args.model
    api_model = args.api_model

    # Resolve provider: --api-model takes priority if no --provider/--model
    if not provider and api_model and not model:
        provider = resolve_provider_from_model(api_model)
        if not provider:
            print(f"Error: Unknown API model '{api_model}'", file=sys.stderr)
            print("", file=sys.stderr)
            print(format_available_models(), file=sys.stderr)
            sys.exit(1)

    if not provider and model:
        provider = resolve_provider_from_model(model)
        if not provider:
            print(f"Error: Unknown model '{model}'", file=sys.stderr)
            print("", file=sys.stderr)
            print(format_available_models(), file=sys.stderr)
            sys.exit(1)

    if not provider and not model and not api_model:
        print("Error: --model, --provider, or --api-model is required", file=sys.stderr)
        sys.exit(1)

    if not provider:
        print("Error: Could not determine provider", file=sys.stderr)
        sys.exit(1)

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
    print(f"Using provider: {provider}")
    if model:
        print(f"Using model: {model}")
    if api_model:
        print(f"Using API model: {api_model}")
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

    # Create prompt (use model name if provided, otherwise just provider name for template)
    model_for_template = model or api_model or provider
    prompt = create_prompt(notebook_path, notebook_summary, provider, model_for_template)

    # Call LLM to generate overview
    print("Calling LLM to generate overview.md...")
    print("This may take a moment...")
    print()

    try:
        overview_content = call_llm(prompt, provider, model, api_model)
    except Exception as e:
        print(f"Error generating overview: {e}", file=sys.stderr)
        sys.exit(1)

    # Strip markdown code block wrapper if present
    overview_content = overview_content.strip()
    if overview_content.startswith('```markdown'):
        overview_content = overview_content[len('```markdown'):].strip()
    elif overview_content.startswith('```'):
        overview_content = overview_content[3:].strip()
    if overview_content.endswith('```'):
        overview_content = overview_content[:-3].strip()

    # Validate the content is actual overview.md content, not conversational response
    if not overview_content.startswith('---'):
        print(f"Error: LLM returned conversational response instead of overview content:", file=sys.stderr)
        print(f"  Response starts with: {overview_content[:100]}...", file=sys.stderr)
        print(f"  Expected response to start with '---' (YAML front matter)", file=sys.stderr)
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
