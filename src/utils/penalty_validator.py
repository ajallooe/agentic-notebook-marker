#!/usr/bin/env python3
"""
Penalty Validator - Detects artificial/excessive penalties in normalized scoring files.

This script runs after the normalizer stage and before instructor review to catch
common grading issues:
1. Penalties that exceed activity marks
2. Penalties affecting 80%+ of students (likely criteria issues)
3. Style issues treated as major correctness errors
4. Penalties that conflate multiple activities
5. Unreasonably low class averages

Usage:
    python penalty_validator.py <assignment_dir> [--fix] [--report-only]
"""

import argparse
import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidationIssue:
    """Represents a detected validation issue."""
    severity: str  # 'error', 'warning', 'info'
    activity: str
    rule: str
    message: str
    suggestion: str
    penalty_id: Optional[str] = None


class PenaltyValidator:
    """Validates normalized scoring files for artificial/excessive penalties."""

    def __init__(self, assignment_dir: Path):
        self.assignment_dir = Path(assignment_dir)
        self.normalized_dir = self.assignment_dir / "processed" / "normalized"
        self.rubric_path = self.assignment_dir / "processed" / "rubric.md"
        self.issues: list[ValidationIssue] = []
        self.activity_marks: dict[str, float] = {}

    def load_rubric(self) -> bool:
        """Load rubric and extract per-activity marks."""
        if not self.rubric_path.exists():
            print(f"Warning: Rubric not found at {self.rubric_path}")
            return False

        rubric_text = self.rubric_path.read_text()

        # Try to extract activity marks from rubric
        # Pattern: A1 ... (X marks) or Activity 1: X marks
        patterns = [
            r'\[?A(\d+)\]?[^\d]*?(\d+)\s*(?:marks?|points?)',
            r'Activity\s*(\d+)[^\d]*?(\d+)\s*(?:marks?|points?)',
            r'\*\*\[A(\d+)\]\*\*[^\d]*?(\d+)\s*(?:marks?|points?)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, rubric_text, re.IGNORECASE)
            for match in matches:
                activity_num, marks = match
                self.activity_marks[f"A{activity_num}"] = float(marks)

        return len(self.activity_marks) > 0

    def parse_scoring_file(self, filepath: Path) -> dict:
        """Parse a normalized scoring file and extract penalties."""
        content = filepath.read_text()
        result = {
            'penalties': [],
            'positives': [],
            'student_count': 0,
            'activity': filepath.stem.replace('_scoring', '')
        }

        # Extract student count
        student_match = re.search(r'(\d+)/(\d+)\s*students?', content)
        if student_match:
            result['student_count'] = int(student_match.group(2))

        # Parse mistakes table
        # Look for table rows with pattern: | M001 | description | X/Y students | severity | deduction |
        mistake_pattern = r'\|\s*(M\d{3})\s*\|\s*([^|]+)\s*\|\s*(\d+)/(\d+)\s*students?\s*\|\s*(\d+)\s*\|\s*(-?\d+(?:\.\d+)?)\s*\|'
        for match in re.finditer(mistake_pattern, content, re.IGNORECASE):
            result['penalties'].append({
                'id': match.group(1),
                'description': match.group(2).strip(),
                'affected': int(match.group(3)),
                'total': int(match.group(4)),
                'severity': int(match.group(5)),
                'deduction': abs(float(match.group(6)))
            })
            if result['student_count'] == 0:
                result['student_count'] = int(match.group(4))

        return result

    def validate_penalty_cap(self, activity: str, penalties: list[dict]) -> None:
        """Rule 2: No penalty should exceed activity's total marks."""
        activity_max = self.activity_marks.get(activity, 100)

        for penalty in penalties:
            if penalty['deduction'] > activity_max:
                self.issues.append(ValidationIssue(
                    severity='error',
                    activity=activity,
                    rule='penalty_cap',
                    penalty_id=penalty['id'],
                    message=f"Penalty {penalty['id']} deducts {penalty['deduction']} points, "
                            f"but {activity} is only worth {activity_max} marks.",
                    suggestion=f"Cap deduction at {activity_max} or reduce to a proportion of activity marks."
                ))

    def validate_high_frequency(self, activity: str, penalties: list[dict], student_count: int) -> None:
        """Rule 3: Flag penalties affecting 80%+ of students."""
        if student_count == 0:
            return

        for penalty in penalties:
            frequency = penalty['affected'] / student_count
            if frequency >= 0.80:
                self.issues.append(ValidationIssue(
                    severity='warning',
                    activity=activity,
                    rule='high_frequency',
                    penalty_id=penalty['id'],
                    message=f"Penalty {penalty['id']} affects {penalty['affected']}/{student_count} "
                            f"({frequency:.0%}) students. This suggests a criteria issue, not student failure.",
                    suggestion="Re-examine if this requirement actually exists in the rubric. "
                               "If 80%+ of students 'fail' the same thing, the criteria may be wrong."
                ))

            # Special case: 100% failure rate
            if frequency >= 0.99:
                self.issues.append(ValidationIssue(
                    severity='error',
                    activity=activity,
                    rule='universal_failure',
                    penalty_id=penalty['id'],
                    message=f"Penalty {penalty['id']} affects ALL students ({penalty['affected']}/{student_count}). "
                            f"This almost certainly indicates a criteria error.",
                    suggestion="REMOVE this penalty. When 100% of students 'fail', the requirement "
                               "is either not in the original assignment or was misinterpreted."
                ))

    def validate_style_vs_correctness(self, activity: str, penalties: list[dict]) -> None:
        """Rule 4: Style issues should have low severity."""
        style_keywords = [
            'variable name', 'naming', 'not stored', 'not printed', 'print statement',
            'unused import', 'comment', 'documentation', 'formatting', 'style',
            'placeholder', 'implicit', 'explicit print', 'display'
        ]

        for penalty in penalties:
            desc_lower = penalty['description'].lower()
            is_style_issue = any(kw in desc_lower for kw in style_keywords)

            if is_style_issue and penalty['severity'] > 4:
                self.issues.append(ValidationIssue(
                    severity='warning',
                    activity=activity,
                    rule='style_vs_correctness',
                    penalty_id=penalty['id'],
                    message=f"Penalty {penalty['id']} appears to be a style issue "
                            f"but has severity {penalty['severity']}/10.",
                    suggestion="Style issues (naming, printing, comments) should have severity ≤4. "
                               "If code works correctly, style issues should not cause major mark loss."
                ))

    def validate_activity_scope(self, activity: str, penalties: list[dict]) -> None:
        """Rule 1: Penalties should only relate to this activity."""
        # Look for penalties that reference other activities
        other_activity_pattern = r'\b(A[1-9]|activity\s*[1-9]|task\s*[1-9])\b'

        for penalty in penalties:
            desc = penalty['description']
            matches = re.findall(other_activity_pattern, desc, re.IGNORECASE)

            # Filter out references to current activity
            current_num = re.search(r'\d+', activity)
            if current_num:
                matches = [m for m in matches if current_num.group() not in m]

            if matches:
                self.issues.append(ValidationIssue(
                    severity='warning',
                    activity=activity,
                    rule='activity_scope',
                    penalty_id=penalty['id'],
                    message=f"Penalty {penalty['id']} may reference other activities: {matches}. "
                            f"Each activity's penalties should only relate to that activity.",
                    suggestion="Ensure this penalty is about the current activity only. "
                               "Do not combine requirements from multiple activities."
                ))

    def validate_total_deductions(self, activity: str, penalties: list[dict]) -> None:
        """Check if total possible deductions exceed activity marks."""
        activity_max = self.activity_marks.get(activity, 100)
        total_deductions = sum(p['deduction'] for p in penalties)

        if total_deductions > activity_max * 1.5:  # Allow some overlap for mutually exclusive penalties
            self.issues.append(ValidationIssue(
                severity='warning',
                activity=activity,
                rule='total_deductions',
                penalty_id=None,
                message=f"Total possible deductions ({total_deductions}) significantly exceed "
                        f"activity marks ({activity_max}).",
                suggestion="Review penalties to ensure they're not overlapping or excessive. "
                           "Students shouldn't be able to lose more than 100% of activity marks."
            ))

    def validate(self) -> list[ValidationIssue]:
        """Run all validations on normalized scoring files."""
        self.issues = []

        # Load rubric for activity marks
        self.load_rubric()

        # Find and validate all scoring files
        scoring_files = list(self.normalized_dir.glob("*_scoring.md"))
        if not scoring_files:
            print(f"No scoring files found in {self.normalized_dir}")
            return self.issues

        for filepath in scoring_files:
            data = self.parse_scoring_file(filepath)
            activity = data['activity']
            penalties = data['penalties']
            student_count = data['student_count']

            if not penalties:
                continue

            # Run all validation rules
            self.validate_penalty_cap(activity, penalties)
            self.validate_high_frequency(activity, penalties, student_count)
            self.validate_style_vs_correctness(activity, penalties)
            self.validate_activity_scope(activity, penalties)
            self.validate_total_deductions(activity, penalties)

        return self.issues

    def generate_report(self) -> str:
        """Generate a human-readable validation report."""
        if not self.issues:
            return "✅ No validation issues found. Penalties appear reasonable.\n"

        errors = [i for i in self.issues if i.severity == 'error']
        warnings = [i for i in self.issues if i.severity == 'warning']
        infos = [i for i in self.issues if i.severity == 'info']

        lines = [
            "=" * 70,
            "PENALTY VALIDATION REPORT",
            "=" * 70,
            "",
            f"Found {len(errors)} errors, {len(warnings)} warnings, {len(infos)} info messages.",
            ""
        ]

        if errors:
            lines.append("🚨 ERRORS (must be fixed before instructor review):")
            lines.append("-" * 50)
            for issue in errors:
                lines.append(f"\n[{issue.activity}] {issue.rule}")
                if issue.penalty_id:
                    lines.append(f"  Penalty: {issue.penalty_id}")
                lines.append(f"  Issue: {issue.message}")
                lines.append(f"  Fix: {issue.suggestion}")
            lines.append("")

        if warnings:
            lines.append("⚠️  WARNINGS (should be reviewed):")
            lines.append("-" * 50)
            for issue in warnings:
                lines.append(f"\n[{issue.activity}] {issue.rule}")
                if issue.penalty_id:
                    lines.append(f"  Penalty: {issue.penalty_id}")
                lines.append(f"  Issue: {issue.message}")
                lines.append(f"  Fix: {issue.suggestion}")
            lines.append("")

        lines.extend([
            "=" * 70,
            "ACTION REQUIRED:",
            "- Fix all ERRORS before proceeding to instructor review",
            "- Review WARNINGS and adjust if appropriate",
            "- Re-run normalization if significant changes are needed",
            "=" * 70,
        ])

        return "\n".join(lines)

    def save_report(self, output_path: Optional[Path] = None) -> Path:
        """Save validation report to file."""
        if output_path is None:
            output_path = self.assignment_dir / "processed" / "logs" / "penalty_validation.txt"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        report = self.generate_report()
        output_path.write_text(report)
        return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Validate normalized scoring files for artificial/excessive penalties."
    )
    parser.add_argument("assignment_dir", help="Path to assignment directory")
    parser.add_argument("--report-only", action="store_true",
                        help="Only generate report, don't exit with error code")
    parser.add_argument("--output", "-o", help="Output file for report")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    validator = PenaltyValidator(Path(args.assignment_dir))
    issues = validator.validate()

    if args.json:
        output = json.dumps([
            {
                'severity': i.severity,
                'activity': i.activity,
                'rule': i.rule,
                'penalty_id': i.penalty_id,
                'message': i.message,
                'suggestion': i.suggestion
            }
            for i in issues
        ], indent=2)
        print(output)
    else:
        report = validator.generate_report()
        print(report)

        if args.output:
            Path(args.output).write_text(report)
            print(f"\nReport saved to: {args.output}")

    # Exit with error if there are errors (unless report-only mode)
    if not args.report_only:
        errors = [i for i in issues if i.severity == 'error']
        if errors:
            print(f"\n❌ {len(errors)} error(s) found. Fix before proceeding.")
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
