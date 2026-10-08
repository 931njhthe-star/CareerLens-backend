"""Evidence-based catalog selection across arbitrary jobs and resumes."""

import unittest

from app.modules.analysis.matching.catalog import match_catalog
from app.modules.analysis.reporting.service import analyze


def posting(identifier, description, role="개발자"):
    return {
        "id": identifier,
        "company": "가상 기업",
        "role": role,
        "description": description,
        "location": "서울",
        "source_type": "example",
    }


class CatalogMatchingTests(unittest.TestCase):
    def test_59_is_not_connected_and_60_is_connected(self):
        resume = (
            "Python 서비스를 개발했습니다.\nSQL 보고서를 작성했습니다.\nReact 화면을 개발했습니다."
        )
        jobs = [
            posting("score59", "Python 개발\nSQL 활용\nReact와 TypeScript 개발\nDocker 운영"),
            posting("score60", "Python 개발\nSQL 활용\nDocker 운영"),
        ]
        result = match_catalog(resume, jobs)
        items = {item["id"]: item for item in result["items"]}
        self.assertEqual(items["score59"]["score"], 59)
        self.assertFalse(items["score59"]["matched"])
        self.assertEqual(items["score60"]["score"], 60)
        self.assertTrue(items["score60"]["matched"])
        self.assertEqual(result["matched_count"], 1)

    def test_different_resumes_change_job_ids_and_connection_count(self):
        jobs = [
            posting("python", "Python 개발"),
            posting("python-sql", "Python 개발\nSQL 활용"),
            posting("cafe", "커피 추출\n재고 관리", "바리스타"),
        ]
        developer = match_catalog("Python 서비스를 개발했습니다. SQL 보고서를 작성했습니다.", jobs)
        barista = match_catalog("커피 추출을 담당했습니다. 재고 관리를 담당했습니다.", jobs)
        self.assertEqual(
            {item["id"] for item in developer["items"] if item["matched"]}, {"python", "python-sql"}
        )
        self.assertEqual({item["id"] for item in barista["items"] if item["matched"]}, {"cafe"})
        self.assertEqual(
            [item["id"] for item in developer["items"]], [item["id"] for item in barista["items"]]
        )
        self.assertEqual(developer["matched_count"], 2)
        self.assertEqual(barista["matched_count"], 1)

    def test_unlisted_job_terms_use_generic_matching(self):
        jobs = [posting("florist", "플라워 어레인지먼트", "플로리스트")]
        result = match_catalog("플라워 어레인지먼트를 제작했습니다.", jobs)
        self.assertTrue(result["items"][0]["matched"])
        unrelated = match_catalog("Python API를 개발했습니다.", jobs)
        self.assertEqual(unrelated["matched_count"], 0)

    def test_catalog_score_equals_detailed_report_including_answers(self):
        resume = "Python과 SQL로 데이터를 분석했습니다."
        answers = {"outcome": "Docker 배포를 담당해 처리 시간을 20% 줄였습니다."}
        jobs = [posting("sample", "Python 개발\nSQL 분석\nDocker 배포")]
        result = match_catalog(resume, jobs, answers)
        report = analyze(
            resume, jobs[0]["company"], jobs[0]["role"], jobs[0]["description"], answers
        )
        self.assertEqual(result["items"][0]["score"], report["score"])
        self.assertEqual(
            result["items"][0]["evidence"],
            [
                {key: match[key] for key in ("requirement", "status", "matched_terms")}
                for match in report["matches"]
            ],
        )

    def test_no_resume_no_jobs_no_requirements_are_explicit(self):
        job = posting("python", "Python 개발")
        no_resume = match_catalog("", [job])
        self.assertEqual(no_resume["status"], "resume_required")
        self.assertIsNone(no_resume["items"][0]["score"])
        self.assertFalse(no_resume["items"][0]["matched"])
        self.assertEqual(no_resume["evaluated_jobs"], 0)
        no_jobs = match_catalog("Python을 개발했습니다.", [])
        self.assertEqual(no_jobs["status"], "no_jobs")
        self.assertEqual(no_jobs["items"], [])
        invalid = match_catalog(
            "Python을 개발했습니다.", [posting("benefits", "복리후생\n무료 식사 제공")]
        )
        self.assertEqual(invalid["items"][0]["status"], "no_requirements")
        self.assertIsNone(invalid["items"][0]["score"])

    def test_names_dates_repetition_and_no_experience_do_not_add_matches(self):
        jobs = [posting("python", "Python 개발")]
        original = match_catalog("Python 개발 경험이 없습니다.", jobs)
        embellished = match_catalog(
            "이름: 홍길동\n생년월일: 1990.01.01\n경력 기간: 2020-2026\n"
            + "Python 개발 경험이 없습니다.\n" * 10,
            jobs,
        )
        self.assertEqual(original, embellished)
        self.assertEqual(original["matched_count"], 0)

    def test_results_are_deterministic_and_locations_are_not_fabricated(self):
        jobs = [posting("b", "SQL 활용"), posting("a", "Python 개발")]
        result = match_catalog("Python을 개발했습니다.", jobs)
        self.assertEqual(result, match_catalog("Python을 개발했습니다.", list(reversed(jobs))))
        self.assertNotIn("latitude", result["items"][0])
        jobs[0].update(latitude=37.5, longitude=127.0)
        located = match_catalog("Python을 개발했습니다.", jobs)
        self.assertEqual(located["items"][1]["latitude"], 37.5)


if __name__ == "__main__":
    unittest.main()
