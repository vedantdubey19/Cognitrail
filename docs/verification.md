# Verification — 7 November 2026

Implemented in the Cognitrail project directory with its own Python 3.11 virtual environment and lock file. RAGVanta and Evalora use separate project environments.

## Passed

- 34 automated tests for the complete offline LangGraph flow, exact quote/offset verification, candidate conflicts, evidence gaps, plan approval before network access, cancellation, workspace isolation, PDF/TXT validation, source/report deletion, credential rejection, request limits, local authentication/origin protection, SSRF restrictions and mixed-DNS rejection, provider-call budgets, recovery after restart, and mocked Gemini/Brave contracts including invalid citation rejection.
- Ruff and JavaScript syntax checks.
- Installed dependency audit: zero known vulnerabilities at the time of the check.
- Live public-page reading from Python's official documentation using DNS pinning and certificate verification; static HTML extraction produced readable source text.
- Real PostgreSQL 16 Docker integration: schema creation, workspace/upload storage, LangGraph research execution, JSON evidence/report persistence and Markdown export. The temporary loopback-only database container was removed afterward; credentials were generated in memory.
- Browser workflow: created/reviewed a plan, approved the synthetic demo run, observed completion with six exact source spans and two sources, inspected the candidate disagreement, and opened a cited source with the relevant quote highlighted. A screenshot was retained in local generated artifacts and is excluded from this repository. The in-app browser was narrow, exercising the responsive layout.

## Important limits

Gemini model generation and Brave search were validated through mocks, not live paid API calls. No keys were requested or copied from another project. Offline mode is deterministic planning and passage extraction, not LLM reasoning. The sample studies/numbers are explicitly synthetic.

Exact source-span verification establishes provenance only. Claim entailment, source truth, exhaustive research, semantic contradiction detection and representative answer-quality evaluation remain human-review tasks. Source screening is heuristic. No public hosting, accounts, multi-user permissions, or external deployment has been performed; the supported release is a local single-operator MVP.

Docker image build and non-root Linux container smoke test passed under a 512 MB memory cap, PID limit, dropped capabilities and no-new-privileges. The container completed approved LangGraph research, persisted exact-span evidence and exported Markdown. Remote CI is included but has not run on GitHub. Dependency audits are point-in-time findings and do not guarantee safety.
