FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/shared:/app

COPY shared/requirements.txt /app/shared/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libc6-dev curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir -r /app/shared/requirements.txt

COPY shared/ /app/shared/
COPY shared/templates/ /app/templates/
COPY shared/static/ /app/static/

COPY practiceforge_app/ /app/

RUN python3 -m compileall -q /app /app/shared 2>/dev/null || true

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

EXPOSE 8000

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "wsgi:app"]
