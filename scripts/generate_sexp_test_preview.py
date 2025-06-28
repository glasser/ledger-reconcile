#!/usr/bin/env python3
# Generate HTML preview of S-expression test fixtures
# This script creates an HTML file that displays all test cases for easy review

import json
from pathlib import Path

from jinja2 import Template


def generate_preview():
    """Generate HTML preview of test fixtures."""
    script_dir = Path(__file__).parent
    fixtures_dir = script_dir.parent / "tests" / "fixtures" / "sexp_parser"
    template_file = script_dir / "test_fixture_template.html"
    output_file = script_dir.parent / "docs" / "sexp_test_fixtures.html"

    # Ensure output directory exists
    output_file.parent.mkdir(exist_ok=True)

    # Load template
    template = Template(template_file.read_text())

    tests = []
    passing_tests = 0
    xfail_tests = 0
    error_tests = 0

    # Collect all test fixtures
    for sexp_file in sorted(fixtures_dir.glob("*.sexp")):
        json_file = sexp_file.with_suffix(".json")
        if not json_file.exists():
            continue

        name = sexp_file.stem

        # Read files
        with sexp_file.open(encoding="utf-8") as f:
            sexp_content = f.read()

        with json_file.open(encoding="utf-8") as f:
            json_content = json.load(f)

        # Determine test status
        is_bug = name.startswith("bug_")
        is_error = isinstance(json_content, dict) and "error" in json_content

        if is_bug:
            css_class = "bug"
            status = "xfail"
            status_label = "XFAIL"
            xfail_tests += 1
            if is_error:
                notes = "Known bug: this should raise an error but currently doesn't (or raises wrong error)."
            else:
                notes = "Known bug: this currently parses to wrong output or fails when it should succeed."
        elif is_error:
            css_class = "error"
            status = "error"
            status_label = "ERROR"
            error_tests += 1
            notes = "This input should raise an error when parsed."
        else:
            css_class = ""
            status = "pass"
            status_label = "PASS"
            passing_tests += 1
            notes = ""

        # Format JSON for display
        if is_error:
            json_display = f"Error: {json_content['error']}"
        else:
            json_display = json.dumps(json_content, ensure_ascii=False, indent=2)

        tests.append(
            {
                "name": name.replace("_", " ").title(),
                "sexp_content": sexp_content,
                "json_display": json_display,
                "css_class": css_class,
                "status": status,
                "status_label": status_label,
                "is_error": is_error,
                "notes": notes,
            }
        )

    # Render template
    html = template.render(
        tests=tests,
        total_tests=len(tests),
        passing_tests=passing_tests,
        xfail_tests=xfail_tests,
        error_tests=error_tests,
    )

    # Write output
    output_file.write_text(html)
    print(f"Generated test fixture preview: {output_file}")
    print(f"Total tests: {len(tests)}")
    print(f"  - Passing: {passing_tests}")
    print(f"  - Known bugs: {xfail_tests}")
    print(f"  - Error cases: {error_tests}")


if __name__ == "__main__":
    generate_preview()
