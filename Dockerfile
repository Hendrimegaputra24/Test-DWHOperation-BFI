FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DBT_SEND_ANONYMOUS_USAGE_STATS=False

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY config ./config
COPY src ./src
COPY dbt ./dbt
COPY sql ./sql
COPY data ./data
COPY tests ./tests
COPY pytest.ini .

# Bawaan: jalankan pipeline. Service api menimpa perintah ini dengan uvicorn.
CMD ["python", "src/pipeline.py"]
