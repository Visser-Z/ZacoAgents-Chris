"""Appending to the operator's live book, and rolling it back (section 5, D4).

Every response here is shaped so the operator can see what is about to happen before it does.
The preview shows the exact cells, formula columns as formulas, and the letters they resolved to
in *this* book -- because the brief's letters are wrong for the real file and a preview that
hid that would hide the one thing worth checking.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from zaco.api.render import money, number
from zaco.api.schemas import (
    AppendedRowOut,
    AppendPreviewOut,
    BookRowOut,
    PreviewRowOut,
    ReadyRoundOut,
    ReasonIn,
    SnapshotOut,
    WorkbookStateOut,
)
from zaco.auth.deps import current_user, requires
from zaco.auth.permissions import Permission
from zaco.db.base import get_db
from zaco.db.models import Round, RoundAction, RoundStatus, User, utcnow
from zaco.resolve import service
from zaco.workbook import agreement, snapshot
from zaco.workbook import append as appender
from zaco.workbook.locate import (
    BookRow,
    SheetLayout,
    WorkbookShapeError,
    locate,
    read_rows,
)

router = APIRouter(prefix="/api/workbook", tags=["workbook"])
rounds = APIRouter(prefix="/api/rounds", tags=["workbook"])

may_append = requires(Permission.APPEND)

#: How many of the book's own rows the state endpoint draws. An append lands at the bottom, so
#: the bottom is what an operator opens this page to look at. A book with years in it would
#: otherwise serialise every row of every sheet on every page load.
MOST_RECENT_ROWS = 500


def _order(layout: SheetLayout) -> list[str]:
    """Field names left to right, the way the book itself reads."""
    return sorted(layout.columns, key=lambda name: layout.columns[name])


def _ready(db: Session) -> list[ReadyRoundOut]:
    """Rounds whose queue is closed and which the book has not seen yet."""
    found = (
        db.execute(
            select(Round)
            .where(Round.status == RoundStatus.RESOLVED.value, Round.appended_at.is_(None))
            .order_by(Round.id)
        )
        .scalars()
        .all()
    )
    return [
        ReadyRoundOut(
            round_id=r.id,
            label=r.label,
            resolved_at=r.resolved_at,
            resolved_by=r.resolved_by.email if r.resolved_by else None,
        )
        for r in found
    ]


def _snapshots() -> list[SnapshotOut]:
    return [
        SnapshotOut(
            name=s.name,
            taken_at=s.taken_at,
            label=s.label,
            byte_count=s.byte_count,
        )
        for s in snapshot.listing()
    ]


@router.get("", response_model=WorkbookStateOut)
def state(db: Session = Depends(get_db), _: User = Depends(current_user)) -> WorkbookStateOut:
    """What the book looks like right now, and every version kept of it."""
    path = service.workbook_path()
    if not path.exists():
        return WorkbookStateOut(
            filename=path.name,
            is_readable=False,
            problem=f"There is no workbook at {path}. Nothing can be appended until there is.",
            versions=_snapshots(),
            ready_rounds=_ready(db),
        )
    try:
        layout = locate(path)
    except WorkbookShapeError as refusal:
        return WorkbookStateOut(
            filename=path.name,
            is_readable=False,
            problem=str(refusal),
            versions=_snapshots(),
            ready_rounds=_ready(db),
        )

    appended = (
        db.execute(
            select(Round)
            .where(Round.appended_at.is_not(None))
            .order_by(Round.appended_at.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )
    in_book = read_rows(path, layout, with_cells=True)
    agreements = _agreements(db, appended, in_book)
    shown = in_book[-MOST_RECENT_ROWS:]
    return WorkbookStateOut(
        filename=path.name,
        is_readable=True,
        sheet_name=layout.sheet_name,
        header_row=layout.header_row,
        row_count=len(in_book),
        letters={name: layout.letter(name) or "" for name in _order(layout)},
        headers={name: layout.headers.get(name, name) for name in _order(layout)},
        order=_order(layout),
        unknown_headers=dict(sorted(layout.unknown_headers.items())),
        byte_count=path.stat().st_size,
        versions=_snapshots(),
        ready_rounds=_ready(db),
        rows=[
            BookRowOut(row_number=r.row_number, cells=r.cells, formulas=r.formulas) for r in shown
        ],
        rows_from=shown[0].row_number if shown else 0,
        numeric_columns=sorted(_MONEY | _QUANTITY | set(appender.FORMULAS)),
        never_written=sorted(appender.NEVER_WRITTEN),
        appended_rounds=[
            AppendedRowOut(
                round_id=r.id,
                first_row=r.appended_first_row or 0,
                last_row=r.appended_last_row or 0,
                appended_at=r.appended_at,
                appended_by=r.appended_by.email if r.appended_by else None,
                agrees=agreements[r.id].agrees,
                finding=agreements[r.id].finding,
                checked=agreements[r.id].checked,
            )
            for r in appended
        ],
    )


def _agreements(
    db: Session, appended: Sequence[Round], in_book: list[BookRow]
) -> dict[int, agreement.Agreement]:
    """Hold every appended round's claim against the file, and against the other claims.

    Re-derived rather than stored, per S1: the documents are the durable record and everything
    else is worked out from them on read. That costs about 40ms a round and means a corrected
    reader shows up here as a difference rather than hiding behind a figure written weeks ago.
    """
    spans = {
        r.id: (r.appended_first_row, r.appended_last_row)
        for r in appended
        if r.appended_first_row is not None and r.appended_last_row is not None
    }
    clashes = agreement.contested(spans)

    found: dict[int, agreement.Agreement] = {}
    for round_ in appended:
        first = round_.appended_first_row
        if first is None:
            found[round_.id] = agreement.Agreement(
                agrees=False,
                finding=(
                    "This round is marked as appended but the record does not say which rows it "
                    "wrote, so nothing can be held against the file."
                ),
            )
            continue
        try:
            built = appender.plan(service.load(db, round_))
        except Exception as failure:  # noqa: BLE001 -- a broken round must not blank the page
            found[round_.id] = agreement.Agreement(
                agrees=False,
                finding=(
                    f"This round cannot be re-derived from its documents ({failure}), so what it "
                    f"wrote cannot be compared with what the book now holds."
                ),
            )
            continue
        claims = [
            agreement.RowClaim(
                row_number=first + offset,
                dn=_as_text(planned.values.get("dn")),
                stm_no=_as_text(planned.values.get("stm_no")),
                description=_as_text(planned.values.get("description")),
            )
            for offset, planned in enumerate(built.rows)
        ]
        result = agreement.compare(claims, in_book)
        if round_.id in clashes:
            result = agreement.Agreement(
                agrees=False,
                finding=" ".join(filter(None, [clashes[round_.id], result.finding])),
                checked=result.checked,
            )
        found[round_.id] = result
    return found


def _saved_as(round_id: int) -> str | None:
    """The copy taken before this round was appended, found by the label the append gave it.

    Looked up by label rather than parsed out of the event's sentence, and `None` when retention
    has already dropped it -- a version that is gone must read as gone, not as a blank name.
    """
    label = f"before round {round_id}"
    return next((s.name for s in snapshot.listing() if s.label == label), None)


def _as_text(value: object) -> str | None:
    """The same reading `read_rows` gives a cell, so the two sides compare like with like."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


@router.get("/download", response_class=FileResponse)
def download(_: User = Depends(may_append)) -> FileResponse:
    path = service.workbook_path()
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"There is no workbook at {path}.")
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@rounds.get("/{round_id}/append", response_model=AppendPreviewOut)
def preview(
    round_id: int, db: Session = Depends(get_db), _: User = Depends(may_append)
) -> AppendPreviewOut:
    """Exactly what would be written, with nothing written."""
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No round {round_id}.")
    return _preview(db, round_)


@rounds.post("/{round_id}/append", response_model=AppendPreviewOut)
def do_append(
    round_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(may_append),
) -> AppendPreviewOut:
    """Snapshot the book, append the rows, and mark the round -- or do none of it (D4)."""
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No round {round_id}.")

    resolved = service.load(db, round_)
    built = appender.plan(resolved)
    if not built.is_writable:
        raise HTTPException(status.HTTP_409_CONFLICT, "; ".join(built.refusals))

    # Marked before the file is touched, and rolled back with the file if the write throws, so
    # "appended" and "actually in the book" cannot come apart.
    round_.status = RoundStatus.APPENDED.value
    round_.appended_at = utcnow()
    round_.appended_by = user
    db.flush()

    try:
        result = appender.append(service.workbook_path(), built, label=f"before round {round_.id}")
    except (appender.AppendRefusedError, WorkbookShapeError) as refusal:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(refusal)) from refusal
    except OSError as failure:
        db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"The workbook could not be written ({failure}). It was put back as it was, and the "
            "round is still waiting to be appended.",
        ) from failure

    round_.appended_first_row = result.first_row
    round_.appended_last_row = result.last_row
    service.record(
        db,
        round_,
        user,
        RoundAction.APPENDED,
        f"rows {result.first_row}-{result.last_row} of {result.sheet_name}",
        f"saved as {result.saved_as.name} first",
    )
    db.flush()
    return _preview(db, round_, appended=result)


@router.post("/versions/{name}/restore", response_model=WorkbookStateOut)
def restore(
    name: str,
    body: ReasonIn,
    db: Session = Depends(get_db),
    user: User = Depends(may_append),
) -> WorkbookStateOut:
    """Put an older version of the book back, saving the current one first.

    The rounds that wrote into the discarded version keep their `appended` mark. Restoring does
    not un-append them: the rows may or may not be in the version being restored, and quietly
    reopening them would invite a second append that duplicates whatever survived.
    """
    found = snapshot.find(name)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"There is no saved version called {name}.")
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Say why the book is being rolled back. It is the file the business settles money "
            "against, and whoever opens it next needs to know which version they have.",
        )

    replaced = snapshot.restore(found, service.workbook_path())
    latest = (
        db.execute(
            select(Round).where(Round.appended_at.is_not(None)).order_by(Round.appended_at.desc())
        )
        .scalars()
        .first()
    )
    if latest is not None:
        service.record(
            db,
            latest,
            user,
            RoundAction.ROLLED_BACK,
            f"restored {found.name}",
            f"{reason} (the version it replaced was kept as {replaced.name})",
        )
        db.flush()
    return state(db, user)


def _preview(
    db: Session, round_: Round, appended: appender.AppendResult | None = None
) -> AppendPreviewOut:
    resolved = service.load(db, round_)
    built = appender.plan(resolved)
    path = service.workbook_path()

    letters: dict[str, str] = {}
    headers: dict[str, str] = {}
    order: list[str] = []
    next_row = 0
    try:
        layout = locate(path)
        order = _order(layout)
        letters = {name: layout.letter(name) or "" for name in order}
        headers = {name: layout.headers.get(name, name) for name in order}
        next_row = layout.last_data_row + 1
    except (WorkbookShapeError, FileNotFoundError):
        pass

    # A round that has already been appended is shown at the rows it actually wrote, not at the
    # next free row. Getting this wrong is not cosmetic: the row number goes into every formula,
    # so the preview would print `=IFERROR(P10*70%,"-")` for a cell the book holds as `P5`.
    start = appended.first_row if appended else (round_.appended_first_row or next_row)
    return AppendPreviewOut(
        round_id=round_.id,
        status=round_.status,
        is_writable=built.is_writable,
        refusals=sorted(set(built.refusals)),
        first_row=start,
        letters=letters,
        headers=headers,
        order=order,
        numeric_columns=sorted(_MONEY | _QUANTITY | set(appender.FORMULAS)),
        formula_columns=sorted(appender.FORMULAS),
        never_written=sorted(appender.NEVER_WRITTEN),
        rows=[
            PreviewRowOut(
                row_number=str(start + offset) if start else "",
                delivery_id=planned.delivery_id or "",
                account_sale=planned.account_sale,
                product=planned.product,
                is_writable=planned.is_writable,
                blocked_by=planned.blocked,
                why=" ".join(planned.notes),
                cells=_cells(planned, letters, start + offset if start else 0),
                blanks=_blanks(planned, start),
            )
            for offset, planned in enumerate(built.rows)
        ],
        appended_at=round_.appended_at,
        appended_by=round_.appended_by.email if round_.appended_by else None,
        appended_rows=(
            None
            if round_.appended_first_row is None
            else f"{round_.appended_first_row}-{round_.appended_last_row}"
        ),
        saved_as=appended.saved_as.name if appended else _saved_as(round_.id),
        versions=_snapshots(),
    )


def _blanks(planned: appender.PlannedRow, start: int) -> dict[str, str]:
    """The blank labels, with the one that points at another row naming it by row number."""
    labels = dict(planned.blanks)
    if planned.counted_with is not None and start:
        labels["qty_received"] = f"counted on row {start + planned.counted_with}"
    return labels


#: How each written column is shown in the preview. Money and quantities cross the wire as
#: strings so no client can turn a Decimal into a float on the way to the screen.
_MONEY = {"price", "nett_total"}
_QUANTITY = {"qty_received", "opening_stock", "cartons_sold"}


def _cells(
    planned: appender.PlannedRow, letters: dict[str, str], row_number: int
) -> dict[str, str]:
    cells: dict[str, str] = {}
    for name in letters:
        if name in appender.NEVER_WRITTEN:
            cells[name] = ""
            continue
        if name in appender.FORMULAS:
            cells[name] = (
                appender.FORMULAS[name].format(r=row_number, **letters) if row_number else ""
            )
            continue
        value = planned.values.get(name)
        if value is None:
            cells[name] = ""
        elif name in _MONEY:
            cells[name] = money(value)  # type: ignore[arg-type]
        elif name in _QUANTITY:
            cells[name] = number(value)  # type: ignore[arg-type]
        else:
            cells[name] = str(value)
    return cells
