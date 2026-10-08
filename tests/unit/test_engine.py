import importlib.util
import json
from pathlib import Path
import unittest


from app.modules.analysis.reporting import service as engine


class AnalysisTests(unittest.TestCase):
    job = "Python과 SQL 기반 데이터 분석 경험\n고객 인터뷰를 통한 사용자 조사\n유관 부서와 협업하여 온보딩 개선"
    strong = "파이썬과 SQL로 제품 데이터를 분석해 전환율을 18% 개선했습니다.\n고객 인터뷰 20건을 수행해 사용자 조사 결과를 정리했습니다.\n디자이너와 협업하여 온보딩을 개선하고 이탈률을 10% 감소시켰습니다."
    weak = (
        "카페에서 음료 조리와 재고 관리를 담당했습니다. 주말 매장 운영과 고객 응대를 수행했습니다."
    )

    def analyze(self, resume, **kwargs):
        return engine.analyze(resume, "예시회사", "제품 매니저", self.job, **kwargs)

    def test_fit_is_differentiated_and_grounded(self):
        strong, weak = self.analyze(self.strong), self.analyze(self.weak)
        self.assertGreater(strong["score"], weak["score"] + 40)
        self.assertEqual(strong["confirmed_count"], 3)
        self.assertEqual(weak["confirmed_count"], 0)
        for match in strong["matches"]:
            for evidence in match["evidence_items"]:
                self.assertIn(evidence["excerpt"], self.strong)
        self.assertEqual(sum(item["score"] for item in strong["criteria"]), strong["score"])
        json.dumps(strong, ensure_ascii=False)

    def test_missing_inputs_raise(self):
        for resume, job, role in (
            ("", self.job, "직무"),
            ("이력서", " ", "직무"),
            ("이력서", self.job, ""),
        ):
            with self.subTest(resume=resume, job=job, role=role):
                with self.assertRaises(ValueError):
                    engine.analyze(resume, "회사", role, job)
        with self.assertRaises(ValueError):
            self.analyze(self.strong, answers=["wrong type"])

    def test_repetition_does_not_improve_score(self):
        plain = "Python SQL 데이터 분석"
        self.assertEqual(self.analyze(plain)["score"], self.analyze((plain + "\n") * 40)["score"])
        a = engine.analyze("Python", "회사", "개발", "Python 개발 경험")
        b = engine.analyze("Python " * 100, "회사", "개발", "Python 개발 경험")
        self.assertEqual(a["score"], b["score"])
        self.assertLess(a["score"], 60)

    def test_negative_experience_does_not_match(self):
        negatives = [
            "Python 경험 없음",
            "Python 개발 경험이 없습니다.",
            "파이썬을 사용하지 않았습니다.",
            "Python을 배운 적 없음",
            "No experience with Python.",
            "I have never used Python.",
            "Python: none",
            "I have not worked with Python.",
            "No Python experience",
            "I am not experienced in Python.",
        ]
        for text in negatives:
            with self.subTest(text=text):
                result = engine.analyze(text, "회사", "개발자", "Python 개발 경험")
                self.assertEqual(result["matches"][0]["status"], "missing")
                self.assertEqual(result["score"], 0)

    def test_other_positive_skill_is_retained(self):
        result = engine.analyze(
            "Python 경험 없음. SQL로 보고서를 작성했습니다.",
            "회사",
            "분석가",
            "Python 개발\nSQL 활용",
        )
        self.assertEqual([match["status"] for match in result["matches"]], ["missing", "confirmed"])

    def test_answers_are_separate_evidence(self):
        answer = "Python과 SQL로 데이터를 분석하고 온보딩 개선을 담당했습니다."
        before = self.analyze(self.weak)
        after = self.analyze(self.weak, answers={"evidence_1": answer})
        self.assertGreater(after["score"], before["score"])
        self.assertTrue(any(match["source"] == "answer" for match in after["matches"]))
        self.assertTrue(
            any(
                item["excerpt"] == answer and item["source"] == "answer"
                for match in after["matches"]
                for item in match["evidence_items"]
            )
        )
        self.assertEqual(
            self.analyze(self.weak, answers={"evidence_1": "Python 경험 없음"})["score"],
            before["score"],
        )

    def test_generic_non_tech_requirements(self):
        good = engine.analyze(
            "커피 추출을 담당하고 에스프레소 레시피를 개선했습니다.\n재고 관리를 담당해 폐기량을 12% 감소시켰습니다.",
            "카페",
            "바리스타",
            "커피 추출\n재고 관리",
        )
        bad = engine.analyze(
            "Python으로 API를 개발했습니다.", "카페", "바리스타", "커피 추출\n재고 관리"
        )
        self.assertGreater(good["score"], bad["score"] + 50)

    def test_plain_excerpt_is_preserved_for_template_escaping(self):
        text = '<script>alert("x")</script> Python API를 개발했습니다.'
        result = engine.analyze(text, "<b>회사</b>", "개발자", "Python API 개발")
        self.assertEqual(result["matches"][0]["evidence_items"][0]["excerpt"], text)
        self.assertIn("<b>회사</b>", result["summary"])

    def test_questions_are_bounded_and_have_unique_ids(self):
        questions = engine.generate_questions(self.weak, self.job, "제품 매니저")
        self.assertGreater(len(questions), 0)
        self.assertLessEqual(len(questions), 3)
        self.assertEqual(len(set(item["id"] for item in questions)), len(questions))
        self.assertTrue(all(item["prompt"] and item["reason"] for item in questions))

    def test_no_rank_or_probability_claim(self):
        result = self.analyze(self.strong)
        self.assertNotIn("상위", result["verdict"])
        self.assertIn("실제 기업의 회신", result["recruiter_email"]["body"])
        self.assertIn("로컬 규칙 기반", result["methodology"])
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_example_job_does_not_evaluate_preamble(self):
        example_dir = Path(__file__).resolve().parents[2] / "data" / "examples"
        job = (example_dir / "job.txt").read_text(encoding="utf-8")
        resume = (example_dir / "resume.txt").read_text(encoding="utf-8")
        result = engine.analyze(resume, "샘플테크", "Python 백엔드 개발자", job)
        self.assertEqual(result["requirement_count"], 9)
        requirements = "\n".join(item["requirement"] for item in result["matches"])
        self.assertNotIn("샘플테크", requirements)
        self.assertNotIn("가상의", requirements)
        questions = engine.generate_questions(resume, job, "Python 백엔드 개발자")
        self.assertFalse(any("가상의" in question["prompt"] for question in questions))

    def test_section_boundaries_and_explicit_demographics_are_excluded(self):
        job = "회사 소개\n우리는 훌륭한 인재를 채용합니다.\n자격 요건\nPython 개발 경험\n20대 여성 우대\n국적: 대한민국\n기독교 신자\n복리후생\n매년 해외 여행과 조식 제공\n지원 방법\n이메일 제출\n우대 사항: Redis 운영 경험"
        result = engine.analyze("Python 개발 및 Redis 운영을 담당했습니다.", "회사", "개발자", job)
        self.assertEqual(
            [item["requirement"] for item in result["matches"]],
            ["Python 개발 경험", "Redis 운영 경험"],
        )
        english = "About us\nWe are hiring.\nRequirements\nPython development experience\nFemale aged 20 required\nReligion: Christian\nBenefits\nFree meals\nHow to apply\nEmail us"
        result = engine.analyze("I developed Python software.", "Example", "Developer", english)
        self.assertEqual(result["requirement_count"], 1)

    def test_explicit_framework_alternatives_accept_either(self):
        job = "Python 및 FastAPI 또는 Flask를 사용한 서비스 개발 경험"
        for framework in ("FastAPI", "Flask"):
            result = engine.analyze(
                f"Python과 {framework}로 서비스를 개발했습니다.", "회사", "개발자", job
            )
            self.assertEqual(result["matches"][0]["status"], "confirmed")
            self.assertEqual(result["matches"][0]["missing_terms"], [])
        result = engine.analyze("Python으로 서비스를 개발했습니다.", "회사", "개발자", job)
        self.assertEqual(result["matches"][0]["status"], "partial")

    def test_database_concepts_are_not_discarded(self):
        job = "SQL 및 PostgreSQL과 Redis를 활용한 서비스 개발"
        result = engine.analyze("SQL로 보고서를 작성했습니다.", "회사", "개발자", job)
        self.assertEqual(result["matches"][0]["status"], "partial")
        self.assertEqual(set(result["matches"][0]["missing_terms"]), {"PostgreSQL", "Redis"})
        result = engine.analyze(
            "SQL과 PostgreSQL을 활용하고 Redis 캐시를 개발했습니다.", "회사", "개발자", job
        )
        self.assertEqual(result["matches"][0]["status"], "confirmed")

    def test_unsectioned_requirements_and_outage_skill_still_work(self):
        result = engine.analyze(
            "Python 서비스 장애 대응과 Redis 운영을 담당했습니다.",
            "회사",
            "개발자",
            "회사소개: Python 서비스를 만드는 곳\nPython 서비스 장애 대응\nRedis 운영\n성별: 남성",
        )
        self.assertEqual(result["requirement_count"], 2)
        self.assertEqual(result["confirmed_count"], 2)

    def test_negative_cloud_experience_in_answers_does_not_increase_score(self):
        job = "AWS 환경에서 서비스 운영 경험"
        negatives = [
            "AWS 환경에서 운영한 경험은 없습니다.",
            "AWS 서비스를 직접 운영해 본 적은 없습니다",
            "AWS 관련 실무 경험이 전혀 없습니다",
            "AWS 사용 경험 없음",
        ]
        before = engine.analyze("Python 서비스를 개발했습니다.", "회사", "개발자", job)
        for answer in negatives:
            with self.subTest(answer=answer):
                result = engine.analyze(
                    "Python 서비스를 개발했습니다.", "회사", "개발자", job, {"evidence_1": answer}
                )
                self.assertEqual(result["matches"][0]["status"], "missing")
                self.assertEqual(result["score"], before["score"])

    def test_absence_of_outage_or_problem_is_positive_experience(self):
        for text in (
            "AWS 서비스를 장애 없이 운영했습니다.",
            "AWS 운영 경험이 있습니다. 문제 없음.",
            "AWS 서비스를 운영했고 Python 환경에서 개발한 경험은 없습니다.",
        ):
            with self.subTest(text=text):
                result = engine.analyze(text, "회사", "개발자", "AWS 서비스 운영 경험")
                self.assertEqual(result["matches"][0]["status"], "confirmed")
        result = engine.analyze(
            "AWS 환경에서 운영한 경험은 없지만 SQL로 보고서를 작성했습니다.",
            "회사",
            "개발자",
            "AWS 서비스 운영\nSQL 활용",
        )
        self.assertEqual([item["status"] for item in result["matches"]], ["missing", "confirmed"])

    def test_contextual_evidence_precedes_longer_keyword_list(self):
        resume = "Python, FastAPI, Flask\nPython과 FastAPI로 API를 개발했습니다.\nFlask로 검색 서비스를 개발했습니다."
        job = "Python과 FastAPI 및 Flask 사용 경험"
        result = engine.analyze(resume, "회사", "개발자", job)
        self.assertEqual(result["matches"][0]["status"], "confirmed")
        self.assertEqual(len(result["matches"][0]["evidence_items"]), 2)
        self.assertTrue(
            all(
                "개발했습니다" in item["excerpt"] for item in result["matches"][0]["evidence_items"]
            )
        )
        keywords = engine.analyze("Python, FastAPI, Flask", "회사", "개발자", job)
        self.assertEqual(keywords["matches"][0]["status"], "partial")
        self.assertTrue(result["gaps"])

    def test_answer_source_labels_hide_internal_keys(self):
        for key, label in (
            ("evidence_1", "보완 답변 1"),
            ("ownership", "본인 기여 답변"),
            ("outcome", "결과·규모 답변"),
            ("internal_key", "보완 답변"),
        ):
            result = engine.analyze(
                "Python으로 서비스를 개발했습니다.",
                "회사",
                "개발자",
                "AWS 서비스 운영",
                {key: "AWS 서비스를 운영했습니다."},
            )
            self.assertEqual(result["matches"][0]["evidence_items"][0]["source_label"], label)


if __name__ == "__main__":
    unittest.main()
