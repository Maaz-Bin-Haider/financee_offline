"""Turn database errors into messages that are safe to show a user.

The tenant stored procedures raise curated messages with RAISE EXCEPTION
(SQLSTATE P0001), written for end users. Any other database error -- a
connection problem, a constraint violation, a programming error -- falls back
to the caller's generic message so internal detail never reaches the browser.
"""


def user_db_error(exc, fallback="Something went wrong. Please try again."):
    """Return the user-facing message for a database exception.

    Django wraps the psycopg2 error, so the original is usually on
    ``__cause__``. A plpgsql RAISE EXCEPTION arrives with pgcode P0001 and its
    text in ``diag.message_primary``.
    """
    for candidate in (getattr(exc, "__cause__", None), exc):
        if candidate is None:
            continue
        pgcode = getattr(candidate, "pgcode", None)
        diag = getattr(candidate, "diag", None)
        message = getattr(diag, "message_primary", None) if diag else None
        if pgcode == "P0001" and message:
            return message.strip()
    return fallback
