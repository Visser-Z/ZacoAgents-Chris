"""Timestamped copies of the operator's book, taken as a step inside the append (D4).

A sidecar container cannot do this job. A Render disk mounts to exactly one service, so a
compose sidecar has nothing to share, and a sidecar that copies a file on a timer can catch it
mid-write and store a snapshot that will not open. Taking the copy inside the append instead
means the thing that is about to change the file is the thing that saved it, and the two either
both happen or neither does.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from zaco.config import get_settings

STAMP = "%Y%m%dT%H%M%S"
NAME = re.compile(r"^(?P<stem>.+)\.(?P<stamp>\d{8}T\d{6})(?P<label>\.[^.]*)?\.xlsx$")


@dataclass(frozen=True)
class Snapshot:
    """One saved version of the book."""

    path: Path
    taken_at: datetime
    label: str
    byte_count: int

    @property
    def name(self) -> str:
        return self.path.name


def directory() -> Path:
    return get_settings().backup_dir


def _slug(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", label).strip("-").lower()
    return cleaned[:40]


def take(source: Path, label: str = "") -> Snapshot:
    """Copy the book aside before anything touches it.

    `copy2` rather than `copy`, so the snapshot keeps the original's timestamps and an operator
    comparing two versions is not looking at the moment they were backed up.
    """
    target_dir = directory()
    target_dir.mkdir(parents=True, exist_ok=True)
    taken_at = datetime.now(UTC)
    slug = _slug(label)
    stem = source.stem
    name = f"{stem}.{taken_at.strftime(STAMP)}" + (f".{slug}" if slug else "") + ".xlsx"
    target = target_dir / name
    shutil.copy2(source, target)
    return Snapshot(path=target, taken_at=taken_at, label=label, byte_count=target.stat().st_size)


def listing() -> list[Snapshot]:
    """Every snapshot, newest first."""
    target_dir = directory()
    if not target_dir.is_dir():
        return []
    found: list[Snapshot] = []
    for path in target_dir.glob("*.xlsx"):
        match = NAME.match(path.name)
        if match is None:
            continue
        try:
            taken_at = datetime.strptime(match["stamp"], STAMP).replace(tzinfo=UTC)
        except ValueError:
            continue
        label = (match["label"] or "").lstrip(".").replace("-", " ")
        found.append(
            Snapshot(path=path, taken_at=taken_at, label=label, byte_count=path.stat().st_size)
        )
    return sorted(found, key=lambda s: s.taken_at, reverse=True)


def find(name: str) -> Snapshot | None:
    """Look a snapshot up by filename, refusing anything that is not one of ours.

    Matched against the listing rather than joined onto the backup directory, so a name
    containing `..` or a separator cannot address a file outside it.
    """
    return next((s for s in listing() if s.name == name), None)


def prune(keep: int | None = None) -> list[Snapshot]:
    """Drop the oldest snapshots past the retention setting. Returns what was removed."""
    keep = get_settings().backup_retention if keep is None else keep
    everything = listing()
    doomed = everything[keep:]
    for snapshot in doomed:
        snapshot.path.unlink(missing_ok=True)
    return doomed


def restore(snapshot: Snapshot, destination: Path) -> Snapshot:
    """Put an older version back, saving the current one first.

    The copy taken here is what makes a rollback undoable. Without it, restoring the wrong
    version destroys the file the operator was actually working on, and a one-click control that
    can do that is a trap.
    """
    replaced = take(destination, label="before rollback") if destination.exists() else None
    shutil.copy2(snapshot.path, destination)
    prune()
    return replaced if replaced is not None else snapshot
