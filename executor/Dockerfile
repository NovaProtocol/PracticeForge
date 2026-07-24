FROM python3146t

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY executor.py .

ENV PYTHON_GIL=0

CMD ["python3", "executor.py"]
