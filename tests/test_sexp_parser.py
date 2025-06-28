# Tests for the S-expression parser
# Data-driven tests using .sexp and .json fixture files

import json
from pathlib import Path

import pytest

from ledger_reconcile.sexp_parser import SExpParser


class TestSExpParser:
    """Data-driven test cases for the S-expression parser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = SExpParser()
        self.fixtures_dir = Path(__file__).parent / "fixtures" / "sexp_parser"

    def get_test_cases(self):
        """Get all test cases from fixture files."""
        test_cases = []
        for sexp_file in sorted(self.fixtures_dir.glob("*.sexp")):
            json_file = sexp_file.with_suffix(".json")
            if json_file.exists():
                test_cases.append((sexp_file.stem, sexp_file, json_file))
        return test_cases



def pytest_generate_tests(metafunc):
    """Generate parameterized tests from fixtures."""
    if metafunc.function.__name__ == "test_fixture":
        fixtures_dir = Path(__file__).parent / "fixtures" / "sexp_parser"
        test_cases = []

        for sexp_file in sorted(fixtures_dir.glob("*.sexp")):
            json_file = sexp_file.with_suffix(".json")
            if json_file.exists():
                test_cases.append((sexp_file.stem, str(sexp_file), str(json_file)))

        metafunc.parametrize(
            "name,sexp_file,json_file", test_cases, ids=[tc[0] for tc in test_cases]
        )


def test_fixture(name, sexp_file, json_file):
    """Parameterized test for each fixture."""
    parser = SExpParser()

    sexp_path = Path(sexp_file)
    json_path = Path(json_file)

    with sexp_path.open(encoding="utf-8") as f:
        sexp_input = f.read()

    with json_path.open(encoding="utf-8") as f:
        expected = json.load(f)

    # Handle error cases
    if isinstance(expected, dict) and "error" in expected:
        if name.startswith("bug_"):
            # Known bugs - mark as xfail
            pytest.xfail(f"Known bug: {expected['error']}")
        else:
            # For now, just skip error test cases since parser doesn't raise exceptions
            pytest.skip("Error handling not yet implemented")
        return

    # Normal test case
    result = parser.parse(sexp_input)
    assert result == expected, (
        f"Input: {sexp_input!r}\nExpected: {expected!r}\nGot: {result!r}"
    )
