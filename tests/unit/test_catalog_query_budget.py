"""Large catalog pages must not issue one remote skill query per posting."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.infrastructure.database.auth_repository import AuthRepository
from app.infrastructure.database.connection import Connection
from app.infrastructure.database.job_repository import JobRepository


class CatalogQueryBudgetTests(unittest.TestCase):
    def test_six_hundred_jobs_keep_skill_order_with_bounded_queries(self):
        with TemporaryDirectory() as folder:
            database = Path(folder) / "catalog.sqlite3"
            AuthRepository(database)
            repository = JobRepository(database)
            postings = [
                {
                    "id": f"example-{index:03d}",
                    "company": "가상 테스트 회사",
                    "role": "개발자",
                    "location": "서울",
                    "employment_type": "정규직",
                    "experience_level": "무관",
                    "description": "담당업무\nPython 서비스 개발",
                    "source_url": "",
                    "created_at": "2026-10-06",
                    "skills": ["Python", "SQL"] if index % 2 else [],
                }
                for index in range(600)
            ]
            repository.seed(postings)
            statements = []
            execute = Connection.execute

            def traced(connection, sql, parameters=()):
                statements.append(sql)
                return execute(connection, sql, parameters)

            with patch.object(Connection, "execute", traced):
                result = repository.list(
                    {
                        "q": "",
                        "location": "",
                        "employment_type": "",
                        "experience_level": "",
                        "skill": "",
                        "saved": False,
                        "page": 1,
                        "page_size": 600,
                    }
                )
            self.assertEqual(result["total"], 600)
            expected = {posting["id"]: posting["skills"] for posting in postings}
            self.assertEqual({item["id"]: item["skills"] for item in result["items"]}, expected)
            skill_queries = [sql for sql in statements if "FROM job_posting_skills WHERE" in sql]
            self.assertLessEqual(len(skill_queries), 2)
            self.assertLessEqual(len(statements), 10)


if __name__ == "__main__":
    unittest.main()
