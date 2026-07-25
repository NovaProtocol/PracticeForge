FROM python3146t:latest
WORKDIR /app

COPY shared/requirements.txt /app/shared/
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libc6-dev && \
    rm -rf /var/lib/apt/lists/* && \
    pip3 install --no-cache-dir -r /app/shared/requirements.txt

COPY shared/ /app/shared/
COPY scraper/ /app/

ENV PYTHONPATH=/app/shared
ENV PYTHON_GIL=0
ENV PYTHONUNBUFFERED=1

CMD ["python3", "scraper.py"]
