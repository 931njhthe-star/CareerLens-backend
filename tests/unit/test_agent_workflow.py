"""Offline fault injection; no external provider, account, or real resume."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app.agent.graphs.analysis import ROOT, analyze_with_agent, build_graph
from app.agent.prompts.loader import load_prompt
from app.integrations.llm.coaching import LlmConfigurationError, build_context
from app.modules.analysis.reporting.service import analyze
from app.retrieval.search.local import retrieve_guidance

INPUT = {
    "resume_text": "Python으로 주문 API를 구현하고 SQL 인덱스를 개선했습니다. 테스트 24개를 작성하고 Docker로 배포했습니다.",
    "company": "가상 기업",
    "role": "Python 백엔드 개발자",
    "job_text": "Python API 개발 경험이 필요합니다. SQL 데이터 모델 설계와 Docker 배포 경험이 필요합니다.",
    "answers": {},
}


def valid_candidate(state):
    return {
        "summary": "작성한 API 작업의 역할과 검증 범위를 설명해 보세요.",
        "recommendations": [
            {
                "text": "API에서 직접 담당한 요청과 테스트 범위를 적어 보세요.",
                "evidence_quote": "Python으로 주문 API를 구현하고",
            }
        ],
        "reference_ids": [state["references"][0]["id"]] if state["references"] else [],
    }


class AgentWorkflowTests(unittest.TestCase):
    def invoke(self, coach=valid_candidate, **kwargs):
        return build_graph(coach=coach, **kwargs).invoke(
            {**INPUT, "mode": "llm"}, {"recursion_limit": 16}
        )["report"]

    def test_rules_mode_preserves_all_original_report_fields(self):
        def forbidden(state):
            self.fail("rules mode called an external coach")

        report = build_graph(coach=forbidden).invoke({**INPUT, "mode": "rules"})["report"]
        original = analyze(**INPUT)
        self.assertEqual({key: report[key] for key in original}, original)
        self.assertEqual(report["agent"]["mode"], "rules")
        self.assertNotIn("structured_coaching", report["agent"]["tools_called"])

    def test_valid_coaching_keeps_original_score(self):
        report = self.invoke()
        self.assertEqual(report["score"], analyze(**INPUT)["score"])
        self.assertEqual(report["agent"]["mode"], "llm_coaching")
        self.assertEqual(report["agent"]["retry_count"], 0)

    def test_unfounded_quote_is_repaired_once_with_feedback(self):
        feedback = []

        def coach(state):
            feedback.append(state["current_error"])
            value = valid_candidate(state)
            if state["retry_count"] == 0:
                value["recommendations"][0][
                    "evidence_quote"
                ] = "대규모 서비스의 매출을 900% 올렸습니다"
            return value

        report = self.invoke(coach)
        self.assertEqual(feedback, ["", "ungrounded_evidence"])
        self.assertEqual(report["agent"]["retry_count"], 1)
        self.assertFalse(report["agent"]["fallback_used"])

    def test_provider_failure_is_bounded_and_secret_error_is_not_exposed(self):
        calls = []

        def coach(state):
            calls.append(1)
            raise RuntimeError("secret-api-key-and-private-resume")

        report = self.invoke(coach)
        self.assertEqual(len(calls), 2)
        self.assertTrue(report["agent"]["fallback_used"])
        self.assertNotIn("ai_coaching", report)
        self.assertNotIn("secret-api", json.dumps(report))

    def test_unknown_reference_and_extra_score_are_rejected(self):
        for kind in ("reference", "score", "empty_quote"):

            def coach(state):
                value = valid_candidate(state)
                if kind == "reference":
                    value["reference_ids"] = ["nonexistent-policy"]
                if kind == "score":
                    value["score"] = 100
                if kind == "empty_quote":
                    value["recommendations"][0]["evidence_quote"] = " " * 12
                return value

            with self.subTest(kind=kind):
                self.assertNotIn("ai_coaching", self.invoke(coach))

    def test_reference_text_cannot_be_used_as_candidate_experience(self):
        def coach(state):
            value = valid_candidate(state)
            value["recommendations"][0]["evidence_quote"] = state["references"][0]["text"]
            return value

        self.assertTrue(self.invoke(coach)["agent"]["fallback_used"])

    def test_retrieval_failure_does_not_break_existing_analysis(self):
        def unavailable(*args):
            raise OSError("private path")

        report = self.invoke(retriever=unavailable)
        self.assertEqual(report["reference_guidance"], [])
        self.assertIn("retrieval_unavailable", report["agent"]["error_codes"])

    def test_prompt_edit_reload_disable_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "prompts"
            shutil.copytree(ROOT / "agent/prompts", directory)
            (directory / "coaching.md").write_text("새로운 코칭 지침", encoding="utf-8")
            self.assertEqual(load_prompt(directory)[0], "새로운 코칭 지침")
            path = directory / "registry.json"
            registry = json.loads(path.read_text(encoding="utf-8"))
            registry["prompts"]["coaching"]["enabled"] = False
            path.write_text(json.dumps(registry), encoding="utf-8")
            report = self.invoke(
                coach=lambda state: self.fail("disabled prompt called"), prompts_dir=directory
            )
            self.assertNotIn("ai_coaching", report)
            registry["prompts"]["coaching"]["file"] = "../outside.md"
            path.write_text(json.dumps(registry), encoding="utf-8")
            self.assertTrue(self.invoke(prompts_dir=directory)["agent"]["fallback_used"])

    def test_keyword_retrieval_returns_relevant_and_no_false_hit(self):
        path = ROOT.parent / "data/knowledge/policies/career-guidance.json"
        self.assertIn("api", [item["id"] for item in retrieve_guidance("Python API", path)])
        self.assertEqual(retrieve_guidance("zzzzunknown", path), [])

    def test_missing_configuration_does_not_retry(self):
        calls = []

        def coach(state):
            calls.append(1)
            raise LlmConfigurationError()

        report = self.invoke(coach)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["agent"]["retry_count"], 0)
        self.assertEqual(report["agent"]["error_codes"], ["llm_unconfigured"])

    def test_context_serialization_stays_within_budget(self):
        context = build_context(
            {
                **INPUT,
                "resume_text": '\\"\n' * 50000,
                "job_text": '\\"\n' * 50000,
                "answers": {str(i): '\\"\n' * 8000 for i in range(3)},
                "report": {"score": 40},
                "settings": {"max_context_chars": 4000},
                "references": [
                    {"id": str(i), "title": "참고", "text": "가" * 2000} for i in range(5)
                ],
            }
        )
        self.assertLessEqual(len(json.dumps(context, ensure_ascii=False)), 4000)

    def test_invalid_editable_corpus_does_not_break_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "guidance.json"
            path.write_text(
                '{"documents":[{"id":"x","title":"x","source":"x","text":"x","keywords":[123]}]}'
            )

            def malformed(query, ignored_path, top_k):
                return retrieve_guidance(query, path, top_k)

            report = self.invoke(retriever=malformed)
            self.assertIn("retrieval_unavailable", report["agent"]["error_codes"])


if __name__ == "__main__":
    unittest.main()
