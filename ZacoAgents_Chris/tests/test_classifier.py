"""Identifying a document by its content (section 4).

The filename is never consulted, so these tests never pass one in. What they assert is that a
document loaded into the wrong place is *refused with an explanation*, not parsed into nonsense.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from zaco.ingest.classifier import UnrecognisedDocumentError, classify, read_document, score
from zaco.ingest.problems import ProblemLog
from zaco.ingest.records import DocumentKind
from zaco.ingest.values import read_text

DATA = Path(__file__).resolve().parent.parent / "data"
FILES = sorted(p for p in DATA.iterdir() if p.is_file())


def _text(path: Path) -> str:
    return read_text(path.read_bytes(), ProblemLog())


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_every_supplied_file_is_identified_confidently(path: Path) -> None:
    candidate = classify(_text(path))
    assert candidate.confidence >= 0.8


@pytest.mark.parametrize(
    ("path", "kind"),
    [(p, k) for p in FILES for k in DocumentKind],
    ids=lambda x: x.name if isinstance(x, Path) else str(x),
)
def test_a_file_declared_as_the_wrong_kind_is_refused(path: Path, kind: DocumentKind) -> None:
    data = path.read_bytes()
    actual = read_document(data).kind
    if kind is actual:
        return
    with pytest.raises(UnrecognisedDocumentError) as refusal:
        read_document(data, expected=kind)
    # The explanation has to name both what it is and what it was uploaded as, or the operator
    # cannot tell which of the two is wrong.
    assert "uploaded as" in str(refusal.value)


def test_the_consignment_report_is_not_mistaken_for_a_daily_sales_detail() -> None:
    """The trap this classifier exists for.

    `ConsignmentReports_20260525-20260531.txt` prints `Report:   Daily Sales Detail` on its own
    header line while being a poorer document -- it carries no account sale per docket at all.
    Classifying on that phrase would file it as the richer kind, and the system would then look
    for payment references that the page does not contain.
    """
    path = DATA / "ConsignmentReports_20260525-20260531.txt"
    assert "Report:   Daily Sales Detail" in path.read_text(encoding="utf-8")

    scores = score(_text(path))
    assert scores[DocumentKind.CONSIGNMENT_REPORT] > scores[DocumentKind.DAILY_SALES_DETAIL]
    assert classify(_text(path)).kind is DocumentKind.CONSIGNMENT_REPORT


def test_the_two_shapes_of_payment_details_both_classify_as_payment_details() -> None:
    for name in (
        "PaymentDetails_20260529-20260602.csv",
        "PaymentDetails_20260603-20260608.txt",
        "PaymentDetails_20260603-20260608_FarmersTrust.csv",
    ):
        assert classify(_text(DATA / name)).kind is DocumentKind.PAYMENT_DETAILS


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"   \n  \n",
        b"hello,world\n1,2,3\n",
        b"\x00\x01\x02\x03",
        b"# A perfectly good markdown file\n\nWith prose in it.\n",
    ],
    ids=["empty", "whitespace", "unrelated csv", "binary", "markdown"],
)
def test_a_file_that_is_none_of_the_five_is_refused(content: bytes) -> None:
    with pytest.raises(UnrecognisedDocumentError):
        read_document(content)


def test_the_refusal_names_the_five_kinds_it_expected() -> None:
    with pytest.raises(UnrecognisedDocumentError) as refusal:
        read_document(b"hello,world\n1,2,3\n")
    message = str(refusal.value)
    assert "Daily Sales Detail" in message
    assert "Payment Details" in message
    assert "Nothing was taken from it" in message


def test_no_two_supplied_files_of_different_kinds_are_ambiguous() -> None:
    """A tie between two readers is refused rather than guessed, so there must be no ties."""
    for path in FILES:
        scores = sorted(score(_text(path)).values(), reverse=True)
        assert scores[0] - scores[1] >= 0.15, path.name


def test_classification_does_not_depend_on_the_filename() -> None:
    """The same bytes classify the same way regardless of what they are called.

    `read_document` takes bytes and no name at all, which is the structural guarantee. This
    asserts the pairwise consequence: no two different kinds share a classification.
    """
    kinds = {path.name: read_document(path.read_bytes()).kind for path in FILES}
    for left, right in itertools.combinations(FILES, 2):
        if kinds[left.name] is not kinds[right.name]:
            assert left.read_bytes() != right.read_bytes()
