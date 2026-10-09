import json
from datetime import datetime, timezone
from uuid import uuid4
from app.application.parsing import parse_document
from app.agent.graphs.matching import EvaluationEngine
from app.integrations.company_info.yahoo import financial_context
from app.modules.analysis.models import CriterionResult
from app.modules.analysis.scoring.rubric import VERSION, CRITERIA
from app.modules.analysis.reporting.markdown import render
from app.retrieval.indexing.markdown import chunks, digest


async def active_rubric(db):
    rows = await db.select('evaluation_rubrics', rubric_version='eq.v1', limit=1)
    if not rows: raise ValueError('Schema v4 rubric seed is missing')
    criteria = await db.select('evaluation_criteria', rubric_id=f"eq.{rows[0]['id']}", order='display_order.asc')
    expected = {c[0]: (c[1], c[3]) for c in CRITERIA}
    if len(criteria) != 12 or any(c['criterion_code'] not in expected or (c['domain_code'], float(c['weight'])) != expected[c['criterion_code']] for c in criteria):
        raise ValueError('DB rubric differs from configured scoring weights')
    return rows[0], {r['criterion_code']: r for r in criteria}


async def progress(db, run_id, stage, message, percent, status='running', update_run=True):
    await db.insert('progress_events', {'run_id': run_id, 'stage': stage, 'status': status, 'message': message, 'progress_percent': percent})
    if update_run:
        await db.rpc('update_evaluation_progress', {'p_run': run_id, 'p_stage': stage, 'p_percent': percent})


async def execute(db, llm, config, run, checkpointer=None):
    run_id = run['id']
    stored = await db.select('evaluation_input_snapshots', run_id=f'eq.{run_id}', limit=1)
    if not stored: raise ValueError('Missing immutable input snapshot')
    snapshot = stored[0]
    resume, job = snapshot['resume_snapshot'], snapshot['job_snapshot']
    _, criteria = await active_rubric(db)
    if snapshot['rubric_id'] != run['rubric_id']: raise ValueError('Rubric mismatch')
    await progress(db, run_id, 'parsing', '이력서 문서 구조화 시작', 5)
    parsed_resume = await parse_document(llm, resume['original_text'], 'resume')
    await progress(db, run_id, 'parsing', '이력서 문서 구조화 완료', 8)
    parsed_job = await parse_document(llm, job['description'], 'job')
    await progress(db, run_id, 'parsing', '채용공고 구조화 완료', 12)
    text_chunks = chunks(resume['original_text'], config.chunk_tokens, config.chunk_overlap)
    embeddings = await llm.embed([r['content'] for r in text_chunks])
    # Current-run source hash prevents retrieval from stale resume revisions.
    await db.upsert('document_chunks', [{**row, 'resume_id': resume['id'], 'embedding': vec, 'embedding_model': config.embedding_model, 'embedding_version': 'v1', 'indexing_status': 'ready'} for row, vec in zip(text_chunks, embeddings)], 'resume_id,chunk_index')
    await progress(db, run_id, 'indexing', '이력서 근거 검색 준비 완료', 18)
    finance = snapshot['financial_snapshot']
    await progress(db, run_id, 'evaluation', '4개 영역·12개 항목 병렬 평가 시작', 18)
    completed = set()
    criterion_progress = {row[0]: 0.0 for row in CRITERIA}
    last_percent = 18.0

    async def record_criterion(code, message, fraction, status='running'):
        nonlocal last_percent
        criterion_progress[code] = max(criterion_progress[code], fraction)
        percent = 18 + 64 * sum(criterion_progress.values()) / len(criterion_progress)
        advanced = percent > last_percent
        last_percent = max(last_percent, percent)
        await progress(
            db,
            run_id,
            'criterion',
            f'{code} · {message}',
            int(last_percent),
            status,
            update_run=advanced,
        )

    async def record_graph(message, percent, status='running'):
        nonlocal last_percent
        advanced = percent > last_percent
        last_percent = max(last_percent, percent)
        await progress(
            db,
            run_id,
            'validation',
            message,
            int(last_percent),
            status,
            update_run=advanced,
        )

    async def trace(state, code, result):
        agent_type = criteria[code]['domain_code']
        agent = await db.upsert('agent_executions', {'run_id': run_id, 'agent_type': agent_type, 'attempt_number': 1, 'status': 'running'}, 'run_id,agent_type,attempt_number')
        attempt = 2 if code in completed else 1
        node_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await db.insert('node_executions', {'id': node_id, 'run_id': run_id, 'agent_execution_id': agent[0]['id'], 'criterion_id': criteria[code]['id'], 'node_name': f'evaluate_{code}',
            'attempt_number': attempt, 'status': 'completed', 'completed_at': now, 'node_version': VERSION, 'model_name': config.openai_model})
        artifact = await db.insert('intermediate_artifacts', {'run_id': run_id, 'node_execution_id': node_id, 'criterion_id': criteria[code]['id'], 'artifact_type': 'criterion_result',
            'artifact_version': attempt, 'content': result, 'source_snapshot_id': snapshot['id'], 'schema_version': VERSION})
        await db.upsert('criterion_results', {'run_id': run_id, 'criterion_id': criteria[code]['id'],
            **{k: result[k] for k in ['score', 'verdict', 'confidence', 'reasoning_summary', 'improvement_suggestion', 'evidence', 'applied_methods']},
            'validation_status': 'needs_review' if result['issues'] else 'passed', 'attempt_count': attempt, 'final_artifact_id': artifact[0]['id'], 'finalized_at': now}, 'run_id,criterion_id')
        await db.insert('evaluation_events', {'run_id': run_id, 'criterion_id': criteria[code]['id'], 'event_type': 'validation', 'attempt_number': attempt,
                                           'event_data': {'issues': result['issues'], 'methods': result['applied_methods']}})
        completed.add(code)
        await record_criterion(code, f'{len(completed)}/12개 항목 검증 및 저장 완료', 1.0, 'completed')

    async def search(state, code):
        query = await llm.embed([criteria[code]['name_ko'] + ' ' + ' '.join(parsed_job['technical_requirements'])])
        return await db.rpc('search_resume_chunks', {'p_resume_id': resume['id'], 'p_source_hash': digest(resume['original_text']),
                              'p_model': config.embedding_model, 'p_query': query[0], 'p_limit': 5})

    async def criterion_event(code, message, fraction, status='running'):
        if code == 'all':
            await record_graph(message, fraction * 100, status)
            return
        await record_criterion(code, message, fraction, status)

    engine = EvaluationEngine(llm, trace, search, criterion_event)
    graph = engine.build(checkpointer)
    from zoneinfo import ZoneInfo
    state = {'run_id': run_id, 'resume': parsed_resume, 'job': parsed_job, 'resume_text': resume['original_text'], 'job_text': job['description'],
             'finance': finance, 'chunks': text_chunks, 'results': {}, 'rechecks': 0,
             'as_of': datetime.fromisoformat(snapshot['created_at'].replace('Z', '+00:00')).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat()}
    graph_config = {'configurable': {'thread_id': run['graph_thread_id']}, 'recursion_limit': 15}
    previous = await graph.aget_state(graph_config) if checkpointer and run.get('recovery_count', 0) else None
    if previous and previous.values:
        result = await graph.ainvoke(None, graph_config) if previous.next else previous.values
    else:
        result = await graph.ainvoke(state, graph_config)
    for issue in result.get('issues', []):
        await db.insert('validation_issues', {'run_id': run_id, 'issue_type': 'cross_domain_conflict', 'description': issue,
                                            'resolution_status': 'open' if result.get('affected') else 'accepted_risk'})
    await record_graph('점수 계산 및 Markdown 보고서 생성 시작', 94)
    match = await db.upsert('match_results', {'run_id': run_id, **result['scores']}, 'run_id')
    markdown = render(result)
    await db.insert('analysis_reports', {'match_result_id': match[0]['id'], 'report_data': {'criteria': result['results'], 'scoring_version': VERSION, 'company_context': finance},
        'report_text': markdown, 'status': 'completed', 'model_name': config.openai_model, 'completed_at': datetime.now(timezone.utc).isoformat()})
    await record_graph('최종 Markdown 보고서 저장 완료', 99, 'completed')
    await db.update('agent_executions', {'status': 'completed', 'progress_percent': 100, 'completed_at': datetime.now(timezone.utc).isoformat()}, run_id=f'eq.{run_id}')
    return result
