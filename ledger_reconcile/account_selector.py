#!/usr/bin/env python3
# Account selection with fuzzy matching

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from rich.console import Console


class AccountSelector:
    """Handles account selection using fzf."""

    def __init__(self, accounts: list[str]):
        self.accounts = accounts
        self.console = Console()

    def select_account(self, prompt_text: str = "Select account") -> str | None:
        """Allow user to select an account using fzf.

        Returns None if fzf is not available or user cancels.
        """
        if not self.accounts:
            self.console.print("[red]No accounts found in ledger file[/red]")
            return None

        # Try to use fzf if available
        try:
            return self._select_with_fzf(prompt_text)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # fzf not available - user must use --account flag
            self.console.print(
                "[yellow]fzf not found - please install fzf or use the --account flag[/yellow]"
            )
            return None

    def _select_with_fzf(self, prompt_text: str) -> str | None:
        """Use fzf for account selection."""
        # Create temporary file with accounts
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            for account in self.accounts:
                f.write(f"{account}\n")
            temp_file = f.name

        try:
            # Run fzf with the accounts file
            with Path(temp_file).open("r") as stdin_file:
                result = subprocess.run(
                    [
                        "fzf",
                        "--prompt",
                        f"{prompt_text}: ",
                        "--height",
                        "40%",
                        "--reverse",
                        "--border",
                        "--preview-window",
                        "hidden",
                    ],
                    stdin=stdin_file,
                    capture_output=True,
                    text=True,
                    check=True,
                )

            selected = result.stdout.strip()
            return selected if selected else None

        finally:
            # Clean up temp file
            Path(temp_file).unlink(missing_ok=True)
