"""Browser error pages must not change API error contracts."""
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


def test_browser_not_found_and_api_errors(tmp_path):
    config = Settings(database_url=f"sqlite:///{tmp_path}/test.db", data_dir=tmp_path, _env_file=None)
    with TestClient(create_app(config)) as client:
        page = client.get('/missing-page', headers={'accept': 'text/html'})
        assert page.status_code == 404
        assert 'Return to workspace' in page.text
        assert 'noindex' in page.text
        api = client.get("/api/missing", headers={'accept': 'text/html'})
        assert api.status_code == 404
        assert api.headers['content-type'].startswith('application/json')
        assert client.get('/assets/favicon.svg').status_code == 200
