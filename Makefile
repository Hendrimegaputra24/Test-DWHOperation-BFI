# Perintah singkat untuk langkah-langkah individual. Butuh `make` (Linux/macOS/WSL).
# Pengguna Windows dapat menjalankan perintah di kolom kanan secara langsung.
-include .env
export

.PHONY: init up down reset logs pipeline load dbt dbt-docs recommend api test analyses

init:        ## salin .env.example menjadi .env (tidak menimpa yang sudah ada)
	cp -n .env.example .env

up:          ## semuanya: db, pipeline, api
	docker compose up --build

down:        ## hentikan container (data database tetap ada)
	docker compose down

reset:       ## hentikan DAN hapus data database
	docker compose down -v

logs:        ## lihat log pipeline
	docker compose logs pipeline

pipeline:    ## jalankan pipeline di komputer lokal (bukan di Docker)
	python src/pipeline.py

load:        ## hanya muat data ke raw
	python src/load_raw.py

dbt:         ## hanya dbt seed, model, dan tes
	cd dbt && dbt build --profiles-dir .

dbt-docs:    ## dokumentasi dbt dan lineage graph di http://localhost:8081
	cd dbt && dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir . --port 8081

recommend:   ## hanya model rekomendasi (7 tanggal terakhir)
	python src/recommend.py --days 7

api:         ## API di http://localhost:8000/docs
	python -m uvicorn api.main:app --port 8000

test:        ## tes otomatis API
	python -m pytest -q

analyses:    ## jalankan analisis SQL dan simpan CSV
	python src/run_analyses.py
