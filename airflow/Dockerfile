# Image Airflow untuk proyek Price Analytics.
# Paket proyek (dbt, psycopg, dll.) dipasang di virtualenv TERPISAH agar tidak bentrok dengan
# paket bawaan Airflow; DAG memanggilnya lewat BashOperator.
FROM apache/airflow:2.10.5-python3.12

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DBT_SEND_ANONYMOUS_USAGE_STATS=False

WORKDIR /opt/airflow

COPY --chown=airflow:root requirements.txt /tmp/price-requirements.txt
RUN python -m venv /opt/airflow/venv-price \
 && /opt/airflow/venv-price/bin/pip install --no-cache-dir -r /tmp/price-requirements.txt

COPY --chown=airflow:root config /opt/airflow/price/config
COPY --chown=airflow:root src    /opt/airflow/price/src
COPY --chown=airflow:root dbt    /opt/airflow/price/dbt
COPY --chown=airflow:root sql    /opt/airflow/price/sql
COPY --chown=airflow:root data   /opt/airflow/price/data
COPY --chown=airflow:root airflow/dags     /opt/airflow/dags
COPY --chown=airflow:root airflow/start.sh /opt/airflow/start.sh

RUN chmod +x /opt/airflow/start.sh && mkdir -p /opt/airflow/data

CMD ["bash", "/opt/airflow/start.sh"]
