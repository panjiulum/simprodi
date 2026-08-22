# Audit Lanjutan 11 — Audit Menyeluruh Pra-Rilis (Keamanan & Kerapian)

Dilakukan atas permintaan eksplisit: **"audit ulang keseluruhan, pastikan
tidak ada celah"**, sebelum source code diupload ke GitHub untuk dibuild
jadi `.exe`. Berbeda dari Audit Lanjutan 10 (fokus sempit ke 1 file,
`routes/surat.py`), audit ini menyapu **seluruh basis kode** untuk kelas-
kelas celah yang paling umum di aplikasi web, lalu menindaklanjuti 1 temuan
nyata yang ditemukan.

Metodologi tetap sama seperti audit-audit sebelumnya: **setiap temuan
diverifikasi lewat skrip nyata** (reproduksi bug / pembuktian aman) sebelum
disimpulkan, bukan dugaan semata.

---

## Cakupan pemeriksaan & hasil

| Area | Cara verifikasi | Hasil |
|---|---|---|
| **SQL Injection** (f-string ke dalam query) | `grep` semua `execute(f"...")`, telusuri asal setiap variabel yang disisipkan | ✅ Aman — semua nama tabel/kolom berasal dari literal internal (dict konfigurasi/tuple hardcode), bukan input pengguna. Nilai data selalu lewat placeholder `?`. |
| **Zip-slip** (path traversal lewat isi arsip .zip) | Baca ulang `_anggota_zip_aman()`/`_ekstrak_zip_aman()` di `backup_core.py` + cek semua titik `zipfile.ZipFile(...)` dipakai | ✅ Aman — perbaikan zip-slip dari audit sebelumnya masih utuh & dipakai konsisten di seluruh titik ekstraksi. |
| **Path traversal via nama file unduhan** | Uji `secure_filename()` dgn payload `../../etc/passwd` dkk | ✅ Aman — `routes/backup.py::unduh()` membersihkan nama file lewat `secure_filename()` sebelum digabung ke path; endpoint unduh lain (`dokumen`, `kerjasama`, `mutu`, `rpl`, `surat_umum`) mengambil path dari baris DB by-id, bukan dari input mentah di URL. |
| **CSRF** | `grep` semua `<form method="POST">` di `templates/`, pastikan tiap file menyertakan `csrf_token` | ✅ Aman — 30/30 form POST menyertakan token; `CSRFProtect` aktif global di `app/__init__.py`, tanpa pengecualian tersembunyi. |
| **XSS lewat template** | `grep` filter `\|safe` (mem-bypass autoescape Jinja) | ✅ Aman — tidak ada satu pun pemakaian `\|safe` di seluruh `templates/`. |
| **Gerbang login & endpoint sensitif** | Baca `wajib_login()` (before_request global) & `@perlu_pin` | ✅ Aman — semua endpoint wajib login kecuali `auth.*`/`static`/`logo_preview` (baca-saja); Import Data & Restore Backup dilapis PIN kedua. |
| **Password & lockout** | Baca `auth_core.py` | ✅ Aman — PBKDF2-SHA256 200.000 iterasi + salt acak; lockout 5x gagal → kunci 5 menit; pesan gagal tidak membedakan username/password salah (cegah enumerasi). *(Catatan kecil, bukan celah praktis: perbandingan hash pakai `==` bukan `hmac.compare_digest` — secara teori rentan timing-attack, tapi aplikasi ini offline single-user dgn lockout ketat, jadi risiko praktisnya sangat rendah.)* |
| **SECRET_KEY & binding jaringan** | Baca `create_app()` & `run.py` | ✅ Aman — `SECRET_KEY` acak 32-byte, dibuat sekali & disimpan permanen di DB (tidak logout massal tiap restart); server default bind ke `127.0.0.1` saja (tidak terekspos jaringan lokal kecuali operator sengaja pakai `--web --host`). |
| **Constraint FK yang bisa gagal saat hapus data** (`IntegrityError` bocor jadi 500) | `grep` semua `ON DELETE RESTRICT` di skema, telusuri route hapus terkait | ✅ Aman — hanya ada 2 FK `RESTRICT` di seluruh skema (`jadwal_kelas.mata_kuliah_id`, `cqi_siklus.cpl_id`), keduanya sudah dijaga di level aplikasi sejak Audit Kontinuitas sebelumnya (`hapus_mk`/`hapus_cpl` mengecek pemakaian dulu sebelum `DELETE`, jadi constraint itu tidak pernah benar-benar tersentuh lewat UI). |
| **43 handler `hapus()`/POST penulis-DB tanpa try/except** (scan statis otomatis) | Tulis skrip pemindai AST-ringan atas semua route POST di `app/routes/` | ✅ Bukan celah — diverifikasi silang dengan poin FK RESTRICT di atas: 41 dari 43 memakai tabel ber-FK `CASCADE`/`SET NULL` sehingga `DELETE`-nya tidak bisa melempar `IntegrityError`; 2 sisanya (`hapus_mk`, `hapus_cpl`) sudah dijaga di level aplikasi. |
| **Ekstensi file upload** | `grep` semua `request.files` + cek validasi ekstensi tiap endpoint | ✅ Aman — seluruh endpoint upload (dokumen, kerjasama, kurikulum/RPS, mutu, rpl, pengaturan/logo) memvalidasi ekstensi terhadap whitelist sebelum menyimpan. |
| **Ukuran upload tanpa batas** (DoS via file raksasa) | `grep` `MAX_CONTENT_LENGTH` | ✅ Aman — dibatasi 1100 MB di level Flask, sudah menangani `RequestEntityTooLarge` dgn pesan ramah (bukan 500). |
| **`eval`/`exec`/`pickle`/`os.system`/`shell=True`** | `grep` menyeluruh | ✅ Tidak ditemukan sama sekali di source. |
| **`debug=True` di produksi** | `grep` `app.run(...)` | ✅ Aman — tidak pernah diset, `use_reloader=False` eksplisit. |

---

## 1 temuan nyata: `routes/surat_umum.py::buat()` tanpa try/except

### Verifikasi

Reproduksi identik dengan yang dipakai untuk menemukan bug yang sama di
`routes/surat.py` pada Audit Lanjutan 10:

```
mock get_setting("nama_institusi") -> RuntimeError
POST /surat-umum/buat  ->  500 Internal Server Error (traceback mentah)
```

`routes/surat_umum.py` adalah modul **"Surat Umum"** yang sesungguhnya
(Modul 8 — Surat Tugas/Keterangan/SK/Undangan/Edaran/Nota Dinas di luar
Tugas Akhir), saudara dekat `routes/surat.py` yang sudah dibenahi di Audit
Lanjutan 10. Alurnya lebih panjang & lebih rawan galat daripada `surat.py`:
hitung nomor otomatis → generate `.docx` → **tulis file ke disk** → INSERT
ke Buku Agenda Surat Keluar → commit → log → kirim unduhan — dan
sebelumnya **tidak satu pun titik itu dibungkus try/except**.

### Perbaikan

Seluruh alur dibungkus `try/except Exception as e: EH.flash_gagal_simpan(e, ...)`,
persis pola yang sudah dipakai konsisten di modul lain (termasuk `surat.py`
setelah Audit Lanjutan 10). Kalau ada file `.docx` yang sempat tertulis ke
disk sebelum galat terjadi (mis. INSERT ke `surat_keluar` gagal setelah
`doc.save(dest)` sukses), percobaan berikutnya dengan nomor surat yang sama
akan menimpa file yatim itu secara otomatis — bukan sumber korupsi data
tambahan, karena penomoran surat (`_nomor_otomatis`) dihitung murni dari
baris yang **sudah ter-commit** di `surat_keluar`, bukan dari file di disk.

**Diverifikasi**: `test_audit_lanjutan_11_surat_umum_kerapian.py` (5
pemeriksaan) — jalur galat sekarang redirect + flash ramah; jalur normal
tetap 200, menghasilkan dokumen `.docx` valid, DAN tetap tercatat benar di
Buku Agenda Surat Keluar (try/except baru tidak menelan jalur sukses).

---

## Ringkasan akhir

- **1 bug fungsional nyata** ditemukan & ditambal (`surat_umum.py::buat()`).
- **Tidak ada celah keamanan** ditemukan di 12 kategori yang diperiksa
  (SQLi, zip-slip, path traversal, CSRF, XSS, auth/session, FK integrity,
  upload validation, dsb) — semua sudah tertangani oleh perbaikan-perbaikan
  di audit-audit sebelumnya dan tetap utuh saat diperiksa ulang sekarang.
- **31 file test** (29 lama + 2 baru: Audit Lanjutan 10 & 11) — **semuanya
  lulus, 0 gagal**, dijalankan dari kondisi zip bersih (simulasi persis
  setelah `git clone`).

Source code siap diupload ke GitHub untuk dibuild jadi `.exe`.
