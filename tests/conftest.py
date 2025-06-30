#!/usr/bin/env python3
# pytest configuration and global fixtures

# Import the UI flow plugin hooks to register them
from .ui_flows import (
    pytest_addoption,
    pytest_sessionfinish,
    pytest_sessionstart,
    pytest_terminal_summary,
)

# Re-export the hooks so pytest can find them (not really necessary but makes
# linter happy).
__all__ = [
    "pytest_addoption",
    "pytest_sessionfinish",
    "pytest_sessionstart",
    "pytest_terminal_summary",
]
