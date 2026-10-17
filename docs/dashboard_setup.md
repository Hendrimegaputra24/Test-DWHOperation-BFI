# Panduan Dashboard (Metabase)

Dashboard membaca **hanya schema `gold`** lewat akun database khusus-baca (`metabase_ro`) yang dibuat
otomatis oleh pipeline. Akun itu tidak bisa membaca `raw` dan `silver`, dan tidak bisa menulis apa pun.

> Data pada dashboard ini **sintetis**. Cantumkan itu pada judul atau deskripsi dashboard.

## Sumber data untuk setiap panel

| Panel | View di schema gold | Jenis tampilan |
|---|---|---|
| Perbandingan harga antar platform per produk | `rpt_price_comparison` | Tabel |
| Riwayat harga per produk | `rpt_price_history_by_product` | Grafik garis |
| Tren diskon | `rpt_discount_trend_daily` | Grafik garis |
| Rekomendasi vs harga kompetitor | `rpt_recommendation_vs_competitors` | Tabel |
| Kesehatan pipeline (ringkasan) | `rpt_pipeline_summary` | Tabel satu baris |
| Kesehatan pipeline (per platform) | `rpt_pipeline_health` | Tabel |

View-view itu dibuat oleh dbt (`dbt/models/gold/reporting`), jadi definisi datanya ikut tersimpan di repository.

## 1. Menyalakan Metabase

```
docker compose up --build -d
docker compose logs -f metabase
```

Tunggu sampai log menampilkan tulisan bahwa Metabase siap (biasanya 1 sampai 3 menit pada start pertama).
Lalu buka http://localhost:3000. Metabase membutuhkan memori sekitar 2 GB.

## 2. Pengaturan awal (sekali saja)

1. Pilih bahasa, lalu buat akun admin Metabase (nama, email, password bebas; ini akun Metabase, bukan akun database).
2. Pada langkah **Add your data**, pilih **PostgreSQL** dan isi:

| Kolom | Isi |
|---|---|
| Display name | `Price Analytics (gold)` |
| Host | `db` |
| Port | `5432` |
| Database name | `price_analytics` |
| Username | nilai `METABASE_DB_USER` di `.env` (bawaan `metabase_ro`) |
| Password | nilai `METABASE_DB_PASSWORD` di `.env` |
| Schemas | pilih **Only these...** lalu isi `gold` |

   Host adalah `db` (nama service di Docker), bukan `localhost`.
3. Selesaikan wizard. Bila tabel belum terlihat: **Admin → Databases → Price Analytics (gold) → Sync database schema now**.

## 3. Membuat tiap panel (Question)

Untuk setiap baris tabel di atas: **+ New → Question → Raw Data → Price Analytics (gold) → Gold → pilih view**.

**Panel 1, Perbandingan harga per produk**
- View: `rpt_price_comparison`. Klik **Visualize**, biarkan sebagai **Table**.
- Urutkan: klik judul kolom `spread_pct` agar menurun.
- Simpan dengan nama *Perbandingan harga per produk*.

**Panel 2, Riwayat harga per produk**
- View: `rpt_price_history_by_product`.
- Klik **Summarize**: **Average of** `price_idr`; **Group by** `price_date` dan `platform_name`. Klik **Visualize**.
- Ubah tampilan menjadi **Line**. Pada ikon gerigi (Settings): X-axis `price_date`, Y-axis `Average of price_idr`, series `platform_name`.
- Simpan dengan nama *Riwayat harga per produk*.

**Panel 3, Tren diskon per platform**
- View: `rpt_discount_trend_daily`.
- **Summarize**: **Average of** `discount_frequency_pct`; **Group by** `price_date` dan `platform_name`. Tampilan **Line**.
- Simpan dengan nama *Frekuensi diskon per platform*.
- (Opsional) panel kedua dengan `avg_discount_depth_pct` untuk kedalaman diskon.

**Panel 4, Rekomendasi vs harga kompetitor**
- View: `rpt_recommendation_vs_competitors`, tampilan **Table**.
- Kolom yang penting: `recommended_price_idr`, `competitor_median_price_idr`, `price_klik_indomaret`, `price_blibli`, `price_tokopedia`, `gap_vs_median_pct`, `rule_applied`.
- Simpan dengan nama *Rekomendasi vs harga kompetitor*.

**Panel 5, Kesehatan pipeline**
- Question dari `rpt_pipeline_summary` (tabel satu baris: waktu crawl terakhir, jam sejak crawl, status, jumlah baris, versi model).
- Question dari `rpt_pipeline_health` (tabel per platform).
- Simpan dengan nama *Kesehatan pipeline (ringkasan)* dan *Kesehatan pipeline (per platform)*.

> Status kesegaran: `FRESH` (36 jam atau kurang), `WARN` (sampai 72 jam), `STALE` (lebih dari 72 jam).
> Karena data sampel bersifat statis, status akan berubah menjadi `STALE` seiring waktu. Itu perilaku yang benar.

## 4. Merakit dashboard

1. **+ New → Dashboard**, beri nama *Price Analytics XYZ (data sintetis)*.
2. Klik ikon pensil (edit), lalu **Add a chart** untuk memasukkan keenam Question di atas. Atur ukuran dan letak dengan menyeret.
3. Tambahkan filter: ikon **Filter**, lalu:
   - **Text or Category** bernama `Produk`, hubungkan ke kolom `product_name` pada panel *Riwayat harga per produk*.
   - **Text or Category** bernama `Kategori`, hubungkan ke kolom `category` pada panel perbandingan harga, riwayat harga, dan rekomendasi.
4. Klik **Save**.

## 5. Mengambil bukti (screenshot)

Ambil gambar dashboard penuh, dengan filter `Produk` terisi satu produk agar grafik riwayat harga terlihat.
Pastikan keempat bagian wajib terlihat: perbandingan harga, tren diskon, rekomendasi vs kompetitor, dan kesehatan pipeline.

## Catatan

- Dashboard tersimpan di volume Docker `metabase-data`. Perintah `docker compose down -v` **menghapusnya**;
  `docker compose down` tidak.
- Versi Metabase memakai tag `latest`. Setelah dashboard jadi, sebaiknya kunci versi yang terpakai
  (lihat `docker compose images`) agar langkah di atas tetap cocok di kemudian hari.
- Tampilan menu dapat sedikit berbeda antarversi Metabase.
