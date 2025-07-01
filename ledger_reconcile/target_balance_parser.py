#!/usr/bin/env python3
# Parser for target balance amounts entered by user

from decimal import Decimal


def parse_balance(input_text: str) -> Decimal:
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
        Decimal with the parsed amount

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
        amount = Decimal(text)
    except Exception as e:
        raise ValueError(f"Invalid number format: {input_text}") from e

    # Apply negative sign
    if is_negative:
        amount = -amount

    return amount


def format_balance(amount: Decimal, align_dollar_sign: bool = False) -> str:
    """Format a Decimal amount as a currency string.

    Args:
        amount: The decimal amount to format
        align_dollar_sign: If True, add a space before positive amounts for alignment

    Returns:
        Formatted currency string (e.g., " $1,234.56" or "-$500.00")
    """
    # Format the amount (always show .00 for consistency)
    abs_amount = abs(amount)

    if amount < 0:
        formatted = f"-${abs_amount:,.2f}"
    else:
        # Add space for alignment if requested
        prefix = " " if align_dollar_sign else ""
        formatted = f"{prefix}${abs_amount:,.2f}"

    return formatted


class TargetBalanceParser:
    """Parses target balance amounts in various formats."""

    def parse(self, input_text: str) -> tuple[Decimal, str]:
        """Parse a target balance amount from user input.

        Args:
            input_text: The raw user input

        Returns:
            Tuple of (amount, formatted_display)
        """
        amount = parse_balance(input_text)
        formatted = format_balance(amount)
        return amount, formatted
