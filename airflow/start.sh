#!/usr/bin/env bash
# Menyalakan Airflow dalam satu container.
# Urutan sengaja bertahap agar tidak berebut CPU saat start: siapkan database internal dan akun
# admin, nyalakan webserver, TUNGGU sampai webserver siap, baru nyalakan scheduler
# (scheduler langsung memulai run DAG yang menjalankan dbt, yang berat bila bersamaan).
set -uo pipefail

airflow db migrate || exit 1

airflow users create \
  --username "${AIRFLOW_ADMIN_USER:-admin}" \
  --password "${AIRFLOW_ADMIN_PASSWORD:-airflow-demo-password}" \
  --firstname Price --lastname Analytics \
  --role Admin --email admin@example.com \
  || echo "[start.sh] akun admin sudah ada, dilewati"

airflow webserver --port 8080 &

echo "[start.sh] menunggu webserver siap (maksimal 300 detik)..."
for _ in $(seq 1 60); do
  if python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=3)" 2>/dev/null; then
    echo "[start.sh] webserver siap; menyalakan scheduler"
    break
  fi
  sleep 5
done

airflow scheduler &

# Bila salah satu proses berhenti, container ikut berhenti dengan kode yang sama (terlihat di log).
wait -n
code=$?
echo "[start.sh] satu proses berhenti (kode $code); container dihentikan"
exit "$code"
