"""Private manual postings and per-account bookmarks on SQLite/PostgreSQL."""

from app.infrastructure.database.connection import Database


class JobRepository:
    def __init__(self, database):
        self.storage = Database(database)
        with self.storage.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS job_postings (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT REFERENCES auth_users(id) ON DELETE CASCADE,
                    company TEXT NOT NULL, role TEXT NOT NULL, location TEXT NOT NULL,
                    employment_type TEXT NOT NULL, experience_level TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source_type TEXT NOT NULL CHECK(source_type IN ('example','manual')),
                    source_url TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                    CHECK((source_type='example' AND owner_id IS NULL)
                          OR (source_type='manual' AND owner_id IS NOT NULL))
                );
                CREATE INDEX IF NOT EXISTS job_postings_owner ON job_postings(owner_id);
                CREATE TABLE IF NOT EXISTS job_posting_skills (
                    posting_id TEXT NOT NULL REFERENCES job_postings(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL, skill TEXT NOT NULL,
                    PRIMARY KEY(posting_id,position), UNIQUE(posting_id,skill)
                );
                CREATE TABLE IF NOT EXISTS job_bookmarks (
                    user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                    posting_id TEXT NOT NULL REFERENCES job_postings(id) ON DELETE CASCADE,
                    PRIMARY KEY(user_id,posting_id)
                );
            """
            )

    @staticmethod
    def insert(db, posting, owner_id, source_type):
        inserted = db.execute(
            "INSERT INTO job_postings(id,owner_id,company,role,location,employment_type,experience_level,description,source_type,source_url,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
            (
                posting["id"],
                owner_id,
                posting["company"],
                posting["role"],
                posting["location"],
                posting["employment_type"],
                posting["experience_level"],
                posting["description"],
                source_type,
                posting["source_url"],
                posting["created_at"],
            ),
        ).rowcount
        if inserted:
            JobRepository.write_skills(db, posting["id"], posting["skills"])
        return inserted

    @staticmethod
    def write_skills(db, posting_id, skills):
        db.execute("DELETE FROM job_posting_skills WHERE posting_id=?", (posting_id,))
        for position, skill in enumerate(skills):
            db.execute(
                "INSERT INTO job_posting_skills VALUES(?,?,?)", (posting_id, position, skill)
            )

    def seed(self, postings):
        with self.storage.connection() as db:
            for posting in postings:
                if self.insert(db, posting, None, "example"):
                    continue
                # Refresh editable bundled examples without deleting bookmarks
                # or overwriting any user-owned manual posting.
                refreshed = db.execute(
                    "UPDATE job_postings SET company=?,role=?,location=?,employment_type=?,experience_level=?,description=?,source_url=?,created_at=? "
                    "WHERE id=? AND owner_id IS NULL AND source_type='example'",
                    tuple(
                        posting[field]
                        for field in (
                            "company",
                            "role",
                            "location",
                            "employment_type",
                            "experience_level",
                            "description",
                            "source_url",
                            "created_at",
                        )
                    )
                    + (posting["id"],),
                ).rowcount
                if refreshed:
                    self.write_skills(db, posting["id"], posting["skills"])

    @staticmethod
    def public_row(db, row, user_id, skills=None):
        posting = dict(row)
        owner_id = posting.pop("owner_id")
        posting["is_owner"] = bool(user_id and owner_id == user_id)
        posting["is_saved"] = bool(posting.pop("saved"))
        posting["skills"] = (
            skills
            if skills is not None
            else [
                item["skill"]
                for item in db.execute(
                    "SELECT skill FROM job_posting_skills WHERE posting_id=? ORDER BY position",
                    (posting["id"],),
                ).fetchall()
            ]
        )
        return posting

    @staticmethod
    def skills_for_postings(db, posting_ids):
        """Read a catalog page in bounded batches, including remote databases."""
        skills = {posting_id: [] for posting_id in posting_ids}
        # Stay below SQLite's older parameter limit; every ID is parameterized.
        for offset in range(0, len(posting_ids), 500):
            batch = posting_ids[offset : offset + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = db.execute(
                "SELECT posting_id,skill FROM job_posting_skills "
                f"WHERE posting_id IN ({placeholders}) ORDER BY posting_id,position",
                batch,
            ).fetchall()
            for row in rows:
                skills[row["posting_id"]].append(row["skill"])
        return skills

    @staticmethod
    def select_sql():
        return (
            "SELECT p.*, EXISTS(SELECT 1 FROM job_bookmarks b "
            "WHERE b.posting_id=p.id AND b.user_id=?) AS saved FROM job_postings p "
        )

    def get(self, posting_id, user_id=None):
        with self.storage.connection() as db:
            row = db.execute(
                self.select_sql() + "WHERE p.id=? AND (p.owner_id IS NULL OR p.owner_id=?)",
                (user_id, posting_id, user_id),
            ).fetchone()
            return self.public_row(db, row, user_id) if row else None

    def list(self, filters, user_id=None):
        clauses, parameters = ["(p.owner_id IS NULL OR p.owner_id=?)"], [user_id]
        if filters.get("role_terms"):
            terms = filters["role_terms"]
            clauses.append(
                "(" + " OR ".join("LOWER(p.role) LIKE ? ESCAPE '!'" for _ in terms) + ")"
            )
            parameters.extend(
                "%" + term.lower().replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
                for term in terms
            )
        for field in ("location", "employment_type", "experience_level"):
            if filters[field]:
                clauses.append(f"p.{field}=?")
                parameters.append(filters[field])
        if filters["skill"]:
            clauses.append(
                "EXISTS(SELECT 1 FROM job_posting_skills s WHERE s.posting_id=p.id AND LOWER(s.skill)=LOWER(?))"
            )
            parameters.append(filters["skill"])
        if filters["q"]:
            pattern = (
                "%"
                + filters["q"].lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
                + "%"
            )
            clauses.append(
                "(LOWER(p.company) LIKE ? ESCAPE '!' OR LOWER(p.role) LIKE ? ESCAPE '!' "
                "OR LOWER(p.description) LIKE ? ESCAPE '!' OR EXISTS(SELECT 1 FROM job_posting_skills s "
                "WHERE s.posting_id=p.id AND LOWER(s.skill) LIKE ? ESCAPE '!'))"
            )
            parameters.extend([pattern] * 4)
        if filters["saved"]:
            clauses.append(
                "EXISTS(SELECT 1 FROM job_bookmarks b WHERE b.posting_id=p.id AND b.user_id=?)"
            )
            parameters.append(user_id)
        where = " WHERE " + " AND ".join(clauses)
        with self.storage.connection() as db:
            total = db.execute(
                "SELECT COUNT(*) AS count FROM job_postings p" + where, parameters
            ).fetchone()["count"]
            rows = db.execute(
                self.select_sql() + where + " ORDER BY p.created_at DESC,p.id LIMIT ? OFFSET ?",
                [
                    user_id,
                    *parameters,
                    filters["page_size"],
                    (filters["page"] - 1) * filters["page_size"],
                ],
            ).fetchall()
            skills = self.skills_for_postings(db, [row["id"] for row in rows])
            items = [self.public_row(db, row, user_id, skills[row["id"]]) for row in rows]
            facets = {}
            for column, key in (
                ("location", "locations"),
                ("employment_type", "employment_types"),
                ("experience_level", "experience_levels"),
            ):
                facets[key] = [
                    row["value"]
                    for row in db.execute(
                        f"SELECT DISTINCT {column} AS value FROM job_postings WHERE owner_id IS NULL OR owner_id=? ORDER BY value",
                        (user_id,),
                    ).fetchall()
                ]
            facets["skills"] = [
                row["skill"]
                for row in db.execute(
                    "SELECT DISTINCT s.skill FROM job_posting_skills s JOIN job_postings p ON p.id=s.posting_id "
                    "WHERE p.owner_id IS NULL OR p.owner_id=? ORDER BY s.skill",
                    (user_id,),
                ).fetchall()
            ]
        return {
            "items": items,
            "total": total,
            "page": filters["page"],
            "page_size": filters["page_size"],
            "filters": facets,
        }

    def create(self, posting, user_id):
        with self.storage.connection() as db:
            self.insert(db, posting, user_id, "manual")
        return self.get(posting["id"], user_id)

    def update(self, posting_id, posting, user_id):
        with self.storage.connection(immediate=True) as db:
            changed = db.execute(
                "UPDATE job_postings SET company=?,role=?,location=?,employment_type=?,experience_level=?,description=?,source_url=? "
                "WHERE id=? AND owner_id=? AND source_type='manual'",
                tuple(
                    posting[field]
                    for field in (
                        "company",
                        "role",
                        "location",
                        "employment_type",
                        "experience_level",
                        "description",
                        "source_url",
                    )
                )
                + (posting_id, user_id),
            ).rowcount
            if changed:
                self.write_skills(db, posting_id, posting["skills"])
        return self.get(posting_id, user_id) if changed else None

    def delete(self, posting_id, user_id):
        with self.storage.connection() as db:
            return bool(
                db.execute(
                    "DELETE FROM job_postings WHERE id=? AND owner_id=? AND source_type='manual'",
                    (posting_id, user_id),
                ).rowcount
            )

    def bookmark(self, posting_id, user_id, saved):
        with self.storage.connection(immediate=True) as db:
            lock = " FOR UPDATE" if self.storage.postgres else ""
            if not db.execute(
                "SELECT id FROM job_postings WHERE id=? AND (owner_id IS NULL OR owner_id=?)"
                + lock,
                (posting_id, user_id),
            ).fetchone():
                return None
            if saved:
                db.execute(
                    "INSERT INTO job_bookmarks VALUES(?,?) ON CONFLICT(user_id,posting_id) DO NOTHING",
                    (user_id, posting_id),
                )
            else:
                db.execute(
                    "DELETE FROM job_bookmarks WHERE user_id=? AND posting_id=?",
                    (user_id, posting_id),
                )
        return self.get(posting_id, user_id)
