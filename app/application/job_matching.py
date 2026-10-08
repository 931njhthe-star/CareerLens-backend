"""Compare the current user's evidence with their visible job catalog."""

from app.modules.analysis.matching.catalog import match_catalog


MAX_MATCHING_JOBS = 1_000


class JobMatchingService:
    def __init__(self, job_repository, draft_repository):
        self.job_repository = job_repository
        self.draft_repository = draft_repository

    def match(self, user_id: str, resume_text: str, answers=None) -> dict:
        # Bypass only the browsing page-size limit; retain its visibility query.
        catalog = self.job_repository.list(
            {
                "q": "",
                "location": "",
                "employment_type": "",
                "experience_level": "",
                "skill": "",
                "saved": False,
                "page": 1,
                "page_size": MAX_MATCHING_JOBS,
            },
            user_id,
        )
        result = match_catalog(resume_text, catalog["items"], answers)
        result["total_jobs"] = catalog["total"]
        result["truncated"] = catalog["total"] > len(catalog["items"])
        return result

    def for_user(self, user_id: str) -> dict:
        draft = self.draft_repository.load(user_id)
        return self.match(user_id, draft["resume_text"], draft.get("answers"))
