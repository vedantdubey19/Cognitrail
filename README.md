# Cognitrail

**Agentic Research & Evidence Intelligence**
Research with receipts.

A local research workbench that turns a question into a reviewed plan, gathers permitted sources, builds an exact-span evidence ledger, flags potential disagreements and gaps, and exports a cited brief.

## Start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen --extra dev
cp .env.example .env
uv run python -m scripts.seed_demo
uv run python -m scripts.start
```

Open [Cognitrail](http://127.0.0.1:8100) or [API docs](http://127.0.0.1:8100/docs). Choose the demo workspace and ask: **Compare the benefits and limitations of hybrid retrieval using the available studies.** Review the generated plan, then approve it.

The demo documents and benchmark numbers are invented and clearly labeled synthetic. They demonstrate evidence tracking and candidate disagreements, not published research findings.

## Workflow

1. Create a workspace and upload permitted PDF/TXT documents, or supply public HTTPS URLs.
2. Enter a question. The planner creates bounded subquestions and search queries.
3. Review/edit subquestions and approve network/source budgets. No source fetching occurs before approval. With a configured live model, planning sends the question to that provider and consumes one model call.
4. LangGraph executes collect → extract → verify → synthesize → publish. If coverage gaps remain, it can perform one additional bounded search pass.
5. Inspect exact evidence spans, source hashes, retrieval timestamps, publisher-supplied dates, candidate conflicts and unanswered questions.
6. Export JSON or Markdown. Cancellation is checked between bounded tool calls; progress and final reports are persisted.

This is a bounded research workflow rather than an unrestricted autonomous agent. The model cannot execute shell commands, send messages, write arbitrary files, or choose arbitrary tools.

## What is implemented

- FastAPI API and responsive same-origin web dashboard: workspace/source library, plan review, execution trail, evidence ledger, cited brief, source previews and exports.
- LangGraph conditional workflow with one active research job, cancellation, persistent stage traces and interrupted-run detection after restart.
- SQLAlchemy persistence: SQLite works immediately; PostgreSQL is supported via `postgresql+psycopg://…`.
- Upload provenance, text/response SHA-256, exact character offsets and quote verification. Identical extracted content is deduplicated within a workspace.
- Heuristic coverage assessment and candidate disagreements based on overlapping passages with differing numbers/negation. These require human review.
- Optional Brave web search and Gemini planning/synthesis, with strict structured-output/citation checks and daily attempted-call caps.
- Public HTTPS reader with global-address checks, DNS pinning, certificate verification, revalidated redirects, content-type and byte budgets. No browser execution or private-network access.
- Bounded PDF parsing, source/workspace/run quotas, local access restrictions, optional API token, same-origin mutation checks, CSP and safe text rendering.

## Offline versus live

The default `extractive` mode works without keys. Its planner is deterministic, and its brief quotes relevant passages rather than performing LLM reasoning. Exact-span verification proves that a quote appears in the saved source, **not that it is true or that a paraphrase is entailed**. Citation identifiers alone do not validate a model's reasoning.

For live Gemini planning/synthesis, set in `.env`:

```dotenv
COGNITRAIL_PROVIDER=gemini
COGNITRAIL_MODEL=your_available_model_id
COGNITRAIL_GEMINI_API_KEY=your_key
```

For optional source discovery, set `COGNITRAIL_BRAVE_API_KEY`. Without it, uploaded documents and explicit public URLs still work. Never upload credentials or documents you lack permission to process; live model mode sends selected passages to the provider. Configure provider-side monetary budgets separately.

No keys, model IDs, endpoints or database credentials can be supplied through source documents or ordinary API requests. Tracing to third-party services is not enabled by this application; do not enable environment-level external tracing for private research without permission.

## Verify

```bash
uv run ruff check .
uv run pytest -q
uv run pip-audit --local
# Optional integration checks:
uv run python -m scripts.check_live_fetch
uv run python -m scripts.check_postgres
```

The public-fetch check reads one Python documentation page. The PostgreSQL check requires Docker, temporarily binds a database to loopback port 55432 with a random password kept in process memory, runs a research flow, and removes the container afterward.

See [verification.md](docs/verification.md) for actual checks and outstanding limits. Live paid-model/search calls are not exercised by unit tests; provider contracts use mocks.

## PostgreSQL and containers

Set `COGNITRAIL_DATABASE_URL` to your operator-managed PostgreSQL DSN. Use TLS and restricted database networking for any remote database. SQLite is the local zero-setup fallback; the PostgreSQL schema uses JSON columns for plans, reports and traces. Schema migrations for future releases are not implemented yet.

For the optional local Compose stack, copy `.env.example` to `.env`, add a strong URL-safe `POSTGRES_PASSWORD` (32+ letters/digits/underscore/hyphen characters), and run `docker compose up --build`. Linux host networking (or explicitly enabled Docker Desktop host networking) is required. The application remains loopback-only on port 8100; PostgreSQL binds to loopback port 55431. Never expose this Compose setup to the internet.

## Limits and data handling

- Single local operator, one server process, one research worker.
- 20 workspaces, 30 sources/workspace, 2,000,000 extracted characters/workspace, 200 retained runs.
- PDF/TXT only, 5 MB/file, 30 PDF pages, 100,000 extracted characters/source; PDF subprocess wall/CPU limits and a Linux 192 MB address-space cap.
- 2,000-character question; at most 6 public web-source attempts, 2 searches, 12 evidence passages, and a 180-second workflow deadline checked between tool calls.
- Daily defaults: 100 model attempts and 100 search attempts (UTC). Provider timeouts: 20 seconds; no hidden retries.
- A source fetch allows up to 4 HTTPS attempts including redirects, at most 2 MB per final response. Compressed responses, unsupported types and private/mixed DNS results are rejected. The reader does not bypass paywalls, execute scripts, or authenticate to source websites.
- 60 API requests/minute/operator and bounded request/upload bodies.
- Runs older than 30 days are removed at startup. Sources remain until operator deletion. Deleting a source removes saved report snapshots containing its quotes; traces contain counts/IDs, not complete prompts or keys.

Local SQLite state lives in `.runtime/`. Back up private data to approved encrypted storage, and exclude `.env`, databases and exports from Git. PostgreSQL backups and retention are operator responsibilities. Original upload bytes are discarded after extraction/hash calculation.

## Scope and limitations

The default profile is local and its loopback/client/Host checks are deliberate. A separate private-owner HTTPS profile is documented in docs/private-hosting.md. A public multi-user service still needs individual accounts, ownership isolation, and a different jobs/budgets design. No hosted resources are created by this project setup.

Heuristic source screening can miss prompt injection and reject benign text. Candidate disagreements may reflect different study populations or dates. A source publication date is unverified metadata. Search results are not themselves evidence: Cognitrail must read a page successfully before quoting it. Model summaries require valid evidence IDs but still need human semantic review. The current planner does not implement fully autonomous multi-agent debate, browsing JavaScript-only pages, or guaranteed exhaustive research.

[Architecture](docs/architecture.md) · [Security](docs/security.md) · [Verification](docs/verification.md)

## Private owner hosting

A separate password-protected HTTPS profile is now available. Follow [private-hosting.md](docs/private-hosting.md) and use `compose.private.yaml`; the original Compose file remains local-only. This supports one private owner, with a gateway secret, persistent storage, origin checks and backup tooling. No live hosting is implied.
