# S-expression parser for parsing ledger emacs output
# Extracted from ledger_interface.py for better modularity and testing


class SExpParseError(ValueError):
    """Exception raised when S-expression parsing fails."""

    pass


class SExpParser:
    """Parser for S-expressions returned by ledger emacs command."""

    def parse(self, s: str):
        """Parse an S-expression string."""
        s = s.strip()
        if not s:
            return None

        if s[0] == '"':
            result, consumed = self._parse_quoted_string(s)
            remaining = s[consumed:].strip()
            if remaining:
                raise SExpParseError(
                    f"Unexpected content after string: {remaining[:20]}"
                )
            return result

        if s[0] != "(":
            # For atoms, the entire string should be the atom
            result, consumed = self._parse_atom(s)
            remaining = s[consumed:].strip()
            if remaining:
                raise SExpParseError(f"Unexpected content after atom: {remaining[:20]}")
            return result

        # Parse the list and get how much was consumed
        result, consumed = self._parse_list(s)
        remaining = s[consumed:].strip()
        if remaining:
            raise SExpParseError(f"Unexpected content after list: {remaining[:20]}")
        return result

    def _parse_quoted_string(self, s: str) -> tuple[str, int]:
        """Parse a quoted string from S-expression.

        Returns:
            Tuple of (parsed string content, bytes consumed)
        """
        if not s.startswith('"'):
            raise SExpParseError(
                f"Expected quoted string to start with quote, got: {s[:10]}"
            )

        result = []
        i = 1
        while i < len(s) and s[i] != '"':
            if s[i] == "\\" and i + 1 < len(s):
                # Handle escape sequences
                next_char = s[i + 1]
                if next_char == '"':
                    result.append('"')
                elif next_char == "\\":
                    result.append("\\")
                elif next_char == "n":
                    result.append("\n")
                elif next_char == "t":
                    result.append("\t")
                elif next_char == "r":
                    result.append("\r")
                else:
                    # Unknown escape, keep as-is
                    result.append(next_char)
                i += 2
            else:
                result.append(s[i])
                i += 1

        if i >= len(s):
            raise SExpParseError(f"Unterminated quoted string: {s}")

        return "".join(result), i + 1  # +1 for the closing quote

    def _parse_atom(self, s: str) -> tuple[str | int | None, int]:
        """Parse an atomic value from S-expression.

        Returns:
            Tuple of (parsed value (string, int, or None), bytes consumed)
        """
        i = 0
        while i < len(s) and not s[i].isspace() and s[i] not in "()":
            i += 1

        atom_str = s[:i]
        if atom_str == "nil":
            return None, i
        if atom_str.isdigit() or (atom_str.startswith("-") and atom_str[1:].isdigit()):
            return int(atom_str), i
        return atom_str, i

    def _parse_list(self, s: str) -> tuple[list, int]:
        """Parse a list from S-expression.

        Returns:
            Tuple of (parsed list of elements, bytes consumed)
        """
        if not s.startswith("("):
            raise SExpParseError("Expected list to start with opening parenthesis")

        elements = []
        i = 1  # skip opening paren

        while i < len(s):
            if s[i].isspace():
                i += 1
                continue

            if s[i] == ")":
                # Found the closing paren for this list
                i += 1  # consume the closing paren
                return elements, i

            if s[i] == '"':
                # String element
                result, consumed = self._parse_quoted_string(s[i:])
                elements.append(result)
                i += consumed
            elif s[i] == "(":
                # Nested list element
                result, consumed = self._parse_list(s[i:])
                elements.append(result)
                i += consumed
            else:
                # Atom element
                result, consumed = self._parse_atom(s[i:])
                elements.append(result)
                i += consumed

        # If we reach here, we ran out of characters without finding a closing paren
        raise SExpParseError("Unclosed list - missing closing parenthesis")

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
            if s[i] == '"':
                # Skip over quoted string to avoid counting parens inside it
                i = self._find_string_end(s, i)
                continue
            elif s[i] == "(":
                depth += 1
            elif s[i] == ")":
                depth -= 1
            i += 1
        return i
