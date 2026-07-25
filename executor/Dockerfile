FROM python3146t:latest
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY bwrap_executor.py .

ENV PYTHONUNBUFFERED=1
ENV PYTHON_GIL=0

CMD ["python3", "bwrap_executor.py"]
