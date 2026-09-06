"""The way back in when every administrator has forgotten their password.

    docker compose exec app python -m zaco.recover you@example.com

Prints a one-time link that sets a new password, valid for four hours.

## Why this is safe, and why nothing weaker would do

Every other route back into an account needs somebody who is already in one: you know your own
password, or an administrator issues you a link. Both dead-end in the same place -- if every
administrator has forgotten, there is nobody left with the standing to help, and until this
existed there was no path at all. The first account is seeded only on an empty database and an
existing password is never reset, so the system was one forgotten password away from being
unopenable with the operator's own live workbook inside it.

The standing this command asks for instead is **possession of the server**. Whoever can run it
already has the database it reads and the workbook file the whole system exists to write, so it
hands them nothing they did not already have. That is the entire argument: a break-glass path is
only sound when the glass is harder to reach than what is behind it.

It follows that this must never be reachable over HTTP, and it is not -- there is no endpoint,
and nothing imports this module. It prints a link rather than setting a password directly so that
the new password is typed by the person who will use it and is never in a shell history or a
terminal scrollback.

The account it opens is written into that account's own trail, attributed to the recovery
command rather than to a person, because nobody's account was used.
"""

from __future__ import annotations

import argparse
import sys

from zaco.auth.service import RESET_PATH, get_user_by_email, issue_reset
from zaco.db.base import get_session_factory

VIA = "the recovery command, run on the server"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m zaco.recover",
        description=(
            "Print a one-time link that lets an account set a new password. For the case where "
            "no administrator can sign in to issue one."
        ),
    )
    parser.add_argument("email", help="the account to let back in")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="where the app is reachable, so the printed link can be opened (default: %(default)s)",
    )
    parser.add_argument(
        "--reason",
        default="",
        help="written into the account trail beside the link",
    )
    args = parser.parse_args(argv)

    session = get_session_factory()()
    try:
        user = get_user_by_email(session, args.email)
        if user is None:
            # Named plainly. The reason `/api/auth/forgot` refuses to say this is that it answers
            # anybody on the internet; this answers somebody holding the database, who could read
            # the users table in the next command.
            print(f"No account for {args.email}.", file=sys.stderr)
            return 1
        if not user.is_active:
            print(
                f"{user.email} is turned off, and a link would be refused when it was used. "
                "Turn the account back on first.",
                file=sys.stderr,
            )
            return 1

        reset = issue_reset(session, user, issued_by=None, via=VIA, reason=args.reason)
        session.commit()
        assert reset.expires_at is not None

        base = args.base_url.rstrip("/")
        print(
            f"Give this to {user.email}. It works once, and expires at "
            f"{reset.expires_at:%Y-%m-%d %H:%M} UTC:"
        )
        print()
        print(f"    {base}{RESET_PATH}/{reset.token}")
        print()
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
