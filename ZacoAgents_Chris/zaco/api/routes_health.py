"""Health check, and an honest statement of anything configured insecurely.

Reports what it actually checked rather than a bare "ok", so a green tick never stands in for a
check that was never made.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from zaco.api.schemas import HealthOut
from zaco.config import get_settings
from zaco.db.base import get_db

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    settings = get_settings()
    warnings: list[str] = []

    try:
        db.execute(text("SELECT 1"))
        database = "up"
    except Exception as exc:  # noqa: BLE001 - the message is the useful part here.
        database = f"down: {type(exc).__name__}"
        warnings.append("The durable record is unreachable. Nothing may be ingested or appended.")

    writable = False
    try:
        settings.workbook_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.workbook_dir / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        writable = True
    except OSError as exc:
        warnings.append(f"Workbook directory is not writable ({exc.strerror}).")

    if settings.is_insecure_secret:
        warnings.append("SECRET_KEY is the shipped default. Set a real one before hosting.")

    # A missing lookup does not crash anything; it just means every product arrives
    # unresolved, which reads as 'more work to do' rather than 'the file is not there'.
    from zaco.domain.build import LOOKUP_PATH

    if not LOOKUP_PATH.exists():
        warnings.append(
            f"Product short-code lookup is missing at {LOOKUP_PATH}. Every product will "
            "arrive unresolved."
        )

    return HealthOut(
        status="ok" if database == "up" and writable and not warnings else "degraded",
        database=database,
        workbook_dir_writable=writable,
        warnings=warnings,
    )
