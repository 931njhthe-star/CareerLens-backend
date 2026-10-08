"""Conditional examples reuse the rubric without manufacturing assessed evidence."""

from copy import deepcopy
import unittest

from app.modules.analysis.matching.scoring import score_evidence
from app.modules.analysis.reporting.improvement import improvement_preview


def sample_report():
    matches = [
        {"requirement": "설계 경험", "status": "missing", "contextual": False, "quantified": False},
        {"requirement": "검증 경험", "status": "partial", "contextual": True, "quantified": False},
        {"requirement": "조사 경험", "status": "confirmed", "contextual": True, "quantified": True},
    ]
    scores = score_evidence(matches)
    return {
        "analysis_mode": "local_rules",
        "score": scores["score"],
        "matches": matches,
        "criteria": [
            {"label": label, "score": scores[key], "max_score": maximum}
            for label, key, maximum in [
                ("경험", "alignment", 70),
                ("맥락", "specificity", 20),
                ("결과", "outcomes", 10),
            ]
        ],
    }


class ImprovementPreviewTests(unittest.TestCase):
    def test_explicit_assumptions_use_original_weights_and_do_not_mutate_report(self):
        report = sample_report()
        before = deepcopy(report)
        preview = improvement_preview(report)
        self.assertEqual(report, before)
        self.assertEqual(preview["basis"], "conditional_rules")
        self.assertEqual(preview["score"], 97)
        self.assertEqual([item["score"] for item in preview["criteria"]], [70, 20, 7])
        self.assertEqual(
            [item["kind"] for item in preview["assumptions"]], ["evidence", "evidence", "outcome"]
        )
        self.assertIn("실제로", preview["assumptions"][0]["detail"])
        self.assertIn("확인할 수 있는 수치가 없다면", preview["assumptions"][-1]["detail"])
        preview["criteria"][0]["label"] = "changed"
        self.assertEqual(report, before)

    def test_unknown_rubrics_inconsistent_scores_and_malformed_reports_fail_closed(self):
        variants = [
            {"analysis_mode": "external_ai"},
            {"criteria": None},
            {"criteria": [None] * 3},
            {"matches": []},
            {"matches": [{"status": "missing"}]},
            {"score": 99},
        ]
        for patch in variants:
            with self.subTest(patch=patch):
                self.assertIsNone(improvement_preview({**sample_report(), **patch}))
        report = sample_report()
        report["criteria"][0]["max_score"] = 60
        self.assertIsNone(improvement_preview(report))

    def test_fully_supported_report_has_no_invented_improvement(self):
        report = sample_report()
        for match in report["matches"]:
            match.update(status="confirmed", contextual=True, quantified=True)
        report["score"] = 100
        for item in report["criteria"]:
            item["score"] = item["max_score"]
        self.assertIsNone(improvement_preview(report))

    def test_preview_does_not_claim_every_missing_item_is_fixed(self):
        report = sample_report()
        report["matches"] = [dict(report["matches"][0], requirement=f"기준 {i}") for i in range(10)]
        report["score"] = 0
        for item in report["criteria"]:
            item["score"] = 0
        preview = improvement_preview(report)
        self.assertEqual(preview["score"], 28)
        self.assertEqual(len(preview["assumptions"]), 4)
