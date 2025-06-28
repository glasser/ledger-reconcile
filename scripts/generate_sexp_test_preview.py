#!/usr/bin/env python3
# Generate HTML preview of S-expression test fixtures
# This script creates an HTML file that displays all test cases for easy review

import json
from pathlib import Path
from jinja2 import Template

# HTML template
html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>S-Expression Parser Test Fixtures</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }
        .test-case {
            background-color: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            margin-bottom: 20px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .test-case.bug {
            border-color: #ffc107;
            background-color: #fffcf5;
        }
        .test-case.error {
            border-color: #dc3545;
            background-color: #fcf5f5;
        }
        .test-name {
            font-size: 1.2em;
            font-weight: bold;
            color: #007bff;
            margin-bottom: 10px;
        }
        .test-case.bug .test-name {
            color: #f59e0b;
        }
        .test-case.error .test-name {
            color: #dc3545;
        }
        .content-section {
            margin: 10px 0;
        }
        .content-label {
            font-weight: bold;
            color: #666;
            margin-bottom: 5px;
        }
        .content-box {
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 4px;
            padding: 10px;
            font-family: "Consolas", "Monaco", "Courier New", monospace;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .json-content {
            color: #007bff;
        }
        .error-content {
            color: #dc3545;
        }
        .status-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: bold;
            margin-left: 10px;
        }
        .status-pass {
            background-color: #28a745;
            color: white;
        }
        .status-xfail {
            background-color: #ffc107;
            color: #333;
        }
        .status-error {
            background-color: #dc3545;
            color: white;
        }
        .summary {
            background-color: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
        }
        .summary-stats {
            display: flex;
            gap: 30px;
        }
        .stat {
            text-align: center;
        }
        .stat-value {
            font-size: 2em;
            font-weight: bold;
        }
        .stat-label {
            color: #666;
        }
    </style>
</head>
<body>
    <h1>S-Expression Parser Test Fixtures</h1>
    
    <div class="summary">
        <h2>Summary</h2>
        <div class="summary-stats">
            <div class="stat">
                <div class="stat-value">{{ total_tests }}</div>
                <div class="stat-label">Total Tests</div>
            </div>
            <div class="stat">
                <div class="stat-value" style="color: #28a745;">{{ passing_tests }}</div>
                <div class="stat-label">Passing</div>
            </div>
            <div class="stat">
                <div class="stat-value" style="color: #ffc107;">{{ xfail_tests }}</div>
                <div class="stat-label">Known Bugs</div>
            </div>
            <div class="stat">
                <div class="stat-value" style="color: #dc3545;">{{ error_tests }}</div>
                <div class="stat-label">Error Cases</div>
            </div>
        </div>
    </div>

    {% for test in tests %}
    <div class="test-case {{ test.css_class }}">
        <div class="test-name">
            {{ test.name }}
            <span class="status-badge status-{{ test.status }}">{{ test.status_label }}</span>
        </div>
        
        <div class="content-section">
            <div class="content-label">Input (S-Expression):</div>
            <div class="content-box">{{ test.sexp_content }}</div>
        </div>
        
        <div class="content-section">
            <div class="content-label">Expected Output (JSON):</div>
            <div class="content-box {% if test.is_error %}error-content{% else %}json-content{% endif %}">{{ test.json_display }}</div>
        </div>
        
        {% if test.notes %}
        <div class="content-section">
            <div class="content-label">Notes:</div>
            <div>{{ test.notes }}</div>
        </div>
        {% endif %}
    </div>
    {% endfor %}
</body>
</html>
"""


def generate_preview():
    """Generate HTML preview of test fixtures."""
    fixtures_dir = Path(__file__).parent.parent / "tests" / "fixtures" / "sexp_parser"
    output_file = Path(__file__).parent.parent / "docs" / "sexp_test_fixtures.html"

    # Ensure output directory exists
    output_file.parent.mkdir(exist_ok=True)

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
            notes = "This is a known bug that needs to be fixed."
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
    template = Template(html_template)
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
