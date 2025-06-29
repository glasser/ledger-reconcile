# Data-driven tests for LedgerFileEditor.update_postings_status API
# Tests the smart status updating logic with precondition checks

import tempfile
from pathlib import Path

from ledger_reconcile.file_editor import LedgerFileEditor

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
                and "input.ledger" in test_data
            ):  # It's a directory with input.ledger
                test_cases.append((test_name, test_data))

        metafunc.parametrize(
            "name,test_data", test_cases, ids=[tc[0] for tc in test_cases]
        )


def test_fixture(name, test_data):
    """Parameterized test for each fixture."""
    # Get test configuration
    assert "config.yaml" in test_data, f"Missing config.yaml for test {name}"
    assert "parsed" in test_data["config.yaml"], (
        f"config.yaml not parsed for test {name}"
    )

    config = test_data["config.yaml"]["parsed"]
    test_params = config.get("test_params")
    assert test_params is not None, (
        f"No 'test_params' key in config.yaml for test {name}"
    )

    # Create temporary file with input content
    input_content = test_data["input.ledger"]["content"]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ledger", delete=False, encoding="utf-8"
    ) as f:
        f.write(input_content)
        ledger_path = Path(f.name)

    try:
        # Create LedgerFileEditor
        editor = LedgerFileEditor(ledger_path)

        # Execute the API call
        result = editor.update_postings_status(
            test_params["posting_line_numbers"],
            test_params["expected_current_status"],
            test_params["new_status"],
        )

        # Check result
        assert result == test_params["expected_result"], (
            f"Test case: {name}\nExpected result: {test_params['expected_result']}\nGot: {result}"
        )

        # If successful, check the output matches expected
        if result and "expected.ledger" in test_data:
            actual_content = ledger_path.read_text()
            expected_content = test_data["expected.ledger"]["content"]
            assert actual_content == expected_content, (
                f"Test case: {name}\nExpected output:\n{expected_content}\nGot:\n{actual_content}"
            )
    finally:
        # Clean up temporary file
        ledger_path.unlink()
