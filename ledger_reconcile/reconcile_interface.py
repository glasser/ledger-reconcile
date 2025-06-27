#!/usr/bin/env python3
# Terminal-based reconciliation interface

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Label

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
    }

    .transactions-table {
        height: 1fr;
        border: solid $primary;
    }

    .balance-info {
        text-align: center;
        margin: 1;
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
        ("enter", "open_in_editor", "Open in VSCode"),
        ("r", "reconcile_all", "Reconcile All !"),
        ("up", "cursor_up", "Up"),
        ("down", "cursor_down", "Down"),
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
        yield Header()
        yield Container(
            Vertical(
                Horizontal(
                    Label(f"Account: {self.account}", classes="info-label"),
                    Label(f" | Target: {self.target_amount}", classes="info-label"),
                    Label(
                        f" | Balance: {self.current_balance}",
                        id="balance-label",
                        classes="info-label",
                    ),
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

        # Add columns
        table.add_columns("Status", "Date", "Description", "Amount", "Line")

        # Filter to show only unreconciled and semi-reconciled transactions (not fully reconciled *)
        filtered_transactions = [t for t in self.transactions if t.status in ("", "!")]

        # Add rows
        for transaction in filtered_transactions:
            # Find posting for this account to get the amount
            amount = ""
            for posting in transaction.account_postings:
                if posting.account == self.account:
                    amount = posting.amount
                    break

            status_display = transaction.status if transaction.status else "·"
            table.add_row(
                status_display,
                transaction.date,
                transaction.description[:50],  # Truncate long descriptions
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
        if table.cursor_row is None:
            return
        row_key = table.get_row_key(table.cursor_row)  # type: ignore[attr-defined]
        if row_key is None:
            return

        line_number = int(str(row_key))

        # Find the transaction
        transaction = None
        for t in self.transactions:
            if t.line_number == line_number:
                transaction = t
                break

        if not transaction:
            return

        # Determine new status (only toggle between empty and "!")
        current_status = transaction.status
        new_status = "!" if current_status == "" else ""

        # Update the file
        if self.file_editor.update_all_postings_in_transaction(line_number, new_status):
            # Update our local data
            transaction.status = new_status

            # Update the table display
            status_display = new_status if new_status else "·"
            if table.cursor_row is not None:
                table.update_cell(str(table.cursor_row), "Status", status_display)

            self.notify(f"Updated transaction status to '{new_status}'")
        else:
            self.notify("Failed to update transaction", severity="error")

    def action_open_in_editor(self) -> None:
        """Open the current transaction in VSCode."""
        table = self.query_one("#transactions-table", DataTable)
        if table.cursor_row is None:
            return

        row_key = table.get_row_key(table.cursor_row)  # type: ignore[attr-defined]
        if row_key is None:
            return

        line_number = int(str(row_key))

        try:
            # Use 'code -g' to open file at specific line
            subprocess.run(
                ["code", "-g", f"{self.ledger_file}:{line_number}"], check=True
            )
            self.notify(f"Opened line {line_number} in VSCode")
        except subprocess.CalledProcessError:
            self.notify("Failed to open in VSCode", severity="error")
        except FileNotFoundError:
            self.notify(
                "VSCode not found. Install VS Code CLI tools.", severity="error"
            )

    def action_reconcile_all(self) -> None:
        """Reconcile all semi-reconciled (!) transactions."""
        reconciled_count = 0

        for transaction in self.transactions:
            if (
                transaction.status == "!"
                and self.file_editor.update_all_postings_in_transaction(
                    transaction.line_number, "*"
                )
            ):
                transaction.status = "*"
                reconciled_count += 1

        if reconciled_count > 0:
            self.notify(f"Reconciled {reconciled_count} transactions")
            # Refresh the table to hide reconciled transactions
            self.call_after_refresh(self.refresh_table)
        else:
            self.notify("No semi-reconciled transactions to reconcile")

    async def refresh_table(self) -> None:
        """Refresh the transactions table."""
        table = self.query_one("#transactions-table", DataTable)
        table.clear()
        await self.setup_table()

    async def _refresh_from_file_change(self) -> None:
        """Refresh data after external file change."""
        await self.load_transactions()
        await self.refresh_table()
        self.notify("File updated externally - data refreshed")

    def action_cursor_up(self) -> None:
        """Move cursor up in the table."""
        table = self.query_one("#transactions-table", DataTable)
        table.action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move cursor down in the table."""
        table = self.query_one("#transactions-table", DataTable)
        table.action_cursor_down()


def run_reconcile_interface(
    ledger_file: Path, account: str, target_amount: str
) -> None:
    """Run the reconciliation interface for the given account."""
    app = ReconcileApp(ledger_file, account, target_amount)
    app.run()
