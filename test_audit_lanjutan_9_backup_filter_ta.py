# -*- coding: utf-8 -*-
"""
test_audit_lanjutan_9_backup_filter_ta.py — Uji Pengembangan Lanjutan 9:
Filter Backup per Tahun Akademik.

Setiap backup (.db cepat maupun .zip lengkap) sekarang ditandai kode tahun
ajaran yang periode-nya berstatus 'Berjalan' saat backup itu dibuat:
  - .db: tag dibaca LANGSUNG dari isi file itu sendiri tiap kali daftar
    riwayat ditampilkan (`backup_core._tag_db_dari_file`) — tidak pernah
    basi karena file .db memang snapshot utuh yang tak berubah lagi.
  - .zip: tag disimpan di `manifest.json` SAAT backup dibuat
    (`backup_core.backup_now_full`), dibaca dari situ
    (`backup_core._tag_zip_dari_manifest`) — bukan buka ulang database di
    dalam arsip tiap render halaman. Backup .zip LAMA (sebelum fitur ini
    ada, manifest tanpa kunci "tahun_akademik") otomatis masuk kategori
    "Tidak diketahui", bukan error.

Ditambahkan `backup_core.list_backups(tahun_akademik=...)`,
`list_tahun_akademik_backup()`, route `/pengaturan/backup?tahun_akademik=`,
dan dropdown filter + kolom "Tahun Akademik" di `backup.html`.

Tidak diikutkan di paket produksi (murni verifikasi pengembangan).
"""
import json
import os
import sqlite3
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402
from app import backup_core  # noqa: E402
from app import db as _db  # noqa: E402

db_path = os.path.join(tmpdir, "test.db")
app = create_app(db_path=db_path)
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False
client = app.test_client()
client.post("/login", data={"username": "kaprodi", "password1": "test1234", "password2": "test1234"},
            follow_redirects=True)

FAILS = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)

backup_dir = backup_core.get_backup_dir()

# ---------------------------------------------------------------------
# 1. Kondisi "belum ada periode aktif": create_app() sendiri sudah
#    otomatis membuat 1 tahun ajaran default lewat migrasi satu-kali
#    (_migrate_tahun_ajaran_lama, dari setting lama tahun_akademik_aktif)
#    supaya instalasi lama tidak kehilangan alur kerja — jadi untuk
#    menguji kondisi "genuinely belum ada periode Berjalan", tabelnya
#    dikosongkan dulu secara eksplisit di sini (bukan skenario yang bisa
#    dicapai lewat create_app() polos).
# ---------------------------------------------------------------------
conn = _db.connect(db_path)
conn.execute("DELETE FROM periode_akademik")
conn.execute("DELETE FROM tahun_ajaran")
conn.commit()

p_kosong = backup_core.backup_now(db_path)
tag_kosong = backup_core._tag_db_dari_file(p_kosong)
check("Backup tanpa periode Berjalan sama sekali -> tag '(Belum ada periode aktif)'",
      tag_kosong == backup_core.TAG_TIDAK_ADA_PERIODE_AKTIF)

# ---------------------------------------------------------------------
# 2. Buka tahun ajaran 2025/2026 (Ganjil Berjalan) -> backup .db & .zip
#    keduanya harus tertandai "2025/2026".
# ---------------------------------------------------------------------
ta1_id, per1 = _db.buka_tahun_ajaran(conn, "2025/2026", aktifkan="Ganjil")

p_db_2025 = backup_core.backup_now(db_path)
p_zip_2025 = backup_core.backup_now_full(db_path)

check("Backup .db saat 2025/2026 Berjalan -> tag '2025/2026'",
      backup_core._tag_db_dari_file(p_db_2025) == "2025/2026")
check("Backup .zip saat 2025/2026 Berjalan -> tag '2025/2026'",
      backup_core._tag_zip_dari_manifest(p_zip_2025) == "2025/2026")
manifest_2025 = backup_core.baca_manifest(p_zip_2025)
check("manifest.json backup .zip menyimpan kunci 'tahun_akademik'",
      manifest_2025 is not None and manifest_2025.get("tahun_akademik") == "2025/2026")

# ---------------------------------------------------------------------
# 3. Transisi ke tahun ajaran 2026/2027 (Ganjil Berjalan), 2025/2026
#    diarsipkan (Draft) -> backup baru harus tertandai "2026/2027", BUKAN
#    ikut menandai ulang backup 2025/2026 yang sudah ada (sudah snapshot).
# ---------------------------------------------------------------------
conn.execute("UPDATE periode_akademik SET status='Draft' WHERE id=?", (per1["Ganjil"],))
ta2_id, per2 = _db.buka_tahun_ajaran(conn, "2026/2027", aktifkan="Ganjil")
conn.commit()

p_db_2026 = backup_core.backup_now(db_path)
p_zip_2026 = backup_core.backup_now_full(db_path)

check("Backup .db saat 2026/2027 Berjalan -> tag '2026/2027'",
      backup_core._tag_db_dari_file(p_db_2026) == "2026/2027")
check("Backup .zip saat 2026/2027 Berjalan -> tag '2026/2027'",
      backup_core._tag_zip_dari_manifest(p_zip_2026) == "2026/2027")
check("Backup 2025/2026 yang lama TIDAK ikut berubah tag-nya (snapshot, bukan live)",
      backup_core._tag_db_dari_file(p_db_2025) == "2025/2026")

# ---------------------------------------------------------------------
# 4. Backup .zip & .db "lama" (simulasi sebelum fitur tag ini ada) ->
#    harus masuk "Tidak diketahui", BUKAN dianggap error / bikin daftar
#    riwayat gagal tampil.
# ---------------------------------------------------------------------
legacy_db_path = os.path.join(backup_dir, "backup_legacy_00000000_000000_000000.db")
raw = sqlite3.connect(legacy_db_path)
raw.execute("CREATE TABLE dummy(id INTEGER)")  # skema tanpa tahun_ajaran/periode_akademik
raw.commit()
raw.close()
check("Backup .db legacy (skema tidak dikenal) -> tag 'Tidak diketahui'",
      backup_core._tag_db_dari_file(legacy_db_path) == backup_core.TAG_TIDAK_DIKETAHUI)

legacy_zip_path = os.path.join(backup_dir, "backup_legacy_lengkap_00000000_000000_000000.zip")
with zipfile.ZipFile(legacy_zip_path, "w") as zf:
    zf.writestr(backup_core.DB_ARCNAME, b"isi tidak relevan untuk uji tag")
    # manifest TANPA kunci "tahun_akademik" -> format lama
    zf.writestr(backup_core.MANIFEST_NAME, json.dumps({"format": "simprodi-backup-lengkap", "versi": 1}))
check("Backup .zip legacy (manifest tanpa kunci tahun_akademik) -> tag 'Tidak diketahui'",
      backup_core._tag_zip_dari_manifest(legacy_zip_path) == backup_core.TAG_TIDAK_DIKETAHUI)

# ---------------------------------------------------------------------
# 5. list_backups(tahun_akademik=...) -> filter tepat, tidak tercampur.
# ---------------------------------------------------------------------
semua = backup_core.list_backups(dengan_tag=True)
check("Total backup yang disiapkan (2 tak-bertahun + 2x2025/2026 + 2x2026/2027 + 2 legacy)",
      len(semua) == 7)

hasil_2025 = backup_core.list_backups(tahun_akademik="2025/2026")
check("Filter '2025/2026' -> tepat 2 file (.db + .zip)", len(hasil_2025) == 2)
check("Filter '2025/2026' -> tidak menyertakan file 2026/2027",
      all("2026" not in b["nama"].replace("2026/2027", "") or True for b in hasil_2025) and
      p_db_2026 not in [b["path"] for b in hasil_2025] and p_zip_2026 not in [b["path"] for b in hasil_2025])

hasil_2026 = backup_core.list_backups(tahun_akademik="2026/2027")
check("Filter '2026/2027' -> tepat 2 file (.db + .zip)", len(hasil_2026) == 2)

hasil_tanpa_ta = backup_core.list_backups(tahun_akademik=backup_core.TAG_TIDAK_ADA_PERIODE_AKTIF)
check("Filter '(Belum ada periode aktif)' -> tepat 1 file", len(hasil_tanpa_ta) == 1)

hasil_tidak_diketahui = backup_core.list_backups(tahun_akademik=backup_core.TAG_TIDAK_DIKETAHUI)
check("Filter 'Tidak diketahui' -> tepat 2 file (legacy .db + .zip)", len(hasil_tidak_diketahui) == 2)

# ---------------------------------------------------------------------
# 6. list_tahun_akademik_backup() -> kode asli terbaru dulu, label khusus
#    di akhir.
# ---------------------------------------------------------------------
opsi = backup_core.list_tahun_akademik_backup()
check("Opsi dropdown: kode asli terbaru dulu, label khusus di akhir",
      opsi == ["2026/2027", "2025/2026", backup_core.TAG_TIDAK_ADA_PERIODE_AKTIF,
               backup_core.TAG_TIDAK_DIKETAHUI])

# ---------------------------------------------------------------------
# 7. status_reminder()/bersihkan_backup_lama() (jalur lama, dipanggil tiap
#    page load lewat notifikasi) TETAP jalan tanpa perlu baca tag sama
#    sekali -> tidak boleh error walau backup legacy ada di folder.
# ---------------------------------------------------------------------
try:
    status = backup_core.status_reminder()
    ok_reminder = status["ada_backup"] is True
except Exception as e:
    ok_reminder = False
    print("  (error:", e, ")")
check("status_reminder() tetap jalan normal (tidak butuh baca tag)", ok_reminder)

# ---------------------------------------------------------------------
# 8. Route HTTP: dropdown & kolom tampil, filter query-string bekerja.
# ---------------------------------------------------------------------
r_index = client.get("/pengaturan/backup/")
check("GET /pengaturan/backup -> 200", r_index.status_code == 200)
check("Kolom 'Tahun Akademik' tampil di tabel riwayat", "Tahun Akademik".encode() in r_index.data)
check("Dropdown filter berisi opsi '2025/2026' & '2026/2027'",
      b'value="2025/2026"' in r_index.data and b'value="2026/2027"' in r_index.data)

nama_db_2025 = os.path.basename(p_db_2025)
nama_db_2026 = os.path.basename(p_db_2026)

r_filter_2025 = client.get("/pengaturan/backup/?tahun_akademik=2025%2F2026")
check("GET ?tahun_akademik=2025/2026 -> 200", r_filter_2025.status_code == 200)
check("Hasil filter menampilkan file 2025/2026", nama_db_2025.encode() in r_filter_2025.data)
check("Hasil filter TIDAK menampilkan file 2026/2027", nama_db_2026.encode() not in r_filter_2025.data)

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
