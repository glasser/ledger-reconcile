#!/usr/bin/env python3
# Main CLI entry point for ledger-reconcile

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.prompt import Prompt

from .account_selector import AccountSelector
from .ledger_interface import LedgerInterface
from .reconcile_interface import run_reconcile_interface


@click.command()
@click.argument("ledger_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--account",
    "-a",
    help="Account name to reconcile (if not provided, will prompt with fuzzy search)",
)
@click.option(
    "--target",
    "-t",
    help="Target amount for reconciliation (if not provided, will prompt)",
)
def main(ledger_file: Path, account: str | None, target: str | None) -> None:
    """Terminal-based ledger reconciliation tool.

    LEDGER_FILE is the path to your ledger file to reconcile.
    """
    console = Console()

    try:
        # Initialize ledger interface
        ledger_interface = LedgerInterface(ledger_file)

        # Get all accounts once for validation and caching
        accounts = ledger_interface.get_accounts()

        if not accounts:
            console.print("[red]No accounts found in ledger file[/red]")
            sys.exit(1)

        # Get account if not provided
        if not account:
            console.print("[bold]Step 1: Select Account[/bold]")
            selector = AccountSelector(accounts)
            account = selector.select_account("Select account to reconcile")

            if not account:
                console.print("[yellow]No account selected. Exiting.[/yellow]")
                sys.exit(0)

        # Validate account exists
        if account not in accounts:
            console.print(f"[red]Account '{account}' not found in ledger file[/red]")
            sys.exit(1)

        # Get target amount if not provided
        if not target:
            console.print(f"\n[bold]Step 2: Set Target Amount for {account}[/bold]")
            cleared_pending_balance = ledger_interface.get_cleared_and_pending_balance(
                account
            )
            console.print(
                f"Cleared+pending balance: [cyan]{cleared_pending_balance}[/cyan]"
            )

            target = Prompt.ask(
                "Enter target amount for reconciliation",
                default=cleared_pending_balance,
            )

        # Launch reconciliation interface
        console.print(f"\n[bold]Step 3: Reconcile {account}[/bold]")
        console.print(f"Target amount: [cyan]{target}[/cyan]")
        console.print("\nLaunching reconciliation interface...")

        run_reconcile_interface(ledger_file, account, target, cached_accounts=accounts)

    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(0)
    except (OSError, ValueError, RuntimeError) as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
