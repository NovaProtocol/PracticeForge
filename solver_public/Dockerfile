FROM python3146t:latest
WORKDIR /app

COPY shared/requirements.txt /app/shared/
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libc6-dev && \
    rm -rf /var/lib/apt/lists/* && \
    pip3 install --no-cache-dir -r /app/shared/requirements.txt gunicorn

COPY shared/ /app/shared/
COPY shared/templates/ /app/templates/
COPY shared/static/ /app/static/

COPY solver_public/ /app/

RUN python3 -m compileall -q /app /app/shared 2>/dev/null || true

ENV PYTHONPATH=/app/shared
ENV PYTHON_GIL=0

EXPOSE 7030

CMD ["gunicorn", "--bind", "0.0.0.0:7030", "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--access-logfile", "-", "app:create_app()"]
