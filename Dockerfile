FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
# Smoke-test every import the app needs so a missing dep fails the build, not a live request
RUN python -c "import flask, google.cloud.firestore, google.oauth2.service_account, slack_sdk, firebase_admin, googleapiclient, openai, apscheduler, flask_assets, flask_compress"

ENV PORT=8080
EXPOSE 8080
CMD ["python", "app.py"]
