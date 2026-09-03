"""Does the book still hold what the record says a round wrote?

An append marks the round and writes the file in one step, so the two cannot come apart at the
moment of writing (D4). They can come apart afterwards. Rolling the book back to an earlier
version restores the *file* and deliberately leaves the round's `appended` mark alone --
`routes_workbook.restore` says why: the rows may or may not be in the version being restored, and
quietly reopening the round would invite a second append duplicating whatever survived.

That decision is right and it leaves the operator blind. The record goes on saying "round 1 wrote
rows 5-9" while the file may no longer have a row 5. Nothing in the system said so.

This module says so. It compares what the record claims against what the file actually holds and
reports the difference in plain words. It changes nothing and decides nothing -- §11: where the
honest answer is "these disagree", make it visible in the output rather than in the code.

**What it compares, and what it therefore cannot see.** `read_rows` carries a row's delivery
note, statement number and description, so those are what is checked. The money in a row is not,
because the book does not give it back to us here. A version swapped for another carrying the
same rows with different figures would pass this check, and the panel says so rather than letting
silence read as a clean bill of health (§10).
"""

from __future__ import annotations

from dataclasses import dataclass

from zaco.workbook.locate import BookRow

#: Stated wherever an agreement is shown. The limits of the check travel with its result.
CHECKED = (
    "Compared on delivery note, statement number and description, at the row numbers the record "
    "claims. The figures in those rows are not compared."
)


@dataclass(frozen=True)
class RowClaim:
    """One row as the record says it was written."""

    row_number: int
    dn: str | None
    stm_no: str | None
    description: str | None


@dataclass(frozen=True)
class Agreement:
    """Whether the file still holds a round's rows, and what differs when it does not."""

    agrees: bool
    finding: str | None
    checked: str = CHECKED


def _same(claimed: str | None, found: str | None) -> bool:
    """Blank and absent are the same thing in a spreadsheet cell, and only here."""
    return (claimed or "").strip() == (found or "").strip()


def compare(claims: list[RowClaim], book: list[BookRow]) -> Agreement:
    """Hold the claimed rows against the rows the file actually has at those numbers."""
    if not claims:
        return Agreement(
            agrees=True,
            finding=None,
            checked="The record claims no rows for this round, so there was nothing to compare.",
        )

    at = {row.row_number: row for row in book}
    missing = [claim.row_number for claim in claims if claim.row_number not in at]
    if len(missing) == len(claims):
        first, last = claims[0].row_number, claims[-1].row_number
        return Agreement(
            agrees=False,
            finding=(
                f"The record says this round wrote rows {first}-{last}, and the book has no rows "
                f"there at all. The most likely cause is a rollback to a version taken before "
                f"this round was appended. The round keeps its appended mark, so it cannot be "
                f"appended again without someone deciding to release it."
            ),
        )
    if missing:
        return Agreement(
            agrees=False,
            finding=(
                f"The book is missing {len(missing)} of the {len(claims)} rows this round claims: "
                f"{', '.join(str(n) for n in missing)}. Part of a round in the book is worse than "
                f"none of it, so this is worth resolving before anything else is appended."
            ),
        )

    differing = [
        claim
        for claim in claims
        if not (
            _same(claim.dn, at[claim.row_number].dn)
            and _same(claim.stm_no, at[claim.row_number].stm_no)
            and _same(claim.description, at[claim.row_number].description)
        )
    ]
    if differing:
        shown = ", ".join(str(claim.row_number) for claim in differing[:5])
        more = "" if len(differing) <= 5 else f" (and {len(differing) - 5} more)"
        return Agreement(
            agrees=False,
            finding=(
                f"The book has rows where this round wrote, but {len(differing)} of them no longer "
                f"read as this round's: {shown}{more}. Two things cause this and they need telling "
                f"apart. Either the book was rolled back to a version holding different rows, or a "
                f"reader has been corrected since the append, so the round derives something today "
                f"that it did not derive then. The file is the thing that was settled against."
            ),
        )
    return Agreement(agrees=True, finding=None)


def contested(spans: dict[int, tuple[int, int]]) -> dict[int, str]:
    """Rounds whose claimed row spans overlap each other.

    Two rounds claiming one row means at least one of them is wrong about where it lives, which
    no per-round comparison can see -- each may match the file perfectly on its own.
    """
    found: dict[int, str] = {}
    for round_id, (first, last) in spans.items():
        clashes = sorted(
            other
            for other, (other_first, other_last) in spans.items()
            if other != round_id and first <= other_last and other_first <= last
        )
        if clashes:
            names = ", ".join(f"#{other}" for other in clashes)
            found[round_id] = (
                f"Rows {first}-{last} are also claimed by {names}. Two rounds cannot both own a "
                f"row; the record of where at least one of them went is wrong."
            )
    return found
