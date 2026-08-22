# -*- coding: utf-8 -*-
"""
db.py — Lapisan database SQLite (offline, 1 file .db per Program Studi).

Versi web: schema dasar identik dengan versi desktop (kompatibel, database
lama bisa langsung dipakai tanpa migrasi manual) + tambahan:
  - kolom mahasiswa.skema ("Reguler" / "RPL")
  - tabel pengguna (fondasi manajemen pengguna, saat ini 1 akun admin)

Fase Fondasi (penggabungan dengan Prodi Office Manager + AKD Excel Pro):
  Modul Mahasiswa & Tugas Akhir di bawah ini TIDAK diubah logikanya sama
  sekali — ini tetap satu-satunya sumber kebenaran untuk data TA (modul TA
  versi POM yang lama sengaja tidak diikutkan, karena itulah yang tadinya
  menyebabkan data ganda). Tabel BARU untuk modul SDM & Kinerja Dosen
  ditambahkan di bagian bawah SCHEMA, mengikuti pola penulisan yang sama
  (AUTOINCREMENT, ON DELETE CASCADE) supaya konsisten dengan skema lama.
"""

import os
import re
import sqlite3

from app import constants as C
from app.constants import DEFAULT_PENGATURAN, PERAN_KAPRODI

SCHEMA = """
CREATE TABLE IF NOT EXISTS ruangan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT UNIQUE NOT NULL,
    kapasitas TEXT,
    keterangan TEXT
);

CREATE TABLE IF NOT EXISTS pengaturan (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS pengguna (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL,
    peran TEXT DEFAULT 'Administrator',
    aktif INTEGER DEFAULT 1,
    dibuat_pada TEXT DEFAULT (datetime('now','localtime')),
    login_terakhir TEXT
);

-- =============================================================================
-- Fase Fondasi (Audit) — Tahun Ajaran Terstruktur
-- Master tunggal untuk Ganjil/Genap/Antara, menggantikan string bebas
-- `tahun_akademik_aktif` di tabel pengaturan (yang tetap dipertahankan
-- sebagai CACHE tampilan, bukan sumber kebenaran lagi — lihat _migrate()
-- & buka_tahun_ajaran()). Tabel-tabel operasional yang tadinya menyimpan
-- semester/tahun_akademik sebagai TEXT bebas kini juga punya kolom
-- `periode_akademik_id` (nullable, ditambahkan lewat _migrate) sebagai
-- sumber kebenaran baru, tanpa menghapus kolom teks lama.
-- =============================================================================
CREATE TABLE IF NOT EXISTS tahun_ajaran (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kode TEXT UNIQUE NOT NULL,        -- "2025/2026"
    status TEXT DEFAULT 'Aktif',      -- Aktif / Selesai / Draft
    dibuat_pada TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS periode_akademik (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tahun_ajaran_id INTEGER NOT NULL,
    jenis TEXT NOT NULL,              -- 'Ganjil' | 'Genap' | 'Antara'
    tgl_mulai TEXT,
    tgl_selesai TEXT,
    status TEXT DEFAULT 'Draft',      -- Draft / Berjalan / Selesai
    UNIQUE(tahun_ajaran_id, jenis),
    FOREIGN KEY(tahun_ajaran_id) REFERENCES tahun_ajaran(id) ON DELETE CASCADE
);

-- Gelombang/batch pendaftaran seminar & sidang dalam satu periode akademik
-- (klarifikasi (a): perluasan dinamis dari nama_tahap_1/2 lama — jumlah
-- tahap sekarang bebas, bukan 2 field hardcode).
CREATE TABLE IF NOT EXISTS tahap_pengajuan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    periode_akademik_id INTEGER NOT NULL,
    urutan INTEGER NOT NULL,          -- 1, 2, 3, ...
    nama TEXT NOT NULL,               -- "Tahap 1 2025/2026", boleh custom
    tgl_buka TEXT,
    tgl_tutup TEXT,
    FOREIGN KEY(periode_akademik_id) REFERENCES periode_akademik(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mahasiswa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nim TEXT UNIQUE NOT NULL,
    nama TEXT NOT NULL,
    jk TEXT,
    tempat_lahir TEXT,
    tgl_lahir TEXT,
    no_hp TEXT,
    email_nik TEXT,
    angkatan TEXT,
    konsentrasi TEXT,
    status TEXT DEFAULT 'Aktif',
    status_ta TEXT DEFAULT 'Belum Mengajukan Judul',
    skema TEXT DEFAULT 'Reguler',
    catatan TEXT
);

CREATE TABLE IF NOT EXISTS dosen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nidn TEXT,
    nama TEXT NOT NULL,
    no_hp TEXT,
    email TEXT,
    aktif INTEGER DEFAULT 1,
    -- Kolom di bawah ini ditambahkan di Fase Fondasi untuk modul SDM & Kinerja
    -- Dosen. Untuk instalasi BARU, CREATE TABLE ini sudah cukup; untuk
    -- database LAMA yang tabel dosen-nya sudah ada, kolom yang sama juga
    -- ditambahkan lewat ALTER TABLE idempoten di _migrate() di bawah.
    nip TEXT,
    -- Fase Pejabat/SDM Lanjutan — SIMPRODI semula memakai NIP (Nomor Induk
    -- Pegawai, khas PNS) sebagai satu-satunya identitas kepegawaian dosen.
    -- Struktur data SISTER (PDDIKTI/Kemdikbudristek) tidak memakai NIP untuk
    -- dosen — yang dipakai adalah NIK (Nomor Induk Kependudukan, wajib utk
    -- SEMUA dosen PNS maupun non-PNS/swasta) dan NUPTK (Nomor Unik Pendidik
    -- & Tenaga Kependidikan, penanda unik nasional lintas-institusi). Kolom
    -- `nip` DIPERTAHANKAN apa adanya (jangan dihapus/di-drop) supaya data
    -- lama yang sudah terlanjur diisi tidak hilang, tapi tidak lagi
    -- ditampilkan/diisi lewat form atau import — nik & nuptk menggantikannya
    -- sebagai identitas resmi yang dipakai di seluruh aplikasi (form, import
    -- generik, dan ekspor Data Dosen).
    nik TEXT,
    nuptk TEXT,
    jabatan_fungsional TEXT,
    pendidikan_terakhir TEXT,
    bidang_keahlian TEXT,
    -- Fase Fondasi (Audit poin 3) — status homebase vs dosen luar prodi/
    -- fakultas/PT. Wajib untuk rasio dosen:mahasiswa (BAN-PT/LAM & BKD)
    -- yang HANYA menghitung dosen homebase sebagai basis rasio prodi.
    status_homebase TEXT DEFAULT 'Homebase',
    unit_asal TEXT,       -- nama prodi/fakultas asal jika bukan homebase
    prodi_homebase TEXT,  -- nama prodi homebase resmi (cross-check PDDIKTI)
    sk_penugasan TEXT      -- no. SK penugasan mengajar (untuk dosen luar)
);

CREATE TABLE IF NOT EXISTS pengajuan_judul (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kode_pengajuan TEXT,
    tgl_pengajuan TEXT,
    mahasiswa_id INTEGER NOT NULL,
    semester TEXT,
    tahap TEXT,
    jml_sks TEXT,
    ipk TEXT,
    judul1 TEXT,
    judul2 TEXT,
    rev1_ket TEXT,
    rev2_ket TEXT,
    rev3_ket TEXT,
    status_final TEXT DEFAULT 'Diajukan',
    tgl_review TEXT,
    catatan_reviewer TEXT,
    judul_final TEXT,
    FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS penetapan_pembimbing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mahasiswa_id INTEGER UNIQUE NOT NULL,
    semester TEXT,
    tahap TEXT,
    judul_final TEXT,
    pembimbing1_id INTEGER,
    pembimbing2_id INTEGER,
    tgl_penetapan TEXT,
    no_sk TEXT,
    pembahas1_id INTEGER,
    pembahas2_id INTEGER,
    pembahas3_id INTEGER,
    ketua_sidang_id INTEGER,
    penguji1_id INTEGER,
    penguji2_id INTEGER,
    penguji3_id INTEGER,
    penguji4_id INTEGER,
    link_sk TEXT,
    FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE
);

-- Antisipasi 'seminar ulang' — mahasiswa_id SENGAJA tidak UNIQUE (lihat
-- _rebuild_seminar_tanpa_unique() untuk migrasi instalasi lama), supaya
-- konsisten dengan `sidang` di bawah yang dari awal memang sudah
-- mendukung banyak baris per mahasiswa (mis. sidang ulang). Seminar ulang
-- jarang terjadi tapi tetap mungkin (proposal ditolak, dsb).
CREATE TABLE IF NOT EXISTS seminar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mahasiswa_id INTEGER NOT NULL,
    status TEXT DEFAULT 'Terdaftar',
    tgl_daftar TEXT,
    tgl_seminar TEXT,
    jam TEXT,
    chk_persetujuan INTEGER DEFAULT 0,
    chk_bukti_bayar INTEGER DEFAULT 0,
    chk_mendeley INTEGER DEFAULT 0,
    chk_krs INTEGER DEFAULT 0,
    chk_bimbingan INTEGER DEFAULT 0,
    chk_hardcopy INTEGER DEFAULT 0,
    chk_turnitin INTEGER DEFAULT 0,
    judul_diseminarkan TEXT,
    ada_perubahan TEXT DEFAULT 'Tidak',
    penguji_ketua_id INTEGER,
    penguji_anggota1_id INTEGER,
    penguji_anggota2_id INTEGER,
    ruangan_id INTEGER,
    FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sidang (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mahasiswa_id INTEGER NOT NULL,
    tgl_sidang TEXT,
    jam_sidang TEXT,
    judul_sidang TEXT,
    ada_perubahan TEXT DEFAULT 'Tidak',
    keterangan_perubahan TEXT,
    ketua_id INTEGER,
    sekretaris_id INTEGER,
    anggota1_id INTEGER,
    anggota2_id INTEGER,
    anggota3_id INTEGER,
    nilai_angka REAL,
    status_kelulusan TEXT,
    ruangan_id INTEGER,
    FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS yudisium (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mahasiswa_id INTEGER UNIQUE NOT NULL,
    sidang_id INTEGER,
    ipk_final REAL,
    tgl_yudisium TEXT,
    no_sk TEXT,
    status_yudisium TEXT DEFAULT 'Direncanakan',
    FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE
);

-- =============================================================================
-- Audit Menyeluruh — PHASE 3: TA Workflow Engine (riwayat transisi status_ta)
-- =============================================================================
-- Sebelum ini, status_ta hanya punya nilai TERKINI (kolom mahasiswa.status_ta)
-- tanpa jejak KAPAN & KENAPA berubah -- kalau ada pertanyaan "kok status
-- mahasiswa ini bisa berubah dari X ke Y", tidak ada cara menelusurinya
-- selain menebak dari log_aktivitas generik (yang tidak mencatat nilai
-- lama/baru secara terstruktur). Tabel ini KHUSUS untuk transisi status_ta
-- (bukan pengganti log_aktivitas umum -- itu ranah Phase 4/Audit Trail),
-- diisi oleh logic.py::recalculate_status_ta() setiap kali status_ta
-- BENAR-BENAR berubah nilainya (bukan setiap kali fungsi itu dipanggil).
CREATE TABLE IF NOT EXISTS status_ta_riwayat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mahasiswa_id INTEGER NOT NULL,
    status_lama TEXT,
    status_baru TEXT NOT NULL,
    dipicu_oleh TEXT,
    wajar INTEGER DEFAULT 1,
    waktu TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS wisuda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mahasiswa_id INTEGER UNIQUE NOT NULL,
    tgl_wisuda TEXT,
    no_ijazah TEXT,
    catatan TEXT,
    FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tracer_study (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mahasiswa_id INTEGER UNIQUE NOT NULL,
    status_saat_ini TEXT,
    nama_instansi TEXT,
    posisi TEXT,
    kesesuaian_bidang TEXT,
    waktu_tunggu TEXT,
    studi_lanjut TEXT,
    program_lanjut TEXT,
    no_hp TEXT,
    catatan TEXT,
    FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE
);

-- =============================================================================
-- Modul SDM & Kinerja Dosen (Fase Fondasi — diadaptasi dari skema AKD Excel Pro)
-- Menggantikan checklist Kinerja Dosen sederhana milik POM lama secara total.
-- Setiap tabel diberi dosen_id eksplisit (1 database untuk SEMUA dosen),
-- disiapkan agar nanti bisa dibatasi per-dosen ("WHERE dosen_id = ...") tanpa
-- perlu ubah struktur tabel, kalau suatu saat aplikasi dibuka online.
-- =============================================================================

CREATE TABLE IF NOT EXISTS aktivitas_pendidikan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dosen_id INTEGER NOT NULL,
    tahun_akademik TEXT,
    semester TEXT,
    mata_kuliah TEXT,
    kode_mk TEXT,
    sks TEXT,
    jumlah_kelas TEXT,
    jumlah_mahasiswa TEXT,
    peran TEXT,
    status TEXT DEFAULT 'Selesai',
    catatan TEXT,
    FOREIGN KEY(dosen_id) REFERENCES dosen(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS aktivitas_penelitian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kode TEXT UNIQUE,
    dosen_id INTEGER NOT NULL,
    judul TEXT NOT NULL,
    skema TEXT,
    sumber_dana TEXT,
    nominal REAL DEFAULT 0,
    pelaksana TEXT,
    tahun_akademik TEXT,
    semester TEXT,
    tgl_publish TEXT,
    jurnal TEXT,
    jilid TEXT,
    volume TEXT,
    halaman TEXT,
    status TEXT,
    jenis_luaran TEXT,
    doi TEXT,
    issn_isbn TEXT,
    url TEXT,
    lokasi_bukti TEXT,
    catatan TEXT,
    FOREIGN KEY(dosen_id) REFERENCES dosen(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS aktivitas_pkm (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kode TEXT UNIQUE,
    dosen_id INTEGER NOT NULL,
    judul TEXT NOT NULL,
    jenis TEXT,
    skema TEXT,
    lokasi TEXT,
    mitra TEXT,
    dana REAL DEFAULT 0,
    tahun_akademik TEXT,
    semester TEXT,
    status TEXT,
    jenis_luaran TEXT,
    url TEXT,
    lokasi_bukti TEXT,
    catatan TEXT,
    FOREIGN KEY(dosen_id) REFERENCES dosen(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS aktivitas_penunjang (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dosen_id INTEGER NOT NULL,
    jenis_penunjang TEXT,
    nama_kegiatan TEXT,
    peran TEXT,
    tanggal TEXT,
    tahun_akademik TEXT,
    semester TEXT,
    status TEXT,
    url TEXT,
    lokasi_bukti TEXT,
    catatan TEXT,
    FOREIGN KEY(dosen_id) REFERENCES dosen(id) ON DELETE CASCADE
);

-- Gabungan 7 sheet luaran workbook asal (Publikasi/HKI/Buku/Prosiding/
-- Seminar/Sertifikat/Penghargaan) jadi 1 tabel dengan kolom jenis_luaran,
-- supaya skema tetap ramping (lihat rancangan-final-modul-sdm-kinerja-dosen.md).
CREATE TABLE IF NOT EXISTS luaran_dosen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kode TEXT UNIQUE,
    dosen_id INTEGER NOT NULL,
    jenis_luaran TEXT NOT NULL,
    judul TEXT NOT NULL,
    penulis_terkait TEXT,
    tahun_akademik TEXT,
    semester TEXT,
    nomor_identitas TEXT,
    penerbit_instansi TEXT,
    sumber_dana TEXT,
    status TEXT,
    masa_berlaku TEXT,
    url TEXT,
    lokasi_bukti TEXT,
    keterangan_tambahan TEXT,
    penelitian_id INTEGER,
    pkm_id INTEGER,
    catatan TEXT,
    FOREIGN KEY(dosen_id) REFERENCES dosen(id) ON DELETE CASCADE,
    FOREIGN KEY(penelitian_id) REFERENCES aktivitas_penelitian(id) ON DELETE SET NULL,
    FOREIGN KEY(pkm_id) REFERENCES aktivitas_pkm(id) ON DELETE SET NULL
);

-- Gabungan 7 sheet peran akademik workbook asal (Reviewer/Editor/Pembimbing/
-- Penguji/Organisasi Profesi/Jabatan/Pelatihan) jadi 1 tabel + jenis_peran.
CREATE TABLE IF NOT EXISTS peran_akademik_dosen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dosen_id INTEGER NOT NULL,
    jenis_peran TEXT NOT NULL,
    nama_instansi_kegiatan TEXT NOT NULL,
    peran_jabatan TEXT,
    tgl_mulai TEXT,
    tgl_selesai TEXT,
    tahun_akademik TEXT,
    semester TEXT,
    status TEXT,
    url TEXT,
    lokasi_bukti TEXT,
    catatan TEXT,
    FOREIGN KEY(dosen_id) REFERENCES dosen(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS timeline_karier_dosen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dosen_id INTEGER NOT NULL,
    jenis_perubahan TEXT,
    keterangan TEXT,
    no_sk TEXT,
    tgl_mulai TEXT,
    tgl_berakhir_target TEXT,
    instansi_penerbit TEXT,
    status TEXT,
    lokasi_bukti TEXT,
    catatan TEXT,
    FOREIGN KEY(dosen_id) REFERENCES dosen(id) ON DELETE CASCADE
);

-- realisasi TIDAK disimpan di sini — dihitung on-the-fly dari COUNT(luaran_dosen)
-- per dosen+tahun+kategori tiap kali dashboard/laporan dibuka, supaya tidak
-- pernah basi seperti rumus Excel yang bisa lupa di-refresh.
CREATE TABLE IF NOT EXISTS target_kinerja_dosen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dosen_id INTEGER NOT NULL,
    tahun INTEGER NOT NULL,
    kategori TEXT NOT NULL,
    target_angka REAL DEFAULT 0,
    keterangan TEXT,
    FOREIGN KEY(dosen_id) REFERENCES dosen(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS log_aktivitas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    waktu TEXT DEFAULT (datetime('now','localtime')),
    aksi TEXT,
    detail TEXT
);

-- =============================================================================
-- Modul 5 — Akademik Operasional & Kalender
-- =============================================================================
CREATE TABLE IF NOT EXISTS kalender_akademik (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    judul TEXT NOT NULL,
    kategori TEXT DEFAULT 'Akademik',
    tgl_mulai TEXT NOT NULL,
    tgl_selesai TEXT,
    jam TEXT,
    lokasi TEXT,
    deskripsi TEXT,
    status TEXT DEFAULT 'Terjadwal',
    pengingat_hari INTEGER DEFAULT 3,
    dibuat_pada TEXT DEFAULT (datetime('now','localtime'))
);

-- =============================================================================
-- Modul 6 — Kegiatan & Program Kerja Prodi
-- =============================================================================
CREATE TABLE IF NOT EXISTS program_kerja (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tahun_akademik TEXT,
    bidang TEXT,
    nama_program TEXT NOT NULL,
    indikator_kinerja TEXT,
    target TEXT,
    satuan TEXT,
    anggaran_rencana REAL DEFAULT 0,
    penanggung_jawab TEXT,
    status TEXT DEFAULT 'Direncanakan',
    catatan TEXT
);

CREATE TABLE IF NOT EXISTS kegiatan_prodi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_kerja_id INTEGER,
    nama_kegiatan TEXT NOT NULL,
    kategori TEXT,
    tgl_mulai TEXT,
    tgl_selesai TEXT,
    lokasi TEXT,
    penanggung_jawab TEXT,
    jumlah_peserta TEXT,
    anggaran_realisasi REAL DEFAULT 0,
    sumber_dana TEXT,
    status TEXT DEFAULT 'Direncanakan',
    lokasi_bukti TEXT,
    catatan TEXT,
    FOREIGN KEY(program_kerja_id) REFERENCES program_kerja(id) ON DELETE SET NULL
);

-- =============================================================================
-- Modul 7 — Document Center
-- =============================================================================
CREATE TABLE IF NOT EXISTS dokumen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    judul TEXT NOT NULL,
    kategori TEXT DEFAULT 'Lainnya',
    nomor_dokumen TEXT,
    tgl_dokumen TEXT,
    sumber_instansi TEXT,
    file_path TEXT,
    nama_file_asli TEXT,
    ukuran_kb INTEGER,
    keterangan TEXT,
    diunggah_pada TEXT DEFAULT (datetime('now','localtime'))
);

-- =============================================================================
-- Modul 8 — Generator Surat Umum (di luar TA) + Buku Agenda Surat Keluar
-- =============================================================================
CREATE TABLE IF NOT EXISTS surat_keluar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomor_surat TEXT,
    jenis_surat TEXT NOT NULL,
    perihal TEXT NOT NULL,
    tujuan TEXT,
    tanggal_surat TEXT,
    isi_ringkas TEXT,
    penandatangan TEXT,
    jabatan_penandatangan TEXT,
    tembusan TEXT,
    lokasi_file TEXT,
    dibuat_pada TEXT DEFAULT (datetime('now','localtime'))
);

-- =============================================================================
-- Modul 9 — Kurikulum & OBE (Outcome-Based Education)
-- =============================================================================
-- Skema mengikuti siklus OBE standar SN-DIKTI/LAMEMBA yang dipakai di
-- dokumen akreditasi prodi: Profil Lulusan -> CPL (kategori Sikap/
-- Pengetahuan/Keterampilan Umum/Keterampilan Khusus) -> CPMK per Mata
-- Kuliah -> pemetaan CPMK-CPL -> status penyusunan RPS. Tidak ada data
-- akademik yang diisi otomatis/tebakan — kurikulum aktif dibuat kosong,
-- diisi manual oleh Kaprodi/tim kurikulum lewat form.
CREATE TABLE IF NOT EXISTS kurikulum_versi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL,
    tahun_berlaku TEXT,
    status TEXT DEFAULT 'Draft',
    keterangan TEXT,
    dibuat_pada TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS cpl (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kurikulum_id INTEGER NOT NULL,
    kode TEXT NOT NULL,
    kategori TEXT DEFAULT 'Pengetahuan',
    deskripsi TEXT NOT NULL,
    urutan INTEGER DEFAULT 0,
    FOREIGN KEY(kurikulum_id) REFERENCES kurikulum_versi(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mata_kuliah (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kurikulum_id INTEGER NOT NULL,
    kode TEXT NOT NULL,
    nama TEXT NOT NULL,
    sks INTEGER DEFAULT 2,
    semester INTEGER DEFAULT 1,
    jenis TEXT DEFAULT 'Wajib',
    kelompok_mk TEXT,
    rps_status TEXT DEFAULT 'Belum Disusun',
    rps_file TEXT,
    rps_nama_file_asli TEXT,
    rps_revisi TEXT,
    rps_tanggal_sahkan TEXT,
    keterangan TEXT,
    FOREIGN KEY(kurikulum_id) REFERENCES kurikulum_versi(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cpmk (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mata_kuliah_id INTEGER NOT NULL,
    kode TEXT NOT NULL,
    deskripsi TEXT NOT NULL,
    FOREIGN KEY(mata_kuliah_id) REFERENCES mata_kuliah(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cpmk_cpl (
    cpmk_id INTEGER NOT NULL,
    cpl_id INTEGER NOT NULL,
    PRIMARY KEY(cpmk_id, cpl_id),
    FOREIGN KEY(cpmk_id) REFERENCES cpmk(id) ON DELETE CASCADE,
    FOREIGN KEY(cpl_id) REFERENCES cpl(id) ON DELETE CASCADE
);

-- =============================================================================
-- Modul 9 lanjutan — Sub-CPMK
-- Rantai keterlacakan OBE diperhalus satu tingkat: CPMK -> Sub-CPMK, supaya
-- setiap pertemuan di BAP (Modul 10) bisa ditautkan ke unit capaian yang
-- lebih kecil daripada CPMK per mata kuliah. Opsional dipakai — CPMK tanpa
-- Sub-CPMK tetap valid (RPS sederhana tidak wajib dipecah lebih lanjut).
-- =============================================================================
CREATE TABLE IF NOT EXISTS sub_cpmk (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cpmk_id INTEGER NOT NULL,
    kode TEXT NOT NULL,
    deskripsi TEXT NOT NULL,
    urutan INTEGER DEFAULT 0,
    FOREIGN KEY(cpmk_id) REFERENCES cpmk(id) ON DELETE CASCADE
);

-- =============================================================================
-- Modul 10 — Jadwal Kelas & BAP (Berita Acara Perkuliahan)
-- Fondasi data akademik tambahan yang sebelumnya belum ada di SIMPRODI:
-- jadwal kelas per tahun akademik/semester, dipakai juga oleh Modul 11
-- (Nilai & OBE Assessment Engine) sebagai unit "siapa mengambil mata
-- kuliah apa, di kelas mana".
-- =============================================================================
CREATE TABLE IF NOT EXISTS jadwal_kelas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mata_kuliah_id INTEGER NOT NULL,
    tahun_akademik TEXT NOT NULL,
    semester_ajaran TEXT DEFAULT 'Ganjil',
    kelas TEXT DEFAULT 'A',
    dosen_id INTEGER,
    hari TEXT,
    jam_mulai TEXT,
    jam_selesai TEXT,
    ruangan_id INTEGER,
    jumlah_pertemuan_rencana INTEGER DEFAULT 16,
    keterangan TEXT,
    FOREIGN KEY(mata_kuliah_id) REFERENCES mata_kuliah(id) ON DELETE CASCADE,
    FOREIGN KEY(dosen_id) REFERENCES dosen(id) ON DELETE SET NULL,
    FOREIGN KEY(ruangan_id) REFERENCES ruangan(id) ON DELETE SET NULL
);

-- realisasi materi TIDAK disimpan sebagai angka statis — dihitung on-the-fly
-- dari COUNT(bap) berstatus 'Terlaksana' per jadwal_kelas, mengikuti prinsip
-- yang sama dengan realisasi_target_kinerja & realisasi program kerja.
CREATE TABLE IF NOT EXISTS bap (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jadwal_kelas_id INTEGER NOT NULL,
    pertemuan_ke INTEGER NOT NULL,
    tanggal TEXT,
    materi TEXT,
    sub_cpmk_id INTEGER,
    jumlah_hadir INTEGER,
    dosen_pengganti TEXT,
    catatan TEXT,
    status TEXT DEFAULT 'Terlaksana',
    FOREIGN KEY(jadwal_kelas_id) REFERENCES jadwal_kelas(id) ON DELETE CASCADE,
    FOREIGN KEY(sub_cpmk_id) REFERENCES sub_cpmk(id) ON DELETE SET NULL,
    UNIQUE(jadwal_kelas_id, pertemuan_ke)
);

-- =============================================================================
-- Modul 11 — Nilai Mahasiswa & OBE Assessment Engine
-- KRS (kartu rencana studi) di sini disederhanakan jadi tabel peserta kelas
-- (mahasiswa terdaftar di 1 jadwal_kelas). nilai_cpmk menyimpan nilai per
-- CPMK per mahasiswa — inilah yang membuat rantai keterlacakan OBE lengkap:
-- CPL -> CPMK -> nilai_cpmk (per mahasiswa) -> capaian CPL individu/program.
-- =============================================================================
CREATE TABLE IF NOT EXISTS krs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mahasiswa_id INTEGER NOT NULL,
    jadwal_kelas_id INTEGER NOT NULL,
    nilai_akhir REAL,
    nilai_huruf TEXT,
    FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE,
    FOREIGN KEY(jadwal_kelas_id) REFERENCES jadwal_kelas(id) ON DELETE CASCADE,
    UNIQUE(mahasiswa_id, jadwal_kelas_id)
);

CREATE TABLE IF NOT EXISTS nilai_cpmk (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    krs_id INTEGER NOT NULL,
    cpmk_id INTEGER NOT NULL,
    nilai_angka REAL,
    FOREIGN KEY(krs_id) REFERENCES krs(id) ON DELETE CASCADE,
    FOREIGN KEY(cpmk_id) REFERENCES cpmk(id) ON DELETE CASCADE,
    UNIQUE(krs_id, cpmk_id)
);

-- =============================================================================
-- Modul 12 — Siklus CQI (Continuous Quality Improvement) / Gap Analysis
-- Gap dihitung dari selisih target_persen (ditetapkan tim kurikulum) vs
-- capaian_persen (dibekukan/snapshot saat siklus dibuat, dari OBE Assessment
-- Engine) — snapshot disengaja supaya rencana tindak lanjut tidak "bergeser"
-- kalau ada nilai baru masuk setelah siklus CQI dibuka.
-- =============================================================================
CREATE TABLE IF NOT EXISTS cqi_siklus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kurikulum_id INTEGER NOT NULL,
    cpl_id INTEGER NOT NULL,
    tahun_akademik TEXT NOT NULL,
    target_persen REAL DEFAULT 70,
    capaian_persen REAL,
    akar_masalah TEXT,
    rencana_tindak_lanjut TEXT,
    penanggung_jawab TEXT,
    tenggat TEXT,
    status TEXT DEFAULT 'Direncanakan',
    evaluasi_hasil TEXT,
    dibuat_pada TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY(kurikulum_id) REFERENCES kurikulum_versi(id) ON DELETE CASCADE,
    FOREIGN KEY(cpl_id) REFERENCES cpl(id) ON DELETE CASCADE
);

-- =============================================================================
-- Modul 13 — Semester Pendek (SP)
-- Mengikuti pola pasangan jadwal_kelas/bap (Modul 10) & krs (Modul 11):
-- sp_kelas = penawaran kelas SP per periode (mata kuliah dari kurikulum
-- aktif), sp_peserta = pendaftaran+approval+nilai akhir mahasiswa per kelas
-- SP (nilai disimpan langsung di sini, bukan tabel terpisah, karena SP
-- tidak memakai rantai CPMK/OBE seperti kelas reguler), sp_pertemuan+
-- sp_presensi = log pertemuan & kehadiran per mahasiswa (SP mewajibkan
-- ambang kehadiran, lihat constants.SP_AMBANG_KEHADIRAN). Status kapasitas
-- kelas ("Dibuka"/"Kurang Kuota"/"Penuh") TIDAK disimpan statis — dihitung
-- on-the-fly dari COUNT(sp_peserta disetujui) vs kuota_min/kuota_maks,
-- konsisten dengan prinsip realisasi_bap/realisasi program kerja.
-- =============================================================================
CREATE TABLE IF NOT EXISTS sp_periode (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL,
    tahun_akademik TEXT,
    tgl_mulai_daftar TEXT,
    tgl_selesai_daftar TEXT,
    tgl_mulai_kuliah TEXT,
    tgl_selesai_kuliah TEXT,
    maks_sks INTEGER DEFAULT 9,
    kuota_min_default INTEGER DEFAULT 15,
    biaya_per_sks REAL DEFAULT 0,
    hanya_mengulang INTEGER DEFAULT 1,
    jumlah_pertemuan_rencana INTEGER DEFAULT 8,
    status TEXT DEFAULT 'Draft',
    keterangan TEXT,
    dibuat_pada TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS sp_kelas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    periode_id INTEGER NOT NULL,
    mata_kuliah_id INTEGER NOT NULL,
    dosen_id INTEGER,
    ruangan_id INTEGER,
    kuota_min INTEGER,
    kuota_maks INTEGER DEFAULT 40,
    hari TEXT,
    jam_mulai TEXT,
    jam_selesai TEXT,
    keterangan TEXT,
    FOREIGN KEY(periode_id) REFERENCES sp_periode(id) ON DELETE CASCADE,
    FOREIGN KEY(mata_kuliah_id) REFERENCES mata_kuliah(id) ON DELETE CASCADE,
    FOREIGN KEY(dosen_id) REFERENCES dosen(id) ON DELETE SET NULL,
    FOREIGN KEY(ruangan_id) REFERENCES ruangan(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS sp_peserta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sp_kelas_id INTEGER NOT NULL,
    mahasiswa_id INTEGER NOT NULL,
    alasan_mengulang TEXT,
    nilai_sebelumnya TEXT,
    status_approval TEXT DEFAULT 'Menunggu',
    tgl_daftar TEXT DEFAULT (datetime('now','localtime')),
    tugas REAL,
    uts REAL,
    uas REAL,
    nilai_akhir REAL,
    nilai_huruf TEXT,
    catatan TEXT,
    FOREIGN KEY(sp_kelas_id) REFERENCES sp_kelas(id) ON DELETE CASCADE,
    FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE,
    UNIQUE(sp_kelas_id, mahasiswa_id)
);

CREATE TABLE IF NOT EXISTS sp_pertemuan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sp_kelas_id INTEGER NOT NULL,
    pertemuan_ke INTEGER NOT NULL,
    tanggal TEXT,
    materi TEXT,
    status TEXT DEFAULT 'Terlaksana',
    catatan TEXT,
    FOREIGN KEY(sp_kelas_id) REFERENCES sp_kelas(id) ON DELETE CASCADE,
    UNIQUE(sp_kelas_id, pertemuan_ke)
);

-- kehadiran per mahasiswa per pertemuan (bukan agregat) — supaya persentase
-- kehadiran wajib 80% SP bisa dihitung per peserta, bukan hanya per kelas.
CREATE TABLE IF NOT EXISTS sp_presensi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sp_pertemuan_id INTEGER NOT NULL,
    sp_peserta_id INTEGER NOT NULL,
    hadir INTEGER DEFAULT 1,
    FOREIGN KEY(sp_pertemuan_id) REFERENCES sp_pertemuan(id) ON DELETE CASCADE,
    FOREIGN KEY(sp_peserta_id) REFERENCES sp_peserta(id) ON DELETE CASCADE,
    UNIQUE(sp_pertemuan_id, sp_peserta_id)
);

-- =============================================================================
-- Modul 14 — RPL (Rekognisi Pembelajaran Lampau)
-- Berdiri sendiri dari kolom mahasiswa.skema ('RPL') yang sudah ada sejak
-- Fase Fondasi (itu untuk mahasiswa yang SUDAH diterima). Modul ini
-- mengelola proses ASESMEN sebelum diterima: pendaftar -> verifikasi berkas
-- (rpl_dokumen, pola sama dengan Document Center Modul 7) -> asesmen
-- konversi SKS per mata kuliah (rpl_konversi, many-to-1 ke rpl_pendaftar)
-- -> keputusan status. rpl_pendaftar.mahasiswa_id opsional diisi manual
-- kalau pendaftar sudah resmi didaftarkan lewat modul Data Mahasiswa
-- (skema='RPL') — modul ini TIDAK auto-membuat baris mahasiswa (perlu NIM
-- dsb yang tak boleh ditebak), konsisten dengan prinsip "tidak ada data
-- yang diisi otomatis/tebakan" yang dipakai Modul 9.
-- =============================================================================
CREATE TABLE IF NOT EXISTS rpl_pendaftar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL,
    no_identitas TEXT,
    no_hp TEXT,
    email TEXT,
    jenis_pengakuan TEXT DEFAULT 'Pengalaman Kerja',
    asal_instansi_pendidikan TEXT,
    lama_pengalaman TEXT,
    tgl_daftar TEXT DEFAULT (datetime('now','localtime')),
    status TEXT DEFAULT 'Verifikasi Berkas',
    catatan_asesor TEXT,
    mahasiswa_id INTEGER,
    FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS rpl_dokumen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rpl_pendaftar_id INTEGER NOT NULL,
    jenis_dokumen TEXT DEFAULT 'Lainnya',
    judul TEXT,
    file_path TEXT,
    nama_file_asli TEXT,
    ukuran_kb INTEGER,
    diunggah_pada TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY(rpl_pendaftar_id) REFERENCES rpl_pendaftar(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rpl_konversi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rpl_pendaftar_id INTEGER NOT NULL,
    mata_kuliah_id INTEGER NOT NULL,
    sks_diakui INTEGER DEFAULT 0,
    nilai_konversi TEXT,
    dasar_pengakuan TEXT,
    catatan TEXT,
    FOREIGN KEY(rpl_pendaftar_id) REFERENCES rpl_pendaftar(id) ON DELETE CASCADE,
    FOREIGN KEY(mata_kuliah_id) REFERENCES mata_kuliah(id) ON DELETE CASCADE,
    UNIQUE(rpl_pendaftar_id, mata_kuliah_id)
);

-- =============================================================================
-- Modul 15 — Penelitian, PKM & Publikasi/HKI (Tri Dharma Program Studi)
-- SENGAJA TIDAK menduplikasi data: aktivitas_penelitian, aktivitas_pkm, dan
-- luaran_dosen SUDAH ada sejak Fase Fondasi (Modul 4 — SDM & Kinerja Dosen,
-- diadaptasi dari workbook AKD Excel Pro) dan sudah dipakai untuk CRUD per
-- dosen di routes/sdm.py. Modul 15 dibangun DI ATAS tabel yang sama untuk
-- tampilan lintas-dosen tingkat program studi (rekap, filter, dashboard
-- eksekutif) — persis seperti maksud deskripsi roadmap lama ("Rekap ...
-- dosen sebagai bagian dari pelaporan Tri Dharma", "Basis data ... program
-- studi"). Satu-satunya tabel BARU adalah tridharma_tinjauan: lapisan
-- tinjauan/keputusan INSTITUSIONAL (oleh Kaprodi/GKM) atas usulan
-- penelitian/PKM, terpisah dari status_aktivitas yang sifatnya laporan
-- mandiri dosen (self-report) — pola pemisahan yang sama seperti
-- pengajuan_judul (mahasiswa mengajukan) vs kolom status_final/
-- catatan_reviewer (Kaprodi meninjau) di modul Tugas Akhir.
-- =============================================================================
CREATE TABLE IF NOT EXISTS tridharma_tinjauan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    penelitian_id INTEGER,
    pkm_id INTEGER,
    status_tinjauan TEXT DEFAULT 'Belum Ditinjau',
    catatan_tinjauan TEXT,
    tenggat_laporan TEXT,
    tgl_tinjauan TEXT,
    ditinjau_oleh TEXT,
    FOREIGN KEY(penelitian_id) REFERENCES aktivitas_penelitian(id) ON DELETE CASCADE,
    FOREIGN KEY(pkm_id) REFERENCES aktivitas_pkm(id) ON DELETE CASCADE,
    UNIQUE(penelitian_id),
    UNIQUE(pkm_id)
);

-- =============================================================================
-- Modul 16 — Kerja Sama & Mitra
-- Domain baru (belum ada tabel yang menaunginya), tapi TETAP direlevansikan
-- ke modul yang sudah ada lewat FK opsional, bukan sekadar label teks
-- seperti demo SITIPRO ("Terintegrasi dengan Modul Tri Dharma" hanya
-- berupa string kategori di sana):
--  - mitra_program.pic_dosen_id -> dosen (Modul 4, PIC internal program)
--  - mitra_program.penelitian_id/pkm_id -> aktivitas_penelitian/aktivitas_pkm
--    (Modul 4/15, dual-nullable-FK, pola sama dengan tridharma_tinjauan)
--  - mitra_luaran.luaran_dosen_id -> luaran_dosen (Modul 4/15, opsional,
--    supaya publikasi/HKI hasil kerja sama tidak dicatat dua kali)
-- Dokumen MoU/MoA/IA SENGAJA punya tabel sendiri (mitra_dokumen), bukan
-- dipaksakan ke tabel `dokumen` (Document Center Modul 7) yang sudah punya
-- kategori 'MoU/Kerjasama' — karena kebutuhannya beda: siklus hidup
-- per-mitra dengan tanggal berakhir & status untuk reminder kadaluarsa,
-- yang tidak dimiliki skema `dokumen` yang generik. Pola ini sama seperti
-- rpl_dokumen (Modul 14) yang juga tidak dipaksakan ke Document Center.
-- =============================================================================
CREATE TABLE IF NOT EXISTS mitra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL,
    kategori TEXT DEFAULT 'Instansi Pemerintah',
    skala TEXT DEFAULT 'Nasional',
    negara TEXT DEFAULT 'Indonesia',
    alamat TEXT,
    kontak_person TEXT,
    no_hp TEXT,
    email TEXT,
    deskripsi TEXT,
    catatan TEXT,
    dibuat_pada TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS mitra_dokumen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mitra_id INTEGER NOT NULL,
    jenis_dokumen TEXT DEFAULT 'MoU (Nota Kesepahaman)',
    nomor_dokumen TEXT,
    judul TEXT,
    tgl_mulai TEXT,
    tgl_berakhir TEXT,
    status TEXT DEFAULT 'Aktif',
    file_path TEXT,
    nama_file_asli TEXT,
    ukuran_kb INTEGER,
    catatan TEXT,
    diunggah_pada TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY(mitra_id) REFERENCES mitra(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mitra_program (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mitra_id INTEGER NOT NULL,
    nama_program TEXT NOT NULL,
    jenis_program TEXT DEFAULT 'Pendidikan/MBKM',
    pic_dosen_id INTEGER,
    penelitian_id INTEGER,
    pkm_id INTEGER,
    tgl_mulai TEXT,
    tgl_selesai TEXT,
    status TEXT DEFAULT 'Perencanaan',
    skor_kepuasan INTEGER,
    deskripsi TEXT,
    catatan TEXT,
    FOREIGN KEY(mitra_id) REFERENCES mitra(id) ON DELETE CASCADE,
    FOREIGN KEY(pic_dosen_id) REFERENCES dosen(id) ON DELETE SET NULL,
    FOREIGN KEY(penelitian_id) REFERENCES aktivitas_penelitian(id) ON DELETE SET NULL,
    FOREIGN KEY(pkm_id) REFERENCES aktivitas_pkm(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS mitra_luaran (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mitra_program_id INTEGER NOT NULL,
    jenis_luaran TEXT DEFAULT 'Lainnya',
    judul TEXT NOT NULL,
    jumlah INTEGER,
    tanggal TEXT,
    luaran_dosen_id INTEGER,
    catatan TEXT,
    FOREIGN KEY(mitra_program_id) REFERENCES mitra_program(id) ON DELETE CASCADE,
    FOREIGN KEY(luaran_dosen_id) REFERENCES luaran_dosen(id) ON DELETE SET NULL
);

-- =============================================================================
-- Modul 17 — Mutu: IKU, Akreditasi & Audit Mutu Internal (SPMI)
-- CATATAN PENTING soal relevansi: SITIPRO hanya benar-benar merutekan
-- /audit-qa (AuditQA.tsx); /iku dan /akreditasi TIDAK PERNAH punya file
-- komponen sama sekali di demo aslinya (App.tsx mengimpor & merutekan
-- AuditQA saja). Jadi IKU & Akreditasi dirancang dari kerangka resmi
-- Kemendikbudristek (8 IKU Perguruan Tinggi) dan LAMEMBA (9 Kriteria
-- Akreditasi, relevan untuk program S1 Administrasi Bisnis/Niaga sesuai
-- profil program studi), BUKAN diadaptasi dari kode SITIPRO yang tidak
-- ada. AuditQA.tsx sendiri (Data Integrity/Workflow/System Health/
-- Security) juga diterjemahkan ulang total: kontennya berorientasi
-- sistem terdistribusi multi-server (System Health 99.9%, Security
-- Alerts) yang tidak relevan untuk SIMPRODI (aplikasi Flask+SQLite
-- single-tenant offline) — diganti Audit Mutu Internal (AMI/SPMI) yang
-- sungguhan berlaku di perguruan tinggi Indonesia, plus dua fitur yang
-- justru punya padanan paling jujur di arsitektur SIMPRODI: pemindai
-- Kelengkapan Data (baca langsung tabel-tabel yang sudah ada, pengganti
-- "Data Integrity" versi nyata) dan penampil log_aktivitas (tabel yang
-- SUDAH ditulis oleh log() di setiap modul sejak Fase Fondasi tapi belum
-- pernah punya UI — pengganti "Security & Logs" versi nyata).
--
-- Realisasi IKU dihitung on-the-fly lintas modul yang sudah ada, BUKAN
-- diketik manual — target_iku hanya menyimpan target & (untuk IKU yang
-- memang tidak bisa dihitung dari data SIMPRODI) realisasi manual:
--   IKU 1 <- tracer_study.status_saat_ini (Modul Kelulusan)
--   IKU 2 <- mitra_luaran jenis 'Mahasiswa Magang/MBKM' (Modul 16)
--   IKU 3 <- aktivitas_penunjang (Modul 4)
--   IKU 4 <- mitra_program jenis 'Praktisi Mengajar' (Modul 16)
--   IKU 5 <- luaran_dosen jenis Publikasi/HKI + aktivitas_pkm bermitra (Modul 4/15)
--   IKU 6 <- mitra skala 'Internasional' berdokumen aktif (Modul 16)
--   IKU 7, IKU 8 <- belum ada sumber data di SIMPRODI, realisasi_manual
-- =============================================================================
CREATE TABLE IF NOT EXISTS target_iku (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tahun TEXT NOT NULL,
    nomor_iku INTEGER NOT NULL,
    target_nilai REAL,
    realisasi_manual REAL,
    catatan TEXT,
    UNIQUE(tahun, nomor_iku)
);

CREATE TABLE IF NOT EXISTS akreditasi_kriteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomor_kriteria INTEGER NOT NULL UNIQUE,
    nama_kriteria TEXT NOT NULL,
    pic_dosen_id INTEGER,
    status TEXT DEFAULT 'Belum Disusun',
    catatan TEXT,
    FOREIGN KEY(pic_dosen_id) REFERENCES dosen(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS akreditasi_bukti (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kriteria_id INTEGER NOT NULL,
    judul TEXT NOT NULL,
    file_path TEXT,
    nama_file_asli TEXT,
    ukuran_kb INTEGER,
    diunggah_pada TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY(kriteria_id) REFERENCES akreditasi_kriteria(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ami_siklus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL,
    tahun_akademik TEXT,
    tgl_pelaksanaan TEXT,
    auditor TEXT,
    status TEXT DEFAULT 'Direncanakan',
    catatan TEXT,
    dibuat_pada TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS ami_temuan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    siklus_id INTEGER NOT NULL,
    standar_spmi TEXT,
    uraian_temuan TEXT NOT NULL,
    kategori TEXT DEFAULT 'Observasi',
    akar_masalah TEXT,
    rencana_tindak_lanjut TEXT,
    pic_dosen_id INTEGER,
    tenggat TEXT,
    status TEXT DEFAULT 'Terbuka',
    FOREIGN KEY(siklus_id) REFERENCES ami_siklus(id) ON DELETE CASCADE,
    FOREIGN KEY(pic_dosen_id) REFERENCES dosen(id) ON DELETE SET NULL
);

-- Fase Pejabat Struktural — direktori pejabat struktural institusi
-- (Rektor, Wakil Rektor, Dekan, Wakil Dekan, Kaprodi, Sekretaris Prodi,
-- dst). Sebelum ini nama/jabatan penandatangan SK & surat hanya tersimpan
-- sebagai 2 baris teks bebas di Pengaturan (nama_penandatangan_default/
-- jabatan_penandatangan_default) tanpa direktori terstruktur, dan
-- _footer_ttd() di routes/surat.py bahkan TIDAK memakainya sama sekali
-- (nama penandatangan selalu dikosongkan manual di setiap SK Tugas Akhir).
-- Tabel ini jadi satu sumber data terstruktur untuk seluruh jajaran
-- pejabat, sekaligus half yang dipakai untuk mengisi blok tanda tangan
-- SK/Surat secara otomatis lewat "Jadikan Default Penandatangan".
CREATE TABLE IF NOT EXISTS pejabat_struktural (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jabatan TEXT NOT NULL,         -- mis. "Rektor", "Dekan", "Ketua Program Studi (Kaprodi)"
    unit TEXT,                     -- nama fakultas/prodi terkait (kosong utk Rektor tingkat institusi)
    nama TEXT NOT NULL,            -- nama lengkap + gelar, mis. "Dr. Contoh Nama, M.Kom."
    nip_nidn TEXT,                 -- NIP (PNS) atau NIDN, ditampilkan di blok tanda tangan SK
    no_sk_pengangkatan TEXT,
    tmt TEXT,                      -- Terhitung Mulai Tanggal menjabat
    masa_akhir TEXT,               -- akhir periode jabatan, boleh kosong (masih menjabat)
    urutan INTEGER DEFAULT 0,      -- urutan tampil (mis. Rektor di atas Dekan di atas Kaprodi)
    aktif INTEGER DEFAULT 1,
    dibuat_pada TEXT DEFAULT (datetime('now','localtime'))
);
"""


def home_dir():
    """Folder home pengguna — SATU tempat rujukan tunggal dipakai di
    SELURUH aplikasi (db.py, backup_core.py, dan semua routes/*.py yang
    menyimpan file: dokumen, mitra_dokumen, surat_keluar, branding,
    tmp_import, rpl_dokumen, rps, akreditasi_bukti).

    Ditemukan lewat build .exe sungguhan di GitHub Actions Windows
    (bukan cuma dugaan): `os.path.expanduser("~")` semula dipanggil
    LANGSUNG di 9 file berbeda. Di Linux itu memang membaca env var HOME,
    tapi sejak Python 3.8 (bpo-36264, "os.path.expanduser should not use
    HOME on windows") ntpath.expanduser() SENGAJA MENGABAIKAN HOME dan
    selalu pakai USERPROFILE di Windows. Akibatnya SEMUA 20 file test
    yang mengisolasi datanya lewat `os.environ["HOME"] = tmpdir` gagal
    total di Windows CI — bukan diarahkan ke folder sementara, tapi
    tetap menulis ke folder home ASLI runner, sehingga test-test yang
    berjalan berurutan di job yang sama saling mengotori data satu sama
    lain (persis pola kegagalan yang muncul: test_backup_reminder.py
    menemukan backup "asing" peninggalan test sebelumnya).

    Perbaikan: cek HOME secara eksplisit dulu di SEMUA platform, baru
    fallback ke os.path.expanduser("~"). Ini AMAN untuk pengguna akhir
    Windows biasa (klik 2x .exe) karena HOME normalnya memang tidak
    pernah di-set di situ, jadi perilakunya sama persis seperti sebelum
    perbaikan ini (tetap jatuh ke USERPROFILE) — yang berubah HANYA saat
    HOME sengaja di-set (mis. oleh test, atau lingkungan Git
    Bash/MSYS/WSL yang memang menyediakan HOME)."""
    return os.environ.get("HOME") or os.path.expanduser("~")


def get_default_db_path():
    """Lokasi default file database — folder Documents pengguna, offline.
    SAMA PERSIS dengan versi desktop, supaya database yang sudah ada bisa
    langsung dipakai versi web ini tanpa perlu pindah file."""
    home = home_dir()
    folder = os.path.join(home, "SistemSkripsi")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "data_prodi.db")


def _column_exists(conn, table, column):
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return column in cols


def _migrate(conn):
    """Migrasi ringan & idempoten — menambah kolom/tabel baru tanpa
    menghapus data lama. Aman dijalankan di database versi desktop lama."""
    additions = [
        ("seminar", "ruangan_id", "INTEGER"),
        ("sidang", "ruangan_id", "INTEGER"),
        ("mahasiswa", "skema", "TEXT DEFAULT 'Reguler'"),
        # Audit Menyeluruh — PHASE 4: Audit Trail generik. log_aktivitas
        # sejak Fase Fondasi hanya (aksi, detail) bebas teks -- cukup utk
        # jejak "apa yang terjadi", tapi tidak cukup utk pertanyaan audit
        # SPMI/AMI/akreditasi yang lebih spesifik: "kolom APA yang berubah,
        # dari NILAI apa ke NILAI apa, pada BARIS mana". Kolom baru ini
        # NULLABLE & OPSIONAL -- 112 pemanggilan db.log(conn, aksi, detail)
        # yang sudah ada di seluruh route tetap jalan tanpa perubahan;
        # hanya titik-titik bernilai tinggi (perubahan status_kelulusan
        # sidang, status seminar, status_yudisium, status mahasiswa, aktif
        # dosen, dan operasi hapus yang sudah dijaga di Phase 1) yang
        # diperbarui utk mengisi kolom terstruktur ini.
        ("log_aktivitas", "modul", "TEXT"),
        ("log_aktivitas", "entitas", "TEXT"),
        ("log_aktivitas", "entitas_id", "INTEGER"),
        ("log_aktivitas", "nilai_lama", "TEXT"),
        ("log_aktivitas", "nilai_baru", "TEXT"),
        ("log_aktivitas", "alasan", "TEXT"),
        # Fase Fondasi — perluasan tabel dosen untuk modul SDM & Kinerja Dosen
        ("dosen", "nip", "TEXT"),
        # Audit Menyeluruh — PHASE 5: lifecycle dosen (lihat komentar
        # panjang di constants.py::STATUS_KEPEGAWAIAN_DOSEN_LIST). Default
        # 'Aktif' dulu utk baris lama, nilai sebenarnya dibetulkan oleh
        # _migrate_status_kepegawaian_dosen() di bawah (mengikuti `aktif`
        # apa adanya, bukan menimpa jadi 'Aktif' semua).
        ("dosen", "status_kepegawaian", "TEXT DEFAULT 'Aktif'"),
        # Audit Menyeluruh — PHASE 6: OBE & CQI (lihat komentar panjang di
        # constants.py::JENIS_ASESMEN_LIST). Default 'Nilai Akhir' berlaku
        # utk SELURUH baris lama (ALTER TABLE ADD COLUMN) -- itu memang
        # makna semantik yang benar utk data lama (satu skor final per CPMK
        # tanpa rincian instrumen), bukan sekadar nilai default kosong.
        ("nilai_cpmk", "jenis_asesmen", "TEXT DEFAULT 'Nilai Akhir'"),
        # Fase Pejabat/SDM Lanjutan — identitas resmi ala SISTER (lihat
        # komentar di CREATE TABLE dosen di atas): NIK & NUPTK menggantikan
        # NIP di form/import/ekspor, tanpa menghapus kolom nip yang lama.
        ("dosen", "nik", "TEXT"),
        ("dosen", "nuptk", "TEXT"),
        ("dosen", "jabatan_fungsional", "TEXT"),
        ("dosen", "pendidikan_terakhir", "TEXT"),
        ("dosen", "bidang_keahlian", "TEXT"),
        # Fase Fondasi (Audit poin 3) — homebase vs dosen luar
        ("dosen", "status_homebase", "TEXT DEFAULT 'Homebase'"),
        ("dosen", "unit_asal", "TEXT"),
        ("dosen", "prodi_homebase", "TEXT"),
        ("dosen", "sk_penugasan", "TEXT"),
        # Fase Fondasi (Audit poin 1) — kolom cache FK ke periode_akademik,
        # ditambahkan di tabel-tabel yang tadinya hanya punya semester/
        # tahun_akademik TEXT bebas. Kolom TEXT lama TETAP dipertahankan
        # sebagai cache tampilan; kolom baru ini jadi sumber kebenaran baru
        # begitu form diarahkan ke dropdown terkunci (lihat routes/akademik.py,
        # routes/jadwal.py, routes/semester_pendek.py).
        ("pengajuan_judul", "periode_akademik_id", "INTEGER"),
        ("penetapan_pembimbing", "periode_akademik_id", "INTEGER"),
        ("jadwal_kelas", "periode_akademik_id", "INTEGER"),
        ("sp_periode", "periode_akademik_id", "INTEGER"),
        # ...perluasan ke tabel SDM/Kinerja & modul mutu yang juga masih
        # memakai tahun_akademik/semester TEXT bebas (lihat komentar di
        # atas skema tabel masing-masing untuk daftar lengkap kolom lama).
        ("aktivitas_pendidikan", "periode_akademik_id", "INTEGER"),
        ("aktivitas_penelitian", "periode_akademik_id", "INTEGER"),
        ("aktivitas_pkm", "periode_akademik_id", "INTEGER"),
        ("aktivitas_penunjang", "periode_akademik_id", "INTEGER"),
        ("luaran_dosen", "periode_akademik_id", "INTEGER"),
        ("peran_akademik_dosen", "periode_akademik_id", "INTEGER"),
        ("program_kerja", "periode_akademik_id", "INTEGER"),
        ("cqi_siklus", "periode_akademik_id", "INTEGER"),
        ("ami_siklus", "periode_akademik_id", "INTEGER"),
        # Fase Fondasi (Audit poin 2, klarifikasi a) — gelombang pendaftaran
        # dinamis per mahasiswa, menggantikan pola tahap TEXT bebas.
        ("pengajuan_judul", "tahap_pengajuan_id", "INTEGER"),
        ("penetapan_pembimbing", "tahap_pengajuan_id", "INTEGER"),
        # Audit Modul Pelaksanaan (Seminar/Sidang) — sebelum ini `seminar` &
        # `sidang` TIDAK punya kolom semester/tahap SAMA SEKALI, sehingga
        # halaman /pelaksanaan/seminar & /pelaksanaan/sidang menumpuk semua
        # mahasiswa lintas periode dalam satu tabel tanpa filter, dan RKP
        # Seminar/Sidang (honor) terpaksa "meminjam" tahap dari
        # penetapan_pembimbing.tahap (tahap SK Pembimbing/pengajuan judul,
        # ditetapkan SEKALI di awal) — padahal satu mahasiswa bisa seminar/
        # sidang di tahap yang BERBEDA dari tahap SK-nya (seminar/sidang
        # biasanya berjalan 3x per semester, sedangkan pengajuan judul cuma
        # 1x di awal semester ganjil/7). Akibatnya rekap honor per tahap bisa
        # salah kelompok. Kolom di bawah membuat seminar & sidang punya
        # tahap MILIK SENDIRI, diisi saat baris itu dibuat/diedit.
        ("seminar", "periode_akademik_id", "INTEGER"),
        ("seminar", "tahap_pengajuan_id", "INTEGER"),
        ("seminar", "tahap", "TEXT"),
        ("sidang", "periode_akademik_id", "INTEGER"),
        ("sidang", "tahap_pengajuan_id", "INTEGER"),
        ("sidang", "tahap", "TEXT"),
        # Snapshot tarif honor SAAT honor itu terbentuk (seminar diset
        # 'Selesai', sidang disimpan / diset LULUS) — supaya kalau tarif di
        # Pengaturan diubah belakangan, honor yang SUDAH direkap & dilaporkan
        # ke bagian keuangan untuk tahap-tahap lama tidak ikut berubah
        # retroaktif. NULL berarti baris lama (sebelum fitur ini ada) —
        # rkp_seminar()/rkp_sidang() jatuh balik ke tarif aktif saat itu.
        ("seminar", "tarif_honor_diterapkan", "REAL"),
        ("sidang", "tarif_penguji_diterapkan", "REAL"),
        ("sidang", "tarif_pemb1_diterapkan", "REAL"),
        ("sidang", "tarif_pemb2_diterapkan", "REAL"),
    ]
    for table, col, coltype in additions:
        if not _column_exists(conn, table, col):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
    _rebuild_seminar_tanpa_unique(conn)
    _rebuild_jadwal_kelas_fk_restrict(conn)
    _rebuild_cqi_siklus_fk_restrict(conn)
    # Audit Menyeluruh — P0 #4-#7 (lihat komentar panjang di atas definisi
    # masing-masing fungsi). Urutan mengikuti rantai TA: pengajuan ->
    # penetapan pembimbing -> seminar -> sidang -> yudisium (yudisium
    # butuh tabel sidang sudah final sebelum FK sidang_id-nya dipasang).
    _rebuild_pengajuan_judul_fk(conn)
    _rebuild_penetapan_pembimbing_fk(conn)
    _rebuild_seminar_fk_dosen_periode(conn)
    _rebuild_sidang_fk_dosen_periode(conn)
    _rebuild_yudisium_fk_sidang(conn)
    # Audit Menyeluruh — PHASE 2: Data Integrity (CHECK constraint + unique
    # index). Dijalankan SETELAH seluruh migrasi FK Phase 1 di atas supaya
    # kolom yang dirujuk CHECK (mis. mahasiswa.status_ta) sudah pasti final.
    _rebuild_mahasiswa_check_status(conn)
    _rebuild_seminar_check_status(conn)
    _rebuild_sidang_check_status(conn)
    _rebuild_yudisium_check_status(conn)
    _rebuild_periode_akademik_check(conn)
    _buat_index_unik_opsional(conn)
    # Audit Menyeluruh — PHASE 5: Data Lifecycle & Versioning Kurikulum.
    _migrate_status_kepegawaian_dosen(conn)
    _rebuild_dosen_check_status_kepegawaian(conn)
    _rebuild_kurikulum_versi_check(conn)
    # Audit Menyeluruh — PHASE 6: OBE & CQI.
    _rebuild_nilai_cpmk_unique_asesmen(conn)
    _rebuild_cqi_siklus_check_status(conn)
    # Isi skema default untuk baris lama yang masih NULL
    conn.execute("UPDATE mahasiswa SET skema='Reguler' WHERE skema IS NULL OR skema=''")
    conn.execute(
        "UPDATE dosen SET status_homebase='Homebase' "
        "WHERE status_homebase IS NULL OR status_homebase=''"
    )
    # Instalasi lama menyimpan peran sebagai "Administrator" — disamakan ke
    # istilah "Kaprodi" yang dipakai di seluruh aplikasi versi gabungan ini,
    # tanpa mengubah baris pengguna lain yang mungkin sudah diberi peran lain.
    conn.execute("UPDATE pengguna SET peran=? WHERE peran='Administrator'", (PERAN_KAPRODI,))
    conn.commit()
    _migrate_tahun_ajaran_lama(conn)


def _rebuild_seminar_tanpa_unique(conn):
    """Antisipasi 'seminar ulang' — tabel `seminar` semula dibuat dengan
    `mahasiswa_id INTEGER UNIQUE NOT NULL`, artinya satu mahasiswa hanya
    boleh punya SATU baris seminar selamanya. Dalam praktik seminar ulang
    memang jarang terjadi (beda dari sidang ulang yang lebih umum) — tapi
    tetap mungkin (mis. seminar pertama gagal/proposal ditolak dan
    mahasiswa harus seminar ulang di tahap berikutnya). Supaya kasus itu
    tidak diblokir sistem (lihat juga `sidang` yang dari awal memang sudah
    mendukung banyak baris per mahasiswa), batasan UNIQUE diangkat di sini.

    SQLite tidak mendukung `ALTER TABLE ... DROP CONSTRAINT`, jadi tabel
    dibangun ulang (rebuild): idempoten — hanya berjalan kalau constraint
    UNIQUE itu masih terdeteksi di skema saat ini; kalau sudah tidak ada
    (instalasi baru, atau instalasi lama yang sudah pernah melalui migrasi
    ini), fungsi langsung keluar tanpa melakukan apa pun. Struktur kolom
    (termasuk seluruh kolom baru dari migrasi tahap/honor di atas) dan
    seluruh data existing dipertahankan utuh — hanya constraint UNIQUE yang
    dihapus."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='seminar'"
    ).fetchone()
    if not row or not row["sql"] or "UNIQUE" not in row["sql"]:
        return

    cols = conn.execute("PRAGMA table_info(seminar)").fetchall()
    defs = []
    names = []
    for c in cols:
        name = c["name"]
        names.append(name)
        if name == "id":
            defs.append("id INTEGER PRIMARY KEY AUTOINCREMENT")
            continue
        piece = f"{name} {c['type'] or 'TEXT'}"
        if name == "mahasiswa_id" or c["notnull"]:
            piece += " NOT NULL"
        if c["dflt_value"] is not None:
            piece += f" DEFAULT {c['dflt_value']}"
        defs.append(piece)
    defs.append("FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE")
    kolom_csv = ", ".join(names)

    conn.execute(f"CREATE TABLE seminar_new ({', '.join(defs)})")
    conn.execute(f"INSERT INTO seminar_new ({kolom_csv}) SELECT {kolom_csv} FROM seminar")
    conn.execute("DROP TABLE seminar")
    conn.execute("ALTER TABLE seminar_new RENAME TO seminar")
    conn.commit()


def _sql_default_literal(dflt_value):
    """`PRAGMA table_info` mengembalikan default berupa ekspresi fungsi
    (mis. `datetime('now','localtime')`) TANPA tanda kurung pembungkus,
    padahal sintaks `CREATE TABLE ... DEFAULT (...)` di SQLite mewajibkan
    ekspresi non-literal dibungkus kurung eksplisit (literal angka/string
    boleh tanpa kurung). Dipakai oleh fungsi rebuild tabel di bawah supaya
    kolom dengan default berupa fungsi (bukan cuma angka/string) tidak
    menyebabkan syntax error saat tabel dibangun ulang."""
    dv = dflt_value.strip()
    if dv.upper() in ("CURRENT_TIME", "CURRENT_DATE", "CURRENT_TIMESTAMP", "NULL", "TRUE", "FALSE"):
        return dv
    if dv.startswith("'") and dv.endswith("'"):
        return dv  # literal string
    try:
        float(dv)
        return dv  # literal angka
    except ValueError:
        pass
    return f"({dv})"  # ekspresi (mis. panggilan fungsi) -> wajib dibungkus


def _rebuild_jadwal_kelas_fk_restrict(conn):
    """Audit Kontinuitas — lapis pertahanan SKEMA, menyusul guard di level
    APLIKASI yang sudah ditambahkan di routes/kurikulum.py::hapus_mk().

    Skema asli `jadwal_kelas.mata_kuliah_id` memakai `ON DELETE CASCADE`:
    kalau baris `mata_kuliah` dihapus, SELURUH `jadwal_kelas` (dan
    turunannya, `bap` & `krs` — presensi dan NILAI mahasiswa) ikut terhapus
    otomatis oleh SQLite sendiri, lewat jalur MANAPUN yang memicunya —
    bukan cuma lewat tombol "Hapus" di halaman Struktur Kurikulum. Guard di
    `hapus_mk()` sudah menutup jalur itu di level aplikasi, tapi tetap
    tidak melindungi dari akses DB langsung atau route lain di masa depan
    yang lupa menyalin guard yang sama. Diganti jadi `ON DELETE RESTRICT`:
    SQLite sendiri yang menolak (melempar `IntegrityError`) penghapusan
    mata_kuliah selama masih ada jadwal_kelas yang menunjuk ke sana, apa
    pun jalur SQL yang memicunya — jaring pengaman terakhir di level data,
    bukan pengganti guard aplikasi (pesan errornya tetap dari `hapus_mk()`
    supaya ramah dibaca operator).

    PENTING (kenapa PRAGMA foreign_keys dimatikan sementara): `bap` dan
    `krs` sama-sama punya FK ke `jadwal_kelas(id) ON DELETE CASCADE`. Kalau
    tabel `jadwal_kelas` di-DROP saat `foreign_keys=ON`, SQLite menjalankan
    DELETE implisit dulu sebelum drop — itu akan MEMICU cascade yang sama
    persis yang ingin dihindari migrasi ini (menghapus seluruh bap/krs
    milik jadwal_kelas yang ada), padahal di sini tabelnya cuma mau
    dibangun ulang lalu diisi balik dengan data yang PERSIS sama. Karena
    itu foreign_keys dimatikan HANYA di seputar drop+rename ini, lalu
    dinyalakan kembali + diverifikasi dgn `PRAGMA foreign_key_check`
    sebelum commit.

    Idempoten (pola sama dengan `_rebuild_seminar_tanpa_unique`): hanya
    berjalan kalau skema saat ini masih memuat teks 'ON DELETE CASCADE'
    persis di baris FK `mata_kuliah_id`; kalau sudah RESTRICT (instalasi
    baru, atau instalasi lama yang sudah pernah lewat migrasi ini),
    langsung keluar tanpa melakukan apa pun. Seluruh kolom (termasuk kolom
    tambahan dari migrasi sebelumnya, mis. `periode_akademik_id`) dan
    seluruh data existing (jadwal, bap, krs, nilai_cpmk) dipertahankan
    utuh — hanya aksi ON DELETE utk 1 FK yang berubah."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='jadwal_kelas'"
    ).fetchone()
    if not row or not row["sql"]:
        return
    if "FOREIGN KEY(mata_kuliah_id) REFERENCES mata_kuliah(id) ON DELETE CASCADE" not in row["sql"]:
        return  # sudah RESTRICT, atau skema tidak dikenali -> jangan diutak-atik

    cols = conn.execute("PRAGMA table_info(jadwal_kelas)").fetchall()
    defs = []
    names = []
    for c in cols:
        name = c["name"]
        names.append(name)
        if name == "id":
            defs.append("id INTEGER PRIMARY KEY AUTOINCREMENT")
            continue
        piece = f"{name} {c['type'] or 'TEXT'}"
        if name == "mata_kuliah_id" or c["notnull"]:
            piece += " NOT NULL"
        if c["dflt_value"] is not None:
            piece += f" DEFAULT {_sql_default_literal(c['dflt_value'])}"
        defs.append(piece)
    defs.append("FOREIGN KEY(mata_kuliah_id) REFERENCES mata_kuliah(id) ON DELETE RESTRICT")
    defs.append("FOREIGN KEY(dosen_id) REFERENCES dosen(id) ON DELETE SET NULL")
    defs.append("FOREIGN KEY(ruangan_id) REFERENCES ruangan(id) ON DELETE SET NULL")
    kolom_csv = ", ".join(names)

    conn.commit()  # pastikan tidak ada transaksi menggantung sebelum ganti PRAGMA
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute(f"CREATE TABLE jadwal_kelas_new ({', '.join(defs)})")
        conn.execute(
            f"INSERT INTO jadwal_kelas_new ({kolom_csv}) SELECT {kolom_csv} FROM jadwal_kelas"
        )
        conn.execute("DROP TABLE jadwal_kelas")
        conn.execute("ALTER TABLE jadwal_kelas_new RENAME TO jadwal_kelas")
        bermasalah = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bermasalah:
            conn.rollback()
            raise RuntimeError(
                "Migrasi jadwal_kelas (RESTRICT) dibatalkan: ditemukan "
                f"{len(bermasalah)} referensi FK tidak konsisten setelah rebuild."
            )
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _rebuild_cqi_siklus_fk_restrict(conn):
    """Audit Kontinuitas — pasangan `_rebuild_jadwal_kelas_fk_restrict` di
    atas, untuk rantai `cpl -> cqi_siklus` (menyusul guard aplikasi di
    routes/kurikulum.py::hapus_cpl()). Tidak ada tabel lain yang mereferensi
    `cqi_siklus(id)` lewat FK, jadi tidak ada risiko cascade tersembunyi
    seperti pada jadwal_kelas — tetap dimatikan sementara sebagai
    kebiasaan aman yang sama. `cqi_siklus.kurikulum_id` (FK ke
    kurikulum_versi) SENGAJA tidak diubah — tidak ada guard/gap terkait
    penghapusan kurikulum_versi karena UI tidak pernah mengeksposnya."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='cqi_siklus'"
    ).fetchone()
    if not row or not row["sql"]:
        return
    if "FOREIGN KEY(cpl_id) REFERENCES cpl(id) ON DELETE CASCADE" not in row["sql"]:
        return

    cols = conn.execute("PRAGMA table_info(cqi_siklus)").fetchall()
    defs = []
    names = []
    for c in cols:
        name = c["name"]
        names.append(name)
        if name == "id":
            defs.append("id INTEGER PRIMARY KEY AUTOINCREMENT")
            continue
        piece = f"{name} {c['type'] or 'TEXT'}"
        if name in ("kurikulum_id", "cpl_id", "tahun_akademik") or c["notnull"]:
            piece += " NOT NULL"
        if c["dflt_value"] is not None:
            piece += f" DEFAULT {_sql_default_literal(c['dflt_value'])}"
        defs.append(piece)
    defs.append("FOREIGN KEY(kurikulum_id) REFERENCES kurikulum_versi(id) ON DELETE CASCADE")
    defs.append("FOREIGN KEY(cpl_id) REFERENCES cpl(id) ON DELETE RESTRICT")
    kolom_csv = ", ".join(names)

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute(f"CREATE TABLE cqi_siklus_new ({', '.join(defs)})")
        conn.execute(
            f"INSERT INTO cqi_siklus_new ({kolom_csv}) SELECT {kolom_csv} FROM cqi_siklus"
        )
        conn.execute("DROP TABLE cqi_siklus")
        conn.execute("ALTER TABLE cqi_siklus_new RENAME TO cqi_siklus")
        bermasalah = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bermasalah:
            conn.rollback()
            raise RuntimeError(
                "Migrasi cqi_siklus (RESTRICT) dibatalkan: ditemukan "
                f"{len(bermasalah)} referensi FK tidak konsisten setelah rebuild."
            )
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


# =============================================================================
# Audit Menyeluruh — P0 #4-#7: Referential Integrity di Rantai TA
# =============================================================================
# SEBELUM perbaikan di bawah ini, kolom-kolom penunjuk berikut disimpan
# sebagai INTEGER polos TANPA FOREIGN KEY sama sekali (lihat Audit §5):
#   - pengajuan_judul / penetapan_pembimbing / seminar / sidang . periode_akademik_id
#     dan .tahap_pengajuan_id  -> tidak menunjuk balik ke periode_akademik /
#     tahap_pengajuan yang benar-benar ada.
#   - seminar.penguji_ketua_id/penguji_anggota1_id/penguji_anggota2_id,
#     sidang.ketua_id/sekretaris_id/anggota1_id/anggota2_id/anggota3_id,
#     penetapan_pembimbing.pembimbing1_id/2_id/pembahas1-3_id/ketua_sidang_id/
#     penguji1-4_id -> tidak menunjuk balik ke dosen yang benar-benar ada.
#   - yudisium.sidang_id -> tidak menunjuk balik ke sidang yang benar-benar ada.
# Akibatnya SQLite tidak pernah menolak ID yatim/salah ketik di kolom-kolom
# itu, dan (sebelum guard hapus mahasiswa/dosen/tahap di atas ditambahkan)
# operasi hapus di tabel induk bisa meninggalkan referensi yatim tanpa
# peringatan apa pun.
#
# SQLite tidak mendukung `ALTER TABLE ... ADD CONSTRAINT`, jadi satu-satunya
# cara melampirkan FK ke kolom yang SUDAH ADA adalah membangun ulang
# tabelnya (pola yang SAMA PERSIS dengan _rebuild_jadwal_kelas_fk_restrict &
# _rebuild_cqi_siklus_fk_restrict di atas). ON DELETE RESTRICT dipilih utk
# semua FK baru ini (bukan CASCADE/SET NULL) karena kolom-kolom ini menunjuk
# ke histori akademik yang tidak boleh hilang diam-diam: SQLite akan
# MENOLAK (IntegrityError) penghapusan periode/tahap/dosen/sidang selama
# masih dirujuk baris manapun di sini — jaring pengaman DB yang melengkapi
# guard di level aplikasi (routes/mahasiswa.py::hapus, routes/dosen.py::hapus,
# routes/pengaturan.py hapus tahap) untuk jalur akses DB langsung/route lain
# di masa depan yang lupa menyalin guard yang sama.


def _rebuild_table_add_fk(conn, table, fk_clauses, unique_cols=()):
    """Helper generik dipakai oleh fungsi _rebuild_*_fk (Audit P0 #4-#7) DAN
    _rebuild_*_check (Audit Phase 2 — Data Integrity, CHECK constraint):
    nama fungsinya menyebut "fk" karena pertama dibuat untuk itu, tapi
    isinya generik terhadap JENIS klausa tabel apa pun yang ditambahkan
    lewat `fk_clauses` (FOREIGN KEY(...) maupun CHECK(...) sama-sama valid
    sebagai elemen list itu) — keduanya sama-sama "table constraint" yang
    di SQLite hanya bisa dilampirkan ke kolom yang SUDAH ADA lewat
    membangun ulang tabel, bukan `ALTER TABLE ... ADD CONSTRAINT`.

    PENTING (kenapa PRAGMA foreign_keys dimatikan sementara): sama seperti
    _rebuild_jadwal_kelas_fk_restrict — beberapa tabel target di sini juga
    jadi RUJUKAN FK ON DELETE CASCADE dari tabel lain (mis. yudisium
    dirujuk lewat sidang_id yang BARU ditambahkan; seminar/sidang dirujuk
    balik oleh tidak ada tabel turunan saat ini, tapi kebiasaan aman yang
    sama tetap dipakai)."""
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    defs, names = [], []
    for c in cols:
        name = c["name"]
        names.append(name)
        if name == "id":
            defs.append("id INTEGER PRIMARY KEY AUTOINCREMENT")
            continue
        piece = f"{name} {c['type'] or 'TEXT'}"
        if name in unique_cols:
            piece += " UNIQUE"
        if c["notnull"]:
            piece += " NOT NULL"
        if c["dflt_value"] is not None:
            piece += f" DEFAULT {_sql_default_literal(c['dflt_value'])}"
        defs.append(piece)
    # Jaring pengaman tambahan: kalau `table` ternyata skema legacy/non-
    # standar yang BELUM punya salah satu kolom yang dirujuk fk_clauses
    # (mis. instalasi sangat lama, atau skema uji minimal), FK utk kolom
    # itu dilewati saja alih-alih membuat CREATE TABLE gagal dengan
    # "unknown column in foreign key definition". Kolom yang memang belum
    # ada tidak mungkin salah rujuk (belum ada datanya sama sekali), jadi
    # aman dilewati -- migrasi ini akan otomatis melengkapinya di
    # kesempatan berikutnya begitu kolomnya ada (mis. lewat ALTER TABLE
    # ADD COLUMN di `additions` sebelum fungsi ini dipanggil).
    fk_terpakai = []
    for clause in fk_clauses:
        m = re.search(r"FOREIGN KEY\((\w+)\)", clause) or re.search(r"CHECK\((\w+)\b", clause)
        if m and m.group(1) not in names:
            continue
        fk_terpakai.append(clause)
    defs.extend(fk_terpakai)
    kolom_csv = ", ".join(names)

    conn.commit()  # tidak ada transaksi menggantung sebelum ganti PRAGMA
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute(f"CREATE TABLE {table}_new ({', '.join(defs)})")
        conn.execute(f"INSERT INTO {table}_new ({kolom_csv}) SELECT {kolom_csv} FROM {table}")
        conn.execute(f"DROP TABLE {table}")
        conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
        bermasalah = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bermasalah:
            conn.rollback()
            raise RuntimeError(
                f"Migrasi {table} (tambah FK) dibatalkan: ditemukan {len(bermasalah)} "
                "referensi tidak konsisten (ID yatim) setelah rebuild. Data lama TIDAK "
                "diubah — hubungi pengembang untuk membersihkan data yatim tsb terlebih dulu."
            )
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _rebuild_pengajuan_judul_fk(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='pengajuan_judul'"
    ).fetchone()
    if not row or not row["sql"]:
        return
    if "REFERENCES periode_akademik(id)" in row["sql"]:
        return  # sudah pernah dimigrasi / instalasi baru
    _rebuild_table_add_fk(
        conn,
        "pengajuan_judul",
        [
            "FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE",
            "FOREIGN KEY(periode_akademik_id) REFERENCES periode_akademik(id) ON DELETE RESTRICT",
            "FOREIGN KEY(tahap_pengajuan_id) REFERENCES tahap_pengajuan(id) ON DELETE RESTRICT",
        ],
    )


def _rebuild_penetapan_pembimbing_fk(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='penetapan_pembimbing'"
    ).fetchone()
    if not row or not row["sql"]:
        return
    if "REFERENCES periode_akademik(id)" in row["sql"]:
        return
    _rebuild_table_add_fk(
        conn,
        "penetapan_pembimbing",
        [
            "FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE",
            "FOREIGN KEY(periode_akademik_id) REFERENCES periode_akademik(id) ON DELETE RESTRICT",
            "FOREIGN KEY(tahap_pengajuan_id) REFERENCES tahap_pengajuan(id) ON DELETE RESTRICT",
            "FOREIGN KEY(pembimbing1_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(pembimbing2_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(pembahas1_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(pembahas2_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(pembahas3_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(ketua_sidang_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(penguji1_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(penguji2_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(penguji3_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(penguji4_id) REFERENCES dosen(id) ON DELETE RESTRICT",
        ],
        unique_cols=("mahasiswa_id",),
    )


def _rebuild_seminar_fk_dosen_periode(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='seminar'"
    ).fetchone()
    if not row or not row["sql"]:
        return
    if "REFERENCES periode_akademik(id)" in row["sql"]:
        return
    _rebuild_table_add_fk(
        conn,
        "seminar",
        [
            "FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE",
            "FOREIGN KEY(periode_akademik_id) REFERENCES periode_akademik(id) ON DELETE RESTRICT",
            "FOREIGN KEY(tahap_pengajuan_id) REFERENCES tahap_pengajuan(id) ON DELETE RESTRICT",
            "FOREIGN KEY(penguji_ketua_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(penguji_anggota1_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(penguji_anggota2_id) REFERENCES dosen(id) ON DELETE RESTRICT",
        ],
    )


def _rebuild_sidang_fk_dosen_periode(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='sidang'"
    ).fetchone()
    if not row or not row["sql"]:
        return
    if "REFERENCES periode_akademik(id)" in row["sql"]:
        return
    _rebuild_table_add_fk(
        conn,
        "sidang",
        [
            "FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE",
            "FOREIGN KEY(periode_akademik_id) REFERENCES periode_akademik(id) ON DELETE RESTRICT",
            "FOREIGN KEY(tahap_pengajuan_id) REFERENCES tahap_pengajuan(id) ON DELETE RESTRICT",
            "FOREIGN KEY(ketua_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(sekretaris_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(anggota1_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(anggota2_id) REFERENCES dosen(id) ON DELETE RESTRICT",
            "FOREIGN KEY(anggota3_id) REFERENCES dosen(id) ON DELETE RESTRICT",
        ],
    )


def _rebuild_yudisium_fk_sidang(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='yudisium'"
    ).fetchone()
    if not row or not row["sql"]:
        return
    if "REFERENCES sidang(id)" in row["sql"]:
        return
    _rebuild_table_add_fk(
        conn,
        "yudisium",
        [
            "FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE",
            "FOREIGN KEY(sidang_id) REFERENCES sidang(id) ON DELETE RESTRICT",
        ],
        unique_cols=("mahasiswa_id",),
    )


# =============================================================================
# Audit Menyeluruh — PHASE 2: Data Integrity (CHECK constraint + unique index)
# =============================================================================
# Melengkapi Phase 1 (FK) dengan lapis integritas berikutnya: kolom "status"
# di seluruh rantai TA sebelumnya adalah TEXT bebas — SQLite menerima nilai
# APA PUN, termasuk typo atau ejaan yang tidak dikenali aplikasi. Guard di
# level route sudah dipasang di Phase 1 (Audit P0 #10) untuk 2 titik entri
# (form manual + impor Excel), tapi itu hanya menutup pintu masuk yang
# SUDAH DIKETAHUI — akses DB langsung atau bug di route lain di masa depan
# tetap bisa menuliskan status tak dikenali. CHECK constraint di bawah ini
# menutupnya di lapis paling dasar (skema DB), konsisten dengan filosofi
# "defense in depth" yang sudah dipakai utk FK di Phase 1.


def _sql_in_list(values):
    """'a','b','c' -> "('a','b','c')" siap ditempel setelah `IN`. Semua
    whitelist status di constants.py adalah literal Python tetap (bukan
    input pengguna), jadi cukup escape tanda kutip tunggal standar SQL."""
    return "(" + ", ".join("'" + v.replace("'", "''") + "'" for v in values) + ")"


def _normalisasi_kolom_ke_whitelist(conn, table, column, whitelist, default_value):
    """Dipanggil SEBELUM menambahkan CHECK(column IN (...)) lewat rebuild
    tabel (_rebuild_table_add_fk) — kalau tidak, baris lama yang nilainya
    di luar whitelist (typo, beda kapitalisasi, sisa data uji/impor lama)
    akan membuat langkah `INSERT INTO ..._new SELECT ...` gagal total dan
    migrasi dibatalkan, mengunci operator dari database-nya sendiri saat
    upgrade. Pencocokan longgar (case-insensitive + trim spasi): nilai yang
    maknanya sama tapi ejaannya beda dibetulkan ke ejaan resmi; nilai yang
    benar-benar tidak dikenali diganti ke `default_value` (boleh None utk
    kolom yang nullable, mis. sidang.status_kelulusan) supaya tidak ada
    baris yang diam-diam ditebak salah statusnya.

    Defensif terhadap skema legacy/uji minimal yang kolomnya belum ada
    sama sekali (lihat catatan serupa di _rebuild_table_add_fk): kalau
    `column` tidak ditemukan di `table`, langsung keluar tanpa melakukan
    apa pun -- pemanggil (_rebuild_table_add_fk) sudah punya jaring
    pengaman sendiri utk melewati klausa CHECK yang kolomnya tidak ada."""
    kolom_ada = any(
        c["name"] == column for c in conn.execute(f"PRAGMA table_info({table})").fetchall()
    )
    if not kolom_ada:
        return 0
    lower_map = {w.lower(): w for w in whitelist}
    rows = conn.execute(
        f"SELECT DISTINCT {column} v FROM {table} WHERE {column} IS NOT NULL"
    ).fetchall()
    berubah = 0
    for r in rows:
        v = r["v"]
        if v in whitelist:
            continue
        benar = lower_map.get(str(v).strip().lower(), default_value)
        conn.execute(f"UPDATE {table} SET {column}=? WHERE {column}=?", (benar, v))
        berubah += 1
    if berubah:
        conn.commit()
    return berubah


def _ambil_fk_existing(conn, table):
    """Ambil klausa FOREIGN KEY(...) yang SUDAH ADA di skema `table` saat
    ini (dibaca dari sqlite_master.sql). WAJIB dipakai setiap kali sebuah
    tabel di-rebuild LEBIH DARI SEKALI oleh fungsi berbeda (mis. Phase 1
    menambahkan FK ke `seminar`, lalu Phase 2 menambahkan CHECK ke tabel
    yang sama) -- _rebuild_table_add_fk() TIDAK membaca constraint lama
    secara otomatis; ia hanya memakai PERSIS `fk_clauses` yang diberikan
    pemanggil saat itu. Tanpa memanggil fungsi ini dulu, rebuild kedua akan
    diam-diam MENGHILANGKAN FK yang sudah dipasang rebuild pertama, karena
    tabel baru dibangun ulang dari nol dengan constraint list yang lebih
    pendek. Asumsi format: setiap FK ditulis 1 klausa/baris utuh persis
    seperti ditulis fungsi-fungsi _rebuild_*_fk di atas (konsisten di
    seluruh db.py -- tidak ada FK multi-baris)."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not row or not row["sql"]:
        return []
    return re.findall(
        r"FOREIGN KEY\(\w+\) REFERENCES \w+\(\w+\)"
        r"(?: ON DELETE (?:CASCADE|RESTRICT|SET NULL|SET DEFAULT|NO ACTION))?",
        row["sql"],
    )


def _rebuild_mahasiswa_check_status(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='mahasiswa'"
    ).fetchone()
    if not row or not row["sql"] or "CHECK(status_ta IN" in row["sql"]:
        return
    _normalisasi_kolom_ke_whitelist(conn, "mahasiswa", "status", C.STATUS_MHS_LIST, "Aktif")
    _normalisasi_kolom_ke_whitelist(conn, "mahasiswa", "status_ta", C.STATUS_TA_LIST, C.STATUS_TA_BELUM)
    _rebuild_table_add_fk(
        conn,
        "mahasiswa",
        [
            f"CHECK(status IN {_sql_in_list(C.STATUS_MHS_LIST)})",
            f"CHECK(status_ta IN {_sql_in_list(C.STATUS_TA_LIST)})",
        ],
    )


def _rebuild_seminar_check_status(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='seminar'"
    ).fetchone()
    if not row or not row["sql"] or "CHECK(status IN" in row["sql"]:
        return
    _normalisasi_kolom_ke_whitelist(conn, "seminar", "status", C.STATUS_SEMINAR_LIST, "Terdaftar")
    _rebuild_table_add_fk(
        conn,
        "seminar",
        _ambil_fk_existing(conn, "seminar")
        + [f"CHECK(status IN {_sql_in_list(C.STATUS_SEMINAR_LIST)})"],
    )


def _rebuild_sidang_check_status(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='sidang'"
    ).fetchone()
    if not row or not row["sql"] or "CHECK(status_kelulusan IS NULL" in row["sql"]:
        return
    # default_value=None -> nilai yang tidak dikenali dikosongkan (bukan
    # ditebak LULUS/TIDAK LULUS/TUNDA), sama seperti perbaikan impor Excel
    # di Phase 1: status kelulusan yang salah tafsir jauh lebih berbahaya
    # daripada dibiarkan kosong menunggu dilengkapi manual.
    _normalisasi_kolom_ke_whitelist(conn, "sidang", "status_kelulusan", C.STATUS_KELULUSAN_SIDANG, None)
    _rebuild_table_add_fk(
        conn,
        "sidang",
        _ambil_fk_existing(conn, "sidang")
        + [f"CHECK(status_kelulusan IS NULL OR status_kelulusan IN {_sql_in_list(C.STATUS_KELULUSAN_SIDANG)})"],
    )


def _rebuild_yudisium_check_status(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='yudisium'"
    ).fetchone()
    if not row or not row["sql"] or "CHECK(status_yudisium IN" in row["sql"]:
        return
    _normalisasi_kolom_ke_whitelist(conn, "yudisium", "status_yudisium", C.STATUS_YUDISIUM_LIST, "Direncanakan")
    _rebuild_table_add_fk(
        conn,
        "yudisium",
        _ambil_fk_existing(conn, "yudisium")
        + [f"CHECK(status_yudisium IN {_sql_in_list(C.STATUS_YUDISIUM_LIST)})"],
        unique_cols=("mahasiswa_id",),
    )


def _rebuild_periode_akademik_check(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='periode_akademik'"
    ).fetchone()
    if not row or not row["sql"] or "CHECK(jenis IN" in row["sql"]:
        return
    _normalisasi_kolom_ke_whitelist(conn, "periode_akademik", "jenis", C.JENIS_PERIODE_LIST, "Ganjil")
    _normalisasi_kolom_ke_whitelist(conn, "periode_akademik", "status", C.STATUS_PERIODE_LIST, "Draft")
    # UNIQUE(tahun_ajaran_id, jenis) dan FOREIGN KEY(tahun_ajaran_id) sudah
    # ada sejak CREATE TABLE awal (lihat skema di atas) -- _ambil_fk_existing
    # mempertahankan FK-nya; UNIQUE komposit tidak terbaca PRAGMA table_info
    # (hanya utk 1 kolom) jadi dituliskan eksplisit lagi di sini supaya
    # tidak hilang saat rebuild.
    _rebuild_table_add_fk(
        conn,
        "periode_akademik",
        _ambil_fk_existing(conn, "periode_akademik")
        + [
            f"CHECK(jenis IN {_sql_in_list(C.JENIS_PERIODE_LIST)})",
            f"CHECK(status IN {_sql_in_list(C.STATUS_PERIODE_LIST)})",
            "UNIQUE(tahun_ajaran_id, jenis)",
        ],
    )


def _buat_index_unik_opsional(conn):
    """Audit Phase 2 — Data Integrity: unique index utk identitas yang
    seharusnya tidak boleh kembar (NIDN/NIK/NUPTK dosen, kode pengajuan,
    nomor surat) dan utk mencegah duplikasi urutan tahap dalam 1 periode.

    SEMUA pakai `CREATE UNIQUE INDEX IF NOT EXISTS` (tidak perlu rebuild
    tabel -- SQLite mendukung index baru di tabel lama tanpa migrasi
    skema) dan SEMUA memakai index PARSIAL (`WHERE col IS NOT NULL AND
    col != ''`) utk field identitas: field-field ini historis banyak
    kosong (belum sempat dilengkapi operator), dan SQLite memperlakukan
    string kosong ('') sebagai nilai yang SAMA utk keperluan UNIQUE (beda
    dari NULL yang boleh berulang) -- tanpa index parsial, 2 baris
    ber-NIDN kosong saja sudah dianggap bentrok.

    Dibungkus try/except per index (bukan lewat _rebuild_table_add_fk yang
    membatalkan seluruh migrasi): kalau instalasi tertentu SUDAH terlanjur
    py punya duplikat nyata (bukan cuma sama-sama kosong) di data lamanya,
    index itu SAJA yang dilewati (dicatat lewat print ke stdout/log
    server, bukan dibiarkan diam-diam) -- tidak mengunci operator dari
    seluruh aplikasinya hanya karena satu field identitas yang datanya
    kotor; itu tanggung jawab pembersihan data terpisah, bukan alasan
    memblokir startup."""
    definisi = [
        ("idx_dosen_nidn_unik", "dosen", "nidn"),
        ("idx_dosen_nik_unik", "dosen", "nik"),
        ("idx_dosen_nuptk_unik", "dosen", "nuptk"),
        ("idx_pengajuan_kode_unik", "pengajuan_judul", "kode_pengajuan"),
        ("idx_surat_nomor_unik", "surat_keluar", "nomor_surat"),
    ]
    for nama_idx, tabel, kolom in definisi:
        ada = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (nama_idx,)
        ).fetchone()
        if ada:
            continue
        kolom_ada = any(
            c["name"] == kolom for c in conn.execute(f"PRAGMA table_info({tabel})").fetchall()
        )
        if not kolom_ada:
            continue
        try:
            conn.execute(
                f"CREATE UNIQUE INDEX {nama_idx} ON {tabel}({kolom}) "
                f"WHERE {kolom} IS NOT NULL AND {kolom} != ''"
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            print(
                f"[SIMPRODI] PERINGATAN: melewati unique index {nama_idx} ({tabel}.{kolom}) -- "
                f"database ini punya nilai {kolom} yang kembar di data lama. Aplikasi tetap "
                f"berjalan normal; bersihkan duplikatnya lalu restart utk mengaktifkan proteksi ini."
            )

    # tahap_pengajuan: urutan tidak boleh kembar dalam 1 periode akademik
    # yang sama (mis. dua "Tahap 1" sekaligus di periode yang sama).
    ada = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_tahap_urutan_unik'"
    ).fetchone()
    if not ada:
        try:
            conn.execute(
                "CREATE UNIQUE INDEX idx_tahap_urutan_unik ON tahap_pengajuan(periode_akademik_id, urutan)"
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            print(
                "[SIMPRODI] PERINGATAN: melewati unique index idx_tahap_urutan_unik -- "
                "ditemukan urutan tahap yang kembar dalam 1 periode akademik di data lama."
            )


# =============================================================================
# Audit Menyeluruh — PHASE 5: Data Lifecycle & Versioning Kurikulum
# =============================================================================


def _migrate_status_kepegawaian_dosen(conn):
    """Isi status_kepegawaian dari nilai `aktif` (boolean) yang SUDAH ADA,
    utk baris lama yang baru dapat kolom ini lewat ALTER TABLE ADD COLUMN
    (nilai defaultnya seragam 'Aktif' dari DEFAULT di atas -- salah utk
    dosen yang sebelumnya sudah `aktif=0`, harus dikoreksi ke 'Nonaktif').
    Idempoten: hanya menyentuh baris yang statusnya masih persis default
    'Aktif' tapi `aktif`-nya 0 (kombinasi yang cuma mungkin muncul sesaat
    setelah ALTER TABLE, sebelum migrasi ini pernah jalan).

    Defensif thd skema legacy/uji minimal yang bahkan belum punya kolom
    `aktif` sama sekali (lihat catatan serupa di _rebuild_table_add_fk)."""
    kolom_ada = any(c["name"] == "aktif" for c in conn.execute("PRAGMA table_info(dosen)").fetchall())
    if not kolom_ada:
        return
    conn.execute(
        "UPDATE dosen SET status_kepegawaian='Nonaktif' WHERE aktif=0 AND status_kepegawaian='Aktif'"
    )
    conn.commit()


def _rebuild_dosen_check_status_kepegawaian(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='dosen'"
    ).fetchone()
    if not row or not row["sql"] or "CHECK(status_kepegawaian IN" in row["sql"]:
        return
    _normalisasi_kolom_ke_whitelist(
        conn, "dosen", "status_kepegawaian", C.STATUS_KEPEGAWAIAN_DOSEN_LIST, "Aktif"
    )
    _rebuild_table_add_fk(
        conn,
        "dosen",
        _ambil_fk_existing(conn, "dosen")
        + [f"CHECK(status_kepegawaian IN {_sql_in_list(C.STATUS_KEPEGAWAIAN_DOSEN_LIST)})"],
    )


def _migrate_status_kurikulum_lama(conn):
    """'Non-aktif' (skema 3-status lama) -> 'Diarsipkan' (skema 5-status
    baru, Audit §24) -- makna praktisnya sama: versi yang sudah tidak
    berlaku. Dijalankan SEBELUM CHECK constraint dipasang, supaya baris
    lama tidak diam-diam kena fallback generik `_normalisasi_kolom_ke_
    whitelist` (yang tidak tahu pemetaan semantik 'Non-aktif'->'Diarsipkan',
    hanya cocok ejaan)."""
    conn.execute("UPDATE kurikulum_versi SET status='Diarsipkan' WHERE status='Non-aktif'")
    conn.commit()


# =============================================================================
# Audit Menyeluruh — PHASE 6: OBE & CQI
# =============================================================================


def _rebuild_nilai_cpmk_unique_asesmen(conn):
    """UNIQUE(krs_id, cpmk_id) (skema lama: 1 skor final per CPMK) ->
    UNIQUE(krs_id, cpmk_id, jenis_asesmen) (skema baru: boleh banyak baris
    per CPMK, satu per instrumen asesmen). Aman utk data lama: constraint
    lama sudah menjamin tidak ada duplikat (krs_id,cpmk_id), jadi constraint
    baru yang lebih longgar itu tidak mungkin dilanggar oleh data yang
    sudah ada."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='nilai_cpmk'"
    ).fetchone()
    if not row or not row["sql"] or "UNIQUE(krs_id, cpmk_id, jenis_asesmen)" in row["sql"]:
        return
    _rebuild_table_add_fk(
        conn,
        "nilai_cpmk",
        _ambil_fk_existing(conn, "nilai_cpmk") + ["UNIQUE(krs_id, cpmk_id, jenis_asesmen)"],
    )


def _rebuild_cqi_siklus_check_status(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='cqi_siklus'"
    ).fetchone()
    if not row or not row["sql"] or "CHECK(status IN" in row["sql"]:
        return
    _normalisasi_kolom_ke_whitelist(conn, "cqi_siklus", "status", C.STATUS_CQI_LIST, "Direncanakan")
    _rebuild_table_add_fk(
        conn,
        "cqi_siklus",
        _ambil_fk_existing(conn, "cqi_siklus")
        + [f"CHECK(status IN {_sql_in_list(C.STATUS_CQI_LIST)})"],
    )


def _rebuild_kurikulum_versi_check(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='kurikulum_versi'"
    ).fetchone()
    if not row or not row["sql"] or "CHECK(status IN" in row["sql"]:
        return
    _migrate_status_kurikulum_lama(conn)
    _normalisasi_kolom_ke_whitelist(conn, "kurikulum_versi", "status", C.STATUS_KURIKULUM_LIST, "Draft")
    _rebuild_table_add_fk(
        conn,
        "kurikulum_versi",
        [f"CHECK(status IN {_sql_in_list(C.STATUS_KURIKULUM_LIST)})"],
    )


def _migrate_tahun_ajaran_lama(conn):
    """Migrasi satu-kali: bila tabel tahun_ajaran masih kosong (instalasi
    lama yang baru upgrade, atau instalasi baru sebelum wizard "Buka Tahun
    Ajaran" dipakai), buat otomatis 1 tahun ajaran dari nilai lama
    `tahun_akademik_aktif` + `nama_tahap_1`/`nama_tahap_2` di pengaturan,
    supaya operator TIDAK kehilangan data/alur kerja begitu naik versi —
    'tahap 1/2' lama otomatis jadi 2 baris pertama di tahap_pengajuan yang
    baru, bebas ditambah tahap ke-3 dst dari UI setelahnya."""
    ada = conn.execute("SELECT COUNT(*) c FROM tahun_ajaran").fetchone()["c"]
    if ada:
        return
    kode = get_setting(conn, "tahun_akademik_aktif", "").strip()
    if not kode:
        return
    nama_tahap_1 = get_setting(conn, "nama_tahap_1", "").strip()
    nama_tahap_2 = get_setting(conn, "nama_tahap_2", "").strip()
    ta_id, periode_ids = buka_tahun_ajaran(conn, kode, aktifkan="Ganjil")
    ganjil_id = periode_ids.get("Ganjil")
    if ganjil_id:
        if nama_tahap_1:
            conn.execute(
                "INSERT INTO tahap_pengajuan(periode_akademik_id, urutan, nama) VALUES(?,1,?)",
                (ganjil_id, nama_tahap_1),
            )
        if nama_tahap_2:
            conn.execute(
                "INSERT INTO tahap_pengajuan(periode_akademik_id, urutan, nama) VALUES(?,2,?)",
                (ganjil_id, nama_tahap_2),
            )
    conn.commit()


def buka_tahun_ajaran(conn, kode, tgl_mulai=None, tgl_selesai=None, aktifkan="Ganjil"):
    """Wizard "Buka Tahun Ajaran Baru" (Audit poin 1, rekomendasi #5):
    membuat 1 baris tahun_ajaran + 3 baris periode_akademik (Ganjil, Genap,
    Antara) sekaligus, idempoten (aman dipanggil ulang dengan kode yang
    sama — tidak menggandakan baris). `aktifkan` menandai periode mana yang
    langsung berstatus 'Berjalan'; boleh None untuk semua 'Draft'.
    Mengembalikan (tahun_ajaran_id, {"Ganjil": id, "Genap": id, "Antara": id})."""
    kode = (kode or "").strip()
    if not kode:
        raise ValueError("Kode tahun ajaran wajib diisi (mis. 2025/2026).")
    row = conn.execute("SELECT id FROM tahun_ajaran WHERE kode=?", (kode,)).fetchone()
    if row:
        ta_id = row["id"]
    else:
        cur = conn.execute("INSERT INTO tahun_ajaran(kode, status) VALUES(?, 'Aktif')", (kode,))
        ta_id = cur.lastrowid
    periode_ids = {}
    for jenis in ("Ganjil", "Genap", "Antara"):
        prow = conn.execute(
            "SELECT id FROM periode_akademik WHERE tahun_ajaran_id=? AND jenis=?",
            (ta_id, jenis),
        ).fetchone()
        if prow:
            periode_ids[jenis] = prow["id"]
            continue
        status = "Berjalan" if jenis == aktifkan else "Draft"
        cur = conn.execute(
            "INSERT INTO periode_akademik(tahun_ajaran_id, jenis, tgl_mulai, tgl_selesai, status) "
            "VALUES(?,?,?,?,?)",
            (
                ta_id,
                jenis,
                tgl_mulai if jenis == aktifkan else None,
                tgl_selesai if jenis == aktifkan else None,
                status,
            ),
        )
        periode_ids[jenis] = cur.lastrowid
    if aktifkan:
        set_setting(conn, "tahun_akademik_aktif", kode)
    conn.commit()
    return ta_id, periode_ids


# Addendum poin 3 — tabel operasional yang punya kolom cache TEXT
# `tahun_akademik` (diturunkan dari kode tahun ajaran lewat cache_periode()
# saat baris dibuat/diedit — lihat routes/sdm.py, jadwal.py, kegiatan.py,
# cqi.py, mutu.py, semester_pendek.py). Kolom ini dipakai luas untuk
# filter/tampilan/rekap, tapi nilainya SNAPSHOT teks pada saat disimpan —
# beda dari `periode_akademik.id`/`tahun_ajaran.id` yang jadi sumber
# kebenaran relasi (tidak pernah berubah). Kalau `tahun_ajaran.kode`
# diedit lewat ubah_kode_tahun_ajaran() tanpa menyentuh tabel-tabel ini,
# cache-nya jadi basi (menampilkan kode lama walau baris masih terhubung
# lewat periode_akademik_id ke tahun ajaran yang sama).
TABEL_CACHE_TAHUN_AKADEMIK = [
    "aktivitas_pendidikan",
    "aktivitas_penelitian",
    "aktivitas_pkm",
    "aktivitas_penunjang",
    "luaran_dosen",
    "peran_akademik_dosen",
    "program_kerja",
    "jadwal_kelas",
    "cqi_siklus",
    "sp_periode",
    "ami_siklus",
]


def _sinkron_cache_tahun_akademik(conn, ta_id, kode_lama, kode_baru):
    """Perbarui kolom cache TEXT `tahun_akademik` di seluruh
    `TABEL_CACHE_TAHUN_AKADEMIK` supaya konsisten dengan `kode_baru`,
    dipanggil dari `ubah_kode_tahun_ajaran()` sebelum commit.

    Dua jalur, karena kolom `periode_akademik_id` di tabel-tabel ini
    nullable (ditambahkan belakangan lewat migrasi, lihat komentar di
    `_migrate()`):
    1. Baris dengan `periode_akademik_id` terisi -> dicocokkan lewat ID
       (join ke `periode_akademik.tahun_ajaran_id`), jalur yang paling
       diandalkan karena tidak bergantung sama sekali pada teks lama.
    2. Baris lama (dari sebelum dropdown periode terkunci ada, jadi
       `periode_akademik_id` masih NULL) -> fallback dicocokkan lewat
       teks `kode_lama` persis, karena `kode` tahun ajaran dijamin unik
       (divalidasi di `ubah_kode_tahun_ajaran()` sebelum sampai sini)
       sehingga tidak berisiko menimpa baris tahun ajaran lain.
    """
    periode_ids = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM periode_akademik WHERE tahun_ajaran_id=?", (ta_id,)
        ).fetchall()
    ]
    for table in TABEL_CACHE_TAHUN_AKADEMIK:
        if periode_ids:
            placeholder = ",".join("?" * len(periode_ids))
            conn.execute(
                f"UPDATE {table} SET tahun_akademik=? "
                f"WHERE periode_akademik_id IN ({placeholder})",
                (kode_baru, *periode_ids),
            )
        conn.execute(
            f"UPDATE {table} SET tahun_akademik=? "
            f"WHERE periode_akademik_id IS NULL AND tahun_akademik=?",
            (kode_baru, kode_lama),
        )


def ubah_kode_tahun_ajaran(conn, ta_id, kode_baru):
    """Restrukturisasi poin 3 — perbaikan salah ketik kode tahun ajaran
    (mis. "2025/2025" seharusnya "2025/2026") TANPA menyediakan fitur
    hapus tahun ajaran/periode sama sekali (sengaja tidak ada fungsi
    hapus_tahun_ajaran/hapus_periode di modul ini).

    Aman dilakukan kapan pun, termasuk setelah periode diaktifkan dan
    data mahasiswa/dosen mulai tersinkron, karena SETIAP tabel yang
    merujuk ke tahun ajaran (periode_akademik, dan seluruh tabel
    operasional lewat periode_akademik_id) menyimpan relasi memakai
    `tahun_ajaran_id`/`periode_akademik_id` (INTEGER, primary key yang
    tidak pernah berubah) — BUKAN `kode` (TEXT). Mengubah `kode` di sini
    tidak membuat baris jadi orphan dan tidak ada join yang putus.

    Beberapa tabel operasional JUGA menyimpan `kode` sebagai cache TEXT
    di kolom `tahun_akademik` (lihat `TABEL_CACHE_TAHUN_AKADEMIK`) untuk
    filter/tampilan/rekap lama — cache itu disinkronkan di sini lewat
    `_sinkron_cache_tahun_akademik()` supaya tidak basi (menampilkan kode
    lama) setelah kode diganti.

    Mengembalikan (True, "") kalau berhasil, atau (False, pesan_error)
    kalau ditolak (kode kosong / sudah dipakai tahun ajaran lain).
    """
    kode_baru = (kode_baru or "").strip()
    if not kode_baru:
        return False, "Kode tahun ajaran wajib diisi (mis. 2025/2026)."

    row = conn.execute("SELECT id, kode FROM tahun_ajaran WHERE id=?", (ta_id,)).fetchone()
    if not row:
        return False, "Tahun ajaran tidak ditemukan."

    bentrok = conn.execute(
        "SELECT id FROM tahun_ajaran WHERE kode=? AND id<>?", (kode_baru, ta_id)
    ).fetchone()
    if bentrok:
        return False, f'Kode "{kode_baru}" sudah dipakai tahun ajaran lain.'

    kode_lama = row["kode"]
    if kode_lama == kode_baru:
        return True, ""  # tidak ada perubahan, anggap berhasil (idempoten)

    conn.execute("UPDATE tahun_ajaran SET kode=? WHERE id=?", (kode_baru, ta_id))

    _sinkron_cache_tahun_akademik(conn, ta_id, kode_lama, kode_baru)

    # Sinkronkan cache tampilan lama (`pengaturan.tahun_akademik_aktif`)
    # kalau tahun ajaran yang diubah ini yang sedang tercatat sebagai
    # aktif di sana — supaya modul lama yang masih membaca cache ini
    # (belum sepenuhnya migrasi ke periode_akademik_id) tetap konsisten.
    if get_setting(conn, "tahun_akademik_aktif", "") == kode_lama:
        set_setting(conn, "tahun_akademik_aktif", kode_baru)

    conn.commit()
    return True, ""


def get_periode_aktif(conn):
    """Periode akademik yang sedang 'Berjalan' — dipakai sebagai default di
    form manapun yang butuh dropdown semester terkunci. Mengembalikan Row
    atau None kalau belum ada tahun ajaran yang dibuka lewat wizard."""
    return conn.execute(
        "SELECT pa.*, ta.kode AS kode_tahun_ajaran FROM periode_akademik pa "
        "JOIN tahun_ajaran ta ON ta.id=pa.tahun_ajaran_id "
        "WHERE pa.status='Berjalan' ORDER BY pa.id DESC LIMIT 1"
    ).fetchone()


def get_tahap_list(conn, periode_akademik_id=None):
    """Daftar tahap/gelombang pendaftaran untuk sebuah periode akademik,
    terurut sesuai `urutan` — jumlahnya dinamis (Audit poin 2, klarifikasi
    a), bukan 2 field hardcode lagi. Jatuh balik ke periode aktif bila
    periode_akademik_id tidak diberikan."""
    if periode_akademik_id is None:
        periode = get_periode_aktif(conn)
        periode_akademik_id = periode["id"] if periode else None
    if not periode_akademik_id:
        return []
    return conn.execute(
        "SELECT * FROM tahap_pengajuan WHERE periode_akademik_id=? ORDER BY urutan",
        (periode_akademik_id,),
    ).fetchall()


def get_periode_list(conn):
    """Semua periode akademik (lintas tahun ajaran), terbaru dulu — sumber
    SATU-SATUNYA dropdown 'Periode Akademik' terkunci yang dipakai di
    seluruh modul (Audit poin 1, tindak lanjut: dropdown UI sungguhan,
    bukan sekadar kolom cache). Label gabungan "2025/2026 - Ganjil" supaya
    operator memilih 1 dropdown, bukan mengetik tahun + pilih semester
    terpisah seperti sebelumnya."""
    rows = conn.execute(
        "SELECT pa.id, pa.jenis, pa.status, ta.kode AS kode_tahun_ajaran "
        "FROM periode_akademik pa JOIN tahun_ajaran ta ON ta.id = pa.tahun_ajaran_id "
        "ORDER BY ta.kode DESC, "
        "CASE pa.jenis WHEN 'Ganjil' THEN 1 WHEN 'Genap' THEN 2 ELSE 3 END"
    ).fetchall()
    out = []
    for r in rows:
        label = f"{r['kode_tahun_ajaran']} - {r['jenis']}"
        if r["status"] == "Berjalan":
            label += " (Berjalan)"
        out.append(
            {
                "id": r["id"],
                "jenis": r["jenis"],
                "status": r["status"],
                "kode_tahun_ajaran": r["kode_tahun_ajaran"],
                "label": label,
            }
        )
    return out


def get_periode_by_id(conn, periode_id):
    """Satu baris periode_akademik + kode tahun ajarannya. None bila
    periode_id kosong/tidak ditemukan (dropdown selalu boleh dikosongkan —
    data lama sebelum wizard Tahun Ajaran dipakai tetap harus bisa
    tersimpan tanpa periode terkunci)."""
    if not periode_id:
        return None
    return conn.execute(
        "SELECT pa.*, ta.kode AS kode_tahun_ajaran FROM periode_akademik pa "
        "JOIN tahun_ajaran ta ON ta.id = pa.tahun_ajaran_id WHERE pa.id=?",
        (periode_id,),
    ).fetchone()


def cache_periode(conn, periode_id):
    """Turunkan representasi TEXT cache (tahun_akademik, semester) dari 1
    baris periode_akademik yang dipilih di dropdown terkunci — supaya kolom
    TEXT lama (dipakai filter/tampilan/rekap yang sudah ada) tetap terisi
    otomatis & konsisten, TANPA operator mengetik ulang manual. Kembalikan
    ("", "") kalau periode_id kosong (form boleh dikirim tanpa periode)."""
    p = get_periode_by_id(conn, periode_id)
    if not p:
        return "", ""
    return p["kode_tahun_ajaran"], p["jenis"]


def cache_periode_gabungan(conn, periode_id):
    """Varian `cache_periode()` untuk tabel yang cuma punya SATU kolom TEXT
    cache gabungan (mis. `pengajuan_judul.semester` /
    `penetapan_pembimbing.semester`, isinya "2025/2026 - Ganjil" dalam satu
    string) — bukan dua kolom tahun_akademik + semester terpisah seperti
    `jadwal_kelas`/tabel SDM. String gabungan dibuat dari label yang SAMA
    persis dengan `get_periode_list()` (tanpa akhiran \" (Berjalan)\") supaya
    konsisten dengan yang tampil di dropdown. Kembalikan string kosong bila
    periode_id kosong (form boleh dikirim tanpa periode terkunci)."""
    ta, sem = cache_periode(conn, periode_id)
    if not ta:
        return ""
    return f"{ta} - {sem}"


def connect(db_path=None):
    db_path = db_path or get_default_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    _seed_defaults(conn)
    conn.commit()
    return conn


def _seed_defaults(conn):
    cur = conn.execute("SELECT COUNT(*) FROM pengaturan")
    if cur.fetchone()[0] == 0:
        for k, v in DEFAULT_PENGATURAN.items():
            conn.execute("INSERT INTO pengaturan(key, value) VALUES(?,?)", (k, v))
    cur = conn.execute("SELECT COUNT(*) FROM pengguna")
    if cur.fetchone()[0] == 0:
        # Satu-satunya akun aktif saat ini adalah Kaprodi (aplikasi offline,
        # 1 admin) — lihat rancangan-final-modul-sdm-kinerja-dosen.md §4.
        conn.execute(
            "INSERT INTO pengguna(nama, peran, aktif) VALUES(?,?,1)", (PERAN_KAPRODI, PERAN_KAPRODI)
        )
    cur = conn.execute("SELECT COUNT(*) FROM kurikulum_versi")
    if cur.fetchone()[0] == 0:
        # Satu kurikulum aktif KOSONG dibuat otomatis supaya modul Kurikulum
        # & OBE langsung siap dipakai — CPL dan Mata Kuliah tetap diisi
        # manual, tidak ada data akademik yang ditebak/diisi otomatis.
        conn.execute(
            "INSERT INTO kurikulum_versi(nama, tahun_berlaku, status, keterangan) "
            "VALUES(?,?,?,?)",
            ("Kurikulum OBE", "", "Aktif", ""),
        )
    cur = conn.execute("SELECT COUNT(*) FROM akreditasi_kriteria")
    if cur.fetchone()[0] == 0:
        # 9 Kriteria Akreditasi LAMEMBA (relevan utk program S1 Administrasi
        # Bisnis/Niaga) dibuat otomatis sebagai KERANGKA KOSONG — hanya
        # nomor & nama kriteria (fakta baku instrumen resmi), status semua
        # 'Belum Disusun' (default tabel, bukan status yang ditebak) dan
        # tanpa PIC/bukti dukung — itu tetap diisi manual oleh Kaprodi/GKM.
        for nomor, nama in [
            (1, "Visi, Misi, Tujuan, dan Strategi"),
            (2, "Tata Pamong, Tata Kelola, dan Kerja Sama"),
            (3, "Mahasiswa"),
            (4, "Sumber Daya Manusia"),
            (5, "Keuangan, Sarana, dan Prasarana"),
            (6, "Pendidikan"),
            (7, "Penelitian"),
            (8, "Pengabdian kepada Masyarakat"),
            (9, "Luaran dan Capaian Tridharma"),
        ]:
            conn.execute(
                "INSERT INTO akreditasi_kriteria(nomor_kriteria, nama_kriteria) VALUES(?,?)",
                (nomor, nama),
            )


# =============================================================================
# Audit UI/UX (permintaan fitur) — Reset Total Data
# =============================================================================
def reset_semua_data(conn):
    """Mengosongkan SELURUH tabel data lalu menabur ulang default awal
    (pengaturan, akun admin kosong, kurikulum default, 9 kriteria
    akreditasi) lewat _seed_defaults() yang SAMA dipakai saat instalasi
    baru pertama kali dibuka — supaya aplikasi kembali persis ke kondisi
    "baru diinstal", bukan diimplementasikan terpisah dan berisiko lupa
    menaburkan sesuatu.

    Sengaja MENGOSONGKAN tabel (DELETE FROM), bukan menghapus file .db itu
    sendiri: lebih portabel & aman -- tidak perlu menutup koneksi aktif
    atau menghadapi file lock (terutama relevan di Windows, target utama
    build .exe aplikasi ini), dan skema/struktur tabel tidak perlu dibuat
    ulang dari nol.

    TIDAK melakukan pengamanan apa pun (PIN/konfirmasi password/backup
    otomatis) -- itu tanggung jawab pemanggil (routes/backup.py), fungsi
    ini murni operasi database, konsisten dengan pola get_setting/
    set_setting di sekitarnya.

    File fisik yang sudah diunggah (dokumen Document Center, RPS, dst.)
    SENGAJA TIDAK ikut dihapus dari disk -- baris database yang
    merujuknya memang hilang (jadi tidak lagi terlihat di aplikasi),
    tapi berkas aslinya tetap ada di folder data sampai dibersihkan
    manual. Ini jauh lebih aman daripada menghapus folder lewat kode:
    risiko salah path/permission jauh lebih berbahaya daripada berkas
    yatim yang sekadar memakan ruang disk, dan berkas itu sudah ikut
    tersalin ke Backup Lengkap yang dibuat otomatis sebelum reset."""
    tabel = [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for t in tabel:
            conn.execute(f"DELETE FROM {t}")
        ada_sequence = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
        ).fetchone()
        if ada_sequence:
            conn.execute("DELETE FROM sqlite_sequence")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    _seed_defaults(conn)
    conn.commit()


def get_setting(conn, key, default=""):
    row = conn.execute("SELECT value FROM pengaturan WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO pengaturan(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def log(conn, aksi, detail="", *, modul=None, entitas=None, entitas_id=None,
        nilai_lama=None, nilai_baru=None, alasan=None):
    """Audit Menyeluruh — PHASE 4: Audit Trail generik.

    Parameter posisional (aksi, detail) TIDAK BERUBAH -- seluruh 112+
    pemanggilan db.log(conn, aksi, detail) yang sudah ada di codebase tetap
    berfungsi persis seperti sebelumnya tanpa disentuh. Parameter baru
    semuanya keyword-only & opsional, dipakai HANYA di titik-titik yang
    memang mencatat perubahan nilai pada satu baris data spesifik (mis.
    status_kelulusan sidang, status seminar, status mahasiswa) -- meniru
    contoh di audit: "Sidang #128, status_kelulusan, TUNDA -> LULUS".

    SENGAJA TIDAK ADA kolom user_id/ip/device (berbeda dari skema audit_log
    generik yang lazim di sistem multi-tenant): SIMPRODI adalah aplikasi
    1-admin offline (lihat PERAN_KAPRODI di constants.py) -- tidak ada
    banyak pengguna utk dibedakan, dan tidak ada jaringan/perangkat lain
    yang relevan dilacak. Menambahkan kolom itu hanya akan berisi nilai
    statis yang tidak menambah informasi apa pun, bukan audit trail yang
    jujur (lihat filosofi yang sama di routes/mutu.py: mengganti metrik
    ala-SaaS yang tidak nyata dengan yang benar-benar bisa dibuktikan)."""
    conn.execute(
        "INSERT INTO log_aktivitas(aksi, detail, modul, entitas, entitas_id, "
        "nilai_lama, nilai_baru, alasan) VALUES(?,?,?,?,?,?,?,?)",
        (aksi, detail, modul, entitas, entitas_id, nilai_lama, nilai_baru, alasan),
    )
    conn.commit()
