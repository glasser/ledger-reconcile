#!/usr/bin/env python3
# Data-driven tests for account selector

import io
import subprocess
from pathlib import Path

import pytest
from rich.console import Console

from ledger_reconcile.account_selector import AccountSelector

from ..fixture_utils import load_directory_tree

# Load test data once at module level
_test_cases_dir = Path(__file__).parent / "test_cases"
_tree = load_directory_tree(_test_cases_dir)


def pytest_generate_tests(metafunc):
    """Generate parameterized tests from fixtures."""
    if metafunc.function.__name__ == "test_fixture":
        test_cases = []
        for name in sorted(_tree.keys()):
            test_cases.append((name, _tree[name]))
        metafunc.parametrize("test_name,test_data", test_cases)


def test_fixture(test_name, test_data):  # noqa: ARG001
    """Run a single account selector test case."""
    # Get config from test data
    config_data = test_data.get("config.yaml", {})
    config = config_data.get("parsed", {})

    accounts = config.get("accounts", [])
    prompt = config.get("prompt", "Select account")
    test_input = config.get("test_input")
    expected_result = config.get("expected_result")
    expected_console_contains = config.get("expected_console_contains")
    requires_fzf = config.get("requires_fzf", False)

    # Check if fzf is available when required
    if requires_fzf:
        try:
            subprocess.run(["fzf", "--version"], capture_output=True, check=True)  # noqa: S607
        except (subprocess.CalledProcessError, FileNotFoundError):
            pytest.fail("fzf is required for this test but not available")

    # Capture console output
    console_output = io.StringIO()
    console = Console(file=console_output, force_terminal=True)

    # Create selector with custom console
    selector = AccountSelector(accounts, console=console)

    # Run the selection
    result = selector.select_account(prompt, test_input=test_input)

    # Get console output
    output = console_output.getvalue()

    # Verify result
    assert result == expected_result, f"Expected {expected_result}, got {result}"

    # Verify console output if expected
    if expected_console_contains:
        assert expected_console_contains in output, (
            f"Expected '{expected_console_contains}' in output, got: {output}"
        )
