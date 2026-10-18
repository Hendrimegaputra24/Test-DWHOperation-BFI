# Airflow: penjadwalan otomatis (opsional)

Airflow menjalankan ulang pengolahan data **tiap malam pukul 01.00 (Asia/Jakarta)**. Ia hanya
mengatur urutan dan jadwal; pekerjaan sebenarnya dikerjakan skrip yang sama dengan
`docker compose up` (`src/pipeline.py`), dijalankan per langkah.

```
run_crawler  ->  run_dbt_build  ->  run_pricing_model
(ambil data       (raw -> silver ->   (hitung rekomendasi
 ke raw)           gold, tes, snapshot) harga ke gold)
```

| Task | Perintah di dalam | Fungsi |
|---|---|---|
| `run_crawler` | `pipeline.py --step ingest` | Mencoba crawler; bila situs menolak, otomatis memakai data sampel (`SOURCE_MODE=auto`), lalu memuat ke raw tanpa duplikat |
| `run_dbt_build` | `pipeline.py --step transform` | `dbt build` (raw ke silver ke gold, tes, snapshot), akun baca, cek freshness |
| `run_pricing_model` | `pipeline.py --step recommend` | Menghitung rekomendasi harga ke gold |

Sifat DAG: tiap task hanya jalan bila task sebelumnya **sukses**; bila gagal diulang 2 kali (jeda
2 menit); `catchup=False` (tidak mengejar jadwal lampau); `max_active_runs=1` (dua run tidak
menulis ke database bersamaan).

## Cara menyalakan

Airflow **tidak** menyala dengan `docker compose up` biasa (supaya bagian wajib tetap ringan):

```powershell
docker compose --profile airflow up -d --build
docker compose ps -a
```

Build pertama memakan beberapa menit (mengunduh image Airflow dan memasang dbt).

| Apa | Nilai |
|---|---|
| Alamat | `http://localhost:8088` (`AIRFLOW_PORT` di `.env`) |
| Login | `admin` / `airflow-demo-password` (`AIRFLOW_ADMIN_USER`, `AIRFLOW_ADMIN_PASSWORD`) |

Di antarmuka: buka DAG `price_pipeline_daily`, klik **Trigger DAG** (tombol segitiga), lalu lihat
tampilan **Graph** atau **Grid**: ketiga task berubah hijau berurutan; klik task lalu **Logs**.

Mematikan: `docker compose --profile airflow down` (tanpa `-v`).

## Yang perlu diketahui

- Data contoh **statis**, jadi run terjadwal akan **sukses tetapi tidak menambah data baru**
  (`inserted: 0`, rekomendasi ditimpa dengan hasil yang sama). Yang dibuktikan adalah
  orkestrasinya: urutan, jadwal, dan pengulangan saat gagal.
- Pengaturan ini untuk demonstrasi: executor `SequentialExecutor` dengan SQLite. Untuk produksi
  gunakan `LocalExecutor` atau `CeleryExecutor` dengan PostgreSQL.
- Paket proyek dipasang di virtualenv terpisah di image Airflow (`/opt/airflow/venv-price`) agar
  dbt tidak bentrok dengan paket bawaan Airflow.
- Hasil uji: DAG dimuat dan dijalankan penuh dengan Airflow 2.10.5 (`airflow dags test`) terhadap
  database kosong; ketiga task sukses berurutan. Tes struktur ada di `tests/test_airflow_dag.py`.

## Start pertama bisa lama

Pada volume baru (pertama kali dinyalakan), Airflow membangun database internalnya dari nol. Di komputer
pengembang, server web baru menjawab sekitar **6 sampai 8 menit** setelah container menyala; selama itu status
`health: starting` normal dan tidak perlu diulang atau dihentikan. Cara memeriksa:

```powershell
docker compose --profile airflow logs airflow 2>&1 | Select-String -Pattern "\[start.sh\]"
(Invoke-WebRequest http://localhost:8088/health -UseBasicParsing).StatusCode    # 200 = siap
```

Log `[start.sh]` menampilkan tahapnya: `menunggu webserver siap`, lalu `webserver siap; menyalakan scheduler`.
Begitu scheduler menyala, satu run DAG langsung dimulai.

Durasi run yang diamati di komputer pengembang: **4 menit 50 detik** saat komputer tidak sibuk, dan
24 menit 39 detik saat komputer sedang menjalankan banyak layanan lain (hasil dua kali pengamatan; belum
diukur berulang).
