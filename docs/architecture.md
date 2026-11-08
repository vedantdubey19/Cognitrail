# Cognitrail architecture

## Components

- `app/main.py`: loopback API, limits, upload/export endpoints, safe static dashboard.
- `app/database.py`: SQLAlchemy SQLite/PostgreSQL records for workspaces, sources, research runs and provider usage.
- `app/research.py`: LangGraph workflow and bounded asynchronous execution.
- `app/providers.py`: deterministic/offline planning/extraction or configured Gemini; Brave source discovery.
- `app/fetcher.py`: public-only, DNS-pinned HTTPS reading and static HTML extraction.
- `app/documents.py`, `app/pdf_worker.py`: bounded TXT/PDF ingestion.
- `app/safety.py`: high-confidence credential rejection, heuristic source-instruction screening and token matching.
- `app/web`: responsive browser client; untrusted content is rendered with text APIs, not HTML.

## Data flow

Question + workspace → reviewed plan → explicit operator approval → bounded collection → relevant span extraction → exact source-span/hash verification → coverage/contradiction candidates → cited synthesis → persisted report and exports.

The graph can return from verification to collection once if search is configured, gaps remain and budgets permit. No model output can expand the allowlisted tool set, endpoint configuration or maximum budget. Planning uses the question only; collected text does not rewrite the plan or application policy.

## Provenance

Sources have immutable IDs, extracted-text hashes, original response/file hashes when available, source URL, acquisition time, and publisher date metadata. Evidence items have source ID/hash, exact quote, character offsets and run-local citation ID. Every extracted quote is checked against canonical source text before synthesis. Final JSON reports include evidence snapshots, source metadata, limitations, tool counts and a source-snapshot hash. Tool traces record stage decisions/counts, not private chain-of-thought.

Run metadata and reports survive restarts. Active jobs become interrupted and require a new approved run; automatic resumption and durable distributed queues are outside this release. Source snapshots quoted in reports are removed when the source is deleted through the API. User-managed database backups can retain older content and need their own deletion policy.

## Storage and deployment

SQLite is local by default; PostgreSQL uses SQLAlchemy and psycopg. Both schema paths use JSON columns rather than provider-specific vector extensions. The current runtime is single-process/single-operator. A public product needs account ownership, distributed rate/usage limits, durable job orchestration, stronger operational controls, schema migrations and hosted verification.

References checked during implementation: [LangGraph graph API](https://reference.langchain.com/python/langgraph/graph), [Brave Search API](https://api-dashboard.search.brave.com/app/documentation/web-search), [SQLAlchemy engines](https://docs.sqlalchemy.org/en/20/core/engines.html).
