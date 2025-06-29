# Tests for the S-expression parser
# Data-driven tests using .sexp and .json fixture files

from pathlib import Path

import pytest

from ledger_reconcile.sexp_parser import SExpParseError, SExpParser

from ..fixture_utils import load_directory_tree

# Load test data once at module level
_test_cases_dir = Path(__file__).parent / "test_cases"
_tree = load_directory_tree(_test_cases_dir)


def pytest_generate_tests(metafunc):
    """Generate parameterized tests from fixtures."""
    if metafunc.function.__name__ == "test_fixture":
        test_cases = []
        for test_name, test_data in sorted(_tree.items()):
            if (
                isinstance(test_data, dict)
                and "path" not in test_data
                and "input.sexp" in test_data
                and ("output.json" in test_data or "output.error" in test_data)
            ):  # It's a directory with required files
                test_cases.append((test_name, test_data))

        metafunc.parametrize(
            "name,test_data", test_cases, ids=[tc[0] for tc in test_cases]
        )


def test_fixture(name, test_data):
    """Parameterized test for each fixture."""
    parser = SExpParser()

    # Get content from in-memory data
    sexp_input = test_data["input.sexp"]["content"]

    # Check if this is an error case
    if "output.error" in test_data:
        # Error case - should raise an exception
        expected_error = test_data["output.error"]["content"].strip()
        with pytest.raises(SExpParseError) as excinfo:
            parser.parse(sexp_input)
        # Optionally verify the error message matches
        assert str(excinfo.value) == expected_error, (
            f"Test: {name}\nInput: {sexp_input!r}\nExpected error: {expected_error!r}\nGot error: {str(excinfo.value)!r}"
        )
        return

    # Normal test case
    expected = test_data["output.json"]["parsed"]
    result = parser.parse(sexp_input)
    assert result == expected, (
        f"Test: {name}\nInput: {sexp_input!r}\nExpected: {expected!r}\nGot: {result!r}"
    )
