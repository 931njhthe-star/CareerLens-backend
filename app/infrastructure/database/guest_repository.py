"""Short-lived guest drafts; only creation may insert, never a late analysis write."""

import json
import logging
import threading
from time import time
import weakref

from app.infrastructure.database.connection import Database
from app.modules.analysis.workspace import empty_draft

RETENTION_SECONDS = 30 * 60


class GuestRepository:
    def __init__(self, database):
        self.storage = Database(database)
        with self.storage.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS guest_workspaces (
                    guest_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    expires_at INTEGER NOT NULL, revision INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS guest_workspaces_expiry
                    ON guest_workspaces(expires_at);
                """
            )
        self.cleanup()

    def cleanup(self):
        with self.storage.connection() as db:
            result = db.execute(
                "DELETE FROM guest_workspaces WHERE expires_at<=?", (int(time()),)
            )
            return result.rowcount

    def create(self, guest_id, draft):
        expires_at = int(time()) + RETENTION_SECONDS
        with self.storage.connection() as db:
            db.execute(
                "INSERT INTO guest_workspaces VALUES(?,?,?,0)",
                (guest_id, json.dumps(draft, ensure_ascii=False), expires_at),
            )
        return {"draft": draft, "expires_at": expires_at, "revision": 0}

    def load(self, guest_id):
        self.cleanup()
        with self.storage.connection() as db:
            row = db.execute(
                "SELECT payload,expires_at,revision FROM guest_workspaces "
                "WHERE guest_id=? AND expires_at>?",
                (guest_id, int(time())),
            ).fetchone()
        if row:
            return {
                "draft": {**empty_draft(), **json.loads(row["payload"])},
                "expires_at": row["expires_at"],
                "revision": row["revision"],
            }
        return None

    def replace(self, guest_id, draft, revision):
        with self.storage.connection() as db:
            result = db.execute(
                "UPDATE guest_workspaces SET payload=?,revision=revision+1 "
                "WHERE guest_id=? AND revision=? AND expires_at>?",
                (json.dumps(draft, ensure_ascii=False), guest_id, revision, int(time())),
            )
        return result.rowcount == 1

    def delete(self, guest_id):
        with self.storage.connection() as db:
            db.execute("DELETE FROM guest_workspaces WHERE guest_id=?", (guest_id,))

    def claim(self, guest_id, user_id):
        """The report transfer and temporary deletion commit together, once only."""
        with self.storage.connection(immediate=True) as db:
            lock = " FOR UPDATE" if self.storage.postgres else ""
            row = db.execute(
                "SELECT payload,expires_at FROM guest_workspaces WHERE guest_id=?" + lock,
                (guest_id,),
            ).fetchone()
            if not row:
                return "expired"
            if row["expires_at"] <= int(time()):
                db.execute("DELETE FROM guest_workspaces WHERE guest_id=?", (guest_id,))
                return "expired"
            draft = json.loads(row["payload"])
            if not isinstance(draft.get("report"), dict):
                return "incomplete"
            db.execute(
                "INSERT INTO workspaces(user_id,payload) VALUES(?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload",
                (user_id, row["payload"]),
            )
            db.execute("DELETE FROM guest_workspaces WHERE guest_id=?", (guest_id,))
            return "claimed"


class GuestCleanup:
    """Every serving process reaps expired rows even when all browsers are closed."""

    def __init__(self, repository, interval=30):
        self.stop_event = threading.Event()
        reference = weakref.ref(repository)
        stopped = self.stop_event

        def run():
            while not stopped.wait(interval):
                current = reference()
                if current is None:
                    break
                try:
                    current.cleanup()
                except Exception:
                    # Never include DB URLs, SQL values or document content in logs.
                    logging.getLogger(__name__).warning("Guest retention cleanup failed")
                finally:
                    del current

        self.thread = threading.Thread(target=run, name="guest-retention", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)
