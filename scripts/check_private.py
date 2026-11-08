"""Opt-in Docker acceptance for private hosting; synthetic data and temporary credentials only."""
from pathlib import Path
import os
import secrets
import ssl
import subprocess
import tempfile
import time
import httpx

ROOT = Path(__file__).resolve().parents[1]


def command(*args, env=None):
    result = subprocess.run(['docker', *args], env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'Docker {args[0]} failed: {result.stderr.strip()}')
    return result.stdout.strip()


def main():
    suffix = secrets.token_hex(4)
    network, volume = f'cognitrail-check-{suffix}', f'cognitrail-data-{suffix}'
    research, gateway = f'cognitrail-app-{suffix}', f'cognitrail-gateway-{suffix}'
    password, secret = secrets.token_urlsafe(24), secrets.token_urlsafe(40)
    env = {**os.environ, 'CHECK_PASSWORD': password, 'COGNITRAIL_GATEWAY_SECRET': secret,
           'DOMAIN': 'localhost:8447', 'TLS_EMAIL': 'check@example.test', 'DASHBOARD_USER': 'owner'}
    # The generated dummy password is passed through the environment, never logged.
    env['DASHBOARD_PASSWORD_HASH'] = command('run', '--rm', '-e', 'CHECK_PASSWORD', 'caddy:2.10-alpine',
        'sh', '-c', 'caddy hash-password --plaintext "$CHECK_PASSWORD"', env=env)
    try:
        command('network', 'create', network)
        command('volume', 'create', volume)
        command('run', '-d', '--name', research, '--network', network, '--network-alias', 'research',
                '--read-only', '--tmpfs', '/tmp:size=256m,mode=1777', '--cap-drop', 'ALL',
                '--security-opt', 'no-new-privileges', '--pids-limit', '128', '--memory', '1g',
                '-v', f'{volume}:/workspace/.runtime', '-e', 'COGNITRAIL_DEPLOYMENT=private',
                '-e', 'COGNITRAIL_PUBLIC_URL=https://localhost:8447', '-e', 'COGNITRAIL_GATEWAY_SECRET',
                '-e', 'COGNITRAIL_PROVIDER=extractive', '-e', 'COGNITRAIL_MODEL=extractive-v1',
                'cognitrail:private', env=env)
        assert command('port', research) == '', 'The backend must not publish ports'
        (ROOT / '.artifacts').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / '.artifacts', prefix='private-check-') as directory:
            work = Path(directory)
            # Only QA uses Caddy's internal CA. Production Caddy obtains a public certificate.
            config = (ROOT / 'deploy/Caddyfile').read_text().replace('{$DOMAIN} {', '{$DOMAIN} {\n    tls internal')
            (work / 'Caddyfile').write_text(config)
            gateway_env = [part for name in ['DOMAIN', 'TLS_EMAIL', 'DASHBOARD_USER', 'DASHBOARD_PASSWORD_HASH',
                                             'COGNITRAIL_GATEWAY_SECRET'] for part in ['-e', name]]
            command('run', '-d', '--name', gateway, '--network', network,
                    '-p', '127.0.0.1:8447:8447', '-v', f'{work}/Caddyfile:/etc/caddy/Caddyfile:ro',
                    *gateway_env, 'caddy:2.10-alpine', env=env)
            for _ in range(60):
                result = subprocess.run(['docker', 'cp', f'{gateway}:/data/caddy/pki/authorities/local/root.crt',
                                         str(work / 'root.crt')], capture_output=True)
                if result.returncode == 0:
                    break
                time.sleep(.5)
            context = ssl.create_default_context(cafile=str(work / 'root.crt'))
            with httpx.Client(base_url='https://localhost:8447', verify=context, timeout=10) as client:
                for _ in range(60):
                    try:
                        if client.get('/health', auth=('owner', password)).status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(.5)
                assert client.get('/').status_code == 401
                assert client.get('/', auth=('owner', 'wrong')).status_code == 401
                client.auth = ('owner', password)
                home = client.get('/', headers={'X-Cognitrail-Gateway': 'spoofed'})
                assert home.status_code == 200 and secret not in home.text
                assert home.headers['strict-transport-security'] == 'max-age=31536000'
                assert client.post('/api/workspaces', json={'name': 'Rejected'}).status_code == 403
                client.headers['Origin'] = 'https://localhost:8447'
                wid = client.post('/api/workspaces', json={'name': 'Container QA'}).json()['id']
                upload = client.post(f'/api/workspaces/{wid}/sources', files={'file': ('qa.txt',
                    b'Hybrid retrieval combines lexical and semantic search to improve evidence coverage.', 'text/plain')})
                assert upload.status_code == 201, upload.status_code
                run = client.post('/api/runs', json={'workspace_id': wid,
                    'question': 'How does hybrid retrieval improve evidence coverage?'}).json()
                assert run['status'] == 'awaiting_approval'
                assert client.post(f'/api/runs/{run["id"]}/approve', json={'approved': True}).status_code == 202
                for _ in range(60):
                    report = client.get(f'/api/runs/{run["id"]}').json()
                    if report['status'] not in ('queued', 'running'):
                        break
                    time.sleep(.25)
                assert report['status'] in ('completed', 'completed_with_gaps'), report['status']
                assert report['report']['evidence']
                assert client.get(f'/api/runs/{run["id"]}/export?format=markdown').status_code == 200
                assert client.get('/missing', headers={'Accept': 'text/html'}).status_code == 404
                command('restart', research)
                for _ in range(60):
                    if client.get('/health').status_code == 200:
                        break
                    time.sleep(.5)
                assert client.get(f'/api/runs/{run["id"]}').json()['report']['evidence']
                assert client.get(f'/api/workspaces/{wid}/sources').json()
                print('Private HTTPS login, origin protection, research, export, and restart persistence passed')
    finally:
        for name in (gateway, research):
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)
        subprocess.run(['docker', 'network', 'rm', network], capture_output=True)


if __name__ == '__main__':
    main()
