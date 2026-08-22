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

FAILS = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)

client.get("/login")
client.post("/login", data={"username": "kaprodi", "password1": "test1234", "password2": "test1234"}, follow_redirects=True)

conn = _db.connect(db_path)

# ------------------------------------------------------- Buka tahun ajaran
client.post("/pengaturan/tahun-akademik", data={"aksi": "buka_tahun", "kode": "2025/2026", "aktifkan": "Ganjil"})
periode_ganjil = conn.execute(
    "SELECT pa.id FROM periode_akademik pa JOIN tahun_ajaran ta ON ta.id=pa.tahun_ajaran_id "
    "WHERE ta.kode='2025/2026' AND pa.jenis='Ganjil'"
).fetchone()
pid = periode_ganjil["id"]
check("Periode Ganjil 2025/2026 berhasil dibuka", bool(pid))

daftar = _db.get_periode_list(conn)
check("get_periode_list() mengembalikan >=3 periode (Ganjil/Genap/Antara)", len(daftar) >= 3)
check("Label periode berformat 'kode - jenis'", any(d["label"].startswith("2025/2026 -") for d in daftar))

ta_cache, sem_cache = _db.cache_periode(conn, pid)
check("cache_periode() menurunkan tahun_akademik='2025/2026'", ta_cache == "2025/2026")
check("cache_periode() menurunkan semester='Ganjil'", sem_cache == "Ganjil")
check("cache_periode() dgn id kosong -> ('','')", _db.cache_periode(conn, None) == ("", ""))

# ------------------------------------------------------------- Dosen dummy
client.post("/dosen/simpan", data={"nama": "Dr. Periode Test", "nidn": "0011112222", "aktif": "on"})
dosen_id = conn.execute("SELECT id FROM dosen WHERE nidn='0011112222'").fetchone()["id"]

# ---------------------------------------------------------- Modul SDM (6 tab)
sdm_page = client.get(f"/sdm/{dosen_id}?tab=pendidikan")
check("Halaman SDM tab Pendidikan -> 200", sdm_page.status_code == 200)
check("Dropdown Periode Akademik tampil di form SDM", b'name="periode_akademik_id"' in sdm_page.data)
check("Opsi periode 2025/2026 - Ganjil ada di dropdown SDM", b"2025/2026 - Ganjil" in sdm_page.data)

r = client.post(f"/sdm/{dosen_id}/pendidikan/simpan", data={
    "periode_akademik_id": str(pid), "mata_kuliah": "Manajemen Strategi", "sks": "3", "status": "Selesai",
}, follow_redirects=True)
row = conn.execute("SELECT * FROM aktivitas_pendidikan WHERE dosen_id=? AND mata_kuliah='Manajemen Strategi'", (dosen_id,)).fetchone()
check("aktivitas_pendidikan tersimpan", bool(row))
check("aktivitas_pendidikan.periode_akademik_id terisi FK asli (bukan cache doang)", row["periode_akademik_id"] == pid)
check("aktivitas_pendidikan.tahun_akademik ikut ter-cache otomatis", row["tahun_akademik"] == "2025/2026")
check("aktivitas_pendidikan.semester ikut ter-cache otomatis", row["semester"] == "Ganjil")

r = client.post(f"/sdm/{dosen_id}/penelitian/simpan", data={
    "judul": "Riset Uji Periode", "periode_akademik_id": str(pid), "status": "Selesai",
}, follow_redirects=True)
row_pen = conn.execute("SELECT * FROM aktivitas_penelitian WHERE dosen_id=? AND judul='Riset Uji Periode'", (dosen_id,)).fetchone()
check("aktivitas_penelitian tersimpan + kode otomatis pakai tahun dari periode", row_pen and row_pen["kode"] == "PEN-2025-001")
check("aktivitas_penelitian.periode_akademik_id terisi", row_pen["periode_akademik_id"] == pid)

r = client.post(f"/sdm/{dosen_id}/luaran/simpan", data={
    "jenis_luaran": "Jurnal Nasional", "judul": "Luaran Uji Periode", "periode_akademik_id": str(pid),
}, follow_redirects=True)
row_lur = conn.execute("SELECT * FROM luaran_dosen WHERE dosen_id=? AND judul='Luaran Uji Periode'", (dosen_id,)).fetchone()
check("luaran_dosen tersimpan dgn periode_akademik_id", row_lur and row_lur["periode_akademik_id"] == pid)

# Edit -> pastikan dropdown ter-preselect
edit_page = client.get(f"/sdm/{dosen_id}?tab=pendidikan&edit={row['id']}")
check("Form edit SDM men-preselect periode yang tersimpan", f'value="{pid}" selected'.encode() in edit_page.data or (f'value="{pid}"'.encode() in edit_page.data and b"selected" in edit_page.data))

# ---------------------------------------------------------- Modul Kegiatan (program_kerja)
keg_page = client.get("/kegiatan/?tab=proker")
check("Dropdown Periode Akademik tampil di form Program Kerja", b'name="periode_akademik_id"' in keg_page.data)
r = client.post("/kegiatan/proker/simpan", data={
    "periode_akademik_id": str(pid), "bidang": "Akademik & Kurikulum", "nama_program": "Program Uji Periode", "status": "Direncanakan",
}, follow_redirects=True)
row_pk = conn.execute("SELECT * FROM program_kerja WHERE nama_program='Program Uji Periode'").fetchone()
check("program_kerja tersimpan dgn periode_akademik_id", row_pk and row_pk["periode_akademik_id"] == pid)
check("program_kerja.tahun_akademik ikut ter-cache", row_pk["tahun_akademik"] == "2025/2026")

# ---------------------------------------------------------------- Modul CQI
cqi_gap = client.get("/cqi/?tab=gap-analysis")
check("Halaman Gap Analysis CQI -> 200", cqi_gap.status_code == 200)
check("Dropdown Periode Akademik tampil di Gap Analysis CQI", b'name="periode_id"' in cqi_gap.data)

# ---------------------------------------------------------------- Modul Mutu (AMI)
mutu_audit = client.get("/mutu/?tab=audit")
check("Dropdown Periode Akademik tampil di form Siklus AMI", b'name="periode_akademik_id"' in mutu_audit.data)
r = client.post("/mutu/audit/siklus/simpan", data={
    "nama": "AMI Uji Periode", "periode_akademik_id": str(pid), "status": "Direncanakan",
}, follow_redirects=True)
row_ami = conn.execute("SELECT * FROM ami_siklus WHERE nama='AMI Uji Periode'").fetchone()
check("ami_siklus tersimpan dgn periode_akademik_id", row_ami and row_ami["periode_akademik_id"] == pid)
check("ami_siklus.tahun_akademik ikut ter-cache", row_ami["tahun_akademik"] == "2025/2026")

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
