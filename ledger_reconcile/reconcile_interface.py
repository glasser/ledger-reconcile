#!/usr/bin/env python3
# Terminal-based reconciliation interface

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import ClassVar

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, HorizontalGroup, Vertical
from textual.widgets import DataTable, Footer, Label

from .file_editor import LedgerFileEditor
from .file_watcher import LedgerFileWatcher
from .ledger_interface import LedgerInterface, ReconciliationEntry


class ReconcileApp(App):
    """Main reconciliation application using Textual."""

    CSS = """
    Screen {
        layers: base overlay;
    }

    .header {
        dock: top;
        height: 3;
        background: $primary;
        color: $text;
    }

    .footer {
        dock: bottom;
        height: 3;
        background: $primary;
        color: $text;
    }

    .main-container {
        height: 1fr;
    }

    .info-label {
        text-align: center;
        width: 1fr;
    }

    .transactions-table {
        height: 1fr;
        border: solid $primary;
    }

    DataTable > .datatable--cursor {
        background: $secondary;
    }

    DataTable > .datatable--header {
        background: $primary;
        color: $text;
    }
    """

    BINDINGS: ClassVar = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
        ("space", "toggle_status", "Toggle Status"),
        ("r", "reconcile_all", "Reconcile All !"),
    ]

    def __init__(self, ledger_file: Path, account: str, target_amount: str):
        super().__init__()
        self.ledger_file = ledger_file
        self.account = account
        self.target_amount = target_amount
        self.ledger_interface = LedgerInterface(ledger_file)
        self.file_watcher = LedgerFileWatcher(ledger_file, self._on_file_changed)
        self.file_editor = LedgerFileEditor(ledger_file, self.file_watcher)
        self.transactions: list[ReconciliationEntry] = []
        self.current_balance = "$0.00"

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Container(
            Vertical(
                HorizontalGroup(
                    Label(f"Account: {self.account}", classes="info-label"),
                    Label(f"Target: {self.target_amount}", classes="info-label"),
                    Label(
                        f"Balance: {self.current_balance}",
                        id="balance-label",
                        classes="info-label",
                    ),
                    classes="info-panel",
                ),
                DataTable(id="transactions-table", classes="transactions-table"),
                classes="main-container",
            )
        )
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize the app when mounted."""
        self.file_watcher.start()
        await self.load_transactions()
        await self.setup_table()

    async def on_unmount(self) -> None:
        """Clean up when unmounted."""
        self.file_watcher.stop()

    def _on_file_changed(self) -> None:
        """Handle external file changes."""
        # Reload transactions when file changes externally
        self.call_later(self._refresh_from_file_change)

    async def load_transactions(self) -> None:
        """Load transactions for the selected account."""
        try:
            self.transactions = (
                self.ledger_interface.get_uncleared_transactions_for_account(
                    self.account
                )
            )
            self.current_balance = self.ledger_interface.get_account_balance(
                self.account
            )

            # Update balance label
            balance_label = self.query_one("#balance-label", Label)
            balance_label.update(f"Balance: {self.current_balance}")

        except (OSError, ValueError, RuntimeError) as e:
            self.notify(f"Error loading transactions: {e}", severity="error")

    async def setup_table(self) -> None:
        """Set up the transactions table."""
        table = self.query_one("#transactions-table", DataTable)

        # Select full rows
        table.cursor_type = "row"

        # Add columns
        table.add_columns("Status", "Date")
        table.add_column("Description", width=50)
        table.add_columns("Amount", "Line")

        # Filter to show only unreconciled and semi-reconciled transactions (not fully reconciled *)
        # Look at the status of postings for this account
        filtered_transactions = []
        for t in self.transactions:
            for posting in t.account_postings:
                if posting.account == self.account and posting.status in ("", "!"):
                    filtered_transactions.append(t)
                    break

        # Add rows
        for transaction in filtered_transactions:
            # Find posting for this account to get the amount and status
            amount = ""
            posting_status = ""
            for posting in transaction.account_postings:
                if posting.account == self.account:
                    amount = posting.amount
                    posting_status = posting.status
                    break

            status_display = posting_status if posting_status else "·"
            table.add_row(
                status_display,
                transaction.date,
                transaction.description,
                amount,
                str(transaction.line_number),
                key=str(transaction.line_number),
            )

    def action_toggle_status(self) -> None:
        """Toggle the status of the currently selected transaction."""
        table = self.query_one("#transactions-table", DataTable)
        if table.cursor_row is None:
            return

        # Get the current row key (line number)
        if table.cursor_coordinate is None:
            return
        cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
        row_key = cell_key.row_key
        if row_key is None or row_key.value is None:
            return

        line_number = int(row_key.value)

        # Find the transaction
        transaction = None
        for t in self.transactions:
            if t.line_number == line_number:
                transaction = t
                break

        if not transaction:
            return

        # Find the posting for this account to determine current status
        current_posting_status = ""
        posting_line_number = None
        for posting in transaction.account_postings:
            if posting.account == self.account:
                current_posting_status = posting.status
                posting_line_number = posting.line_number
                break

        if posting_line_number is None:
            self.notify("Could not find posting for this account", severity="error")
            return

        # Determine new status (only toggle between empty and "!")
        new_status = "!" if current_posting_status == "" else ""

        # Update the file using new API - just update this specific posting
        # Save current cursor position using row key for reliability
        current_row = table.cursor_row
        current_row_key = row_key

        if self.file_editor.update_postings_status(
            [posting_line_number], current_posting_status, new_status
        ):
            # Use call_later for better timing control
            self.call_later(
                self._refresh_and_restore_cursor, current_row, current_row_key
            )

            self.notify(f"Updated posting status to '{new_status}'")
        else:
            self.notify(
                "Failed to update posting (may have changed externally)",
                severity="error",
            )

    @on(DataTable.RowSelected)
    def open_in_editor(self, event: DataTable.RowSelected) -> None:
        """Open the current transaction in VSCode."""
        row_key = event.row_key
        if not row_key.value:
            return
        line_number = int(row_key.value)

        try:
            # Use 'code -g' to open file at specific line
            subprocess.run(
                ["code", "-g", f"{self.ledger_file}:{line_number}"], check=True
            )
        except subprocess.CalledProcessError:
            self.notify("Failed to open in VSCode", severity="error")
        except FileNotFoundError:
            self.notify(
                "VSCode not found. Install VS Code CLI tools.", severity="error"
            )

    def action_reconcile_all(self) -> None:
        """Reconcile all semi-reconciled (!) transactions."""
        # Collect all pending postings for this account
        pending_posting_lines = []
        for transaction in self.transactions:
            for posting in transaction.account_postings:
                if posting.account == self.account and posting.status == "!":
                    pending_posting_lines.append(posting.line_number)

        if not pending_posting_lines:
            self.notify("No semi-reconciled transactions to reconcile")
            return

        # Update all pending postings to cleared using new API
        if self.file_editor.update_postings_status(pending_posting_lines, "!", "*"):
            self.notify(f"Reconciled {len(pending_posting_lines)} postings")
            # Refresh the table to hide reconciled transactions
            self.call_after_refresh(self.load_transactions)
            self.call_after_refresh(self.refresh_table)
        else:
            self.notify(
                "Failed to reconcile postings (may have changed externally)",
                severity="error",
            )

    async def refresh_table(self) -> None:
        """Refresh the transactions table."""
        table = self.query_one("#transactions-table", DataTable)
        table.clear()
        await self.setup_table()

    async def _refresh_and_restore_cursor(
        self, target_row: int, target_row_key
    ) -> None:
        """Refresh data and restore cursor position."""
        await self.load_transactions()
        await self.refresh_table()

        table = self.query_one("#transactions-table", DataTable)

        # Try to find the same row by key first (more reliable)
        if target_row_key and target_row_key.value:
            from textual.coordinate import Coordinate

            for row_idx in range(table.row_count):
                cell_key = table.coordinate_to_cell_key(Coordinate(row_idx, 0))
                if cell_key.row_key and cell_key.row_key.value == target_row_key.value:
                    table.move_cursor(row=row_idx, scroll=True, animate=False)
                    # Ensure table has focus
                    table.focus()
                    return

        # Fallback to row index, but clamp to valid range
        max_row = table.row_count - 1
        safe_row = min(target_row, max_row) if max_row >= 0 else 0
        table.move_cursor(row=safe_row, scroll=True, animate=False)
        # Ensure table has focus
        table.focus()

    async def _refresh_from_file_change(self) -> None:
        """Refresh data after external file change."""
        await self.load_transactions()
        await self.refresh_table()
        self.notify("File updated externally - data refreshed")


def run_reconcile_interface(
    ledger_file: Path, account: str, target_amount: str
) -> None:
    """Run the reconciliation interface for the given account."""
    app = ReconcileApp(ledger_file, account, target_amount)
    app.run()
