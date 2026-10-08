"""Per-user workspaces stored in the teammate's configured database."""

import json

from app.infrastructure.database.connection import Database
from app.modules.analysis.workspace import empty_draft


class DraftRepository:
    def __init__(self, database):
        self.storage = Database(database)
        with self.storage.connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS workspaces (user_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    def load(self, user_id):
        with self.storage.connection() as db:
            row = db.execute(
                "SELECT payload FROM workspaces WHERE user_id=?", (user_id,)
            ).fetchone()
        return {**empty_draft(), **json.loads(row["payload"])} if row else empty_draft()

    def save(self, user_id, draft):
        with self.storage.connection() as db:
            db.execute(
                "INSERT INTO workspaces(user_id,payload) VALUES(?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload",
                (user_id, json.dumps(draft, ensure_ascii=False)),
            )

    def delete(self, user_id):
        with self.storage.connection() as db:
            db.execute("DELETE FROM workspaces WHERE user_id=?", (user_id,))

    def save_if_unchanged(self, user_id, draft, expected):
        """Do not overwrite edits or deletion made while analysis was running."""
        with self.storage.connection() as db:
            row = db.execute(
                "SELECT payload FROM workspaces WHERE user_id=?", (user_id,)
            ).fetchone()
            if not row or {**empty_draft(), **json.loads(row["payload"])} != expected:
                return False
            result = db.execute(
                "UPDATE workspaces SET payload=? WHERE user_id=? AND payload=?",
                (json.dumps(draft, ensure_ascii=False), user_id, row["payload"]),
            )
            return result.rowcount == 1


# Retained for the original application's import; both databases are supported.
SqliteDraftRepository = DraftRepository
