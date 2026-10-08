"""Persist only bundled, fictional resume examples on SQLite/PostgreSQL.

Uploaded resumes belong to workspace drafts and never enter this catalog.
Seeding inserts missing IDs and leaves existing rows unchanged.
An explicit packaged refresh upgrades the known fictional fixture IDs only.
"""

import json

from app.infrastructure.database.connection import Database

PACKAGED_IDS = {
    *(f"resume-{index:02d}" for index in range(1, 21)),
    *(f"synthetic-resume-{index:03d}" for index in range(1, 201)),
}
PACK_NAME = "career-resumes-v2"
PACK_VERSION = 2


class ResumeExampleRepository:
    def __init__(self, database):
        self.storage = Database(database)
        with self.storage.connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS resume_examples ("
                "id TEXT PRIMARY KEY, "
                "source_type TEXT NOT NULL CHECK(source_type='synthetic'), "
                "payload_json TEXT NOT NULL)"
            )

    def seed(self, examples):
        """Add fixture rows idempotently without replacing stored examples."""
        inserted = 0
        with self.storage.connection() as db:
            for example in examples:
                if example.get("source_type") != "synthetic":
                    raise ValueError("예시 저장소에는 가상 이력서만 넣을 수 있습니다.")
                if not example.get("id") or not example.get("resume_text", "").strip():
                    raise ValueError("가상 이력서의 ID와 본문을 확인해 주세요.")
                inserted += db.execute(
                    "INSERT INTO resume_examples(id,source_type,payload_json) "
                    "VALUES(?,?,?) ON CONFLICT(id) DO NOTHING",
                    (
                        example["id"],
                        "synthetic",
                        json.dumps(example, ensure_ascii=False),
                    ),
                ).rowcount
        return inserted

    def list(self):
        with self.storage.connection() as db:
            rows = db.execute("SELECT payload_json FROM resume_examples ORDER BY id").fetchall()
        examples = [json.loads(row["payload_json"]) for row in rows]
        return [
            {
                key: value
                for key, value in item.items()
                if key not in {"resume_text", "resume_sections"}
            }
            for item in examples
        ]

    def refresh_packaged(self, examples):
        """Refresh this versioned fixture pack without replacing other rows.

        Normal ``seed`` remains insert-only. Only the explicitly known 220
        bundled IDs with matching pack metadata can use this upgrade path.
        User workspace uploads are stored elsewhere and never read here.
        """
        changed = {"inserted": 0, "updated": 0}
        with self.storage.connection() as db:
            for example in examples:
                if (
                    example.get("id") not in PACKAGED_IDS
                    or example.get("source_type") != "synthetic"
                    or example.get("fixture_pack") != PACK_NAME
                    or example.get("fixture_version") != PACK_VERSION
                    or not example.get("resume_text", "").strip()
                ):
                    raise ValueError(
                        "갱신 대상은 버전이 확인된 기본 가상 이력서 220개로 제한됩니다."
                    )
                payload = json.dumps(example, ensure_ascii=False)
                inserted = db.execute(
                    "INSERT INTO resume_examples(id,source_type,payload_json) "
                    "VALUES(?,?,?) ON CONFLICT(id) DO NOTHING",
                    (example["id"], "synthetic", payload),
                ).rowcount
                changed["inserted"] += inserted
                if not inserted:
                    changed["updated"] += db.execute(
                        "UPDATE resume_examples SET payload_json=? "
                        "WHERE id=? AND source_type='synthetic' AND payload_json<>?",
                        (payload, example["id"], payload),
                    ).rowcount
        return changed

    def get(self, example_id):
        with self.storage.connection() as db:
            row = db.execute(
                "SELECT payload_json FROM resume_examples WHERE id=?",
                (example_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None
