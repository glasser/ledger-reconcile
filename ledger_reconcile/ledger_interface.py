#!/usr/bin/env python3
# Interface to the ledger CLI for extracting account and transaction data

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LedgerPosting:
    """Represents a posting within a transaction."""

    account: str
    amount: str
    status: str  # '', '!', or '*'
    line_number: int
    original_line: str


@dataclass
class LedgerTransaction:
    """Represents a complete transaction with all its postings."""

    date: str
    description: str
    status: str  # '', '!', or '*'
    line_number: int
    postings: list[LedgerPosting]
    original_line: str


@dataclass
class ReconciliationEntry:
    """Represents a transaction with only the postings for a specific account."""

    date: str
    description: str
    status: str  # '', '!', or '*'
    line_number: int  # Line number of the transaction header
    account_postings: list[LedgerPosting]  # Only postings for the target account
    original_line: str


class LedgerInterface:
    """Interface to extract data from ledger files using the ledger CLI."""

    def __init__(self, ledger_file: Path):
        self.ledger_file = ledger_file

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

    def get_account_balance(self, account: str) -> str:
        """Get the current balance for an account."""
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
        except subprocess.CalledProcessError:
            # For non-existent accounts, return $0.00
            return "$0.00"

        # Fallback return (should never be reached)
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
        parsed = self._parse_sexp_simple(normalized)
        if not parsed or not isinstance(parsed, list):
            return transactions

        # Each top-level element is a complete transaction
        for transaction_data in parsed:
            if isinstance(transaction_data, list) and len(transaction_data) >= 5:
                transaction = self._create_transaction_from_data(transaction_data)
                if transaction:
                    transactions.append(transaction)

        return transactions

    def _parse_sexp_simple(self, s: str):
        """Simple S-expression parser."""
        s = s.strip()
        if not s or s == "nil":
            return None

        if s[0] == '"':
            return self._parse_quoted_string(s)

        if s[0] != "(":
            return self._parse_atom(s)

        return self._parse_list(s)

    def _parse_quoted_string(self, s: str) -> str:
        """Parse a quoted string from S-expression."""
        i = 1
        while i < len(s) and s[i] != '"':
            if s[i] == "\\":
                i += 2  # skip escaped char
            else:
                i += 1
        return s[1:i] if i < len(s) else s[1:]

    def _parse_atom(self, s: str):
        """Parse an atomic value from S-expression."""
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return int(s)
        return s

    def _parse_list(self, s: str) -> list:
        """Parse a list from S-expression."""
        elements = []
        i = 1  # skip opening paren
        while i < len(s) - 1:  # skip closing paren
            if s[i] == " ":
                i += 1
                continue

            start = i
            if s[i] == '"':
                # String element
                i = self._find_string_end(s, i)
                elements.append(self._parse_sexp_simple(s[start:i]))
            elif s[i] == "(":
                # Nested list element
                i = self._find_list_end(s, i)
                elements.append(self._parse_sexp_simple(s[start:i]))
            else:
                # Atom element
                while i < len(s) and s[i] not in " ()":
                    i += 1
                elements.append(self._parse_sexp_simple(s[start:i]))

        return elements

    def _find_string_end(self, s: str, start: int) -> int:
        """Find the end of a quoted string."""
        i = start + 1
        while i < len(s) and s[i] != '"':
            if s[i] == "\\":
                i += 2
            else:
                i += 1
        return i + 1  # include closing quote

    def _find_list_end(self, s: str, start: int) -> int:
        """Find the end of a nested list."""
        depth = 1
        i = start + 1
        while i < len(s) and depth > 0:
            if s[i] == "(":
                depth += 1
            elif s[i] == ")":
                depth -= 1
            i += 1
        return i

    def _create_transaction_from_data(self, data: list) -> ReconciliationEntry | None:
        """Create a LedgerTransaction from parsed S-expression data."""
        try:
            # Format: (file line-no date-info code description posting1 posting2...)
            if len(data) < 5:
                return None

            line_number = data[1]

            # Date is a triple (high low microseconds) - convert to string
            date_info = data[2]
            if isinstance(date_info, list) and len(date_info) >= 2:
                # Convert emacs time to date
                import datetime

                seconds = date_info[0] * 65536 + date_info[1]
                dt = datetime.datetime.fromtimestamp(seconds)
                date = dt.strftime("%Y/%m/%d")
            else:
                date = "2024/01/01"  # fallback

            description = data[4] if data[4] else ""

            # Extract status from description if it starts with ! or *
            status, description = self._extract_status_from_description(description)

            # Parse postings
            postings = []
            for i in range(5, len(data)):
                posting_data = data[i]
                if isinstance(posting_data, list) and len(posting_data) >= 3:
                    posting_status = ""
                    if len(posting_data) > 3 and posting_data[3]:
                        # Convert posting status
                        if posting_data[3] == "pending":
                            posting_status = "!"
                        elif posting_data[3] == "cleared":
                            posting_status = "*"
                        else:
                            posting_status = posting_data[3]

                    # If transaction has no status but posting does, promote posting status to transaction
                    if not status and posting_status:
                        status = posting_status

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
                status=status,
                line_number=line_number,
                account_postings=postings,
                original_line="",  # Not available in emacs format
            )

        except (IndexError, TypeError, ValueError, AttributeError) as e:
            # If parsing fails, this indicates a bug in our S-expression parser
            # or unexpected ledger output format - fail loudly so it gets fixed
            msg = f"Failed to parse ledger emacs output: {e}\nRaw S-expression data: {data}"
            raise RuntimeError(msg) from e

    def _extract_status_from_description(self, description: str) -> tuple[str, str]:
        """Extract status marker from transaction description.

        Returns (status, cleaned_description) tuple.
        """
        if not description:
            return "", description

        # Define status prefixes and their corresponding markers
        status_patterns = [
            ("\\\\! ", "!"),  # Double-escaped pending
            ("\\\\* ", "*"),  # Double-escaped cleared
            ("\\! ", "!"),  # Escaped pending
            ("\\* ", "*"),  # Escaped cleared
            ("! ", "!"),  # Unescaped pending
            ("* ", "*"),  # Unescaped cleared
        ]

        for prefix, status in status_patterns:
            if description.startswith(prefix):
                return status, description[len(prefix) :]

        return "", description
