#!/usr/bin/env python3
# Account selection with fuzzy matching

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from fuzzywuzzy import fuzz, process
from rich.console import Console
from rich.prompt import Prompt


class AccountSelector:
    """Handles account selection with fuzzy matching support."""

    def __init__(self, accounts: list[str]):
        self.accounts = accounts
        self.console = Console()

    def select_account(self, prompt_text: str = "Select account") -> str | None:
        """Allow user to select an account using fuzzy matching.

        First tries to use fzf if available, otherwise falls back to
        a simple text-based fuzzy search interface.
        """
        if not self.accounts:
            self.console.print("[red]No accounts found in ledger file[/red]")
            return None

        # Try to use fzf if available
        try:
            return self._select_with_fzf(prompt_text)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fall back to built-in fuzzy search
            return self._select_with_builtin_fuzzy(prompt_text)

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

    def _select_with_builtin_fuzzy(self, prompt_text: str) -> str | None:
        """Built-in fuzzy search fallback when fzf is not available."""
        self.console.print(f"\n[bold]{prompt_text}[/bold]")
        self.console.print(
            "[dim]Type to search (fuzzy matching), or press Enter with empty input to cancel[/dim]"
        )

        while True:
            query = Prompt.ask("\nSearch accounts", default="")

            if not query:
                return None

            # Perform fuzzy search
            matches = process.extract(
                query, self.accounts, limit=10, scorer=fuzz.partial_ratio
            )
            if matches is None:
                matches = []

            if not matches:
                self.console.print(
                    "[yellow]No matches found. Try a different search term.[/yellow]"
                )
                continue

            # Display matches
            self.console.print("\n[bold]Matches:[/bold]")
            for i, (account, score) in enumerate(matches, 1):  # type: ignore[misc]
                self.console.print(
                    f"[cyan]{i:2}[/cyan]. {account} [dim]({score}% match)[/dim]"
                )

            # Get user selection
            try:
                choice = Prompt.ask(
                    f"\nSelect account (1-{len(matches)}) or search again", default=""
                )

                if not choice:
                    continue  # Search again

                index = int(choice) - 1
                if 0 <= index < len(matches):
                    return matches[index][0]
                else:
                    self.console.print(
                        f"[red]Invalid choice. Please enter 1-{len(matches)}[/red]"
                    )

            except ValueError:
                self.console.print("[red]Invalid input. Please enter a number.[/red]")
