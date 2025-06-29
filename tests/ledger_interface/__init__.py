# Data-driven tests for LedgerInterface using .ledger and .json fixture files
# Tests the complete pipeline from ledger files to ReconciliationEntry objects

import tempfile
from pathlib import Path

from ledger_reconcile.ledger_interface import LedgerInterface

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
    # Get expected results from config.yaml
    assert "config.yaml" in test_data, f"Missing config.yaml for test {name}"
    assert "parsed" in test_data["config.yaml"], (
        f"config.yaml not parsed for test {name}"
    )

    config = test_data["config.yaml"]["parsed"]
    expected = config.get("expected")
    assert expected is not None, f"No 'expected' key in config.yaml for test {name}"

    # Create temporary file with ledger content
    ledger_content = test_data["input.ledger"]["content"]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ledger", delete=False, encoding="utf-8"
    ) as f:
        f.write(ledger_content)
        ledger_path = Path(f.name)

    try:
        # Create LedgerInterface with the test file
        interface = LedgerInterface(ledger_path)

        # Get uncleared transactions for Assets:Checking
        transactions = interface.get_uncleared_transactions_for_account(
            "Assets:Checking"
        )

        # Convert to serializable format for comparison
        result = []
        for txn in transactions:
            txn_dict = {
                "filename": "input.ledger",  # Use consistent name for comparison
                "line_number": txn.line_number,
                "date": txn.date,
                "description": txn.description,
                "account_postings": [],
            }

            for posting in txn.account_postings:
                posting_dict = {
                    "account": posting.account,
                    "amount": posting.amount,
                    "status": posting.status,
                    "line_number": posting.line_number,
                    "original_line": posting.original_line,
                }
                txn_dict["account_postings"].append(posting_dict)

            result.append(txn_dict)

        assert result == expected, (
            f"Test case: {name}\nExpected: {expected}\nGot: {result}"
        )
    finally:
        # Clean up temporary file
        ledger_path.unlink()
