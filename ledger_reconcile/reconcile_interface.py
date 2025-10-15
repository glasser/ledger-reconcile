#!/usr/bin/env python3
# Terminal-based reconciliation interface

from __future__ import annotations

import subprocess
from decimal import Decimal
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, HorizontalGroup, Vertical
from textual.coordinate import Coordinate
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Input, Label

from .account_selector import AccountSelector
from .file_editor import LedgerFileEditor
from .file_watcher import LedgerFileWatcher
from .ledger_interface import LedgerInterface, ReconciliationEntry
from .target_balance_parser import format_balance, parse_balance


class ConfirmationScreen(ModalScreen[bool]):
    """A simple confirmation dialog."""

    BINDINGS: ClassVar = [
        ("y", "confirm", "Yes"),
        ("n", "cancel", "No"),
        ("escape", "cancel", "Cancel"),
    ]

    @property
    def CSS(self) -> str:  # noqa: N802
        """Load CSS from file."""
        css_path = Path(__file__).parent / "css" / "confirmation_screen.tcss"
        return css_path.read_text()

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


class TargetBalanceScreen(ModalScreen[Decimal | None]):
    """Modal dialog for adjusting the target balance."""

    BINDINGS: ClassVar = [
        ("escape", "cancel", "Cancel"),
    ]

    @property
    def CSS(self) -> str:  # noqa: N802
        """Load CSS from file."""
        css_path = Path(__file__).parent / "css" / "target_balance_screen.tcss"
        return css_path.read_text()

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
            parsed_amount = parse_balance(new_target)
            self.dismiss(parsed_amount)
        except ValueError as e:
            self.notify(f"Invalid target balance: {e}", severity="error")

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(None)


class ReconcileApp(App):
    """Main reconciliation application using Textual."""

    @property
    def CSS(self) -> str:  # noqa: N802
        """Load CSS from file."""
        css_path = Path(__file__).parent / "css" / "reconcile_app.tcss"
        return css_path.read_text()

    BINDINGS: ClassVar = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
        ("space", "toggle_status", "Toggle Status"),
        ("c", "reconcile_all", "Clear All !"),
        ("!", "set_all_pending", "Set All !"),
        ("t", "adjust_target", "Adjust Target"),
        ("s", "toggle_sort", "Reverse Sort"),
        ("r", "refresh", "Refresh"),
        ("a", "switch_account", "Switch Account"),
    ]

    # Reactive variables that automatically update UI labels
    target_amount: reactive[Decimal] = reactive(Decimal("0.00"))
    cleared_pending_balance: reactive[Decimal] = reactive(Decimal("0.00"))
    delta: reactive[Decimal] = reactive(Decimal("0.00"))

    def __init__(
        self,
        ledger_file: Path,
        account: str,
        target_amount: str,
        disable_file_watcher: bool = False,
        cached_accounts: list[str] | None = None,
    ):
        super().__init__()
        self.ledger_file = ledger_file
        self.account = account

        # Parse and store target amount - use set_reactive to avoid triggering watchers
        self.target_amount_decimal = parse_balance(target_amount)
        self.set_reactive(ReconcileApp.target_amount, self.target_amount_decimal)

        self.ledger_interface = LedgerInterface(ledger_file)
        self.file_watcher = (
            None
            if disable_file_watcher
            else LedgerFileWatcher(ledger_file, self._on_file_changed)
        )
        self.file_editor = LedgerFileEditor(ledger_file, self.file_watcher)
        self.transactions: list[ReconciliationEntry] = []

        # Track sort order
        self.reverse_sort = False  # False = oldest first, True = newest first

        # Cache accounts (loaded once per app session)
        self._cached_accounts: list[str] | None = cached_accounts

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Container(
            Vertical(
                HorizontalGroup(
                    Label(
                        f"Account: {self.account}",
                        id="account-label",
                        classes="info-label",
                    ),
                    Label(
                        f"Target: {format_balance(self.target_amount)}",
                        id="target-label",
                        classes="info-label",
                    ),
                    classes="info-panel-row",
                ),
                HorizontalGroup(
                    Label(
                        f"Cleared+Pending: {format_balance(self.cleared_pending_balance)}",
                        id="cleared-pending-balance-label",
                        classes="info-label",
                    ),
                    Label(
                        f"Delta: {format_balance(self.delta)}",
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

    def compute_delta(self) -> Decimal:
        """Compute delta based on current target and balance."""
        return self.target_amount - self.cleared_pending_balance

    def get_cached_accounts(self) -> list[str]:
        """Get accounts from cache or load and cache them."""
        if self._cached_accounts is None:
            self._cached_accounts = self.ledger_interface.get_accounts()
        return self._cached_accounts

    def watch_target_amount(self, target_amount: Decimal) -> None:
        """Update target label when target_amount changes."""
        try:
            target_label = self.query_one("#target-label", Label)
            target_label.update(f"Target: {format_balance(target_amount)}")
        except NoMatches:
            # Widget not created yet during compose()
            pass

    def watch_cleared_pending_balance(self, cleared_pending_balance: Decimal) -> None:
        """Update balance label when cleared_pending_balance changes."""
        try:
            balance_label = self.query_one("#cleared-pending-balance-label", Label)
            balance_label.update(
                f"Cleared+Pending: {format_balance(cleared_pending_balance)}"
            )
        except NoMatches:
            # Widget not created yet during compose()
            pass

    def watch_delta(self, delta: Decimal) -> None:
        """Update delta label when delta changes."""
        try:
            delta_label = self.query_one("#delta-label", Label)
            delta_label.update(f"Delta: {format_balance(delta)}")
        except NoMatches:
            # Widget not created yet during compose()
            pass

    async def on_mount(self) -> None:
        """Initialize the app when mounted."""
        if self.file_watcher:
            self.file_watcher.start()
        await self.load_transactions()
        await self.setup_table()

    async def on_unmount(self) -> None:
        """Clean up when unmounted."""
        if self.file_watcher:
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
            balance_str = self.ledger_interface.get_cleared_and_pending_balance(
                self.account
            )
            self.cleared_pending_balance = parse_balance(balance_str)

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

        # The API already filters transactions appropriately, so we just need to sort them
        sorted_transactions = sorted(
            self.transactions, key=lambda t: t.date, reverse=self.reverse_sort
        )
        # Add rows - create one row per posting
        for transaction in sorted_transactions:
            # Create a row for each posting (ledger already filtered to this account)
            for posting in transaction.account_postings:
                # Parse and reformat amount for consistent display with alignment
                try:
                    parsed_amount = parse_balance(posting.amount)
                    amount = format_balance(parsed_amount, align_dollar_sign=True)
                except ValueError:
                    # If parsing fails, use original amount
                    amount = posting.amount

                status_display = posting.status if posting.status else "·"

                # Apply special styling for pending status "!"
                if posting.status == "!":
                    # Create styled text cells with background color for pending items
                    # Use justify to help fill cell width with background color
                    styled_row = [
                        Text(status_display, style="on bright_blue", justify="left"),
                        Text(
                            str(posting.line_number),
                            style="on bright_blue",
                            justify="left",
                        ),
                        Text(transaction.date, style="on bright_blue", justify="left"),
                        Text(
                            transaction.check_code,
                            style="on bright_blue",
                            justify="left",
                        ),
                        Text(amount, style="on bright_blue", justify="left"),
                        Text(
                            transaction.description,
                            style="on bright_blue",
                            justify="left",
                        ),
                    ]
                    table.add_row(*styled_row, key=str(posting.line_number))
                else:
                    # Regular row for other statuses
                    table.add_row(
                        status_display,
                        str(posting.line_number),
                        transaction.date,
                        transaction.check_code,
                        amount,
                        transaction.description,
                        key=str(posting.line_number),
                    )

    def action_toggle_status(self) -> None:
        """Toggle the status of the currently selected transaction."""
        table = self.query_one("#transactions-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return

        # Get the current row key (posting line number)
        if table.cursor_coordinate is None:
            return
        cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
        row_key = cell_key.row_key
        if row_key is None or row_key.value is None:
            return

        posting_line_number = int(row_key.value)

        # Find the current status directly from the posting line number
        current_posting_status = ""
        for transaction in self.transactions:
            for posting in transaction.account_postings:
                if posting.line_number == posting_line_number:
                    current_posting_status = posting.status
                    break

        # Determine new status (only toggle between empty and "!")
        new_status = "!" if current_posting_status == "" else ""

        # Update the file using new API - just update this specific posting
        # Save current cursor position using row key for reliability
        current_row = table.cursor_row
        current_row_key = row_key

        if self.file_editor.update_postings_status(
            [posting_line_number], current_posting_status, new_status
        ):
            # Move cursor down one row if possible
            next_row = current_row + 1 if current_row is not None else 0
            if next_row < table.row_count:
                # Move to next row
                self.call_later(self._refresh_and_restore_cursor, next_row, None)
            else:
                # Stay on current row if at the end
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
        """Open the current posting in VSCode."""
        row_key = event.row_key
        if not row_key.value:
            return
        posting_line_number = int(row_key.value)

        try:
            # Use 'code -g' to open file at specific line (posting line number)
            subprocess.run(
                ["code", "-g", f"{self.ledger_file}:{posting_line_number}"], check=True
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

    def action_set_all_pending(self) -> None:
        """Toggle all visible transactions between uncleared and pending.

        This is equivalent to selecting every visible row and toggling them.
        Matches the behavior of space key which toggles "" <-> "!".
        If all are pending, clears them all. If any are uncleared, sets all to pending.
        """
        # Count pending vs uncleared postings
        pending_lines = []
        uncleared_lines = []
        for transaction in self.transactions:
            for posting in transaction.account_postings:
                if posting.account == self.account:
                    if posting.status == "!":
                        pending_lines.append(posting.line_number)
                    elif posting.status == "":
                        uncleared_lines.append(posting.line_number)

        # If all are pending, clear them all
        # Otherwise, set all uncleared to pending
        if uncleared_lines:
            # Set all uncleared to pending
            target_lines = uncleared_lines
            from_status = ""
            to_status = "!"
            action_desc = "pending"
        elif pending_lines:
            # Clear all pending
            target_lines = pending_lines
            from_status = "!"
            to_status = ""
            action_desc = "uncleared"
        else:
            self.notify("No transactions to toggle")
            return

        # Save current cursor position
        table = self.query_one("#transactions-table", DataTable)
        current_row = table.cursor_row if table.cursor_row is not None else 0
        current_row_key = None

        if current_row < table.row_count and table.cursor_coordinate is not None:
            cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
            current_row_key = cell_key.row_key

        if self.file_editor.update_postings_status(
            target_lines, from_status, to_status
        ):
            self.notify(f"Set {len(target_lines)} postings to {action_desc}")
            # Refresh the table to show updated status
            self.call_after_refresh(
                self._refresh_and_restore_cursor, current_row, current_row_key
            )
        else:
            self.notify(
                "Failed to update postings (may have changed externally)",
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
        # Get current cursor position before refresh
        table = self.query_one("#transactions-table", DataTable)
        current_row = table.cursor_row
        current_row_key = None

        if current_row is not None and current_row < table.row_count:
            # Get the row key for the current cursor position
            cell_key = table.coordinate_to_cell_key(Coordinate(current_row, 0))
            if cell_key and cell_key.row_key:
                current_row_key = cell_key.row_key

        # Refresh data and restore cursor position
        self.call_after_refresh(
            self._refresh_and_restore_cursor, current_row or 0, current_row_key
        )
        self.notify("Refreshed from file")

    def action_switch_account(self) -> None:
        """Switch to a different account using fzf selection."""
        # Use run_worker to handle the async operation
        self.run_worker(self._switch_account_worker(), exclusive=True)

    async def _switch_account_worker(self) -> None:
        """Worker method to handle account switching."""
        try:
            # Get cached accounts
            accounts = self.get_cached_accounts()

            if not accounts:
                self.notify("No accounts found in ledger file", severity="error")
                return

            # Create account selector
            account_selector = AccountSelector(accounts)

            # Suspend the app to allow fzf to take over the terminal
            with self.suspend():
                selected_account = account_selector.select_account("Switch to account")

            if selected_account is None:
                self.notify("Account selection cancelled")
                return

            if selected_account == self.account:
                self.notify(f"Already on account {self.account}")
                return

            # Switch to the new account
            self.account = selected_account

            # Update the account label
            try:
                account_label = self.query_one("#account-label", Label)
                account_label.update(f"Account: {self.account}")
            except NoMatches:
                pass

            # Clear current data and reload for new account
            self.transactions = []
            table = self.query_one("#transactions-table", DataTable)
            table.clear(columns=True)

            # Load transactions for the new account
            await self.load_transactions()
            await self.setup_table()

            self.notify(f"Switched to account: {self.account}")

        except (OSError, ValueError, RuntimeError) as e:
            self.notify(f"Error switching account: {e}", severity="error")

    async def _adjust_target_worker(self) -> None:
        """Worker method to handle target balance adjustment."""
        target_screen = TargetBalanceScreen(format_balance(self.target_amount))
        new_target = await self.push_screen_wait(target_screen)

        if new_target is not None:
            # Update the target amount directly
            self.target_amount = new_target
            self.notify(
                f"Target balance updated to {format_balance(self.target_amount)}"
            )

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

        # Only try to get row key if table has rows and cursor is valid
        if table.row_count > 0 and table.cursor_coordinate is not None:
            cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
            current_row_key = cell_key.row_key

        # Refresh data and restore cursor position
        await self._refresh_and_restore_cursor(current_row, current_row_key)
        self.notify("File updated externally - data refreshed")


def run_reconcile_interface(
    ledger_file: Path,
    account: str,
    target_amount: str,
    cached_accounts: list[str] | None = None,
) -> None:
    """Run the reconciliation interface for the given account."""
    app = ReconcileApp(
        ledger_file, account, target_amount, cached_accounts=cached_accounts
    )
    app.run()
