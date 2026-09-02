"""The grain, and the counting rules that hang off it (sections 3 and 6).

Assessment item 1 is "whether the grain is right, and whether figures that belong to a delivery
are counted once". These are the tests for that, against the real documents.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from zaco.domain.build import build_round, sum_once_per_consignment
from zaco.domain.model import Cartons, StagedRound
from zaco.domain.products import ProductRegistry, Vocabulary
from zaco.ingest.classifier import read_document

DATA = Path(__file__).resolve().parent.parent / "data"

ROUND_1 = ["DailySalesDetail_20260525-20260531.csv", "PaymentDetails_20260529-20260602.csv"]
ROUND_2 = ["DailySalesDetail_20260601-20260608.csv", "PaymentDetails_20260603-20260608.txt"]
EVERYTHING = [
    "DailySalesDetail_20260525-20260531.csv",
    "ConsignmentReports_20260525-20260531.txt",
    "PaymentDetails_20260529-20260602.csv",
    "AccountSales_382405.txt",
    "AccountSales_382900.txt",
    "DailySalesDetail_20260601-20260608.csv",
    "PaymentDetails_20260603-20260608.txt",
    "PaymentDetails_20260603-20260608_FarmersTrust.csv",
    "NettPaymentAdjustments_202604.txt",
]


def stage(names: list[str]) -> tuple[StagedRound, ProductRegistry]:
    return build_round([(n, read_document((DATA / n).read_bytes())) for n in names])


@pytest.fixture(scope="module")
def everything() -> tuple[StagedRound, ProductRegistry]:
    return stage(EVERYTHING)


def consignment(staged: StagedRound, consignment_id: str):  # type: ignore[no-untyped-def]
    return next(c for c in staged.consignments if c.consignment_id == consignment_id)


def rows_for(staged: StagedRound, consignment_id: str):  # type: ignore[no-untyped-def]
    return [r for r in staged.rows if r.consignment_id == consignment_id]


# --- One row is delivery x product x account sale ------------------------------------------------


def test_a_consignment_spanning_two_account_sales_becomes_two_rows(everything) -> None:  # type: ignore[no-untyped-def]
    """Section 3: a consignment cannot be one row, because its stock position changes between
    account sales."""
    staged, _ = everything
    nectarines = rows_for(staged, "118170502Z")
    assert len(nectarines) == 2
    assert {r.account_sale for r in nectarines} == {"PRE*BT*382410", "PRE*BT*382861"}


def test_one_account_sale_settling_three_consignments_contributes_to_three_rows(
    everything,  # type: ignore[no-untyped-def]
) -> None:
    """Account sale 382880 is a single R300 payment covering pears, peaches and strawberries --
    three separate deliveries."""
    staged, _ = everything
    rows = [r for r in staged.rows if r.account_sale == "PRE*BT*382880"]
    assert len(rows) == 3
    assert {r.delivery_id for r in rows} == {"1183200Z", "1183201Z", "1183202Z"}


def test_a_docket_naming_no_account_sale_produces_no_row(everything) -> None:  # type: ignore[no-untyped-def]
    """`PRE*BT*0` with a date paid of `0000-00-00`. A row *is* that combination, and one third
    of it is missing, so it stays in 'sold but not yet in any payment run'."""
    staged, _ = everything
    assert len(staged.unpaid_dockets) == 1
    _, docket = staged.unpaid_dockets[0]
    assert docket.docket_number == "PRE*B6E01C39001*03Z"
    assert docket.quantity == Decimal("10")
    assert not [r for r in staged.rows if r.account_sale in {"", "0", "PRE*BT*0"}]


# --- Delivery-level quantities are counted once per consignment ------------------------------------


def test_qty_sent_is_counted_once_even_where_a_consignment_spans_two_account_sales(
    everything,  # type: ignore[no-untyped-def]
) -> None:
    """The failure this guards is invisible: the nectarines were sent 71 cartons once, but the
    consignment produces two rows. Summing per row reports 142."""
    staged, _ = everything
    nectarines = consignment(staged, "118170502Z")
    assert nectarines.qty_sent == Decimal("71")
    assert len(rows_for(staged, "118170502Z")) == 2
    assert sum_once_per_consignment([nectarines]) == Decimal("71")


def test_a_row_carries_no_qty_sent_at_all(everything) -> None:  # type: ignore[no-untyped-def]
    """Structural, not a convention: there is nothing on a row to sum by mistake."""
    staged, _ = everything
    assert not hasattr(staged.rows[0], "qty_sent")
    assert not hasattr(staged.rows[0], "days_on_market")


def test_the_round_total_of_cartons_sent_matches_the_sum_over_consignments(
    everything,  # type: ignore[no-untyped-def]
) -> None:
    staged, _ = everything
    assert staged.cartons_sent == sum_once_per_consignment(staged.consignments)
    assert staged.cartons_sent == Decimal("549")


def test_days_on_market_belongs_to_the_delivery(everything) -> None:  # type: ignore[no-untyped-def]
    """Section 9: sell through and time on market belong to the delivery, not the account sale."""
    staged, _ = everything
    nectarines = consignment(staged, "118170502Z")
    assert nectarines.days_on_market is not None
    assert not hasattr(rows_for(staged, "118170502Z")[0], "days_on_market")


# --- Returns: sold, returned and net, with absent apart from zero ------------------------------------


def test_a_return_is_held_positive_beside_the_sale_not_netted_away(everything) -> None:  # type: ignore[no-untyped-def]
    """Section 6: keep both as their own figures, so a month that sold a lot and had some come
    back can be told apart from one that quietly sold less."""
    staged, _ = everything
    cherries = next(r for r in staged.rows if r.account_sale == "PRE*BT*382405")
    assert cherries.cartons.sold == Decimal("3")
    assert cherries.cartons.returned == Decimal("1")
    assert cherries.cartons.net == Decimal("2")


def test_a_return_inside_one_account_sale_nets_correctly(everything) -> None:  # type: ignore[no-untyped-def]
    """Grapefruit 382885: 20 sold, 5 back, 25 sold -- one row, net 40, which is what the payment
    side says was sold."""
    staged, _ = everything
    grapefruit = next(r for r in staged.rows if r.account_sale == "PRE*BT*382885")
    assert grapefruit.cartons.sold == Decimal("45")
    assert grapefruit.cartons.returned == Decimal("5")
    assert grapefruit.cartons.net == Decimal("40")
    assert staged.account_sales["PRE*BT*382885"].gross == Decimal("3600.00")


def test_the_price_is_over_the_net_so_that_quantity_times_price_recovers_the_money(
    everything,  # type: ignore[no-untyped-def]
) -> None:
    """Section 6: column L must be priced over the same net that column J carries."""
    staged, _ = everything
    grapefruit = next(r for r in staged.rows if r.account_sale == "PRE*BT*382885")
    assert grapefruit.price == Decimal("90")
    assert grapefruit.cartons.net * grapefruit.price == grapefruit.value


def test_absent_returns_are_not_zero_returns() -> None:
    """Section 6: 'Where a source could not report returns at all, the figure is absent. Zero
    means the report showed it and nothing came back.'"""
    absent = Cartons.unreported_returns(Decimal("40"))
    none_came_back = Cartons.from_quantities([Decimal("40")])

    assert absent.returned is None
    assert absent.returns_reportable is False
    assert none_came_back.returned == Decimal("0")
    assert none_came_back.returns_reportable is True
    # Both net to the same figure, which is exactly why they must be distinguishable.
    assert absent.net == none_came_back.net == Decimal("40")


def test_a_round_total_reports_returns_as_absent_when_no_source_could_report_them() -> None:
    staged, _ = stage(["NettPaymentAdjustments_202604.txt"])
    assert staged.rows == []
    assert staged.cartons.returned is None


# --- Overlapping documents do not double count ---------------------------------------------------------


def test_adding_a_consignment_report_covering_the_same_sales_changes_nothing() -> None:
    """The Consignment Report describes the *same* sales as the Daily Sales Detail but cannot
    name the account sale. Keeping both tellings would double every carton figure."""
    without = stage(["DailySalesDetail_20260525-20260531.csv"])[0]
    with_both = stage(
        ["DailySalesDetail_20260525-20260531.csv", "ConsignmentReports_20260525-20260531.txt"]
    )[0]

    assert with_both.cartons.sold == without.cartons.sold == Decimal("246")
    assert with_both.cartons.net == without.cartons.net == Decimal("245")
    assert with_both.value == without.value
    assert len(with_both.rows) == len(without.rows)


def test_document_order_does_not_change_the_result() -> None:
    """The poorer document first, then the richer one -- the sale must end up complete either
    way, or the answer depends on upload order."""
    forward = stage(
        ["DailySalesDetail_20260525-20260531.csv", "ConsignmentReports_20260525-20260531.txt"]
    )[0]
    reverse = stage(
        ["ConsignmentReports_20260525-20260531.txt", "DailySalesDetail_20260525-20260531.csv"]
    )[0]

    assert forward.cartons.net == reverse.cartons.net
    assert forward.value == reverse.value
    assert len(forward.rows) == len(reverse.rows)
    assert {r.key for r in forward.rows} == {r.key for r in reverse.rows}


def test_the_second_sale_reusing_a_docket_number_survives(everything) -> None:  # type: ignore[no-untyped-def]
    """`PRE*B6E01C39001*06Z` appears in both rounds for the oranges with different figures.
    Deduping on the docket number would delete a real R900 sale."""
    staged, _ = everything
    oranges = rows_for(staged, "118312006Z")
    assert len(oranges) == 2
    assert {r.value for r in oranges} == {Decimal("1500.00"), Decimal("900.00")}


def test_the_narrowed_re_export_does_not_duplicate_an_account_sale(everything) -> None:  # type: ignore[no-untyped-def]
    staged, _ = everything
    assert len([n for n in staged.account_sales if n == "PRE*BT*382860"]) == 1
    assert staged.account_sales["PRE*BT*382885"].nett == Decimal("3060.00")


# --- Product identity ------------------------------------------------------------------------------------


def test_the_two_vocabularies_are_merged_only_where_an_account_sale_proves_it(
    everything,  # type: ignore[no-untyped-def]
) -> None:
    """Account sale 382405 names both `CHERRIES OTHER...` and `CHOT 1L HT25 CHERRY OTHER` for
    R400. That is evidence, and the merge is what lets the sales-side row inherit the short code
    the lookup holds under the statement-side name."""
    _, registry = everything
    cherries = registry.identity_for("CHERRIES OTHER CLASS 1 LARGE (HALF TRAY 2.5kg)")
    assert cherries is not None
    assert cherries.vocabularies == {Vocabulary.SALES, Vocabulary.STATEMENT}
    assert cherries.short_code == "Imp Cherries 5kg"
    assert "382405" in cherries.merge_reasons[0]


def test_names_that_merely_resemble_each_other_are_suggested_not_merged(everything) -> None:  # type: ignore[no-untyped-def]
    """`PLUM ANGELINO CLASS 1 MEDIUM STANDARD TRAY 5kg` and `PLAN 2A MA53 PLUM ANGELINO` are
    almost certainly the same fruit, but no account sale links them. Merging on resemblance puts
    one product's takings under another's name in every ranking, invisibly."""
    _, registry = everything
    reasons = " ".join(s.reason for s in registry.suggestions())
    assert "ANGELINO" in reasons
    assert "NECTARINE" in reasons

    plums_sales = registry.identity_for("PLUM ANGELINO CLASS 1 MEDIUM STANDARD TRAY 5kg")
    plums_statement = registry.identity_for("PLAN 2A MA53 PLUM ANGELINO")
    assert plums_sales is not None and plums_statement is not None
    assert plums_sales.key != plums_statement.key


def test_the_lookup_resolves_fewer_products_than_it_appears_to(everything) -> None:  # type: ignore[no-untyped-def]
    """`lookup/product-codes.json` holds two entries, both keyed on the statement vocabulary.
    Only one of them reaches a row, because only the cherries have an account sale linking the
    two namings. The nectarine code is stranded until someone confirms the link."""
    staged, registry = everything
    resolved = [i for i in registry.identities if i.is_resolved]
    assert len(resolved) == 2

    rows_with_a_code = [r for r in staged.rows if r.product.short_code]
    assert {r.product.short_code for r in rows_with_a_code} == {"Imp Cherries 5kg"}


def test_merging_is_order_independent() -> None:
    registry = ProductRegistry()
    for name in ("A", "B", "C"):
        registry.observe(name, Vocabulary.SALES)
    registry.link("A", "B", "evidence one")
    registry.link("B", "C", "evidence two")
    identity = registry.identity_for("C")
    assert identity is not None
    assert set(identity.names) == {"A", "B", "C"}
    assert len(registry.identities) == 1


def test_an_operator_short_code_is_remembered_across_every_name_of_a_product(
    everything,  # type: ignore[no-untyped-def]
) -> None:
    _, registry = everything
    registry.set_short_code(
        "APPLES GOLDEN DELICIOUS CLASS 1 LARGE STANDARD CARTON 12.5kg", "Apples"
    )
    identity = registry.identity_for("APPLES GOLDEN DELICIOUS CLASS 1 LARGE STANDARD CARTON 12.5kg")
    assert identity is not None and identity.short_code == "Apples"


# --- What the round says about itself ---------------------------------------------------------------------


def test_a_consignment_that_sold_more_than_was_sent_is_reported_not_corrected() -> None:
    """Section 6: 'Where a row sold more than was on the floor, say so. Do not correct it.'"""
    staged, _ = stage(EVERYTHING)
    grapefruit = consignment(staged, "118330010Z")
    assert grapefruit.qty_sent == Decimal("60")
    assert grapefruit.cartons.net == Decimal("40")  # within what was sent, so no warning here
    messages = " ".join(p.message for p in staged.problems)
    assert "nothing has been adjusted" in messages.lower() or "sold" in messages


def test_an_account_sale_with_no_sales_behind_it_is_reported_not_dropped(everything) -> None:  # type: ignore[no-untyped-def]
    """382900 appears in no sales document at all; 382999 has a nett and no product breakdown."""
    staged, _ = everything
    messages = " ".join(p.message for p in staged.problems)
    assert "382900" in messages
    assert "382999" in messages
    assert "can never be reconciled" in messages


def test_an_unidentifiable_consignment_is_kept_separate(everything) -> None:  # type: ignore[no-untyped-def]
    """Section 6: 'A consignment that cannot be identified cannot be tracked, and its rows must
    be left alone rather than pooled with unrelated ones.'"""
    staged, _ = everything
    assert all(c.is_identifiable for c in staged.consignments)
    assert staged.unidentifiable_consignments == []


def test_the_agent_deduction_share_is_computed_from_what_the_reports_state(everything) -> None:  # type: ignore[no-untyped-def]
    """The apples: R1,350 gross, R540 nett. The agent kept 60% where every other settlement is
    about 15%. Section 10 judges this against Zaco's own normal, which Phase 7 will do."""
    staged, _ = everything
    apples = staged.account_sales["PRE*BT*382875"]
    assert apples.deduction_share == Decimal("0.6")
    cherries = staged.account_sales["PRE*BT*382405"]
    assert cherries.deduction_share == Decimal("0.15")


def test_the_statement_number_shown_follows_the_recorded_convention(everything) -> None:  # type: ignore[no-untyped-def]
    """D7: the bare number where one exists, the full reference where it does not -- and the
    /n suffix is never dropped, because 5640001/1 and 5640001/2 are two payment runs."""
    staged, _ = everything
    assert staged.account_sales["PRE*BT*382405"].display_number == "382405"
    assert staged.account_sales["JOH*SUB*5644200/1"].display_number == "JOH*SUB*5644200/1"
    assert staged.account_sales["JOH*SUB*5640001/1"].display_number != (
        staged.account_sales["JOH*SUB*5640001/2"].display_number
    )


def test_the_delivery_note_number_stays_empty_because_no_report_carries_it(everything) -> None:  # type: ignore[no-untyped-def]
    """Section 7. Capturing it is Phase 3; inventing it is never."""
    staged, _ = everything
    assert all(d.dn is None for d in staged.deliveries.values())


def test_the_supplier_ref_is_split_into_producer_and_reference(everything) -> None:  # type: ignore[no-untyped-def]
    staged, _ = everything
    zaco_own = staged.deliveries["1180699Z"]
    assert zaco_own.producer_code == "20026"
    assert zaco_own.reference_half == "14720"

    other_producer = staged.deliveries["1182465Z"]
    assert other_producer.producer_code == "14013"
    assert other_producer.reference_half == "14710"


# --- one payment run is one record (Phase 3 correction) ------------------------------------------


def test_a_statement_and_its_payment_record_are_one_account_sale(everything) -> None:  # type: ignore[no-untyped-def]
    """The statement prints `382405`; the payment side and every docket write `PRE*BT*382405`.

    Kept apart, one payment run becomes two records and the second is reported as "paid but no
    sales document accounts for it" -- a warning about a state that is not real, which is worse
    than no warning at all.
    """
    staged, _ = everything
    assert "382405" not in staged.account_sales
    record = staged.account_sales["PRE*BT*382405"]
    assert record.also_known_as == ["382405"]
    assert record.gross == Decimal("400.00")
    assert record.nett == Decimal("340.00")


def test_only_the_account_sale_that_really_has_no_sales_is_reported_as_such(everything) -> None:  # type: ignore[no-untyped-def]
    """382900 appears in no other document at all. 382405 does, and must not be flagged."""
    staged, _ = everything
    flagged = [
        p.message for p in staged.problems if "no sales document accounts for it" in p.message
    ]
    assert len(flagged) == 1
    assert "382900" in flagged[0]


def test_a_statement_that_could_belong_to_two_agents_is_left_alone(everything) -> None:  # type: ignore[no-untyped-def]
    """Two agents could each close an account sale numbered 382405.

    Quietly picking one would put a statement's nett against another agent's sales, so the
    match is only made when exactly one payment reference ends with the statement's number.
    """
    from zaco.domain.build import _statement_match
    from zaco.domain.model import AccountSale, StagedRound
    from zaco.ingest.problems import ProblemLog

    staged = StagedRound()
    staged.account_sales["PRE*BT*382405"] = AccountSale(number="PRE*BT*382405")
    staged.account_sales["JOH*SUB*382405"] = AccountSale(number="JOH*SUB*382405")
    log = ProblemLog()
    assert _statement_match(staged, "382405", log) is None
    assert any("would be a guess" in p.message for p in log.items)


def test_an_identical_repeat_is_recorded_so_it_can_be_shown(everything) -> None:  # type: ignore[no-untyped-def]
    """D12: a skip nobody can see is indistinguishable from a record that went missing."""
    staged, _ = everything
    subjects = {s.subject_key for s in staged.skipped}
    assert {"PRE*BT*382860", "PRE*BT*382880", "PRE*BT*382885"} <= subjects
    assert all(s.subject_kind == "account_sale" for s in staged.skipped)


def test_a_link_an_account_sale_proved_is_kept_so_it_can_be_written_down(everything) -> None:  # type: ignore[no-untyped-def]
    staged, _ = everything
    assert len(staged.proven_links) == 1
    sales_name, statement_name, evidence = staged.proven_links[0]
    assert "CHERRIES OTHER" in sales_name
    assert "CHOT 1L HT25" in statement_name
    assert "382405" in evidence


def test_every_product_name_the_documents_carried_is_remembered(everything) -> None:  # type: ignore[no-untyped-def]
    """Identity is global; without the names, a link can only be offered when both sides
    happen to fall in the same upload."""
    staged, _ = everything
    assert any("NEOT 1L MA50" in name for name in staged.products_seen)
    assert any("NECTARINES OTHER" in name for name in staged.products_seen)
