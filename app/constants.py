# -*- coding: utf-8 -*-
"""
constants.py — Kamus istilah & parameter tetap Sistem Informasi Program Studi.

Kamus status di sini adalah PERBAIKAN atas temuan Audit (Medium #16):
"Taksonomi status tidak selaras antara dropdown Data Mahasiswa dan label
Dashboard/Statistik". Di aplikasi ini hanya ADA SATU daftar status resmi,
dipakai konsisten di semua form (dropdown, bukan ketik bebas) dan semua
rekap — sehingga kelas bug ini tidak bisa terjadi lagi.

Riwayat penggabungan (Fase Fondasi):
  Aplikasi ini adalah hasil penyatuan "Sistem Manajemen Skripsi" (Flask,
  modul Mahasiswa & Tugas Akhir — dipertahankan tanpa perubahan logika)
  dengan modul-modul dari "Prodi Office Manager"/POM (Electron/JSON, kini
  diporting ke SQLite) dan skema "AKD Excel Pro" untuk modul SDM & Kinerja
  Dosen. Nama & versi aplikasi diperbarui untuk mencerminkan cakupannya
  yang sekarang lebih luas dari sekadar skripsi.
"""

APP_NAME = "Sistem Informasi Program Studi"
APP_SHORT_NAME = "SIMPRODI"
APP_VERSION = "2.0.0"

# ---------------------------------------------------------------------------
# Status Pengajuan TA (Data Mahasiswa) — kamus tunggal, dipakai di seluruh app
# ---------------------------------------------------------------------------
STATUS_TA_BELUM = "Belum Mengajukan Judul"
STATUS_TA_MENGAJUKAN = "Mengajukan Judul"
STATUS_TA_BIMBINGAN = "Proses Bimbingan"
STATUS_TA_SUDAH_SIDANG = "Sudah Sidang"
STATUS_TA_LULUS = "LULUS"
STATUS_TA_TIDAK_LULUS = "TIDAK LULUS"
STATUS_TA_TUNDA = "TUNDA"
STATUS_TA_MENUNGGU_WISUDA = "Menunggu Wisuda"

STATUS_TA_LIST = [
    STATUS_TA_BELUM,
    STATUS_TA_MENGAJUKAN,
    STATUS_TA_BIMBINGAN,
    STATUS_TA_SUDAH_SIDANG,
    STATUS_TA_LULUS,
    STATUS_TA_TIDAK_LULUS,
    STATUS_TA_TUNDA,
    STATUS_TA_MENUNGGU_WISUDA,
]

STATUS_MHS_LIST = ["Aktif", "Cuti", "Non-Aktif", "Drop Out"]

# ---------------------------------------------------------------------------
# Fase Fondasi (Audit poin 1 & 3) — Tahun Ajaran terstruktur & Homebase Dosen
# ---------------------------------------------------------------------------
JENIS_PERIODE_LIST = ["Ganjil", "Genap", "Antara"]
STATUS_PERIODE_LIST = ["Draft", "Berjalan", "Selesai"]

STATUS_HOMEBASE_LIST = [
    "Homebase",
    "Dosen Luar Prodi",
    "Dosen Luar Fakultas",
    "Dosen Luar PT",
]

# ---------------------------------------------------------------------------
# Fase Pejabat Struktural — daftar saran nama jabatan (bukan pembatas keras;
# form tetap menerima teks bebas via <datalist>, supaya nomenklatur jabatan
# yang berbeda antar-institusi tetap bisa diketik manual).
# ---------------------------------------------------------------------------
DAFTAR_JABATAN_STRUKTURAL = [
    "Rektor",
    "Wakil Rektor I",
    "Wakil Rektor II",
    "Wakil Rektor III",
    "Dekan",
    "Wakil Dekan I",
    "Wakil Dekan II",
    "Wakil Dekan III",
    "Ketua Program Studi (Kaprodi)",
    "Sekretaris Program Studi",
    "Ketua LPPM",
    "Kepala Laboratorium",
    "Kepala Tata Usaha",
]

JK_LIST = ["L", "P"]

STATUS_REVIEW_LIST = ["Diajukan", "Disetujui", "Revisi", "Ditolak"]

STATUS_SEMINAR_LIST = ["Terdaftar", "Selesai", "Batal"]

STATUS_KELULUSAN_SIDANG = ["LULUS", "TIDAK LULUS", "TUNDA"]

STATUS_YUDISIUM_LIST = ["Direncanakan", "Terlaksana", "Batal"]

STUDI_LANJUT_LIST = ["Tidak", "Ya", "Belum Tahu"]

STATUS_KERJA_LIST = [
    "Belum Bekerja",
    "Bekerja - Sesuai Bidang",
    "Bekerja - Tidak Sesuai Bidang",
    "Wiraswasta",
    "Melanjutkan Studi",
]

# Checklist kelengkapan dokumen seminar (7 item, sesuai sheet Seminar asli)
SEMINAR_CHECKLIST = [
    ("chk_persetujuan", "Lbr. Persetujuan"),
    ("chk_bukti_bayar", "Bukti Bayar"),
    ("chk_mendeley", "Sert. Mendeley"),
    ("chk_krs", "KRS"),
    ("chk_bimbingan", "Bukti Bimbingan"),
    ("chk_hardcopy", "Hardcopy 3x"),
    ("chk_turnitin", "Plagiasi Turnitin"),
]


# ---------------------------------------------------------------------------
# Konversi nilai (identik dengan formula asli sheet 'Rencana Yudisium')
# ---------------------------------------------------------------------------
def nilai_angka_ke_huruf(nilai):
    """Audit bug baru — sebelumnya SEMUA nilai di bawah 65 jatuh ke huruf
    "C" (termasuk nilai 0), padahal C adalah grade LULUS dalam sistem
    akademik Indonesia sementara D/E berarti GAGAL/Tidak Lulus. Skala di
    bawah sekarang menambahkan tingkatan D & E, dengan batas B- (>=65)
    TETAP TIDAK BERUBAH — sengaja dijaga konsisten dengan KKM_CPMK=65 yang
    sudah dipakai OBE Assessment Engine sebagai ambang lulus CPMK (lihat
    logic._cpmk_progress / KKM_CPMK di bawah)."""
    if nilai is None or nilai == "":
        return ""
    n = float(nilai)
    if n >= 85:
        return "A"
    if n >= 80:
        return "A-"
    if n >= 75:
        return "B+"
    if n >= 70:
        return "B"
    if n >= 65:
        return "B-"
    if n >= 55:
        return "C"  # lulus — grade huruf lulus terendah
    if n >= 40:
        return "D"  # tidak lulus — mengulang disarankan
    return "E"  # tidak lulus


def nilai_angka_ke_huruf_yudisium(nilai):
    """Audit Lanjutan 6 (temuan tambahan) — konversi nilai_angka -> huruf
    KHUSUS utk konteks Yudisium/Wisuda/SK Yudisium (dipakai di
    logic.rencana_yudisium_rows() & logic.wisuda_rows(), yang muncul di
    ekspor Excel resmi "Rencana Yudisium"/"Wisuda" DAN di dokumen
    SK Yudisium (routes/surat.py::_gen_sk_yudisium) — bukan cuma
    tampilan internal).

    Kenapa BUKAN nilai_angka_ke_huruf() biasa: baris di kedua fungsi itu
    HANYA berisi mahasiswa yang sidang.status_kelulusan sudah 'LULUS'
    (lihat logic.sync_yudisium_dari_sidang() — filter WHERE
    status_kelulusan='LULUS' saat membuat baris yudisium). status_kelulusan
    itu keputusan MANUAL tim penguji, independen dari nilai_angka —
    lumrah dalam sidang skripsi Indonesia, panel bisa meluluskan mahasiswa
    walau nilai sidang pas-pasan/rendah. Kalau nilai_angka rendah itu
    (mis. 30 atau 55) dilewatkan apa adanya ke nilai_angka_ke_huruf(),
    hasilnya bisa "D" atau "E" — padahal secara definisi aplikasi sendiri
    (lihat nilai_angka_ke_huruf() di atas) D/E berarti GAGAL/tidak lulus. Baris yang
    sama, di dokumen yang sama, akan menyatakan mahasiswa itu LULUS
    (itulah premis dia ada di tabel Yudisium sama sekali) sekaligus
    "Nilai Huruf: D/E" (=tidak lulus) — kontradiksi tertanam di dokumen
    resmi yudisium/wisuda/SK yang dipakai institusi, bukan cuma tampilan
    internal yang bisa diabaikan.

    Perbaikan: nilai_angka MENTAH tetap ditampilkan apa adanya (kolom
    "Nilai Angka" tidak disentuh, transparan penuh) -- hanya kolom
    "Nilai Huruf" turunannya yang di-floor ke "C" (huruf lulus terendah)
    kalau hasil konversi mentah jatuh ke D/E, PERSIS krn baris ybs sudah
    dipastikan LULUS oleh keputusan panel. Utk mata kuliah biasa (nilai.py,
    semester_pendek.html, dsb) D/E TETAP dipakai apa adanya lewat
    nilai_angka_ke_huruf() yang asli -- di situ tidak ada keputusan panel
    yang menimpa nilai, jadi D/E memang berarti tidak lulus sungguhan."""
    huruf = nilai_angka_ke_huruf(nilai)
    if huruf in ("D", "E"):
        return "C"
    return huruf


def ipk_ke_predikat(ipk):
    if ipk is None or ipk == "":
        return ""
    n = float(ipk)
    if n >= 3.51:
        return "Dengan Pujian (Cumlaude)"
    if n >= 3.01:
        return "Sangat Memuaskan"
    if n >= 2.76:
        return "Memuaskan"
    return "Cukup"


# ---------------------------------------------------------------------------
# Modul SDM & Kinerja Dosen (diadaptasi dari skema "AKD Excel Pro")
# Kamus tunggal Master Data — sama seperti kamus status TA di atas, supaya
# dropdown di form input dan label di rekap/laporan tidak pernah selisih.
# ---------------------------------------------------------------------------
PERAN_KAPRODI = "Kaprodi"  # satu-satunya peran aktif saat ini (aplikasi offline, 1 admin)

SEMESTER_LIST = ["Ganjil", "Genap", "Antara"]

SKEMA_PENELITIAN_PKM_LIST = [
    "Penelitian Mandiri",
    "Penelitian Dasar",
    "Penelitian Terapan",
    "Penelitian Pengembangan",
    "PKM Mandiri",
    "PKM Reguler",
]

SUMBER_DANA_LIST = [
    "Mandiri",
    "Internal Perguruan Tinggi",
    "DIKTI/DIKTISAINTEK",
    "Hibah Eksternal",
    "Lainnya",
]

STATUS_AKTIVITAS_SDM_LIST = [
    "Draft",
    "Submitted",
    "Accepted",
    "Published",
    "Completed",
]

JENIS_LUARAN_LIST = [
    "Publikasi",
    "HKI",
    "Buku",
    "Prosiding",
    "Seminar",
    "Sertifikat",
    "Penghargaan",
]

JENIS_PERAN_AKADEMIK_LIST = [
    "Reviewer",
    "Editor",
    "Pembimbing",
    "Penguji",
    "Organisasi Profesi",
    "Jabatan",
    "Pelatihan",
]

JENIS_PERUBAHAN_KARIER_LIST = [
    "Jabatan Fungsional",
    "Pangkat/Golongan",
    "Sertifikasi Dosen (Serdos)",
    "NIDN/NIDK",
    "Pendidikan",
]

KATEGORI_TARGET_KINERJA_LIST = [
    "Publikasi",
    "Penelitian",
    "PKM",
    "HKI",
    "Buku",
    "Prosiding",
]

# Ambang "segera berakhir" untuk Reminder Masa Berlaku (Sertifikat, Jabatan,
# Organisasi Profesi) — dipakai bareng Notification Center, sama seperti
# ambang H-7/H-1 yang sudah dipakai kalender akademik.
REMINDER_MASA_BERLAKU_HARI = 90

# ---------------------------------------------------------------------------
# Modul 5 — Akademik Operasional & Kalender
# ---------------------------------------------------------------------------
KATEGORI_KALENDER_LIST = [
    "Akademik",
    "Ujian",
    "Rapat",
    "Libur",
    "Deadline",
    "Kegiatan",
    "Lainnya",
]
STATUS_KALENDER_LIST = ["Terjadwal", "Selesai", "Batal"]
WARNA_KATEGORI_KALENDER = {
    "Akademik": "#2563eb",
    "Ujian": "#dc2626",
    "Rapat": "#7c3aed",
    "Libur": "#16a34a",
    "Deadline": "#ea580c",
    "Kegiatan": "#0891b2",
    "Lainnya": "#64748b",
}

# ---------------------------------------------------------------------------
# Modul 6 — Kegiatan & Program Kerja Prodi
# ---------------------------------------------------------------------------
BIDANG_PROKER_LIST = [
    "Akademik & Kurikulum",
    "Kemahasiswaan",
    "SDM & Kelembagaan",
    "Sarana & Prasarana",
    "Kerjasama & Kemitraan",
    "Penjaminan Mutu",
    "Penelitian & PKM",
    "Lainnya",
]
STATUS_PROKER_LIST = ["Direncanakan", "Berjalan", "Selesai", "Tertunda", "Dibatalkan"]
KATEGORI_KEGIATAN_LIST = [
    "Rapat",
    "Pelatihan/Workshop",
    "Kunjungan/Studi Banding",
    "Seminar/Kuliah Umum",
    "Sosialisasi",
    "Monev",
    "Lainnya",
]
STATUS_KEGIATAN_LIST = ["Direncanakan", "Berlangsung", "Selesai", "Batal"]

# ---------------------------------------------------------------------------
# Modul 7 — Document Center
# ---------------------------------------------------------------------------
KATEGORI_DOKUMEN_LIST = [
    "SK/Surat Keputusan",
    "Surat Masuk",
    "Surat Keluar",
    "Kurikulum",
    "Akreditasi",
    "MoU/Kerjasama",
    "Laporan",
    "Kepegawaian",
    "Lainnya",
]
EKSTENSI_DOKUMEN_DIIZINKAN = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "jpg",
    "jpeg",
    "png",
    "zip",
    "rar",
}

# ---------------------------------------------------------------------------
# Modul 8 — Generator Surat Umum (di luar TA) + Buku Agenda Surat Keluar
# ---------------------------------------------------------------------------
# Kode singkat dipakai di format penomoran otomatis (mis. 001/ST/SIMPRODI/VII/2026)
JENIS_SURAT_UMUM = {
    "Surat Tugas": "ST",
    "Surat Keterangan": "SKet",
    "Surat Keputusan": "SK",
    "Surat Undangan": "SU",
    "Surat Edaran": "SE",
    "Nota Dinas": "ND",
    "Surat Pemberitahuan": "SPem",
    "Surat Permohonan": "SPerm",
    "Surat Balasan": "SB",
    "Surat Keterangan Aktif Kuliah": "SKAK",
}
JENIS_SURAT_UMUM_LIST = list(JENIS_SURAT_UMUM.keys())

# Kalimat pembuka baku per jenis surat — dipakai generator sebagai default
# (masih bisa ditimpa/diisi ulang di form karena pengisian isi tetap bebas).
PEMBUKA_SURAT_UMUM = {
    "Surat Tugas": "Yang bertanda tangan di bawah ini menugaskan kepada:",
    "Surat Keterangan": "Yang bertanda tangan di bawah ini menerangkan dengan sebenarnya bahwa:",
    "Surat Keputusan": "Menimbang, mengingat, dan memperhatikan hal-hal sebagaimana mestinya, "
    "dengan ini memutuskan:",
    "Surat Undangan": "Sehubungan dengan akan dilaksanakannya kegiatan sebagaimana tersebut di bawah "
    "ini, kami mengundang Bapak/Ibu untuk hadir pada:",
    "Surat Edaran": "Sehubungan dengan hal-hal yang perlu disampaikan, dengan ini diberitahukan "
    "kepada seluruh pihak terkait sebagai berikut:",
    "Nota Dinas": "Sehubungan dengan tugas dan tanggung jawab, disampaikan hal-hal sebagai berikut:",
    "Surat Pemberitahuan": "Dengan ini kami sampaikan pemberitahuan sebagai berikut:",
    "Surat Permohonan": "Dengan ini kami mengajukan permohonan sebagai berikut:",
    "Surat Balasan": "Menindaklanjuti surat/permohonan sebelumnya, dengan ini kami sampaikan balasan "
    "sebagai berikut:",
    "Surat Keterangan Aktif Kuliah": "Yang bertanda tangan di bawah ini menerangkan bahwa mahasiswa "
    "berikut benar terdaftar aktif kuliah:",
}


DEFAULT_PENGATURAN = {
    "tahun_akademik_aktif": "2025-2026",
    "nama_tahap_1": "Tahap 1 2025 - 2026",
    "nama_tahap_2": "Tahap 2 2025 - 2026",
    "nama_institusi": "Institut Administrasi dan Kesehatan Setih Setio Muara Bungo",
    "nama_prodi": "S1 Ilmu Administrasi Bisnis (Niaga)",
    "nama_fakultas": "Fakultas Administrasi",
    "alamat": "Jalan Setih Setio No.05, Pasir Putih, Muara Bungo 37211",
    "telp": "08117450744",
    "email": "iakssmuarabungo@gmail.com",
    "tarif_honor_seminar": "20000",
    "tarif_honor_penguji_sidang": "30000",
    "tarif_honor_pembimbing_1": "300000",
    "tarif_honor_pembimbing_2": "200000",
    "ambang_beban_dosen": "10",
    "durasi_sidang_menit": "90",
    "durasi_seminar_menit": "60",
    # Modul 8 — dipakai format penomoran otomatis Surat Keluar
    "kode_institusi_surat": "IAKS",
    "jabatan_penandatangan_default": "Ketua Program Studi",
    "nama_penandatangan_default": "",
    # Fase Pejabat Struktural — disinkron otomatis dari tabel
    # pejabat_struktural saat pejabat dijadikan default penandatangan;
    # dipakai di blok tanda tangan SK Tugas Akhir (routes/surat.py) & Surat
    # Umum (routes/surat_umum.py) supaya NIP/NIDN pejabat ikut tercetak.
    "nip_nidn_penandatangan_default": "",
    # Preferensi Tampilan, Tema & Pusat Notifikasi (Audit Lanjutan 3) — nilai
    # awal identik dengan perilaku aplikasi SEBELUM modul ini ada, supaya
    # database lama yang baru pertama kali membuka menu ini tidak berubah
    # tampilan/perilakunya sampai pengguna sengaja mengubahnya.
    "pref_densitas": "Nyaman",
    "pref_sidebar_mode": "otomatis",
    "pref_agenda_hari": "7",
    "tema_warna": "indigo",
    "notif_ambang_sdm": "90",
    "notif_ambang_tridharma": "14",
    "notif_ambang_mitra": "30",
    "notif_ambang_ami": "14",
}

# ---------------------------------------------------------------------------
# Modul 9 — Kurikulum & OBE
# ---------------------------------------------------------------------------
# Kategori CPL mengikuti unsur capaian pembelajaran SN-DIKTI (Permendikbudristek
# 53/2023) yang juga dipakai sebagai unsur penilaian pada instrumen akreditasi
# LAMEMBA — bukan istilah bebas, supaya matriks CPL bisa langsung dipetakan
# ke borang akreditasi.
KATEGORI_CPL_LIST = ["Sikap", "Pengetahuan", "Keterampilan Umum", "Keterampilan Khusus"]

JENIS_MK_LIST = ["Wajib", "Pilihan"]

STATUS_RPS_LIST = ["Belum Disusun", "Draft", "Review GKM", "Disahkan"]

# Audit Menyeluruh — PHASE 5: Data Lifecycle & Versioning Kurikulum.
# Sebelumnya hanya 3 status (Draft/Aktif/Non-aktif) — cukup utk menandai
# "yang mana yang berlaku sekarang", tapi tidak mencerminkan siklus hidup
# penyusunan kurikulum yang sesungguhnya (draft -> ditinjau GKM -> disetujui
# senat/GKM -> diberlakukan -> pensiun/diarsipkan setelah digantikan versi
# baru). Diperluas jadi 5 tahap eksplisit, cocok dgn Audit §24 (Draft ->
# Review -> Approved -> Active -> Archived). "Non-aktif" lama dipetakan ke
# "Diarsipkan" saat migrasi (lihat _rebuild_kurikulum_versi_check di db.py)
# -- makna praktisnya sama: versi yang sudah tidak berlaku.
STATUS_KURIKULUM_LIST = ["Draft", "Review", "Disetujui", "Aktif", "Diarsipkan"]
# Status yang tidak lagi boleh diubah secara destruktif (hapus CPL/MK/CPMK/
# Sub-CPMK). Audit §24 secara literal menyebut "Active" (Aktif) sebagai
# titik kunci, TAPI di codebase ini "Aktif" sejak awal juga dipakai sebagai
# penanda "kurikulum yang sedang dikerjakan/dibangun" (lihat helper
# _kurikulum_aktif() di routes/kurikulum.py, dan test_audit_kontinuitas.py
# yang secara sengaja menguji CPL/MK TANPA pemakaian nyata tetap boleh
# dihapus meski kurikulumnya "Aktif") — mengunci "Aktif" secara membabi
# buta akan merusak alur normal membangun struktur kurikulum baru sebelum
# ada mahasiswa/kelas yang benar-benar memakainya.
#
# Keputusan desain: proteksi thd data akademik yang SUDAH benar-benar
# dipakai (kelas sudah dibuka, siklus CQI sudah tercatat) TETAP lewat guard
# berbasis pemakaian nyata yang sudah ada (Audit Kontinuitas, jauh sebelum
# audit ini) di hapus_cpl/hapus_mk — itu proteksi yang sesungguhnya
# dibutuhkan. Kunci status di sini HANYA utk "Diarsipkan": kurikulum yang
# sudah resmi pensiun tidak ada alasan legitimate utk masih diubah
# strukturnya lewat modul ini (kalau perlu revisi, Clone Version dulu).
STATUS_KURIKULUM_TERKUNCI = {"Diarsipkan"}

# Audit Menyeluruh — PHASE 5: lifecycle dosen (Audit §23) — sebelumnya
# hanya kolom `aktif` (boolean 1/0), tidak membedakan ALASAN nonaktif
# (masih 1 prodi tapi cuti/nonaktif sementara vs pindah ke institusi lain
# vs pensiun permanen) padahal ketiganya punya implikasi berbeda utk
# pelaporan SDM/BKD. `dosen.aktif` (boolean) DIPERTAHANKAN apa adanya demi
# kompatibilitas — dipakai di banyak query `WHERE aktif=1` di seluruh
# aplikasi (dropdown pemilihan dosen dsb.) — tapi sekarang DITURUNKAN
# otomatis dari status_kepegawaian (aktif=1 hanya kalau "Aktif"), bukan
# lagi field terpisah yang bisa tidak sinkron.
STATUS_KEPEGAWAIAN_DOSEN_LIST = ["Aktif", "Nonaktif", "Pindah", "Pensiun"]

EKSTENSI_RPS_DIIZINKAN = {"pdf", "doc", "docx"}

# ---------------------------------------------------------------------------
# Modul 10 — Jadwal Kelas & BAP (Berita Acara Perkuliahan)
# ---------------------------------------------------------------------------
HARI_LIST = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]

STATUS_BAP_LIST = ["Terlaksana", "Ditunda", "Dosen Pengganti"]

# Ambang realisasi materi dianggap "berisiko" (dipakai badge merah/kuning di
# dashboard modul), bukan pembatas keras — Kaprodi tetap bisa lihat semua.
AMBANG_REALISASI_BAP_AMAN = 80  # persen

# ---------------------------------------------------------------------------
# Modul 11 — Nilai Mahasiswa & OBE Assessment Engine
# ---------------------------------------------------------------------------
# KKM (Kriteria Ketuntasan Minimal) skala 0-100 dipakai OBE Assessment Engine
# untuk menghitung "persentase mahasiswa mencapai CPMK/CPL". Nilai 65 ini
# sengaja disamakan dengan ambang huruf B- (bukan C) di nilai_angka_ke_huruf()
# — angka konstanta ini TIDAK diubah oleh audit penambahan grade D/E, supaya
# perhitungan capaian CPL yang sudah berjalan tetap konsisten.
KKM_CPMK = 65

# Audit Menyeluruh — PHASE 6: OBE & CQI. Rantai keterlacakan OBE penuh per
# Audit §25/§26 adalah "CPL -> CPMK -> Sub-CPMK -> Assessment -> Nilai ->
# Achievement -> CQI". Sebelum ini, nilai_cpmk hanya punya SATU nilai_angka
# polos per (krs_id, cpmk_id) — mewakili "hasil akhir CPMK", tapi TIDAK
# menyebutkan instrumen asesmen APA yang menghasilkan angka itu (Tugas?
# UTS? UAS? Proyek?), padahal itu justru bukti yang biasanya diminta
# asesor akreditasi ("tunjukkan instrumen penilaian yang dipakai").
#
# `jenis_asesmen` MENAMBAHKAN langkah "Assessment" itu secara eksplisit,
# TANPA mengubah cara kerja "Nilai Akhir Mata Kuliah" yang sudah ada
# (default kolom ini = 'Nilai Akhir', jadi alur input satu-nilai-per-CPMK
# yang sudah dipakai operator sekarang tetap identik) — operator yang mau
# lebih rinci tinggal memilih instrumen lain di dropdown sebelum input,
# dan skornya tercatat terpisah per instrumen (bukan menimpa). Perhitungan
# capaian (logic.py::capaian_cpl_mahasiswa/program) TIDAK perlu diubah:
# sudah generik merata-ratakan SEMUA baris nilai_cpmk yang cocok filternya,
# jadi otomatis ikut menghitung berapa pun banyak instrumen yang terisi.
JENIS_ASESMEN_LIST = ["Nilai Akhir", "Tugas", "Kuis", "UTS", "UAS", "Proyek", "Praktikum"]

# ---------------------------------------------------------------------------
# Modul 12 — Siklus CQI (Continuous Quality Improvement)
# ---------------------------------------------------------------------------
STATUS_CQI_LIST = ["Direncanakan", "Berjalan", "Selesai"]
TARGET_CAPAIAN_CPL_DEFAULT = 70  # persen, bisa diubah per CPL saat siklus dibuat

# ---------------------------------------------------------------------------
# Modul 13 — Semester Pendek (SP)
# ---------------------------------------------------------------------------
STATUS_SP_PERIODE_LIST = ["Draft", "Pendaftaran Dibuka", "Berjalan", "Selesai"]

# Status kapasitas kelas TIDAK termasuk daftar ini — dihitung on-the-fly
# (lihat logic.sp_status_kelas()), bukan status yang dipilih manual.
STATUS_APPROVAL_SP_LIST = ["Menunggu", "Disetujui", "Ditolak"]

STATUS_PERTEMUAN_SP_LIST = ["Terlaksana", "Ditunda"]

# Bobot komponen nilai akhir SP (identik dengan pola tampilan SITIPRO:
# Tugas 30% + UTS 30% + UAS 40%) — dipakai logic.sp_hitung_nilai_akhir().
SP_BOBOT_TUGAS = 0.30
SP_BOBOT_UTS = 0.30
SP_BOBOT_UAS = 0.40

# Ambang kehadiran wajib SP (identik dengan syarat kehadiran 80% di aturan
# akademik SP pada umumnya) — informasional/badge, bukan pembatas keras
# terhadap penginputan nilai (Kaprodi tetap yang memutuskan).
SP_AMBANG_KEHADIRAN = 80

# ---------------------------------------------------------------------------
# Modul 14 — RPL (Rekognisi Pembelajaran Lampau)
# ---------------------------------------------------------------------------
JENIS_PENGAKUAN_RPL_LIST = [
    "Pendidikan Formal Sebelumnya",
    "Pengalaman Kerja",
    "Pelatihan/Sertifikasi",
]

STATUS_RPL_LIST = ["Verifikasi Berkas", "Asesmen Portofolio", "Disetujui", "Ditolak"]

JENIS_DOKUMEN_RPL_LIST = [
    "Ijazah",
    "Transkrip Nilai",
    "Sertifikat Pelatihan/Kompetensi",
    "Surat Pengalaman Kerja",
    "Portofolio",
    "Lainnya",
]

# ---------------------------------------------------------------------------
# Modul 15 — Penelitian, PKM & Publikasi/HKI (Tri Dharma Program Studi)
# Dibangun DI ATAS data aktivitas_penelitian/aktivitas_pkm/luaran_dosen
# (Modul 4 — SDM & Kinerja Dosen), bukan tabel baru yang menduplikasi data.
# Kamus di sini HANYA untuk tabel baru tridharma_tinjauan (tinjauan/
# keputusan institusional, terpisah dari status self-report dosen yang
# sudah punya kamusnya sendiri: STATUS_AKTIVITAS_SDM_LIST).
# ---------------------------------------------------------------------------
STATUS_TINJAUAN_TRIDHARMA_LIST = ["Belum Ditinjau", "Direview", "Disetujui", "Revisi", "Ditolak"]

# Ambang "segera jatuh tempo" untuk reminder tenggat laporan hibah
# (tridharma_tinjauan.tenggat_laporan) — pola sama dengan
# REMINDER_MASA_BERLAKU_HARI, konteks berbeda (laporan, bukan sertifikat).
AMBANG_TENGGAT_LAPORAN_HARI = 14
# ---------------------------------------------------------------------------
# Modul 16 — Kerja Sama & Mitra
# ---------------------------------------------------------------------------
KATEGORI_MITRA_LIST = [
    "Instansi Pemerintah",
    "Industri/Perusahaan Nasional",
    "Perusahaan Multinasional",
    "Lembaga Pendidikan",
    "Organisasi Non-Profit/LSM",
    "Lainnya",
]
SKALA_MITRA_LIST = ["Nasional", "Internasional"]

JENIS_DOKUMEN_MITRA_LIST = [
    "MoU (Nota Kesepahaman)",
    "MoA (Perjanjian Kerja Sama)",
    "IA (Implementation Arrangement)",
    "Perjanjian Lainnya",
]
STATUS_DOKUMEN_MITRA_LIST = ["Draft", "Aktif", "Proses Perpanjangan", "Berakhir", "Dibatalkan"]

JENIS_PROGRAM_MITRA_LIST = [
    "Pendidikan/MBKM",
    "Magang/Praktik Kerja",
    "Praktisi Mengajar",
    "Tri Dharma/Penelitian",
    "Tri Dharma/PKM",
    "Pertukaran Mahasiswa",
    "Penyerapan Lulusan",
    "Lainnya",
]
STATUS_PROGRAM_MITRA_LIST = ["Perencanaan", "Berjalan", "Selesai", "Dibatalkan"]

JENIS_LUARAN_KERJASAMA_LIST = [
    "Mahasiswa Magang/MBKM",
    "Publikasi Bersama",
    "HKI Bersama",
    "Modul/Bahan Ajar Bersama",
    "Penyerapan Lulusan",
    "Lainnya",
]

# Ambang "segera berakhir" dokumen MoU/MoA/IA — sama dengan konteks demo
# SITIPRO ("berakhir dalam 30 hari"), pola sama dgn REMINDER_MASA_BERLAKU_HARI.
AMBANG_KADALUARSA_MOU_HARI = 30

# ---------------------------------------------------------------------------
# Modul 17 — Mutu: IKU, Akreditasi & Audit Mutu Internal (SPMI)
# ---------------------------------------------------------------------------
# (nomor, nama, cara_hitung) — cara_hitung hanya label tampilan yang
# menjelaskan sumber data realisasi, DERIVED = dihitung otomatis lintas
# modul, MANUAL = tidak ada sumber data di SIMPRODI, diisi Kaprodi.
DAFTAR_IKU = [
    (1, "Lulusan Mendapat Pekerjaan yang Layak", "DERIVED"),
    (2, "Mahasiswa Mendapat Pengalaman di Luar Kampus", "DERIVED"),
    (3, "Dosen Berkegiatan di Luar Kampus", "DERIVED"),
    (4, "Praktisi Mengajar di Dalam Kampus", "DERIVED"),
    (5, "Hasil Kerja Dosen Digunakan Masyarakat/Rekognisi", "DERIVED"),
    (6, "Program Studi Bekerja Sama dengan Mitra Kelas Dunia", "DERIVED"),
    (7, "Kelas yang Kolaboratif dan Partisipatif", "MANUAL"),
    (8, "Program Studi Berstandar Internasional", "MANUAL"),
]

STATUS_KRITERIA_AKREDITASI_LIST = ["Belum Disusun", "Proses Penyusunan", "Draft Selesai", "Final"]

STATUS_AMI_SIKLUS_LIST = ["Direncanakan", "Berjalan", "Selesai"]
KATEGORI_TEMUAN_AMI_LIST = ["Sesuai", "Observasi", "KTS Minor", "KTS Mayor"]
STATUS_TEMUAN_AMI_LIST = ["Terbuka", "Proses Tindak Lanjut", "Selesai", "Terverifikasi"]

# ---------------------------------------------------------------------------
# Audit Lanjutan 3 — Preferensi Tampilan, Pusat Notifikasi & Tema Tampilan
# ---------------------------------------------------------------------------
# Preferensi Tampilan (routes/preferensi.py) — preferensi tunggal (aplikasi
# 1 akun/1 komputer, lihat catatan pengguna di db.py), disimpan di tabel
# `pengaturan` yang sama dengan Identitas & Branding, bukan tabel baru.
PREF_DENSITAS_LIST = ["Nyaman", "Padat"]

# (kode, label) — "otomatis" = perilaku asli sidebar (grup aktif otomatis
# terbuka, sisanya ingat pilihan terakhir via localStorage, lihat base.html).
PREF_SIDEBAR_MODE_LIST = [
    ("otomatis", "Ingat pilihan terakhir per grup (default)"),
    ("buka_semua", "Selalu buka semua grup saat halaman dimuat"),
    ("tutup_semua", "Selalu tutup semua grup kecuali yang sedang aktif"),
]

# Rentang "Agenda Mendatang" di Dashboard & Pusat Notifikasi — sebelumnya
# baku 7 hari (acara_mendatang(conn, hari=7) di dashboard.py).
PREF_AGENDA_HARI_LIST = [3, 7, 14, 30]

# Tema Tampilan (routes/tema.py) — hanya mengganti aksen warna (--primary/
# --primary-dark/--primary-soft/--violet/--violet-soft), BUKAN mode gelap:
# --surface/--canvas/--ink tetap terang di semua tema supaya kontras teks
# & keterbacaan tabel/rekap yang sudah teruji tidak berubah, sesuai cakupan
# roadmap asal ("pilihan tema warna ... di luar tema indigo baku").
# "indigo" = palet asal SIMPRODI (:root di style.css), tanpa override.
TEMA_WARNA_LIST = [
    {"kode": "indigo", "label": "Indigo (Baku)", "preview": "#5352D0"},
    {"kode": "emerald", "label": "Emerald", "preview": "#0F9D67"},
    {"kode": "ocean", "label": "Ocean Blue", "preview": "#1D6FC4"},
    {"kode": "amber", "label": "Amber", "preview": "#C4750E"},
    {"kode": "rose", "label": "Rose", "preview": "#C43F6B"},
    {"kode": "slate", "label": "Slate", "preview": "#465166"},
]

# Pusat Notifikasi (routes/notifikasi.py) — ambang default per kategori,
# masing-masing sudah punya konstanta bawaan sendiri di fungsi asal
# logic.py (REMINDER_MASA_BERLAKU_HARI, AMBANG_TENGGAT_LAPORAN_HARI,
# AMBANG_KADALUARSA_MOU_HARI, dan 14 hari baku untuk AMI); daftar ini hanya
# dipakai untuk membangun form pengaturan ambang di satu tempat terpusat,
# key `pengaturan` yang dibaca menimpa konstanta baku di atas kalau diisi.
NOTIF_AMBANG_FIELDS = [
    (
        "notif_ambang_sdm",
        "SDM — Masa Berlaku Sertifikat/Peran Akademik",
        REMINDER_MASA_BERLAKU_HARI,
    ),
    ("notif_ambang_tridharma", "Tri Dharma — Tenggat Laporan Hibah", AMBANG_TENGGAT_LAPORAN_HARI),
    (
        "notif_ambang_mitra",
        "Kerja Sama — Kadaluarsa Dokumen MoU/MoA/IA",
        AMBANG_KADALUARSA_MOU_HARI,
    ),
    ("notif_ambang_ami", "Mutu — Tenggat Tindak Lanjut Temuan AMI", 14),
]

# Audit poin 4 — batas ambang notifikasi. Harus sinkron dengan atribut
# min/max pada <input type="number"> di templates/pengaturan/notifikasi.html;
# dulu hanya ditegakkan di client (HTML), sisi server cuma cek .isdigit()
# sehingga nilai seperti 999999 tetap tersimpan tanpa batas atas.
NOTIF_AMBANG_MIN = 1
NOTIF_AMBANG_MAX = 365
