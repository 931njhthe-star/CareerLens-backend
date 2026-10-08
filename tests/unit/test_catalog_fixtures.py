"""The synthetic demonstration data must exercise different visible matches."""

import json
from pathlib import Path
import unittest

from app.modules.analysis.matching.catalog import match_catalog


EXAMPLES = Path(__file__).resolve().parents[2] / "data" / "examples"


def read_examples(filename):
    return json.loads((EXAMPLES / filename).read_text(encoding="utf-8"))


class CatalogFixtureTests(unittest.TestCase):
    def test_desktop_resumes_have_distinct_connection_sets_and_counts(self):
        jobs = read_examples("orchestration_job_postings.json")
        resumes = read_examples("desktop_ai_resumes.json")["items"]
        results = [match_catalog(resume["resume_text"], jobs) for resume in resumes]
        connection_sets = {
            tuple(item["id"] for item in result["items"] if item["matched"]) for result in results
        }
        self.assertEqual(len(resumes), 40)
        self.assertGreaterEqual(len(connection_sets), 15)
        self.assertGreater(len({result["matched_count"] for result in results}), 1)
        self.assertTrue(all(result["matched_count"] < len(jobs) for result in results))
        self.assertTrue(any(result["matched_count"] > 0 for result in results))
        for result in results:
            self.assertEqual({item["id"] for item in result["items"]}, {job["id"] for job in jobs})
            self.assertTrue(
                all(item["matched"] == (item["score"] >= 60) for item in result["items"])
            )


if __name__ == "__main__":
    unittest.main()
