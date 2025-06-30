# ledger-reconcile

Terminal-based reconciliation tool for ledger files.

## Features

- Fuzzy account selection with fzf support
- Interactive transaction status toggling
- VSCode integration for editing
- Batch reconciliation of semi-reconciled transactions

## Usage

```bash
ledger-reconcile path/to/your.ledger
```

Or specify account and target directly:

```bash
ledger-reconcile path/to/your.ledger --account "CC:Amazon Chase" --target "$1,234.56"
```

## Controls

- **Space**: Toggle transaction status (empty ↔ !)  
- **Enter**: Open transaction in VSCode
- **R**: Reconcile all semi-reconciled (!) transactions
- **Up/Down**: Navigate transactions
- **Q**: Quit

## Requirements

- Python 3.11+
- ledger CLI tool
- fzf (optional, for better account selection)
- VSCode (optional, for edit integration)