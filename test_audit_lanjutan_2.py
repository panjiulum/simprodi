# -*- coding: utf-8 -*-
"""
test_audit_lanjutan_2.py — Uji Pengembangan Lanjutan (Backup Menyeluruh +
Import Modul SDM & Mahasiswa).

Tidak diikutkan di paket produksi (murni verifikasi pengembangan).
"""
import os
import io
import sys
import zipfile
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402
from app import backup_core  # noqa: E402
from app import import_generic  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)


db_path = os.path.join(tmpdir, "test.db")
app = create_app(db_path=db_path)
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False
client = app.test_client()
client.post("/login", data={"username": "kaprodi", "password1": "test1234", "password2": "test1234"}, follow_redirects=True)
# Restrukturisasi poin 2: menu Import & Restore sekarang digerbangi PIN
# tambahan (terpisah dari password login) — set PIN sekali di sini,
# otomatis langsung terverifikasi untuk sesi `client` yang sedang aktif.
client.post("/pengaturan/pin", data={"pin1": "246810", "pin2": "246810"}, follow_redirects=True)

# ===========================================================================
# 1) BACKUP LENGKAP (.zip) — mencadangkan database + file fisik
# ===========================================================================
data_root = backup_core.get_data_root()
for folder, _desc in backup_core.DATA_SUBFOLDERS:
    os.makedirs(os.path.join(data_root, folder), exist_ok=True)
with open(os.path.join(data_root, "dokumen", "contoh_sk.pdf"), "wb") as fh:
    fh.write(b"%PDF-1.4 contoh isi dokumen")
with open(os.path.join(data_root, "surat_keluar", "contoh_surat.docx"), "wb") as fh:
    fh.write(b"contoh isi surat")

r = client.post("/pengaturan/backup/sekarang", data={"tipe": "lengkap"}, follow_redirects=True)
check("POST backup lengkap -> 200", r.status_code == 200)

backups = backup_core.list_backups()
zip_backups = [b for b in backups if b["nama"].endswith(".zip")]
check("Ada file backup .zip di riwayat", len(zip_backups) >= 1)

zip_path = zip_backups[0]["path"]
with zipfile.ZipFile(zip_path) as zf:
    names = zf.namelist()
    check("Zip berisi data_prodi.db", "data_prodi.db" in names)
    check("Zip berisi file dari folder dokumen", any(n.startswith("files/dokumen/") for n in names))
    check("Zip berisi file dari folder surat_keluar", any(n.startswith("files/surat_keluar/") for n in names))
    check("Zip berisi manifest.json", "manifest.json" in names)

manifest = backup_core.baca_manifest(zip_path)
check("baca_manifest() mengembalikan dict valid", isinstance(manifest, dict) and manifest.get("format") == "simprodi-backup-lengkap")

ok, pesan = backup_core.validasi_file_restore_zip(zip_path)
check(f"validasi_file_restore_zip() lolos untuk backup sah ({pesan})", ok)

# ===========================================================================
# 2) RESTORE LENGKAP — hapus file fisik, restore dari zip, pastikan kembali
# ===========================================================================
import shutil as _shutil
_shutil.rmtree(os.path.join(data_root, "dokumen"))
check("Folder dokumen sengaja dihapus dulu (simulasi komputer baru)",
      not os.path.isdir(os.path.join(data_root, "dokumen")))

cadangan_pra_restore = backup_core.restore_dari_file_zip(zip_path, db_path)
check("restore_dari_file_zip() mengembalikan path backup pra-restore",
      cadangan_pra_restore and os.path.isfile(cadangan_pra_restore))
check("Folder dokumen KEMBALI ada setelah restore",
      os.path.isfile(os.path.join(data_root, "dokumen", "contoh_sk.pdf")))
check("Folder surat_keluar KEMBALI ada setelah restore",
      os.path.isfile(os.path.join(data_root, "surat_keluar", "contoh_surat.docx")))

# File .zip rusak / bukan backup SIMPRODI harus ditolak
bad_zip = os.path.join(tmpdir, "bukan_backup.zip")
with zipfile.ZipFile(bad_zip, "w") as zf:
    zf.writestr("halo.txt", "bukan backup simprodi")
ok, pesan = backup_core.validasi_file_restore_zip(bad_zip)
check(f"Zip tanpa data_prodi.db DITOLAK ({pesan})", not ok)

# ===========================================================================
# 3) Restore endpoint via HTTP (butuh login ulang) — pastikan alur .zip jalan
# ===========================================================================
client2 = app.test_client()
client2.post("/login", data={"username": "kaprodi", "password": "test1234"}, follow_redirects=True)
# PIN sudah diatur lewat sesi `client` di atas (tersimpan di db) — sesi
# client2 ini beda cookie/sesi, jadi tetap wajib verifikasi PIN ulang.
client2.post("/pengaturan/pin/verifikasi", data={"pin": "246810"}, follow_redirects=True)
with open(zip_path, "rb") as fh:
    zip_bytes = fh.read()
r = client2.post(
    "/pengaturan/backup/restore",
    data={
        "password_konfirmasi": "test1234",
        "file_restore": (io.BytesIO(zip_bytes), "backup_lengkap_test.zip"),
    },
    content_type="multipart/form-data",
    follow_redirects=True,
)
check("POST restore .zip via HTTP -> 200 (redirect ke login)", r.status_code == 200)
check("Pesan sukses restore lengkap tampil", "Restore lengkap berhasil".encode() in r.data)

# ===========================================================================
# 4) IMPORT GENERIK — Dosen (prasyarat SDM) & Mahasiswa
# ===========================================================================
client3 = app.test_client()
client3.post("/login", data={"username": "kaprodi", "password": "test1234"}, follow_redirects=True)
client3.post("/pengaturan/pin/verifikasi", data={"pin": "246810"}, follow_redirects=True)

import openpyxl


def _buat_xlsx(header, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


dosen_buf = _buat_xlsx(import_generic.DOSEN_HEADER, [
    ["0011112222", "Dr. Budi Santoso, M.Kom", "081211112222", "budi@kampus.ac.id",
     "198001012010121001", "1111222233334444", "Lektor", "S3", "Basis Data", "Homebase", "", "", "", "Y"],
])
r = client3.post(
    "/pengaturan/import-generik/proses",
    data={"modul": "dosen", "file_excel": (dosen_buf, "dosen.xlsx")},
    content_type="multipart/form-data", follow_redirects=True,
)
check("Import Dosen via generik -> 200", r.status_code == 200)
check("Import Dosen -> 1 data baru", b'<div class="v">1</div>' in r.data)

import app.db as _db
with app.app_context():
    conn = app.get_db()
    dosen_row = conn.execute("SELECT id FROM dosen WHERE nidn='0011112222'").fetchone()
check("Dosen baru benar-benar tersimpan di database", dosen_row is not None)

mhs_buf = _buat_xlsx(import_generic.MAHASISWA_HEADER, [
    ["2025010099", "Contoh Mahasiswa Uji", "L", "Kota Uji", "01/01/2005",
     "081234567890", "mhs@student.ac.id", "2025", "Aktif", "Reguler"],
])
r = client3.post(
    "/pengaturan/import-generik/proses",
    data={"modul": "mahasiswa", "file_excel": (mhs_buf, "mhs.xlsx")},
    content_type="multipart/form-data", follow_redirects=True,
)
check("Import Mahasiswa via generik -> 200", r.status_code == 200)
check("Import Mahasiswa -> 1 data baru", b'<div class="v">1</div>' in r.data)

# Import ulang file SAMA -> harus jadi "update", bukan digandakan (idempoten)
mhs_buf2 = _buat_xlsx(import_generic.MAHASISWA_HEADER, [
    ["2025010099", "Contoh Mahasiswa Uji (Update)", "L", "Kota Uji", "01/01/2005",
     "081234567890", "mhs@student.ac.id", "2025", "Aktif", "Reguler"],
])
r = client3.post(
    "/pengaturan/import-generik/proses",
    data={"modul": "mahasiswa", "file_excel": (mhs_buf2, "mhs2.xlsx")},
    content_type="multipart/form-data", follow_redirects=True,
)
with app.app_context():
    conn = app.get_db()
    n_mhs = conn.execute("SELECT COUNT(*) c FROM mahasiswa WHERE nim='2025010099'").fetchone()["c"]
    nama_mhs = conn.execute("SELECT nama FROM mahasiswa WHERE nim='2025010099'").fetchone()["nama"]
check("Import ulang NIM sama TIDAK menggandakan baris (masih 1)", n_mhs == 1)
check("Import ulang NIM sama MEMPERBARUI nama (idempoten)", nama_mhs == "Contoh Mahasiswa Uji (Update)")

# ===========================================================================
# 5) IMPORT GENERIK — Modul SDM (7 sub-tabel), pakai dosen yang sudah diimpor
# ===========================================================================
sdm_modul_diuji = [
    "sdm_pendidikan", "sdm_penelitian", "sdm_pkm", "sdm_penunjang",
    "sdm_luaran", "sdm_peran_akademik", "sdm_timeline", "sdm_target",
]
for modul in sdm_modul_diuji:
    check(f"Modul import '{modul}' terdaftar di IMPORTERS", modul in import_generic.IMPORTERS)

# Template harus bisa diunduh & headernya harus konsisten dgn definisi
for modul in sdm_modul_diuji:
    r = client3.get(f"/pengaturan/import-generik/template/{modul}")
    check(f"Unduh template '{modul}' -> 200", r.status_code == 200)

info = import_generic.IMPORTERS["sdm_pendidikan"]
buf = _buat_xlsx(info["header"], [info["contoh"]])
r = client3.post(
    "/pengaturan/import-generik/proses",
    data={"modul": "sdm_pendidikan", "file_excel": (buf, "sdm.xlsx")},
    content_type="multipart/form-data", follow_redirects=True,
)
check("Import SDM Pendidikan (data dosen SUDAH ada) -> 1 data baru",
      b'<div class="v">1</div>' in r.data)

with app.app_context():
    conn = app.get_db()
    row = conn.execute(
        "SELECT * FROM aktivitas_pendidikan WHERE dosen_id=(SELECT id FROM dosen WHERE nidn='0012345678')"
    ).fetchone()
check("Baris aktivitas_pendidikan tersimpan dgn dosen_id benar (dari contoh template NIDN 0012345678)",
      row is None)  # dosen NIDN contoh belum ada di DB -> harus DILEWATI, bukan bikin dosen baru

# Sekarang tambahkan dosen dengan NIDN yang dipakai di contoh template SDM, lalu ulangi semua modul
dosen_sdm_buf = _buat_xlsx(import_generic.DOSEN_HEADER, [
    ["0012345678", "Dr. Contoh Nama, M.Kom", "081234567890", "contoh@kampus.ac.id",
     "198501012010121001", "5555666677778888", "Lektor", "S3", "Rekayasa Perangkat Lunak", "Homebase", "", "", "", "Y"],
])
client3.post("/pengaturan/import-generik/proses",
             data={"modul": "dosen", "file_excel": (dosen_sdm_buf, "dosen2.xlsx")},
             content_type="multipart/form-data", follow_redirects=True)

hasil_per_modul = {}
for modul in sdm_modul_diuji:
    info = import_generic.IMPORTERS[modul]
    buf = _buat_xlsx(info["header"], [info["contoh"]])
    r = client3.post(
        "/pengaturan/import-generik/proses",
        data={"modul": modul, "file_excel": (buf, f"{modul}.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    hasil_per_modul[modul] = r
    check(f"Import '{modul}' (dosen sudah ada) -> 1 data baru",
          b'<div class="v">1</div>' in r.data)

TABEL_PER_MODUL = {
    "sdm_pendidikan": "aktivitas_pendidikan",
    "sdm_penelitian": "aktivitas_penelitian",
    "sdm_pkm": "aktivitas_pkm",
    "sdm_penunjang": "aktivitas_penunjang",
    "sdm_luaran": "luaran_dosen",
    "sdm_peran_akademik": "peran_akademik_dosen",
    "sdm_timeline": "timeline_karier_dosen",
    "sdm_target": "target_kinerja_dosen",
}
with app.app_context():
    conn = app.get_db()
    dosen_id = conn.execute("SELECT id FROM dosen WHERE nidn='0012345678'").fetchone()["id"]
    for modul, table in TABEL_PER_MODUL.items():
        n = conn.execute(f"SELECT COUNT(*) c FROM {table} WHERE dosen_id=?", (dosen_id,)).fetchone()["c"]
        check(f"Tabel {table} berisi 1 baris utk dosen contoh setelah import '{modul}'", n == 1)

# Idempoten: import ulang template yang SAMA persis -> harus "update", tidak menggandakan
for modul in sdm_modul_diuji:
    info = import_generic.IMPORTERS[modul]
    buf = _buat_xlsx(info["header"], [info["contoh"]])
    client3.post(
        "/pengaturan/import-generik/proses",
        data={"modul": modul, "file_excel": (buf, f"{modul}_ulang.xlsx")},
        content_type="multipart/form-data", follow_redirects=True,
    )
with app.app_context():
    conn = app.get_db()
    for modul, table in TABEL_PER_MODUL.items():
        n = conn.execute(f"SELECT COUNT(*) c FROM {table} WHERE dosen_id=?", (dosen_id,)).fetchone()["c"]
        check(f"Import ulang '{modul}' TIDAK menggandakan baris (masih 1)", n == 1)

# Kode otomatis utk tabel yg pakai kode_prefix (PEN/PKM/LUR)
with app.app_context():
    conn = app.get_db()
    kode_pen = conn.execute("SELECT kode FROM aktivitas_penelitian WHERE dosen_id=?", (dosen_id,)).fetchone()["kode"]
    kode_pkm = conn.execute("SELECT kode FROM aktivitas_pkm WHERE dosen_id=?", (dosen_id,)).fetchone()["kode"]
    kode_lur = conn.execute("SELECT kode FROM luaran_dosen WHERE dosen_id=?", (dosen_id,)).fetchone()["kode"]
check(f"Kode otomatis Penelitian terisi format PEN-xxxx-xxx ({kode_pen})", kode_pen and kode_pen.startswith("PEN-"))
check(f"Kode otomatis PKM terisi format PKM-xxxx-xxx ({kode_pkm})", kode_pkm and kode_pkm.startswith("PKM-"))
check(f"Kode otomatis Luaran terisi format LUR-xxxx-xxx ({kode_lur})", kode_lur and kode_lur.startswith("LUR-"))

# Dosen yang TIDAK ADA di database harus dilewati (bukan bikin dosen baru)
with app.app_context():
    conn = app.get_db()
    jumlah_dosen_sebelum = conn.execute("SELECT COUNT(*) c FROM dosen").fetchone()["c"]
buf_dosen_tak_dikenal = _buat_xlsx(
    import_generic.IMPORTERS["sdm_target"]["header"],
    [["9999999999", "2025", "Publikasi", "3", "Target dosen tidak dikenal"]],
)
r = client3.post(
    "/pengaturan/import-generik/proses",
    data={"modul": "sdm_target", "file_excel": (buf_dosen_tak_dikenal, "target_unknown.xlsx")},
    content_type="multipart/form-data", follow_redirects=True,
)
check("Import SDM dgn NIDN tak dikenal -> 0 baru, 1 dilewati",
      b'<div class="v">0</div>' in r.data and b"tidak ditemukan di" in r.data)
with app.app_context():
    conn = app.get_db()
    jumlah_dosen_sesudah = conn.execute("SELECT COUNT(*) c FROM dosen").fetchone()["c"]
check("Import SDM dgn NIDN tak dikenal TIDAK membuat dosen baru",
      jumlah_dosen_sesudah == jumlah_dosen_sebelum)

# ===========================================================================
print("\n=== SELESAI ===")
if FAILS:
    print(f"ADA {len(FAILS)} YANG GAGAL:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
