"""The 600-posting catalog must contain substantive occupational variation."""

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
import unittest

from app.modules.job_postings.catalog import validate_posting
from app.modules.job_postings.requirements import _requirements


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "data" / "examples"
sys.path.insert(0, str(ROOT / "scripts"))
from expand_job_catalog import enrich_original, new_postings  # noqa: E402


class ExpandedJobCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {}
        for filename in (
            "job_postings.json",
            "orchestration_job_postings.json",
            "expanded_job_postings.json",
        ):
            cls.files[filename] = json.loads((EXAMPLES / filename).read_text(encoding="utf-8"))
        cls.jobs = [posting for postings in cls.files.values() for posting in postings]
        cls.manifest = json.loads(
            (EXAMPLES / "expanded_jobs_manifest.json").read_text(encoding="utf-8")
        )

    def test_exact_count_preserved_identifiers_and_authoring_manifest(self):
        self.assertEqual(len(self.jobs), 600)
        self.assertEqual(len({posting["id"] for posting in self.jobs}), 600)
        self.assertEqual([len(items) for items in self.files.values()], [30, 30, 540])
        original_ids = {posting["id"] for posting in self.files["job_postings.json"]}
        self.assertIn("example-backend-python", original_ids)
        self.assertIn("example-recommendation-po", original_ids)
        self.assertEqual(
            {posting["id"] for posting in self.files["orchestration_job_postings.json"]},
            {f"orchestration-{number:03d}" for number in range(1, 31)},
        )
        for filename, expected in self.manifest["files"].items():
            self.assertEqual(
                hashlib.sha256((EXAMPLES / filename).read_bytes()).hexdigest(), expected
            )

    def test_detailed_descriptions_valid_payloads_and_multiple_sectors(self):
        self.assertEqual(len({posting["description"] for posting in self.jobs}), 600)
        sectors = Counter(posting["sector"] for posting in self.jobs)
        self.assertEqual(len(sectors), 18)
        self.assertTrue(all(count >= 30 for count in sectors.values()))
        for posting in self.jobs:
            with self.subTest(posting=posting["id"]):
                self.assertGreaterEqual(len(posting["description"]), 900)
                self.assertLessEqual(len(posting["description"]), 1800)
                self.assertEqual(validate_posting(posting)["description"], posting["description"])
                for section in (
                    "자격요건",
                    "우대사항",
                    "근무조건",
                    "급여",
                    "복리후생",
                    "전형절차",
                    "지원방법",
                ):
                    self.assertIn("\n\n" + section + "\n", posting["description"])
                self.assertIn("가상 채용공고", posting["description"])

    def test_variants_change_work_content_and_not_just_names(self):
        groups = defaultdict(list)
        for posting in self.files["expanded_job_postings.json"]:
            groups[posting["role_archetype"]].append(posting)
        self.assertEqual(len(groups), 54)
        for role, postings in groups.items():
            with self.subTest(role=role):
                self.assertEqual(len(postings), 10)
                self.assertEqual(len({tuple(posting["scenario"]) for posting in postings}), 10)
                extracted = {
                    tuple(item["text"] for item in _requirements(posting["description"]))
                    for posting in postings
                }
                self.assertEqual(len(extracted), 10)

    def test_company_pay_and_benefits_are_not_scored_requirements(self):
        for posting in self.jobs:
            requirements = _requirements(posting["description"])
            self.assertGreaterEqual(len(requirements), 4, posting["id"])
            self.assertLessEqual(len(requirements), 12, posting["id"])
            for item in requirements:
                self.assertFalse(
                    any(
                        word in item["text"]
                        for word in ("연봉 ", "시급 ", "가상 채용공고", "실제 지원서 접수")
                    ),
                    posting["id"],
                )
            salary = posting["description"].split("\n\n급여\n", 1)[1].split("\n\n", 1)[0]
            self.assertIn("가상 범위", salary)
            self.assertIn("시급" if posting["employment_type"] == "파트타임" else "연봉", salary)

    def test_regeneration_is_deterministic_for_original_and_new_jobs(self):
        self.assertEqual(new_postings(), self.files["expanded_job_postings.json"])
        for offset, filename in ((0, "job_postings.json"), (30, "orchestration_job_postings.json")):
            regenerated = [
                enrich_original(posting, offset + index)
                for index, posting in enumerate(self.files[filename])
            ]
            self.assertEqual(regenerated, self.files[filename])


if __name__ == "__main__":
    unittest.main()
