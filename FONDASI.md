# Fase Fondasi — Catatan Teknis

Fase ini menyiapkan struktur project gabungan + migrasi skema database.
Belum ada halaman/route baru — murni fondasi data, supaya modul-modul
berikutnya (SDM, Akademik Operasional, Kegiatan, dst) tinggal dibangun di
atas skema yang sudah final, tanpa perlu migrasi ulang berkali-kali.

## Apa yang TIDAK diubah
- Seluruh route, template, dan logika modul Mahasiswa & Tugas Akhir
  (`mahasiswa.py`, `akademik.py`, `pelaksanaan.py`, `kelulusan.py`,
  `rekap.py`, `surat.py`, `pengaturan.py`, `auth.py`, `dashboard.py`,
  `ruangan.py`, `dosen.py`) — persis seperti sebelumnya.
- Lokasi database (`~/SistemSkripsi/data_prodi.db`) — database lama tetap
  kompatibel, migrasi berjalan otomatis & idempoten saat pertama dibuka.
- Alur login & session (`auth_core.py`) — masih 1 akun/1 password.

## Apa yang berubah

### `app/db.py`
- **12 tabel baru** untuk modul SDM & Kinerja Dosen (lihat daftar di bawah),
  ditambahkan di `SCHEMA` dengan pola penulisan yang identik dengan tabel
  yang sudah ada (`AUTOINCREMENT`, `ON DELETE CASCADE`, `FOREIGN KEY`).
- Tabel `dosen` diperluas 4 kolom: `nip`, `jabatan_fungsional`,
  `pendidikan_terakhir`, `bidang_keahlian`. Ditulis dua kali secara sengaja:
  langsung di `CREATE TABLE` (untuk instalasi baru) **dan** di `_migrate()`
  lewat `ALTER TABLE` idempoten (untuk database lama yang tabel `dosen`-nya
  sudah terlanjur ada tanpa kolom ini).
- `_migrate()` menambah satu baris: baris `pengguna` lama dengan
  `peran='Administrator'` otomatis disamakan jadi `'Kaprodi'` saat database
  lama dibuka — supaya istilah di seluruh aplikasi konsisten tanpa
  menghapus/mengubah data pengguna lain.
- `_seed_defaults()`: akun pertama pada database baru sekarang dibuat
  dengan nama & peran `"Kaprodi"` (sebelumnya `"Admin Prodi"` /
  `"Administrator"`).
- **Sudah diuji**: migrasi dari skema versi lama (simulasi) maupun
  pembuatan database baru, keduanya menghasilkan struktur yang sama dan
  tidak kehilangan data.

Tabel baru (grup Modul 4 — SDM & Kinerja Dosen):
```
aktivitas_pendidikan       aktivitas_penelitian      aktivitas_pkm
aktivitas_penunjang        luaran_dosen              peran_akademik_dosen
timeline_karier_dosen      target_kinerja_dosen
```
Rasional tiap tabel & pemetaannya ke sheet workbook `AKD Excel Pro` ada di
`rancangan-final-modul-sdm-kinerja-dosen.md` (dikirim terpisah di
percakapan perancangan) — file `db.py` ini adalah implementasi persis dari
rancangan tersebut, tidak ada penyesuaian tambahan saat coding.

### `app/constants.py`
- `APP_NAME` diubah dari `"Sistem Manajemen Skripsi"` menjadi
  `"Sistem Informasi Program Studi"` (`APP_SHORT_NAME = "SIMPRODI"`),
  `APP_VERSION` dinaikkan ke `2.0.0` — mencerminkan cakupan aplikasi yang
  sekarang lebih luas dari sekadar skripsi. Ini tampil otomatis di semua
  template lewat `inject_globals()` di `app/__init__.py` (tidak perlu ubah
  template).
- Kamus dropdown baru untuk modul SDM (`SEMESTER_LIST`,
  `SKEMA_PENELITIAN_PKM_LIST`, `SUMBER_DANA_LIST`,
  `STATUS_AKTIVITAS_SDM_LIST`, `JENIS_LUARAN_LIST`,
  `JENIS_PERAN_AKADEMIK_LIST`, `JENIS_PERUBAHAN_KARIER_LIST`,
  `KATEGORI_TARGET_KINERJA_LIST`, `REMINDER_MASA_BERLAKU_HARI`) — mengikuti
  pola kamus tunggal yang sama dengan `STATUS_TA_LIST`, supaya dropdown form
  dan label rekap tidak pernah selisih (prinsip yang sama seperti perbaikan
  Audit Medium #16 yang sudah ada di file ini).

## Belum dikerjakan (menyusul)
- `app/import_sdm.py` — import Excel dari workbook `AKD Excel Pro`,
  mengikuti pola `import_excel.py` yang sudah ada.
- Bab SDM/Modul 5–8 di Rekap & Laporan resmi (Modul 9) — saat ini rekap
  masih khusus Tugas Akhir.
- E-Signature untuk Generator Surat (Modul 8).

## Modul 5–8 (SELESAI dikoding & diuji — fase ini)
Menambah 5 tabel baru di `db.py` (`kalender_akademik`, `program_kerja`,
`kegiatan_prodi`, `dokumen`, `surat_keluar`) dengan pola `CREATE TABLE IF
NOT EXISTS` yang identik dengan tabel lama — tidak perlu `ALTER TABLE` di
`_migrate()` karena semuanya tabel baru, bukan perluasan tabel lama.

- **Modul 5 — `routes/kalender.py`**: CRUD agenda (pola `ruangan.py`) +
  kalender bulanan (grid, dibangun dari `calendar` stdlib, tanpa
  dependensi baru). `acara_mendatang()` diekspor & dipanggil dari
  `routes/dashboard.py` (perubahan aditif — 2 baris tambahan, tidak
  menyentuh query/logika dashboard yang sudah ada) supaya agenda H-0..H+7
  otomatis tampil di halaman utama.
- **Modul 6 — `routes/kegiatan.py`**: 2 tabel terkait (`program_kerja` 1->N
  `kegiatan_prodi`) dalam 1 halaman 2-tab. Realisasi (%) program dihitung
  on-the-fly dari rasio kegiatan berstatus "Selesai" — prinsip sama dengan
  Realisasi Target Kinerja Modul SDM (tidak disimpan statis).
- **Modul 7 — `routes/dokumen.py`**: upload file ke
  `~/SistemSkripsi/dokumen/` (pola sama dgn upload logo di
  `pengaturan.py`, nama file dibuat unik dgn UUID prefix supaya tidak
  saling menimpa), whitelist ekstensi (`EKSTENSI_DOKUMEN_DIIZINKAN` di
  `constants.py`), filter kategori + pencarian.
- **Modul 8 — `routes/surat_umum.py`**: generator surat resmi umum di luar
  TA (Surat Tugas/Keterangan/SK/Undangan/Edaran/Nota Dinas/dll), nomor
  otomatis format `{urut:03d}/{kode_jenis}/{kode_institusi}/{bulan
  romawi}/{tahun}` (urut dihitung dari jumlah baris `surat_keluar` tahun
  berjalan +1 — global per institusi, bukan per jenis, sesuai praktik
  umum administrasi Indonesia). Setiap surat tersimpan permanen di
  `~/SistemSkripsi/surat_keluar/` + tercatat di tabel `surat_keluar`
  (Buku Agenda Surat Keluar) supaya bisa diunduh ulang tanpa generate
  ulang & nomor tidak pernah tabrakan.

**Sudah diuji lewat Flask test client** (`test_modules.py` — hanya untuk
pengembangan, tidak diikutkan di paket produksi): tambah data → tampil di
list → edit/hapus untuk Modul 5 & 6; upload/unduh/tolak-ekstensi-terlarang
untuk Modul 7; generate 2 surat berturut-turut → nomor otomatis unik &
increment, tercatat di Buku Agenda, bisa diunduh ulang untuk Modul 8;
reminder kalender tampil di Dashboard; dan konfirmasi ke-17+ halaman
modul lama tetap merespons normal setelah perubahan `base.html`, `db.py`,
`constants.py`, dan `dashboard.py`.

## Modul 4 — SDM & Kinerja Dosen (SELESAI dikoding, sudah diuji)
`app/routes/sdm.py` + `app/templates/sdm_index.html` + `sdm_detail.html`.

- **CRUD generik** untuk 8 tabel lewat `TABEL_CONFIG` (bukan ditulis 8x
  manual) — tab: Pendidikan, Penelitian, PKM, Penunjang, Luaran, Peran
  Akademik, Timeline Karier, Target Kinerja.
- **Kode otomatis** `PEN-2026-001` / `PKM-2026-001` / `LUR-2026-001`
  (`_generate_kode()`), sama format dengan workbook asal.
- **Dashboard Kesiapan BKD/SISTER** (`_hitung_kesiapan()`) — rasio aktivitas
  berstatus selesai, dihitung ulang tiap halaman dibuka.
- **Reminder Masa Berlaku** (`_hitung_reminder()`) — dari `luaran_dosen.masa_berlaku`
  dan `peran_akademik_dosen.tgl_selesai`, ambang H-90 dari `REMINDER_MASA_BERLAKU_HARI`.
- **Realisasi Target Kinerja** dihitung on-the-fly dari `COUNT(luaran_dosen)`
  per kategori+tahun — bukan kolom statis.
- **Sudah diuji lewat Flask test client** (bukan cuma render halaman kosong):
  tambah dosen → isi semua 8 kategori data → kode otomatis benar → realisasi
  target terhitung tepat → reminder kadaluarsa terdeteksi → edit & hapus data
  berhasil → seluruh halaman lama (Mahasiswa/Dosen/Ruangan/Akademik/Pengaturan)
  tetap normal setelah perubahan `base.html`.

## Modul 13–14 — Semester Pendek & RPL (SELESAI dikoding & diuji)
`app/routes/semester_pendek.py` + `app/routes/rpl.py` +
`app/templates/semester_pendek.html` + `app/templates/rpl.html`.
Rasional lengkap ada di `docs/INTEGRASI_SITIPRO_SIMPRODI.md` §9.

- 8 tabel baru di `db.py` (`sp_periode`, `sp_kelas`, `sp_peserta`,
  `sp_pertemuan`, `sp_presensi`, `rpl_pendaftar`, `rpl_dokumen`,
  `rpl_konversi`) — pola `CREATE TABLE IF NOT EXISTS` identik dengan
  modul lain, tidak ada `ALTER TABLE` (semuanya tabel baru).
- Status kapasitas kelas SP dan total SKS diakui RPL dihitung on-the-fly
  (`logic.sp_status_kelas()`, `logic.rpl_total_sks_diakui()`) — prinsip
  yang sama dengan realisasi_bap/realisasi proker, bukan kolom statis.
- Nilai akhir SP dihitung otomatis dari bobot Tugas 30%/UTS 30%/UAS 40%
  (`logic.sp_hitung_nilai_akhir()`), memakai `nilai_angka_ke_huruf()`
  yang sama dengan modul TA.
- Dashboard mendapat ringkasan aditif periode SP aktif + pendaftar RPL
  dalam asesmen (2 baris tambahan di `dashboard.py`, tidak mengubah
  logika lama).
- **Sudah diuji lewat Flask test client** (`test_sp_rpl.py`): periode →
  kelas dari kurikulum aktif → status kapasitas berubah sesuai jumlah
  peserta disetujui → presensi per peserta terhitung tepat → nilai akhir
  terhitung tepat dari 3 komponen → export CSV; pendaftar RPL → konversi
  SKS → total terhitung tepat → unggah/unduh dokumen. Seluruh 41 tautan
  sidebar tetap 200, dan `test_modules.py`/`test_new_modules.py` tetap
  lulus (tidak ada modul lama yang tersentuh).

## Modul 15 — Penelitian, PKM & Publikasi/HKI (SELESAI dikoding & diuji)
`app/routes/tridharma.py` + `app/templates/tridharma.html`. Rasional
lengkap ada di `docs/INTEGRASI_SITIPRO_SIMPRODI.md` §10.

- **TIDAK ada tabel baru untuk data Penelitian/PKM/Publikasi/HKI** — modul
  ini dibangun DI ATAS `aktivitas_penelitian`, `aktivitas_pkm`,
  `luaran_dosen`, `aktivitas_pendidikan`, `aktivitas_penunjang` yang
  sudah ada di Modul 4 (SDM & Kinerja Dosen) sejak Fase Fondasi. `sdm.py`
  tidak disentuh sama sekali.
- Satu tabel baru: `tridharma_tinjauan` — tinjauan/keputusan
  institusional (Kaprodi/GKM) atas usulan Penelitian/PKM, terpisah dari
  status self-report dosen. Relasi opsional ke `aktivitas_penelitian`
  ATAU `aktivitas_pkm` (dual-nullable-FK, pola sama dengan
  `luaran_dosen.penelitian_id/pkm_id`).
- Nilai tambah modul: rekap & filter **lintas semua dosen sekaligus**
  (dashboard, daftar Penelitian+PKM gabungan, daftar Luaran, rekap
  Pendidikan & Penunjang) — sesuatu yang secara struktural tidak bisa
  didapat dari `sdm.py` (navigasinya selalu satu dosen per halaman).
  Semua tautan edit data asli mengarah balik ke `sdm.py`.
- Dashboard mendapat ringkasan aditif jumlah dosen belum capai target
  kinerja tahun berjalan + reminder tenggat laporan hibah (2 baris
  tambahan di `dashboard.py`, tidak mengubah logika lama).
- **Sudah diuji lewat Flask test client** (`test_tridharma.py`): data
  diinput lewat `sdm.py` (tidak disentuh) → tampil benar di rekap lintas
  dosen Modul 15 → filter jenis berfungsi → tinjauan institusional
  ter-upsert (bukan duplikat) → reminder tenggat laporan otomatis
  muncul di dashboard. Seluruh 41 tautan sidebar tetap 200 (3 entri
  roadmap lama diganti 3 entri modul nyata), dan seluruh test suite
  sebelumnya tetap lulus.

## Modul 16 — Kerja Sama & Mitra (SELESAI dikoding & diuji)
`app/routes/kerjasama.py` + `app/templates/kerjasama.html`. Rasional
lengkap ada di `docs/INTEGRASI_SITIPRO_SIMPRODI.md` §11.

- 4 tabel baru (domain ini memang belum ada tabelnya sama sekali di
  SIMPRODI, beda dengan Modul 15): `mitra`, `mitra_dokumen`,
  `mitra_program`, `mitra_luaran`.
- **Relevansi ke modul lain lewat FK sungguhan** (bukan label teks
  seperti demo SITIPRO): `mitra_program.pic_dosen_id` → `dosen` (Modul
  4), `mitra_program.penelitian_id`/`pkm_id` → `aktivitas_penelitian`/
  `aktivitas_pkm` (Modul 4/15, opsional), `mitra_luaran.luaran_dosen_id`
  → `luaran_dosen` (Modul 4/15, opsional, hindari duplikasi entri).
- Dokumen MoU/MoA/IA punya tabel & upload sendiri (`mitra_dokumen`),
  terpisah dari Document Center — butuh siklus hidup (`tgl_berakhir` +
  `status`) untuk reminder kadaluarsa yang tidak dimiliki skema
  `dokumen` generik. Status dokumen per mitra (Aktif/Segera Berakhir/
  Berakhir) dihitung on-the-fly, bukan kolom manual.
- Indeks Kepuasan Mitra dihitung dari rata-rata `skor_kepuasan` yang
  BENAR-BENAR diisi pengguna — tidak ada angka statis seperti 85% di
  demo yang tidak berasal dari evaluasi sungguhan.
- Dashboard mendapat ringkasan aditif jumlah dokumen MoU/MoA/IA segera/
  sudah berakhir (1 baris tambahan di `dashboard.py`, tidak mengubah
  logika lama).
- **Sudah diuji lewat Flask test client** (`test_kerjasama.py`): mitra →
  dokumen dengan tanggal berakhir dalam ambang → status otomatis
  "Segera Berakhir" → program ditautkan ke PIC dosen & Penelitian (JOIN
  benar, relevansi FK teruji) → rata-rata skor kepuasan program studi &
  per-mitra terhitung tepat → luaran kerja sama tersimpan. Seluruh 41
  tautan sidebar tetap 200, dan seluruh test suite sebelumnya tetap
  lulus.

## Modul 17 — Mutu: IKU, Akreditasi & Audit Mutu Internal (SELESAI dikoding & diuji)
`app/routes/mutu.py` + `app/templates/mutu.html`. Rasional lengkap ada di
`docs/INTEGRASI_SITIPRO_SIMPRODI.md` §12. Menutup seluruh daftar menu
SITIPRO — `ROADMAP_MODULES` kini kosong.

- SITIPRO cuma benar-benar merutekan `/audit-qa`; `/iku` dan
  `/akreditasi` TIDAK PERNAH punya komponen di demo aslinya. IKU &
  Akreditasi dirancang dari kerangka resmi (8 IKU Kemendikbudristek,
  9 Kriteria LAMEMBA — relevan utk profil S1 Administrasi Bisnis/Niaga).
- `AuditQA.tsx` (Data Integrity/System Health/Security) diterjemahkan
  ulang total — isinya berorientasi sistem terdistribusi yang tidak
  jujur untuk SIMPRODI (Flask+SQLite offline). Diganti Audit Mutu
  Internal (AMI/SPMI, PDCA tingkat standar mutu — beda dari CQI Modul 12
  yang PDCA-nya khusus CPL/OBE), pemindai Kelengkapan Data, dan penampil
  `log_aktivitas` (tabel yang sudah ditulis sejak Fase Fondasi, baru
  sekarang punya UI).
- **6 dari 8 IKU dihitung on-the-fly lintas modul** — IKU1←tracer_study
  (Kelulusan), IKU2/4/6←mitra_luaran/mitra_program/mitra (Modul 16),
  IKU3←aktivitas_penunjang (Modul 4), IKU5←luaran_dosen (Modul 4/15).
  IKU7 & IKU8 jujur ditandai "Manual" (SIMPRODI belum punya sumber data).
- 9 Kriteria LAMEMBA otomatis ter-seed sebagai kerangka kosong (nomor +
  nama saja, status semua "Belum Disusun") saat database baru dibuat.
  PIC dipilih dari dosen aktif sungguhan, bukan teks bebas.
- Kategori temuan AMI memakai istilah baku audit mutu Indonesia
  (Sesuai/Observasi/KTS Minor/KTS Mayor), bukan "issue" generik.
- Dashboard mendapat ringkasan aditif temuan AMI terbuka + reminder
  tenggat tindak lanjut (2 baris tambahan di `dashboard.py`).
- **Sudah diuji lewat Flask test client** (`test_mutu.py`): data lintas
  modul diinput lewat modul-modul yang sudah ada (TIDAK disentuh) → IKU
  3/4/5/6 terhitung TEPAT (diverifikasi angkanya, bukan cuma tampil) →
  9 kriteria LAMEMBA ter-seed → PIC/status/bukti akreditasi tersimpan →
  siklus & temuan AMI tercatat → pemindai Kelengkapan Data & Log
  Aktivitas berfungsi. Seluruh 41 tautan sidebar tetap 200, dan seluruh
  test suite sebelumnya tetap lulus.

## Halaman Login (DIPERBARUI & diuji) — bukan modul baru
`app/templates/login.html` (ditulis ulang) + CSS terkait di `style.css`
+ 2 baris aditif di `app/__init__.py`. Rasional lengkap ada di
`docs/INTEGRASI_SITIPRO_SIMPRODI.md` §13. **`routes/auth.py` dan
`app/auth_core.py` TIDAK disentuh** — model autentikasi tetap satu
password admin bersama (bukan username+password ala SITIPRO, karena
SIMPRODI memang tidak punya tabel akun pengguna — single-tenant untuk
satu Kaprodi/operator).

- Tata letak dua panel diadaptasi dari `Login.tsx` SITIPRO, tapi palet
  warna TETAP indigo SIMPRODI sendiri (bukan oranye SITIPRO), dan konten
  panel kiri jujur menampilkan 4 modul nyata (Kurikulum & OBE, SDM,
  Kerja Sama & Mitra, Mutu/IKU/Akreditasi), bukan tagline pemasaran.
- Fitur baru: toggle tampil/sembunyikan password, deteksi Caps Lock,
  spinner submit — semua murni JS sisi klien, tidak menyentuh backend.
- Logo & nama institusi/prodi dari Pengaturan kini tampil di halaman
  login (sebelumnya cuma ikon 🎓 generik) — butuh 1 pengecualian presisi
  di gerbang login (`pengaturan.logo_preview`, murni baca file gambar)
  yang sudah diverifikasi tidak membocorkan route lain.
- **Sengaja TIDAK diadaptasi**: splash screen dgn langkah palsu ("Loading
  AI Engine" dst — SIMPRODI tidak punya AI Engine), tombol "Windows
  Hello" (tidak lintas platform), checkbox "ingat saya" (SECRET_KEY
  di-generate ulang tiap start, sesi tidak pernah benar-benar bertahan),
  "lupa password" (tidak ada infrastruktur email offline — ganti
  password yang sungguhan sudah ada di Pengaturan).
- **Sudah diuji lewat Flask test client** (`test_login.py`): state buat
  password & state login normal, validasi, branding pre-login, dan
  verifikasi keamanan bahwa route lain tetap wajib login (pengecualian
  gerbang tidak bocor). Seluruh 41 tautan sidebar tetap 200, dan seluruh
  test suite sebelumnya tetap lulus.

## Restrukturisasi Sidebar (SELESAI & diuji) — bukan modul baru
`app/templates/base.html` (struktur `nav_groups` ditulis ulang) +
`app/routes/roadmap.py` (5 placeholder baru) + `app/templates/
roadmap.html` (1 kalimat digeneralisasi). Analisis UX lengkap (8 bagian:
masalah, sidebar baru, alasan tiap grup, rekomendasi menu, yang
digabung/dipindah/tetap, rencana ke depan) ada di
`docs/RESTRUKTURISASI_SIDEBAR.md`. **Tidak ada fitur yang dihapus, tidak
ada logika backend yang diubah** — murni reorganisasi label & pengelompokan.

- Sidebar lama: 8 grup, 41 tautan, grup "Akademik" terlalu padat (15
  item mencampur operasional harian + siklus hidup mahasiswa + Tugas
  Akhir + siklus mutu).
- Sidebar baru: **10 grup + Dashboard, 47 tautan** (42 endpoint modul
  nyata — sama seperti sebelumnya + 1 tautan baru ke Log Aktivitas yang
  sudah ada tapi belum ditautkan + 5 placeholder baru).
- Grup baru: **Mahasiswa** (siklus hidup mahasiswa: Data Mahasiswa, SP,
  RPL, Tracer Study) dan **Tugas Akhir** (6 tahap, dipisah dari Akademik
  karena volume & sifat linear alurnya). **Siklus CQI** dipindah ke
  **Mutu & Analytics** (disandingkan dgn AMI — sama-sama PDCA mutu, beda
  level). **Pengaturan** dipisah dari **Administrasi** (identitas prodi
  vs cara memakai aplikasi, pola sama dgn Odoo/ERPNext).
- 5 menu direkomendasikan tapi BELUM dibangun (di luar cakupan
  reorganisasi navigasi): Preferensi Tampilan, Notifikasi, Backup &
  Restore (prioritas tinggi — risiko nyata utk app 1-file-SQLite),
  Tema Tampilan, Tentang Aplikasi — diarahkan ke `roadmap.modul`
  (halaman jujur "dalam pengembangan"), bukan tautan mati.
- Ditolak secara eksplisit dgn alasan (bukan diabaikan begitu saja):
  Favorite Menu, Help Center, Recycle Bin, Archive, Template Manager,
  Master Data (grup terpisah), Task Center, Announcement, Integrasi, API
  — semuanya tidak relevan untuk aplikasi offline single-tenant 1 prodi.
- **Sudah diuji lewat Flask test client** (`test_sidebar.py`): 11 grup
  tampil sesuai urutan baru → 47 tautan semuanya 200 → tidak ada 1 pun
  endpoint modul lama yang hilang dari sidebar → highlight menu aktif
  presisi utk endpoint yang dipakai berulang (Tri Dharma, Mutu) →
  placeholder roadmap baru jujur (tanpa form/data tiruan) & bisa
  dibedakan dari 404 slug tak terdaftar. Seluruh test suite sebelumnya
  tetap lulus.

## Audit Lanjutan — Dropdown Periode Akademik & Retensi Backup Otomatis (SELESAI & diuji)
Menindaklanjuti 2 temuan spesifik dari audit fondasi sebelumnya:

**1. `periode_akademik_id` sekarang benar-benar dipakai, bukan cuma kolom cache.**
9 tabel (`aktivitas_pendidikan`, `aktivitas_penelitian`, `aktivitas_pkm`,
`aktivitas_penunjang`, `luaran_dosen`, `peran_akademik_dosen`,
`program_kerja`, `cqi_siklus`, `ami_siklus`) sudah punya kolom FK ini sejak
migrasi sebelumnya, tapi belum ada satu pun form yang menuliskannya — semua
masih pakai input teks bebas `tahun_akademik`. Sekarang:
- `db.py` menambah `get_periode_list()`, `get_periode_by_id()`,
  `cache_periode()` — satu sumber dropdown terkunci dipakai di semua modul.
- 6 tab di `sdm.py`, `kegiatan.py` (Program Kerja), `cqi.py` (Gap Analysis
  → Buka Siklus), dan `mutu.py` (Siklus AMI) diganti dari input teks jadi
  dropdown Periode Akademik. Kolom TEXT lama (`tahun_akademik`, `semester`)
  **tetap dipertahankan** sebagai cache — diturunkan otomatis dari periode
  terpilih, bukan diketik manual lagi — supaya filter/tampilan/rekap yang
  sudah ada di modul lain tidak perlu diubah.
- Diuji lewat `test_periode_dropdown.py` (24 pemeriksaan): dropdown tampil
  di tiap form, FK asli tersimpan (bukan cuma cache), cache text ikut
  terisi otomatis, kode otomatis (`PEN-2025-001`) ikut memakai tahun dari
  periode terpilih, form edit men-preselect periode yang tersimpan.

**2. `bersihkan_backup_lama()` sekarang terjadwal otomatis + reminder di UI.**
Sebelumnya fungsi retensi ini hanya terpanggil manual di dalam tombol
"Backup Sekarang" — kalau operator tidak pernah membuka menu Backup &
Restore, backup lama menumpuk selamanya, dan operator tidak tahu kapan
terakhir kali backup dibuat. Sekarang:
- `app/__init__.py`: retensi berjalan otomatis sekali setiap aplikasi
  start (tanpa perlu klik apa pun), lalu diulang tiap 24 jam lewat thread
  daemon kalau proses dibiarkan menyala lama (mode web). Dilewati saat
  `TESTING=True`.
- `backup_core.status_reminder()`: cek "kapan backup terakhir" dan
  tandai perlu-reminder kalau belum pernah backup atau sudah ≥7 hari.
- `logic.get_notifikasi()`: reminder ini otomatis muncul di panel
  Notifikasi Dashboard (mekanisme yang sama dgn reminder tenggat modul
  lain) — tidak perlu membuka Backup & Restore dulu untuk tahu keadaannya.
- Diuji lewat `test_backup_reminder.py` (12 pemeriksaan): status kosong →
  reminder aktif; backup baru → reminder hilang; backup 400 hari →
  reminder tampil dgn badge di Dashboard; retensi otomatis benar-benar
  mengurangi file lama saat `create_app()` tanpa `TESTING=True`.

## Modul "Tentang Aplikasi" (BARU, dibangun sungguhan — sebelumnya roadmap)
Bagian dari audit yang sama: menu ini sebelumnya diarahkan ke
`roadmap.modul` (placeholder). Sekarang jadi modul nyata di
`routes/tentang.py` + `templates/tentang.html` — halaman read-only berisi
versi aplikasi, identitas instansi, ukuran & jumlah tabel database,
ringkasan jumlah data utama, status & kebijakan retensi backup, dan
jumlah modul aktif vs direncanakan. **Semua angka dihitung langsung dari
data berjalan** (blueprint yang sungguh terdaftar, isi tabel, file
database) — bukan teks statis yang bisa basi.

Tindak lanjut kebersihan sekaligus:
- `roadmap.py`: entry `backup-restore` (sudah lama jadi modul nyata tapi
  belum dibersihkan dari daftar roadmap) dan `tentang-aplikasi` dihapus —
  tersisa 3 placeholder jujur (Preferensi Tampilan, Notifikasi, Tema
  Tampilan).
- `panduan.py`: catatan roadmap yang masih menyebut "Backup & Restore
  (begitu tersedia)" diperbaiki, ditambah entri panduan sungguhan untuk
  Backup & Restore dan Tentang Aplikasi.
- `test_sidebar.py` diperbarui mengikuti (49 tautan tetap, placeholder
  roadmap 4→3).

Seluruh test suite (7 file, termasuk 2 file baru) lulus setelah perubahan
ini — tidak ada modul lama yang rusak.

## Audit Lanjutan — Wiring `periode_akademik_id` di 4 Tabel Inti TA
Gap yang disebut eksplisit di audit sebelumnya: `pengajuan_judul`,
`penetapan_pembimbing`, `jadwal_kelas`, `sp_periode` sudah punya kolom
`periode_akademik_id` (ditambahkan lewat `_migrate()` bersamaan dengan 9
tabel tambahan Modul SDM/Kegiatan/Mutu), tapi belum ada route/template
yang benar-benar menulis ke kolom itu — dropdown "Periode Akademik"
terkunci belum ada di form-nya. Diselesaikan dengan pola PERSIS sama
dengan yang sudah dipakai 9 tabel tambahan (`db.get_periode_list()` untuk
isi dropdown, `db.cache_periode()`/`db.cache_periode_gabungan()` untuk
menurunkan cache TEXT lama):

- **`app/db.py`** — tambah `cache_periode_gabungan()`: varian
  `cache_periode()` untuk tabel yang cuma punya SATU kolom TEXT cache
  gabungan (`pengajuan_judul.semester` / `penetapan_pembimbing.semester`,
  formatnya "2025/2026 - Ganjil" dalam satu string), beda dari
  `jadwal_kelas`/tabel SDM yang punya 2 kolom terpisah
  (`tahun_akademik` + `semester`).
- **`pengajuan_judul`** (`routes/akademik.py`, `pengajuan_simpan()`):
  dropdown Periode Akademik menggantikan input teks bebas "Semester".
  Periode boleh kosong (kolom nullable, sama seperti sebelumnya).
- **`penetapan_pembimbing`** (`routes/akademik.py`, `penetapan_simpan()`):
  sama persis dengan pengajuan_judul.
- **`jadwal_kelas`** (`routes/jadwal.py`, `simpan_kelas()`): dropdown
  Periode Akademik menggantikan TOTAL 2 kontrol lama (input teks bebas
  "Tahun Akademik" + dropdown "Semester" terpisah). Berbeda dari 2 tabel
  di atas, periode di sini **wajib dipilih** (validasi baru, sejajar
  dengan validasi Mata Kuliah wajib) karena `jadwal_kelas.tahun_akademik`
  adalah kolom `NOT NULL` — tidak boleh kosong seperti sebelumnya.
- **`sp_periode`** (`routes/semester_pendek.py`, `simpan_periode()`):
  dropdown "Periode Akademik (Tahun Ajaran)" — sengaja dibedakan namanya
  dari `periode_rows` (periode Semester Pendek itu sendiri) di context
  template supaya tidak tertukar. Periode boleh tetap kosong (kolom
  nullable), konsisten dengan perilaku sebelumnya sebelum wizard "Buka
  Tahun Ajaran" dipakai.
- Filter tahun (`jadwal.py` filter chip "Semua Tahun"/per-tahun) TIDAK
  diubah — tetap baca dari kolom cache TEXT `tahun_akademik` seperti
  sebelumnya, karena cache itu sekarang justru SELALU konsisten (diisi
  otomatis dari periode, bukan ketikan bebas yang bisa typo).
- **Sudah diuji** (`test_periode_dropdown_lanjutan.py`, 30 pemeriksaan):
  dropdown tampil & berisi opsi periode yang benar di ke-4 form → submit
  → FK asli (`periode_akademik_id`) tersimpan tepat, bukan cuma cache →
  cache TEXT lama ikut terisi otomatis dan formatnya benar → form edit
  men-preselect periode tersimpan → validasi wajib di `jadwal_kelas`
  benar-benar menolak submit tanpa periode → `sp_periode` tetap boleh
  kosong tanpa error → regresi: Mahasiswa/SDM/Kegiatan tetap 200.
  `test_periode_dropdown.py` (9 tabel lama) tetap lulus tanpa perubahan.

## Panduan Penggunaan — Unduh Dokumen Resmi (.docx)
Modul Panduan Penggunaan (`routes/panduan.py`) sudah ada sejak audit
sebelumnya (accordion per grup sidebar, pencarian, tombol cetak lewat
`window.print()`). Tindak lanjut kali ini: tombol cetak browser diganti
namanya jadi "Cetak / Simpan PDF" (jujur soal mekanismenya) dan
DITAMBAHKAN tombol baru "⬇️ Unduh Dokumen Resmi (.docx)" yang
membangkitkan file Word SUNGGUHAN via `python-docx` — bukan hasil
print-to-PDF browser yang tata letaknya bisa berantakan di tiap perangkat.

- **`_bangun_docx_panduan()`** (baru, di `panduan.py`): memakai pola &
  helper yang sama dengan `routes/surat.py`/`routes/surat_umum.py`
  (kop dari Pengaturan Identitas & Branding, `io.BytesIO()` + `send_file`).
  Struktur dokumen sistematis: sampul (logo bila ada, nama aplikasi,
  versi, instansi/prodi) → tabel Identitas Dokumen → Kata Pengantar →
  Daftar Isi (field TOC bawaan Word, otomatis ambil seluruh heading
  berjenjang + nomor halaman begitu di-update di Word) → isi panduan per
  grup/modul dengan heading bernomor (`1.`, `1.1`, dst, memakai heading
  style bawaan Word supaya field TOC bisa membacanya) → Catatan Penutup.
  Header berisi judul dokumen, footer berisi "Halaman X dari Y" (field
  PAGE/NUMPAGES, ikut terhitung otomatis, bukan angka statis).
- Endpoint baru `GET /panduan/unduh` — murni baca (tidak menulis apa pun
  ke database), aman dipanggil berulang kali, nama file otomatis memuat
  tanggal (`Panduan-Penggunaan-SIMPRODI-YYYYMMDD.docx`).
- Kontennya bersumber dari `PANDUAN_GROUPS` yang SAMA dengan yang tampil
  di halaman web — begitu ada modul baru ditambahkan ke panduan in-app,
  dokumen unduhan otomatis ikut lengkap tanpa perlu disunting manual.
- **Sudah diuji** (`test_panduan_unduh.py`, 24 pemeriksaan): tombol
  tampil di halaman → endpoint 200 dengan Content-Type/Content-Disposition
  yang benar → file adalah ZIP OOXML valid (tidak korup) → seluruh 10
  grup dan 43 modul (jumlah saat ini) muncul sebagai heading bernomor
  tepat → field TOC & PAGE/NUMPAGES benar-benar tersemat (bukan teks
  statis) → metadata dokumen terisi → idempoten (unduh ulang tidak error).
  `test_sidebar.py` diperbarui mengikuti label tombol baru + tambahan 1
  pemeriksaan untuk tombol unduh docx.

Seluruh test suite (9 file, termasuk 2 file baru pada bagian ini) lulus
setelah perubahan ini — tidak ada modul lama yang rusak.

## Audit Lanjutan — Backup Menyeluruh & Import Modul SDM (SELESAI & diuji)
Audit ulang menemukan 2 celah utama pada dua menu yang sebelumnya "Ada"
tapi belum tuntas:

**1) Backup & Restore hanya mencakup database.** `backup_now()` versi awal
cuma menyalin `data_prodi.db`. Padahal banyak modul menyimpan file FISIK
di luar database: Document Center (`dokumen/`), Kerja Sama (`mitra_dokumen/`),
RPS Kurikulum (`rps/`), bukti Mutu/Akreditasi (`akreditasi_bukti/`), RPL
(`rpl_dokumen/`), arsip Surat Keluar (`surat_keluar/`), dan logo/identitas
(`branding/`). Restore ke komputer baru dari backup lama akan membuat
seluruh file itu hilang — baris metadata di database (nama file, path)
masih ada tapi tautannya patah.

Perbaikan di `app/backup_core.py`:
- `backup_now_full()` — backup LENGKAP: snapshot database (lewat SQLite
  Online Backup API, sama seperti sebelumnya) + seluruh isi 7 folder di
  atas, dibungkus jadi 1 file `.zip` disertai `manifest.json` (daftar
  folder & jumlah file). ­Ini jadi mode **default** tombol "Backup Sekarang".
- `restore_dari_file_zip()` / `validasi_file_restore_zip()` — restore dari
  `.zip`: database dipulihkan seperti biasa, folder file fisik yang ADA
  di dalam zip akan MENGGANTI folder yang sama di komputer ini (folder yg
  tidak ada di dalam zip dibiarkan, tidak dihapus paksa).
- Fungsi lama (`backup_now`/`restore_dari_file`, database saja) TETAP ADA
  sebagai pilihan "Database Saja (cepat)" di dropdown UI, dan restore
  tetap menerima file `.db` lama untuk kompatibilitas mundur.
- **Bug ditemukan & diperbaiki selama pengujian**: nama file backup semula
  cuma presisi detik (`backup_20260101_120000.db`) — kalau backup
  pra-restore otomatis (pengaman sebelum menimpa data) kebetulan dibuat
  di detik yang sama dengan nama file yang sedang dipakai sebagai SUMBER
  restore, filenya bisa saling menimpa. Diperbaiki dgn presisi mikrodetik
  + upload sumber restore selalu diisolasi ke folder sementara sendiri
  dulu SEBELUM proses backup pra-restore dijalankan, jadi tidak mungkin
  lagi file sumber ikut tertimpa oleh langkah pengamanannya sendiri.
- Bug kecil kedua: `logout()` (dipanggil otomatis setelah restore, demi
  keamanan) memakai `session.clear()` yang turut menghapus pesan flash
  "Restore berhasil" — pesan itu jadi tidak pernah terlihat. Diperbaiki
  supaya pesan flash yang tertunda ikut dipertahankan lewat proses logout.

**2) Modul Import Data hanya mendukung Dosen & Mahasiswa.** 7 tabel log
Modul SDM & Kinerja Dosen (Pendidikan/Pengajaran, Penelitian, PKM,
Penunjang, Luaran, Peran Akademik, Timeline Karier, Target Kinerja)
sebelumnya cuma bisa diisi satu-satu lewat form.

Perbaikan di `app/import_generic.py`: 1 factory generik
(`_buat_proses_baris_log_sdm`) membangun ke-7 importer sekaligus —
konsisten dengan pola `TABEL_CONFIG` generik di `routes/sdm.py`. Setiap
importer mencocokkan baris ke dosen yang SUDAH ADA (via NIDN atau nama;
tidak pernah membuat dosen baru dari jalur ini), lalu upsert idempoten
(kombinasi dosen + field judul/nama utama + tahun — sesuai jenis tabel)
supaya file yang sama boleh diunggah ulang tanpa menggandakan data. Kode
otomatis (`PEN-2026-003` dst) tetap dibangkitkan utk Penelitian/PKM/Luaran,
sama seperti lewat form manual. Dropdown pemilihan modul di UI dikelompokkan
per kategori ("Data Master" vs "SDM & Kinerja Dosen") lewat `<optgroup>`.
- Bug ditemukan & diperbaiki selama pengujian: label kolom wajib untuk
  importer Target Kinerja sempat tidak cocok persis dengan judul kolom di
  template (kolom di template memuat daftar pilihan kategori dalam kurung,
  labelnya sendiri tidak) — akibatnya semua baris salah dianggap kosong.
  Sudah diperbaiki dgn 1 konstanta label bersama utk header & validasi.
- Bug ketiga: nama sheet Excel untuk beberapa label modul memuat karakter
  `/` (tidak valid utk nama sheet) — `buat_template()` sekarang menyaring
  karakter terlarang (`[ ] : * ? / \`) sebelum dipakai sebagai judul sheet.

**Pengujian** (`test_audit_lanjutan_2.py`, 60 pemeriksaan, semua lulus):
backup lengkap benar-benar memuat file fisik & manifest → restore lengkap
mengembalikan file yang sudah dihapus (simulasi pindah komputer) → zip
tanpa `data_prodi.db` ditolak → restore via HTTP menampilkan pesan sukses
→ ke-7 importer SDM terdaftar, template bisa diunduh → dosen yang belum
ada di database membuat baris DILEWATI (bukan bikin dosen baru) →
setelah dosen ada, seluruh 8 modul (Dosen/Mahasiswa + 7 SDM) berhasil
menambah 1 baris masing-masing → kode otomatis PEN/PKM/LUR terisi benar
→ import ulang file yang SAMA tidak menggandakan baris (idempoten).
`test_audit_fondasi.py` diperbarui mengikuti format nama file backup baru
(`.zip`), sisanya tidak berubah. Seluruh 10 file test suite (termasuk 1
file baru pada bagian ini) lulus.

## Audit Lanjutan 3 — Bab SDM & Program Kerja di Rekap & Laporan (SELESAI & diuji)
Tindak lanjut atas gap yang disebut eksplisit di tabel status README (Modul
9 — "Rekap TA sudah ada, Bab SDM/modul lain menyusul"): Dashboard Modul SDM
(`sdm.index()`) dan halaman Program Kerja (`kegiatan.index()`) sudah
menghitung kesiapan BKD/SISTER & realisasi (%) sejak audit-audit
sebelumnya, tapi keduanya cuma tampil sbg dashboard in-app — belum jadi
bagian dari Rekap & Laporan resmi (tanpa filter Tahun Akademik lintas
dosen, tanpa kemampuan ekspor Excel untuk borang/laporan).

Ditambahkan ke `app/routes/rekap.py`, memakai fungsi murni (`_hitung_kesiapan`
dari `sdm.py`, `_hitung_realisasi` dari `kegiatan.py`) yang sudah ada —
BUKAN ditulis ulang dgn rumus terpisah — supaya angka di Rekap selalu
identik dgn yang tampil di Dashboard SDM/halaman Program Kerja:

- **Rekap Kinerja Dosen (SDM)** (`/rekap/kinerja-dosen` +
  `/rekap/kinerja-dosen/ekspor`): per dosen aktif — jumlah entri di 7
  kategori (Pendidikan/Penelitian/PKM/Penunjang/Luaran/Peran
  Akademik/Timeline Karier), total entri, kesiapan BKD (%), kesiapan
  SISTER (%), jumlah reminder masa berlaku aktif. Filter Homebase/Semua
  Dosen (pola sama dgn `rasio_dosen`) & Tahun Akademik. Nama dosen
  ditautkan ke `sdm.detail()` utk drill-down.
  - Catatan desain: `timeline_karier_dosen` TIDAK punya kolom
    `tahun_akademik` (peristiwa karier seperti kenaikan pangkat tidak
    terikat 1 periode akademik tertentu — lihat skemanya di `db.py`),
    jadi dikecualikan dari filter tahun & dari daftar opsi dropdown Tahun
    Akademik, tapi jumlahnya tetap dihitung & ditampilkan apa adanya.
- **Rekap Program Kerja** (`/rekap/program-kerja` +
  `/rekap/program-kerja/ekspor`): 2 tingkat — ringkasan per bidang
  (jumlah program, jumlah kegiatan, kegiatan selesai, anggaran rencana,
  realisasi %) di atas, detail per program di bawah. Ekspor Excel 2-sheet
  (pola sama dgn `rkp_sidang_ekspor`: Bagian 1 = detail, Bagian 2 =
  ringkasan agregat). Filter Tahun Akademik.
- Kedua bab didaftarkan ke sidebar (`base.html`, grup "📊 Mutu &
  Analytics") dan ke Panduan Penggunaan (`panduan.py`) — entri Panduan
  otomatis ikut di dokumen .docx unduhan (`panduan.unduh`) tanpa perlu
  disunting manual, karena bersumber dari `PANDUAN_GROUPS` yang sama.
- Bug ditemukan & diperbaiki selama pengujian: draft awal sempat memakai
  `db.get_periode_list()` (kolom `kode_tahun_ajaran`) utk mengisi dropdown
  Tahun Akademik di bab Kinerja Dosen — salah kolom (`KeyError:
  'tahun_akademik'`) dan salah sumber (seharusnya tahun yang BENAR-BENAR
  ada di tabel log SDM, bukan seluruh periode yang terdaftar di
  Pengaturan). Diperbaiki dgn `SELECT DISTINCT tahun_akademik` langsung
  dari ke-6 tabel log yang punya kolom itu.
- **Sudah diuji** (`test_audit_lanjutan_3.py`, 34 pemeriksaan, semua
  lulus): seed 2 dosen (1 homebase, 1 luar) + entri log di 3 kategori +
  1 program kerja dgn 2 kegiatan (1 Selesai) → kedua bab merespons 200 →
  filter Homebase/Semua Dosen menyaring dgn tepat → filter Tahun Akademik
  bekerja (termasuk tahun yang tidak ada datanya -> tabel kosong, bukan
  error) → ekspor Excel kinerja dosen berisi header & baris yang benar,
  konsisten dgn filter homebase → ekspor Excel program kerja 2-sheet
  berisi realisasi 50% yang benar di kedua sheet → 2 tautan baru terdaftar
  di sidebar & Panduan, dokumen .docx Panduan tetap terunduh normal →
  regresi: seluruh bab Rekap lama, Dashboard SDM asal, dan halaman Program
  Kerja asal tetap 200 dan angkanya tidak berubah. `test_sidebar.py`
  diperbarui mengikuti (jumlah tautan sidebar 49→51, deskripsi disesuaikan
  jadi 47 modul nyata + 3 placeholder). Seluruh 11 file test suite
  (termasuk 1 file baru pada bagian ini) lulus setelah perubahan ini —
  tidak ada modul lama yang rusak.

## Modul Preferensi Tampilan, Pusat Notifikasi & Tema Tampilan (SELESAI dikoding & diuji — Audit Lanjutan 4)
Menggantikan 3 placeholder roadmap terakhir di grup "⚙️ Pengaturan"
(`routes/roadmap.py` -> `ROADMAP_MODULES` kini kosong) dengan modul nyata.
Tidak ada tabel baru — ketiganya memakai tabel `pengaturan` (key-value)
yang sama dengan Identitas & Branding, lewat `get_setting`/`set_setting`
yang sudah ada di `db.py`.

- **`routes/preferensi.py`** — 3 preferensi, semuanya benar-benar dipakai
  (bukan sekadar tersimpan): densitas tabel (`Nyaman`/`Padat` -> class
  `density-padat` di `<body>`, lihat style.css), mode default grup sidebar
  (`otomatis`/`buka_semua`/`tutup_semua`, wired ke script accordion di
  `base.html`), dan rentang hari Agenda Mendatang (menggantikan angka baku
  `7` di `dashboard.py`, dipakai juga oleh Pusat Notifikasi).
- **`routes/notifikasi.py`** — mengumpulkan SEMUA sumber reminder yang
  sudah ada (bukan sumber baru): `logic.get_notifikasi()`,
  `kalender.acara_mendatang()`, `logic.sdm_reminder_semua()` (fungsi BARU
  di `logic.py`, versi lintas-dosen dari `sdm._hitung_reminder()`),
  `logic.tridharma_reminder_tenggat()`, `logic.mitra_reminder_dokumen()`,
  `logic.ami_reminder_tenggat()`. Ambang hari per kategori bisa diatur di
  halaman ini (menimpa konstanta baku `REMINDER_MASA_BERLAKU_HARI` dkk.
  lewat parameter `ambang_hari` yang sudah didukung tiap fungsi asal).
  Badge jumlah (lewat tenggat + segera) tampil di ikon lonceng topbar di
  semua halaman (`app/__init__.py` -> `inject_globals()`), yang sekarang
  mengarah ke `notifikasi.index` (sebelumnya ke `kalender.index`).
- **`routes/tema.py`** — 6 pilihan aksen warna lewat atribut `data-theme`
  di `<html>` (blok `html[data-theme=...]` di `style.css`, hanya menimpa
  `--primary`/`--primary-dark`/`--primary-soft`/`--violet`/`--violet-soft`).
  Sengaja BUKAN mode gelap — `--surface`/`--canvas`/`--ink` tetap sama di
  semua tema supaya kontras & keterbacaan tabel/rekap yang sudah teruji
  tidak berubah.

**Sudah diuji** (`test_audit_lanjutan_4.py` — 22 pemeriksaan, semua lulus;
juga memperbarui `test_sidebar.py` yang tadinya menguji perilaku
placeholder lama, dan `routes/panduan.py` yang tadinya punya catatan
"masih roadmap" untuk ketiga menu ini) + regresi 11 skrip tes lama (semua
tetap lulus, termasuk Dashboard/SDM/Kalender/Kerja Sama yang jadi sumber
data Pusat Notifikasi).
