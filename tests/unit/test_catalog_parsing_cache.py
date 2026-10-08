"""Repeated catalog reads may reuse parsing, but scores must stay current."""

import unittest
from unittest.mock import patch

from app.modules.analysis.matching.catalog import catalog_requirements, match_catalog
from app.modules.job_postings.requirements import _requirements


class CatalogParsingCacheTests(unittest.TestCase):
    def test_resume_and_job_changes_always_recalculate_connections(self):
        catalog_requirements.cache_clear()
        self.addCleanup(catalog_requirements.cache_clear)
        job = {
            "id": "same-job",
            "company": "가상 기업",
            "role": "담당자",
            "location": "서울",
            "description": "담당업무\nPython API 개발",
        }
        developer = "Python API를 개발하고 요청 처리를 담당하여 응답 시간을 20% 개선했습니다."
        barista = "카페에서 커피 추출과 재고 관리를 담당했습니다. 주문 처리 시간을 20% 줄였습니다."

        with patch(
            "app.modules.analysis.matching.catalog._requirements", wraps=_requirements
        ) as parse:
            first = match_catalog(developer, [job])["items"][0]
            second = match_catalog(barista, [job])["items"][0]
            job["description"] = "담당업무\n커피 추출\n재고 관리"
            third = match_catalog(barista, [job])["items"][0]
            fourth = match_catalog(developer, [job])["items"][0]

        self.assertTrue(first["matched"])
        self.assertFalse(second["matched"])
        self.assertTrue(third["matched"])
        self.assertFalse(fourth["matched"])
        self.assertEqual(parse.call_count, 2)
        self.assertEqual({item["id"] for item in (first, second, third, fourth)}, {"same-job"})


if __name__ == "__main__":
    unittest.main()
