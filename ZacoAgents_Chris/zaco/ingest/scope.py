"""Reading what an export says it covers.

Section 4: "A report states its own scope. If an export was narrowed to one market or one agent
rather than run for everything, the system must say so, because the person who ran it usually
believes they took the lot."

Three states, not two, and the difference is load bearing:

* `Market:   ALL` -- a stated full scope. Nothing is missing.
* `Market,TSHWANE MARKET` -- a stated narrow scope. Everything outside it is missing, and the
  operator must be told before any figure from it is trusted as complete.
* `Market:` with nothing after it -- which is what `ConsignmentReports_20260525-20260531.txt`
  actually contains. That states *no* scope. Reading it as ALL would be inventing a fact, so it
  is reported as unstated instead.
"""

from __future__ import annotations

import re

from zaco.ingest.problems import ProblemLog
from zaco.ingest.records import DocumentScope
from zaco.ingest.values import clean, parse_date, parse_datetime, squeeze

_LABELLED = re.compile(r"^(?P<label>[A-Za-z ]+):\s*(?P<value>.*?)\s*$")
_RUN_DATE = re.compile(r"Run\s+Date:\s*(?P<stamp>[\d/\-]+\s+[\d:]+)", re.IGNORECASE)
_DATE_RANGE = re.compile(
    r"Date\s+Range:\s*(?P<from>[\d/\-]+)\s*-\s*(?P<to>[\d/\-]+)", re.IGNORECASE
)

#: What the exports print to mean "everything".
_MEANS_ALL = {"all", "*"}


def read_scope_header(lines: list[str], log: ProblemLog, limit: int = 15) -> DocumentScope:
    """Read the `Market: / Agent: / Date Range: / Run Date:` block the text reports open with."""
    scope = DocumentScope()

    for number, raw in enumerate(lines[:limit], start=1):
        line = clean(raw)
        if not line:
            continue

        run_date = _RUN_DATE.search(line)
        if run_date:
            scope.run_at = parse_datetime(run_date.group("stamp"))

        date_range = _DATE_RANGE.search(line)
        if date_range:
            scope.date_from = parse_date(date_range.group("from"))
            scope.date_to = parse_date(date_range.group("to"))
            continue

        match = _LABELLED.match(line)
        if match is None:
            continue
        label = squeeze(match.group("label")).lower()
        value = squeeze(match.group("value"))
        if label == "market":
            # `market_stated` means the export said something, not that it said ALL. A blank
            # filter is silence, and silence is not a claim of completeness.
            scope.market_stated = bool(value)
            scope.market = None if value.lower() in _MEANS_ALL or not value else value
        elif label == "agent":
            scope.agent_stated = bool(value)
            scope.agent = None if value.lower() in _MEANS_ALL or not value else value

        if label in {"market", "agent"} and not value:
            log.note(
                f"The {label} filter on this export is blank. That states no scope rather than "
                "a full one, so it is not read as ALL.",
                number,
                raw,
            )

    warn_if_narrowed(scope, log)
    return scope


def read_scope_row(row: list[str], log: ProblemLog, number: int) -> DocumentScope:
    """Read the CSV form: `Market,ALL,,Agent,ALL` or `Market,TSHWANE MARKET,,Agent,Farmers...`."""
    scope = DocumentScope()
    cells = [clean(c) for c in row]
    for index, item in enumerate(cells):
        label = item.lower().rstrip(":")
        if label not in {"market", "agent"}:
            continue
        value = next((c for c in cells[index + 1 :] if c), "")
        if label == "market":
            scope.market_stated = True
            scope.market = None if value.lower() in _MEANS_ALL else value or None
        else:
            scope.agent_stated = True
            scope.agent = None if value.lower() in _MEANS_ALL else value or None

    warn_if_narrowed(scope, log, number)
    return scope


def warn_if_narrowed(scope: DocumentScope, log: ProblemLog, number: int | None = None) -> None:
    if scope.is_narrowed:
        named = " and ".join(p for p in (scope.market, scope.agent) if p)
        log.warn(
            f"This export was run for {named} only, not for everything. Anything outside that "
            "is absent from this file rather than absent from the business.",
            number,
        )
    elif scope.is_unstated:
        log.note(
            "This export does not state which markets or agents it covers, so it cannot be "
            "assumed to be complete.",
            number,
        )
