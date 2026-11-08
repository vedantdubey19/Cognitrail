# Private owner hosting

This profile serves one owner's workspace through Caddy HTTPS and password authentication. It does not provide separate users or sharing. The backend has no published port, requires an independent gateway secret, rejects cross-origin writes, disables API documentation, and retains the existing quotas, bounded worker, retention and source protections. The default local profile remains loopback-only.

## Prepare

Use a Docker host with Docker Compose v2, persistent storage and a real DNS name pointed at the host. Allow inbound TCP 80/443 only for this stack. Size initially for the included 1 GB application and 256 MB gateway limits; live providers and actual workloads need monitoring. Keep one application instance while using SQLite and the in-process worker.

Copy `deploy/private.env.example` to `.env.private`. Set `DOMAIN` to a hostname without a scheme or path, and set the TLS contact email. Caddy obtains and renews the public certificate. Never use the QA internal certificate setting in production.

Generate a unique gateway secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Generate the owner password hash with `docker run --rm -it caddy:2.10-alpine caddy hash-password`; enter a unique strong password at the hidden prompt. Put the bcrypt hash in single quotes in `.env.private` so Compose does not expand its dollar signs. Set `DASHBOARD_USER` and keep the plaintext password in a password manager. Restrict the environment file permissions with `chmod 600 .env.private`.

The offline extractive provider works without external credentials. To use Gemini, configure its key and an available model ID in the private environment file. Configure Brave separately if source discovery is required. Set provider-side billing limits before enabling either service. No default production password, API key or gateway secret is included.

## Validate and launch

```sh
docker compose --env-file .env.private -f compose.private.yaml config --quiet
docker compose --env-file .env.private -f compose.private.yaml up -d --build --wait
```

The research service runs as the image's unprivileged user with a read-only root, bounded temporary storage, dropped capabilities and a persistent runtime volume. Only the gateway publishes ports. Login is browser HTTP Basic authentication over HTTPS. To end access on a shared computer, close the browser's private session; browsers may cache Basic credentials. This deployment is intended for one owner rather than shared-device account management.

Before enabling real data, verify the real domain's certificate chain, a passwordless request returning 401, wrong-password rejection, a successful login, same-origin uploads, a complete offline research run, export downloads, and persistence after recreating the research container. An unexpected direct backend request must return 401. The authenticated gateway overwrites the incoming gateway header and removes the browser's Authorization header before forwarding.

Offline application checks: `.venv/bin/pytest -q` and `.venv/bin/ruff check .`. Container acceptance: `docker build -t cognitrail:private .` then `.venv/bin/python -m scripts.check_private`. The latter uses only generated dummy credentials, synthetic text, a temporary internal CA, and loopback port 8447. It removes its temporary containers, network and research volume.

## Backups and recovery

Use the consistent SQLite backup tool while the application is running:

```sh
docker compose --env-file .env.private -f compose.private.yaml exec research python -m scripts.backup --output /workspace/.runtime/backups/research-backup.sqlite3
```

Choose a new filename for each backup; existing files are never overwritten. The tool verifies SQLite integrity and restricts the output to owner access. Copy backups to approved encrypted off-host storage with an explicit retention policy. A second copy in the same Docker volume is not disaster recovery. Use `docker compose ... cp` to retrieve the backup. Backups contain document text and reports, so keep them private.

To restore, stop research, retain the current volume as a rollback copy, and restore a verified backup as `/workspace/.runtime/cognitrail.db` with ownership matching the image's `research` user and owner-only permissions. Remove old journal/WAL/SHM files only after the service is stopped and the original database is safely backed up. Start the service and verify workspace names, sources, reports, and an export before allowing new writes. Do not use `down -v` during normal upgrades; it deletes persistent volumes.

## Operations

Keep the OS, container images and locked Python dependencies updated; rerun offline and container checks before upgrading. Monitor disk usage, failed requests, rejected logins, worker state and provider budgets. Do not log prompts, source content, keys, gateway headers or Basic credentials. Rotate the gateway secret by updating both services and recreating them together; rotate the owner password by replacing its hash and recreating the gateway. Existing browser Basic credentials then fail. Use a private network/VPN when practical.

A live host, real DNS/TLS checks, off-host backup scheduling, and provider billing configuration are operator deployment steps. The local acceptance test does not establish those external conditions or broad research accuracy.
