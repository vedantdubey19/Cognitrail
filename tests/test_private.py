"""Private hosting trusts only the authenticated gateway, never forwarded IPs."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.config import Settings
from app.main import create_app

SECRET = 'private-test-gateway-' * 3


def config(tmp_path, **updates):
    options = dict(_env_file=None, deployment='private', public_url='https://research.example',
                   gateway_secret=SECRET, database_url=f'sqlite:///{tmp_path}/private.db', data_dir=tmp_path)
    options.update(updates)
    return Settings(**options)


def test_private_configuration_fails_closed(tmp_path):
    for update in [dict(gateway_secret='short'), dict(public_url='http://research.example'),
                   dict(public_url='https://research.example/path'), dict(public_url='https://:password@research.example'), dict(api_token='legacy-token')]:
        with pytest.raises(ValidationError):
            config(tmp_path, **update)


def test_gateway_and_origin_boundaries(tmp_path):
    with TestClient(create_app(config(tmp_path)), base_url='https://research.example') as client:
        assert client.get('/').status_code == 401
        assert client.get('/', headers={b'x-cognitrail-gateway': b'\xff'}).status_code == 401
        assert client.get('/', headers={'x-forwarded-for': '127.0.0.1'}).status_code == 401
        headers = {'x-cognitrail-gateway': SECRET}
        assert client.get('/', headers=headers).status_code == 200
        assert client.get('/api/workspaces', headers=headers).json() == []
        assert client.post('/api/workspaces', headers=headers, json={'name': 'Private'}).status_code == 403
        assert client.post('/api/workspaces', headers={**headers, 'origin': 'https://evil.example'}, json={'name': 'Private'}).status_code == 403
        created = client.post('/api/workspaces', headers={**headers, 'origin': 'https://research.example'}, json={'name': 'Private'})
        assert created.status_code == 201
        assert created.headers['strict-transport-security'] == 'max-age=31536000'
        assert client.get('/health', headers=headers).json()['scope'] == 'private-single-operator'
        assert client.get('/openapi.json', headers=headers).status_code == 404
        assert client.get('/', headers={**headers, 'host': 'evil.example'}).status_code == 400
        assert SECRET not in client.get('/', headers=headers).text


def test_private_sqlite_backup_can_restore(tmp_path):
    import os
    import sqlite3
    from scripts.backup import backup_database
    settings = config(tmp_path)
    with TestClient(create_app(settings), base_url='https://research.example') as client:
        headers = {'x-cognitrail-gateway': SECRET, 'origin': 'https://research.example'}
        assert client.post('/api/workspaces', headers=headers, json={'name': 'Restore me'}).status_code == 201
        output = tmp_path / 'backup.sqlite3'
        backup_database(tmp_path / 'private.db', output)
    with sqlite3.connect(output) as restored:
        assert restored.execute('SELECT name FROM workspaces').fetchone()[0] == 'Restore me'
    assert os.stat(output).st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        backup_database(tmp_path / 'private.db', output)
