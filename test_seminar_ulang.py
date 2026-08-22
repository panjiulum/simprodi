import os, sys, tempfile, sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402
from app import db as _db  # noqa: E402
from app import logic as L  # noqa: E402

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
    conn.execute("INSERT INTO tahap_pengajuan(periode_akademik_id, urutan, nama) VALUES(?,1,'Tahap 1 2025/2026')", (periode_id,))
    conn.execute("INSERT INTO tahap_pengajuan(periode_akademik_id, urutan, nama) VALUES(?,2,'Tahap 2 2025/2026')", (periode_id,))
    conn.execute("INSERT INTO dosen(nama, aktif) VALUES('Dr. Andi', 1)")
    conn.execute("INSERT INTO dosen(nama, aktif) VALUES('Dr. Budi', 1)")
    conn.execute("INSERT INTO mahasiswa(nim, nama) VALUES('001','Mhs Ulang')")
    conn.commit()
    da = conn.execute("SELECT id FROM dosen WHERE nama='Dr. Andi'").fetchone()["id"]
    dbud = conn.execute("SELECT id FROM dosen WHERE nama='Dr. Budi'").fetchone()["id"]
    m1 = conn.execute("SELECT id FROM mahasiswa WHERE nim='001'").fetchone()["id"]
    conn.execute(
        "INSERT INTO penetapan_pembimbing(mahasiswa_id, tahap, pembimbing1_id) VALUES(?,?,?)",
        (m1, "Tahap 1 2025/2026", da),
    )
    conn.commit()

# --- Tes 0: skema tabel seminar TIDAK lagi punya UNIQUE pada mahasiswa_id ---
raw = sqlite3.connect(db_path)
sql = raw.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='seminar'").fetchone()[0]
raw.close()
print("Skema seminar:", sql.replace("\n", " "))
assert "UNIQUE" not in sql, "GAGAL: constraint UNIQUE masih ada di tabel seminar setelah migrasi"
print("LULUS Tes 0: constraint UNIQUE pada seminar.mahasiswa_id sudah diangkat (migrasi rebuild berhasil).")

print("\n=== Seminar PERTAMA mhs Mhs Ulang di Tahap 1, status Batal (proposal ditolak) ===")
r = client.post(
    "/pelaksanaan/seminar/simpan",
    data={
        "mahasiswa_id": str(m1),
        "periode_akademik_id": str(periode_id),
        "tahap": "Tahap 1 2025/2026",
        "status": "Batal",
        "penguji_ketua_id": str(da),
    },
    follow_redirects=True,
)
print("status:", r.status_code)
body = r.get_data(as_text=True)
assert "Data seminar disimpan" in body
print("LULUS Tes 1: baris seminar PERTAMA (Batal) berhasil disimpan tanpa error UNIQUE.")

print("\n=== Seminar ULANG mhs yang SAMA di Tahap 2, status Selesai ===")
r = client.post(
    "/pelaksanaan/seminar/simpan",
    data={
        "mahasiswa_id": str(m1),
        "periode_akademik_id": str(periode_id),
        "tahap": "Tahap 2 2025/2026",
        "status": "Selesai",
        "penguji_ketua_id": str(dbud),
    },
    follow_redirects=True,
)
print("status:", r.status_code)
body = r.get_data(as_text=True)
assert r.status_code == 200
assert "sudah punya data seminar" not in body.lower(), "GAGAL: masih menampilkan pesan error duplikat lama"
print("LULUS Tes 2: baris seminar KEDUA (seminar ulang) untuk mahasiswa yang SAMA berhasil disimpan (tidak diblokir).")

with app.test_request_context():
    conn = app.get_db()
    rows = conn.execute("SELECT tahap, status FROM seminar WHERE mahasiswa_id=? ORDER BY id", (m1,)).fetchall()
    print("Baris seminar mhs Mhs Ulang:", [dict(r) for r in rows])
    assert len(rows) == 2, "GAGAL: harus ada 2 baris seminar (seminar ulang)"

    # --- Tes 3: status_seminar_mahasiswa() pakai 'Selesai-priority' ---
    status = L.status_seminar_mahasiswa(conn, m1)
    print("Status seminar keseluruhan mahasiswa (harus 'Selesai' walau baris pertama 'Batal'):", status)
    assert status == "Selesai", f"GAGAL: status harus 'Selesai', dapat {status}"
    print("LULUS Tes 3: status_seminar_mahasiswa() pakai logika Selesai-priority (bukan baris pertama/terakhir naif).")

    # --- Tes 4: versi batch mengembalikan hasil yang SAMA ---
    batch = L._status_seminar_batch(conn, [m1])
    assert batch[m1] == "Selesai", f"GAGAL: _status_seminar_batch harus 'Selesai', dapat {batch}"
    print("LULUS Tes 4: _status_seminar_batch() konsisten dengan versi non-batch.")

    # --- Tes 5: honor HANYA dihitung dari baris yang 'Selesai' (bukan yg 'Batal') ---
    honor_t1 = L.rkp_seminar(conn, "Tahap 1 2025/2026")  # baris Batal -> tidak menghasilkan honor
    honor_t2 = L.rkp_seminar(conn, "Tahap 2 2025/2026")  # baris Selesai -> menghasilkan honor utk Dr. Budi
    print("Honor seminar Tahap 1 (baris Batal, harus KOSONG):", honor_t1)
    print("Honor seminar Tahap 2 (baris Selesai, harus Dr. Budi):", honor_t2)
    assert honor_t1 == [], "GAGAL: baris seminar 'Batal' tidak boleh menghasilkan honor"
    assert len(honor_t2) == 1 and honor_t2[0]["nama"] == "Dr. Budi"
    print("LULUS Tes 5: honor seminar ulang dihitung per BARIS (hanya yang 'Selesai'), tidak tercampur/duplikat salah.")

# --- Tes 6: halaman list menampilkan KEDUA baris seminar mahasiswa yang sama ---
r = client.get("/pelaksanaan/seminar?tahap=Semua")
tbody = r.get_data(as_text=True).split("<tbody>", 1)[1].split("</tbody>", 1)[0]
jumlah_baris = tbody.count("Mhs Ulang")
print("Jumlah baris 'Mhs Ulang' tampil di tabel (harus 2):", jumlah_baris)
assert jumlah_baris == 2, "GAGAL: kedua baris seminar ulang harus tampil di tabel"
print("LULUS Tes 6: halaman /pelaksanaan/seminar menampilkan kedua baris seminar (bukan menimpa satu sama lain).")

print("\nSEMUA TES SEMINAR ULANG LULUS.")
