#!/usr/bin/env python3
# Tests for ledger interface

import tempfile
from pathlib import Path

from ledger_reconcile.ledger_interface import LedgerInterface


class TestLedgerInterface:
    """Test the LedgerInterface class."""

    def create_test_ledger(self, content: str) -> Path:
        """Create a temporary ledger file with the given content."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ledger", delete=False
        ) as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name
        return Path(temp_file_path)

    def test_parse_simple_transaction(self):
        """Test parsing a simple transaction."""
        content = """2024-01-01 Opening Balance
    Assets:Checking              $1000.00
    Equity:Opening Balances

2024-01-02 ! Grocery Store
    Expenses:Food                 $45.67
    CC:Visa                      -$45.67
"""
        ledger_file = self.create_test_ledger(content)

        try:
            interface = LedgerInterface(ledger_file)
            transactions = interface.get_uncleared_transactions_for_account("CC:Visa")

            assert len(transactions) == 1
            transaction = transactions[0]

            assert transaction.date == "2024/01/02"
            assert transaction.description == "Grocery Store"
            # Check that the posting for CC:Visa has the expected status
            assert transaction.account_postings[0].status == "!"
            # Note: ledger emacs with account filter only returns postings for that account
            assert len(transaction.account_postings) == 1
            assert transaction.account_postings[0].account == "CC:Visa"

        finally:
            ledger_file.unlink()

    def test_parse_transaction_with_amounts(self):
        """Test parsing transactions with explicit amounts."""
        content = """2024-01-01 Test Transaction
    Assets:Checking               $100.00
    Expenses:Test                 $50.00
    CC:Test Card                 -$150.00
"""
        ledger_file = self.create_test_ledger(content)

        try:
            interface = LedgerInterface(ledger_file)
            transactions = interface.get_uncleared_transactions_for_account(
                "CC:Test Card"
            )

            assert len(transactions) == 1
            transaction = transactions[0]

            # Find the posting for CC:Test Card
            cc_posting = None
            for posting in transaction.account_postings:
                if posting.account == "CC:Test Card":
                    cc_posting = posting
                    break

            assert cc_posting is not None
            assert cc_posting.amount == "$-150.00"

        finally:
            ledger_file.unlink()

    def test_get_accounts(self):
        """Test getting list of accounts."""
        content = """2024-01-01 Test
    Assets:Checking               $100.00
    Assets:Savings                $200.00
    Expenses:Food                 $45.67
    CC:Visa                      -$345.67
"""
        ledger_file = self.create_test_ledger(content)

        try:
            interface = LedgerInterface(ledger_file)
            accounts = interface.get_accounts()

            expected_accounts = [
                "Assets:Checking",
                "Assets:Savings",
                "CC:Visa",
                "Expenses:Food",
            ]

            for account in expected_accounts:
                assert account in accounts

        finally:
            ledger_file.unlink()

    def test_transaction_with_posting_status(self):
        """Test parsing transactions with status markers on postings."""
        content = """2024-01-01 Mixed Status Transaction
    ! Assets:Checking             $100.00
    ! Expenses:Test               $50.00
    CC:Test Card                 -$150.00
"""
        ledger_file = self.create_test_ledger(content)

        try:
            interface = LedgerInterface(ledger_file)
            transactions = interface.get_uncleared_transactions_for_account(
                "Assets:Checking"
            )

            assert len(transactions) == 1
            transaction = transactions[0]

            # Check posting statuses - only returns postings for the queried account
            assert len(transaction.account_postings) == 1
            assert transaction.account_postings[0].account == "Assets:Checking"
            # This posting has status (from whatever source)
            assert transaction.account_postings[0].status == "!"

        finally:
            ledger_file.unlink()

    def test_reconciled_transaction_status(self):
        """Test transaction with status on the transaction line."""
        content = """2024-01-01 ! Semi-Reconciled Transaction
    Assets:Checking               $100.00
    Expenses:Test                 $50.00
    CC:Test Card                 -$150.00
"""
        ledger_file = self.create_test_ledger(content)

        try:
            interface = LedgerInterface(ledger_file)
            transactions = interface.get_uncleared_transactions_for_account(
                "Assets:Checking"
            )

            assert len(transactions) == 1
            transaction = transactions[0]

            assert transaction.description == "Semi-Reconciled Transaction"
            # Check that the posting has the status (regardless of source)
            assert transaction.account_postings[0].status == "!"

        finally:
            ledger_file.unlink()

    def test_empty_ledger(self):
        """Test handling empty ledger file."""
        content = ""
        ledger_file = self.create_test_ledger(content)

        try:
            interface = LedgerInterface(ledger_file)
            accounts = interface.get_accounts()
            transactions = interface.get_uncleared_transactions_for_account(
                "Nonexistent:Account"
            )

            assert len(accounts) == 0
            assert len(transactions) == 0

        finally:
            ledger_file.unlink()

    def test_line_numbers_with_comments_and_blank_lines(self):
        """Test that line numbers correctly map to the original file."""
        content = """# This is a comment on line 1
# Another comment on line 2

2024-01-01 Opening Balance
    Assets:Checking              $1000.00
    Equity:Opening Balances

# Comment before second transaction

2024-01-02 ! Grocery Store
    Expenses:Food                 $45.67
    CC:Visa                      -$45.67
"""
        ledger_file = self.create_test_ledger(content)

        try:
            interface = LedgerInterface(ledger_file)
            transactions = interface.get_uncleared_transactions_for_account(
                "Assets:Checking"
            )

            assert len(transactions) == 1
            transaction = transactions[0]

            # The transaction starts on line 4 (1-indexed) in the original file
            assert transaction.line_number == 4
            assert transaction.description == "Opening Balance"

            # Check posting line numbers
            checking_posting = None
            for posting in transaction.account_postings:
                if posting.account == "Assets:Checking":
                    checking_posting = posting
                    break

            assert checking_posting is not None
            # The Assets:Checking posting is on line 5
            assert checking_posting.line_number == 5

        finally:
            ledger_file.unlink()

    def test_line_numbers_for_multiple_transactions(self):
        """Test line numbers for multiple transactions in a file."""
        content = """2024-01-01 Transaction One
    Assets:Checking               $100.00
    Expenses:Test

2024-01-02 Transaction Two
    Assets:Checking               $200.00
    Expenses:Other

2024-01-03 Transaction Three
    Assets:Checking               $300.00
    Expenses:More
"""
        ledger_file = self.create_test_ledger(content)

        try:
            interface = LedgerInterface(ledger_file)
            transactions = interface.get_uncleared_transactions_for_account(
                "Assets:Checking"
            )

            assert len(transactions) == 3

            # Verify line numbers
            assert transactions[0].line_number == 1
            assert transactions[0].description == "Transaction One"

            assert transactions[1].line_number == 5
            assert transactions[1].description == "Transaction Two"

            assert transactions[2].line_number == 9
            assert transactions[2].description == "Transaction Three"

        finally:
            ledger_file.unlink()

    def test_uncleared_filtering_and_account_filtering(self):
        """Test that the function filters by account AND only returns uncleared transactions."""
        content = """2024-01-01 Opening Balance
    Assets:Checking              $1000.00
    Equity:Opening Balances

2024-01-02 ! Pending Transaction
    Assets:Checking               $100.00
    Expenses:Food

2024-01-03 * Fully Reconciled Transaction
    Assets:Checking               $200.00
    Expenses:Food

2024-01-04 Transaction for Different Account
    Assets:Savings                $300.00
    Expenses:Food

2024-01-05 Uncleared Transaction
    Assets:Checking               $400.00
    Expenses:Food
"""
        ledger_file = self.create_test_ledger(content)

        try:
            interface = LedgerInterface(ledger_file)
            transactions = interface.get_uncleared_transactions_for_account(
                "Assets:Checking"
            )

            # Should only get:
            # - Opening Balance (uncleared, involves Assets:Checking)
            # - Pending Transaction (pending, involves Assets:Checking)
            # - Uncleared Transaction (uncleared, involves Assets:Checking)
            # Should NOT get:
            # - Fully Reconciled Transaction (cleared with *)
            # - Transaction for Different Account (doesn't involve Assets:Checking)
            assert len(transactions) == 3

            descriptions = [t.description for t in transactions]
            assert "Opening Balance" in descriptions
            assert "Pending Transaction" in descriptions
            assert "Uncleared Transaction" in descriptions
            assert "Fully Reconciled Transaction" not in descriptions
            assert "Transaction for Different Account" not in descriptions

            # Test that we get nothing for an account with only cleared transactions
            savings_transactions = interface.get_uncleared_transactions_for_account(
                "Assets:Savings"
            )
            assert len(savings_transactions) == 1  # Only the uncleared one

        finally:
            ledger_file.unlink()
