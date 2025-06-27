#!/usr/bin/env python3
# Tests for file editing operations

import tempfile
from pathlib import Path

from ledger_reconcile.file_editor import LedgerFileEditor


class TestLedgerFileEditor:
    """Test the LedgerFileEditor class."""

    def create_test_ledger(self, content: str) -> Path:
        """Create a temporary ledger file with the given content."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ledger", delete=False
        ) as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name
        return Path(temp_file_path)

    def read_file_content(self, file_path: Path) -> str:
        """Read the content of a file."""
        with file_path.open() as f:
            return f.read()

    def test_update_transaction_status_add_marker(self):
        """Test adding a status marker to a transaction."""
        content = """2024-01-01 Test Transaction
    Assets:Checking               $100.00
    Expenses:Test                 $50.00
"""
        ledger_file = self.create_test_ledger(content)

        try:
            editor = LedgerFileEditor(ledger_file)
            result = editor.update_transaction_status(1, "!")

            assert result is True

            updated_content = self.read_file_content(ledger_file)
            lines = updated_content.split("\n")
            assert "2024-01-01 ! Test Transaction" in lines[0]

        finally:
            ledger_file.unlink()

    def test_update_transaction_status_change_marker(self):
        """Test changing an existing status marker."""
        content = """2024-01-01 ! Test Transaction
    Assets:Checking               $100.00
    Expenses:Test                 $50.00
"""
        ledger_file = self.create_test_ledger(content)

        try:
            editor = LedgerFileEditor(ledger_file)
            result = editor.update_transaction_status(1, "*")

            assert result is True

            updated_content = self.read_file_content(ledger_file)
            lines = updated_content.split("\n")
            assert "2024-01-01 * Test Transaction" in lines[0]

        finally:
            ledger_file.unlink()

    def test_update_transaction_status_remove_marker(self):
        """Test removing a status marker from a transaction."""
        content = """2024-01-01 * Test Transaction
    Assets:Checking               $100.00
    Expenses:Test                 $50.00
"""
        ledger_file = self.create_test_ledger(content)

        try:
            editor = LedgerFileEditor(ledger_file)
            result = editor.update_transaction_status(1, "")

            assert result is True

            updated_content = self.read_file_content(ledger_file)
            lines = updated_content.split("\n")
            assert "2024-01-01 Test Transaction" in lines[0]

        finally:
            ledger_file.unlink()

    def test_update_posting_status(self):
        """Test updating status marker on individual posting."""
        content = """2024-01-01 Test Transaction
    Assets:Checking               $100.00
    Expenses:Test                 $50.00
"""
        ledger_file = self.create_test_ledger(content)

        try:
            editor = LedgerFileEditor(ledger_file)
            result = editor.update_posting_status(2, "!")

            assert result is True

            updated_content = self.read_file_content(ledger_file)
            lines = updated_content.split("\n")
            assert "! Assets:Checking" in lines[1]

        finally:
            ledger_file.unlink()

    def test_update_all_postings_in_transaction(self):
        """Test updating all postings in a transaction and moving status to header."""
        content = """2024-01-01 Test Transaction
    Assets:Checking               $100.00
    Expenses:Test                 $50.00
    CC:Visa                      -$150.00
"""
        ledger_file = self.create_test_ledger(content)

        try:
            editor = LedgerFileEditor(ledger_file)
            result = editor.update_all_postings_in_transaction(1, "*")

            assert result is True

            updated_content = self.read_file_content(ledger_file)
            lines = updated_content.split("\n")

            # Transaction header should have the status
            assert "2024-01-01 * Test Transaction" in lines[0]

            # Postings should not have status markers
            assert (
                "Assets:Checking" in lines[1]
                and "!" not in lines[1]
                and "*" not in lines[1]
            )
            assert (
                "Expenses:Test" in lines[2]
                and "!" not in lines[2]
                and "*" not in lines[2]
            )
            assert "CC:Visa" in lines[3] and "!" not in lines[3] and "*" not in lines[3]

        finally:
            ledger_file.unlink()

    def test_preserve_whitespace(self):
        """Test that whitespace is preserved when updating."""
        content = """2024-01-01 Test Transaction
    Assets:Checking               $100.00
        Expenses:Test             $50.00
"""
        ledger_file = self.create_test_ledger(content)

        try:
            editor = LedgerFileEditor(ledger_file)
            result = editor.update_posting_status(3, "!")

            assert result is True

            updated_content = self.read_file_content(ledger_file)
            lines = updated_content.split("\n")

            # Should preserve the extra indentation
            assert "        ! Expenses:Test" in lines[2]

        finally:
            ledger_file.unlink()

    def test_multiple_transactions(self):
        """Test editing in a file with multiple transactions."""
        content = """2024-01-01 First Transaction
    Assets:Checking               $100.00
    Expenses:Test                 $100.00

2024-01-02 Second Transaction
    Assets:Savings                $200.00
    Expenses:Test                 $200.00
"""
        ledger_file = self.create_test_ledger(content)

        try:
            editor = LedgerFileEditor(ledger_file)

            # Update first transaction
            result1 = editor.update_transaction_status(1, "!")
            # Update second transaction
            result2 = editor.update_transaction_status(5, "*")

            assert result1 is True
            assert result2 is True

            updated_content = self.read_file_content(ledger_file)
            lines = updated_content.split("\n")

            assert "2024-01-01 ! First Transaction" in lines[0]
            assert "2024-01-02 * Second Transaction" in lines[4]

        finally:
            ledger_file.unlink()

    def test_invalid_line_number(self):
        """Test handling invalid line numbers."""
        content = """2024-01-01 Test Transaction
    Assets:Checking               $100.00
"""
        ledger_file = self.create_test_ledger(content)

        try:
            editor = LedgerFileEditor(ledger_file)

            # Test line numbers that are too high or too low
            assert editor.update_transaction_status(0, "!") is False
            assert editor.update_transaction_status(100, "!") is False
            assert editor.update_posting_status(0, "!") is False
            assert editor.update_posting_status(100, "!") is False

        finally:
            ledger_file.unlink()
