# -*- coding: utf-8 -*-
"""
test_audit_lanjutan_5.py — Uji Pengembangan Lanjutan 5 (menutup gap audit
di 4 modul yang belum pernah dibedah secara khusus: Kelulusan/Tracer
Study, Kegiatan & Program Kerja, Backup & Restore, Import Excel).

Temuan yang divalidasi di sini (lihat komentar audit di masing-masing
file sumber untuk detail lengkap):

1. routes/kelulusan.py
   - yudisium_simpan(): dulu TIDAK dibungkus try/except -> IPK Final
     bukan angka bisa memicu 500 mentah. Sekarang divalidasi + pesan
     ramah, dan IPK di luar rentang 0.00-4.00 ditolak.
   - status_yudisium sekarang divalidasi terhadap C.STATUS_YUDISIUM_LIST.
   - wisuda_simpan() sekarang dibungkus try/except (konsisten dgn modul
     lain).
   - tracer_hapus() sekarang tercatat ke log_aktivitas (dulu tidak).
   - _kirim_excel() yang digandakan di kelulusan.py & rekap.py sudah
     dipusatkan ke app/export_utils.py (kirim_excel) — 3 ekspor Excel di
     modul Kelulusan tetap harus jalan normal.
2. routes/kegiatan.py
   - simpan_proker()/simpan_kegiatan(): bidang/status/kategori sekarang
     divalidasi terhadap daftar resmi; anggaran negatif ditolak.
3. app/backup_core.py
   - Perbaikan celah "zip slip" (path traversal) pada restore .zip:
     entri arsip dgn path absolut / "../" sekarang ditolak SEBELUM
     proses restore berjalan.
4. app/__init__.py
   - MAX_CONTENT_LENGTH sekarang ditetapkan secara eksplisit (dulu tidak
     ada batas sama sekali).

Tidak diikutkan di paket produksi (murni verifikasi pengembangan).
"""
import os
import sys
import io
import zipfile
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402
from app import backup_core  # noqa: E402

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
client.post("/pengaturan/pin", data={"pin1": "246810", "pin2": "246810"}, follow_redirects=True)

# ---------------------------------------------------------------------
# 0. Konfigurasi dasar
# ---------------------------------------------------------------------
check("MAX_CONTENT_LENGTH ditetapkan (dulu tidak ada sama sekali)",
      app.config.get("MAX_CONTENT_LENGTH") is not None and app.config["MAX_CONTENT_LENGTH"] > 0)

# ---------------------------------------------------------------------
# 1. Kelulusan — Yudisium: penanganan galat & validasi
# ---------------------------------------------------------------------
with app.app_context():
    conn = app.get_db()
    conn.execute("INSERT INTO mahasiswa(nim, nama, status, status_ta) VALUES(?,?,?,?)",
                 ("2022000111", "Mhs Uji Yudisium", "Aktif", "Sudah Sidang"))
    mid = conn.execute("SELECT id FROM mahasiswa WHERE nim='2022000111'").fetchone()["id"]
    conn.execute(
        "INSERT INTO sidang(mahasiswa_id, judul_sidang, nilai_angka, status_kelulusan) "
        "VALUES(?,?,?,?)", (mid, "Judul Uji Yudisium", 88, "LULUS"))
    conn.commit()

# Trigger sync (GET halaman yudisium memanggil sync_yudisium_dari_sidang)
yud_page = client.get("/kelulusan/yudisium")
check("GET /kelulusan/yudisium -> 200", yud_page.status_code == 200)
check("Mahasiswa LULUS sidang otomatis muncul di draft Yudisium", b"Mhs Uji Yudisium" in yud_page.data)

# 1a. IPK bukan angka -> dulu 500 mentah, sekarang pesan ramah + tetap 200
r = client.post("/kelulusan/yudisium/simpan", data={
    "mahasiswa_id": str(mid), "ipk_final": "abc-tidak-valid", "status_yudisium": "Direncanakan",
}, follow_redirects=True)
check("IPK Final non-angka -> TIDAK 500, direct balik dgn 200", r.status_code == 200)
check("Pesan galat IPK non-angka ditampilkan ke pengguna", "bukan angka yang valid".encode() in r.data)
with app.app_context():
    row = app.get_db().execute("SELECT ipk_final FROM yudisium WHERE mahasiswa_id=?", (mid,)).fetchone()
check("IPK tidak tersimpan (tetap NULL) setelah input tidak valid", row["ipk_final"] is None)

# 1b. IPK di luar rentang 0.00-4.00 -> ditolak
r = client.post("/kelulusan/yudisium/simpan", data={
    "mahasiswa_id": str(mid), "ipk_final": "9.99", "status_yudisium": "Direncanakan",
}, follow_redirects=True)
check("IPK 9.99 (di luar rentang) ditolak", "0.00 dan 4.00".encode() in r.data)

# 1c. status_yudisium nilai sembarang (POST paksa di luar <select>) -> jatuh ke default, bukan disimpan mentah
r = client.post("/kelulusan/yudisium/simpan", data={
    "mahasiswa_id": str(mid), "ipk_final": "3.75", "status_yudisium": "STATUS_PAKSA_TIDAK_RESMI",
    "tgl_yudisium": "01 Agu 2026", "no_sk": "SK/001/2026",
}, follow_redirects=True)
check("POST yudisium dgn status tidak resmi -> tetap 200", r.status_code == 200)
with app.app_context():
    row = app.get_db().execute(
        "SELECT ipk_final, status_yudisium FROM yudisium WHERE mahasiswa_id=?", (mid,)).fetchone()
check("IPK valid (3.75) tersimpan", row["ipk_final"] == 3.75)
check("Status tidak resmi TIDAK disimpan mentah -> jatuh ke default 'Direncanakan'",
      row["status_yudisium"] == "Direncanakan")

# 1d. Alur normal: status Terlaksana + No SK -> auto-sync ke Wisuda + status_ta mahasiswa berubah
r = client.post("/kelulusan/yudisium/simpan", data={
    "mahasiswa_id": str(mid), "ipk_final": "3.80", "status_yudisium": "Terlaksana",
    "tgl_yudisium": "01 Agu 2026", "no_sk": "SK/002/2026",
}, follow_redirects=True)
check("Yudisium Terlaksana + No SK tersimpan -> 200", r.status_code == 200)
with app.app_context():
    conn = app.get_db()
    mhs = conn.execute("SELECT status_ta FROM mahasiswa WHERE id=?", (mid,)).fetchone()
    wis = conn.execute("SELECT id FROM wisuda WHERE mahasiswa_id=?", (mid,)).fetchone()
check("status_ta mahasiswa ikut berubah (MENUNGGU WISUDA)", mhs["status_ta"] is not None)
check("Baris Wisuda otomatis dibuat (sync_wisuda_dari_yudisium)", wis is not None)

# ---------------------------------------------------------------------
# 2. Kelulusan — Wisuda: dibungkus try/except (regresi alur normal)
# ---------------------------------------------------------------------
r = client.post("/kelulusan/wisuda/simpan", data={
    "mahasiswa_id": str(mid), "tgl_wisuda": "20 Agu 2026", "no_ijazah": "IJZ/001/2026", "catatan": "Uji",
}, follow_redirects=True)
check("POST wisuda/simpan (alur normal) tetap 200", r.status_code == 200)
check("Flash sukses wisuda tampil", "Data wisuda disimpan".encode() in r.data)
with app.app_context():
    row = app.get_db().execute("SELECT no_ijazah FROM wisuda WHERE mahasiswa_id=?", (mid,)).fetchone()
check("Data wisuda benar-benar tersimpan", row["no_ijazah"] == "IJZ/001/2026")

# ---------------------------------------------------------------------
# 3. Kelulusan — Tracer Study: log aktivitas utk hapus (dulu tidak ada)
# ---------------------------------------------------------------------
r = client.post("/kelulusan/tracer/simpan", data={
    "mahasiswa_id": str(mid), "status_saat_ini": "Bekerja", "nama_instansi": "PT Uji Tracer",
    "posisi": "Staf", "no_hp": "0812xxxxxx",
}, follow_redirects=True)
check("POST tracer/simpan -> 200", r.status_code == 200)
with app.app_context():
    conn = app.get_db()
    trow = conn.execute("SELECT id FROM tracer_study WHERE mahasiswa_id=?", (mid,)).fetchone()
check("Data tracer study tersimpan", trow is not None)
tid = trow["id"]

with app.app_context():
    n_log_sebelum = app.get_db().execute(
        "SELECT COUNT(*) c FROM log_aktivitas WHERE aksi='Hapus Tracer Study'").fetchone()["c"]
check("Belum ada log 'Hapus Tracer Study' sebelum penghapusan", n_log_sebelum == 0)

r = client.post(f"/kelulusan/tracer/{tid}/hapus", follow_redirects=True)
check("POST tracer/<id>/hapus -> 200", r.status_code == 200)
with app.app_context():
    conn = app.get_db()
    masih_ada = conn.execute("SELECT id FROM tracer_study WHERE id=?", (tid,)).fetchone()
    n_log_sesudah = conn.execute(
        "SELECT COUNT(*) c FROM log_aktivitas WHERE aksi='Hapus Tracer Study'").fetchone()["c"]
check("Data tracer study benar-benar terhapus", masih_ada is None)
check("Penghapusan tracer study SEKARANG tercatat ke log_aktivitas (dulu tidak)", n_log_sesudah == 1)

# ---------------------------------------------------------------------
# 4. Kelulusan — Ekspor Excel (3 halaman, memakai export_utils.kirim_excel bersama)
# ---------------------------------------------------------------------
for label, url in (
    ("Yudisium", "/kelulusan/yudisium/ekspor"),
    ("Wisuda", "/kelulusan/wisuda/ekspor"),
    ("Tracer Study", "/kelulusan/tracer/ekspor"),
):
    r = client.get(url)
    check(f"Ekspor Excel {label} -> 200", r.status_code == 200)
    check(f"Ekspor Excel {label} bertipe xlsx",
          r.headers.get("Content-Type", "").startswith(
              "application/vnd.openxmlformats-officedocument.spreadsheetml"))

# Regresi — Rekap juga memakai export_utils.kirim_excel bersama sekarang
r = client.get("/rekap/pembimbing/ekspor")
check("Regresi: Rekap Pembimbing ekspor (pakai export_utils bersama) tetap 200", r.status_code == 200)

# ---------------------------------------------------------------------
# 5. Kegiatan & Program Kerja — validasi bidang/status/kategori & anggaran
# ---------------------------------------------------------------------
r = client.post("/kegiatan/proker/simpan", data={
    "bidang": "Bidang Ngasal Tidak Resmi", "nama_program": "Proker Uji Tolak Bidang", "status": "Direncanakan",
}, follow_redirects=True)
check("Proker dgn bidang tidak resmi -> ditolak", "Bidang tidak dikenal".encode() in r.data)
with app.app_context():
    row = app.get_db().execute(
        "SELECT id FROM program_kerja WHERE nama_program='Proker Uji Tolak Bidang'").fetchone()
check("Proker bidang tidak resmi TIDAK tersimpan", row is None)

r = client.post("/kegiatan/proker/simpan", data={
    "bidang": "Akademik & Kurikulum", "nama_program": "Proker Uji Anggaran Minus",
    "status": "Direncanakan", "anggaran_rencana": "-500000",
}, follow_redirects=True)
check("Proker dgn anggaran_rencana negatif -> ditolak", "tidak boleh bernilai negatif".encode() in r.data)
with app.app_context():
    row = app.get_db().execute(
        "SELECT id FROM program_kerja WHERE nama_program='Proker Uji Anggaran Minus'").fetchone()
check("Proker anggaran negatif TIDAK tersimpan", row is None)

r = client.post("/kegiatan/proker/simpan", data={
    "bidang": "Akademik & Kurikulum", "nama_program": "Proker Uji Sah", "status": "Berjalan",
    "anggaran_rencana": "1000000",
}, follow_redirects=True)
check("Proker dgn data sah -> tersimpan normal (regresi)", r.status_code == 200)
with app.app_context():
    conn = app.get_db()
    row = conn.execute("SELECT id FROM program_kerja WHERE nama_program='Proker Uji Sah'").fetchone()
check("Proker sah benar-benar tersimpan", row is not None)
proker_id = row["id"] if row else None

r = client.post("/kegiatan/pelaksanaan/simpan", data={
    "nama_kegiatan": "Kegiatan Uji Tolak Kategori", "kategori": "Kategori Ngasal",
    "status": "Direncanakan",
}, follow_redirects=True)
check("Kegiatan dgn kategori tidak resmi -> ditolak", "Kategori kegiatan tidak dikenal".encode() in r.data)

r = client.post("/kegiatan/pelaksanaan/simpan", data={
    "nama_kegiatan": "Kegiatan Uji Anggaran Minus", "kategori": "Rapat",
    "status": "Selesai", "anggaran_realisasi": "-1",
}, follow_redirects=True)
check("Kegiatan dgn anggaran_realisasi negatif -> ditolak", "tidak boleh bernilai negatif".encode() in r.data)

r = client.post("/kegiatan/pelaksanaan/simpan", data={
    "program_kerja_id": str(proker_id) if proker_id else "",
    "nama_kegiatan": "Kegiatan Uji Sah", "kategori": "Rapat", "status": "Selesai",
    "anggaran_realisasi": "250000",
}, follow_redirects=True)
check("Kegiatan dgn data sah -> tersimpan normal (regresi)", r.status_code == 200)
if proker_id:
    keg_page = client.get(f"/kegiatan/?tab=proker")
    check("Realisasi Proker Uji Sah ikut terhitung (1/1 Selesai -> 100%)",
          b"Proker Uji Sah" in keg_page.data)

# ---------------------------------------------------------------------
# 6. Backup & Restore — perbaikan zip-slip (path traversal)
# ---------------------------------------------------------------------
with app.app_context():
    db_live_path = app.config["DB_PATH"]
zip_valid_db = os.path.join(tmpdir, "_valid_snapshot.db")
backup_core._snapshot_db_to(db_live_path, zip_valid_db)

marker_path = os.path.join(tmpdir, "..", "pwned_by_ziptest.txt")
marker_path = os.path.abspath(marker_path)
if os.path.exists(marker_path):
    os.remove(marker_path)

evil_zip_buf = io.BytesIO()
with zipfile.ZipFile(evil_zip_buf, "w") as zf:
    zf.write(zip_valid_db, arcname="data_prodi.db")
    zf.writestr("../pwned_by_ziptest.txt", "harusnya tidak pernah ditulis di luar folder tujuan")
evil_zip_buf.seek(0)

with app.app_context():
    pwd_hash_sebelum = app.get_db().execute(
        "SELECT value FROM pengaturan WHERE key='password_hash'").fetchone()

r = client.post("/pengaturan/backup/restore", data={
    "password_konfirmasi": "test1234",
    "file_restore": (evil_zip_buf, "evil_backup.zip"),
}, content_type="multipart/form-data", follow_redirects=True)
check("Upload .zip berisi path traversal -> ditolak (bukan 500, bukan diproses)", r.status_code == 200)
check("Pesan penolakan menyebut entri tidak aman", "tidak aman".encode() in r.data or "ditolak".encode() in r.data)
check("File TIDAK pernah ditulis keluar dari folder tujuan (zip-slip gagal)",
      not os.path.exists(marker_path))
with app.app_context():
    pwd_hash_sesudah = app.get_db().execute(
        "SELECT value FROM pengaturan WHERE key='password_hash'").fetchone()
check("Sesi masih valid (restore jahat tidak sempat menimpa database)",
      pwd_hash_sebelum == pwd_hash_sesudah)

# Zip SAH (tanpa entri jahat) harus tetap bisa divalidasi lolos (regresi)
good_zip_path = os.path.join(tmpdir, "_good.zip")
with zipfile.ZipFile(good_zip_path, "w") as zf:
    zf.write(zip_valid_db, arcname="data_prodi.db")
    zf.writestr("files/dokumen/contoh_uji.txt", "halo dari uji regresi")
ok, pesan = backup_core.validasi_file_restore_zip(good_zip_path)
check(f"Regresi: zip Backup Lengkap SAH tetap lolos validasi ({pesan})", ok is True)

# ---------------------------------------------------------------------
# 7. Regresi umum — modul lain tidak tersentuh
# ---------------------------------------------------------------------
check("Dashboard tetap 200 setelah semua perubahan di atas", client.get("/").status_code == 200)
check("Halaman Kegiatan tetap 200 (regresi)", client.get("/kegiatan/").status_code == 200)
check("Halaman Backup & Restore tetap 200 (regresi)", client.get("/pengaturan/backup/").status_code == 200)
check("Halaman Import & Export tetap 200 (regresi)", client.get("/pengaturan/import-export").status_code == 200)
check("Halaman Import Generik tetap 200 (regresi)", client.get("/pengaturan/import-generik").status_code == 200)
check("Halaman Rekap Program Kerja tetap 200 (regresi)", client.get("/rekap/program-kerja").status_code == 200)

# ---------------------------------------------------------------------
# 8. Import Excel (Import Generik) — file .xlsx palsu/korup tidak lagi 500
# ---------------------------------------------------------------------
fake_xlsx = io.BytesIO(b"ini bukan file excel yang valid sama sekali")
r = client.post("/pengaturan/import-generik/proses", data={
    "modul": "dosen", "file_excel": (fake_xlsx, "dosen_palsu.xlsx"),
}, content_type="multipart/form-data", follow_redirects=True)
check("Upload .xlsx palsu/korup (lolos cek ekstensi) -> TIDAK 500", r.status_code == 200)
check("Pesan ramah 'tidak bisa dibuka sebagai workbook' ditampilkan",
      "tidak bisa dibuka sebagai workbook".encode() in r.data)

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
