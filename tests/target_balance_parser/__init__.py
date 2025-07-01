# Data-driven tests for target balance parsing
# Tests parsing various formats of target amounts that users might input

from pathlib import Path

from ledger_reconcile.target_balance_parser import TargetBalanceParser

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
                and "config.yaml" in test_data
            ):  # It's a directory with config.yaml
                test_cases.append((test_name, test_data))

        metafunc.parametrize(
            "name,test_data", test_cases, ids=[tc[0] for tc in test_cases]
        )


def test_fixture(name, test_data):
    """Parameterized test for each fixture."""
    # Get test data from config.yaml
    assert "config.yaml" in test_data, f"Missing config.yaml for test {name}"
    assert "parsed" in test_data["config.yaml"], (
        f"config.yaml not parsed for test {name}"
    )

    config = test_data["config.yaml"]["parsed"]
    input_text = config.get("input")
    expected = config.get("expected")

    assert input_text is not None, f"No 'input' key in config.yaml for test {name}"
    assert expected is not None, f"No 'expected' key in config.yaml for test {name}"

    # Create parser and test
    parser = TargetBalanceParser()
    amount, formatted_display = parser.parse(input_text)

    # Check parsed amount
    assert float(amount) == expected["parsed_amount"], (
        f"Test case: {name}\nExpected amount: {expected['parsed_amount']}\nGot: {float(amount)}"
    )

    # Check formatted display
    assert formatted_display == expected["formatted_display"], (
        f"Test case: {name}\nExpected display: {expected['formatted_display']}\nGot: {formatted_display}"
    )
