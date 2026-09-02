"""Deciding what a document is, by reading it.

Section 4: "Identify each document by its content, not by its filename. A document loaded into
the wrong place must be refused with an explanation, not parsed into nonsense."

So the filename is never consulted -- not even as a tie-breaker. Every reader offers a
confidence from the text alone, and three outcomes are possible:

* one reader is clearly best -- parse with it
* nothing recognises the document -- refuse, and say what the five known kinds look like
* two readers are equally confident -- refuse, because guessing between them is exactly how a
  document gets parsed into nonsense

The case that makes this worth doing properly: `ConsignmentReports_20260525-20260531.txt` prints
`Report:   Daily Sales Detail` on its own header line. Classifying on that phrase would file it
as the richer document, and the system would then look for account sale numbers that the page
does not contain.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from zaco.ingest import (
    account_sales,
    consignment_report,
    daily_sales,
    nett_adjustments,
    payment_details,
)
from zaco.ingest.problems import ProblemLog
from zaco.ingest.records import TITLES, DocumentKind, ParseResult
from zaco.ingest.values import read_text

#: Below this, a document is not recognised at all.
RECOGNITION_THRESHOLD = 0.5

#: Two candidates closer together than this are a tie, and a tie is refused rather than guessed.
AMBIGUITY_MARGIN = 0.15


@dataclass(frozen=True)
class Candidate:
    kind: DocumentKind
    confidence: float
    sniff: Callable[[str], float]
    parse: Callable[[str, ProblemLog], ParseResult]


class UnrecognisedDocumentError(Exception):
    """Raised when a document cannot be identified, carrying an explanation for the operator."""

    def __init__(self, message: str, scores: dict[DocumentKind, float]) -> None:
        super().__init__(message)
        self.scores = scores


def _article(title: str) -> str:
    return f"an {title}" if title[0].upper() in "AEIOU" else f"a {title}"


_READERS = (
    (DocumentKind.DAILY_SALES_DETAIL, daily_sales),
    (DocumentKind.CONSIGNMENT_REPORT, consignment_report),
    (DocumentKind.ACCOUNT_SALES_STATEMENT, account_sales),
    (DocumentKind.PAYMENT_DETAILS, payment_details),
    (DocumentKind.NETT_PAYMENT_ADJUSTMENTS, nett_adjustments),
)


def score(text: str) -> dict[DocumentKind, float]:
    """What each reader makes of this document. Useful to show the operator either way."""
    return {kind: module.sniff(text) for kind, module in _READERS}


def classify(text: str) -> Candidate:
    scores = score(text)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_kind, best_score = ranked[0]

    if best_score < RECOGNITION_THRESHOLD:
        raise UnrecognisedDocumentError(
            "This file does not read as any of the five report kinds this system handles. "
            "Expected one of: "
            + ", ".join(TITLES[kind] for kind, _ in _READERS)
            + ". Nothing was taken from it.",
            scores,
        )

    runner_up_kind, runner_up_score = ranked[1]
    if best_score - runner_up_score < AMBIGUITY_MARGIN:
        raise UnrecognisedDocumentError(
            f"This file reads equally as {_article(TITLES[best_kind])} and "
            f"{_article(TITLES[runner_up_kind])}, "
            "so it cannot be identified with confidence. Guessing between the two risks reading "
            "figures that are not there. Nothing was taken from it.",
            scores,
        )

    module = dict(_READERS)[best_kind]
    return Candidate(kind=best_kind, confidence=best_score, sniff=module.sniff, parse=module.parse)


def read_document(data: bytes, expected: DocumentKind | None = None) -> ParseResult:
    """Classify and parse one uploaded file.

    `expected` is what the operator said they were uploading. A mismatch is refused rather than
    honoured in either direction: the file is not what they think it is, and that is worth
    stopping for.
    """
    log = ProblemLog()
    text = read_text(data, log)
    if not text.strip():
        raise UnrecognisedDocumentError("The file is empty, or could not be read as text.", {})

    candidate = classify(text)
    if expected is not None and candidate.kind is not expected:
        raise UnrecognisedDocumentError(
            f"This file reads as {_article(TITLES[candidate.kind])}, but it was uploaded as "
            f"{_article(TITLES[expected])}. Nothing was taken from it. Check which export "
            "was run.",
            score(text),
        )

    result = candidate.parse(text, log)
    result.problems = log.items
    return result
