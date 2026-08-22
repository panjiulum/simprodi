"""Verifikasi migrasi skema `_rebuild_jadwal_kelas_fk_restrict` &
`_rebuild_cqi_siklus_fk_restrict` (lapis pertahanan SKEMA, menyusul guard
APLIKASI yang sudah diuji di test_audit_kontinuitas.py). Fokus di sini:
migrasi tidak boleh merusak database LAMA yang sudah punya data bertahun-
tahun (skenario paling berisiko — ini yang paling penting dipastikan
"tidak mengganggu modul yang sudah bekerja dengan baik").
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import db as _db  # noqa: E402

FAILS = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)


# =====================================================================
# 1) Simulasikan database LAMA persis skema sebelum audit ini (CASCADE),
#    lengkap dengan data bertahun-tahun: kurikulum, mata kuliah, KELAS di
#    3 tahun akademik berbeda, presensi (BAP), KRS, dan nilai per-CPMK.
# =====================================================================
tmpdir = tempfile.mkdtemp()
old_db_path = os.path.join(tmpdir, "old_data_prodi.db")

SKEMA_LAMA_MINIMAL = """
CREATE TABLE mahasiswa (id INTEGER PRIMARY KEY AUTOINCREMENT, nim TEXT UNIQUE NOT NULL, nama TEXT NOT NULL, status TEXT DEFAULT 'Aktif');
CREATE TABLE dosen (id INTEGER PRIMARY KEY AUTOINCREMENT, nama TEXT NOT NULL, nidn TEXT);
CREATE TABLE ruangan (id INTEGER PRIMARY KEY AUTOINCREMENT, nama TEXT UNIQUE NOT NULL);
CREATE TABLE pengaturan (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE pengguna (id INTEGER PRIMARY KEY AUTOINCREMENT, nama TEXT NOT NULL, peran TEXT DEFAULT 'Administrator', aktif INTEGER DEFAULT 1);
CREATE TABLE seminar (id INTEGER PRIMARY KEY AUTOINCREMENT, mahasiswa_id INTEGER UNIQUE NOT NULL, FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE);
CREATE TABLE sidang (id INTEGER PRIMARY KEY AUTOINCREMENT, mahasiswa_id INTEGER NOT NULL, FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE);

CREATE TABLE kurikulum_versi (id INTEGER PRIMARY KEY AUTOINCREMENT, nama TEXT NOT NULL, tahun_berlaku TEXT, status TEXT DEFAULT 'Draft', keterangan TEXT, dibuat_pada TEXT DEFAULT (datetime('now','localtime')));
CREATE TABLE cpl (id INTEGER PRIMARY KEY AUTOINCREMENT, kurikulum_id INTEGER NOT NULL, kode TEXT NOT NULL, kategori TEXT DEFAULT 'Pengetahuan', deskripsi TEXT NOT NULL, urutan INTEGER DEFAULT 0, FOREIGN KEY(kurikulum_id) REFERENCES kurikulum_versi(id) ON DELETE CASCADE);
CREATE TABLE mata_kuliah (id INTEGER PRIMARY KEY AUTOINCREMENT, kurikulum_id INTEGER NOT NULL, kode TEXT NOT NULL, nama TEXT NOT NULL, sks INTEGER DEFAULT 2, semester INTEGER DEFAULT 1, jenis TEXT DEFAULT 'Wajib', kelompok_mk TEXT, rps_status TEXT DEFAULT 'Belum Disusun', rps_file TEXT, rps_nama_file_asli TEXT, rps_revisi TEXT, rps_tanggal_sahkan TEXT, keterangan TEXT, FOREIGN KEY(kurikulum_id) REFERENCES kurikulum_versi(id) ON DELETE CASCADE);
CREATE TABLE cpmk (id INTEGER PRIMARY KEY AUTOINCREMENT, mata_kuliah_id INTEGER NOT NULL, kode TEXT NOT NULL, deskripsi TEXT NOT NULL, FOREIGN KEY(mata_kuliah_id) REFERENCES mata_kuliah(id) ON DELETE CASCADE);
CREATE TABLE cpmk_cpl (cpmk_id INTEGER NOT NULL, cpl_id INTEGER NOT NULL, PRIMARY KEY(cpmk_id, cpl_id), FOREIGN KEY(cpmk_id) REFERENCES cpmk(id) ON DELETE CASCADE, FOREIGN KEY(cpl_id) REFERENCES cpl(id) ON DELETE CASCADE);
CREATE TABLE sub_cpmk (id INTEGER PRIMARY KEY AUTOINCREMENT, cpmk_id INTEGER NOT NULL, kode TEXT NOT NULL, deskripsi TEXT NOT NULL, urutan INTEGER DEFAULT 0, FOREIGN KEY(cpmk_id) REFERENCES cpmk(id) ON DELETE CASCADE);

CREATE TABLE jadwal_kelas (id INTEGER PRIMARY KEY AUTOINCREMENT, mata_kuliah_id INTEGER NOT NULL, tahun_akademik TEXT NOT NULL, semester_ajaran TEXT DEFAULT 'Ganjil', kelas TEXT DEFAULT 'A', dosen_id INTEGER, hari TEXT, jam_mulai TEXT, jam_selesai TEXT, ruangan_id INTEGER, jumlah_pertemuan_rencana INTEGER DEFAULT 16, keterangan TEXT, FOREIGN KEY(mata_kuliah_id) REFERENCES mata_kuliah(id) ON DELETE CASCADE, FOREIGN KEY(dosen_id) REFERENCES dosen(id) ON DELETE SET NULL, FOREIGN KEY(ruangan_id) REFERENCES ruangan(id) ON DELETE SET NULL);
CREATE TABLE bap (id INTEGER PRIMARY KEY AUTOINCREMENT, jadwal_kelas_id INTEGER NOT NULL, pertemuan_ke INTEGER NOT NULL, tanggal TEXT, materi TEXT, sub_cpmk_id INTEGER, jumlah_hadir INTEGER, dosen_pengganti TEXT, catatan TEXT, status TEXT DEFAULT 'Terlaksana', FOREIGN KEY(jadwal_kelas_id) REFERENCES jadwal_kelas(id) ON DELETE CASCADE, FOREIGN KEY(sub_cpmk_id) REFERENCES sub_cpmk(id) ON DELETE SET NULL, UNIQUE(jadwal_kelas_id, pertemuan_ke));
CREATE TABLE krs (id INTEGER PRIMARY KEY AUTOINCREMENT, mahasiswa_id INTEGER NOT NULL, jadwal_kelas_id INTEGER NOT NULL, nilai_akhir REAL, nilai_huruf TEXT, FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE CASCADE, FOREIGN KEY(jadwal_kelas_id) REFERENCES jadwal_kelas(id) ON DELETE CASCADE, UNIQUE(mahasiswa_id, jadwal_kelas_id));
CREATE TABLE nilai_cpmk (id INTEGER PRIMARY KEY AUTOINCREMENT, krs_id INTEGER NOT NULL, cpmk_id INTEGER NOT NULL, nilai_angka REAL, FOREIGN KEY(krs_id) REFERENCES krs(id) ON DELETE CASCADE, FOREIGN KEY(cpmk_id) REFERENCES cpmk(id) ON DELETE CASCADE, UNIQUE(krs_id, cpmk_id));

CREATE TABLE cqi_siklus (id INTEGER PRIMARY KEY AUTOINCREMENT, kurikulum_id INTEGER NOT NULL, cpl_id INTEGER NOT NULL, tahun_akademik TEXT NOT NULL, target_persen REAL DEFAULT 70, capaian_persen REAL, akar_masalah TEXT, rencana_tindak_lanjut TEXT, penanggung_jawab TEXT, tenggat TEXT, status TEXT DEFAULT 'Direncanakan', evaluasi_hasil TEXT, dibuat_pada TEXT DEFAULT (datetime('now','localtime')), FOREIGN KEY(kurikulum_id) REFERENCES kurikulum_versi(id) ON DELETE CASCADE, FOREIGN KEY(cpl_id) REFERENCES cpl(id) ON DELETE CASCADE);
"""

raw = sqlite3.connect(old_db_path)
raw.executescript(SKEMA_LAMA_MINIMAL)

# --- Data 3 tahun akademik berbeda, murni lewat SQL mentah (simulasi
#     database lama yang sudah dipakai bertahun-tahun sebelum audit ini) ---
raw.execute("INSERT INTO kurikulum_versi(id, nama, status) VALUES(1,'Kurikulum 2020','Aktif')")
raw.execute("INSERT INTO mata_kuliah(id, kurikulum_id, kode, nama) VALUES(1,1,'MK-LAMA','Basis Data')")
raw.execute("INSERT INTO cpl(id, kurikulum_id, kode, deskripsi) VALUES(1,1,'CPL-01','Mampu merancang basis data')")
raw.execute("INSERT INTO cqi_siklus(id, kurikulum_id, cpl_id, tahun_akademik) VALUES(1,1,1,'2021/2022')")
raw.execute("INSERT INTO mahasiswa(id, nim, nama) VALUES(1,'2001001','Mhs Lama Satu')")
for tahun, kelas_id, jadwal_id in [("2021/2022", 1, 1), ("2022/2023", 2, 2), ("2023/2024", 3, 3)]:
    raw.execute(
        "INSERT INTO jadwal_kelas(id, mata_kuliah_id, tahun_akademik, kelas) VALUES(?,1,?,?)",
        (jadwal_id, tahun, kelas_id),
    )
    raw.execute(
        "INSERT INTO bap(jadwal_kelas_id, pertemuan_ke, status) VALUES(?,1,'Terlaksana')",
        (jadwal_id,),
    )
    raw.execute(
        "INSERT INTO krs(mahasiswa_id, jadwal_kelas_id, nilai_akhir, nilai_huruf) VALUES(1,?,85,'A')",
        (jadwal_id,),
    )
raw.commit()
raw.close()

jml_jadwal_sebelum = 3
jml_bap_sebelum = 3
jml_krs_sebelum = 3

# =====================================================================
# 2) Buka database lama itu dengan KODE BARU (app/db.py hasil perbaikan)
#    — ini persis yang terjadi saat operator update aplikasi ke versi ini.
# =====================================================================
conn = _db.connect(old_db_path)

sql_jk = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='jadwal_kelas'"
).fetchone()["sql"]
sql_cqi = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='cqi_siklus'"
).fetchone()["sql"]
check("jadwal_kelas.mata_kuliah_id sekarang ON DELETE RESTRICT", "ON DELETE RESTRICT" in sql_jk)
check("cqi_siklus.cpl_id sekarang ON DELETE RESTRICT", "ON DELETE RESTRICT" in sql_cqi)
check("cqi_siklus.kurikulum_id TETAP ON DELETE CASCADE (tidak ikut diubah)", "kurikulum_id" in sql_cqi and "CASCADE" in sql_cqi)

# --- Data lama harus utuh 100%, tidak ada yang hilang/berubah ---
n_jadwal = conn.execute("SELECT COUNT(*) n FROM jadwal_kelas").fetchone()["n"]
n_bap = conn.execute("SELECT COUNT(*) n FROM bap").fetchone()["n"]
n_krs = conn.execute("SELECT COUNT(*) n FROM krs").fetchone()["n"]
nilai_row = conn.execute("SELECT nilai_akhir, nilai_huruf FROM krs WHERE jadwal_kelas_id=1").fetchone()
tahun_terpakai = [r["tahun_akademik"] for r in conn.execute("SELECT tahun_akademik FROM jadwal_kelas ORDER BY id").fetchall()]

check(f"Jumlah jadwal_kelas tetap {jml_jadwal_sebelum} (tidak ada yang hilang)", n_jadwal == jml_jadwal_sebelum)
check(f"Jumlah bap (presensi) tetap {jml_bap_sebelum}", n_bap == jml_bap_sebelum)
check(f"Jumlah krs (nilai) tetap {jml_krs_sebelum}", n_krs == jml_krs_sebelum)
check("Nilai mahasiswa (85/A) dari kelas 2021/2022 tidak berubah", nilai_row["nilai_akhir"] == 85 and nilai_row["nilai_huruf"] == "A")
check(
    "Ketiga tahun akademik (2021/2022, 2022/2023, 2023/2024) semuanya masih ada",
    tahun_terpakai == ["2021/2022", "2022/2023", "2023/2024"],
)

# --- Foreign key integrity check menyeluruh: tidak ada baris orphan
#     tersisa akibat proses rebuild ---
fk_problems = conn.execute("PRAGMA foreign_key_check").fetchall()
check("PRAGMA foreign_key_check bersih setelah migrasi (tidak ada FK rusak)", len(fk_problems) == 0)

# =====================================================================
# 3) RESTRICT benar-benar bekerja di level DB — percobaan hapus mata
#    kuliah/CPL yang masih dipakai lewat SQL MENTAH (bukan lewat guard
#    aplikasi) harus ditolak SQLite sendiri.
# =====================================================================
try:
    conn.execute("DELETE FROM mata_kuliah WHERE id=1")
    conn.commit()
    check("DELETE mata_kuliah yang masih dipakai kelas ditolak SQLite (RESTRICT)", False)
except sqlite3.IntegrityError:
    conn.rollback()
    check("DELETE mata_kuliah yang masih dipakai kelas ditolak SQLite (RESTRICT)", True)

try:
    conn.execute("DELETE FROM cpl WHERE id=1")
    conn.commit()
    check("DELETE cpl yang masih dipakai siklus CQI ditolak SQLite (RESTRICT)", False)
except sqlite3.IntegrityError:
    conn.rollback()
    check("DELETE cpl yang masih dipakai siklus CQI ditolak SQLite (RESTRICT)", True)

# Data tetap utuh setelah kedua percobaan gagal di atas
check("mata_kuliah id=1 masih ada setelah percobaan DELETE ditolak", conn.execute("SELECT id FROM mata_kuliah WHERE id=1").fetchone() is not None)
check("cpl id=1 masih ada setelah percobaan DELETE ditolak", conn.execute("SELECT id FROM cpl WHERE id=1").fetchone() is not None)
check("Nilai (krs) tetap 3 baris setelah percobaan DELETE ditolak", conn.execute("SELECT COUNT(*) n FROM krs").fetchone()["n"] == 3)

# =====================================================================
# 4) Idempotensi: menutup & membuka ulang koneksi (persis siklus start
#    aplikasi berikutnya) tidak boleh error atau mengubah apa pun lagi.
# =====================================================================
conn.close()
conn2 = _db.connect(old_db_path)
n_jadwal2 = conn2.execute("SELECT COUNT(*) n FROM jadwal_kelas").fetchone()["n"]
check("Buka ulang (migrasi ke-2) tidak error & jumlah data tidak berubah", n_jadwal2 == jml_jadwal_sebelum)

# =====================================================================
# 5) Instalasi BARU (bukan upgrade dari database lama) juga harus otomatis
#    dapat skema RESTRICT sejak awal, tanpa harus melalui jalur migrasi.
# =====================================================================
tmpdir2 = tempfile.mkdtemp()
new_db_path = os.path.join(tmpdir2, "baru.db")
conn3 = _db.connect(new_db_path)
sql_jk_baru = conn3.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='jadwal_kelas'"
).fetchone()["sql"]
check("Instalasi database BARU langsung RESTRICT sejak awal", "ON DELETE RESTRICT" in sql_jk_baru)

print()
if FAILS:
    print(f"=== {len(FAILS)} GAGAL ===")
    for f in FAILS:
        print(" -", f)
    sys.exit(1)
else:
    print("=== SELESAI ===")
    print("SEMUA TES LULUS.")
