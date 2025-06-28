# Tests for the S-expression parser
# Data-driven tests using .sexp and .json fixture files

import json
from pathlib import Path

import pytest

from ledger_reconcile.sexp_parser import SExpParseError, SExpParser


def get_fixtures_dir() -> Path:
    """Get the fixtures directory path."""
    return Path(__file__).parent / "fixtures" / "sexp_parser"


def get_all_sexp_files() -> list[Path]:
    """Get all .sexp files in the fixtures directory."""
    return sorted(get_fixtures_dir().glob("*.sexp"))


def get_test_cases() -> list[tuple[str, Path, Path]]:
    """Get all valid test cases (sexp files with corresponding json files)."""
    test_cases = []
    for sexp_file in get_all_sexp_files():
        json_file = sexp_file.with_suffix(".json")
        if json_file.exists():
            test_cases.append((sexp_file.stem, sexp_file, json_file))
    return test_cases


class TestSExpParser:
    """Data-driven test cases for the S-expression parser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = SExpParser()

    def test_all_sexp_files_have_json_files(self):
        """Ensure every .sexp file has a corresponding .json file."""
        missing_json_files = []
        for sexp_file in get_all_sexp_files():
            json_file = sexp_file.with_suffix(".json")
            if not json_file.exists():
                missing_json_files.append(sexp_file.name)

        assert not missing_json_files, f"Missing JSON files for: {missing_json_files}"


def pytest_generate_tests(metafunc):
    """Generate parameterized tests from fixtures."""
    if metafunc.function.__name__ == "test_fixture":
        test_cases = [
            (name, str(sexp_file), str(json_file))
            for name, sexp_file, json_file in get_test_cases()
        ]

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
            # Test should raise an exception
            with pytest.raises(SExpParseError):
                parser.parse(sexp_input)
        return

    # Normal test case
    result = parser.parse(sexp_input)
    assert result == expected, (
        f"Input: {sexp_input!r}\nExpected: {expected!r}\nGot: {result!r}"
    )
