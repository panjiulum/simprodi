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
# 1. Form Data Dosen menampilkan field NIK & NUPTK, TIDAK LAGI field NIP
# ---------------------------------------------------------------------
r_form = client.get("/dosen/")
check("Halaman Data Dosen -> 200", r_form.status_code == 200)
check("Field NIK tampil di form", b'name="nik"' in r_form.data)
check("Field NUPTK tampil di form", b'name="nuptk"' in r_form.data)
check("Field NIP TIDAK LAGI tampil di form (diganti NIK/NUPTK)", b'name="nip"' not in r_form.data)

# ---------------------------------------------------------------------
# 2. Simpan dosen baru dengan NIK & NUPTK valid (16 digit)
# ---------------------------------------------------------------------
r_simpan = client.post(
    "/dosen/simpan",
    data={
        "nidn": "0012345678",
        "nama": "Dr. Contoh Dosen, M.Kom",
        "no_hp": "081234567890",
        "email": "contoh@kampus.ac.id",
        "nik": "3201012345670001",
        "nuptk": "1234567890123456",
        "aktif": "on",
        "status_homebase": "Homebase",
    },
    follow_redirects=True,
)
check("Simpan dosen baru -> 200", r_simpan.status_code == 200)
check("Pesan sukses tambah dosen tampil", "ditambahkan".encode() in r_simpan.data)

with app.test_request_context():
    conn = app.get_db()
    row = conn.execute("SELECT * FROM dosen WHERE nama='Dr. Contoh Dosen, M.Kom'").fetchone()

check("Data dosen tersimpan di database", row is not None)
check("Kolom nik tersimpan dengan benar", row["nik"] == "3201012345670001")
check("Kolom nuptk tersimpan dengan benar", row["nuptk"] == "1234567890123456")

# ---------------------------------------------------------------------
# 3. Kolom nip lama TETAP ADA di skema (data lama tidak hilang) meski
#    tidak lagi dipakai lewat form/import.
# ---------------------------------------------------------------------
with app.test_request_context():
    conn = app.get_db()
    kolom = [c["name"] for c in conn.execute("PRAGMA table_info(dosen)").fetchall()]
check("Kolom nip masih ada di skema (data lama aman)", "nip" in kolom)
check("Kolom nik ada di skema", "nik" in kolom)
check("Kolom nuptk ada di skema", "nuptk" in kolom)

# ---------------------------------------------------------------------
# 4. Validasi lunak: NIK/NUPTK bukan 16 digit tetap TERSIMPAN tapi
#    disertai peringatan (bukan diblokir total).
# ---------------------------------------------------------------------
r_invalid = client.post(
    "/dosen/simpan",
    data={
        "nidn": "0099999999",
        "nama": "Dr. Dosen NIK Pendek",
        "nik": "12345",
        "nuptk": "",
        "aktif": "on",
        "status_homebase": "Homebase",
    },
    follow_redirects=True,
)
check("Peringatan NIK tidak 16 digit tampil", "NIK biasanya 16 digit".encode() in r_invalid.data)
with app.test_request_context():
    conn = app.get_db()
    row2 = conn.execute("SELECT * FROM dosen WHERE nama='Dr. Dosen NIK Pendek'").fetchone()
check("Data tetap tersimpan meski NIK tidak standar (validasi lunak)", row2 is not None and row2["nik"] == "12345")

# ---------------------------------------------------------------------
# 5. Import generik: template & label kolom pakai NIK/NUPTK, bukan NIP
# ---------------------------------------------------------------------
r_template = client.get("/pengaturan/import-generik/template/dosen")
check("Unduh template import Dosen -> 200", r_template.status_code == 200)

import openpyxl, io as _io
wb = openpyxl.load_workbook(_io.BytesIO(r_template.data))
header = [c.value for c in wb.active[1]]
check("Header template mengandung NIK", "NIK" in header)
check("Header template mengandung NUPTK", "NUPTK" in header)
check("Header template TIDAK LAGI mengandung NIP", "NIP" not in header)

# ---------------------------------------------------------------------
# 6. Ekspor Data Dosen menyertakan NIK & NUPTK
# ---------------------------------------------------------------------
r_export = client.get("/pengaturan/export/dosen")
check("Ekspor Data Dosen -> 200", r_export.status_code == 200)
wb2 = openpyxl.load_workbook(_io.BytesIO(r_export.data))
header2 = [c.value for c in wb2.active[1]]
check("Ekspor mengandung kolom NIK", "NIK" in header2)
check("Ekspor mengandung kolom NUPTK", "NUPTK" in header2)

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
