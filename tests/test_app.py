#!/usr/bin/env python3
# Test app for snapshot testing

import tempfile
from pathlib import Path

from ledger_reconcile.reconcile_interface import ReconcileApp


def create_test_ledger() -> Path:
    """Create a test ledger file."""
    content = """2024-01-01 Opening Balance
    Assets:Checking              $500.00
    Equity:Opening Balances

2024-01-02 ! Pending Transaction
    Assets:Checking               $100.00
    Expenses:Food

2024-01-03 Uncleared Transaction
    Assets:Checking               $200.00
    Expenses:Other
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ledger", delete=False
    ) as temp_file:
        temp_file.write(content)
        temp_file_path = temp_file.name
    return Path(temp_file_path)


# Create the app instance for snapshot testing
ledger_file = create_test_ledger()
app = ReconcileApp(ledger_file, "Assets:Checking", "$800.00")

if __name__ == "__main__":
    try:
        app.run()
    finally:
        ledger_file.unlink()
