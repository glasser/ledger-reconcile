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

        If all postings in a transaction have the same status, the status should be
        moved to the transaction header instead of individual postings.

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

            # Find all posting lines for this transaction
            posting_lines = []
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
                i += 1

            # Update the transaction header
            trans_idx = transaction_line_number - 1
            old_trans_line = lines[trans_idx]
            new_trans_line = self._update_transaction_line(old_trans_line, new_status)
            lines[trans_idx] = new_trans_line

            # Clear status from all posting lines (since it's now on the transaction)
            for posting_line_idx in posting_lines:
                old_posting_line = lines[posting_line_idx]
                new_posting_line = self._update_posting_line(old_posting_line, "")
                lines[posting_line_idx] = new_posting_line

            # Mark that we're making an internal change
            if self.file_watcher:
                self.file_watcher.mark_internal_change()

            return self.safe_editor.write_lines_safely(lines, read_time)

        except (IndexError, ValueError, OSError):
            return False

    def _update_transaction_line(self, line: str, new_status: str) -> str:
        """Update the status marker in a transaction header line."""
        # Transaction line format: DATE [STATUS] DESCRIPTION
        match = re.match(r"^(\d{4}[-/]\d{2}[-/]\d{2})\s*([!*]?)\s*(.*)$", line.strip())
        if not match:
            return line

        date = match.group(1)
        _ = match.group(2)  # old_status - not used but captured by regex
        description = match.group(3)

        # Preserve original whitespace structure
        leading_ws = line[: len(line) - len(line.lstrip())]
        trailing_ws = ""
        if line.endswith("\n"):
            trailing_ws = "\n"

        # Build new line
        if new_status:
            new_line = f"{leading_ws}{date} {new_status} {description}{trailing_ws}"
        else:
            new_line = f"{leading_ws}{date} {description}{trailing_ws}"

        return new_line

    def _update_posting_line(self, line: str, new_status: str) -> str:
        """Update the status marker in a posting line."""
        if not line.strip():
            return line

        # Preserve leading whitespace
        leading_ws = line[: len(line) - len(line.lstrip())]
        stripped = line.lstrip()

        # Check if line has existing status
        has_existing_status = stripped.startswith(("!", "*"))

        # Remove existing status if present
        if has_existing_status:
            stripped = stripped[1:].lstrip()

        # If no new status and no existing status, return line unchanged
        if not new_status and not has_existing_status:
            return line

        # Preserve trailing whitespace/newline
        trailing_ws = ""
        if line.endswith("\n"):
            trailing_ws = "\n"

        # Build new line
        if new_status:
            new_line = f"{leading_ws}{new_status} {stripped}{trailing_ws}"
        else:
            # When removing status, reconstruct without status marker
            new_line = f"{leading_ws}{stripped}{trailing_ws}"

        return new_line
