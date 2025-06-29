# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running Tests
```bash
# Run all tests
mise run test

# Run specific test file
python -m pytest tests/test_sexp_parser.py -v

# Run specific test
python -m pytest "tests/test_sexp_parser.py::test_fixture[nil]" -v
```

### Code Quality
```bash
# Run all checks (lint, format, typecheck, test)
mise run check

# Format code
mise run format

# Run linter
mise run lint

# Fix linting issues
mise run lint -- --fix

# Type checking
mise run typecheck
```

### Application
```bash
# Run the reconciliation tool
mise run reconcile

# Or directly with arguments
ledger-reconcile path/to/file.ledger --account "CC:Amazon Chase" --target "$1,234.56"

# Generate HTML preview of S-expression test fixtures
mise run preview-sexp-tests
```

## Architecture Overview

The application follows a layered architecture with clear separation of concerns:

1. **UI Layer** (`reconcile_interface.py`): Textual-based TUI that handles user interaction
2. **Business Logic** (`ledger_interface.py`): Interfaces with the ledger CLI tool
3. **Data Layer** (`file_editor.py`): Safely modifies ledger files
4. **Parsing Layer** (`sexp_parser.py`): Parses S-expressions from ledger's emacs output

### Key Interactions

- The UI watches the ledger file for external changes via `file_watcher.py`
- Account selection uses fuzzy matching (prefers `fzf` if available, falls back to `fuzzywuzzy`)
- File editing is atomic to prevent race conditions
- S-expression parser handles ledger's emacs output format for structured data

### Data Flow
1. User selects account → `account_selector.py` (fuzzy search)
2. Ledger data fetched → `ledger_interface.py` calls `ledger emacs`
3. S-expressions parsed → `sexp_parser.py` converts to Python objects
4. UI displays transactions → `reconcile_interface.py` shows DataTable
5. Status updates → `file_editor.py` modifies ledger file safely
6. File changes detected → `file_watcher.py` triggers UI refresh

## Important Context

### IDEAS.md
There's an `IDEAS.md` file in `ledger_reconcile/` that contains a checklist of improvements to work on. Always check this file and mark completed items. (Don't just check off in your internal task list.) NEVER CHECK OFF AN ITEM IF `mise run check` FAILS.

### S-Expression Test Fixtures
Tests use data-driven approach with `.sexp` input files and `.json` expected output files in `tests/fixtures/sexp_parser/`. Tests prefixed with `bug_` are known issues (xfail). The HTML preview shows all test cases visually.

### Status Markers
- Empty string: Unreconciled transaction
- `!`: Pending/semi-reconciled
- `*`: Cleared/fully reconciled

### External Dependencies
- Requires `ledger` CLI tool installed
- Optional: `fzf` for better account selection
- Optional: `code` (VSCode) for editing integration

### Safety Considerations
- Never write to ledger files without using `FileEditor` class
- Always use `SafeFileEditor` for atomic writes
- File watcher ignores internal changes to prevent feedback loops
- Be careful writing test data to files with shell commands: you tend to get confused and accidentally end up with extra backslashes before exclamation points and similar things. Just write files with your file writing tool!
