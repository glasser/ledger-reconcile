#!/usr/bin/env python3
# Terminal-based reconciliation interface

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import ClassVar

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, HorizontalGroup, Vertical
from textual.coordinate import Coordinate
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Input, Label

from .file_editor import LedgerFileEditor
from .file_watcher import LedgerFileWatcher
from .ledger_interface import LedgerInterface, ReconciliationEntry
from .target_balance_parser import TargetBalanceParser, calculate_delta


class ConfirmationScreen(ModalScreen[bool]):
    """A simple confirmation dialog."""

    BINDINGS: ClassVar = [
        ("y", "confirm", "Yes"),
        ("n", "cancel", "No"),
        ("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    ConfirmationScreen {
        align: center middle;
    }

    .confirmation-dialog {
        background: $surface;
        border: thick $primary;
        width: 70;
        height: auto;
        padding: 0 2;
    }

    .confirmation-message {
        margin: 1 0;
    }

    .confirmation-buttons {
        align: center middle;
        margin-top: 1;
    }

    .confirmation-buttons Button {
        margin: 0 1;
    }

    Footer {
        margin-top: 1;
    }
    """

    def __init__(self, message: str, count: int) -> None:
        super().__init__()
        self.message = message
        self.count = count

    def compose(self) -> ComposeResult:
        """Create the confirmation dialog."""
        yield Container(
            Label(self.message, classes="confirmation-message"),
            Label(
                f"This will reconcile {self.count} postings.",
                classes="confirmation-message",
            ),
            HorizontalGroup(
                Button("Yes", id="confirm", variant="success"),
                Button("No", id="cancel", variant="error"),
                classes="confirmation-buttons",
            ),
            Footer(),
            classes="confirmation-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm(self) -> None:
        """Confirm the dialog."""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(False)


class TargetBalanceScreen(ModalScreen[str | None]):
    """Modal dialog for adjusting the target balance."""

    BINDINGS: ClassVar = [
        ("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    TargetBalanceScreen {
        align: center middle;
    }

    .target-dialog {
        background: $surface;
        border: thick $primary;
        width: 60;
        height: auto;
        padding: 1 2;
    }

    .dialog-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 0;
    }

    .input-container {
        margin: 0;
        height: auto;
    }

    .input-label {
        margin-bottom: 0;
    }

    .dialog-buttons {
        align: center middle;
        margin-top: 0;
    }

    .dialog-buttons Button {
        margin: 0 1;
    }

    Input {
        width: 100%;
        margin: 1 0;
    }
    """

    def __init__(self, current_target: str) -> None:
        super().__init__()
        self.current_target = current_target

    def compose(self) -> ComposeResult:
        """Create the target balance dialog."""
        with Container(classes="target-dialog"):
            yield Label("Adjust Target Balance", classes="dialog-title")
            with Container(classes="input-container"):
                yield Label("Enter new target balance:", classes="input-label")
                yield Input(
                    value=self.current_target,
                    placeholder="e.g., $1,234.56",
                    id="target-input",
                )
            with HorizontalGroup(classes="dialog-buttons"):
                yield Button("Submit", variant="primary", id="submit")
                yield Button("Cancel", variant="default", id="cancel")

    def on_mount(self) -> None:
        """Focus the input when the dialog opens."""
        input_widget = self.query_one("#target-input", Input)
        input_widget.focus()
        # Move cursor to end for easy editing
        if input_widget.value:
            input_widget.cursor_position = len(input_widget.value)

    @on(Button.Pressed, "#submit")
    @on(Input.Submitted, "#target-input")
    def action_submit(self) -> None:
        """Submit the new target balance."""
        input_widget = self.query_one("#target-input", Input)
        new_target = input_widget.value.strip()

        if not new_target:
            self.notify("Target balance cannot be empty", severity="error")
            return

        # Try to parse the new target to validate it
        try:
            parser = TargetBalanceParser()
            parser.parse(new_target)
            self.dismiss(new_target)
        except ValueError as e:
            self.notify(f"Invalid target balance: {e}", severity="error")

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(None)


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

    .info-panel-row {
        height: 1;
        margin-bottom: 0;
    }

    .delta-label {
        color: $warning;
        text-style: bold;
    }

    .transactions-table {
        height: 1fr;
        border: solid $primary;
        overflow-x: hidden;
    }

    DataTable > .datatable--cursor {
        background: $secondary;
    }

    DataTable > .datatable--header {
        background: $primary;
        color: $text;
    }

    /* Zebra striping for columns */
    DataTable .datatable--cursor-cell-column-0,
    DataTable .datatable--cursor-cell-column-2,
    DataTable .datatable--cursor-cell-column-4 {
        background: $surface-lighten-1;
    }

    DataTable .datatable--cell-column-0,
    DataTable .datatable--cell-column-2,
    DataTable .datatable--cell-column-4 {
        background: $surface-lighten-1;
    }
    """

    BINDINGS: ClassVar = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
        ("space", "toggle_status", "Toggle Status"),
        ("c", "reconcile_all", "Clear All !"),
        ("t", "adjust_target", "Adjust Target"),
        ("s", "toggle_sort", "Reverse Sort"),
        ("r", "refresh", "Refresh"),
    ]

    # Reactive variables that automatically update UI labels
    target_amount: reactive[str] = reactive("$0.00", init=False)
    cleared_pending_balance: reactive[str] = reactive("$0.00", init=False)
    delta: reactive[str] = reactive("$0.00", init=False)

    def __init__(self, ledger_file: Path, account: str, target_amount: str):
        super().__init__()
        self.ledger_file = ledger_file
        self.account = account

        # Parse and store target amount
        parser = TargetBalanceParser()
        self.target_amount_parsed = parser.parse(target_amount)
        self.target_amount = self.target_amount_parsed.formatted_display

        self.ledger_interface = LedgerInterface(ledger_file)
        self.file_watcher = LedgerFileWatcher(ledger_file, self._on_file_changed)
        self.file_editor = LedgerFileEditor(ledger_file, self.file_watcher)
        self.transactions: list[ReconciliationEntry] = []

        # Track sort order
        self.reverse_sort = False  # False = oldest first, True = newest first

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Container(
            Vertical(
                HorizontalGroup(
                    Label(f"Account: {self.account}", classes="info-label"),
                    Label(
                        f"Target: {self.target_amount}",
                        id="target-label",
                        classes="info-label",
                    ),
                    classes="info-panel-row",
                ),
                HorizontalGroup(
                    Label(
                        f"Cleared+Pending: {self.cleared_pending_balance}",
                        id="cleared-pending-balance-label",
                        classes="info-label",
                    ),
                    Label(
                        f"Delta: {self.delta}",
                        id="delta-label",
                        classes="info-label delta-label",
                    ),
                    classes="info-panel-row",
                ),
                DataTable(id="transactions-table", classes="transactions-table"),
                classes="main-container",
            )
        )
        yield Footer()

    def watch_target_amount(self, target_amount: str) -> None:
        """Update target label when target_amount changes."""
        try:
            if hasattr(self, "_target_label"):
                self._target_label.update(f"Target: {target_amount}")
        except AttributeError:
            pass

    def watch_cleared_pending_balance(self, cleared_pending_balance: str) -> None:
        """Update cleared+pending balance label when it changes."""
        try:
            if hasattr(self, "_cleared_pending_label"):
                self._cleared_pending_label.update(
                    f"Cleared+Pending: {cleared_pending_balance}"
                )
        except AttributeError:
            pass

    def watch_delta(self, delta: str) -> None:
        """Update delta label when delta changes."""
        try:
            if hasattr(self, "_delta_label"):
                self._delta_label.update(f"Delta: {delta}")
        except AttributeError:
            pass

    async def on_mount(self) -> None:
        """Initialize the app when mounted."""
        # Cache label references for reactive watchers
        self._target_label = self.query_one("#target-label", Label)
        self._cleared_pending_label = self.query_one(
            "#cleared-pending-balance-label", Label
        )
        self._delta_label = self.query_one("#delta-label", Label)

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

            # Get balance types for reconciliation - reactive variables will automatically update UI
            self.cleared_pending_balance = (
                self.ledger_interface.get_cleared_and_pending_balance(self.account)
            )
            self.delta = calculate_delta(
                self.target_amount, self.cleared_pending_balance
            )

        except (OSError, ValueError, RuntimeError) as e:
            self.notify(f"Error loading transactions: {e}", severity="error")

    async def setup_table(self) -> None:
        """Set up the transactions table."""
        table = self.query_one("#transactions-table", DataTable)

        # Select full rows
        table.cursor_type = "row"

        # Add columns - status first, then line number, date, check, amount, description
        table.add_column("")  # Status column - no header, just the symbol
        table.add_column("Line")
        table.add_column("Date")
        table.add_column("Check")
        table.add_column("Amount")
        table.add_column("Description")

        # Filter to show only unreconciled and semi-reconciled transactions (not fully reconciled *)
        # Look at the status of postings for this account
        filtered_transactions = []
        for t in self.transactions:
            for posting in t.account_postings:
                if posting.account == self.account and posting.status in ("", "!"):
                    filtered_transactions.append(t)
                    break

        # Sort transactions based on current sort order
        sorted_transactions = sorted(
            filtered_transactions, key=lambda t: t.date, reverse=self.reverse_sort
        )
        # Add rows
        for transaction in sorted_transactions:
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
                str(transaction.line_number),
                transaction.date,
                transaction.check_code,
                amount,
                transaction.description,
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
        # Use run_worker to handle the async operation
        self.run_worker(self._reconcile_all_worker(), exclusive=True)

    async def _reconcile_all_worker(self) -> None:
        """Worker method to handle reconcile all with confirmation."""
        # Collect all pending postings for this account
        pending_posting_lines = []
        for transaction in self.transactions:
            for posting in transaction.account_postings:
                if posting.account == self.account and posting.status == "!":
                    pending_posting_lines.append(posting.line_number)

        if not pending_posting_lines:
            self.notify("No semi-reconciled transactions to reconcile")
            return

        # Show confirmation dialog
        confirmation_screen = ConfirmationScreen(
            "Are you sure you want to reconcile all pending transactions?",
            len(pending_posting_lines),
        )
        confirmed = await self.push_screen_wait(confirmation_screen)

        if not confirmed:
            self.notify("Reconciliation cancelled")
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

    def action_adjust_target(self) -> None:
        """Show modal to adjust the target balance."""
        # Use run_worker to handle the async operation
        self.run_worker(self._adjust_target_worker(), exclusive=True)

    def action_toggle_sort(self) -> None:
        """Toggle the sort order of transactions."""
        self.reverse_sort = not self.reverse_sort
        # Refresh the table to apply new sort order
        self.call_after_refresh(self.refresh_table)

    def action_refresh(self) -> None:
        """Manually refresh data from the ledger file."""
        # Reload transactions and refresh the table
        self.call_after_refresh(self.load_transactions)
        self.call_after_refresh(self.refresh_table)
        self.notify("Refreshed from file")

    async def _adjust_target_worker(self) -> None:
        """Worker method to handle target balance adjustment."""
        target_screen = TargetBalanceScreen(self.target_amount)
        new_target = await self.push_screen_wait(target_screen)

        if new_target is not None:
            # Parse and update the target amount
            try:
                parser = TargetBalanceParser()
                self.target_amount_parsed = parser.parse(new_target)
                self.target_amount = self.target_amount_parsed.formatted_display

                # Recalculate delta - reactive variables will automatically update UI
                self.delta = calculate_delta(
                    self.target_amount, self.cleared_pending_balance
                )

                self.notify(f"Target balance updated to {self.target_amount}")
            except ValueError as e:
                self.notify(f"Error updating target: {e}", severity="error")

    async def refresh_table(self) -> None:
        """Refresh the transactions table."""
        table = self.query_one("#transactions-table", DataTable)
        table.clear(columns=True)
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
        table = self.query_one("#transactions-table", DataTable)

        # Save current cursor position for restoration
        current_row = table.cursor_row if table.cursor_row is not None else 0
        current_row_key = None

        if table.cursor_coordinate is not None:
            cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
            current_row_key = cell_key.row_key

        # Refresh data and restore cursor position
        await self._refresh_and_restore_cursor(current_row, current_row_key)
        self.notify("File updated externally - data refreshed")


def run_reconcile_interface(
    ledger_file: Path, account: str, target_amount: str
) -> None:
    """Run the reconciliation interface for the given account."""
    app = ReconcileApp(ledger_file, account, target_amount)
    app.run()
