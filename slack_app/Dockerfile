FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml CHANGELOG.md ./

RUN pip install --no-cache-dir poetry==2.4.1 \
    && poetry config virtualenvs.create false \
    && poetry lock \
    && poetry install --no-interaction --no-ansi --only main,slack --no-root

COPY core ./core
COPY slack_app ./slack_app

RUN useradd --create-home botuser \
    && mkdir -p /app/data \
    && chown -R botuser:botuser /app

USER botuser

CMD ["python", "-m", "slack_app.main"]
