import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402
from app import db as _db  # noqa: E402

db_path = os.path.join(tmpdir, "test.db")
app = create_app(db_path=db_path)
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False

client = app.test_client()

client.get("/login")
client.post("/login", data={"username": "kaprodi", "password1": "test1234", "password2": "test1234"}, follow_redirects=True)

with app.test_request_context():
    conn = app.get_db()
    ta_id, periode_ids = _db.buka_tahun_ajaran(conn, "2025/2026", aktifkan="Ganjil")
    periode_id = periode_ids["Ganjil"]
    conn.commit()

    # kurikulum aktif + mata kuliah + dosen + ruangan
    conn.execute("INSERT INTO kurikulum_versi(nama, tahun_berlaku, status) VALUES('Kur A','2025','Aktif')")
    kur_id = conn.execute("SELECT id FROM kurikulum_versi WHERE nama='Kur A'").fetchone()["id"]
    conn.execute("INSERT INTO mata_kuliah(kurikulum_id, kode, nama, sks, semester) VALUES(?,?,?,?,?)",
                 (kur_id, "IF101", "Algoritma", 3, 1))
    conn.execute("INSERT INTO mata_kuliah(kurikulum_id, kode, nama, sks, semester) VALUES(?,?,?,?,?)",
                 (kur_id, "IF102", "Basis Data", 3, 1))
    mk1 = conn.execute("SELECT id FROM mata_kuliah WHERE kode='IF101'").fetchone()["id"]
    mk2 = conn.execute("SELECT id FROM mata_kuliah WHERE kode='IF102'").fetchone()["id"]
    conn.execute("INSERT INTO dosen(nama, aktif) VALUES('Dr. Budi', 1)")
    dosen_id = conn.execute("SELECT id FROM dosen WHERE nama='Dr. Budi'").fetchone()["id"]
    conn.execute("INSERT INTO ruangan(nama) VALUES('Lab 1')")
    ruangan_id = conn.execute("SELECT id FROM ruangan WHERE nama='Lab 1'").fetchone()["id"]
    conn.commit()

form_common = {
    "periode_akademik_id": str(periode_id),
    "kelas": "A",
    "dosen_id": str(dosen_id),
    "hari": "Senin",
    "jam_mulai": "08.00",
    "jam_selesai": "10.00",
    "ruangan_id": str(ruangan_id),
    "jumlah_pertemuan_rencana": "16",
}

r1 = client.post("/jadwal/kelas/simpan", data=dict(form_common, mata_kuliah_id=str(mk1)), follow_redirects=True)
print("simpan kelas 1:", r1.status_code)

r2 = client.post("/jadwal/kelas/simpan", data=dict(form_common, mata_kuliah_id=str(mk2)), follow_redirects=True)
print("simpan kelas 2 (bentrok dosen+ruangan+jam identik):", r2.status_code)
bentrok_terdeteksi = "Bentrok Jadwal Terdeteksi" in r2.get_data(as_text=True)
print("Halaman konfirmasi bentrok muncul:", bentrok_terdeteksi)

with app.test_request_context():
    conn = app.get_db()
    n = conn.execute("SELECT COUNT(*) c FROM jadwal_kelas WHERE dosen_id=?", (dosen_id,)).fetchone()["c"]
print(f"Jumlah kelas tersimpan untuk dosen ini (harus 1 = bentrok DICEGAH sebelum konfirmasi): {n}")
assert n == 1, "BUG: bentrok tidak dicegah, kelas kedua langsung tersimpan tanpa konfirmasi"
assert bentrok_terdeteksi, "BUG: halaman konfirmasi bentrok tidak muncul"

# Now confirm anyway (operator sengaja override)
r3 = client.post("/jadwal/kelas/simpan",
                  data=dict(form_common, mata_kuliah_id=str(mk2), konfirmasi_bentrok="1"),
                  follow_redirects=True)
with app.test_request_context():
    conn = app.get_db()
    n2 = conn.execute("SELECT COUNT(*) c FROM jadwal_kelas WHERE dosen_id=?", (dosen_id,)).fetchone()["c"]
print(f"Setelah konfirmasi override, jumlah kelas tersimpan untuk dosen ini (harus 2): {n2}")
assert n2 == 2, "Konfirmasi override seharusnya tetap bisa menyimpan"

print("\n[OK] Semua pengecekan cek_bentrok_kelas lulus.")
