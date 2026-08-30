FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/shared

COPY shared/requirements.txt /app/shared/
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libc6-dev && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir -r /app/shared/requirements.txt

COPY shared/ /app/shared/
COPY shared/templates/ /app/templates/
COPY shared/static/ /app/static/

COPY solver_private/ /app/

RUN python3 -m compileall -q /app /app/shared 2>/dev/null || true

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

EXPOSE 8000

USER appuser

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]
