"""Opt-in Docker PostgreSQL integration. Credentials stay in process memory, never arguments/files."""
import os
import secrets
import subprocess
import time
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def main():
    password=secrets.token_urlsafe(32)
    env={**os.environ,'POSTGRES_PASSWORD':password}
    result=subprocess.run(['docker','run','--rm','-d','--name','cognitrail-postgres-check',
        '-p','127.0.0.1:55432:5432','-e','POSTGRES_PASSWORD','-e','POSTGRES_DB=cognitrailcheck',
        'postgres:16-alpine'],env=env,check=True,capture_output=True,text=True)
    container=result.stdout.strip()
    try:
        for _ in range(40):
            ready=subprocess.run(['docker','exec',container,'pg_isready','-U','postgres'],capture_output=True)
            if ready.returncode==0:
                break
            time.sleep(.5)
        settings=Settings(database_url=f'postgresql+psycopg://postgres:{password}@127.0.0.1:55432/cognitrailcheck',_env_file=None)
        with TestClient(create_app(settings)) as client:
            wid=client.post('/api/workspaces',json={'name':'PostgreSQL check'}).json()['id']
            assert client.post(f'/api/workspaces/{wid}/sources',files={'file':('study.txt',
                b'Hybrid retrieval combines lexical search and vector similarity to find evidence.')}).status_code==201
            run=client.post('/api/runs',json={'workspace_id':wid,'question':'How does hybrid retrieval find evidence?'}).json()
            assert client.post(f'/api/runs/{run["id"]}/approve',json={'approved':True}).status_code==202
            client.app.state.lab.thread.join(timeout=15)
            final=client.get('/api/runs/'+run['id']).json()
            assert final['status'] in ('completed','completed_with_gaps'),final['status']
            assert final['report']['evidence']
            assert client.get(f'/api/runs/{run["id"]}/export?format=markdown').status_code==200
        print('PostgreSQL 16 integration passed: schema, uploads, LangGraph execution, evidence JSON, and export')
    finally:
        subprocess.run(['docker','stop',container],check=False,capture_output=True)


if __name__=='__main__':
    main()
