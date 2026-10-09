import math
from datetime import date
from app.modules.analysis.models import CriterionResult, ParsedResume, ParsedJob
from app.modules.analysis.scoring.rubric import CRITERIA, DOMAIN_WEIGHTS


def geometric(items: list[tuple[float | None, float, str]]) -> float | None:
    active = [(s, w) for s, w, v in items if v != 'not_applicable']
    if not active or any(s is None for s, _ in active):
        return None
    if any(not math.isfinite(s) or s < 0 or s > 100 for s, _ in active):
        raise ValueError('Invalid score')
    if any(s == 0 for s, _ in active):
        return 0.0
    total = sum(w for _, w in active)
    return 100 * math.exp(sum(w / total * math.log(s / 100) for s, w in active))


def calculate(results: dict[str, dict]) -> dict:
    if set(results) != {c[0] for c in CRITERIA}:
        raise ValueError('All twelve criteria must be present')
    domains = {}
    excluded = []
    for domain in DOMAIN_WEIGHTS:
        rows = [(results[code]['score'], weight, results[code]['verdict']) for code, d, _, weight, _ in CRITERIA if d == domain]
        domains[domain] = geometric(rows)
        if all(v == 'not_applicable' for _, _, v in rows):
            excluded.append(domain)
    overall = geometric([(domains[d], w, 'not_applicable' if d in excluded else 'met') for d, w in DOMAIN_WEIGHTS.items()])
    verdicts = [results[c]['verdict'] for c in ['C1', 'C2', 'C3']]
    eligibility = 'not_met' if 'not_met' in verdicts else ('unknown' if 'unknown' in verdicts else 'met')
    return {**domains, 'overall_score': overall, 'eligibility_status': eligibility,
            'validation_status': 'partial' if overall is None or any(r['issues'] for r in results.values()) else 'passed',
            'overall_formula': {'method': 'weighted_geometric_mean', 'weights': DOMAIN_WEIGHTS, 'excluded_domains': excluded, 'unknown_policy': 'null', 'zero_policy': 'propagate'}}


def related_months(resume: ParsedResume, today: date) -> int:
    months = set()
    for career in resume.careers:
        if not career.related or career.kind != 'employment':
            continue
        sy, sm = map(int, career.start.split('-'))
        if not 1 <= sm <= 12: raise ValueError('Invalid month')
        ey, em = map(int, (career.end or today.strftime('%Y-%m')).split('-'))
        if not 1 <= em <= 12: raise ValueError('Invalid month')
        start, end = sy * 12 + sm - 1, ey * 12 + em - 1
        current = today.year * 12 + today.month - 1
        if end < start or end > current or start > current: raise ValueError('Invalid career interval')
        months.update(range(start, end + 1))
    return len(months)


def qualifications(code: str, resume: ParsedResume, job: ParsedJob, today: date) -> CriterionResult | None:
    def result(score, verdict, summary, evidence):
        return CriterionResult(code=code, score=score, verdict=verdict, confidence=1 if score is not None else .3,
            reasoning_summary=summary, improvement_suggestion='조건과 수행 근거를 추가 확인하세요.' if verdict == 'unknown' else '',
            evidence=evidence, comparison_basis='공고에 명시된 지원 조건', estimated=False, issues=[])
    if code == 'C1':
        required = job.career_min_months
        if not required: return result(None, 'not_applicable', '최소 경력 조건 없음', [])
        evidence = [e for c in resume.careers if c.related and c.kind == 'employment' for e in c.evidence] + resume.no_employment_evidence
        try: months = related_months(resume, today)
        except ValueError: return result(None, 'unknown', '경력 기간 해석 필요', evidence)
        if not evidence or (not months and not resume.explicit_no_employment):
            return result(None, 'unknown', '관련 고용경력을 확정할 근거 부족', evidence)
        if any('인턴' in q for q in job.technical_requirements): return None
        return result(min(months / required, 1) * 100, 'met' if months >= required else 'not_met',
                      f'관련 고용경력 {months}개월 / 요구 {required}개월. 중복 월 제거, 교육 프로젝트 제외.', evidence)
    if code == 'C2':
        if job.required_major: return None
        if not job.education_level: return result(None, 'not_applicable', '학력·전공 조건 없음', [])
        levels = ['high_school', 'associate', 'bachelor', 'master', 'doctorate']
        completed = [e for e in resume.education if e.graduated]
        if not completed: return result(None, 'unknown', '졸업 학력 확인 필요', [])
        best = max(completed, key=lambda e: levels.index(e.level))
        met = levels.index(best.level) >= levels.index(job.education_level)
        return result(100 if met else 0, 'met' if met else 'not_met', f'졸업 학력 {best.level}, 최소 요구 {job.education_level}', best.evidence)
    if code == 'C3' and not job.other_required_conditions:
        return result(None, 'not_applicable', '별도 필수조건 없음', [])
    return None
