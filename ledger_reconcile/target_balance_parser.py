#!/usr/bin/env python3
# Parser for target balance amounts entered by user

from dataclasses import dataclass


@dataclass
class ParsedBalance:
    """Represents a parsed balance amount."""

    amount: float
    formatted_display: str


class TargetBalanceParser:
    """Parses target balance amounts in various formats."""

    def parse(self, input_text: str) -> ParsedBalance:
        """Parse a target balance amount from user input.

        Supports formats like:
        - $1234.56
        - $1,234.56
        - 1234.56
        - -$500.00
        - $100 (adds .00)

        Args:
            input_text: The raw user input

        Returns:
            ParsedBalance with the parsed amount and formatted display

        Raises:
            ValueError: If the input cannot be parsed as a valid amount
        """
        if not input_text or not input_text.strip():
            raise ValueError("Empty input")

        # Clean up whitespace
        text = input_text.strip()

        # Check for negative sign at the beginning
        is_negative = text.startswith("-")
        if is_negative:
            text = text[1:].strip()

        # Remove dollar sign if present
        has_dollar_sign = text.startswith("$")
        if has_dollar_sign:
            text = text[1:].strip()

        # Remove commas and spaces (handles bad copy-paste, OCR, etc.)
        text = text.replace(",", "").replace(" ", "")

        # Validate that what's left is a valid number
        try:
            amount = float(text)
        except ValueError as e:
            raise ValueError(f"Invalid number format: {input_text}") from e

        # Apply negative sign
        if is_negative:
            amount = -amount

        # Format for display (always show .00 for consistency)
        abs_amount = abs(amount)
        formatted = f"${abs_amount:,.2f}"

        if is_negative:
            formatted = f"-{formatted}"

        return ParsedBalance(amount=amount, formatted_display=formatted)


def calculate_delta(target_amount: str, cleared_pending_balance: str) -> str:
    """Calculate the delta between target and cleared+pending balance.

    Args:
        target_amount: Target balance as formatted string (e.g., "$1,234.56")
        cleared_pending_balance: Cleared+pending balance as formatted string (e.g., "$500.00")

    Returns:
        Formatted delta string (e.g., "$734.56" or "-$234.56")
    """
    parser = TargetBalanceParser()

    target_parsed = parser.parse(target_amount)
    cleared_pending_parsed = parser.parse(cleared_pending_balance)

    delta = target_parsed.amount - cleared_pending_parsed.amount

    # Format the delta (always show .00 for consistency)
    abs_delta = abs(delta)
    formatted = f"${abs_delta:,.2f}"

    if delta < 0:
        formatted = f"-{formatted}"

    return formatted
