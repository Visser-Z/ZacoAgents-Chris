"""What the operator's own workbook already knows.

Two things, both of which make the queue's proposals better and neither of which is guessed:

* **The DN join.** Where a row already carries both an STM No and a DN, the operator has
  already decided which delivery note a payment run belongs to. Reusing that is the only DN
  answer in the system that is evidence rather than inference.
* **The series.** The `14xxx` numbers already used, so a minted number cannot collide with one.

In the supplied rounds the join recovers nothing: the book holds account sales `381900` and
`381950`, and the data holds `382399`-`382999`. That is not a reason to skip building it -- the
join is correct and pays from round 3 onward -- but it *is* the honest answer for today, and the
queue says so rather than implying the book had nothing to offer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from zaco.workbook.locate import WorkbookShapeError, read_rows

log = logging.getLogger("zaco.resolve.book")

#: The operator's own "not paid yet" marker in column F (D7). It is not an account sale, so it
#: must never become a join key -- every unpaid row in the book would link to one delivery note.
NOT_PAID_MARKER = "0"


@dataclass
class BookKnowledge:
    """Everything Phase 3 takes from the existing book."""

    links: dict[str, str] = field(default_factory=dict)
    """Account sale number to the delivery note already recorded against it."""

    delivery_notes: list[str] = field(default_factory=list)
    """Every DN in the book, so a minted number is next after all of them."""

    short_codes: list[str] = field(default_factory=list)
    """The descriptions the operator actually types, offered when capturing a product code."""

    row_count: int = 0
    problem: str | None = None
    """Why the book could not be read, when it could not. Absence of a book is not an error."""

    @property
    def is_readable(self) -> bool:
        return self.problem is None


def read(path: Path) -> BookKnowledge:
    """Read the book, or say why not. A missing book never stops a round being resolved."""
    if not path.exists():
        return BookKnowledge(
            problem=(
                f"No workbook at {path}. Delivery notes cannot be reused from it and a minted "
                "number has no series to be next in, so the queue will ask for each one."
            )
        )
    try:
        rows = read_rows(path)
    except (WorkbookShapeError, OSError, ValueError) as exc:
        log.warning("Could not read %s: %s", path, exc)
        return BookKnowledge(problem=str(exc))

    knowledge = BookKnowledge(row_count=len(rows))
    for row in rows:
        if row.dn:
            knowledge.delivery_notes.append(row.dn)
            if row.stm_no and row.stm_no != NOT_PAID_MARKER:
                knowledge.links.setdefault(row.stm_no, row.dn)
        if row.description and row.description not in knowledge.short_codes:
            knowledge.short_codes.append(row.description)
    return knowledge
