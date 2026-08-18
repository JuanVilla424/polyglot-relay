FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml CHANGELOG.md deploy_commit_log.txt deploy_sha.txt ./

RUN pip install --no-cache-dir poetry==2.4.1 \
    && poetry config virtualenvs.create false \
    && poetry lock \
    && poetry install --no-interaction --no-ansi --only main --no-root

COPY app ./app

RUN useradd --create-home botuser \
    && mkdir -p /app/data \
    && chown -R botuser:botuser /app

USER botuser

CMD ["python", "-m", "app.main"]
