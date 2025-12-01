#!/usr/bin/env python3
"""
Create interactive adjustment dashboard for marking scheme approval.

Generates a Jupyter notebook with ipywidgets for instructor to adjust
mark deductions and see live distribution updates.
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List


def create_dashboard_notebook(
    normalized_data_path: str,
    student_mappings_path: str,
    output_path: str,
    assignment_type: str = "structured"
) -> str:
    """
    Create an interactive Jupyter notebook dashboard.

    Args:
        normalized_data_path: Path to normalized scoring JSON
        student_mappings_path: Path to per-student mistake/positive mappings JSON
        output_path: Where to save the notebook
        assignment_type: "structured" or "freeform"

    Returns:
        Path to created notebook
    """
    # Load data to get activity marks
    with open(normalized_data_path, 'r') as f:
        normalized_data = json.load(f)

    activity_marks = normalized_data.get('activity_marks', {})

    # Create notebook structure
    notebook = {
        "cells": [],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "name": "python",
                "version": "3.8.0"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 4
    }

    # Title cell
    notebook["cells"].append(_markdown_cell(f"""
# Marking Scheme Adjustment Dashboard

This interactive dashboard allows you to:
1. Review normalized mistake and positive point assessments
2. Adjust mark deductions and bonuses
3. See live mark distribution updates
4. Approve final marking scheme

**Assignment Type**: {assignment_type.title()}
**Activity Allocations**: {', '.join([f'{k}={v}' for k, v in sorted(activity_marks.items())])}
    """.strip()))

    # Cell 1: Imports
    notebook["cells"].append(_code_cell("""
# @title Import Required Libraries

import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import ipywidgets as widgets

from IPython.display import display, clear_output
from pathlib import Path
from ipywidgets import interact, interactive, fixed, interact_manual, widgets
    """))

    # Cell 2: Plotting setup
    notebook["cells"].append(_code_cell("""
# @title Configure Plotting and Display Settings

# Set up plotting
%matplotlib inline

plt.style.use('seaborn-v0_8-darkgrid')

# Configure pandas to show all rows
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
pd.set_option('display.max_colwidth', 100)
    """))

    # Cell 3: Load data
    notebook["cells"].append(_code_cell(f"""
# @title Load Scoring Data and Student Mappings

# Load normalized scoring data
with open('{normalized_data_path}', 'r') as f:
    normalized_data = json.load(f)

# Load per-student mappings
with open('{student_mappings_path}', 'r') as f:
    student_mappings = json.load(f)
    """))

    # Cell 4: Extract and display summary
    notebook["cells"].append(_code_cell("""
# @title Extract Data and Display Summary

# Extract mistakes and positives
mistakes = normalized_data.get('mistakes', [])
positives = normalized_data.get('positives', [])
total_marks = normalized_data.get('total_marks', 100)
activity_marks = normalized_data.get('activity_marks', {})

# Remove metadata from student mappings
students = {k: v for k, v in student_mappings.items() if not k.startswith('_')}

print(f"✓ Loaded {len(mistakes)} mistake types and {len(positives)} positive types")
print(f"✓ Total marks available: {total_marks}")
print(f"✓ Activity allocations: {activity_marks}")
print(f"✓ Students with mappings: {len(students)}")
    """))

    # Mistakes table cell
    notebook["cells"].append(_markdown_cell("## Mistake Deductions\n\nReview the mark deductions for each mistake type:"))

    notebook["cells"].append(_code_cell("""
# @title Display Mistakes Table

# Create DataFrame for mistakes
mistakes_df = pd.DataFrame(mistakes)

# Rename columns for better readability
mistakes_df_display = mistakes_df.rename(columns={
    'id': 'ID',
    'description': 'Description',
    'frequency': 'Students Affected',
    'severity': 'Severity (1-10)',
    'suggested_deduction': 'Suggested Deduction (marks)',
    'activity': 'Activity',
    'activity_marks': 'Activity Total (marks)'
})

print(f"Total mistake types: {len(mistakes_df)}")
display(mistakes_df_display[['ID', 'Activity', 'Activity Total (marks)', 'Description',
                               'Students Affected', 'Severity (1-10)', 'Suggested Deduction (marks)']])
    """))

    # Positives table cell
    notebook["cells"].append(_markdown_cell("## Positive Bonuses\n\nReview bonus points for positive achievements:"))

    notebook["cells"].append(_code_cell("""
# @title Display Positives Table

# Create DataFrame for positives
positives_df = pd.DataFrame(positives)

# Rename columns for better readability
positives_df_display = positives_df.rename(columns={
    'id': 'ID',
    'description': 'Description',
    'frequency': 'Students Demonstrating',
    'quality': 'Quality (1-10)',
    'suggested_bonus': 'Suggested Bonus (marks)',
    'activity': 'Activity',
    'activity_marks': 'Activity Total (marks)'
})

print(f"Total positive types: {len(positives_df)}")
display(positives_df_display[['ID', 'Activity', 'Activity Total (marks)', 'Description',
                               'Students Demonstrating', 'Quality (1-10)', 'Suggested Bonus (marks)']])
    """))

    # Interactive adjustment cell
    notebook["cells"].append(_markdown_cell("""
## Interactive Mark Adjustment

Use the sliders below to adjust deductions and bonuses. The distribution will update automatically.
    """))

    notebook["cells"].append(_code_cell("""
# @title Create Adjustment Sliders for Mistakes

# Create adjustment widgets for mistakes
mistake_widgets = {}
mistake_checkboxes = {}

for _, mistake in mistakes_df.iterrows():
    mistake_id = mistake['id']
    description = mistake['description']
    suggested = float(mistake['suggested_deduction'])
    activity_id = mistake['activity']
    activity_total = mistake.get('activity_marks', 100)

    # Truncate description for display
    desc_short = description[:60] + '...' if len(description) > 60 else description

    # Create label with activity context
    label = f"{mistake_id} ({activity_total}marks): {desc_short}"

    # Create checkbox (checked by default)
    mistake_checkboxes[mistake_id] = widgets.Checkbox(
        value=True,
        description='Include in feedback',
        indent=False,
        layout=widgets.Layout(width='200px')
    )

    # Create slider
    mistake_widgets[mistake_id] = widgets.FloatSlider(
        value=suggested,
        min=0,
        max=activity_total,  # Max is the total marks for this activity
        step=0.5,
        description=mistake_id,
        style={'description_width': '120px'},
        layout=widgets.Layout(width='600px'),
        continuous_update=False
    )

    # Display: label, checkbox, and slider in a row
    display(widgets.HTML(f"<b>{label}</b>"))
    display(widgets.HBox([mistake_checkboxes[mistake_id], mistake_widgets[mistake_id]]))

print(f"\\n✓ Created {len(mistake_widgets)} mistake adjustment sliders with checkboxes")
    """))

    notebook["cells"].append(_code_cell("""
# @title Create Adjustment Sliders for Positives

# Create adjustment widgets for positives
positive_widgets = {}
positive_checkboxes = {}

for _, positive in positives_df.iterrows():
    positive_id = positive['id']
    description = positive['description']
    suggested = float(positive['suggested_bonus'])
    activity_id = positive['activity']
    activity_total = positive.get('activity_marks', 10)

    # Truncate description for display
    desc_short = description[:60] + '...' if len(description) > 60 else description

    # Create label with activity context
    label = f"{positive_id} ({activity_total}marks): {desc_short}"

    # Create checkbox (checked by default)
    positive_checkboxes[positive_id] = widgets.Checkbox(
        value=True,
        description='Include in feedback',
        indent=False,
        layout=widgets.Layout(width='200px')
    )

    # Create slider
    positive_widgets[positive_id] = widgets.FloatSlider(
        value=suggested,
        min=0,
        max=min(suggested * 2, 10),  # Bonuses typically smaller
        step=0.5,
        description=positive_id,
        style={'description_width': '120px'},
        layout=widgets.Layout(width='600px'),
        continuous_update=False
    )

    # Display: label, checkbox, and slider in a row
    display(widgets.HTML(f"<b>{label}</b>"))
    display(widgets.HBox([positive_checkboxes[positive_id], positive_widgets[positive_id]]))

print(f"\\n✓ Created {len(positive_widgets)} positive adjustment sliders with checkboxes")
    """))

    # Calculation function
    notebook["cells"].append(_code_cell("""
# @title Define Mark Calculation Functions

def calculate_marks(mistake_vals, positive_vals, mistake_checks, positive_checks):
    \"\"\"Calculate marks for all students based on current adjustments.\"\"\"
    marks = {}

    # Filter out metadata keys
    student_data = {k: v for k, v in students.items() if not k.startswith('_')}

    for student_name, mapping in student_data.items():
        student_mark = total_marks

        # Apply mistake deductions (only if checkbox is enabled)
        for mistake_id in mapping.get('mistakes', []):
            if mistake_id in mistake_vals and mistake_checks.get(mistake_id, True):
                student_mark -= mistake_vals[mistake_id]

        # Apply positive bonuses (only if checkbox is enabled)
        for positive_id in mapping.get('positives', []):
            if positive_id in positive_vals and positive_checks.get(positive_id, True):
                student_mark += positive_vals[positive_id]

        # Clamp to valid range
        student_mark = max(0, min(total_marks, student_mark))
        marks[student_name] = student_mark

    return marks

def plot_distribution(marks_dict):
    \"\"\"Plot histogram of mark distribution.\"\"\"
    if not marks_dict:
        print("⚠️  No student data available for distribution")
        return

    marks = list(marks_dict.values())

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Histogram
    ax1.hist(marks, bins=20, edgecolor='black', alpha=0.7)
    ax1.set_xlabel('Marks')
    ax1.set_ylabel('Number of Students')
    ax1.set_title('Mark Distribution')
    ax1.axvline(np.mean(marks), color='red', linestyle='--', label=f'Mean: {np.mean(marks):.1f}')
    ax1.axvline(np.median(marks), color='green', linestyle='--', label=f'Median: {np.median(marks):.1f}')
    ax1.legend()

    # Grade bands
    grade_bands = {
        'A (90-100%)': len([m for m in marks if m >= total_marks * 0.9]),
        'B (80-89%)': len([m for m in marks if total_marks * 0.8 <= m < total_marks * 0.9]),
        'C (70-79%)': len([m for m in marks if total_marks * 0.7 <= m < total_marks * 0.8]),
        'D (60-69%)': len([m for m in marks if total_marks * 0.6 <= m < total_marks * 0.7]),
        'F (<60%)': len([m for m in marks if m < total_marks * 0.6]),
    }

    ax2.bar(grade_bands.keys(), grade_bands.values(), edgecolor='black', alpha=0.7)
    ax2.set_xlabel('Grade Band')
    ax2.set_ylabel('Number of Students')
    ax2.set_title('Grade Distribution')
    ax2.tick_params(axis='x', rotation=45)

    plt.tight_layout()
    plt.show()

    # Statistics
    print("\\nStatistics:")
    print(f"  Mean: {np.mean(marks):.2f} / {total_marks}")
    print(f"  Median: {np.median(marks):.2f} / {total_marks}")
    print(f"  Std Dev: {np.std(marks):.2f}")
    print(f"  Min: {np.min(marks):.2f} / {total_marks}")
    print(f"  Max: {np.max(marks):.2f} / {total_marks}")
    print(f"\\nGrade Distribution:")
    for band, count in grade_bands.items():
        percentage = (count/len(marks)*100) if len(marks) > 0 else 0
        print(f"  {band}: {count} students ({percentage:.1f}%)")

def update_display():
    \"\"\"Update marks and distribution based on current widget values.\"\"\"
    clear_output(wait=True)
    # Collect slider values
    mistake_vals = {k: w.value for k, w in mistake_widgets.items()}
    positive_vals = {k: w.value for k, w in positive_widgets.items()}
    # Collect checkbox states
    mistake_checks = {k: w.value for k, w in mistake_checkboxes.items()}
    positive_checks = {k: w.value for k, w in positive_checkboxes.items()}
    marks = calculate_marks(mistake_vals, positive_vals, mistake_checks, positive_checks)
    plot_distribution(marks)
    return marks

print("✓ Calculation functions defined")
    """))

    # Interactive display
    notebook["cells"].append(_markdown_cell("""
## Mark Distribution

The chart below updates as you adjust sliders above. Click "Update Distribution" to refresh.
    """))

    notebook["cells"].append(_code_cell("""
# @title Display Mark Distribution (Interactive)

# Create update button
update_button = widgets.Button(
    description="Update Distribution",
    button_style='success',
    icon='refresh'
)
output = widgets.Output()

def on_update_click(b):
    with output:
        current_marks = update_display()

update_button.on_click(on_update_click)
display(update_button)
display(output)

# Initial display
with output:
    current_marks = update_display()
    """))

    # Save scheme cell
    notebook["cells"].append(_markdown_cell("""
## Save Approved Scheme

Once you're satisfied with the mark distribution, run the cell below to save the approved scheme.
    """))

    notebook["cells"].append(_code_cell("""
# @title Save Approved Marking Scheme

def save_approved_scheme(output_path='approved_scheme.json'):
    \"\"\"Save the approved marking scheme.\"\"\"
    scheme = {
        'total_marks': total_marks,
        'activity_marks': activity_marks,
        'mistakes': {},
        'positives': {},
        'excluded_mistakes': [],
        'excluded_positives': [],
        'timestamp': pd.Timestamp.now().isoformat()
    }

    # Only include items where checkbox is enabled
    for mistake_id, widget in mistake_widgets.items():
        if mistake_checkboxes[mistake_id].value:
            scheme['mistakes'][mistake_id] = float(widget.value)
        else:
            scheme['excluded_mistakes'].append(mistake_id)

    for positive_id, widget in positive_widgets.items():
        if positive_checkboxes[positive_id].value:
            scheme['positives'][positive_id] = float(widget.value)
        else:
            scheme['excluded_positives'].append(positive_id)

    with open(output_path, 'w') as f:
        json.dump(scheme, f, indent=2)

    print(f"✓ Approved scheme saved to: {output_path}")
    print(f"  - {len(scheme['mistakes'])} mistake deductions (included)")
    print(f"  - {len(scheme['excluded_mistakes'])} mistakes excluded from feedback")
    print(f"  - {len(scheme['positives'])} positive bonuses (included)")
    print(f"  - {len(scheme['excluded_positives'])} positives excluded from feedback")
    print(f"\\nYou may now close this notebook and continue the marking process.")

    return scheme

# Run this cell to save
approved_scheme = save_approved_scheme('approved_scheme.json')
    """))

    # Write notebook to file
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump(notebook, f, indent=2)

    return str(output_file)


def _markdown_cell(text: str) -> Dict:
    """Create a markdown cell."""
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": text.split('\n')
    }


def _code_cell(code: str) -> Dict:
    """Create a code cell."""
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": code.strip().split('\n')
    }


def main():
    """CLI interface."""
    parser = argparse.ArgumentParser(
        description="Create interactive marking adjustment dashboard"
    )
    parser.add_argument(
        "normalized_data",
        help="Path to normalized scoring JSON"
    )
    parser.add_argument(
        "student_mappings",
        help="Path to student mistake/positive mappings JSON"
    )
    parser.add_argument(
        "-o", "--output",
        default="adjustment_dashboard.ipynb",
        help="Output notebook path"
    )
    parser.add_argument(
        "-t", "--type",
        choices=["structured", "freeform"],
        default="structured",
        help="Assignment type"
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve the scheme without instructor interaction"
    )

    args = parser.parse_args()

    notebook_path = create_dashboard_notebook(
        args.normalized_data,
        args.student_mappings,
        args.output,
        args.type
    )

    print(f"✓ Dashboard created: {notebook_path}")

    if args.auto_approve:
        # Auto-approve: create approved_scheme.json using the default values
        print("Auto-approving marking scheme...")
        output_dir = Path(args.output).parent
        approved_scheme_path = output_dir / "approved_scheme.json"

        # Load the normalized data to extract the scheme
        with open(args.normalized_data, 'r') as f:
            normalized_data = json.load(f)

        # Create approved scheme with default values (LLM-suggested deductions)
        approved_scheme = {
            "approved": True,
            "auto_approved": True,
            "activity_marks": normalized_data.get("activity_marks", {}),
            "mistakes": normalized_data.get("mistakes", {}),
            "positives": normalized_data.get("positives", {}),
            "total_marks": normalized_data.get("total_marks", 100)
        }

        with open(approved_scheme_path, 'w') as f:
            json.dump(approved_scheme, f, indent=2)

        print(f"✓ Scheme auto-approved: {approved_scheme_path}")
    else:
        print(f"\nTo use:")
        print(f"  jupyter notebook \"{notebook_path}\"")


if __name__ == "__main__":
    main()
