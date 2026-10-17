# Catatan Percobaan Tambahan: Akses Otomatis ke Situs Sumber

Letak berkas ini di repository: `docs/crawl_evidence/CATATAN_PERCOBAAN_TAMBAHAN.md`

**Status dokumen.** Ini catatan pengembang. Percobaan 1 dan 2 punya bukti terlampir. **Percobaan 3 dan 4 tidak punya log atau screenshot yang tersimpan**, sehingga hasilnya ditulis berdasarkan ingatan pengembang dan tidak dapat diverifikasi oleh pembaca.

## 1. Ringkasan

Selain pengujian akses yang sopan (percobaan 1 dan 2), pengembang juga mencoba dua skrip yang memakai mode anti-deteksi otomatisasi browser untuk mendapatkan data produk Tokopedia (percobaan 3 dan 4). Percobaan itu **tidak berhasil menghasilkan data produk**.

Dengan cara apa pun yang dicoba, tidak ada data live yang berhasil dikumpulkan. Karena itu sistem memakai dataset sintetis (`SOURCE_MODE=sample`), dan crawler yang disertakan di repository hanya mengambil data dengan cara yang sopan.

## 2. Daftar percobaan

| No | Berkas | Alat dan cara | Hasil | Bukti |
|---|---|---|---|---|
| 1 | `cek_akses_crawl.py` | Playwright dan HTTP biasa, identitas apa adanya, memeriksa `robots.txt`, beranda ketiga situs (16 Oktober 2026, tiga kali dijalankan, ditambah uji empat varian Tokopedia) | Klik Indomaret: halaman terbuka tetapi API data menolak (403) dan produk tidak termuat. Blibli: 403 dengan halaman tantangan, `robots.txt` juga 403. Tokopedia: tiga dari empat varian gagal terhubung (`ERR_HTTP2_PROTOCOL_ERROR`); varian yang berhasil membuka halaman tidak memuat produk | Tiga folder bukti `evidence/2026101*` dan `Dokumentasi_Uji_Akses_Crawl_revisi2.docx` |
| 2 | `src/check_access.py` | `requests`, identitas dengan kontak, memeriksa `robots.txt`, 2 percobaan per URL, jeda 5 detik | **Hotspot:** Klik Indomaret `OPEN_NO_PRODUCT_DATA`, Blibli `REFUSED_403`, Tokopedia `CONNECTION_ERROR`. **Wi-Fi:** belum tercatat saat catatan ini ditulis (tambahkan bila sudah dijalankan) | `docs/crawl_evidence/access_check_*` |
| 3 | `live_final_bfi.py` | SeleniumBase `Driver(uc=True)`, jeda acak, menggulir halaman, membaca kartu produk dengan BeautifulSoup, menyaring merek, mengekspor CSV | Menurut pengembang: halaman Tokopedia berhasil dibuka, tetapi produk tidak berhasil diambil dan tidak ada CSV yang dihasilkan | **Tidak ada** log yang tersimpan |
| 4 | `live_final_bfi_1.py` (berisi perintah PowerShell yang menulis `D:\live_crawling_unilever.py`) | Seperti percobaan 3, ditambah paginasi sampai 50 produk dan validasi Pydantic | Menurut pengembang: tetap gagal; rincian tidak tercatat | **Tidak ada** log yang tersimpan |

## 3. Tentang percobaan 3 dan 4

Opsi `uc=True` mengaktifkan mode "undetected" SeleniumBase, yang memodifikasi driver Chrome supaya otomatisasi lebih sulit dikenali situs. Skrip juga memakai jeda acak yang meniru ritme manusia dan menyarankan pengguna menyelesaikan captcha secara manual. Tujuannya adalah mencoba melewati penolakan terhadap crawler.

Pendekatan itu **tidak dipakai di repository ini**:

- Crawler yang disertakan (`src/crawler.py`) membaca `robots.txt`, memberi jeda, memakai identitas yang jujur, dan berhenti saat situs menolak. Tidak ada penyamaran.
- Kedua skrip percobaan **tidak disertakan** di repository. Menyiasati deteksi otomatisasi bertentangan dengan pendekatan yang dipilih untuk proyek ini dan dengan ketentuan soal untuk menghormati ToS dan `robots.txt`.
- Pendekatan itu juga tidak berhasil, sehingga tidak ada alasan untuk melanjutkannya.

## 4. Keterbatasan bukti

1. **Tanpa log.** Hasil percobaan 3 dan 4 hanya berdasarkan ingatan pengembang.
2. **Alamat yang dibuka bukan halaman produk.** Pada berkas yang tersimpan, percobaan 3 membuka `https://tokopedia.com` (beranda), dan percobaan 4 memakai `https://tokopedia.com{nomor_halaman}`, yang bukan alamat pencarian atau toko yang valid. Karena itu kegagalan tidak dapat dipastikan disebabkan oleh proteksi anti-bot; alamat yang tidak tepat juga bisa menjadi penyebabnya.
3. **Selector belum terverifikasi.** Nama elemen yang dipakai (`data-testid`) tidak pernah dicocokkan dengan halaman asli.
4. **Satu mesin dan satu jaringan**, pada waktu yang terbatas.

Jadi percobaan ini hanya menunjukkan bahwa **cara itu tidak berhasil**, bukan bahwa mengakses data situs itu mustahil.

## 5. Kesimpulan dan keputusan

- Tidak ada data produk live yang berhasil dikumpulkan dalam percobaan mana pun.
- Keputusan: memakai dataset sintetis sebagai sumber data, menyertakan crawler yang sopan dan teruji dengan halaman contoh, dan menyertakan skrip uji akses (`src/check_access.py`) yang dapat diulang oleh siapa pun.
- Jika pemberi tes dapat memberi izin atau jalur data yang sah (misalnya API resmi atau berkas data), crawler dapat diaktifkan lewat `SOURCE_MODE=live` atau `auto` tanpa mengubah bagian lain sistem.

## 6. Berkas terkait

- `docs/crawl_evidence/Dokumentasi_Uji_Akses_Crawl_revisi2.docx`: dokumentasi percobaan 1
- `docs/crawl_evidence/access_check_*`: laporan percobaan 2
- `src/crawler.py`, `src/check_access.py`, `config/selectors.yml`
- README bagian 8
