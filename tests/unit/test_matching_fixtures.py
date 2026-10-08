"""Fixture coverage and idempotent DB behavior for the matching demonstration."""

import json
from pathlib import Path
import tempfile
import unittest

from app.application.resume_examples import load_examples
from app.infrastructure.database.resume_example_repository import ResumeExampleRepository
from app.integrations.document_parsers.resume import extract_resume
from app.modules.job_postings.catalog import validate_posting
from app.modules.job_postings.requirements import _requirements


EXAMPLES = Path(__file__).resolve().parents[2] / "data" / "examples"


class MatchingFixtureTests(unittest.TestCase):
    def test_job_catalog_has_30_distinct_valid_orchestration_examples(self):
        jobs = json.loads(
            (EXAMPLES / "orchestration_job_postings.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(jobs), 30)
        self.assertEqual(len({job["id"] for job in jobs}), 30)
        self.assertEqual(len({job["description"] for job in jobs}), 30)
        for job in jobs:
            with self.subTest(job=job["id"]):
                validate_posting(job)
                self.assertTrue(job["synthetic"])
                self.assertIn("AI 오케스트레이션", job["skills"])
                self.assertGreaterEqual(len(_requirements(job["description"])), 3)
                self.assertTrue(33 <= job["latitude"] <= 39)
                self.assertTrue(124 <= job["longitude"] <= 132)

    def test_200_new_resumes_preserve_old_20_and_cover_multiple_roles(self):
        items = load_examples()
        self.assertEqual(len(items), 220)
        self.assertEqual(len({item["id"] for item in items}), 220)
        additions = [item for item in items if item["id"].startswith("synthetic-resume-")]
        self.assertEqual(len(additions), 200)
        self.assertEqual(len({item["resume_text"] for item in additions}), 200)
        self.assertEqual(len({item["role"] for item in additions}), 20)
        self.assertEqual(sum("AI 오케스트레이션" in item["role"] for item in additions), 10)
        for item in additions:
            self.assertGreaterEqual(len(item["resume_text"]), 2200)
            self.assertEqual(item["source_type"], "synthetic")
            self.assertEqual(item["fixture_version"], 2)
            self.assertTrue(
                {"자기소개와 지원동기", "강점과 협업 사례", "보완할 점과 개선 노력"}.issubset(
                    section["title"] for section in item["resume_sections"]
                )
            )

    def test_desktop_resumes_are_separate_and_parse_as_uploads(self):
        desktop = json.loads((EXAMPLES / "desktop_ai_resumes.json").read_text(encoding="utf-8"))[
            "items"
        ]
        catalog_ids = {item["id"] for item in load_examples()}
        self.assertEqual(len(desktop), 40)
        self.assertFalse(catalog_ids.intersection(item["id"] for item in desktop))
        self.assertGreaterEqual(len({tuple(item["skills"]) for item in desktop}), 30)
        self.assertEqual(
            [item["id"] for item in desktop[:10]],
            [f"desktop-ai-{index:02d}" for index in range(1, 11)],
        )
        for item in desktop:
            extracted = extract_resume("resume.txt", item["resume_text"].encode("utf-8-sig"))
            self.assertEqual(extracted, item["resume_text"])
            self.assertGreaterEqual(len(extracted), 2200)

    def test_db_seeding_is_idempotent_and_survives_reopening(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "fixture.sqlite3"
            repository = ResumeExampleRepository(database)
            fixtures = load_examples()
            self.assertEqual(repository.seed(fixtures[:20]), 20)
            self.assertEqual(repository.seed(fixtures), 200)
            self.assertEqual(repository.seed(fixtures), 0)
            changed = {**fixtures[0], "resume_text": "This must not overwrite the stored example."}
            repository.seed([changed])
            reopened = ResumeExampleRepository(database)
            self.assertEqual(reopened.get(fixtures[0]["id"]), fixtures[0])
            self.assertEqual(len(reopened.list()), 220)
            self.assertTrue(all("resume_text" not in row for row in reopened.list()))
            self.assertTrue(all("resume_sections" not in row for row in reopened.list()))
            self.assertIsNone(reopened.get("nonexistent"))

    def test_explicit_packaged_refresh_updates_only_known_fixture_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "fixture.sqlite3"
            repository = ResumeExampleRepository(database)
            fixtures = load_examples()
            old = {
                **fixtures[0],
                "resume_text": "Earlier short fictional draft",
                "fixture_version": 1,
            }
            unrelated = {
                **fixtures[1],
                "id": "custom-synthetic-example",
                "resume_text": "Preserve this unrelated example",
            }
            repository.seed([old, unrelated])
            self.assertEqual(repository.refresh_packaged(fixtures), {"inserted": 219, "updated": 1})
            self.assertEqual(repository.refresh_packaged(fixtures), {"inserted": 0, "updated": 0})
            reopened = ResumeExampleRepository(database)
            self.assertEqual(reopened.get(fixtures[0]["id"]), fixtures[0])
            self.assertEqual(reopened.get(unrelated["id"]), unrelated)
            with self.assertRaises(ValueError):
                repository.refresh_packaged([unrelated])
            with self.assertRaises(ValueError):
                repository.refresh_packaged([{**fixtures[0], "source_type": "uploaded"}])
            self.assertEqual(reopened.get(unrelated["id"]), unrelated)

    def test_same_role_variants_have_different_introductions_and_strengths(self):
        additions = [item for item in load_examples() if item["id"].startswith("synthetic-resume-")]
        for start in range(0, 200, 10):
            family = additions[start : start + 10]
            for title in ("자기소개와 지원동기", "강점과 협업 사례"):
                contents = {
                    tuple(block["paragraphs"])
                    for item in family
                    for block in item["resume_sections"]
                    if block["title"] == title
                }
                self.assertEqual(len(contents), 10)

    def test_repository_rejects_uploaded_resume_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = ResumeExampleRepository(Path(folder) / "fixture.sqlite3")
            with self.assertRaises(ValueError):
                repository.seed(
                    [{"id": "private", "source_type": "uploaded", "resume_text": "private"}]
                )
            self.assertEqual(repository.list(), [])


if __name__ == "__main__":
    unittest.main()
