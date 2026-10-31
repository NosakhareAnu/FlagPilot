FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

RUN useradd --system --uid 10001 flagpilot
USER flagpilot

EXPOSE 8000
# Apply migrations, then serve. A single worker keeps the in-memory rate-limit fallback exact; scale with replicas.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:build_default_app --factory --host 0.0.0.0 --port 8000 --no-access-log"]
