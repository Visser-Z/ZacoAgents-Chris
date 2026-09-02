"""Password hashing, session cookies and the invite domain gate. No database needed."""

from __future__ import annotations

from pathlib import Path

import pytest

from zaco.auth.service import (
    domain_allowed,
    hash_password,
    issue_session,
    normalise_email,
    read_session,
    verify_password,
)
from zaco.config import Settings
from zaco.db.models import User


def test_password_verification() -> None:
    stored = hash_password("a real password")
    assert verify_password(stored, "a real password") is True
    assert verify_password(stored, "a real passwore") is False


def test_the_same_password_hashes_differently_each_time() -> None:
    assert hash_password("same") != hash_password("same")


def test_session_round_trip(settings_env: Path) -> None:
    user = User(id=7, email="a@b.c", password_hash="x")
    assert read_session(issue_session(user)) == 7


def test_a_session_signed_with_another_key_is_refused(settings_env: Path) -> None:
    user = User(id=7, email="a@b.c", password_hash="x")
    forged = issue_session(user, Settings(secret_key="a-different-key"))
    assert read_session(forged) is None


def test_rubbish_session_tokens_are_refused(settings_env: Path) -> None:
    assert read_session("not-a-token") is None
    assert read_session("") is None


@pytest.mark.parametrize(
    ("email", "expected"), [("Someone@Zaco.co.za", True), ("someone@gmail.com", False)]
)
def test_the_domain_rule_gates_who_may_be_invited(email: str, expected: bool) -> None:
    settings = Settings(allowed_email_domains=["zaco.co.za"])
    assert domain_allowed(email, settings) is expected


def test_no_domain_rule_means_no_restriction() -> None:
    assert domain_allowed("anyone@anywhere.com", Settings(allowed_email_domains=[])) is True


def test_emails_are_compared_case_insensitively() -> None:
    assert normalise_email("  Someone@Zaco.CO.ZA ") == "someone@zaco.co.za"
