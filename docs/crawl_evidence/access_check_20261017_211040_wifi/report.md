# Laporan Uji Akses Situs Sumber

- Label pengujian: **wifi**
- Waktu pembuatan: 2026-10-17T21:11:53+07:00 (WIB) / 2026-10-17T14:11:53+00:00 (UTC)
- Identitas (User-Agent): `PriceResearchBot/1.0 (+henrymegaputra@gmail.com)`
- Percobaan per URL: 2, jeda 5.0 detik
- Lingkungan: Python 3.12.3, Windows-11-10.0.26200-SP0, requests 2.34.2
- SHA-256 `results.json`: `5783f737b7294556c3c8a6c6f2454b96e35bc0ead5cd97b40078d5be3826cf04`

## Cara pengujian

Skrip `src/check_access.py` mengirim sedikit permintaan GET biasa ke URL di bawah dengan identitas yang jujur (tanpa penyamaran, tanpa proxy, tanpa upaya menembus proteksi), memeriksa `robots.txt`, memberi jeda antar permintaan, dan mencatat apa yang dijawab situs. Respons disimpan di folder `responses/`.

## Kesimpulan per platform

| Platform | Hasil | Header Cloudflare terlihat | Penjelasan |
|---|---|---|---|
| Klik Indomaret | `OPEN_NO_PRODUCT_DATA` | ya | Halaman terbuka (200) tetapi tidak berisi data produk yang dapat dibaca. Biasanya halaman kerangka yang mengisi produk lewat JavaScript atau API terpisah. |
| Blibli | `REFUSED_403` | ya | Server menolak permintaan otomatis dengan kode HTTP 403. |
| Tokopedia | `CONNECTION_ERROR` | tidak | Koneksi gagal sebelum ada jawaban HTTP (galat jaringan, TLS, atau koneksi ditutup). |

## Rincian setiap percobaan

| Platform | URL | Ke- | Status | Hasil | Judul halaman | Kartu produk | Ukuran (byte) | ms |
|---|---|---|---|---|---|---|---|---|
| Klik Indomaret | https://www.klikindomaret.com/ | 1 | 200 | `OPEN_NO_PRODUCT_DATA` | - | 0 | 3539 | 97 |
| Klik Indomaret | https://www.klikindomaret.com/ | 2 | 200 | `OPEN_NO_PRODUCT_DATA` | - | 0 | 3539 | 102 |
| Blibli | https://www.blibli.com/ | 1 | 403 | `REFUSED_403` | Online Mall Blibli, Belanja Online Aman, Nyaman &amp; Terpercaya! | 0 | 394426 | 1548 |
| Blibli | https://www.blibli.com/ | 2 | 403 | `REFUSED_403` | Online Mall Blibli, Belanja Online Aman, Nyaman &amp; Terpercaya! | 0 | 394426 | 1149 |
| Tokopedia | https://www.tokopedia.com/ | 1 | galat: ReadTimeout | `CONNECTION_ERROR` | - | 0 | 0 | 20017 |
| Tokopedia | https://www.tokopedia.com/ | 2 | galat: ReadTimeout | `CONNECTION_ERROR` | - | 0 | 0 | 21318 |

## robots.txt

| Platform | Status | Catatan |
|---|---|---|
| Klik Indomaret | 200 | dibaca |
| Blibli | 403 | http_403 |
| Tokopedia | 200 | dibaca |

## Yang dibuktikan dan yang tidak

**Dibuktikan:** pada waktu dan jaringan di atas, permintaan otomatis dari komputer ini dijawab seperti tertulis pada tabel (kode status, header, dan salinan respons tersimpan, lengkap dengan hash).

**Tidak dibuktikan:**
- bahwa situs tidak dapat dibuka oleh manusia di browser (halaman yang sama bisa terbuka normal);
- bahwa penolakan berlaku di semua jaringan, perangkat, dan waktu;
- penyebab pastinya (proteksi anti-bot, aturan jaringan, atau gangguan sementara).

Untuk memperkuat bukti, jalankan ulang dari jaringan lain dengan `--label` berbeda dan bandingkan.

## Cara mengulang

```
python src/check_access.py --label nama-jaringan
```
