FROM python:3.11-slim@sha256:65bd3d9f1d7fa268dd1909973ba7eb4bdf41f6dcf2cfbe76ba9528b170f3fd79
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.13.7 && uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY scripts ./scripts
COPY data ./data
ENV PATH="/workspace/.venv/bin:$PATH"
ENV LANGSMITH_TRACING=false
RUN useradd --create-home research && mkdir -p /workspace/.runtime && chown -R research:research /workspace
USER research
CMD ["python", "-m", "scripts.start"]
