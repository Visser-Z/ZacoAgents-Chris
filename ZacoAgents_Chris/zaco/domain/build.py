"""Turning parsed documents into deliveries, consignments and rows.

The readers say what each page contained. This decides what those pages *mean* together, which
is where the grain gets applied and where the two product vocabularies have to be reconciled.

Nothing here invents a fact. Where two documents disagree, both figures are kept and the
disagreement is reported; where a document could not say something, the result says so rather
than substituting a zero.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from zaco.domain.model import (
    ZERO,
    AccountSale,
    Consignment,
    Delivery,
    DocketFact,
    Evidence,
    Row,
    StagedRound,
)
from zaco.domain.products import ProductIdentity, ProductRegistry, Vocabulary
from zaco.ingest.problems import ProblemLog
from zaco.ingest.records import (
    AccountSalesStatement,
    ConsignmentBlock,
    DocumentKind,
    NettAdjustment,
    ParseResult,
    PaymentRecord,
)

LOOKUP_PATH = Path(__file__).resolve().parent.parent.parent / "lookup" / "product-codes.json"

#: Which readers produce docket-level detail, and therefore *can* report a return.
_DOCKET_KINDS = {DocumentKind.DAILY_SALES_DETAIL, DocumentKind.CONSIGNMENT_REPORT}


def load_short_codes(path: Path | None = None) -> dict[str, str]:
    """`lookup/product-codes.json`: what is known so far, and deliberately far from complete."""
    target = path or LOOKUP_PATH
    if not target.exists():
        return {}
    data = json.loads(target.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def build_round(
    documents: list[tuple[str, ParseResult]],
    registry: ProductRegistry | None = None,
) -> tuple[StagedRound, ProductRegistry]:
    """Assemble one round. `documents` is (filename, parse result), in upload order."""
    registry = registry or ProductRegistry(load_short_codes())
    log = ProblemLog()
    staged = StagedRound(sources=[name for name, _ in documents])
    statements: list[AccountSalesStatement] = []

    for name, result in documents:
        staged.problems.extend(result.problems)
        for block in result.consignments:
            _add_consignment(staged, registry, block, result.kind, name, log)
        for statement in result.statements:
            _add_statement(staged, registry, statement)
            statements.append(statement)
        for payment in result.payments:
            _add_payment(staged, registry, payment, name, log)
        for adjustment in result.adjustments:
            _add_adjustment(staged, adjustment)

    staged.rows = _build_rows(staged)
    _link_vocabularies(staged, registry, statements, log)
    _check_grain(staged, log)
    staged.problems.extend(log.items)
    return staged, registry


# --- sales side ---------------------------------------------------------------------------------


def _add_consignment(
    staged: StagedRound,
    registry: ProductRegistry,
    block: ConsignmentBlock,
    kind: DocumentKind,
    source: str,
    log: ProblemLog,
) -> None:
    product = registry.observe(block.product_name or "(unnamed product)", Vocabulary.SALES)
    delivery = _delivery_for(staged, block)
    consignment = _consignment_for(delivery, block, product)

    # A later document may name the market an earlier one printed as `Destination`. Filling a
    # gap from another document is recovery; overwriting a stated value would be invention.
    consignment.market = consignment.market or block.market
    consignment.agent = consignment.agent or block.agent
    delivery.market = delivery.market or block.market
    delivery.agent = delivery.agent or block.agent
    consignment.evidence.add(Evidence.SALES if kind in _DOCKET_KINDS else Evidence.PAYMENT)
    _adopt_quantities(consignment, block, log)

    known = {d.identity: d for d in consignment.dockets}
    for docket in block.dockets:
        fact = DocketFact(
            docket_number=docket.docket_number,
            date_sold=docket.date_sold,
            quantity=docket.quantity,
            price=docket.price,
            value=docket.value,
            account_sale=docket.payment_reference,
            date_delivered=docket.date_delivered,
            date_paid=docket.date_paid,
            source_kind=kind,
            source_name=source,
        )
        seen = known.get(fact.identity)
        if seen is None:
            known[fact.identity] = fact
            consignment.dockets.append(fact)
            continue

        label = f"Docket {fact.docket_number} on consignment {consignment.consignment_id or '?'}"
        if fact.richness > seen.richness:
            # The same sale, told better. A Daily Sales Detail names the account sale a
            # Consignment Report cannot, so the poorer telling is completed rather than kept
            # beside it -- keeping both would count the sale twice.
            seen.account_sale = seen.account_sale or fact.account_sale
            seen.date_paid = seen.date_paid or fact.date_paid
            seen.date_delivered = seen.date_delivered or fact.date_delivered
            log.note(
                f"{label} was already read from a document that could not name its account "
                f"sale. {source} names it as {fact.account_sale}, so the existing sale was "
                "completed rather than recorded again."
            )
        else:
            log.note(
                f"{label} was already read from another document with the same figures. "
                f"{source} did not add it again."
            )


def _adopt_quantities(consignment: Consignment, block: ConsignmentBlock, log: ProblemLog) -> None:
    """Take Qty Sent once, and report rather than resolve a disagreement between documents."""
    if block.qty_sent is not None:
        if consignment.qty_sent is None:
            consignment.qty_sent = block.qty_sent
        elif consignment.qty_sent != block.qty_sent:
            log.warn(
                f"Consignment {consignment.consignment_id or '?'}: one document says "
                f"{consignment.qty_sent} cartons were sent and another says {block.qty_sent}. "
                "Both are kept; neither is chosen."
            )
    if block.qty_available is not None and consignment.qty_available is None:
        consignment.qty_available = block.qty_available


def _delivery_for(staged: StagedRound, block: ConsignmentBlock) -> Delivery:
    key = block.delivery_id or f"(unidentified {len(staged.deliveries)})"
    delivery = staged.deliveries.get(key)
    if delivery is None:
        delivery = Delivery(
            delivery_id=block.delivery_id,
            supplier_ref=block.supplier_ref,
            market=block.market,
            agent=block.agent,
        )
        staged.deliveries[key] = delivery
    elif delivery.supplier_ref is None:
        delivery.supplier_ref = block.supplier_ref
    return delivery


def _consignment_for(
    delivery: Delivery, block: ConsignmentBlock, product: ProductIdentity
) -> Consignment:
    for existing in delivery.consignments:
        if block.consignment_id and existing.consignment_id == block.consignment_id:
            return existing
        if not block.consignment_id and existing.product.key == product.key:
            return existing
    consignment = Consignment(
        consignment_id=block.consignment_id,
        delivery_id=delivery.delivery_id,
        product=product,
        supplier_ref=block.supplier_ref or delivery.supplier_ref,
        market=block.market,
        agent=block.agent,
    )
    delivery.consignments.append(consignment)
    return consignment


# --- payment side ---------------------------------------------------------------------------------


def _add_payment(
    staged: StagedRound,
    registry: ProductRegistry,
    payment: PaymentRecord,
    source: str,
    log: ProblemLog,
) -> None:
    number = payment.account_sale_number
    if not number:
        return
    for line in payment.commodities:
        if line.commodity:
            registry.observe(line.commodity, Vocabulary.SALES)

    incoming = AccountSale(
        number=number,
        market=payment.market,
        agent=payment.agent,
        date_paid=payment.date_paid,
        nett=payment.nett_payment,
        gross=payment.gross_payment,
        total_deductions=payment.total_deductions,
        deduction_vat=payment.deduction_vat,
        has_commodity_breakdown=payment.has_commodity_breakdown,
        sales_value=(
            sum((c.sales_total for c in payment.commodities if c.sales_total is not None), ZERO)
            if payment.commodities
            else None
        ),
    )

    existing = staged.account_sales.get(number)
    if existing is None:
        staged.account_sales[number] = incoming
        return
    _reconcile_duplicate_payment(existing, incoming, source, log)


def _reconcile_duplicate_payment(
    existing: AccountSale, incoming: AccountSale, source: str, log: ProblemLog
) -> None:
    """The narrowed re-export overlapping the full one.

    Identical figures are the same payment seen twice; different figures are a conflict, and a
    person decides which document wins (D12). Neither is silently overwritten.
    """
    differing = [
        name
        for name in ("nett", "gross", "total_deductions", "date_paid")
        if getattr(existing, name) != getattr(incoming, name)
    ]
    if differing:
        log.warn(
            f"Account sale {existing.display_number} appears twice with different "
            f"{', '.join(differing)}. {source} was not applied over the earlier document; this "
            "needs a decision and a reason."
        )
    else:
        log.note(
            f"Account sale {existing.display_number} appears again in {source} with identical "
            "figures. It was not recorded twice."
        )


def _add_adjustment(staged: StagedRound, adjustment: NettAdjustment) -> None:
    number = adjustment.account_sale_number
    if not number or number in staged.account_sales:
        return
    staged.account_sales[number] = AccountSale(
        number=number,
        market=adjustment.market,
        agent=adjustment.agent,
        date_paid=adjustment.date_paid,
        nett=adjustment.nett_payment,
        gross=adjustment.gross_payment,
        total_deductions=adjustment.total_deductions,
        deduction_vat=adjustment.deduction_vat,
        # This kind carries no product and no quantity at all (section 4).
        has_commodity_breakdown=False,
    )


def _add_statement(
    staged: StagedRound, registry: ProductRegistry, statement: AccountSalesStatement
) -> None:
    for product in statement.products:
        if product.product_name:
            registry.observe(product.product_name, Vocabulary.STATEMENT)

    number = statement.account_sale_number
    if not number:
        return
    record = staged.account_sales.get(number)
    if record is None:
        record = AccountSale(number=number)
        staged.account_sales[number] = record
    if record.date_paid is None:
        record.date_paid = statement.statement_date
    if record.nett is None:
        record.nett = statement.nett_amount
    if record.gross is None:
        record.gross = statement.gross_amount


# --- reconciling the two product vocabularies -------------------------------------------------


def _link_vocabularies(
    staged: StagedRound,
    registry: ProductRegistry,
    statements: list[AccountSalesStatement],
    log: ProblemLog,
) -> None:
    """Merge a statement product with a sales product only where an account sale proves it.

    The proof: the same account sale names both, and the value agrees to the cent. Anything less
    is a resemblance, and `registry.suggestions()` offers those to the operator instead.

    In the supplied rounds this proves exactly one link -- account sale 382405 names both
    `CHERRIES OTHER CLASS 1 LARGE (HALF TRAY 2.5kg)` and `CHOT 1L HT25 CHERRY OTHER` for R400 --
    and that is the honest answer. The others are offered as suggestions, not merged.
    """
    for statement in statements:
        number = statement.account_sale_number
        if not number:
            continue
        rows = [r for r in staged.rows if r.account_sale.endswith(number)]
        for product in statement.products:
            if not product.product_name or product.stated_total_value is None:
                continue
            matches = [r for r in rows if r.value == product.stated_total_value]
            if len(matches) != 1:
                # Two rows of the same value under one account sale would make the link
                # ambiguous, and a wrong merge puts one product's takings under another's name.
                continue
            sales_name = matches[0].product.display_name
            if sales_name == product.product_name:
                continue
            registry.link(
                sales_name,
                product.product_name,
                reason=f"account sale {number} names both for R{product.stated_total_value}",
            )
            log.note(
                f"{sales_name!r} and {product.product_name!r} are the same product: account "
                f"sale {number} names both for R{product.stated_total_value}."
            )


# --- the grain --------------------------------------------------------------------------------


def _build_rows(staged: StagedRound) -> list[Row]:
    """One row per delivery x product x account sale.

    A consignment spanning two account sales produces two rows; an account sale settling three
    consignments contributes to three. Dockets naming no account sale produce no row at all,
    because a row *is* that combination and one third of it is missing.
    """
    rows: dict[tuple[str, str, str], Row] = {}
    for consignment in staged.consignments:
        for docket in consignment.dockets:
            if not docket.account_sale:
                continue
            key = (consignment.delivery_id or "", consignment.product.key, docket.account_sale)
            row = rows.get(key)
            if row is None:
                row = Row(
                    delivery_id=consignment.delivery_id,
                    consignment_id=consignment.consignment_id,
                    product=consignment.product,
                    account_sale=docket.account_sale,
                    market=consignment.market,
                    agent=consignment.agent,
                    evidence=set(consignment.evidence),
                )
                rows[key] = row
            row.dockets.append(docket)
    return sorted(
        rows.values(),
        key=lambda r: (str(r.earliest_date or ""), r.delivery_id or "", r.account_sale),
    )


def _check_grain(staged: StagedRound, log: ProblemLog) -> None:
    for consignment in staged.consignments:
        label = consignment.consignment_id or consignment.delivery_id or "?"

        if not consignment.is_identifiable:
            log.warn(
                f"A consignment on delivery {consignment.delivery_id or '?'} has no consignment "
                "ID. It cannot be tracked across rounds, so its rows are kept separate rather "
                "than pooled with any other."
            )

        sold = consignment.cartons.net
        if consignment.qty_sent is not None and sold > consignment.qty_sent:
            # Section 6: say so, do not correct it. This happens in the real book too.
            log.warn(
                f"Consignment {label} sold {sold} cartons but only {consignment.qty_sent} were "
                "sent. Reported as it stands; nothing has been adjusted."
            )

        if len(consignment.account_sales) > 1:
            log.note(
                f"Consignment {label} spans account sales "
                f"{', '.join(consignment.account_sales)}, so it becomes "
                f"{len(consignment.account_sales)} rows. Its {consignment.qty_sent} cartons sent "
                "are counted once, not once per row."
            )

    for number, record in staged.account_sales.items():
        if not record.has_commodity_breakdown:
            nett = record.nett if record.nett is not None else "?"
            log.warn(
                f"Account sale {record.display_number} has a nett of R{nett} and no product "
                "breakdown, so it can never be reconciled against the sales side."
            )
            continue
        if not [r for r in staged.rows if r.account_sale == number]:
            log.warn(
                f"Account sale {record.display_number} was paid but no sales document accounts "
                "for it. Its money is real; it is reported rather than dropped."
            )


def sum_once_per_consignment(consignments: list[Consignment]) -> Decimal:
    """Delivery-level quantities, counted correctly.

    Exists so the rule has a name that can be searched for, and so a caller reaching for a sum
    over rows finds this instead.
    """
    seen: set[str] = set()
    total = ZERO
    for consignment in consignments:
        key = consignment.consignment_id or f"{consignment.delivery_id}:{consignment.product.key}"
        if key in seen or consignment.qty_sent is None:
            continue
        seen.add(key)
        total += consignment.qty_sent
    return total
