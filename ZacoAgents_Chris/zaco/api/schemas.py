"""Request and response shapes for `/api/*`.

These are the contract a React or Flutter frontend would build against later (D1), so they are
kept explicit rather than serialising ORM objects directly.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from zaco.auth.permissions import Permission


class HealthOut(BaseModel):
    status: str
    database: str
    workbook_dir_writable: bool
    warnings: list[str] = Field(default_factory=list)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    permissions: list[Permission]
    is_active: bool
    last_login_at: datetime | None = None


class InviteIn(BaseModel):
    email: EmailStr
    permissions: list[Permission] = Field(default_factory=list)


class InvitationOut(BaseModel):
    id: int
    email: str
    permissions: list[Permission]
    accept_url: str
    expires_at: datetime
    accepted_at: datetime | None = None


class AcceptIn(BaseModel):
    token: str
    password: str
    display_name: str = ""


class PermissionsIn(BaseModel):
    permissions: list[Permission] = Field(default_factory=list)


class ActiveIn(BaseModel):
    is_active: bool


class Message(BaseModel):
    detail: str


# --- Ingest (Phase 1) -------------------------------------------------------------------------


class ProblemOut(BaseModel):
    severity: str
    message: str
    line_number: int | None = None
    line: str | None = None


class ScopeOut(BaseModel):
    description: str
    market: str | None = None
    agent: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    run_at: datetime | None = None
    is_narrowed: bool
    is_unstated: bool


class RecordPreview(BaseModel):
    """One parsed record, flattened for display. The domain model arrives in Phase 2."""

    label: str
    detail: str
    figures: dict[str, str] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)


class InspectionOut(BaseModel):
    filename: str
    kind: str
    kind_title: str
    confidence: float
    scores: dict[str, float]
    scope: ScopeOut
    counts: dict[str, int]
    problems: list[ProblemOut]
    preview: list[RecordPreview]


class RefusalOut(BaseModel):
    """Why a document was not read. Section 4 requires an explanation, not a stack trace."""

    filename: str
    detail: str
    scores: dict[str, float]


# --- Staged round (Phase 2) -------------------------------------------------------------------


class ProductOut(BaseModel):
    key: str
    display_name: str
    short_code: str | None = None
    vocabularies: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    merge_reasons: list[str] = Field(default_factory=list)


class SuggestionOut(BaseModel):
    """A possible product link, with its reasoning. Never applied automatically."""

    left: str
    right: str
    reason: str


class CartonsOut(BaseModel):
    """Sold, returned and net, with absent kept apart from zero (section 6)."""

    sold: str
    returned: str | None
    net: str
    returns_reportable: bool


class RowOut(BaseModel):
    """One prospective workbook row: delivery x product x account sale."""

    delivery_id: str | None
    consignment_id: str | None
    product: str
    short_code: str | None
    account_sale: str
    account_sale_display: str
    market: str | None
    agent: str | None
    cartons: CartonsOut
    value: str
    price: str | None
    earliest_date: date | None


class ConsignmentOut(BaseModel):
    consignment_id: str | None
    product: str
    short_code: str | None
    market: str | None
    agent: str | None
    qty_sent: str | None
    qty_available: str | None
    cartons: CartonsOut
    value: str
    docket_count: int
    account_sales: list[str] = Field(default_factory=list)
    days_on_market: int | None = None
    is_identifiable: bool = True


class DeliveryOut(BaseModel):
    delivery_id: str | None
    dn: str | None
    supplier_ref: str | None
    producer_code: str | None
    reference_half: str | None
    market: str | None
    agent: str | None
    qty_sent: str
    consignments: list[ConsignmentOut] = Field(default_factory=list)


class AccountSaleOut(BaseModel):
    number: str
    display_number: str
    market: str | None
    agent: str | None
    date_paid: date | None
    nett: str | None
    gross: str | None
    deduction_share: str | None
    has_commodity_breakdown: bool
    row_count: int


class UnpaidDocketOut(BaseModel):
    consignment_id: str | None
    docket_number: str
    date_sold: date | None
    quantity: str | None
    value: str | None


class StagedRoundOut(BaseModel):
    sources: list[str]
    totals: dict[str, str]
    cartons: CartonsOut
    deliveries: list[DeliveryOut]
    rows: list[RowOut]
    account_sales: list[AccountSaleOut]
    products: list[ProductOut]
    suggestions: list[SuggestionOut]
    unpaid_dockets: list[UnpaidDocketOut]
    problems: list[ProblemOut]


# --- Resolution queue (Phase 3) ---------------------------------------------------------------


class TestOut(BaseModel):
    """One of the three tests a supplier reference has to pass to be proposed as a DN."""

    name: str
    passed: bool
    detail: str


class QueueItemOut(BaseModel):
    """One open question, with the evidence it was raised on."""

    kind: str
    key: str
    title: str
    question: str
    reasoning: str
    evidence: dict[str, str] = Field(default_factory=dict)
    proposal: str | None = None
    provenance: str | None = None
    tests: list[TestOut] = Field(default_factory=list)
    counter_evidence: str | None = None
    choices: list[str] = Field(default_factory=list)
    companions: list[str] = Field(default_factory=list)
    requires_reason: bool = False


class SuspensionOut(BaseModel):
    id: int
    subject_kind: str
    subject_key: str
    description: str
    differences: str
    chosen_source: str | None = None
    reason: str = ""
    is_decided: bool = False
    decided_by: str | None = None
    decided_at: datetime | None = None


class AlertOut(BaseModel):
    """Something that was deliberately not counted, said out loud rather than logged (D12)."""

    subject: str
    message: str


class DeliveryNoteOut(BaseModel):
    delivery_id: str
    dn: str | None
    provenance: str
    reasoning: str
    operator_reason: str = ""
    approved_by: str | None = None
    approved_at: datetime | None = None


class StockOut(BaseModel):
    """Opening stock, what sold, and what is left. Absent stays absent (section 6)."""

    opening: str | None
    sold: str
    closing: str | None
    is_carried_forward: bool = False
    note: str | None = None


class ResolvedRowOut(RowOut):
    """A prospective workbook row once the queue's answers are applied to it."""

    dn: str | None = None
    dn_provenance: str | None = None
    grouping_date: date | None = None
    stock: StockOut | None = None
    is_writable: bool = False
    blocked_by: list[str] = Field(default_factory=list)


class RoundSummaryOut(BaseModel):
    id: int
    label: str
    status: str
    created_at: datetime
    created_by: str | None = None
    document_count: int
    duplicate_count: int = 0
    withdrawn_count: int = 0
    open_questions: int = 0


class DocumentOut(BaseModel):
    """One uploaded file and whether it is currently contributing anything."""

    id: int
    filename: str
    kind: str
    byte_count: int
    state: str
    """`counted`, `duplicate` or `withdrawn`."""

    duplicate_of_round_id: int | None = None
    withdrawn_reason: str = ""
    withdrawn_by: str | None = None
    withdrawn_at: datetime | None = None


class EventOut(BaseModel):
    """Something a person did to this round after it was uploaded."""

    action: str
    subject: str
    reason: str
    at: datetime
    by: str | None = None


class RoundOut(BaseModel):
    """One saved round, everything it amounts to, and everything still unanswered."""

    summary: RoundSummaryOut
    totals: dict[str, str]
    cartons: CartonsOut
    is_clear: bool
    blocking_reason: str | None = None
    book: dict[str, str]
    queue: list[QueueItemOut] = Field(default_factory=list)
    suspensions: list[SuspensionOut] = Field(default_factory=list)
    alerts: list[AlertOut] = Field(default_factory=list)
    delivery_notes: list[DeliveryNoteOut] = Field(default_factory=list)
    rows: list[ResolvedRowOut] = Field(default_factory=list)
    deliveries: list[DeliveryOut] = Field(default_factory=list)
    account_sales: list[AccountSaleOut] = Field(default_factory=list)
    products: list[ProductOut] = Field(default_factory=list)
    problems: list[ProblemOut] = Field(default_factory=list)
    stock_notes: list[str] = Field(default_factory=list)
    documents: list[DocumentOut] = Field(default_factory=list)
    events: list[EventOut] = Field(default_factory=list)
    orphaned_delivery_notes: list[DeliveryNoteOut] = Field(default_factory=list)
    """Approved notes whose delivery a withdrawal took away -- their numbers are still held."""


class ApproveDnIn(BaseModel):
    dn: str | None = None
    """`None` records a deliberate "no delivery note", which needs a reason (D11)."""

    provenance: str = "operator"
    reason: str = ""


class BulkDnIn(BaseModel):
    """One delivery note across several deliveries -- the one-truck case."""

    delivery_ids: list[str] = Field(min_length=1)
    dn: str | None = None
    provenance: str = "operator"
    reason: str = ""


class CaptureCodeIn(BaseModel):
    product_key: str
    short_code: str = Field(min_length=1, max_length=200)


class LinkDecisionIn(BaseModel):
    left: str
    right: str
    accepted: bool
    reason: str = ""


class ReasonIn(BaseModel):
    """A typed reason, for the actions that undo something somebody already did.

    Not `min_length=1` here: the endpoints check it themselves so the refusal can say what the
    reason is for, which is the difference between a message that teaches and one that nags.
    """

    reason: str = ""


class DecideSuspensionIn(BaseModel):
    chosen_source: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    """Mandatory. A choice with no reason is unusable to whoever reads it next quarter (D12)."""


# --- the workbook (section 5) --------------------------------------------------------------------


class SnapshotOut(BaseModel):
    """One saved version of the operator's book."""

    name: str
    taken_at: datetime
    label: str = ""
    byte_count: int


class AppendedRowOut(BaseModel):
    """Which rows of the book one round wrote, and whether the book still holds them."""

    round_id: int
    first_row: int
    last_row: int
    appended_at: datetime | None = None
    appended_by: str | None = None

    agrees: bool = True
    """False when the file no longer holds what the record says this round wrote."""

    finding: str | None = None
    """What differs, in plain words. Only set when `agrees` is false."""

    checked: str = ""
    """What the comparison looked at, and what it therefore could not see. Always shown."""


class ReadyRoundOut(BaseModel):
    """A round whose queue is closed and which has not been appended yet."""

    round_id: int
    label: str = ""
    resolved_at: datetime | None = None
    resolved_by: str | None = None


class WorkbookStateOut(BaseModel):
    """The book as it stands, and the letters its columns actually resolved to.

    `letters` is not decoration. The brief prints 21 columns A to U; the real book has 23, so
    `Baby Stock` is at L and not K. Showing what was resolved is the only way an operator can
    check that the system is writing into the columns they think it is.
    """

    filename: str
    is_readable: bool
    problem: str | None = None
    sheet_name: str | None = None
    header_row: int | None = None
    row_count: int = 0
    byte_count: int = 0
    letters: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    order: list[str] = Field(default_factory=list)
    unknown_headers: dict[str, int] = Field(default_factory=dict)
    """Columns the book has that this system does not write. `Buyer note` and `Packhouse` land
    here, and they are the reason nothing may be written by position."""

    versions: list[SnapshotOut] = Field(default_factory=list)
    appended_rounds: list[AppendedRowOut] = Field(default_factory=list)
    ready_rounds: list[ReadyRoundOut] = Field(default_factory=list)


class PreviewRowOut(BaseModel):
    """One row as it would be written.

    `cells` is kept in its own dict rather than flattened alongside these fields, because one of
    the workbook's own columns is called NOTES and a flattened shape let it quietly overwrite the
    row's explanation of itself.
    """

    row_number: str
    delivery_id: str
    account_sale: str
    product: str
    is_writable: bool = True
    blocked_by: list[str] = Field(default_factory=list)
    why: str = ""
    """Every reason at length, for the list beneath the grid."""

    cells: dict[str, str] = Field(default_factory=dict)
    blanks: dict[str, str] = Field(default_factory=dict)
    """Field name to a short label saying why that cell is empty, shown in the cell itself."""


class AppendPreviewOut(BaseModel):
    """Exactly what would be written, or exactly what was."""

    round_id: int
    status: str
    is_writable: bool
    refusals: list[str] = Field(default_factory=list)
    first_row: int = 0
    letters: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    """Field name to the header text as this book writes it, so the grid shows the operator
    their own words above their own letters."""

    order: list[str] = Field(default_factory=list)
    """Field names in the order the columns sit in this book, left to right."""

    numeric_columns: list[str] = Field(default_factory=list)
    formula_columns: list[str] = Field(default_factory=list)
    """Columns that belong to the operator. A computed value is never written into one."""

    never_written: list[str] = Field(default_factory=list)
    rows: list[PreviewRowOut] = Field(default_factory=list)
    appended_at: datetime | None = None
    appended_by: str | None = None
    appended_rows: str | None = None
    saved_as: str | None = None
    versions: list[SnapshotOut] = Field(default_factory=list)
