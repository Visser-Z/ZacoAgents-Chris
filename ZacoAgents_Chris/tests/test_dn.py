"""The delivery note rules (D8-D11), against the references the real data actually contains.

These are the judgement calls the whole of column A rests on, so they are unit tests: no
database, no HTTP, one rule per case, and every assertion is a reference from `data/`.
"""

from __future__ import annotations

import pytest

from zaco.resolve.dn import (
    DnProvenance,
    counter_evidence,
    next_free,
    propose,
    reference_tests,
)

#: Every producer code the supplied rounds contain. `14013` is the one that matters: it is a
#: producer *and* looks exactly like a delivery note.
PRODUCERS = ("20026", "14013", "39001")

#: The workbook's existing delivery notes, which is the only thing establishing the series.
BOOK = ("14690", "14691", "14692")


# --- counter-evidence: only on positive proof (D10) ---------------------------------------------


def test_a_reference_pointing_at_its_own_producer_is_not_a_delivery_note() -> None:
    found = counter_evidence("20026*20026", PRODUCERS)
    assert found is not None
    assert "producer code itself" in found.reason


def test_a_reference_of_zeros_is_not_a_delivery_note() -> None:
    found = counter_evidence("20026*00000", PRODUCERS)
    assert found is not None
    assert "run of zeros" in found.reason


def test_a_reference_that_is_a_producer_code_elsewhere_is_not_a_delivery_note() -> None:
    """`20026*14013`: five digits beginning 14, and still not a DN."""
    found = counter_evidence("20026*14013", PRODUCERS)
    assert found is not None
    assert "producer code" in found.reason


@pytest.mark.parametrize(
    "reference",
    ["20026*14720", "20026*14880", "20026*14885", "20026*14886", "20026*14887", "14013*14710"],
)
def test_an_ordinary_reference_earns_no_flag(reference: str) -> None:
    """A flag on most rows would mean nothing. Nine of eleven deliveries carry none."""
    assert counter_evidence(reference, PRODUCERS) is None


def test_a_missing_reference_is_absence_not_counter_evidence() -> None:
    """Delivery 1181705Z has a blank Supplier Ref. Nothing is contradicted by a blank."""
    assert counter_evidence(None, PRODUCERS) is None
    assert counter_evidence("", PRODUCERS) is None


# --- the three tests -------------------------------------------------------------------------


def test_a_usable_reference_passes_all_three() -> None:
    assert all(t.passed for t in reference_tests("20026*14720", PRODUCERS))


def test_a_reference_outside_the_series_fails_the_first_test() -> None:
    results = {t.name: t.passed for t in reference_tests("20026*203003", PRODUCERS)}
    assert results["in the 14xxx series"] is False


def test_a_reference_that_is_a_producer_code_fails_the_second() -> None:
    results = {t.name: t.passed for t in reference_tests("20026*14013", PRODUCERS)}
    assert results["in the 14xxx series"] is True
    assert results["not a known producer code"] is False


def test_a_reference_repeating_its_producer_fails_the_third() -> None:
    results = {t.name: t.passed for t in reference_tests("20026*20026", PRODUCERS)}
    assert results["not its own producer half"] is False


def test_no_reference_at_all_reports_that_rather_than_three_failures() -> None:
    results = reference_tests(None, PRODUCERS)
    assert len(results) == 1
    assert "nothing to test" in results[0].detail


# --- minting ------------------------------------------------------------------------------------


def test_minting_goes_above_the_top_of_the_series_not_into_its_gaps() -> None:
    """A gap is at least as likely to be a note issued on paper as it is to be free."""
    assert next_free(["14690", "14691", "14692"]) == "14693"
    assert next_free(["14690", "14880"]) == "14881"


def test_minting_ignores_numbers_outside_the_series() -> None:
    assert next_free(["203003", "14690", "1183200Z"]) == "14691"


def test_minting_refuses_when_nothing_establishes_the_series() -> None:
    """With no workbook and no approved DN there is no series to be next in."""
    assert next_free([]) is None
    assert next_free(["203003"]) is None


def test_minting_refuses_rather_than_leaving_the_series() -> None:
    assert next_free(["14999"]) is None


# --- proposals ------------------------------------------------------------------------------------


def test_the_reference_half_is_proposed_where_it_passes() -> None:
    proposal = propose(
        "1180699Z", "20026*14720", producer_codes=PRODUCERS, taken=BOOK, zaco_producer_code="20026"
    )
    assert proposal.dn == "14720"
    assert proposal.provenance is DnProvenance.REFERENCE
    assert proposal.needs_approval


def test_a_number_is_minted_where_the_reference_cannot_be_used() -> None:
    proposal = propose(
        "1183001Z", "20026*14013", producer_codes=PRODUCERS, taken=BOOK, zaco_producer_code="20026"
    )
    assert proposal.dn == "14693"
    assert proposal.provenance is DnProvenance.MINTED
    assert proposal.counter_evidence is not None


def test_a_delivery_with_no_reference_is_minted_and_carries_no_flag() -> None:
    proposal = propose(
        "1181705Z", None, producer_codes=PRODUCERS, taken=BOOK, zaco_producer_code="20026"
    )
    assert proposal.dn == "14693"
    assert proposal.provenance is DnProvenance.MINTED
    assert proposal.counter_evidence is None


def test_the_workbook_wins_over_the_reference() -> None:
    """The operator's own book is evidence; a reference half is only usually right."""
    proposal = propose(
        "1180699Z",
        "20026*14720",
        producer_codes=PRODUCERS,
        taken=BOOK,
        workbook_links={"381900": "14690"},
        account_sales=["381900"],
        zaco_producer_code="20026",
    )
    assert proposal.dn == "14690"
    assert proposal.provenance is DnProvenance.WORKBOOK
    assert "381900" in proposal.reasoning


def test_the_workbook_join_recovers_nothing_from_the_supplied_rounds() -> None:
    """The book holds 381900/381950; the data holds 382399-382999. Honest, and still correct."""
    proposal = propose(
        "1180699Z",
        "20026*14720",
        producer_codes=PRODUCERS,
        taken=BOOK,
        workbook_links={"381900": "14690", "381950": "14692"},
        account_sales=["382405", "382860"],
        zaco_producer_code="20026",
    )
    assert proposal.provenance is DnProvenance.REFERENCE


def test_another_producers_load_is_flagged_as_a_question_not_answered_as_a_fact() -> None:
    """`14013*14710`: whether Zaco issues its own DN for someone else's produce is unrecorded."""
    proposal = propose(
        "1182465Z", "14013*14710", producer_codes=PRODUCERS, taken=BOOK, zaco_producer_code="20026"
    )
    assert proposal.foreign_producer == "14013"
    assert proposal.dn == "14710"


def test_a_proposal_always_needs_approval_even_when_it_is_not_a_guess() -> None:
    proposal = propose(
        "1180699Z",
        "20026*14720",
        producer_codes=PRODUCERS,
        taken=BOOK,
        workbook_links={"381900": "14690"},
        account_sales=["381900"],
    )
    assert proposal.needs_approval


def test_minting_cannot_collide_with_a_number_proposed_moments_earlier() -> None:
    taken = set(BOOK)
    first = propose("A", None, producer_codes=PRODUCERS, taken=taken)
    assert first.dn is not None
    taken.add(first.dn)
    second = propose("B", None, producer_codes=PRODUCERS, taken=taken)
    assert second.dn != first.dn
