import os, sys, tempfile, datetime as dt
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

# ------------------------------------------------- status_reminder(): kosong
check("Belum ada backup -> perlu_reminder True", backup_core.status_reminder()["perlu_reminder"] is True)
check("Belum ada backup -> ada_backup False", backup_core.status_reminder()["ada_backup"] is False)

# ------------------------------------------------- backup baru -> aman dulu
db_path = os.path.join(tmpdir, "test.db")
app = create_app(db_path=db_path)
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False
client = app.test_client()
client.post("/login", data={"username": "kaprodi", "password1": "test1234", "password2": "test1234"}, follow_redirects=True)

r = client.post("/pengaturan/backup/sekarang", follow_redirects=True)
check("Backup Sekarang -> 200", r.status_code == 200)

status_baru = backup_core.status_reminder()
check("Setelah backup baru -> perlu_reminder False", status_baru["perlu_reminder"] is False)
check("Setelah backup baru -> hari_sejak_terakhir == 0", status_baru["hari_sejak_terakhir"] == 0)

dash = client.get("/")
check("Dashboard TIDAK menampilkan reminder backup basi (baru saja backup)",
      b"tidak diperbarui" not in dash.data and b"Belum pernah backup" not in dash.data)

# --------------------------------------------- simulasikan backup basi (>7 hari)
backup_dir = backup_core.get_backup_dir()
lama_path = os.path.join(backup_dir, "backup_20200101_000000.db")
with open(lama_path, "wb") as fh:
    fh.write(b"SQLite format 3\x00" + b"\x00" * 100)
lama_ts = (dt.datetime.now() - dt.timedelta(days=400)).timestamp()
os.utime(lama_path, (lama_ts, lama_ts))
# hapus backup yang baru dibuat supaya file lama ini jadi satu-satunya/terbaru
for f in os.listdir(backup_dir):
    if f != "backup_20200101_000000.db":
        os.remove(os.path.join(backup_dir, f))

status_basi = backup_core.status_reminder()
check("Backup 400 hari lalu -> perlu_reminder True", status_basi["perlu_reminder"] is True)
check("Backup 400 hari lalu -> hari_sejak_terakhir >= 399", status_basi["hari_sejak_terakhir"] >= 399)

dash2 = client.get("/")
check("Dashboard MENAMPILKAN reminder backup basi lewat notifikasi UI",
      b"tidak diperbarui" in dash2.data)
check("Badge level 'danger'/'warning' tampil (bukan default polos)",
      b'class="badge warn"' in dash2.data or b'class="badge danger"' in dash2.data)

# --------------------------------------------- retensi otomatis saat app start
# Simulasikan 5 file backup lama (>30 hari, retensi default) + pastikan
# bersihkan_backup_lama() terpanggil otomatis saat create_app() (bukan cuma
# manual lewat tombol Backup Sekarang).
for i in range(5):
    p = os.path.join(backup_dir, f"backup_2020010{i}_000000.db")
    with open(p, "wb") as fh:
        fh.write(b"SQLite format 3\x00" + b"\x00" * 100)
    ts = (dt.datetime.now() - dt.timedelta(days=500 - i)).timestamp()
    os.utime(p, (ts, ts))
jumlah_sebelum = len(backup_core.list_backups())
check(f"Disiapkan {jumlah_sebelum} file backup lama utk uji retensi otomatis", jumlah_sebelum >= 5)

# create_app() TANPA TESTING=True -> retensi otomatis harus berjalan sekali
# di awal (lihat app/__init__.py: "if not app.config.get('TESTING')")
app2 = create_app(db_path=db_path)  # TESTING sengaja TIDAK diset -> jalur produksi
jumlah_sesudah = len(backup_core.list_backups())
check("Retensi otomatis berjalan sendiri saat app start (tanpa klik manual) -> jumlah backup lama berkurang",
      jumlah_sesudah < jumlah_sebelum)
check("Retensi tetap menyisakan minimal 3 file (safety-net)", jumlah_sesudah >= 3)

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
