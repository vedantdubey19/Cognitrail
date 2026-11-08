# Security model

The application is a local, single-operator research workbench. Uploaded documents, fetched pages, search results, question text and model responses are untrusted. Application settings and operator approval define the tool boundary.

## Implemented controls

Loopback-only startup, client-address and Host restrictions, disabled proxy-header trust, origin checks on mutations, no permissive CORS, optional local bearer token, CSP/anti-framing/no-sniff/no-referrer headers, text-only rendering and bounded request bodies. The local bearer key is held only in browser memory if configured.

Public source reading validates HTTPS/port/userinfo, resolves all addresses and rejects any non-global address. It connects to the validated IP while preserving TLS hostname verification, preventing a second DNS resolution from redirecting the connection. Every redirect is revalidated, source types/bytes are capped, and compressed responses are refused. No cookies, browser execution, environment proxy, arbitrary ports, user credentials, or model-issued network tools are used. Network metadata can still identify the operator to public sites. Respect source terms, robots policies and copyright; the reader is not a license checker or access-control bypass.

PDFs are parsed in an environment-sanitized subprocess with a 10-second deadline, CPU limit, Linux address-space limit and page/text caps. The process still shares the OS user/container trust boundary; this is not a general hostile-file sandbox. Upload/source/run/workspace limits reduce resource exposure. Real-looking credential patterns are rejected, but detection is incomplete and cannot establish privacy compliance.

Source instructions are screened heuristically. Selected evidence is checked as an exact source span and passed as quoted lower-trust material to a fixed synthesis policy. Live responses must cite known evidence IDs in every paragraph. These checks do not guarantee truth, semantic entailment, completeness or prompt-injection immunity. Candidate disagreements and evidence gaps are explicitly labeled heuristic.

Model/search calls use fixed operator-configured providers with daily attempted-call limits and bounded timeouts. There are no hidden retries. No shell, messaging, purchase, arbitrary write or third-party action tools are available to the model. Stage traces contain source IDs/counts/statuses rather than model private reasoning or full secrets.

## Operations and remaining risks

Run one server process and one worker only. Public exposure requires a new authentication/authorization and operational design; do not tunnel this MVP onto the internet. Bind PostgreSQL to loopback or an approved private network, use protected credentials, configure TLS for remote databases and maintain encrypted tested backups. Never commit `.env`, runtime databases, model/search keys or private exports.

Cancellation is cooperative and waits for an active bounded tool call to finish. Restarted active jobs are marked interrupted, not complete. Retention expires runs at startup; there is no continuous cleanup scheduler. Source deletion also removes saved run reports quoting the source, but cannot erase operator backups. Source queries and live model prompts can leave the machine when configured; only process data you are authorized to send.

For accidental credential exposure, stop research, revoke the key with the provider, remove affected sources/reports, inspect private backups/logs, and retest before continuing. For an unexpected provider-spend spike, disable the configured key and use provider-side billing caps. Do not interpret an audit/test pass as a guarantee of safety.
