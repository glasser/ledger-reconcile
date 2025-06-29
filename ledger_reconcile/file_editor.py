#!/usr/bin/env python3
# File editing operations for updating reconciliation markers

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .file_watcher import SafeFileEditor

if TYPE_CHECKING:
    from .file_watcher import LedgerFileWatcher


class LedgerFileEditor:
    """Handles editing ledger files to update reconciliation markers."""

    def __init__(
        self, ledger_file: Path, file_watcher: LedgerFileWatcher | None = None
    ):
        self.ledger_file = ledger_file
        self.safe_editor = SafeFileEditor(ledger_file)
        self.file_watcher = file_watcher

    def update_transaction_status(self, line_number: int, new_status: str) -> bool:
        """Update the status marker for a transaction at the given line number.

        Args:
            line_number: 1-based line number of the transaction
            new_status: New status marker ('', '!', or '*')

        Returns:
            True if the update was successful, False otherwise
        """
        try:
            lines, read_time = self.safe_editor.read_lines_safely()
            if line_number < 1 or line_number > len(lines):
                return False

            line_idx = line_number - 1  # Convert to 0-based
            old_line = lines[line_idx]

            # Parse and update the transaction line
            new_line = self._update_transaction_line(old_line, new_status)
            if new_line != old_line:
                lines[line_idx] = new_line

                # Mark that we're making an internal change
                if self.file_watcher:
                    self.file_watcher.mark_internal_change()

                return self.safe_editor.write_lines_safely(lines, read_time)
            else:
                return False
        except (IndexError, ValueError, OSError):
            return False

    def update_posting_status(self, line_number: int, new_status: str) -> bool:
        """Update the status marker for a posting at the given line number.

        Args:
            line_number: 1-based line number of the posting
            new_status: New status marker ('', '!', or '*')

        Returns:
            True if the update was successful, False otherwise
        """
        try:
            lines, read_time = self.safe_editor.read_lines_safely()
            if line_number < 1 or line_number > len(lines):
                return False

            line_idx = line_number - 1  # Convert to 0-based
            old_line = lines[line_idx]

            # Parse and update the posting line
            new_line = self._update_posting_line(old_line, new_status)
            if new_line != old_line:
                lines[line_idx] = new_line

                # Mark that we're making an internal change
                if self.file_watcher:
                    self.file_watcher.mark_internal_change()

                return self.safe_editor.write_lines_safely(lines, read_time)
            else:
                return False
        except (IndexError, ValueError, OSError):
            return False

    def update_all_postings_in_transaction(
        self, transaction_line_number: int, new_status: str
    ) -> bool:
        """Update status markers for all postings in a transaction.

        Smart about physical representation:
        - If all postings will have the same status → use transaction header
        - If postings have different statuses → use individual posting lines

        Args:
            transaction_line_number: 1-based line number of the transaction header
            new_status: New status marker ('', '!', or '*')

        Returns:
            True if the update was successful, False otherwise
        """
        try:
            lines, read_time = self.safe_editor.read_lines_safely()
            if transaction_line_number < 1 or transaction_line_number > len(lines):
                return False

            # Find all posting lines for this transaction and their current statuses
            posting_lines = []
            current_statuses = []
            i = transaction_line_number  # Start after transaction header (1-based)

            while i < len(lines):
                line = lines[i]
                if not line.strip():
                    # Empty line - end of transaction
                    break
                if re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}", line.strip()):
                    # Next transaction - end of current transaction
                    break
                if line.lstrip() and not line.startswith((" ", "\t")):
                    # Non-indented line that's not a date - end of transaction
                    break

                # This is a posting line
                if line.strip():  # Only add non-empty lines
                    posting_lines.append(i)
                    current_status = self._extract_posting_status(lines[i])
                    current_statuses.append(current_status)
                i += 1

            # Decide physical representation: if all postings will have same status, use transaction header
            all_same_status = len(set([new_status] * len(posting_lines))) == 1

            if all_same_status and posting_lines:
                # Use transaction header representation
                trans_idx = transaction_line_number - 1
                old_trans_line = lines[trans_idx]
                new_trans_line = self._update_transaction_line(
                    old_trans_line, new_status
                )
                lines[trans_idx] = new_trans_line

                # Clear status from all posting lines (since it's now on the transaction)
                for posting_line_idx in posting_lines:
                    old_posting_line = lines[posting_line_idx]
                    new_posting_line = self._update_posting_line(old_posting_line, "")
                    lines[posting_line_idx] = new_posting_line
            else:
                # Use individual posting representation
                trans_idx = transaction_line_number - 1
                old_trans_line = lines[trans_idx]
                new_trans_line = self._update_transaction_line(
                    old_trans_line, ""
                )  # Clear transaction status
                lines[trans_idx] = new_trans_line

                # Set status on each posting line
                for posting_line_idx in posting_lines:
                    old_posting_line = lines[posting_line_idx]
                    new_posting_line = self._update_posting_line(
                        old_posting_line, new_status
                    )
                    lines[posting_line_idx] = new_posting_line

            # Mark that we're making an internal change
            if self.file_watcher:
                self.file_watcher.mark_internal_change()

            return self.safe_editor.write_lines_safely(lines, read_time)

        except (IndexError, ValueError, OSError):
            return False

    def update_postings_status(
        self,
        posting_line_numbers: list[int],
        expected_current_status: str,
        new_status: str,
    ) -> bool:
        """Update status markers for a set of postings, with safety check.

        This is the main API for the reconciliation UI. It ensures all specified
        postings currently have the expected status before making any changes.
        Intelligently uses transaction headers vs individual postings.

        Args:
            posting_line_numbers: 1-based line numbers of postings to update
            expected_current_status: Status all postings must currently have ('', '!', or '*')
            new_status: New status to set ('', '!', or '*')

        Returns:
            True if update was successful, False if precondition failed or error occurred
        """
        if not posting_line_numbers:
            return True  # Nothing to do

        try:
            lines, read_time = self.safe_editor.read_lines_safely()

            # First, verify all postings have the expected status
            for line_num in posting_line_numbers:
                if line_num < 1 or line_num > len(lines):
                    return False
                if not self._is_valid_posting_line(lines[line_num - 1]):
                    return False  # Line is not a valid posting
                trans_line_num = self._find_transaction_for_posting(lines, line_num)
                if trans_line_num is None:
                    return False
                current_status = self._get_effective_posting_status(
                    lines, line_num, trans_line_num
                )
                if current_status != expected_current_status:
                    return False  # Precondition failed

            # Group postings by transaction
            transactions = {}  # transaction_line_number -> list of posting line numbers
            for posting_line_num in posting_line_numbers:
                trans_line_num = self._find_transaction_for_posting(
                    lines, posting_line_num
                )
                if trans_line_num is None:
                    return False
                if trans_line_num not in transactions:
                    transactions[trans_line_num] = []
                transactions[trans_line_num].append(posting_line_num)

            # Process each transaction
            for trans_line_num, posting_lines_in_trans in transactions.items():
                # Find ALL postings in this transaction (not just the ones we're updating)
                all_posting_lines = self._find_all_postings_for_transaction(
                    lines, trans_line_num
                )

                # Determine the status for each posting after our update
                final_statuses = {}
                for posting_line in all_posting_lines:
                    if posting_line in posting_lines_in_trans:
                        final_statuses[posting_line] = new_status
                    else:
                        final_statuses[posting_line] = (
                            self._get_effective_posting_status(
                                lines, posting_line, trans_line_num
                            )
                        )

                # Check if all postings will have the same status
                unique_statuses = set(final_statuses.values())
                all_same_status = len(unique_statuses) == 1

                if all_same_status and all_posting_lines:
                    # Use transaction header representation
                    trans_idx = trans_line_num - 1
                    lines[trans_idx] = self._update_transaction_line(
                        lines[trans_idx], new_status
                    )
                    # Clear status from all posting lines
                    for posting_line in all_posting_lines:
                        lines[posting_line - 1] = self._update_posting_line(
                            lines[posting_line - 1], ""
                        )
                else:
                    # Use individual posting representation
                    trans_idx = trans_line_num - 1
                    lines[trans_idx] = self._update_transaction_line(
                        lines[trans_idx], ""
                    )
                    # Set appropriate status on each posting
                    for posting_line, status in final_statuses.items():
                        lines[posting_line - 1] = self._update_posting_line(
                            lines[posting_line - 1], status
                        )

            # Mark that we're making an internal change
            if self.file_watcher:
                self.file_watcher.mark_internal_change()

            return self.safe_editor.write_lines_safely(lines, read_time)

        except (IndexError, ValueError, OSError):
            return False

    def _find_transaction_for_posting(
        self, lines: list[str], posting_line_num: int
    ) -> int | None:
        """Find the transaction header line for a given posting line."""
        # Search backwards for transaction header
        for i in range(
            posting_line_num - 2, -1, -1
        ):  # -2 because posting_line_num is 1-based
            line = lines[i]
            if re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}", line.strip()):
                return i + 1  # Convert to 1-based
            if not line.strip():
                # Empty line before finding transaction - something's wrong
                return None
        return None

    def _find_all_postings_for_transaction(
        self, lines: list[str], trans_line_num: int
    ) -> list[int]:
        """Find all posting lines for a given transaction."""
        posting_lines = []
        i = trans_line_num  # Start after transaction header (1-based)

        while i < len(lines):
            line = lines[i]
            if not line.strip():
                # Empty line - end of transaction
                break
            if re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}", line.strip()):
                # Next transaction - end of current transaction
                break
            if line.lstrip() and not line.startswith((" ", "\t")):
                # Non-indented line that's not a date - end of transaction
                break

            # This is a posting line
            if line.strip():  # Only add non-empty lines
                posting_lines.append(i + 1)  # Convert to 1-based
            i += 1

        return posting_lines

    def _extract_posting_status(self, line: str) -> str:
        """Extract the current status marker from a posting line."""
        # Posting line format: [STATUS] ACCOUNT [AMOUNT]
        stripped = line.lstrip()
        if stripped.startswith(("!", "*")):
            return stripped[0]
        return ""

    def _get_effective_posting_status(
        self, lines: list[str], posting_line_num: int, trans_line_num: int
    ) -> str:
        """Get the effective status of a posting, considering transaction header."""
        # First check if posting has explicit status
        posting_status = self._extract_posting_status(lines[posting_line_num - 1])
        if posting_status:
            return posting_status

        # Otherwise, check transaction header status
        trans_line = lines[trans_line_num - 1]
        match = re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}\s*([!*]?)", trans_line.strip())
        if match and match.group(1):
            return match.group(1)

        return ""

    def _is_valid_posting_line(self, line: str) -> bool:
        """Check if a line is a valid posting line."""
        stripped = line.strip()
        if not stripped:
            return False  # Empty line
        if stripped.startswith(";"):
            return False  # Comment line
        if re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}", stripped):
            return False  # Transaction header line
        return line.startswith((" ", "\t"))  # Must be indented (posting)

    def _update_transaction_line(self, line: str, new_status: str) -> str:
        """Update the status marker in a transaction header line."""
        # Transaction line format: DATE [STATUS] DESCRIPTION
        line_without_newline = line.rstrip("\n")
        match = re.match(
            r"^(\d{4}[-/]\d{2}[-/]\d{2})\s*([!*]?)\s*(.*)$",
            line_without_newline.strip(),
        )
        if not match:
            return line

        date = match.group(1)
        _ = match.group(2)  # old_status - not used but captured by regex
        description = match.group(3)

        # Preserve original whitespace structure
        leading_ws = line_without_newline[
            : len(line_without_newline) - len(line_without_newline.lstrip())
        ]
        has_newline = line.endswith("\n")

        # Build new line
        if new_status:
            new_line = f"{leading_ws}{date} {new_status} {description}"
        else:
            new_line = f"{leading_ws}{date} {description}"

        # Preserve original line ending
        if has_newline:
            new_line += "\n"

        return new_line

    def _update_posting_line(self, line: str, new_status: str) -> str:
        """Update the status marker in a posting line."""
        if not line.strip():
            return line

        # Preserve leading whitespace and newline
        line_without_newline = line.rstrip("\n")
        leading_ws = line_without_newline[
            : len(line_without_newline) - len(line_without_newline.lstrip())
        ]
        stripped = line_without_newline.lstrip()
        has_newline = line.endswith("\n")

        # Check if line has existing status
        has_existing_status = stripped.startswith(("!", "*"))

        # Remove existing status if present
        if has_existing_status:
            stripped = stripped[1:].lstrip()

        # If no new status and no existing status, return line unchanged
        if not new_status and not has_existing_status:
            return line

        # Build new line
        if new_status:
            new_line = f"{leading_ws}{new_status} {stripped}"
        else:
            # When removing status, reconstruct without status marker
            new_line = f"{leading_ws}{stripped}"

        # Preserve original line ending
        if has_newline:
            new_line += "\n"

        return new_line
