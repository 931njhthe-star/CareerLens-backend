"""Application operations for browsing and privately collecting job postings."""

from datetime import datetime, timezone
from uuid import uuid4

from app.modules.job_postings.catalog import validate_filters, validate_posting


class JobService:
    def __init__(self, repository, source):
        self.repository = repository
        self.source = source
        examples = source.load_examples()
        self.repository.seed(
            [
                {**validate_posting(item), "id": item["id"], "created_at": item["created_at"]}
                for item in examples
            ]
        )

    def list(self, query, user_id=None):
        return self.repository.list(validate_filters(query), user_id)

    def get(self, posting_id, user_id=None):
        return self.repository.get(posting_id, user_id)

    def create(self, payload, user_id):
        posting = {
            **validate_posting(payload),
            "id": "manual-" + uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return self.repository.create(posting, user_id)

    def update(self, posting_id, payload, user_id):
        return self.repository.update(posting_id, validate_posting(payload), user_id)

    def delete(self, posting_id, user_id):
        return self.repository.delete(posting_id, user_id)

    def bookmark(self, posting_id, user_id, saved):
        return self.repository.bookmark(posting_id, user_id, saved)
