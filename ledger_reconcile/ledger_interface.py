#!/usr/bin/env python3
# Interface to the ledger CLI for extracting account and transaction data

from __future__ import annotations

import datetime
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .sexp_parser import SExpParser


@dataclass
class LedgerPosting:
    """Represents a posting with its reconciliation status."""

    account: str
    amount: str
    status: str  # The reconciliation status of this posting ("", "!", or "*")
    line_number: int
    original_line: str


@dataclass
class ReconciliationEntry:
    """Represents a transaction with only the postings for a specific account."""

    date: str
    description: str
    line_number: int  # Line number of the transaction header
    account_postings: list[LedgerPosting]  # Only postings for the target account
    original_line: str


class LedgerInterface:
    """Interface to extract data from ledger files using the ledger CLI."""

    def __init__(self, ledger_file: Path):
        self.ledger_file = ledger_file
        self.sexp_parser = SExpParser()

    def get_accounts(self) -> list[str]:
        """Get all account names from the ledger file."""
        try:
            result = subprocess.run(
                [
                    "ledger",
                    "-f",
                    str(self.ledger_file),
                    "--no-aliases",
                    "--no-pager",
                    "--price-db",
                    "/dev/null",
                    "accounts",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            accounts = [
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
            ]
            return sorted(accounts)
        except subprocess.CalledProcessError:
            # For empty files or files with no accounts, return empty list
            return []

    def get_uncleared_transactions_for_account(
        self, account: str
    ) -> list[ReconciliationEntry]:
        """Get all uncleared transactions involving the specified account."""
        try:
            # Use ledger emacs to get transaction data with proper line numbers
            # --uncleared filters out fully reconciled (*) transactions
            result = subprocess.run(
                [
                    "ledger",
                    "-f",
                    str(self.ledger_file),
                    "--no-aliases",
                    "--no-pager",
                    "--price-db",
                    "/dev/null",
                    "--uncleared",
                    "emacs",
                    account,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return self._parse_ledger_emacs_output(result.stdout)
        except subprocess.CalledProcessError:
            # For empty results or non-existent accounts, return empty list
            return []

    def get_cleared_and_pending_balance(self, account: str) -> str:
        """Get the balance for an account including only cleared and pending transactions.

        This uses ledger's --limit option to filter to 'cleared or pending' status.
        Cleared transactions have '*' status, pending have '!' status.
        """
        try:
            result = subprocess.run(
                [
                    "ledger",
                    "-f",
                    str(self.ledger_file),
                    "--no-aliases",
                    "--no-pager",
                    "--price-db",
                    "/dev/null",
                    "--limit",
                    "cleared or pending",
                    "balance",
                    account,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            # Extract just the amount from the balance output
            lines = result.stdout.strip().split("\n")
            if lines and lines[0].strip():
                # Balance line format is typically "    $1,234.56  Account:Name"
                balance_line = lines[0]
                # Extract the amount (everything before the account name)
                parts = balance_line.strip().split()
                if parts:
                    return parts[0]
                else:
                    return "$0.00"
            else:
                return "$0.00"
        except subprocess.CalledProcessError:
            # For non-existent accounts or no cleared/pending transactions, return $0.00
            return "$0.00"

    def _parse_ledger_emacs_output(
        self, ledger_output: str
    ) -> list[ReconciliationEntry]:
        """Parse the S-expression output from 'ledger emacs' command."""
        transactions = []

        if not ledger_output.strip():
            return transactions

        # Normalize whitespace and parse as a single S-expression
        normalized = " ".join(ledger_output.split())

        if not normalized or not normalized.startswith("("):
            return transactions

        # Parse the whole S-expression - it contains multiple transactions
        parsed = self.sexp_parser.parse(normalized)
        if not parsed or not isinstance(parsed, list):
            return transactions

        # Each top-level element is a complete transaction
        for transaction_data in parsed:
            if isinstance(transaction_data, list) and len(transaction_data) >= 5:
                transaction = self._create_transaction_from_data(transaction_data)
                if transaction:
                    transactions.append(transaction)

        return transactions

    def _create_transaction_from_data(self, data: list) -> ReconciliationEntry | None:
        """Create a ReconciliationEntry from parsed S-expression data."""
        try:
            # Format: (file line-no date-info code description posting1 posting2...)
            if len(data) < 5:
                return None

            line_number = data[1]

            # Date is a triple (high low microseconds) - convert to string
            date_info = data[2]
            if isinstance(date_info, list) and len(date_info) >= 2:
                # Convert emacs time to date
                seconds = date_info[0] * 65536 + date_info[1]
                dt = datetime.datetime.fromtimestamp(seconds)
                date = dt.strftime("%Y/%m/%d")
            else:
                date = "2024/01/01"  # fallback

            description = data[4] if data[4] else ""

            # Parse postings - just extract the status for each posting
            postings = []
            for i in range(5, len(data)):
                posting_data = data[i]
                if isinstance(posting_data, list) and len(posting_data) >= 3:
                    posting_status = self._convert_status(
                        posting_data[3] if len(posting_data) > 3 else None
                    )

                    posting_obj = LedgerPosting(
                        account=posting_data[1] if len(posting_data) > 1 else "",
                        amount=posting_data[2] if len(posting_data) > 2 else "",
                        status=posting_status,
                        line_number=posting_data[0] if len(posting_data) > 0 else 0,
                        original_line="",  # Not available in emacs format
                    )
                    postings.append(posting_obj)

            # Create the reconciliation entry
            return ReconciliationEntry(
                date=date,
                description=description,
                line_number=line_number,
                account_postings=postings,
                original_line="",  # Not available in emacs format
            )

        except (IndexError, TypeError, ValueError, AttributeError) as e:
            # If parsing fails, this indicates a bug in our S-expression parser
            # or unexpected ledger output format - fail loudly so it gets fixed
            msg = f"Failed to parse ledger emacs output: {e}\nRaw S-expression data: {data}"
            raise RuntimeError(msg) from e

    def _convert_status(self, ledger_status) -> str:
        """Convert ledger emacs status to our status format."""
        if not ledger_status:
            return ""
        if ledger_status == "pending":
            return "!"
        if ledger_status == "cleared":
            return "*"
        if isinstance(ledger_status, str):
            return ledger_status
        return ""
