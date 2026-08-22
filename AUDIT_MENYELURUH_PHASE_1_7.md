# Rekap Akhir — Implementasi Audit Menyeluruh SIMPRODI (Phase 1–7)

**S1 Ilmu Administrasi Bisnis (Niaga) — Institut Administrasi dan Kesehatan Setih Setio Muara Bungo**

Dokumen ini merangkum seluruh pekerjaan yang telah dikerjakan berdasarkan *Audit Menyeluruh SIMPRODI dan Rekomendasi Pengembangan*, dari perbaikan UI/UX awal hingga implementasi lengkap 7 fase roadmap pengembangan.

---

## 0. Titik Awal — Perbaikan UI/UX & Analisis Audit

Sebelum masuk ke roadmap 7 fase, dua hal dikerjakan lebih dulu:

1. **Perbaikan UI/UX modul Document Center & Generator Surat Umum** — chip filter yang tumpang tindih (CSS `flex-wrap` hilang), total dokumen salah hitung saat difilter, dan bug senyap tanggal surat (format ISO tidak dikenali parser, diam-diam jatuh ke tanggal hari ini).
2. **Analisis independen atas dokumen Audit Menyeluruh** — setiap temuan kritis diverifikasi langsung ke source code (bukan diterima mentah-mentah), dan terbukti akurat: bug `status_ta`, referential integrity yang hilang, hard-delete tanpa guard, dsb. semuanya berhasil direproduksi di kode.

---

## Phase 1 — Perbaikan Kritis (P0), 10 Item

| # | Item | Perbaikan |
|---|------|-----------|
| 1–3 | Bug `status_ta` salah setelah sidang dihapus + state machine tersebar | `logic.recalculate_status_ta()` sentral menggantikan `_sync_status_ta_sidang()` yang buggy (default salah ke "Sudah Sidang" saat tidak ada baris sidang) |
| 4–7 | FK integrity hilang di rantai TA | FK `ON DELETE RESTRICT` ditambahkan ke `periode_akademik`, `tahap_pengajuan`, `dosen`, `sidang` pada 5 tabel (`pengajuan_judul`, `penetapan_pembimbing`, `seminar`, `sidang`, `yudisium`) |
| 8–9 | Hard delete mahasiswa/dosen tanpa guard | Guard cek histori sebelum hapus; diarahkan ke field Status/Aktif sebagai pengganti |
| 10 | Validasi whitelist status tidak ada | Diterapkan di form manual **dan** jalur impor Excel (`import_excel.py`) |

**Form Data Mahasiswa**: field Status TA diubah jadi *read-only* (badge), tidak bisa lagi ditimpa manual.

**Ditemukan & diperbaiki sekaligus (di luar 10 item awal):**
- `import_excel.py` bisa *crash total* saat impor dosen dengan NIDN kembar
- `sidang_simpan()` satu-satunya rute tanpa `try/except` di seluruh modul akademik
- SK Pembimbing bisa dihapus meski mahasiswa sudah sidang (arsip resmi hilang)

---

## Phase 2 — Data Integrity (CHECK Constraint & Unique Index)

- **CHECK constraint** pada seluruh kolom status inti: `mahasiswa.status`/`status_ta`, `seminar.status`, `sidang.status_kelulusan` (nullable), `yudisium.status_yudisium`, `periode_akademik.jenis`/`status` — didahului normalisasi longgar (case-insensitive) agar data lama tidak menggagalkan migrasi.
- **Unique index parsial**: `dosen.nidn`/`nik`/`nuptk`, `pengajuan_judul.kode_pengajuan`, `surat_keluar.nomor_surat`, `tahap_pengajuan(periode_akademik_id, urutan)`.
- **Bug ditemukan saat implementasi**: helper rebuild-tabel tidak mempertahankan FK Phase 1 saat tabel yang sama di-rebuild ulang oleh Phase 2 — nyaris menghapus FK `seminar`/`sidang`/`yudisium` secara diam-diam. Diperbaiki dengan `_ambil_fk_existing()`.
- **Bug ditemukan di data uji**: 4 dari 30 test suite gagal — 3 di antaranya karena status placeholder tidak baku di fixture test itu sendiri, baru terungkap berkat CHECK constraint baru.

---

## Phase 3 — TA Workflow Engine

- **`app/workflow_ta.py`** (modul baru): graf transisi status_ta eksplisit (`TRANSISI_TA`) — menandai (bukan memblokir) transisi tidak wajar, karena aplikasi 1-admin offline harus tetap bisa dikoreksi.
- **Tabel `status_ta_riwayat`** (baru): audit event khusus alur TA — status lama, baru, pemicu, penanda wajar/tidak, waktu.
- **UI**: kartu "📜 Riwayat Status TA" di halaman Ubah Data Mahasiswa.
- **Re-check (dilakukan saat Phase 4)**: transisi ke "Menunggu Wisuda" (modul Yudisium) ternyata melewati `workflow_ta` sepenuhnya — titik paling penting (kelulusan final) tidak tercatat. Diperbaiki.

---

## Phase 4 — Audit Trail Generik

- **Evolusi `log_aktivitas`** yang sudah dipakai 112+ titik (bukan tabel baru terpisah — lebih rendah risiko): 6 kolom baru nullable (`modul`, `entitas`, `entitas_id`, `nilai_lama`, `nilai_baru`, `alasan`).
- **`db.log()`** diperluas dengan parameter keyword opsional — 100% backward-compatible.
- **Retrofit titik bernilai tinggi**: `sidang.status_kelulusan` (persis contoh literal dokumen audit: *"Sidang #128, status_kelulusan, TUNDA → LULUS"*), `seminar.status`, `yudisium.status_yudisium`, `mahasiswa.status`, `dosen.aktif`, operasi hapus.
- **UI**: halaman Log Aktivitas (Modul Mutu) menampilkan kolom Entitas + Perubahan (`lama → baru`).
- **Keputusan sadar**: tidak menambahkan `user_id`/`ip`/`device` — aplikasi 1-admin offline, kolom itu hanya akan berisi nilai statis tanpa informasi nyata.

---

## Phase 5 — Data Lifecycle & Versioning Kurikulum

- **Lifecycle Dosen**: `aktif` (boolean) → `status_kepegawaian` (Aktif/Nonaktif/Pindah/Pensiun), dengan `aktif` diturunkan otomatis (satu sumber kebenaran, bukan dua field yang bisa tidak sinkron).
- **Lifecycle Kurikulum**: 3 status → 5 tahap resmi (Draft → Review → Disetujui → Aktif → Diarsipkan).
- **Fitur Clone Version** (baru): menyalin seluruh CPL, MK, CPMK, Sub-CPMK, dan pemetaan CPMK↔CPL ke kurikulum Draft baru.
- **Keputusan desain penting**: dokumen audit menyebut "Active" sebagai titik kunci anti-destruktif, namun regression test yang ada membuktikan "Aktif" di codebase ini juga berarti "sedang dikerjakan" — mengunci "Aktif" akan merusak alur kerja normal. Kunci hanya diterapkan pada **Diarsipkan**; proteksi "Aktif" tetap mengandalkan guard pemakaian nyata yang sudah teruji.
- **Bug ditemukan & diperbaiki**: `simpan_versi()` masih menulis status lama `'Non-aktif'` (melanggar CHECK baru); `import_generic.py` tidak menyinkronkan `status_kepegawaian` saat impor massal dosen.
- **Re-check**: guard anti-destruktif ternyata hanya di rute **hapus**, bukan **tambah/edit** — CPL di kurikulum Diarsipkan masih bisa disisipi/diubah. Diperbaiki di 4 rute `simpan_*`.

---

## Phase 6 — OBE & CQI

- **Langkah "Assessment" eksplisit**: kolom `jenis_asesmen` baru di `nilai_cpmk` (Tugas/Kuis/UTS/UAS/Proyek/Praktikum/Nilai Akhir) — satu CPMK bisa punya beberapa skor per instrumen, bukan cuma satu angka final. Alur lama tetap 100% identik (default "Nilai Akhir").
- **CHECK constraint** pada `cqi_siklus.status`; **guard hapus** untuk siklus CQI "Selesai" (bukti PDCA lengkap tidak boleh hilang).
- **Bug analitik serius ditemukan saat re-check**: setelah `jenis_asesmen` ditambahkan, `capaian_cpl_program()` merata-ratakan **per baris nilai**, bukan **per mahasiswa** — mahasiswa dengan banyak instrumen tercatat "membobot" hasil beberapa kali lipat. Terbukti lewat simulasi: **"% Mahasiswa Tuntas" salah dari 75% menjadi seharusnya 50%** — metrik akreditasi yang bisa menyesatkan. Diperbaiki dengan agregasi dua tahap (per mahasiswa-per-CPMK dulu, baru lintas mahasiswa); modul CQI otomatis ikut benar karena memakai fungsi yang sama.

---

## Phase 7 — Dashboard Control Center

- Dashboard lama sudah mengumpulkan sinyal dari 15+ modul, tapi tersebar sebagai kartu per-modul — masalahnya arsitektur informasi, bukan kekurangan data.
- **Direorganisasi** (murni baca-ulang data yang sama, tanpa logika bisnis baru) ke 6 kategori berorientasi keputusan:
  - **KPI** — Mahasiswa Aktif, Dosen Aktif, Nilai Rata-rata Sidang, Kelengkapan RPS
  - **⚠️ Risk** — dosen overload, SK tidak lengkap, sidang TUNDA, realisasi BAP rendah, dst.
  - **⏰ Deadline** — jadwal 7 hari, agenda kalender, tenggat hibah/MoU/AMI, pengingat backup
  - **🔄 Workflow** — pengajuan menunggu review, belum SK pembimbing, siap yudisium, RPL dalam proses
  - **🎯 Quality** — kelengkapan RPS, rata-rata capaian CPL, siklus CQI, temuan AMI
  - **📁 Evidence** *(baru, sebelumnya tidak ada)* — jumlah dokumen Document Center, surat keluar tercatat, RPS disahkan, status backup

---

## Ringkasan Verifikasi

Setiap fase, tanpa kecuali, diverifikasi dengan pola yang sama sebelum dianggap selesai:

1. **Seluruh 30 test suite bawaan proyek** dijalankan ulang — hijau di setiap fase.
2. **Smoke-test end-to-end HTTP** khusus per fase (bukan hanya unit test) — membuktikan skenario nyata lewat rute Flask sungguhan.
3. **Simulasi migrasi database legacy** (skema sangat lama, data "kotor") di setiap fase — memastikan instalasi lama bisa naik versi tanpa kehilangan data atau error.

## Bug Nyata yang Ditemukan Selama Proses (di luar temuan awal audit)

Selain 10 item P0 dan rekomendasi dokumen audit, proses implementasi sendiri menemukan **9 bug/celah tambahan** — bukti bahwa setiap fase benar-benar diuji, bukan sekadar ditulis:

1. Filter chip UI overflow (CSS `flex-wrap` hilang) — titik awal proyek
2. Bug senyap tanggal ISO tidak ter-parse di Generator Surat Umum
3. `import_excel.py` bisa crash total akibat NIDN kembar
4. `sidang_simpan()` tanpa `try/except`
5. SK Pembimbing bisa dihapus meski mahasiswa sudah sidang
6. Helper rebuild-tabel menghapus FK secara diam-diam saat tabel di-rebuild dua kali
7. `simpan_versi()` kurikulum menulis status lama yang sudah tidak valid
8. `import_generic.py` tidak menyinkronkan `status_kepegawaian` dosen
9. Guard anti-destruktif kurikulum hanya di rute hapus, bukan simpan
10. Bug analitik capaian CPL (agregasi per-baris, bukan per-mahasiswa) — paling signifikan, berdampak langsung ke metrik akreditasi

## File Hasil Akhir

`simprodi_phase1_to_7.zip` — source code lengkap, siap ditimpakan ke folder instalasi lama (migrasi otomatis berjalan saat aplikasi pertama kali dibuka).
