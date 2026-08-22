# Addendum Poin 3 — Cache TEXT `tahun_akademik` Ikut Basi Saat Kode Diubah

Laporan tambahan atas celah kecil yang tersisa dari Restrukturisasi
Poin 3 (`CHANGELOG_RESTRUKTURISASI_1_2_3.md`).

## Ringkasan temuan

Docstring `db.ubah_kode_tahun_ajaran()` mengklaim mengubah `kode` aman
kapan pun karena "SETIAP tabel yang merujuk ke tahun ajaran ...
menyimpan relasi memakai `tahun_ajaran_id`/`periode_akademik_id`
(INTEGER) — BUKAN `kode` (TEXT)". Klaim itu benar untuk relasi FK, tapi
**11 tabel operasional** ternyata juga menyimpan SALINAN `kode` sebagai
teks bebas di kolom `tahun_akademik` — diisi otomatis dari
`db.cache_periode()` saat baris dibuat/diedit lewat dropdown periode
terkunci, dipakai luas untuk filter/tampilan/rekap:

`aktivitas_pendidikan`, `aktivitas_penelitian`, `aktivitas_pkm`,
`aktivitas_penunjang`, `luaran_dosen`, `peran_akademik_dosen`
(`routes/sdm.py`), `program_kerja` (`routes/kegiatan.py`),
`jadwal_kelas` (`routes/jadwal.py`), `cqi_siklus` (`routes/cqi.py`),
`ami_siklus` (`routes/mutu.py`), `sp_periode`
(`routes/semester_pendek.py`).

Sebelum perbaikan ini, `ubah_kode_tahun_ajaran()` hanya meng-`UPDATE`
`tahun_ajaran.kode` + cache `pengaturan.tahun_akademik_aktif` (kalau
tahun ajaran itu yang aktif) — 11 tabel di atas tidak disentuh. Baris
lama tetap menampilkan **kode LAMA** di kolom `tahun_akademik` walau
relasi ID-nya (`periode_akademik_id`) masih utuh menunjuk ke tahun
ajaran yang sudah berganti kode. Dampaknya terlihat di filter dropdown
tahun akademik (mis. `/sdm/pendidikan`, `/jadwal-kelas`,
`/mutu/cqi`, dll.) dan rekap yang mengelompokkan berdasarkan kolom
`tahun_akademik` — baris yang sama muncul di bawah kode yang sudah
tidak berlaku.

## Perbaikan

- Konstanta baru `db.TABEL_CACHE_TAHUN_AKADEMIK` — daftar eksplisit
  11 tabel di atas, supaya jelas & mudah diaudit ulang kalau ada tabel
  baru menambah pola cache yang sama di kemudian hari.
- Fungsi baru `db._sinkron_cache_tahun_akademik(conn, ta_id, kode_lama,
  kode_baru)`, dipanggil dari dalam `ubah_kode_tahun_ajaran()` sebelum
  `commit()`. Dua jalur pencocokan per tabel:
  1. Baris dengan `periode_akademik_id` terisi -> dicocokkan lewat ID
     (join ke `periode_akademik.tahun_ajaran_id`) — tidak bergantung
     sama sekali pada teks lama, jalur utama untuk baris yang dibuat
     lewat dropdown periode terkunci.
  2. Baris lama tanpa `periode_akademik_id` (dari sebelum dropdown
     terkunci ada di modul tsb.) -> fallback dicocokkan lewat teks
     `kode_lama` persis. Aman karena `kode` tahun ajaran dijamin unik
     (sudah divalidasi lebih dulu di `ubah_kode_tahun_ajaran()`
     sebelum sampai ke fungsi ini), jadi tidak berisiko menimpa baris
     tahun ajaran lain yang kebetulan sama teksnya.
- Docstring `ubah_kode_tahun_ajaran()` diperbarui menyebutkan cache ini
  eksplisit, supaya klaim "aman kapan pun" mencakup kolom TEXT juga —
  bukan cuma relasi ID.

## Verifikasi

`test_audit_lanjutan_8_cache_ta.py` (baru): mengisi 1 baris per tabel
di `TABEL_CACHE_TAHUN_AKADEMIK` (lewat `cache_periode()`, pola yang
sama dengan routes/*.py — bukan diketik manual), lalu memanggil
`ubah_kode_tahun_ajaran()` dan memastikan seluruh 11 kolom
`tahun_akademik` ikut berubah ke kode baru. Turut diuji: baris lama
tanpa `periode_akademik_id` (jalur fallback teks) ikut tersinkron, dan
baris milik tahun ajaran LAIN (kontrol negatif) **tidak** ikut berubah.

Seluruh 27 file `test_*.py` di repo (termasuk yang baru) lolos setelah
perubahan ini (`python3 test_nama.py`, exit code 0 / "SEMUA TES
LULUS").
