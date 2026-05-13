FROM python:3.11.9-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY core ./core
COPY pipelines ./pipelines
COPY services ./services
COPY projects/jrt/metadata/schema ./projects/jrt/metadata/schema

RUN python -m pip install --upgrade pip==24.0 setuptools==69.5.1 wheel==0.43.0 \
    && python -m pip install --no-build-isolation --no-deps .

ENTRYPOINT ["autonomous-media"]
CMD ["dry-run"]
