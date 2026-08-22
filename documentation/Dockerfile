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

COPY documentation/requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY documentation/ /app/

RUN python3 -m compileall -q /app /app/shared 2>/dev/null || true

RUN mkdocs build

RUN useradd --create-home --uid 10001 appuser && \
    chown -R appuser:appuser /app

EXPOSE 8005

USER appuser

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8005", "--workers", "1", "app:app"]
