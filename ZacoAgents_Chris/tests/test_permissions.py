"""Permission parsing is lenient on read: a value the code no longer knows must not crash."""

from __future__ import annotations

from zaco.auth.permissions import ALL_PERMISSIONS, Permission, parse


def test_every_permission_has_a_description() -> None:
    from zaco.auth.permissions import DESCRIPTIONS

    assert set(DESCRIPTIONS) == set(ALL_PERMISSIONS)


def test_unknown_values_are_dropped_rather_than_raising() -> None:
    assert parse(["append", "not_a_permission", "ingest"]) == {
        Permission.APPEND,
        Permission.INGEST,
    }


def test_none_and_rubbish_read_as_no_permissions() -> None:
    assert parse(None) == set()
    assert parse(42) == set()
    assert parse([]) == set()


def test_a_comma_separated_string_is_accepted() -> None:
    assert parse("admin, append") == {Permission.ADMIN, Permission.APPEND}
