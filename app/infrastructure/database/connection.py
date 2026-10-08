"""Small DB-API boundary for teammate-owned SQLite or PostgreSQL databases."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


class Connection:
    def __init__(self, raw, postgres):
        self.raw, self.postgres = raw, postgres

    def execute(self, sql, parameters=()):
        # All SQL here is application-owned; values always remain parameters.
        return self.raw.execute(sql.replace("?", "%s") if self.postgres else sql, parameters)

    def executescript(self, sql):
        for statement in sql.split(";"):
            if statement.strip():
                self.execute(statement)


class Database:
    def __init__(self, location):
        self.location = str(location)
        self.postgres = self.location.startswith(("postgresql://", "postgres://"))
        if self.postgres:
            import psycopg

            self.integrity_error = psycopg.IntegrityError
            with self.connection(initialize=True) as db:
                db.execute("CREATE SCHEMA IF NOT EXISTS careerlens")
        else:
            self.integrity_error = sqlite3.IntegrityError
            Path(self.location).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self, immediate=False, initialize=False):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row

            url = urlsplit(self.location)
            options = dict(connect_timeout=10, prepare_threshold=None, row_factory=dict_row)
            if url.hostname not in ("localhost", "127.0.0.1", "::1") and "sslmode" not in parse_qs(
                url.query
            ):
                options["sslmode"] = "require"
            try:
                raw = psycopg.connect(self.location, **options)
            except psycopg.OperationalError:
                raise RuntimeError(
                    "Cannot connect to DATABASE_URL. Check your database connection and credentials."
                ) from None
        else:
            raw = sqlite3.connect(self.location, timeout=10)
            raw.row_factory = sqlite3.Row
        try:
            if self.postgres:
                if not initialize:
                    raw.execute("SET search_path TO careerlens")
            else:
                raw.execute("PRAGMA foreign_keys=ON")
                if immediate:
                    raw.execute("BEGIN IMMEDIATE")
            yield Connection(raw, self.postgres)
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()
