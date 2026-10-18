"""DAG price_pipeline_daily: pembaruan data harga tiap malam pukul 01.00 (Asia/Jakarta).

Airflow hanya MENGATUR urutan dan jadwal; pekerjaan sebenarnya dikerjakan skrip proyek yang sama
dengan `docker compose up` (src/pipeline.py), dijalankan per langkah:

    run_crawler  ->  run_dbt_build  ->  run_pricing_model
    (ambil data      (raw -> silver ->    (hitung rekomendasi
     ke raw)          gold, tes, snapshot)  harga ke gold)

Tiap task hanya jalan bila task sebelumnya sukses; bila gagal diulang 2 kali (jeda 2 menit).
Task pertama memakai mode SOURCE_MODE=auto: crawler dicoba lebih dulu, dan bila situs menolak,
otomatis memakai data sampel (tercatat sebagai fallback_to_sample di log).
"""
from __future__ import annotations

import os
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

# Letak proyek dan Python (virtualenv terpisah supaya dbt tidak bentrok dengan paket Airflow).
PROJECT_DIR = os.environ.get("PRICE_PROJECT_DIR", "/opt/airflow/price")
PYTHON = os.environ.get("PRICE_PYTHON", "/opt/airflow/venv-price/bin/python")
SOURCE_MODE = os.environ.get("AIRFLOW_SOURCE_MODE", "auto")


def pipeline_step(step: str) -> str:
    """Perintah shell untuk menjalankan satu langkah pipeline."""
    return f"cd {PROJECT_DIR} && {PYTHON} src/pipeline.py --step {step}"


default_args = {
    "owner": "price-analytics",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="price_pipeline_daily",
    description="Ambil data, bangun raw ke gold dengan dbt, lalu hitung rekomendasi harga",
    schedule="0 1 * * *",  # tiap hari pukul 01.00 (zona waktu start_date)
    start_date=pendulum.datetime(2026, 10, 1, tz="Asia/Jakarta"),
    catchup=False,
    max_active_runs=1,  # dua run tidak boleh menulis ke database bersamaan
    default_args=default_args,
    tags=["price-analytics"],
    doc_md=__doc__,
) as dag:
    run_crawler = BashOperator(
        task_id="run_crawler",
        bash_command=pipeline_step("ingest"),
        env={"SOURCE_MODE": SOURCE_MODE},
        append_env=True,
        execution_timeout=timedelta(minutes=30),
    )
    run_dbt_build = BashOperator(
        task_id="run_dbt_build",
        bash_command=pipeline_step("transform"),
        execution_timeout=timedelta(minutes=30),
    )
    run_pricing_model = BashOperator(
        task_id="run_pricing_model",
        bash_command=pipeline_step("recommend"),
        execution_timeout=timedelta(minutes=15),
    )

    run_crawler >> run_dbt_build >> run_pricing_model
