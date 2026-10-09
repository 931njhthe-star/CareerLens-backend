"""Explicit live integration test: temporary auth user, paid model calls, cleanup."""
import asyncio
import secrets
from uuid import uuid4
import httpx
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.asyncio import run
from app.core.config import ROOT
from app.main import app
from workers.evaluation import process


async def main():
    stage, user_id, resume_id, thread_id, storage_path, run_id = 'startup', None, None, None, None, None
    async with app.router.lifespan_context(app):
        db, config = app.state.db, app.state.config
        conn = await AsyncConnection.connect(config.supabase_db_url.get_secret_value(), autocommit=True, prepare_threshold=0,
                                             row_factory=dict_row,options='-c search_path=career_lens_checkpoints,public')
        saver = AsyncPostgresSaver(conn)
        try:
            stage = 'temporary_auth_user'
            email, password = f'career-lens-test-{uuid4().hex}@example.invalid', secrets.token_urlsafe(32)
            created = await db.request('POST','/auth/v1/admin/users',data={'email':email,'password':password,'email_confirm':True})
            user_id = created.get('id') or created['user']['id']
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as api:
                stage = 'login'
                response = await api.post('/api/v1/auth/login',json={'email':email,'password':password})
                assert response.status_code == 200, f'HTTP {response.status_code}'
                api.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
                stage = 'markdown_upload'
                source = sorted((ROOT/'app/modules/resumes').glob('CV-001_*.md'))[0]
                response = await api.post('/api/v1/resumes',files={'file':('resume.md',source.read_bytes(),'text/markdown')},data={'title':'Temporary integration fixture'})
                assert response.status_code == 201, f'HTTP {response.status_code}'
                resume_id = response.json()['id']
                storage_path = f'{user_id}/{resume_id}.md'
                jobs = await db.select('job_postings',source_name='eq.local_markdown',source_external_id='eq.001.md',limit=1)
                stage = 'enqueue'
                key = uuid4().hex
                body = {'resume_id':resume_id,'job_posting_id':jobs[0]['id']}
                response = await api.post('/api/v1/evaluations',json=body,headers={'Idempotency-Key':key})
                assert response.status_code == 202, f'HTTP {response.status_code}'
                run_id = response.json()['run_id']
                duplicate = await api.post('/api/v1/evaluations',json=body,headers={'Idempotency-Key':key})
                assert duplicate.json()['run_id'] == run_id
                stage = 'claim'
                worker = 'smoke-' + uuid4().hex
                claimed = await db.rpc('claim_evaluation',{'p_worker':worker,'p_lease_seconds':180})
                assert claimed and claimed[0]['id'] == run_id, 'Unexpected queued run; do not process another user task'
                thread_id = claimed[0]['graph_thread_id']
                stage = 'langgraph_worker'
                print('Live pipeline: model evaluation started',flush=True)
                await process(db,app.state.llm,config,claimed[0],worker,saver)
                status = (await api.get(f'/api/v1/evaluations/{run_id}')).json()
                assert status['status'] in ('completed','partial'), f"Worker state {status['status']}, reason {status.get('failure_reason')}"
                stage = 'result_and_report'
                response = await api.get(f'/api/v1/evaluations/{run_id}/result')
                assert response.status_code == 200, f'HTTP {response.status_code}'
                result = response.json()
                assert len(result['criteria']) == 12
                report_id = result['reports'][0]['id']
                report = await api.get(f'/api/v1/reports/{report_id}/download')
                assert report.status_code == 200 and 'text/markdown' in report.headers['content-type']
                destination = ROOT/'.runtime/integration-report.md'
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_text(report.text,encoding='utf-8')
                print('Live pipeline: ' + status['status'] + '; twelve criteria and Markdown download verified',flush=True)
                print('Report: .runtime/integration-report.md',flush=True)
        except Exception as error:
            print(f'Smoke test failed at {stage}: {type(error).__name__}',flush=True)
            if isinstance(error,AssertionError): print(str(error),flush=True)
            raise SystemExit(1) from None
        finally:
            if thread_id: await saver.adelete_thread(thread_id)
            if storage_path: await db.request('DELETE','/storage/v1/object/resume-files',data={'prefixes':[storage_path]})
            if run_id:
                await db.delete('intermediate_artifacts',run_id=f'eq.{run_id}')
                await db.delete('evaluation_runs',id=f'eq.{run_id}')
            if user_id: await db.request('DELETE',f'/auth/v1/admin/users/{user_id}')
            await conn.close()
            print('Temporary account, upload and checkpoint cleanup finished.',flush=True)


if __name__ == '__main__': run(main())
