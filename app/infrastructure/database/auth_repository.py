"""Authentication storage in the database configured by each teammate."""

import time
from app.infrastructure.database.connection import Database

MAX_RATE_WINDOW = 30 * 60


class AuthRepository:
    def __init__(self, database):
        self.database = str(database)
        self.storage = Database(database)
        with self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS auth_users (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL, password_hash TEXT, created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    digest TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES auth_users(id),
                    expires_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS auth_sessions_user ON auth_sessions(user_id);
                CREATE TABLE IF NOT EXISTS auth_password_resets (
                    digest TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES auth_users(id),
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_oauth_accounts (
                    provider TEXT NOT NULL, subject TEXT NOT NULL,
                    user_id TEXT NOT NULL REFERENCES auth_users(id),
                    PRIMARY KEY(provider, subject)
                );
                CREATE TABLE IF NOT EXISTS auth_rate_limits (
                    bucket TEXT PRIMARY KEY, started_at INTEGER NOT NULL, count INTEGER NOT NULL
                );
            """
            )

    def connection(self, immediate=False):
        return self.storage.connection(immediate=immediate)

    def create_user(self, user):
        try:
            with self.connection() as db:
                db.execute(
                    "INSERT INTO auth_users VALUES(?,?,?,?,?)",
                    (
                        user["id"],
                        user["email"],
                        user["name"],
                        user["password_hash"],
                        int(time.time()),
                    ),
                )
            return True
        except self.storage.integrity_error:
            return False

    def user_by_email(self, email):
        with self.connection() as db:
            row = db.execute("SELECT * FROM auth_users WHERE email=?", (email,)).fetchone()
            return dict(row) if row else None

    def create_session(self, digest, user_id, expires):
        with self.connection() as db:
            db.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (int(time.time()),))
            db.execute("INSERT INTO auth_sessions VALUES(?,?,?)", (digest, user_id, expires))

    def session_user(self, digest, now):
        with self.connection() as db:
            row = db.execute(
                "SELECT u.* FROM auth_users u JOIN auth_sessions s ON s.user_id=u.id WHERE s.digest=? AND s.expires_at>?",
                (digest, now),
            ).fetchone()
            return dict(row) if row else None

    def revoke_session(self, digest):
        with self.connection() as db:
            db.execute("DELETE FROM auth_sessions WHERE digest=?", (digest,))

    def create_reset(self, digest, user_id, expires):
        with self.connection(immediate=True) as db:
            if self.storage.postgres:
                db.execute("SELECT id FROM auth_users WHERE id=? FOR UPDATE", (user_id,)).fetchone()
            db.execute(
                "DELETE FROM auth_password_resets WHERE user_id=? OR expires_at<=?",
                (user_id, int(time.time())),
            )
            db.execute("INSERT INTO auth_password_resets VALUES(?,?,?)", (digest, user_id, expires))

    def consume_reset(self, digest, password_hash, now):
        with self.connection(immediate=True) as db:
            # SQLite write lock / PostgreSQL row lock keeps tokens single-use.
            lock = " FOR UPDATE" if self.storage.postgres else ""
            if self.storage.postgres:
                candidate = db.execute(
                    "SELECT user_id FROM auth_password_resets WHERE digest=? AND expires_at>?",
                    (digest, now),
                ).fetchone()
                if not candidate:
                    return False
                # Match create_reset's lock order, then re-check the token.
                db.execute(
                    "SELECT id FROM auth_users WHERE id=? FOR UPDATE", (candidate["user_id"],)
                ).fetchone()
            row = db.execute(
                "SELECT user_id FROM auth_password_resets WHERE digest=? AND expires_at>?" + lock,
                (digest, now),
            ).fetchone()
            if not row:
                return False
            user_id = row["user_id"]
            db.execute("UPDATE auth_users SET password_hash=? WHERE id=?", (password_hash, user_id))
            db.execute("DELETE FROM auth_password_resets WHERE user_id=?", (user_id,))
            db.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
            return True

    def oauth_user(self, provider, subject):
        with self.connection() as db:
            row = db.execute(
                "SELECT u.* FROM auth_users u JOIN auth_oauth_accounts o ON o.user_id=u.id WHERE o.provider=? AND o.subject=?",
                (provider, subject),
            ).fetchone()
            return dict(row) if row else None

    def create_oauth_user(self, user, provider, subject):
        try:
            with self.connection() as db:
                db.execute(
                    "INSERT INTO auth_users VALUES(?,?,?,?,?)",
                    (user["id"], user["email"], user["name"], None, int(time.time())),
                )
                db.execute(
                    "INSERT INTO auth_oauth_accounts VALUES(?,?,?)", (provider, subject, user["id"])
                )
            return True
        except self.storage.integrity_error:
            return False

    def allow_attempt(self, bucket, limit=30, window=600):
        if not 1 <= window <= MAX_RATE_WINDOW:
            raise ValueError("Unsupported rate-limit window")
        now = int(time.time())
        with self.connection(immediate=True) as db:
            # Auth and guest buckets have different windows. A short auth
            # request must never reset a still-active guest allowance.
            db.execute(
                "DELETE FROM auth_rate_limits WHERE started_at<=?", (now - MAX_RATE_WINDOW,)
            )
            db.execute(
                "DELETE FROM auth_rate_limits WHERE bucket=? AND started_at<=?",
                (bucket, now - window),
            )
            db.execute(
                "INSERT INTO auth_rate_limits VALUES(?,?,1) ON CONFLICT(bucket) DO UPDATE SET count=auth_rate_limits.count+1",
                (bucket, now),
            )
            return (
                db.execute(
                    "SELECT count FROM auth_rate_limits WHERE bucket=?", (bucket,)
                ).fetchone()["count"]
                <= limit
            )
