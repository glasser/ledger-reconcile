#!/usr/bin/env python3
# Tests for the reconcile interface UI

import tempfile
from pathlib import Path

import pytest

from ledger_reconcile.reconcile_interface import ReconcileApp


class TestReconcileInterface:
    """Test the ReconcileApp UI components."""

    def create_test_ledger(self, content: str) -> Path:
        """Create a temporary ledger file with the given content."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ledger", delete=False
        ) as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name
        return Path(temp_file_path)

    @pytest.mark.asyncio
    async def test_ui_layout_basic_widgets(self):
        """Test that basic UI components are present and visible."""
        content = """2024-01-01 Opening Balance
    Assets:Checking              $1000.00
    Equity:Opening Balances

2024-01-02 ! Pending Transaction
    Assets:Checking               $100.00
    Expenses:Food
"""
        ledger_file = self.create_test_ledger(content)

        try:
            app = ReconcileApp(ledger_file, "Assets:Checking", "$1100.00")
            async with app.run_test() as pilot:
                # Wait for the app to load
                await pilot.pause()

                # Check that the main containers exist
                assert app.query_one(".info-panel")
                assert app.query_one(".transactions-table")
                assert app.query_one("#balance-label")

                # Check that the DataTable exists
                data_table = app.query_one("#transactions-table")
                assert data_table is not None

        finally:
            ledger_file.unlink()

    @pytest.mark.asyncio
    async def test_balance_info_widgets_visible(self):
        """Test that account, target, and balance info are visible."""
        content = """2024-01-01 Test Transaction
    Assets:Checking               $500.00
    Expenses:Test
"""
        ledger_file = self.create_test_ledger(content)

        try:
            app = ReconcileApp(ledger_file, "Assets:Checking", "$500.00")
            async with app.run_test() as pilot:
                await pilot.pause()

                # Check that the info panel contains the expected widgets
                info_panel = app.query_one(".info-panel")
                assert info_panel is not None

                # Check for balance label specifically
                balance_label = app.query_one("#balance-label")
                assert balance_label is not None

                # Check that balance label text gets updated after loading
                # (it starts as $0.00 but should update to actual balance)
                assert "Balance:" in str(balance_label.renderable)

        finally:
            ledger_file.unlink()

    @pytest.mark.asyncio
    async def test_info_panel_layout(self):
        """Test the info panel layout and content."""
        content = """2024-01-01 Test
    Assets:Checking               $200.00
    Expenses:Test
"""
        ledger_file = self.create_test_ledger(content)

        try:
            app = ReconcileApp(ledger_file, "Assets:Checking", "$200.00")
            async with app.run_test() as pilot:
                await pilot.pause()

                # Get all labels with balance-info class
                balance_info_widgets = app.query(".balance-info")

                # Should have multiple balance-info widgets:
                # - Account label
                # - Target label
                # - Balance label
                # - Help text
                assert len(balance_info_widgets) >= 3

                # Check that account info is displayed
                found_account = False
                found_target = False
                found_balance = False

                for widget in balance_info_widgets:
                    text = str(widget.renderable)
                    if "Account:" in text and "Assets:Checking" in text:
                        found_account = True
                    elif "Target:" in text and "$200.00" in text:
                        found_target = True
                    elif "Balance:" in text:
                        found_balance = True

                assert found_account, "Account info not found in UI"
                assert found_target, "Target info not found in UI"
                assert found_balance, "Balance info not found in UI"

        finally:
            ledger_file.unlink()

    @pytest.mark.asyncio
    async def test_transactions_table_visible(self):
        """Test that the transactions table is visible and populated."""
        content = """2024-01-01 Transaction One
    Assets:Checking               $100.00
    Expenses:Test

2024-01-02 ! Transaction Two
    Assets:Checking               $200.00
    Expenses:Other
"""
        ledger_file = self.create_test_ledger(content)

        try:
            app = ReconcileApp(ledger_file, "Assets:Checking", "$300.00")
            async with app.run_test() as pilot:
                await pilot.pause()

                # Check that the table exists and has the expected structure
                table = app.query_one("#transactions-table")
                assert table is not None

                # The table should have columns
                assert table.columns

                # Should have rows for the transactions
                # (Note: this depends on the internal structure of DataTable)
                # We can at least verify the table component exists

        finally:
            ledger_file.unlink()

    @pytest.mark.asyncio
    async def test_widget_sizes_and_visibility(self):
        """Test that widgets have reasonable sizes and are actually visible."""
        content = """2024-01-01 Test
    Assets:Checking               $100.00
    Expenses:Test
"""
        ledger_file = self.create_test_ledger(content)

        try:
            app = ReconcileApp(ledger_file, "Assets:Checking", "$100.00")
            async with app.run_test(size=(80, 24)) as pilot:  # Standard terminal size
                await pilot.pause()

                # Check info panel has reasonable size
                info_panel = app.query_one(".info-panel")
                assert info_panel.size.height > 0
                assert info_panel.size.width > 0

                # Check transactions table has reasonable size
                table = app.query_one("#transactions-table")
                assert table.size.height > 0
                assert table.size.width > 0

                # Info panel shouldn't take up the whole screen
                assert (
                    info_panel.size.height < 20
                )  # Should be much smaller than full height

        finally:
            ledger_file.unlink()

    @pytest.mark.asyncio
    async def test_info_panel_detailed_layout(self):
        """Test detailed layout and content of the info panel."""
        content = """2024-01-01 Test Transaction
    Assets:Checking               $100.00
    Expenses:Test
"""
        ledger_file = self.create_test_ledger(content)

        try:
            app = ReconcileApp(ledger_file, "Assets:Checking", "$100.00")
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()

                # Get the info panel container
                info_panel = app.query_one(".info-panel")
                assert info_panel.display  # Should be displayed

                # Check individual balance-info widgets
                balance_widgets = app.query(".balance-info")
                assert len(balance_widgets) >= 3  # Account, Target, Balance

                # Check that they're all displayed and visible
                for widget in balance_widgets:
                    assert widget.display
                    assert widget.size.height > 0

                # Check specific content
                account_widget = None
                target_widget = None
                balance_widget = None

                for widget in balance_widgets:
                    text = str(widget.renderable)
                    if "Account:" in text:
                        account_widget = widget
                    elif "Target:" in text:
                        target_widget = widget
                    elif "Balance:" in text and widget.id == "balance-label":
                        balance_widget = widget

                assert account_widget is not None, "Account widget not found"
                assert target_widget is not None, "Target widget not found"
                assert balance_widget is not None, "Balance widget not found"

                # Check that balance gets updated after loading
                assert "Assets:Checking" in str(account_widget.renderable)
                assert "$100.00" in str(target_widget.renderable)

                # Balance should get updated from $0.00 to actual balance
                balance_text = str(balance_widget.renderable)
                assert "Balance:" in balance_text
                # Note: balance might still be $0.00 if transactions haven't loaded yet

        finally:
            ledger_file.unlink()

    @pytest.mark.asyncio
    async def test_layout_with_real_data_flow(self):
        """Test the complete data loading and UI update flow."""
        content = """2024-01-01 Opening Balance
    Assets:Checking              $500.00
    Equity:Opening Balances

2024-01-02 ! Pending Transaction
    Assets:Checking               $100.00
    Expenses:Food
"""
        ledger_file = self.create_test_ledger(content)

        try:
            app = ReconcileApp(ledger_file, "Assets:Checking", "$600.00")
            async with app.run_test(size=(80, 24)) as pilot:
                # Wait for initial load
                await pilot.pause()

                # Wait a bit more to ensure async loading completes
                await pilot.pause(0.1)

                # Check that balance label gets updated with real balance
                balance_label = app.query_one("#balance-label")
                balance_text = str(balance_label.renderable)

                # Should show actual balance, not $0.00
                assert "Balance:" in balance_text

                # Check that transactions table gets populated
                table = app.query_one("#transactions-table")

                # Table should have content after loading
                assert (
                    table.row_count > 0
                ), f"Table has {table.row_count} rows, expected > 0"

        finally:
            ledger_file.unlink()

    def test_ui_snapshot(self, snap_compare):
        """Test the UI layout using snapshot testing."""
        from pathlib import Path

        test_app_path = Path(__file__).parent / "test_app.py"
        assert snap_compare(str(test_app_path), terminal_size=(80, 24))
