#!/usr/bin/env python3
# Data-driven tests for account switching functionality

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ledger_reconcile.reconcile_interface import ReconcileApp

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


@pytest.mark.asyncio
async def test_fixture(test_name, test_data):  # noqa: ARG001, PLR0915
    """Run a single account switching test case."""
    # Get config from test data
    config_data = test_data.get("config.yaml", {})
    config = config_data.get("parsed", {})

    initial_account = config.get("initial_account", "Assets:Checking")
    target_account = config.get("target_account", "Assets:Savings")
    available_accounts = config.get("available_accounts", [])
    initial_target_amount = config.get("initial_target_amount", "$1000.00")
    expected_result = config.get("expected_result")
    expected_error = config.get("expected_error")
    account_selector_returns = config.get("account_selector_returns")
    test_caching = config.get("test_caching", False)

    # Create a temporary ledger file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ledger", delete=False) as f:
        f.write("2024-01-01 Test Transaction\n")
        f.write("    Assets:Checking              $100.00\n")
        f.write("    Income:Test\n")
        temp_file = Path(f.name)

    try:
        # Create app with cached accounts (or None for caching test)
        app = ReconcileApp(
            temp_file,
            initial_account,
            initial_target_amount,
            disable_file_watcher=True,
            cached_accounts=None if test_caching else available_accounts,
        )

        # Mock the account selector
        with patch(
            "ledger_reconcile.reconcile_interface.AccountSelector"
        ) as mock_account_selector_class:
            mock_account_selector = Mock()
            mock_account_selector_class.return_value = mock_account_selector

            # Configure the mock to return the expected account
            mock_account_selector.select_account.return_value = account_selector_returns

            # Mock the app's suspend method
            with patch.object(app, "suspend") as mock_suspend:
                mock_suspend.return_value.__enter__ = Mock()
                mock_suspend.return_value.__exit__ = Mock()

                # Mock ledger interface for caching tests
                if test_caching:
                    with patch.object(
                        app.ledger_interface, "get_accounts"
                    ) as mock_get_accounts:
                        mock_get_accounts.return_value = available_accounts

                        # First call should hit the cache
                        accounts_1 = app.get_cached_accounts()
                        assert accounts_1 == available_accounts

                        # Second call should use cache, not call get_accounts again
                        accounts_2 = app.get_cached_accounts()
                        assert accounts_2 == available_accounts

                        # get_accounts should only be called once due to caching
                        mock_get_accounts.assert_called_once()

                # Mock UI elements that get updated during account switching
                with patch.object(app, "query_one") as mock_query_one:
                    mock_label = Mock()
                    mock_query_one.return_value = mock_label

                    # Mock the setup_table and load_transactions methods
                    with (
                        patch.object(app, "setup_table") as mock_setup_table,
                        patch.object(
                            app, "load_transactions"
                        ) as mock_load_transactions,
                    ):
                        # Run the account switching worker
                        if expected_error:
                            # Test error scenarios
                            with pytest.raises(Exception) as exc_info:
                                await app._switch_account_worker()
                            assert expected_error in str(exc_info.value)
                        else:
                            # Test successful scenarios
                            await app._switch_account_worker()

                            # Verify the result
                            if expected_result:
                                if expected_result == "account_changed":
                                    assert app.account == target_account
                                    # Verify UI was updated and data was reloaded
                                    mock_label.update.assert_called_once()
                                    mock_setup_table.assert_called_once()
                                    mock_load_transactions.assert_called_once()
                                elif expected_result in (
                                    "account_unchanged",
                                    "cancelled",
                                ):
                                    assert app.account == initial_account

                            # Verify account selector was called correctly (unless no accounts available)
                            if (
                                account_selector_returns is not None
                                and available_accounts
                            ):
                                mock_account_selector.select_account.assert_called_once()
                                call_args = (
                                    mock_account_selector.select_account.call_args
                                )
                                assert "Switch to account" in call_args[0][0]

    finally:
        temp_file.unlink()
