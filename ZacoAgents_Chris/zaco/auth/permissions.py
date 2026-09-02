"""What an account is allowed to do (D14).

Granular per account rather than fixed roles, because the operator, whoever settles terms, and
whoever only reads reports are three different jobs that do not nest neatly.

Every queue answer, DN approval, duplicate decision and append is stamped with the person who
made it. That trail is the reason D14 rejects shared domain accounts: "chose the FarmersTrust
export because X" is worth nothing if the record says a domain decided.
"""

from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    INGEST = "ingest"
    """Upload and stage a round of agent reports."""

    RESOLVE = "resolve"
    """Answer the resolution queue: product codes, DNs, duplicate conflicts."""

    APPEND = "append"
    """Write staged rows into the operator's live workbook, and roll a version back."""

    RECORD_TERMS = "record_terms"
    """Maintain the supplier register and the agreed commission per delivery line."""

    VIEW_REPORTS = "view_reports"
    """Read reconciliation, settlement, reporting and the agent conduct panel."""

    ADMIN = "admin"
    """Invite accounts and set their permissions."""


ALL_PERMISSIONS: tuple[Permission, ...] = tuple(Permission)

DESCRIPTIONS: dict[Permission, str] = {
    Permission.INGEST: "Upload and stage rounds",
    Permission.RESOLVE: "Answer the resolution queue",
    Permission.APPEND: "Append to the workbook and roll back versions",
    Permission.RECORD_TERMS: "Record suppliers and commission terms",
    Permission.VIEW_REPORTS: "View reports",
    Permission.ADMIN: "Invite accounts and set permissions",
}


def parse(values: object) -> set[Permission]:
    """Read a stored or submitted permission list leniently, dropping anything unrecognised."""
    if values is None:
        return set()
    if isinstance(values, str):
        values = [part.strip() for part in values.split(",")]
    if not isinstance(values, (list, tuple, set, frozenset)):
        return set()
    out: set[Permission] = set()
    for value in values:
        try:
            out.add(Permission(str(value).strip()))
        except ValueError:
            continue
    return out
