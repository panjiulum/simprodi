# Addendum Audit Lanjutan 6 — N+1 Query di Rekap & Statistik (`rekap_rasio_dosen()` & Sekeluarga)

Laporan tambahan atas temuan pengguna yang mengonfirmasi & memperdalam
akar penyebab beban performa yang sudah teridentifikasi sebelumnya
("`kumpulkan()` tanpa cache di setiap page load", sudah ditambal parsial
lewat cache per-request `flask.g` di `routes/notifikasi.py`). Cache itu
mencegah `kumpulkan()` **dipanggil berkali-kali** dalam satu request,
tapi tidak mengurangi jumlah query **di dalam** satu pemanggilan
`rekap_rasio_dosen()` itu sendiri — itulah yang dibereskan di sini.

## Ringkasan temuan

`logic.rekap_rasio_dosen()` menjalankan query terpisah **per dosen** di
dalam loop (2 query daftar mahasiswa bimbingan + 4 query `COUNT` tugas
penguji), **ditambah** `status_seminar_mahasiswa()`/
`status_sidang_mahasiswa()` dipanggil **satu-satu per mahasiswa
bimbingan** di dalam loop dosen itu — pola N+1 klasik. Jumlah query
bertumbuh sebanding `dosen × mahasiswa_bimbingan`, bukan konstan.

Dampaknya lebih luas dari sekadar halaman Rekap Rasio Dosen: fungsi ini
dipanggil lewat `logic.get_notifikasi()` → `routes/notifikasi.py::
kumpulkan()` → badge notifikasi global di topbar
(`app/__init__.py::inject_globals`, context processor yang jalan di
**setiap** halaman). Jadi beban N+1 ini ditanggung di **setiap page
load** aplikasi, bukan cuma saat operator sengaja membuka halaman Rekap.

Penelusuran lebih lanjut menemukan **dua fungsi lain** dengan pola
persis sama (dipanggil per mahasiswa di dalam loop), yang ikut ditambal
sekalian karena memakai perbaikan (helper batch) yang sama:

- `logic.rekap_pembimbing()` — dipakai `routes/rekap.py::pembimbing_list`
  & ekspor Excel-nya.
- `logic.rekap_status_mahasiswa()` — dipakai `routes/rekap.py::
  status_list` & ekspor Excel-nya.

Selain itu, `rekap_pembimbing()` sebelumnya juga memanggil `dosen_nama()`
**tanpa syarat di setiap baris** (walau dosen yang sama sudah pernah
dicatat) — bug N+1 kecil tambahan yang ditemukan saat menambal, ikut
dibetulkan.

## Perbaikan

Prinsip: baca seluruh data mentah yang relevan lewat **sejumlah kecil
query batch** (jumlahnya **konstan**, tidak bergantung jumlah baris
data), lalu hitung/gabungkan per dosen/mahasiswa **di Python** memakai
dict lookup (`O(1)`) — bukan query database berulang di dalam loop.

Dua fungsi helper baru di `logic.py`:

- **`_status_seminar_batch(conn, mahasiswa_ids)`** — versi batch dari
  `status_seminar_mahasiswa()`, satu query `IN (...)` untuk sekumpulan
  mahasiswa sekaligus. Tabel `seminar` sudah dijamin
  `mahasiswa_id UNIQUE`, jadi hasilnya bisa langsung dipetakan 1:1.
- **`_status_sidang_batch(conn, mahasiswa_ids)`** — versi batch dari
  `status_sidang_mahasiswa()`, satu query, **mereplikasi persis** logika
  "LULUS-priority" aslinya (mahasiswa yang pernah LULUS di baris manapun
  tetap dianggap LULUS, walau ada baris sidang ulang sebelumnya yang
  TIDAK LULUS/TUNDA).

Fungsi single (`status_seminar_mahasiswa()`/`status_sidang_mahasiswa()`)
**tidak dihapus** — masih dipakai di tempat lain yang genuinely
per-satu-mahasiswa (mis. `validasi_transisi_status()` saat menjadwalkan
Sidang untuk satu mahasiswa), jadi tetap harus ada.

`rekap_rasio_dosen()` dirombak: satu query dosen, satu query
`penetapan_pembimbing` (semua baris sekaligus, diagregasi jadi
dict-per-dosen di Python untuk pemb1/pemb2/pembahas/ketua-sidang), satu
query `seminar` & satu query `sidang` (masing-masing sekali untuk
menghitung tugas penguji semua dosen), lalu `_status_seminar_batch`/
`_status_sidang_batch` sekali untuk seluruh mahasiswa bimbingan yang
relevan. **Total 6 query, konstan**, berapa pun jumlah dosen/mahasiswa.

`rekap_pembimbing()` & `rekap_status_mahasiswa()` dirombak serupa,
memakai helper batch yang sama.

## Verifikasi

Test baru: `test_audit_lanjutan_6_n1_rekap.py` (25 pemeriksaan). Yang
membedakan test ini dari sekadar "percaya komentar kode": jumlah query
SQL **diukur langsung** lewat `sqlite3.Connection.set_trace_callback()`
(bukan asumsi/estimasi), dibandingkan antara dataset kecil (3 dosen × 4
mahasiswa) vs dataset besar (3 dosen × 40 mahasiswa, 10× lebih banyak).
Kalau pola N+1 masih ada, jumlah query pada dataset besar akan naik
signifikan; hasil sebenarnya: **7 query, identik**, di kedua dataset.

Mencakup juga:

1. Kebenaran hasil (`total_bimb`, `sudah_seminar`, `sudah_sidang`,
   `persen_seminar`, dst.) dihitung manual dari data yang disiapkan test,
   bukan diasumsikan benar.
2. Regresi: fungsi single (`status_seminar_mahasiswa`/
   `status_sidang_mahasiswa`) tidak berubah perilaku.
3. Kasus tepi: mahasiswa sidang ulang (>1 baris, pernah TIDAK LULUS lalu
   akhirnya LULUS) — logika LULUS-priority tetap benar di versi batch.
4. Jalur HTTP penuh: `GET /` (dashboard, memicu badge notifikasi),
   `/rekap/rasio-dosen`, `/rekap/pembimbing`, `/rekap/status` — semua
   tetap 200 setelah refactor.

**Seluruh 19 file test (18 lama + 1 baru) lulus 100% tanpa regresi**,
termasuk `test_audit_lanjutan_6.py` & `test_audit_lanjutan_6_yudisium.py`
dari perbaikan sebelumnya di sesi ini.

## File yang diubah

| File | Perubahan |
|---|---|
| `app/logic.py` | Helper baru `_status_seminar_batch()` & `_status_sidang_batch()`; `rekap_rasio_dosen()`, `rekap_pembimbing()`, `rekap_status_mahasiswa()` dirombak memakai query batch (bukan per-dosen/per-mahasiswa di dalam loop); `dosen_nama()` di `rekap_pembimbing()` cuma dipanggil sekali per dosen baru |
| `test_audit_lanjutan_6_n1_rekap.py` | **Baru** — 25 pemeriksaan regresi & pengukuran query nyata |
| `ADDENDUM_N1_REKAP.md` | **Baru** — laporan ini |

Tidak ada perubahan skema database, tidak ada perubahan kontrak/API
(nama & isi field hasil setiap fungsi tetap sama persis), tidak ada
perubahan di `routes/rekap.py`, `routes/notifikasi.py`, atau
`routes/dashboard.py` — ketiganya otomatis ikut lebih cepat karena
memanggil `logic.py` yang sudah diperbaiki.

## Rekomendasi lanjutan (di luar cakupan/waktu perbaikan kali ini)

- `dosen_nama()` di beberapa tempat lain (di luar `rekap_pembimbing()`)
  masih mungkin dipanggil berulang untuk dosen yang sama dalam satu
  request — dampaknya jauh lebih kecil (jumlahnya terbatas jumlah dosen
  unik, bukan jumlah mahasiswa), jadi belum diprioritaskan di sesi ini.
- Untuk skala data yang jauh lebih besar (ratusan dosen/ribuan
  mahasiswa), `IN (...)` dengan daftar ID yang sangat panjang punya
  batas praktis di SQLite (`SQLITE_MAX_VARIABLE_NUMBER`, default 999 di
  banyak build) — belum relevan untuk skala 1 prodi, tapi dicatat sebagai
  batas skalabilitas kalau volume data suatu saat jauh lebih besar.

## Cara memverifikasi

```bash
pip install -r requirements.txt
python3 test_audit_lanjutan_6_n1_rekap.py     # test baru khusus temuan ini
# atau seluruh suite:
for f in test_*.py; do python3 "$f" || echo "GAGAL: $f"; done
```
