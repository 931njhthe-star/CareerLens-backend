"""Private catalog matching, report refresh and resume-change behavior."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app import create_app


class JobMatchingApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "matching-tests-only",
                "DATABASE": str(Path(self.temp.name) / "matching.sqlite3"),
            }
        )
        self.alice = self.register("alice-matching@example.test")
        self.bob = self.register("bob-matching@example.test")

    def mutate(self, client, method, path, **kwargs):
        token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
        return client.open(path, method=method, headers={"X-CSRF-Token": token}, **kwargs)

    def register(self, email):
        client = self.app.test_client()
        response = self.mutate(
            client,
            "POST",
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "Matching-test-password-2026!",
                "name": "가상 사용자",
            },
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        return client

    def save_resume(self, client, text):
        response = self.mutate(client, "PUT", "/api/v1/resume", json={"resume_text": text})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def create_job(self, client, requirement="Python API 개발", role="개발자"):
        payload = {
            "company": "나의 가상 회사",
            "role": role,
            "location": "서울",
            "employment_type": "정규직",
            "experience_level": "무관",
            "skills": [],
            "description": "회사소개\n독립 테스트를 위한 가상의 채용 기업입니다.\n담당업무\n"
            + requirement,
            "source_url": "",
        }
        response = self.mutate(client, "POST", "/api/v1/job-postings", json=payload)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["posting"]

    def matches(self, client):
        response = client.get("/api/v1/job-matches")
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["job_matches"]

    def test_login_and_resume_are_required_without_inventing_scores(self):
        self.assertEqual(self.app.test_client().get("/api/v1/job-matches").status_code, 401)
        result = self.matches(self.alice)
        self.assertEqual(result["status"], "resume_required")
        self.assertEqual(result["matched_count"], 0)
        self.assertTrue(all(item["score"] is None for item in result["items"]))

    def test_private_manual_jobs_and_resumes_are_user_scoped(self):
        job = self.create_job(self.alice)
        self.save_resume(
            self.alice,
            "Python으로 API를 개발했습니다. 서비스 요청 처리를 담당하여 응답 속도를 20% 개선했습니다.",
        )
        alice = self.matches(self.alice)
        bob = self.matches(self.bob)
        self.assertIn(job["id"], {item["id"] for item in alice["items"]})
        self.assertNotIn(job["id"], {item["id"] for item in bob["items"]})
        self.assertEqual(bob["status"], "resume_required")
        selected = next(item for item in alice["items"] if item["id"] == job["id"])
        self.assertTrue(selected["matched"])
        self.assertNotIn("owner_id", selected)
        self.assertNotIn("resume_text", selected)

    def test_replacing_resume_changes_connections_and_invalidates_report(self):
        developer_job = self.create_job(self.alice)
        cafe_job = self.create_job(self.alice, "커피 추출\n재고 관리", "바리스타")
        self.save_resume(
            self.alice,
            "Python으로 API를 개발했습니다. 서비스 요청 처리를 담당하여 응답 속도를 20% 개선했습니다.",
        )
        before = self.matches(self.alice)
        connected_before = {item["id"] for item in before["items"] if item["matched"]}
        self.assertIn(developer_job["id"], connected_before)
        self.assertNotIn(cafe_job["id"], connected_before)
        response = self.save_resume(
            self.alice,
            "카페에서 커피 추출을 담당했습니다. 재고 관리를 담당하며 일일 재고 소진과 음료 주문을 관리했습니다.",
        )
        self.assertIsNone(response["draft"]["report"])
        after = self.matches(self.alice)
        connected_after = {item["id"] for item in after["items"] if item["matched"]}
        self.assertIn(cafe_job["id"], connected_after)
        self.assertNotIn(developer_job["id"], connected_after)
        self.assertEqual(
            {item["id"] for item in before["items"]}, {item["id"] for item in after["items"]}
        )

    def test_report_uses_same_score_and_refreshes_after_job_deletion(self):
        job = self.create_job(self.alice)
        self.save_resume(
            self.alice,
            "Python으로 API를 개발했습니다. 서비스 요청 처리를 담당하여 응답 속도를 20% 개선했습니다.",
        )
        self.mutate(
            self.alice,
            "PUT",
            "/api/v1/job",
            json={
                "company": job["company"],
                "role": job["role"],
                "job_text": job["description"],
            },
        )
        response = self.mutate(self.alice, "POST", "/api/v1/analysis", json={"answers": {}})
        self.assertEqual(response.status_code, 200, response.get_json())
        report = response.get_json()["report"]
        selected = next(item for item in report["job_matches"]["items"] if item["id"] == job["id"])
        self.assertEqual(selected["score"], report["score"])
        self.assertEqual(report["job_matches"], self.matches(self.alice))
        self.mutate(self.alice, "DELETE", "/api/v1/job-postings/" + job["id"])
        refreshed = self.alice.get("/api/v1/workspace").get_json()["draft"]["report"]
        self.assertNotIn(job["id"], {item["id"] for item in refreshed["job_matches"]["items"]})

    def test_legacy_report_gets_current_matching_without_reanalysis(self):
        self.mutate(self.alice, "POST", "/api/v1/example")
        with self.alice.session_transaction() as session:
            user_id = session["user_id"]
        repository = self.app.extensions["workspace_service"].repository
        draft = repository.load(user_id)
        draft["report"] = {"score": 12, "summary": "기존 보고서"}
        repository.save(user_id, draft)
        refreshed = self.alice.get("/api/v1/workspace").get_json()["draft"]["report"]
        self.assertEqual(refreshed["score"], 12)
        self.assertEqual(refreshed["job_matches"], self.matches(self.alice))


if __name__ == "__main__":
    unittest.main()
