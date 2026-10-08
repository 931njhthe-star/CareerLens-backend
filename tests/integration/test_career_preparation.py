"""Desired-role preparation completes only after actual, current analysis work."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from app.application.workspace import analyze


class CareerPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        mode = patch.dict("os.environ", {"CAREERLENS_ANALYSIS_MODE": "rules"})
        mode.start()
        self.addCleanup(mode.stop)
        self.config = {
            "TESTING": True,
            "SECRET_KEY": "preparation-tests-only",
            "DATABASE": str(Path(self.temp.name) / "test.sqlite3"),
        }
        self.app = create_app(self.config)
        self.client = self.register("preparation@example.test")
        self.resume = "Python과 Flask로 서버 API를 개발했습니다. SQL로 데이터를 분석하고 조회 시간을 30% 줄였습니다. 테스트를 작성하고 서비스 배포와 운영을 담당했습니다."

    def register(self, email):
        client = self.app.test_client()
        response = self.mutate(
            "POST",
            "/auth/register",
            client=client,
            json={
                "email": email,
                "password": "CareerLens-Test-2026!",
                "name": "연습 사용자",
                "terms_accepted": True,
                "privacy_accepted": True,
            },
        )
        self.assertIn(response.status_code, (200, 201))
        return client

    def mutate(self, method, path, client=None, **kwargs):
        client = client or self.client
        csrf = client.get("/api/v1/auth/session").get_json()["csrf_token"]
        return client.open(
            "/api/v1" + path, method=method, headers={"X-CSRF-Token": csrf}, **kwargs
        )

    def select(self, role_id="backend", **kwargs):
        self.assertEqual(
            self.mutate("PUT", "/resume", json={"resume_text": self.resume}).status_code, 200
        )
        response = self.mutate("PUT", "/career-target", json={"role_id": role_id, **kwargs})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def prepare(self, stage, **kwargs):
        return self.mutate("POST", "/preparation", json={"stage": stage, **kwargs})

    def complete(self):
        for stage in ("resume", "role", "report"):
            response = self.prepare(stage)
            self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_auth_and_csrf_protect_new_routes(self):
        guest = self.app.test_client()
        for method, route in (
            ("PUT", "/career-target"),
            ("POST", "/preparation"),
        ):
            self.assertEqual(guest.open("/api/v1" + route, method=method).status_code, 401)
        self.assertEqual(guest.get("/api/v1/career-roles").status_code, 200)
        self.assertEqual(
            self.client.put("/api/v1/career-target", json={"role_id": "backend"}).status_code, 403
        )
        self.assertEqual(
            self.client.post("/api/v1/preparation", json={"stage": "resume"}).status_code, 403
        )

    def test_role_selection_has_no_company_or_job_ad(self):
        items = self.client.get("/api/v1/career-roles").get_json()["items"]
        self.assertTrue(any(item["id"] == "custom" for item in items))
        selected = self.select()
        self.assertEqual(selected["draft"]["analysis_mode"], "desired_role")
        self.assertEqual(selected["draft"]["company"], "")
        self.assertEqual(selected["draft"]["job_text"], "")
        self.assertFalse(selected["preparation"]["complete"])
        self.assertEqual(selected["questions"], [])

    def test_each_stage_is_real_ordered_and_report_is_preliminary(self):
        selected = self.select()
        self.assertEqual(self.prepare("report").status_code, 400)
        self.assertEqual(self.mutate("POST", "/analysis", json={}).status_code, 400)
        first = self.prepare(
            "resume", fingerprint=selected["preparation"]["fingerprint"]
        ).get_json()
        self.assertEqual(
            [item["status"] for item in first["preparation"]["stages"]],
            ["complete", "pending", "pending"],
        )
        self.assertGreater(first["preparation"]["resume_evidence"]["action_statement_count"], 0)
        complete = self.complete()
        self.assertTrue(complete["preparation"]["complete"])
        self.assertTrue(complete["questions"])
        self.assertIsNone(complete["draft"]["report"])
        report = complete["preparation"]["preliminary_report"]
        self.assertEqual(report["reference_source"], "internal_role_reference")
        self.assertEqual(len(report["criteria"]), 3)
        self.assertNotIn("job_matches", report)
        self.assertIn("실제 채용공고와 비교한 결과는 아닙니다", report["summary"])
        self.assertNotIn("공고의", complete["questions"][0]["prompt"])

    def test_final_report_uses_role_context_and_no_catalog_matching(self):
        self.select()
        completed = self.complete()
        question_id = completed["questions"][0]["id"]
        with patch.object(
            self.app.extensions["job_matching_service"],
            "match",
            side_effect=AssertionError("catalog must not be used"),
        ):
            result = self.mutate(
                "POST",
                "/analysis",
                json={"answers": {question_id: "SQL로 데이터를 조회하고 API를 개발했습니다."}},
            )
            self.assertEqual(result.status_code, 200, result.get_json())
            report = result.get_json()["report"]
            self.assertEqual(report["assessment_context"], "desired_role")
            self.assertEqual(report["company"], "")
            self.assertNotIn("job_matches", report)
            self.assertEqual(
                self.client.get("/api/v1/workspace").get_json()["draft"]["report"], report
            )

    def test_successful_retry_does_not_rerun_agent(self):
        self.select()
        self.complete()
        with patch(
            "app.application.workspace.analyze",
            side_effect=AssertionError("must reuse completed stage"),
        ):
            self.assertTrue(self.prepare("report").get_json()["preparation"]["complete"])

    def test_agent_failure_leaves_report_pending_and_can_retry(self):
        self.select()
        self.prepare("resume")
        self.prepare("role")
        with patch(
            "app.application.workspace.analyze",
            side_effect=ValueError("분석을 다시 시도해 주세요."),
        ):
            self.assertEqual(self.prepare("report").status_code, 400)
        pending = self.client.get("/api/v1/workspace").get_json()["preparation"]
        self.assertFalse(pending["complete"])
        self.assertEqual(pending["stages"][2]["status"], "pending")
        self.assertNotIn("preliminary_report", pending)
        self.assertTrue(self.prepare("report").get_json()["preparation"]["complete"])

    def test_changed_inputs_invalidate_preparation_and_old_fingerprint(self):
        selected = self.select()
        self.complete()
        unchanged = self.mutate("PUT", "/career-target", json={"role_id": "backend"}).get_json()
        self.assertTrue(unchanged["preparation"]["complete"])
        changed = self.mutate(
            "PUT",
            "/resume",
            json={"resume_text": self.resume + "\nDocker로 배포 자동화를 구현했습니다."},
        ).get_json()
        self.assertFalse(changed["preparation"]["complete"])
        self.assertEqual(changed["questions"], [])
        self.assertEqual(
            self.prepare("resume", fingerprint=selected["preparation"]["fingerprint"]).status_code,
            409,
        )
        self.complete()
        changed = self.mutate("PUT", "/career-target", json={"role_id": "frontend"}).get_json()
        self.assertFalse(changed["preparation"]["complete"])
        self.assertIsNone(changed["draft"]["report"])

    def test_stale_agent_completion_cannot_overwrite_new_resume(self):
        self.select()
        self.prepare("resume")
        self.prepare("role")
        with self.client.session_transaction() as session:
            user_id = session["user_id"]
        updated = self.resume + "\n새로운 프로젝트에서 Redis를 운영했습니다."

        def concurrent_edit(*args, **kwargs):
            report = analyze(*args, **kwargs)
            self.app.extensions["workspace_service"].save_resume(user_id, updated)
            return report

        with patch("app.application.workspace.analyze", side_effect=concurrent_edit):
            self.assertEqual(self.prepare("report").status_code, 409)
        result = self.client.get("/api/v1/workspace").get_json()
        self.assertEqual(result["draft"]["resume_text"], updated)
        self.assertFalse(result["preparation"]["complete"])

    def test_custom_role_validation_and_user_isolation(self):
        other = self.register("other@example.test")
        self.select("custom", role="영상 기획", focus="교육 콘텐츠")
        result = self.complete()
        self.assertEqual(result["preparation"]["role_reference"]["label"], "영상 기획")
        self.assertEqual(result["questions"][-1]["id"], "focus")
        self.assertIn("교육 콘텐츠", result["questions"][-1]["prompt"])
        self.assertIn("공통 경험 기준", result["preparation"]["preliminary_report"]["methodology"])
        self.assertIsNone(other.get("/api/v1/workspace").get_json()["preparation"])
        before = self.client.get("/api/v1/workspace").get_json()
        for payload in (
            {"role_id": "missing"},
            {"role_id": []},
            {"role_id": "custom"},
            {"role_id": "backend", "focus": "x" * 1001},
        ):
            self.assertEqual(self.mutate("PUT", "/career-target", json=payload).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/workspace").get_json(), before)

    def test_legacy_job_api_switches_back_without_stale_role_state(self):
        self.select()
        self.complete()
        legacy = self.mutate(
            "PUT",
            "/job",
            json={
                "company": "가상 회사",
                "role": "백엔드",
                "job_text": "Python으로 API를 개발한 경험이 필요합니다. SQL로 데이터베이스를 운영한 경험이 필요합니다.",
            },
        ).get_json()
        self.assertEqual(legacy["draft"]["analysis_mode"], "job_posting")
        self.assertIsNone(legacy["draft"]["career_target"])
        self.assertIsNone(legacy["preparation"])
        self.assertTrue(legacy["questions"])

    def test_completed_preparation_survives_restart(self):
        self.select()
        completed = self.complete()
        with self.client.session_transaction() as session:
            user_id = session["user_id"]
        restarted = create_app(self.config)
        self.assertEqual(restarted.extensions["workspace_service"].workspace(user_id), completed)
