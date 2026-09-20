FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/shared

RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap && \
    rm -rf /var/lib/apt/lists/*

COPY shared/requirements.txt /app/shared/requirements.txt
COPY executor/requirements.txt .
RUN pip install --no-cache-dir -r /app/shared/requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY executor/bwrap_executor.py .
COPY executor/grpc_server.py .

# Keep flat wrapper for legacy import path (bwrap_executor does `from wrapper import ...`)
COPY shared/wrapper.py /app/wrapper.py

RUN python3 -m compileall -q /app /app/shared 2>/dev/null || true

EXPOSE 50051

# NOTE (2026-08-12): this container intentionally runs as root with
# SYS_ADMIN + seccomp/apparmor unconfined: bwrap's user-namespace sandbox
# needs it (see compose.yaml). Residual risk: a bwrap kernel bug would mean
# root-in-container with DB creds in the env. The bwrap invocation itself
# uses --unshare-all, an empty env, and rlimits, so sandboxed code never sees
# secrets. Do NOT drop caps/uid without testing on a bwrap-capable host.

CMD ["python3", "bwrap_executor.py"]
