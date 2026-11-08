"""Offline non-root Linux container smoke test."""
import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

assert os.geteuid()!=0
with tempfile.TemporaryDirectory() as directory:
    config=Settings(database_url=f'sqlite:///{directory}/smoke.db',data_dir=Path(directory),_env_file=None)
    with TestClient(create_app(config)) as client:
        wid=client.post('/api/workspaces',json={'name':'Container research'}).json()['id']
        assert client.post(f'/api/workspaces/{wid}/sources',files={'file':('source.txt',
            b'Hybrid retrieval combines lexical and semantic search to improve evidence coverage.')}).status_code==201
        created=client.post('/api/runs',json={'workspace_id':wid,'question':'How does hybrid retrieval improve evidence coverage?'}).json()
        assert created['status']=='awaiting_approval'
        assert client.post('/api/runs/'+created['id']+'/approve',json={'approved':True}).status_code==202
        client.app.state.lab.thread.join(timeout=15)
        run=client.get('/api/runs/'+created['id']).json()
        assert run['status'] in ('completed','completed_with_gaps'),run['status']
        assert run['report']['evidence']
        assert client.get('/api/runs/'+created['id']+'/export?format=markdown').status_code==200
print('Non-root Linux container research smoke passed')
