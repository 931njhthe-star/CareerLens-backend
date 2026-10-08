"""Authenticated workflow behavior, persistence, invalidation and user isolation."""

from contextlib import closing
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from app import create_app


class WorkspaceApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {
            "TESTING": True,
            "SECRET_KEY": "test-only-workspace-key",
            "DATABASE": str(Path(self.temp.name) / "test.sqlite3"),
        }
        self.app = create_app(self.config)
        self.client = self.register("one@example.test")

    def csrf(self, client=None):
        return (client or self.client).get("/api/v1/auth/session").get_json()["csrf_token"]

    def register(self, email):
        client = self.app.test_client()
        response = client.post(
            "/api/v1/auth/register",
            headers={"X-CSRF-Token": self.csrf(client)},
            json={
                "email": email,
                "password": "CareerLens-Test-2026!",
                "name": "테스트 지원자",
                "terms_accepted": True,
                "privacy_accepted": True,
            },
        )
        self.assertIn(response.status_code, (200, 201), response.get_json())
        return client

    def mutate(self, method, path, *, client=None, **kwargs):
        client = client or self.client
        return client.open(
            path, method=method, headers={"X-CSRF-Token": self.csrf(client)}, **kwargs
        )

    def load_example(self, client=None):
        response = self.mutate("POST", "/api/v1/example", client=client)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def run_analysis(self, answers=None):
        response = self.mutate("POST", "/api/v1/analysis", json={"answers": answers or {}})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["report"]

    def test_public_health_and_all_workflow_routes_require_login(self):
        guest = self.app.test_client()
        self.assertEqual(guest.get("/api/v1/health").get_json(), {"status": "ok"})
        for method, path in [
            ("GET", "workspace"),
            ("PUT", "resume"),
            ("POST", "resume/upload"),
            ("PUT", "job"),
            ("GET", "questions"),
            ("POST", "analysis"),
            ("POST", "example"),
            ("DELETE", "workspace"),
        ]:
            with self.subTest(method=method, path=path):
                self.assertEqual(guest.open(f"/api/v1/{path}", method=method).status_code, 401)

    def test_empty_workspace_and_complete_example_analysis(self):
        empty = self.client.get("/api/v1/workspace").get_json()
        self.assertEqual(empty["draft"]["resume_text"], "")
        self.assertEqual(empty["questions"], [])
        example = self.load_example()
        self.assertGreater(len(example["questions"]), 0)
        report = self.run_analysis()
        self.assertEqual(report["analysis_mode"], "local_rules")
        self.assertEqual(report["requirement_count"], 9)
        draft = self.client.get("/api/v1/workspace").get_json()["draft"]
        self.assertEqual(report, draft["report"])
        self.assertTrue(draft["created_at"])
        self.assertNotIn("실제 기업의 회신", report["verdict"])
        self.assertIn("실제 기업의 회신", report["recruiter_email"]["body"])

    def test_twenty_synthetic_resume_examples_require_auth_and_preserve_selected_job(self):
        guest = self.app.test_client()
        self.assertEqual(guest.get("/api/v1/resume-examples").status_code, 401)
        items = self.client.get("/api/v1/resume-examples").get_json()["items"]
        self.assertEqual(len(items), 220)
        self.assertEqual(len({item["id"] for item in items}), 220)
        self.assertTrue(
            all(item["source_type"] == "synthetic" and "resume_text" not in item for item in items)
        )
        before = self.load_example()["draft"]
        example = self.client.get("/api/v1/resume-examples/" + items[0]["id"]).get_json()["example"]
        result = self.mutate(
            "PUT", "/api/v1/resume", json={"resume_text": example["resume_text"]}
        ).get_json()["draft"]
        self.assertEqual(result["resume_text"], example["resume_text"])
        self.assertEqual(result["job_text"], before["job_text"])
        self.assertEqual(result["company"], before["company"])
        self.assertIsNone(result["report"])

    def test_old_saved_report_get_derives_preview_without_rewriting_user_data(self):
        self.load_example()
        original = self.run_analysis()
        with closing(sqlite3.connect(self.config["DATABASE"])) as db:
            user_id, payload = db.execute("SELECT user_id, payload FROM workspaces").fetchone()
            draft = json.loads(payload)
            draft["report"].pop("improvement_preview", None)
            legacy_payload = json.dumps(draft, ensure_ascii=False)
            db.execute("UPDATE workspaces SET payload=? WHERE user_id=?", (legacy_payload, user_id))
            db.commit()
        response = self.client.get("/api/v1/workspace").get_json()["draft"]["report"]
        self.assertIsNotNone(response["improvement_preview"])
        self.assertEqual(response["score"], original["score"])
        self.assertEqual(response["matches"], original["matches"])
        with closing(sqlite3.connect(self.config["DATABASE"])) as db:
            stored = db.execute(
                "SELECT payload FROM workspaces WHERE user_id=?", (user_id,)
            ).fetchone()[0]
        self.assertEqual(stored, legacy_payload)

    def test_unknown_example_does_not_change_saved_workspace(self):
        before = self.load_example()
        self.assertEqual(self.client.get("/api/v1/resume-examples/not-a-fixture").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/workspace").get_json(), before)

    def test_resume_upload_saved_for_review_then_manual_edit(self):
        self.load_example()
        self.run_analysis()
        text = "Python과 Flask로 API를 개발했습니다.\r\nSQL로 데이터 분석을 수행하고 처리 시간을 30% 줄였습니다."
        response = self.mutate(
            "POST",
            "/api/v1/resume/upload",
            data={"file": (BytesIO(text.encode("utf-8-sig")), "C:/private/이력서.txt")},
        )
        self.assertEqual(response.status_code, 200)
        draft = response.get_json()["draft"]
        self.assertEqual(draft["resume_text"], text.replace("\r\n", "\n"))
        self.assertEqual(draft["filename"], "이력서.txt")
        self.assertIsNone(draft["report"])
        edited = draft["resume_text"] + "\nDocker 배포를 담당했습니다."
        result = self.mutate("PUT", "/api/v1/resume", json={"resume_text": edited})
        self.assertEqual(result.get_json()["draft"]["resume_text"], edited)
        self.assertEqual(
            self.client.get("/api/v1/workspace").get_json()["draft"]["resume_text"], edited
        )

    def test_invalid_upload_keeps_existing_workspace(self):
        before = self.load_example()
        response = self.mutate(
            "POST", "/api/v1/resume/upload", data={"file": (BytesIO(b"binary\x00text"), "bad.txt")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/v1/workspace").get_json(), before)

    def test_changed_resume_invalidates_but_equal_normalized_text_keeps_report(self):
        self.load_example()
        draft = self.client.get("/api/v1/workspace").get_json()["draft"]
        self.mutate("PUT", "/api/v1/resume", json={"resume_text": draft["resume_text"]})
        report = self.run_analysis()
        response = self.mutate(
            "PUT",
            "/api/v1/resume",
            json={
                "resume_text": "\r\n" + draft["resume_text"].strip().replace("\n", "\r\n") + "\n"
            },
        )
        self.assertEqual(response.get_json()["draft"]["report"], report)
        response = self.mutate(
            "PUT",
            "/api/v1/resume",
            json={
                "resume_text": draft["resume_text"]
                + "\n추가 프로젝트에서 Redis 캐시를 개발했습니다."
            },
        )
        state = response.get_json()["draft"]
        self.assertIsNone(state["report"])
        self.assertEqual(state["answers"], {})
        self.assertIsNone(state["created_at"])

    def test_changed_job_invalidates_and_same_job_keeps_report(self):
        example = self.load_example()["draft"]
        payload = {key: example[key].strip() for key in ("company", "role", "job_text")}
        self.mutate("PUT", "/api/v1/job", json=payload)
        report = self.run_analysis()
        result = self.mutate("PUT", "/api/v1/job", json=payload)
        self.assertEqual(result.get_json()["draft"]["report"], report)
        payload["company"] = "다른회사"
        result = self.mutate("PUT", "/api/v1/job", json=payload)
        self.assertIsNone(result.get_json()["draft"]["report"])

    def test_answers_remain_separate_sources_and_unknown_questions_fail(self):
        example = self.load_example()
        question_id = example["questions"][0]["id"]
        report = self.run_analysis(
            {question_id: "AWS 서비스를 운영하고 Docker 배포를 담당했습니다."}
        )
        self.assertTrue(
            any(
                item["source"] == "answer"
                for match in report["matches"]
                for item in match["evidence_items"]
            )
        )
        result = self.mutate("POST", "/api/v1/analysis", json={"answers": {"invented": "test"}})
        self.assertEqual(result.status_code, 400)
        self.assertEqual(self.client.get("/api/v1/workspace").get_json()["draft"]["report"], report)

    def test_invalid_types_and_lengths_do_not_overwrite_data(self):
        before = self.load_example()
        cases = [
            ("PUT", "resume", {"resume_text": None}),
            ("PUT", "resume", {"resume_text": "a" * 39}),
            ("PUT", "resume", {"resume_text": "a" * 50_001}),
            ("PUT", "job", {"company": ["x"], "role": "개발", "job_text": "a" * 40}),
            ("PUT", "job", {"company": "a" * 121, "role": "개발", "job_text": "a" * 40}),
            ("POST", "analysis", {"answers": []}),
            ("POST", "analysis", {"answers": {before["questions"][0]["id"]: "a" * 8001}}),
        ]
        for method, path, payload in cases:
            with self.subTest(path=path, payload_type=type(payload)):
                result = self.mutate(method, f"/api/v1/{path}", json=payload)
                self.assertEqual(result.status_code, 400)
                self.assertEqual(self.client.get("/api/v1/workspace").get_json(), before)

    def test_missing_prerequisites_and_non_object_json_fail_cleanly(self):
        self.assertEqual(
            self.mutate("POST", "/api/v1/analysis", json={"answers": {}}).status_code, 400
        )
        self.assertEqual(
            self.mutate(
                "PUT", "/api/v1/job", json={"company": "test", "role": "dev", "job_text": "x" * 40}
            ).status_code,
            400,
        )
        for value in ([], "text", 123):
            self.assertEqual(self.mutate("PUT", "/api/v1/resume", json=value).status_code, 400)

    def test_workspace_delete_is_user_scoped_and_keeps_login(self):
        self.load_example()
        other = self.register("two@example.test")
        other_before = self.load_example(other)
        response = self.mutate("DELETE", "/api/v1/workspace")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["draft"]["resume_text"], "")
        self.assertEqual(self.client.get("/api/v1/workspace").status_code, 200)
        self.assertEqual(other.get("/api/v1/workspace").get_json(), other_before)

    def test_persistence_survives_new_application(self):
        before = self.load_example()
        restarted = create_app(self.config)
        # Read persisted state through the application boundary with the same authenticated owner.
        with self.client.session_transaction() as session:
            user_id = session["user_id"]
        self.assertEqual(restarted.extensions["workspace_service"].workspace(user_id), before)

    def test_csrf_required_on_workflow_mutation(self):
        response = self.client.post("/api/v1/example")
        self.assertIn(response.status_code, (400, 403))
        self.assertEqual(
            self.client.get("/api/v1/workspace").get_json()["draft"]["resume_text"], ""
        )

    def test_errors_are_json_and_sensitive_responses_not_cached(self):
        response = self.mutate("PUT", "/api/v1/resume", data="{", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIsInstance(response.get_json()["error"]["message"], str)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")


if __name__ == "__main__":
    unittest.main()
