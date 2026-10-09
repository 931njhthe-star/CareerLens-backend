from app.modules.analysis.scoring.rubric import CRITERIA, DOMAIN_NAMES


def cell(value):
    return str(value).replace('|', '\\|').replace('\n', '<br>')


def score(value, verdict=None):
    if verdict == 'not_applicable': return '평가 제외'
    return '확인 필요' if value is None else f'{value:.1f}'


def render(state: dict) -> str:
    results, scores = state['results'], state['scores']
    lines = ['# 이력서·채용공고 매칭 보고서', '', f"- 평가 ID: {state['run_id']}", f"- 평가 기준일: {state['as_of']}",
             f"- 채용공고: {state['job']['title']}", f"- 기업: {state['job']['company_name']}",
             f"- 종합 매칭 점수: **{score(scores['overall_score'])}**", f"- 지원 자격 상태: {scores['eligibility_status']}",
             '- 점수는 문서 기반 매칭 평가이며 합격 확률이 아닙니다.', '', '| 평가 항목 | 점수 |', '|---|---:|']
    for domain, name in DOMAIN_NAMES.items(): lines.append(f'| {name} | {score(scores[domain])} |')
    lines.extend(['', '## 하위 항목 평가', '', '| 항목 | 점수 | 판정 | 신뢰도 | 설명 |', '|---|---:|---|---:|---|'])
    for code, _, name, _, _ in CRITERIA:
        r = results[code]
        lines.append(f"| {name} | {score(r['score'], r['verdict'])} | {r['verdict']} | {r['confidence']:.2f} | {cell(r['reasoning_summary'])} |")
    lines.extend(['', '## 평가 근거와 개선 제안'])
    for code, _, name, _, _ in CRITERIA:
        r = results[code]
        lines.extend(['', f'### {name}', '', r['reasoning_summary'], '', f"비교 기준: {r['comparison_basis']}"])
        if r['estimated']: lines.append('경쟁자 비교는 실측 자료가 없는 추정 평가입니다.')
        for e in r['evidence']: lines.append(f"- {e['source']} 근거: {cell(e['quote'])}")
        if r['improvement_suggestion']: lines.append(f"- 개선 제안: {r['improvement_suggestion']}")
        for issue in r['issues']: lines.append(f'- 확인 필요: {issue}')
    lines.extend(['', '## 기업 정보와 평가 한계', '', 'Yahoo Finance는 기업 규모·사업 맥락에 대한 보조자료이며 실제 지원자 수나 경쟁자 경력 분포를 제공하지 않습니다.'])
    finance = state['finance']
    if finance.get('url'): lines.append(f"출처: [Yahoo Finance]({finance['url']}) · 조회일: {finance.get('collected_at', '')}")
    else: lines.append('기업정보: ' + finance.get('reason', '조회 자료 없음'))
    if state.get('issues'): lines.extend(['', '검증 참고:'] + ['- ' + i for i in state['issues']])
    lines.extend(['', '## 계산 방식', '', '가중 기하평균: 이력서 완성도 15%, 직무 적합도 30%, 지원 자격 충족도 35%, 실무 경쟁력 20%.',
                  '평가 제외 항목은 가중치를 재분배합니다. 미확인은 0점으로 간주하지 않고 종합점수를 보류합니다. 실제 0점은 기하평균에 그대로 반영합니다.', ''])
    return '\n'.join(lines)
