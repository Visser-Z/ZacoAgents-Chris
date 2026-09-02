"""What a reader says when it cannot read something.

Section 4 requires readers to survive the documents as supplied, and section 13 assesses
whether they "fail loudly rather than quietly when they cannot". So a line a reader does not
understand becomes a `Problem` that travels with the result and is shown to the operator. It is
never skipped silently, and it never becomes a zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "error"
    """The document cannot be trusted. Nothing from it may be ingested."""

    WARNING = "warning"
    """Something is wrong or missing that the operator must see before relying on the figures."""

    NOTE = "note"
    """Worth saying, but the figures stand."""


@dataclass(frozen=True)
class Problem:
    severity: Severity
    message: str
    line_number: int | None = None
    line: str | None = None

    def __str__(self) -> str:
        where = f" (line {self.line_number})" if self.line_number else ""
        return f"{self.severity}{where}: {self.message}"


@dataclass
class ProblemLog:
    """Collects problems while parsing, so a reader never has to decide whether to raise."""

    items: list[Problem] = field(default_factory=list)

    def error(self, message: str, line_number: int | None = None, line: str | None = None) -> None:
        self.items.append(Problem(Severity.ERROR, message, line_number, _trim(line)))

    def warn(self, message: str, line_number: int | None = None, line: str | None = None) -> None:
        self.items.append(Problem(Severity.WARNING, message, line_number, _trim(line)))

    def note(self, message: str, line_number: int | None = None, line: str | None = None) -> None:
        self.items.append(Problem(Severity.NOTE, message, line_number, _trim(line)))

    @property
    def has_errors(self) -> bool:
        return any(p.severity is Severity.ERROR for p in self.items)

    def of(self, severity: Severity) -> list[Problem]:
        return [p for p in self.items if p.severity is severity]


def _trim(line: str | None) -> str | None:
    if line is None:
        return None
    line = line.rstrip("\r\n")
    return line if len(line) <= 200 else line[:197] + "..."
