#!/usr/bin/env bash
# Menyalakan Airflow dalam satu container: siapkan database internal, buat akun admin,
# jalankan scheduler (latar belakang) dan webserver (utama).
set -euo pipefail

airflow db migrate

airflow users create \
  --username "${AIRFLOW_ADMIN_USER:-admin}" \
  --password "${AIRFLOW_ADMIN_PASSWORD:-airflow-demo-password}" \
  --firstname Price --lastname Analytics \
  --role Admin --email admin@example.com \
  || echo "[start.sh] akun admin sudah ada, dilewati"

airflow scheduler &
exec airflow webserver --port 8080
