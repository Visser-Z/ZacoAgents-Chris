"""The questions a round cannot be finished without answering (section 7).

Four kinds, and they are asked in this order for a reason:

1. **Product links.** Whether two names in the two vocabularies are the same fruit. Answered
   first because accepting one can carry a short code across and remove a question below it.
2. **Product codes.** The operator's own code for column G. Not derivable from any report.
3. **Delivery notes.** Column A, proposed with reasoning, approved by hand (D8).
4. **Disagreements.** Two documents describing one record differently, held out until someone
   chooses and says why (D12).

Every item carries the evidence it was raised on, so the question can be answered from the card
rather than by going back to the files. Nothing here decides anything: an item is a question and
a proposal, and the answer arrives from the API with a person's name on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from zaco.domain.model import ZERO, Delivery, StagedRound
from zaco.domain.products import ProductRegistry
from zaco.resolve.dn import Proposal, Test


class ItemKind(StrEnum):
    PRODUCT_LINK = "product_link"
    PRODUCT_CODE = "product_code"
    DELIVERY_NOTE = "delivery_note"
    DISAGREEMENT = "disagreement"


#: The order the queue is worked in. Answering a link can resolve a code, so links come first.
ORDER: tuple[ItemKind, ...] = (
    ItemKind.PRODUCT_LINK,
    ItemKind.PRODUCT_CODE,
    ItemKind.DELIVERY_NOTE,
    ItemKind.DISAGREEMENT,
)


@dataclass
class Item:
    """One open question, with everything needed to answer it."""

    kind: ItemKind
    key: str
    title: str
    question: str
    reasoning: str
    evidence: dict[str, str] = field(default_factory=dict)
    proposal: str | None = None
    provenance: str | None = None
    tests: list[Test] = field(default_factory=list)
    counter_evidence: str | None = None
    choices: list[str] = field(default_factory=list)
    """Existing answers worth offering -- the short codes already in the operator's book."""

    companions: list[str] = field(default_factory=list)
    """Other deliveries that could plausibly share this one's answer (the one-truck case)."""

    requires_reason: bool = False
    """Set where an answer is a judgement rather than a fact, and must be justified in writing."""


def _money(value: Decimal | None) -> str:
    return "-" if value is None else f"R{value:,.2f}"


def _number(value: Decimal | None) -> str:
    return "-" if value is None else f"{value:g}"


def product_link_items(registry: ProductRegistry, in_round: set[str] | None = None) -> list[Item]:
    """Resemblances across the two vocabularies, never applied on their own (section 6).

    Offered when **either** side appears in this round, not both. The plums sell in one round
    and their statement arrives in the next, so requiring both would mean the question is never
    askable at all -- and the statement name would sit for ever wanting a code of its own.
    """
    items: list[Item] = []
    for suggestion in registry.suggestions():
        left = registry.identity_for(suggestion.left)
        right = registry.identity_for(suggestion.right)
        if left is None or right is None:
            continue
        if in_round is not None and not ({left.key, right.key} & in_round):
            continue
        coded = right if right.short_code else left
        gain = (
            f"Accepting this puts the code {coded.short_code!r} on the other name too."
            if coded.short_code
            else "Neither name has a short code yet, so accepting this leaves one question "
            "rather than two."
        )
        items.append(
            Item(
                kind=ItemKind.PRODUCT_LINK,
                key=f"{suggestion.left}||{suggestion.right}",
                title=f"{left.display_name} — {right.display_name}",
                question="Are these the same product?",
                reasoning=f"{suggestion.reason} {gain}",
                evidence={
                    "Sales side": next(
                        (n.raw for n in left.names.values() if n.vocabulary == "sales"),
                        left.display_name,
                    ),
                    "Statement side": next(
                        (n.raw for n in right.names.values() if n.vocabulary == "statement"),
                        right.display_name,
                    ),
                    "Shared words": ", ".join(sorted(suggestion.shared_words)),
                    "Short code held": coded.short_code or "none on either name",
                },
                requires_reason=False,
            )
        )
    return items


def product_code_items(
    registry: ProductRegistry,
    staged: StagedRound,
    choices: list[str],
    in_round: set[str] | None = None,
) -> list[Item]:
    """Every product in this round with no operator code. A row cannot be written for one.

    Restricted to this round's products. The registry knows every name ever seen, and asking an
    operator to code a product that appears nowhere in front of them -- while refusing to let
    them finish until they do -- would be a queue nobody could clear.
    """
    items: list[Item] = []
    for identity in registry.unresolved:
        if in_round is not None and identity.key not in in_round:
            continue
        rows = [r for r in staged.rows if r.product.key == identity.key]
        consignments = [c for c in staged.consignments if c.product.key == identity.key]
        sold = sum((r.cartons.net for r in rows), ZERO)
        value = sum((r.value for r in rows), ZERO)
        agents = sorted({c.agent for c in consignments if c.agent})
        sales = sorted({r.account_sale for r in rows})

        if rows:
            impact = (
                f"{len(rows)} row(s) in this round wait on this code, covering {_number(sold)} "
                f"cartons and {_money(value)}."
            )
        else:
            impact = (
                "No row in this round needs this code. The name appears only on the statement "
                "side, so it is asked about but is not holding the round up."
            )

        items.append(
            Item(
                kind=ItemKind.PRODUCT_CODE,
                key=identity.key,
                title=identity.display_name,
                question="What is Zaco's short code for this product?",
                reasoning=(
                    "The reports name products in the market's words. Column G holds the "
                    f"operator's own code, which no report carries. {impact}"
                ),
                evidence={
                    "Known as": " / ".join(sorted(n.raw for n in identity.names.values())),
                    "Vocabulary": ", ".join(sorted(v.value for v in identity.vocabularies)),
                    "Cartons (net)": _number(sold),
                    "Gross": _money(value),
                    "Agents": ", ".join(agents) or "-",
                    "Account sales": ", ".join(sales) or "none yet",
                },
                choices=choices,
            )
        )
    return items


def _companions(
    delivery: Delivery, deliveries: list[Delivery], dates: dict[str, date]
) -> list[str]:
    """Deliveries that look like the same truck: same agent, same day.

    A hint for the multi-select, not a claim. `1183200Z`, `1183201Z` and `1183202Z` -- pears,
    peaches and strawberries -- share a delivery date, an agent and a single account sale paying
    R300, which is very likely one load under one delivery note. Whether it is remains an open
    question in DECISIONS.md, so the queue offers to assign one number to all three and does not
    do it unasked.
    """
    mine = dates.get(delivery.delivery_id or "")
    if mine is None or not delivery.agent:
        return []
    return sorted(
        other.delivery_id
        for other in deliveries
        if other.delivery_id
        and other is not delivery
        and other.agent == delivery.agent
        and dates.get(other.delivery_id) == mine
    )


def delivery_note_items(
    staged: StagedRound,
    proposals: dict[str, Proposal],
    approved: set[str],
    zaco_producer_code: str,
) -> list[Item]:
    """One card per delivery that still has no approved DN."""
    deliveries = list(staged.deliveries.values())
    earliest: dict[str, date] = {}
    for delivery in deliveries:
        if not delivery.delivery_id:
            continue
        dates = [
            r.earliest_date
            for r in staged.rows
            if r.delivery_id == delivery.delivery_id and r.earliest_date
        ]
        if dates:
            earliest[delivery.delivery_id] = min(dates)

    items: list[Item] = []
    for delivery in deliveries:
        key = delivery.delivery_id or ""
        if not key or key in approved:
            continue
        proposal = proposals.get(key)
        products = sorted({c.product.display_name for c in delivery.consignments})
        sales = sorted({s for c in delivery.consignments for s in c.account_sales})

        evidence = {
            "Delivery": key,
            "Supplier ref": delivery.supplier_ref or "none given",
            "Producer": delivery.producer_code or "-",
            "Reference half": delivery.reference_half or "-",
            "Market": delivery.market or "not stated",
            "Agent": delivery.agent or "-",
            "Delivered": str(earliest.get(key, "-")),
            "Cartons sent": _number(delivery.qty_sent),
            "Products": ", ".join(products) or "-",
            "Account sales": ", ".join(sales) or "none yet",
        }
        foreign = proposal.foreign_producer if proposal else None
        if foreign and foreign != zaco_producer_code:
            evidence["Produce belongs to"] = (
                f"producer {foreign}, not Zaco ({zaco_producer_code}). Whether Zaco issues its "
                "own delivery note for another producer's load is not something the documents "
                "say. 'No DN — carried for producer " + foreign + "' is a valid answer here."
            )

        items.append(
            Item(
                kind=ItemKind.DELIVERY_NOTE,
                key=key,
                title=f"Delivery {key}",
                question="Which delivery note number covers this delivery?",
                reasoning=proposal.reasoning if proposal else "No proposal could be made.",
                evidence=evidence,
                proposal=proposal.dn if proposal else None,
                provenance=proposal.provenance.value if proposal and proposal.provenance else None,
                tests=list(proposal.tests) if proposal else [],
                counter_evidence=(
                    proposal.counter_evidence.reason
                    if proposal and proposal.counter_evidence
                    else None
                ),
                companions=_companions(delivery, deliveries, earliest),
            )
        )
    return items


def sort_queue(items: list[Item]) -> list[Item]:
    return sorted(items, key=lambda i: (ORDER.index(i.kind), i.title))
