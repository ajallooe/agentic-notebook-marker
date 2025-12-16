#!/usr/bin/env python3
"""
Name Resolver Agent - LLM-based student name extraction and matching.

This agent runs after the pattern designer to establish canonical student names
by having an LLM analyze submission file paths and match against gradebook entries.

The LLM is the primary mechanism for name inference - it can handle:
- Creative/non-standard filename patterns
- Misspellings and truncations
- Names embedded in various parts of the path
- Matching to gradebook entries when provided
"""

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add src/utils to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))


class NameResolver:
    """LLM-based name resolution from submission paths to canonical names."""

    def __init__(self, assignment_dir: str, gradebook_paths: List[str] = None):
        """
        Initialize the name resolver.

        Args:
            assignment_dir: Path to assignment directory
            gradebook_paths: Optional list of gradebook CSV paths
        """
        self.assignment_dir = Path(assignment_dir)
        self.assignment_name = self.assignment_dir.name
        self.gradebook_paths = gradebook_paths or []

        # Data structures
        self.gradebook_names = []  # List of canonical names from gradebook
        self.submission_paths = []  # List of relative paths to submissions
        self.name_mapping = {}  # path -> canonical name

    def load_gradebook_names(self) -> List[str]:
        """Load unique student names from gradebooks."""
        names = set()

        for gradebook_path in self.gradebook_paths:
            if not os.path.exists(gradebook_path):
                print(f"WARNING: Gradebook not found: {gradebook_path}")
                continue

            try:
                with open(gradebook_path, 'r', encoding='utf-8-sig') as f:
                    content = f.read()

                # Strip BOM if present
                if content.startswith('\ufeff'):
                    content = content[1:]

                lines = content.split('\n')
                reader = csv.DictReader(lines)

                for row in reader:
                    first = row.get('First name', '').strip()
                    last = row.get('Last name', '').strip()

                    if first:
                        full_name = f"{first} {last}".strip()
                        names.add(full_name)

            except Exception as e:
                print(f"ERROR loading gradebook {gradebook_path}: {e}")

        self.gradebook_names = sorted(names)
        return self.gradebook_names

    def find_submission_paths(self) -> List[str]:
        """Find all submission paths relative to submissions directory."""
        submissions_dir = self.assignment_dir / 'submissions'

        if not submissions_dir.exists():
            print(f"WARNING: Submissions directory not found: {submissions_dir}")
            return []

        paths = []
        for notebook_path in submissions_dir.rglob("*.ipynb"):
            rel_path = notebook_path.relative_to(submissions_dir)
            paths.append(str(rel_path))

        self.submission_paths = sorted(paths)
        return self.submission_paths

    def build_prompt(self, output_path: str) -> str:
        """Build the prompt for the LLM agent."""
        script_dir = Path(__file__).parent.parent
        template_path = script_dir / 'prompts' / 'name_resolver.md'

        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        # Build gradebook section
        if self.gradebook_names:
            gradebook_section = f"""## Gradebook Names (Source of Truth)

These are the official student names from the gradebook. Match extracted names to the closest entry:

```
{chr(10).join(self.gradebook_names)}
```

**Important**: The canonical name in your output should match one of these gradebook entries exactly."""
        else:
            gradebook_section = """## No Gradebook Provided

No gradebook was provided, so use the clearest form of the name you can extract from each path."""

        # Format submission paths
        submission_paths = '\n'.join(self.submission_paths)

        # Fill template
        prompt = template.format(
            assignment_name=self.assignment_name,
            total_submissions=len(self.submission_paths),
            gradebook_section=gradebook_section,
            submission_paths=submission_paths,
            output_path=output_path,
        )

        return prompt

    def resolve_names(self, provider: str = None, model: str = None,
                      api_model: str = None, output_path: str = None) -> Dict[str, str]:
        """
        Use LLM to resolve submission paths to canonical names.

        Args:
            provider: LLM provider
            model: Model for CLI calls
            api_model: Model for API calls (headless)
            output_path: Where to save the mapping

        Returns:
            Dictionary mapping submission paths to canonical names
        """
        if not self.gradebook_names and self.gradebook_paths:
            self.load_gradebook_names()

        if not self.submission_paths:
            self.find_submission_paths()

        if not self.submission_paths:
            print("No submissions found")
            return {}

        # Determine output path
        if output_path is None:
            output_path = str(self.assignment_dir / 'processed' / 'name_mapping.json')

        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Build prompt
        prompt = self.build_prompt(output_path)

        # Call LLM
        print(f"Calling LLM to resolve {len(self.submission_paths)} submission names...")
        success = self._call_llm(prompt, provider, model, api_model)

        if success and os.path.exists(output_path):
            # Load the mapping created by LLM
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.name_mapping = data.get('name_mapping', {})
                print(f"Resolved {len(self.name_mapping)} names")
            except Exception as e:
                print(f"Error loading LLM output: {e}")

        return self.name_mapping

    def _call_llm(self, prompt: str, provider: str = None, model: str = None,
                  api_model: str = None) -> bool:
        """Call the LLM using llm_caller.sh."""
        script_dir = Path(__file__).parent.parent
        llm_caller = script_dir / 'llm_caller.sh'

        cmd = [str(llm_caller)]

        # Add model/provider options
        if api_model:
            cmd.extend(['--api-model', api_model])
        elif model:
            cmd.extend(['--model', model])
        elif provider:
            cmd.extend(['--provider', provider])

        # Interactive mode so the LLM can use tools
        cmd.extend(['--mode', 'interactive', '--prompt', prompt])

        try:
            # Run in interactive mode
            result = subprocess.run(
                cmd,
                timeout=300,  # 5 minute timeout
                cwd=str(script_dir.parent)
            )
            return result.returncode == 0

        except subprocess.TimeoutExpired:
            print("LLM call timed out after 5 minutes")
            return False
        except Exception as e:
            print(f"LLM call error: {e}")
            return False

    def get_summary(self) -> dict:
        """Get resolution summary."""
        resolved = len(self.name_mapping)
        total = len(self.submission_paths)

        return {
            'total_submissions': total,
            'resolved': resolved,
            'unresolved': total - resolved,
            'gradebook_entries': len(self.gradebook_names),
        }


def main():
    parser = argparse.ArgumentParser(
        description='LLM-based name resolution from submission paths'
    )
    parser.add_argument('--assignment-dir', required=True,
                        help='Assignment directory')
    parser.add_argument('--gradebooks', nargs='+',
                        help='Gradebook CSV files')
    parser.add_argument('--output', help='Output mapping path')
    parser.add_argument('--provider', help='LLM provider')
    parser.add_argument('--model', help='Model for CLI calls')
    parser.add_argument('--api-model', help='Model for API calls')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show prompt without calling LLM')

    args = parser.parse_args()

    # Find gradebooks if not specified
    gradebook_paths = args.gradebooks
    if not gradebook_paths:
        gradebooks_dir = Path(args.assignment_dir) / 'gradebooks'
        if gradebooks_dir.exists():
            gradebook_paths = [
                str(f) for f in gradebooks_dir.glob('*.csv')
                if '_filled' not in f.name and '_summarized' not in f.name
            ]

    # Create resolver
    resolver = NameResolver(args.assignment_dir, gradebook_paths)

    # Load data
    print(f"Assignment: {resolver.assignment_name}")

    resolver.load_gradebook_names()
    print(f"Gradebook entries: {len(resolver.gradebook_names)}")

    resolver.find_submission_paths()
    print(f"Submissions found: {len(resolver.submission_paths)}")

    if args.dry_run:
        # Just show the prompt
        output_path = args.output or str(
            Path(args.assignment_dir) / 'processed' / 'name_mapping.json'
        )
        prompt = resolver.build_prompt(output_path)
        print("\n" + "="*60)
        print("PROMPT (dry-run)")
        print("="*60)
        print(prompt)
        return

    # Resolve names
    resolver.resolve_names(
        provider=args.provider,
        model=args.model,
        api_model=args.api_model,
        output_path=args.output
    )

    # Print summary
    summary = resolver.get_summary()
    print(f"\n{'='*60}")
    print("RESOLUTION SUMMARY")
    print(f"{'='*60}")
    print(f"Total submissions: {summary['total_submissions']}")
    print(f"Resolved: {summary['resolved']}")
    print(f"Unresolved: {summary['unresolved']}")


if __name__ == '__main__':
    main()
