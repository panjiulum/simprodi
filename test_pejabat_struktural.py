import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402

db_path = os.path.join(tmpdir, "test.db")
app = create_app(db_path=db_path)
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False
client = app.test_client()

FAILS = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)

client.post("/login", data={"username": "kaprodi", "password1": "test1234", "password2": "test1234"}, follow_redirects=True)

# ---------------------------------------------------------------------
# 1. Halaman kosong -> form tambah tampil, belum ada penandatangan default
# ---------------------------------------------------------------------
r_empty = client.get("/pengaturan/pejabat")
check("Halaman Pejabat Struktural -> 200", r_empty.status_code == 200)
check("Belum ada data -> pesan kosong tampil", "Belum ada data pejabat struktural".encode() in r_empty.data)
check("Menu Pejabat Struktural muncul di sidebar", b"Pejabat Struktural" in r_empty.data)

# ---------------------------------------------------------------------
# 2. Tambah Rektor, Dekan, dan Kaprodi
# ---------------------------------------------------------------------
def tambah(jabatan, nama, unit="", nip_nidn="", urutan=0):
    return client.post(
        "/pengaturan/pejabat/simpan",
        data={
            "jabatan": jabatan,
            "nama": nama,
            "unit": unit,
            "nip_nidn": nip_nidn,
            "no_sk_pengangkatan": "",
            "tmt": "",
            "masa_akhir": "",
            "urutan": str(urutan),
            "aktif": "on",
        },
        follow_redirects=True,
    )

r1 = tambah("Rektor", "Prof. Dr. Rektor Contoh, M.Pd.", nip_nidn="196501011990031001", urutan=0)
check("Tambah Rektor -> 200", r1.status_code == 200)
check("Pesan sukses tambah Rektor tampil", "ditambahkan".encode() in r1.data)

r2 = tambah("Dekan", "Dr. Dekan Contoh, M.Si.", unit="Fakultas Administrasi", nip_nidn="197001011995031002", urutan=1)
check("Tambah Dekan -> 200", r2.status_code == 200)

r3 = tambah(
    "Ketua Program Studi (Kaprodi)",
    "Dr. Kaprodi Contoh, M.Kom.",
    unit="S1 Ilmu Administrasi Bisnis",
    nip_nidn="1012345601",
    urutan=2,
)
check("Tambah Kaprodi -> 200", r3.status_code == 200)

with app.test_request_context():
    conn = app.get_db()
    rows = conn.execute("SELECT * FROM pejabat_struktural ORDER BY urutan").fetchall()
check("3 pejabat tersimpan di database", len(rows) == 3)
check("Urutan tampil sesuai (Rektor paling atas)", rows[0]["jabatan"] == "Rektor")

r_list = client.get("/pengaturan/pejabat")
check("Nama Rektor tampil di daftar", "Prof. Dr. Rektor Contoh, M.Pd.".encode() in r_list.data)
check("Nama Dekan tampil di daftar", "Dr. Dekan Contoh, M.Si.".encode() in r_list.data)
check("Nama Kaprodi tampil di daftar", "Dr. Kaprodi Contoh, M.Kom.".encode() in r_list.data)

# ---------------------------------------------------------------------
# 3. Wajib isi jabatan & nama
# ---------------------------------------------------------------------
r_kosong = client.post(
    "/pengaturan/pejabat/simpan",
    data={"jabatan": "", "nama": "", "aktif": "on"},
    follow_redirects=True,
)
check("Jabatan/Nama kosong ditolak", "wajib diisi".encode() in r_kosong.data)
with app.test_request_context():
    conn = app.get_db()
    n = conn.execute("SELECT COUNT(*) c FROM pejabat_struktural").fetchone()["c"]
check("Data kosong TIDAK tersimpan", n == 3)

# ---------------------------------------------------------------------
# 4. "Jadikan Default Penandatangan" -> sinkron ke setting lama, dan
#    dipakai otomatis di blok tanda tangan SK Tugas Akhir (surat.py).
# ---------------------------------------------------------------------
with app.test_request_context():
    conn = app.get_db()
    kaprodi_id = conn.execute(
        "SELECT id FROM pejabat_struktural WHERE nama='Dr. Kaprodi Contoh, M.Kom.'"
    ).fetchone()["id"]

r_default = client.post(
    f"/pengaturan/pejabat/{kaprodi_id}/jadikan-default", follow_redirects=True
)
check("Jadikan default -> 200", r_default.status_code == 200)
check("Pesan sukses jadikan default tampil", "penandatangan default".encode() in r_default.data)

with app.test_request_context():
    conn = app.get_db()
    from app import db as _db
    nama_setting = _db.get_setting(conn, "nama_penandatangan_default", "")
    jabatan_setting = _db.get_setting(conn, "jabatan_penandatangan_default", "")
    nip_setting = _db.get_setting(conn, "nip_nidn_penandatangan_default", "")
check("Setting nama_penandatangan_default tersinkron", nama_setting == "Dr. Kaprodi Contoh, M.Kom.")
check("Setting jabatan_penandatangan_default tersinkron", jabatan_setting == "Ketua Program Studi (Kaprodi)")
check("Setting NIP/NIDN tersinkron", nip_setting == "1012345601")

r_halaman = client.get("/pengaturan/pejabat")
check(
    "Kartu 'penandatangan default saat ini' tampil di halaman",
    "penandatangan default saat ini".encode() in r_halaman.data.lower() or b"Dr. Kaprodi Contoh" in r_halaman.data,
)

# ---------------------------------------------------------------------
# 5. Buat mahasiswa + penetapan pembimbing minimal, lalu cetak SK
#    Pembimbing -> nama & NIP/NIDN Kaprodi HARUS ikut tercetak (bug lama:
#    _footer_ttd selalu kosong & hardcode "Ketua Program Studi").
# ---------------------------------------------------------------------
with app.test_request_context():
    conn = app.get_db()
    conn.execute("INSERT INTO mahasiswa(nim, nama) VALUES('2023010001','Contoh Mahasiswa')")
    conn.execute("INSERT INTO dosen(nama, aktif) VALUES('Dr. Pembimbing Satu', 1)")
    mid = conn.execute("SELECT id FROM mahasiswa WHERE nim='2023010001'").fetchone()["id"]
    did = conn.execute("SELECT id FROM dosen WHERE nama='Dr. Pembimbing Satu'").fetchone()["id"]
    conn.execute(
        "INSERT INTO penetapan_pembimbing(mahasiswa_id, semester, tahap, judul_final, "
        "pembimbing1_id, tgl_penetapan, no_sk) VALUES(?,?,?,?,?,?,?)",
        (mid, "Ganjil 2025/2026", "Tahap 1", "Judul Contoh", did, "2025-09-01", "001/SK/2025"),
    )
    conn.commit()

r_sk = client.post(
    "/surat/buat",
    data={"mahasiswa_id": str(mid), "jenis": "SK Pembimbing"},
    follow_redirects=True,
)
check("Cetak SK Pembimbing -> 200", r_sk.status_code == 200)

import docx, io as _io
doc = docx.Document(_io.BytesIO(r_sk.data))
teks = "\n".join(p.text for p in doc.paragraphs)
check("Nama Kaprodi (default penandatangan) tercetak di SK", "Dr. Kaprodi Contoh, M.Kom." in teks)
check("Jabatan Kaprodi tercetak di SK (bukan hardcode lama)", "Ketua Program Studi (Kaprodi)," in teks)
check("NIP/NIDN Kaprodi ikut tercetak di SK", "1012345601" in teks)

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
