"""PostgreSQL backend preserving real instants under a local session timezone.

Django's default psycopg2 factory assumes the connection timezone is fixed in
settings. Requests choose the installation timezone so SQL CURRENT_DATE follows
the local business day. Decode the offset PostgreSQL actually returns instead;
this also distinguishes repeated wall times across a DST transition.
"""
from datetime import timedelta, timezone
from django.db.backends.postgresql.base import DatabaseWrapper as PostgreSQLWrapper


class DatabaseWrapper(PostgreSQLWrapper):
    def tzinfo_factory(self, offset):
        if not isinstance(offset, timedelta):
            offset = timedelta(minutes=offset)
        return timezone(offset)
