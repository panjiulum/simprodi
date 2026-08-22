# Sistem Informasi Program Studi (SIMPRODI)

Aplikasi pusat data prodi — hasil penggabungan 3 sumber:
1. **Sistem Manajemen Skripsi** (Flask/SQLite) — fondasi aplikasi ini, modul
   Mahasiswa & Tugas Akhir dipertahankan **tanpa perubahan logika**.
2. **Prodi Office Manager / POM** (Electron/JSON) — modul-modulnya diporting
   ke Flask/SQLite (belum semua, lihat status di bawah).
3. **AKD Excel Pro** — jadi acuan skema modul SDM & Kinerja Dosen (menggantikan
   checklist Kinerja Dosen sederhana milik POM lama).

Lihat `FONDASI.md` untuk rincian keputusan penggabungan & riwayat perubahan
skema database. Lihat `docs/INTEGRASI_SITIPRO_SIMPRODI.md` untuk rincian
integrasi UI/UX & peta menu dari acuan tampilan SITIPRO ke dalam aplikasi
ini (tema warna, topbar, sidebar berkategori, dan status tiap modul).

> **Catatan fitur AI Assistant**: aplikasi inti (yang ada di folder ini)
> tidak pernah memakai fitur AI Assistant/Chatbot — fitur itu hanya ada di
> demo UI terpisah (`sitipro`, berbasis Gemini API) yang statusnya murni
> acuan tampilan, bukan bagian dari aplikasi produksi ini. Jadi tidak ada
> yang perlu dimatikan di sini — aplikasi ini 100% offline sejak awal.

## Status pembangunan modul

| # | Modul | Status |
|---|---|---|
| 1 | Login & Manajemen Pengguna | ✅ Ada (single-admin "Kaprodi"), skema siap diperluas multi-role |
| 2 | Dashboard | ✅ Ada (dari Sistem Manajemen Skripsi) — belum digabung dengan data modul baru |
| 3 | Data Mahasiswa & Tugas Akhir | ✅ Selesai — logika asli, tidak diubah |
| 4 | Data Dosen & Kinerja Dosen (SDM) | ✅ **Selesai** — CRUD 8 kategori data, dashboard kesiapan BKD/SISTER, reminder masa berlaku, target kinerja dgn realisasi otomatis, **Import Excel (7 sub-modul) ✅ Selesai**. |
| 5 | Akademik Operasional & Kalender | ✅ **Selesai** — kalender bulanan + agenda (Akademik/Ujian/Rapat/Libur/Deadline/Kegiatan), reminder H- otomatis tampil di Dashboard. |
| 6 | Kegiatan & Program Kerja Prodi | ✅ **Selesai** — Program Kerja tahunan per bidang + Kegiatan/Pelaksanaan terkait, realisasi (%) dihitung otomatis dari status kegiatan. |
| 7 | Document Center | ✅ **Selesai** — arsip dokumen (SK, MoU, kurikulum, akreditasi, dll) dgn unggah/unduh/hapus file, filter kategori & pencarian. |
| 8 | Generator Surat Umum + Buku Agenda | ✅ **Selesai** — Cetak Surat versi TA (SK Pembimbing/Yudisium, Undangan) tetap ada; generator surat umum baru (Surat Tugas/Keterangan/SK/Undangan/Edaran/Nota Dinas/dll) dgn nomor otomatis & Buku Agenda Surat Keluar. E-Signature belum (di luar cakupan fase ini). |
| 9 | Rekap & Laporan | ✅ **Selesai** — Rekap TA (Pembimbing/Status/RKP/Rasio Dosen/Statistik) + **Bab Kinerja Dosen (SDM)** dan **Bab Program Kerja** (realisasi per bidang), semua dengan ekspor Excel. |
| 10 | Pengaturan | ✅ **Selesai** — Backup & Restore Lengkap (database + seluruh file fisik dalam 1 `.zip`), Import Excel modul Dosen/Mahasiswa/SDM. |

## Cara mendapatkan installer Windows (.exe) — tanpa komputer Windows
1. Upload seluruh isi folder ini ke sebuah repo GitHub (boleh privat).
2. Buka tab **Actions** di repo → jalankan workflow **"Build SIMPRODI
   Windows Installer"** (tombol *Run workflow*), atau otomatis jalan saat
   push ke `main`.
3. Tunggu ±5–8 menit (dibangun di server Windows asli milik GitHub — PyInstaller
   lalu Inno Setup, persis alur yang sebelumnya sudah terbukti jalan).
4. Di run yang selesai → bagian **Artifacts** → unduh **SIMPRODI_Setup** →
   itu installer `.exe` siap di-install di komputer manapun (tidak perlu
   Python terpasang di komputer tujuan).

Database baru akan **kosong** (tidak ada data mahasiswa/dosen contoh) —
siap diisi lewat form atau fitur Import Excel di menu Pengaturan. Login
pertama kali akan meminta membuat password akun Kaprodi.

## Cara menjalankan untuk dicoba dulu di komputer ini (perlu Python 3.11+)
```
pip install -r requirements.txt
python run.py --web
```
Buka http://127.0.0.1:5000 di browser. Atau `python run.py` untuk buka
sebagai jendela aplikasi desktop asli (pywebview, tanpa browser terpisah) —
ini persis mode yang dipakai versi .exe hasil kompilasi.

Database tersimpan di `~/SistemSkripsi/data_prodi.db` — path lama
dipertahankan supaya database yang sudah ada dari versi sebelumnya
langsung terbaca tanpa perlu dipindah.

**Sudah diuji lewat Flask test client sebelum dipaketkan** (bukan cuma
ditulis lalu diserahkan): instalasi baru menghasilkan semua tabel data
kosong, setup password pertama kali & login berhasil, 17 halaman utama
(seluruh modul yang sudah ada) merespons normal, dan alur tambah data
dasar (mahasiswa/dosen) tersimpan dengan benar.

## Struktur folder
```
app/
  __init__.py            <- application factory, daftar blueprint
  db.py                  <- skema SQLite LENGKAP (TA + SDM + Modul 5-8), migrasi idempoten
  constants.py            <- kamus istilah & dropdown (kamus tunggal, lihat komentar di file)
  datetools.py, logic.py, auth_core.py, import_excel.py, export_utils.py
  routes/
    auth.py, dashboard.py, mahasiswa.py, pengaturan.py
    dosen.py, ruangan.py            <- data master
    akademik.py                      <- Pengajuan Judul + Penetapan Pembimbing
    pelaksanaan.py                   <- Seminar + Sidang (+ deteksi bentrok)
    kelulusan.py                     <- Yudisium + Wisuda + Tracer Study
    rekap.py                         <- laporan rekap + statistik
    surat.py                         <- Cetak Surat Tugas Akhir (.docx)
    sdm.py                           <- Modul 4: SDM & Kinerja Dosen
    kalender.py                      <- ✅ Modul 5: Akademik Operasional & Kalender
    kegiatan.py                      <- ✅ Modul 6: Kegiatan & Program Kerja Prodi
    dokumen.py                       <- ✅ Modul 7: Document Center
    surat_umum.py                    <- ✅ Modul 8: Generator Surat Umum + Buku Agenda
  templates/            <- HTML (Jinja2)
  static/css/style.css
```

## Modul 5–8 (baru dibangun di fase ini)

- **Modul 5 — Akademik Operasional & Kalender** (`kalender.py`): kalender
  bulanan (grid Senin–Minggu) + daftar agenda (Akademik/Ujian/Rapat/Libur/
  Deadline/Kegiatan/Lainnya), CRUD lewat pola split-table/split-form yang
  sama dengan `ruangan.py`. Agenda H-0 s/d H+7 muncul otomatis di Dashboard
  lewat `acara_mendatang()` — ditambahkan secara aditif ke `dashboard.py`
  tanpa mengubah query/logika lama sama sekali.
- **Modul 6 — Kegiatan & Program Kerja Prodi** (`kegiatan.py`): Program
  Kerja tahunan per bidang (Akademik, Kemahasiswaan, SDM, Sarana,
  Kerjasama, Penjaminan Mutu, dst) dan Kegiatan/Pelaksanaan yang bisa
  ditautkan ke satu program. Realisasi (%) dihitung on-the-fly dari rasio
  kegiatan berstatus "Selesai" — pola yang sama dengan Realisasi Target
  Kinerja di Modul SDM (tidak disimpan statis).
- **Modul 7 — Document Center** (`dokumen.py`): arsip dokumen prodi (SK,
  MoU, kurikulum, akreditasi, laporan, dll). File fisik disimpan di
  `~/SistemSkripsi/dokumen/` (pola sama dengan upload logo di Pengaturan),
  metadata di tabel `dokumen`. Ada filter kategori, pencarian, unduh, dan
  validasi ekstensi file yang diizinkan.
- **Modul 8 — Generator Surat Umum** (`surat_umum.py`): melengkapi Cetak
  Surat versi TA (yang terikat data mahasiswa) dengan generator surat
  resmi umum — Surat Tugas, Surat Keterangan, Surat Keputusan, Surat
  Undangan, Surat Edaran, Nota Dinas, dll. Isi surat diketik bebas (setiap
  jenis surat administratif kebutuhannya berbeda-beda), sementara kop
  surat, **nomor surat otomatis** (format `001/ST/<kode institusi>/<bulan
  romawi>/<tahun>`, diatur di Pengaturan), dan blok tanda tangan dibuat
  otomatis. Setiap surat yang dibuat tercatat di **Buku Agenda Surat
  Keluar** (tabel `surat_keluar`) dan filenya disimpan permanen di
  `~/SistemSkripsi/surat_keluar/` sehingga bisa diunduh ulang kapan saja
  tanpa generate ulang.

Ke-4 modul ini **sudah diuji lewat Flask test client** (`test_modules.py`,
tidak diikutkan di paket produksi): tambah/lihat/unduh data di tiap modul,
validasi ekstensi file, penomoran surat otomatis (increment & tidak
tabrakan antar-jenis), dan konfirmasi ke-17 halaman modul lama (Mahasiswa/
Dosen/Ruangan/Akademik/Pengaturan/SDM/Cetak Surat TA) tetap merespons
normal setelah perubahan `base.html`, `db.py`, dan `dashboard.py`.

## Langkah berikutnya (belum dikerjakan)
- E-Signature untuk Generator Surat (Modul 8) — di luar cakupan fase ini,
  surat yang dihasilkan masih berupa .docx untuk ditandatangani manual/
  digital lewat aplikasi lain.
- 3 placeholder jujur di menu Pengaturan (bukan celah, sengaja ditunda
  sampai ada kebutuhan konkret dari pemakaian sehari-hari): Preferensi
  Tampilan, Pusat Notifikasi, Tema Tampilan — lihat `roadmap.py`.

## Audit Lanjutan 3 — Bab SDM & Program Kerja di Rekap & Laporan (SELESAI)
Menutup gap eksplisit yang disebut di tabel status Modul 9 di atas: rekap
resmi sebelumnya hanya mencakup Tugas Akhir. Ditambahkan 2 bab baru ke
`routes/rekap.py` (halaman + ekspor Excel), memakai rumus yang SAMA PERSIS
dengan modul sumbernya supaya angka selalu konsisten (bukan dihitung ulang
dgn logika terpisah yang bisa bergeser):
- **Rekap Kinerja Dosen (SDM)** (`/rekap/kinerja-dosen`) — rincian jumlah
  entri per 7 kategori Tri Dharma per dosen + kesiapan BKD/SISTER (rumus
  dari `sdm.py:_hitung_kesiapan`), filter Homebase/Semua Dosen & Tahun
  Akademik. `timeline_karier_dosen` sengaja dikecualikan dari filter tahun
  (peristiwa karier tidak terikat 1 periode akademik, sesuai skema aslinya).
- **Rekap Program Kerja** (`/rekap/program-kerja`) — ringkasan realisasi
  per bidang + detail per program (rumus dari
  `kegiatan.py:_hitung_realisasi`), ekspor Excel 2-sheet (Detail Program +
  Ringkasan Bidang), filter Tahun Akademik.
- Terdaftar di sidebar (`base.html`) & Panduan Penggunaan (`panduan.py`,
  otomatis ikut di dokumen .docx unduhan tanpa disunting manual).
- **Sudah diuji** (`test_audit_lanjutan_3.py`, 34 pemeriksaan): kedua bab
  merespons 200 → filter Homebase/Semua & Tahun Akademik bekerja tepat →
  ekspor Excel berisi kolom & baris yang benar (termasuk realisasi 50% dari
  seed 1 dari 2 kegiatan Selesai) → 2 bab baru terdaftar di sidebar &
  Panduan → regresi: Rekap lama, Dashboard SDM asal, dan halaman Program
  Kerja asal tetap 200. `test_sidebar.py` diperbarui mengikuti (49→51
  tautan). Seluruh 11 file test suite (termasuk 1 file baru pada bagian
  ini) lulus tanpa ada modul lama yang rusak.

## Audit Menyeluruh — Phase 1–7 (SELESAI)

Implementasi penuh atas *Audit Menyeluruh SIMPRODI dan Rekomendasi
Pengembangan*: dari perbaikan kritis (bug `status_ta`, referential
integrity, hard-delete tanpa guard) sampai TA Workflow Engine, Audit Trail
generik, Data Lifecycle & Versioning Kurikulum, rantai OBE & CQI, dan
reorganisasi Dashboard jadi Control Center (KPI/Risk/Deadline/Workflow/
Quality/Evidence). Rincian lengkap tiap fase, keputusan desain, dan daftar
bug yang ditemukan selama proses (10 di antaranya di luar temuan dokumen
audit asli) ada di **`AUDIT_MENYELURUH_PHASE_1_7.md`**.

Setiap fase diverifikasi dengan 3 lapis pengujian sebelum dianggap
selesai: seluruh test suite bawaan (`test_*.py`), smoke-test HTTP
end-to-end lewat proses Flask sungguhan (bukan hanya test client), dan
simulasi migrasi dari database berskema sangat lama. Migrasi skema
berjalan **otomatis** saat aplikasi pertama kali dibuka — tidak ada
langkah manual yang perlu dijalankan operator saat upgrade dari versi
sebelumnya.
