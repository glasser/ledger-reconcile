# S-expression parser for parsing ledger emacs output
# Extracted from ledger_interface.py for better modularity and testing


class SExpParser:
    """Parser for S-expressions returned by ledger emacs command."""

    def parse(self, s: str):
        """Parse an S-expression string."""
        s = s.strip()
        if not s or s == "nil":
            return None

        if s[0] == '"':
            return self._parse_quoted_string(s)

        if s[0] != "(":
            return self._parse_atom(s)

        return self._parse_list(s)

    def _parse_quoted_string(self, s: str) -> str:
        """Parse a quoted string from S-expression."""
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
        return "".join(result)

    def _parse_atom(self, s: str):
        """Parse an atomic value from S-expression."""
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return int(s)
        return s

    def _parse_list(self, s: str) -> list:
        """Parse a list from S-expression."""
        elements = []
        i = 1  # skip opening paren
        while i < len(s) - 1:  # skip closing paren
            if s[i].isspace():
                i += 1
                continue

            start = i
            if s[i] == '"':
                # String element
                i = self._find_string_end(s, i)
                elements.append(self.parse(s[start:i]))
            elif s[i] == "(":
                # Nested list element
                i = self._find_list_end(s, i)
                elements.append(self.parse(s[start:i]))
            else:
                # Atom element
                while i < len(s) and not s[i].isspace() and s[i] not in "()":
                    i += 1
                elements.append(self.parse(s[start:i]))

        return elements

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
            if s[i] == "(":
                depth += 1
            elif s[i] == ")":
                depth -= 1
            i += 1
        return i
