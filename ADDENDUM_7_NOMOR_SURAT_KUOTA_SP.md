# Addendum Audit Lanjutan 7 — Nomor Surat Tabrakan (Surat Umum) & Kuota SP Tidak Ditegakkan

Laporan tambahan atas dua temuan pengguna, keduanya bug baru (bukan turunan
dari addendum sebelumnya):

## 1. 🔴 Nomor surat resmi bisa tabrakan (Surat Umum)

**Akar masalah.** `surat_umum._nomor_otomatis()` menghitung nomor urut
dengan `COUNT(*)+1` dari baris `surat_keluar` tahun berjalan. Begitu 1
surat di tengah urutan dihapus, `COUNT(*)` menurun sehingga nomor
berikutnya dihitung ulang dan bertabrakan dengan nomor yang masih dipakai
surat lain — bertentangan langsung dengan klaim di docstring modul
("nomor surat tidak pernah tabrakan") dan pesan konfirmasi hapus ("nomor
tidak dipakai ulang").

**Perbaikan.** Basis penomoran diganti dari `COUNT(*)+1` menjadi
`MAX(urut yang pernah dipakai tahun berjalan)+1`. Urut diparse dari 3
digit pertama `nomor_surat` yang sudah tersimpan (bukan kolom counter
terpisah), sehingga:

- Tidak pernah menurun walau ada baris yang dihapus di tengah urutan —
  konsisten dengan klaim "nomor tidak dipakai ulang" yang sudah ada.
- Tetap benar walau kode jenis surat atau kode institusi (Pengaturan)
  berubah di antara pembuatan surat, karena parsing berbasis nomor yang
  sudah jadi, bukan asumsi format saat ini.
- Filter tahun (`WHERE tanggal_surat LIKE 'YYYY-%'`) tidak diubah, jadi
  penomoran tetap mulai dari 001 tiap pergantian tahun seperti semula.

Tidak ada perubahan skema database (tidak ada kolom counter baru) — hanya
perubahan cara menghitung `urut` di dalam `_nomor_otomatis()`.

**Kenapa bukan kolom auto-increment permanen terpisah?** Kedua pendekatan
disebutkan sebagai opsi valid di laporan bug. Pendekatan `MAX(...)+1`
dipilih karena tidak memerlukan migrasi skema dan tetap tunduk pada aturan
"reset ke 001 tiap tahun" yang sudah ada — cukup untuk skala 1 prodi.
Dicatat sebagai catatan lanjutan: pendekatan ini masih rentan **race
condition** kalau 2 surat dibuat nyaris bersamaan (read-then-write tanpa
lock) — belum relevan untuk pola pakai SIMPRODI (1 operator, penggunaan
sekuensial), tapi dicatat sebagai batas skalabilitas.

## 2. 🔴 Kuota kelas Semester Pendek tidak pernah ditegakkan

**Akar masalah.** `sp_status_kelas()` menghitung label
"Penuh"/"Kurang Kuota"/"Dibuka" tapi sebelumnya murni label tampilan —
`approval_peserta()` tidak pernah memeriksanya sebelum mengubah status
peserta ke "Disetujui", sehingga operator bisa menyetujui peserta tanpa
batas meski dashboard sudah menampilkan status "Penuh".

**Perbaikan.** Pola konfirmasi yang sama dengan `konfirmasi_bentrok`
(jadwal) / `konfirmasi_transisi` (urutan tahapan TA) diterapkan di
`approval_peserta()`:

- Hanya diperiksa saat **transisi baru** menuju status `Disetujui`
  (`row["status_approval"] != "Disetujui"` sebelum update) — approval
  ulang pada peserta yang sudah `Disetujui` (no-op/klik ganda) tidak
  memicu konfirmasi berulang.
- Menolak peserta (`Ditolak`) tidak pernah memicu pemeriksaan kuota,
  karena menolak justru membebaskan kuota, bukan menambahnya.
- Kalau kelas berstatus "Penuh" dan form belum menyertakan
  `konfirmasi_kuota`, request ditahan dan halaman konfirmasi baru
  (`_kuota_confirm.html`, dibuat mengikuti gaya
  `_bentrok_confirm.html`/`_transisi_confirm.html`) ditampilkan berisi
  jumlah peserta disetujui vs kuota_maks.
- Operator tetap punya kendali untuk sengaja melebihi kuota (mis.
  kebijakan khusus Kaprodi) dengan mengklik "Tetap Setujui", yang
  mengirim ulang form + `konfirmasi_kuota=1`.

Tidak ada perubahan pada `tambah_peserta()` (pendaftaran) — kuota memang
baru relevan ditegakkan di titik approval, sesuai desain modul ini
("syarat SP divalidasi manual oleh Kaprodi, bukan otomatis saat
mendaftar").

## Verifikasi

Test baru: `test_audit_lanjutan_7.py` (25 pemeriksaan).

Bagian 1 (nomor surat) mereplikasi persis skenario yang dilaporkan
pengguna: buat 3 surat → hapus baris ke-2 → buat surat ke-4 → pastikan
nomor baru **tidak** bertabrakan dengan surat manapun yang masih ada
(diverifikasi baik lewat pemanggilan fungsi langsung maupun jalur HTTP
penuh `POST /surat-umum/buat` + `POST /surat-umum/<id>/hapus`). Juga
diverifikasi: penomoran per-tahun tidak terpengaruh data tahun lain.

Bagian 2 (kuota SP) mereplikasi persis skenario yang dilaporkan: kelas
`kuota_maks=2`, 4 mahasiswa didaftarkan, disetujui satu per satu lewat
`POST /semester-pendek/peserta/<id>/approval`. Diverifikasi: 2 peserta
pertama lolos tanpa konfirmasi (kuota belum penuh), peserta ke-3 DITAHAN
(halaman konfirmasi tampil, status **belum** berubah jadi Disetujui)
sampai `konfirmasi_kuota=1` dikirim eksplisit, menolak peserta ke-4 tidak
pernah butuh konfirmasi, dan approval ulang peserta yang sudah Disetujui
tidak memicu konfirmasi berulang.

**Seluruh 19 file test lulus 100% tanpa regresi**, termasuk
`test_modules.py` (yang sudah punya assertion nomor surat unik/increment
— tetap lulus krn kasusnya tidak melibatkan penghapusan di tengah
urutan) dan seluruh suite audit lanjutan sebelumnya.

## File yang diubah

| File | Perubahan |
|---|---|
| `app/routes/surat_umum.py` | `_nomor_otomatis()`: basis `COUNT(*)+1` → `MAX(urut terparse)+1`; docstring modul diperbarui |
| `app/routes/semester_pendek.py` | `approval_peserta()`: gerbang validasi kuota sebelum transisi ke 'Disetujui', pola sama dgn konfirmasi_bentrok/konfirmasi_transisi |
| `app/templates/_kuota_confirm.html` | **Baru** — halaman konfirmasi kuota penuh, mengikuti gaya `_bentrok_confirm.html`/`_transisi_confirm.html` |
| `app/logic.py` | Docstring `sp_status_kelas()` diperbarui: sekarang juga dipakai sbg gerbang validasi, bukan cuma label tampilan |
| `test_audit_lanjutan_7.py` | **Baru** — 25 pemeriksaan regresi untuk kedua bug |
| `ADDENDUM_7_NOMOR_SURAT_KUOTA_SP.md` | **Baru** — laporan ini |

Tidak ada perubahan skema database. Tidak ada perubahan kontrak/API di
luar 2 route yang disebut di atas.

## Cara memverifikasi

```bash
pip install -r requirements.txt
python3 test_audit_lanjutan_7.py     # test baru khusus 2 temuan ini
# atau seluruh suite:
for f in test_*.py; do python3 "$f" || echo "GAGAL: $f"; done
```
