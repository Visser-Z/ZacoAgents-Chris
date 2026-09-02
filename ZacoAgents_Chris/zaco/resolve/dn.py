"""Delivery note numbers: proposed with reasoning, never derived and never assumed (D8-D11).

Workbook column A is Zaco's own delivery note number. **No agent report carries it.** The
account sales statement prints a field labelled `DELIVERY NOTE NO : 203003`, which is the
agent's own number in the same `203xxx` series as the payment reports' FMS IDs -- Zaco's
delivery notes are `14xxx`. Reading that field into column A gives a book that looks finished
and is wrong in every row, so this module never looks at it.

One DN can also cover several market deliveries (`20026*14705 & 14706` is a single payment
against two references), so the relationship is one-to-many and cannot be derived even in
principle. What is possible is to *propose* a number and show the working:

1. **Reuse.** Where the workbook already links an account sale to a DN, that DN is the answer
   and carries no guesswork at all. In the supplied rounds this recovers nothing -- the book
   holds `381900`/`381950` and the data holds `382399`-`382999` -- but it is the only source
   that is evidence rather than inference, so it is tried first and pays from round 3 onward.
2. **The reference half.** `20026*14720` splits into a producer half and a reference half, and
   the reference half is *often* the delivery note. Only proposed when it passes all three
   tests below.
3. **Mint.** The next free number above everything known in the series.

Every one of those is a proposal. Nothing here writes a DN; `needs_approval` is on every
proposal this module produces, and the only proposal that is not a guess still has to be
looked at.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

#: Zaco's delivery note series. Five digits beginning `14`, which is what the workbook holds
#: (`14690`-`14692`) and what every usable reference half in the supplied data looks like.
DN_SERIES = re.compile(r"^14\d{3}$")

#: The top of the series. Minting past it would leave the space the operator recognises.
SERIES_CEILING = 14999


class DnProvenance(StrEnum):
    """Where a delivery note number came from. Held in the system, never in the sheet (D9)."""

    WORKBOOK = "workbook"
    """Already linked to this account sale in the operator's own book. Evidence, not inference."""

    REFERENCE = "reference"
    """The supplier reference half, which passed all three tests."""

    MINTED = "minted"
    """Nothing to go on, so the next free number in the series."""

    OPERATOR = "operator"
    """Typed by hand. Overrides any proposal, and needs no justification beyond being said."""

    NONE_FOREIGN_PRODUCER = "none_foreign_producer"
    """Deliberately no DN: the load is another producer's produce (D11).

    A recorded answer, not a blank. The row is written with column A visibly empty and the
    reason attached, so "no DN" can be told apart from "nobody has got to this one yet".
    """


@dataclass(frozen=True)
class Test:
    """One of the three conditions the reference half has to meet, and whether it met it."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class CounterEvidence:
    """Positive proof that a reference is *not* a delivery note (D10).

    Deliberately narrow. A flag that appears on most rows tells the operator nothing, so this
    fires only where the reference contradicts itself -- never merely because a reference is
    unusual, missing or unrecognised. In the supplied rounds it catches two of eleven
    deliveries, and the other nine carry no flag, so a flag still means something.
    """

    reference: str
    reason: str


@dataclass(frozen=True)
class Proposal:
    """A proposed DN with everything behind it, for a person to approve or overwrite."""

    delivery_id: str | None
    supplier_ref: str | None
    dn: str | None
    provenance: DnProvenance | None
    reasoning: str
    tests: list[Test] = field(default_factory=list)
    counter_evidence: CounterEvidence | None = None
    foreign_producer: str | None = None
    """Set when the produce belongs to another producer, which is a question rather than a fact."""

    @property
    def needs_approval(self) -> bool:
        """Always. Kept as a property so the rule is visible at every call site (D8)."""
        return True


def producer_half(supplier_ref: str | None) -> str | None:
    if not supplier_ref or "*" not in supplier_ref:
        return None
    return supplier_ref.split("*", 1)[0].strip()


def reference_half(supplier_ref: str | None) -> str | None:
    if not supplier_ref or "*" not in supplier_ref:
        return None
    return supplier_ref.split("*", 1)[1].strip()


def counter_evidence(
    supplier_ref: str | None, producer_codes: Iterable[str]
) -> CounterEvidence | None:
    """Whether this reference is *provably* not a delivery note.

    Absence is not counter-evidence: a delivery with no supplier reference at all has nothing
    to contradict, and saying "provably not a DN" about a blank would be a claim the documents
    do not support. It gets a minted proposal like any other unknown.
    """
    if not supplier_ref:
        return None
    producer = producer_half(supplier_ref)
    reference = reference_half(supplier_ref)
    if producer is None or reference is None:
        return None

    if reference == producer:
        return CounterEvidence(
            reference=supplier_ref,
            reason=(
                f"The reference half is {reference}, which is the producer code itself. A "
                "reference pointing at its own producer identifies nothing, so it is not a "
                "delivery note."
            ),
        )
    if set(reference) <= {"0"}:
        return CounterEvidence(
            reference=supplier_ref,
            reason=(
                f"The reference half is {reference}. A run of zeros is a placeholder the export "
                "prints where it has nothing, not a number anyone issued."
            ),
        )
    known = {str(code) for code in producer_codes if code}
    if reference in known and reference != producer:
        return CounterEvidence(
            reference=supplier_ref,
            reason=(
                f"The reference half is {reference}, which appears elsewhere in this round as a "
                "producer code. It is in the same five-digit shape as a delivery note and is not "
                "one."
            ),
        )
    return None


def reference_tests(supplier_ref: str | None, producer_codes: Iterable[str]) -> list[Test]:
    """The three tests of D8, each answered separately so the operator sees which one failed."""
    reference = reference_half(supplier_ref)
    producer = producer_half(supplier_ref)
    known = {str(code) for code in producer_codes if code}

    if reference is None:
        return [
            Test(
                "has a reference half",
                False,
                "No supplier reference was given, so there is nothing to test."
                if not supplier_ref
                else f"{supplier_ref} has no asterisk, so it has no reference half.",
            )
        ]

    return [
        Test(
            "in the 14xxx series",
            bool(DN_SERIES.match(reference)),
            f"{reference} is in Zaco's delivery note series."
            if DN_SERIES.match(reference)
            else f"{reference} is not five digits beginning 14, so it is not a delivery note.",
        ),
        Test(
            "not a known producer code",
            reference not in known,
            f"{reference} is not used as a producer code anywhere in this round."
            if reference not in known
            else f"{reference} is a producer code elsewhere in this round.",
        ),
        Test(
            "not its own producer half",
            reference != producer,
            f"{reference} differs from the producer half {producer}."
            if reference != producer
            else f"{reference} is the producer half repeated, which identifies nothing.",
        ),
    ]


def next_free(taken: Iterable[str]) -> str | None:
    """The next number above everything known in the series, or `None` if that cannot be said.

    Above the top rather than into the gaps. Whether the `14xxx` series is contiguous is an
    open question (DECISIONS.md), and a gap is at least as likely to be a delivery note issued
    on paper and never entered as it is to be free. Reusing one would put two loads under one
    number in a book the business settles money against.

    Returns `None` when nothing establishes where the series sits -- with no workbook and no
    approved DN there is no series to be next in, and inventing `14000` would be a guess
    dressed as a proposal. The queue then asks for the number instead.
    """
    numbers = [int(value) for value in (str(t).strip() for t in taken) if DN_SERIES.match(value)]
    if not numbers:
        return None
    candidate = max(numbers) + 1
    if candidate > SERIES_CEILING:
        return None
    return str(candidate)


def propose(
    delivery_id: str | None,
    supplier_ref: str | None,
    *,
    producer_codes: Iterable[str],
    taken: Iterable[str],
    workbook_links: Mapping[str, str] | None = None,
    account_sales: Iterable[str] = (),
    zaco_producer_code: str | None = None,
) -> Proposal:
    """Propose one delivery's DN, with the reasoning that produced it.

    `workbook_links` maps an account sale number to the DN the operator's own book already
    records against it; `taken` is every DN already spoken for, so a mint cannot collide with
    a proposal made moments earlier in the same round.
    """
    codes = {str(c) for c in producer_codes if c}
    counter = counter_evidence(supplier_ref, codes)
    producer = producer_half(supplier_ref)
    is_foreign = bool(producer and zaco_producer_code and producer != zaco_producer_code)
    foreign = producer if is_foreign else None

    links = workbook_links or {}
    for number in account_sales:
        linked = links.get(number)
        if linked:
            return Proposal(
                delivery_id=delivery_id,
                supplier_ref=supplier_ref,
                dn=linked,
                provenance=DnProvenance.WORKBOOK,
                reasoning=(
                    f"The workbook already records delivery note {linked} against account sale "
                    f"{number}. That is the operator's own record, so it is reused rather than "
                    "proposed afresh."
                ),
                counter_evidence=counter,
                foreign_producer=foreign,
            )

    tests = reference_tests(supplier_ref, codes)
    reference = reference_half(supplier_ref)
    if reference and all(t.passed for t in tests):
        return Proposal(
            delivery_id=delivery_id,
            supplier_ref=supplier_ref,
            dn=reference,
            provenance=DnProvenance.REFERENCE,
            reasoning=(
                f"The supplier reference {supplier_ref} splits into producer {producer} and "
                f"reference {reference}, and {reference} passes all three tests. It is very "
                "often the delivery note, and it is still only a proposal."
            ),
            tests=tests,
            counter_evidence=counter,
            foreign_producer=foreign,
        )

    failed = [t for t in tests if not t.passed]
    why = " ".join(t.detail for t in failed)
    minted = next_free(taken)
    if minted is None:
        return Proposal(
            delivery_id=delivery_id,
            supplier_ref=supplier_ref,
            dn=None,
            provenance=None,
            reasoning=(
                f"{why} Nothing establishes where the 14xxx series currently sits, so a minted "
                "number would be a guess. Please enter the delivery note number."
            ),
            tests=tests,
            counter_evidence=counter,
            foreign_producer=foreign,
        )
    return Proposal(
        delivery_id=delivery_id,
        supplier_ref=supplier_ref,
        dn=minted,
        provenance=DnProvenance.MINTED,
        reasoning=(
            f"{why} There is nothing to derive a number from, so {minted} is the next free "
            "number above everything known in the series."
        ),
        tests=tests,
        counter_evidence=counter,
        foreign_producer=foreign,
    )
