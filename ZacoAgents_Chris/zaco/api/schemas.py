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
