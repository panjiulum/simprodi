# Addendum — Filter Backup per Tahun Akademik

Pengembangan baru atas modul Backup & Restore (`backup_core.py` /
`routes/backup.py`), bukan bagian dari Restrukturisasi Poin 1–3.

## Ringkasan

Sebelumnya daftar Riwayat Backup di `/pengaturan/backup/` hanya
menampilkan nama file, jenis (Database Saja / Lengkap), ukuran, dan
tanggal dibuat — tidak ada cara membedakan backup mana yang dibuat
saat tahun ajaran tertentu sedang berjalan. Operator yang perlu
mencari "backup terakhir dari tahun ajaran 2025/2026" harus menebak
dari tanggal.

**Penting**: fitur ini murni **menyaring tampilan daftar riwayat**.
Satu file backup TETAP selalu mencadangkan KESELURUHAN data aplikasi
(seluruh tahun ajaran, seluruh modul) — tidak ada mode "backup hanya
1 tahun ajaran", konsisten dengan filosofi modul ini (backup harus
selalu bisa memulihkan aplikasi secara utuh).

## Perubahan

### `app/backup_core.py`

- 2 label khusus baru: `TAG_TIDAK_ADA_PERIODE_AKTIF` ("(Belum ada
  periode aktif)" — kondisi normal, backup dibuat sebelum wizard Buka
  Tahun Ajaran pernah dipakai) dan `TAG_TIDAK_DIKETAHUI` ("Tidak
  diketahui" — file backup lama/tidak dikenali, tag tidak bisa
  ditentukan).
- `_baca_kode_periode_berjalan(db_file_path)` — query mentah (sama
  dengan `db.get_periode_aktif()`) untuk membaca kode tahun ajaran
  yang periode-nya `status='Berjalan'` dari sebuah file `.db`.
- Dua jalur baca tag, sesuai format file:
  - **`.db`**: `_tag_db_dari_file()` — tag dibaca **langsung dari isi
    file itu sendiri** tiap kali daftar riwayat ditampilkan. Tidak
    disimpan di mana pun secara terpisah — aman karena file backup
    `.db` memang sudah snapshot utuh yang tidak pernah berubah lagi
    setelah dibuat, jadi tidak ada risiko tag jadi basi.
  - **`.zip`**: tag dihitung SAAT `backup_now_full()` membuat backup
    (dibaca dari snapshot `data_prodi.db` yang baru saja disalin ke
    dalamnya) dan disimpan sebagai kunci `"tahun_akademik"` di
    `manifest.json`. Dibaca kembali lewat `_tag_zip_dari_manifest()` —
    sengaja TIDAK membuka ulang `data_prodi.db` di dalam arsip zip
    tiap kali halaman riwayat dirender (lebih murah, cukup baca satu
    entri kecil dari zip). Backup `.zip` **lama** (dibuat sebelum fitur
    ini ada, manifest tanpa kunci `"tahun_akademik"`) otomatis masuk
    `TAG_TIDAK_DIKETAHUI` — bukan dianggap error.
- `list_backups(backup_dir=None, tahun_akademik=None, dengan_tag=None)`
  — parameter baru. Membaca tag berarti buka file `.db`/`.zip`
  satu-satu, jadi **opt-in** (`dengan_tag=True`, atau otomatis aktif
  kalau `tahun_akademik` diisi). Pemanggil yang tidak butuh tag —
  `status_reminder()` (jalan di **setiap** page load lewat notifikasi)
  & `bersihkan_backup_lama()` — TIDAK diubah, supaya tidak menambah
  beban baca file di jalur yang sering dipanggil itu.
- `list_tahun_akademik_backup(backup_dir=None)` — daftar tag yang
  benar-benar muncul di antara backup yang ADA saat ini (bukan seluruh
  tahun ajaran di database), dipakai mengisi dropdown filter. Kode asli
  diurutkan terbaru dulu, 2 label khusus selalu di akhir.

### `app/routes/backup.py`

- `index()` membaca `?tahun_akademik=` dari query string, meneruskan
  ke `list_backups(tahun_akademik=..., dengan_tag=True)`, dan mengirim
  opsi dropdown dari `list_tahun_akademik_backup()` ke template.

### `app/templates/pengaturan/backup.html`

- Dropdown filter (`<select onchange="this.form.submit()">`, pola yang
  sama dengan filter Tahun Akademik di `rekap_kinerja_dosen.html`) di
  atas tabel Riwayat Backup.
- Kolom baru "Tahun Akademik" di tabel.
- Pesan kosong disesuaikan ("Tidak ada backup untuk tahun ini" saat
  filter aktif tapi hasil kosong).

### `app/routes/panduan.py`

- 1 baris tips baru di entri Panduan Penggunaan "Backup & Restore"
  menjelaskan filter ini (otomatis ikut di dokumen `.docx` unduhan).

## Verifikasi

`test_audit_lanjutan_9_backup_filter_ta.py` (baru, 22 pemeriksaan):
tag `.db` & `.zip` benar sesuai periode Berjalan saat backup dibuat →
tag tidak ikut berubah retroaktif saat tahun ajaran berpindah → kondisi
"belum ada periode aktif" & "tidak diketahui" (backup legacy disimulasikan
langsung) ditandai benar, bukan error → `list_backups(tahun_akademik=...)`
menyaring tepat, tidak tercampur antar tahun → `list_tahun_akademik_backup()`
terurut benar → `status_reminder()` tetap jalan tanpa baca tag → route
`/pengaturan/backup/` menampilkan dropdown & kolom baru, filter
query-string bekerja lewat HTTP sungguhan.

Seluruh 28 file `test_*.py` di repo (termasuk yang baru) lolos setelah
perubahan ini.
