#!/usr/bin/env python3
# Generate all test case previews and index

import sys
from pathlib import Path

import jinja2

# Add the parent directory to the path to import from tests
sys.path.insert(0, str(Path(__file__).parent.parent))
from tests.fixture_utils import load_directory_tree


def generate_preview(fixtures_dir: Path, output_file: Path, tree: dict):
    """Generate HTML preview of all test fixtures."""
    test_cases = tree

    # Template file should be a sibling of test_cases directory
    template_file = fixtures_dir.parent / "template.html.j2"
    if not template_file.exists():
        raise FileNotFoundError(f"Template file not found at {template_file}")

    # Load template
    template_content = template_file.read_text(encoding="utf-8")
    template = jinja2.Template(template_content)

    # Prepare template data
    template_data = {
        "fixtures_dir": fixtures_dir,
        "test_cases": test_cases,
        "total_cases": len(test_cases),
    }

    # Render template
    rendered = template.render(**template_data)

    # Write output
    output_file.write_text(rendered, encoding="utf-8")
    print(f"Generated preview: {output_file}")


def generate_index(test_dirs: list[tuple[str, Path]], output_file: Path):
    """Generate index HTML file listing all test suites."""
    # Load template
    template_file = Path(__file__).parent / "index_template.html.j2"
    template_content = template_file.read_text(encoding="utf-8")
    template = jinja2.Template(template_content)

    template_data = {
        "test_suites": test_dirs,
    }
    rendered = template.render(**template_data)
    output_file.write_text(rendered, encoding="utf-8")
    print(f"Generated index: {output_file}")


def main():
    """Generate all test case previews."""
    tests_dir = Path(__file__).parent.parent / "tests"

    # Find all test directories with test_cases subdirectories
    test_suites = []
    for item in sorted(tests_dir.iterdir()):
        if item.is_dir() and (item / "test_cases").exists():
            # Load directory tree once
            test_cases_dir = item / "test_cases"
            tree = load_directory_tree(test_cases_dir)

            test_suites.append((item.name, item))

            # Generate preview for this test suite using the already-loaded tree
            output_file = item / "test_cases.html"
            generate_preview(test_cases_dir, output_file, tree)

    # Generate index
    if test_suites:
        index_file = tests_dir / "test_cases.html"
        generate_index(test_suites, index_file)


if __name__ == "__main__":
    main()
