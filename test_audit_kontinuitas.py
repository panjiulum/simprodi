"""Verifikasi 3 perbaikan dari Audit Final Kontinuitas (AUDIT_KONTINUITAS_FINAL.md):
1. hapus_mk (kurikulum.py) ditolak kalau mata kuliah sudah pernah dibuka
   sebagai kelas (mencegah cascade delete jadwal_kelas/bap/krs/nilai_cpmk).
2. hapus_cpl (kurikulum.py) ditolak kalau CPL masih dipakai siklus CQI.
3. hapus_tahap (pengaturan.py) ditolak kalau tahap masih dirujuk data
   mahasiswa (pengajuan_judul/penetapan_pembimbing/seminar/sidang).
Untuk ketiganya: kasus TANPA pemakaian tetap boleh dihapus seperti semula
(tidak ada regresi perilaku lama untuk data yang belum pernah dipakai).
"""
import os
import sys
import tempfile

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

# =====================================================================
# 1) hapus_mk — mata kuliah yang SUDAH dibuka sebagai kelas
# =====================================================================
conn.execute("INSERT INTO kurikulum_versi(nama, tahun_berlaku, status) VALUES('Kur Uji','2024',\'Aktif\')")
kur_id = conn.execute("SELECT id FROM kurikulum_versi WHERE nama='Kur Uji'").fetchone()["id"]
conn.execute(
    "INSERT INTO mata_kuliah(kurikulum_id, kode, nama, sks, semester) VALUES(?,?,?,?,?)",
    (kur_id, "MK001", "Mata Kuliah Uji", 3, 1),
)
mk_id = conn.execute("SELECT id FROM mata_kuliah WHERE kode='MK001'").fetchone()["id"]
conn.execute(
    "INSERT INTO jadwal_kelas(mata_kuliah_id, tahun_akademik, semester_ajaran, kelas) VALUES(?,?,?,?)",
    (mk_id, "2023/2024", "Ganjil", "A"),
)
conn.commit()

r = client.post(f"/kurikulum/mk/{mk_id}/hapus", follow_redirects=True)
masih_ada = conn.execute("SELECT id FROM mata_kuliah WHERE id=?", (mk_id,)).fetchone()
check("Mata kuliah yang sudah dibuka sebagai kelas TIDAK terhapus", masih_ada is not None)
check("Pesan peringatan menyebut 'kelas'", b"kelas" in r.data.lower())
check("Endpoint tetap 200 (redirect ditangani)", r.status_code == 200)

# Hapus kelasnya dulu -> sekarang hapus_mk harus berhasil
conn.execute("DELETE FROM jadwal_kelas WHERE mata_kuliah_id=?", (mk_id,))
conn.commit()
client.post(f"/kurikulum/mk/{mk_id}/hapus", follow_redirects=True)
sudah_hilang = conn.execute("SELECT id FROM mata_kuliah WHERE id=?", (mk_id,)).fetchone()
check("Mata kuliah TANPA kelas tetap bisa dihapus (tidak ada regresi)", sudah_hilang is None)

# =====================================================================
# 2) hapus_cpl — CPL yang SUDAH dipakai siklus CQI
# =====================================================================
conn.execute("INSERT INTO cpl(kurikulum_id, kode, kategori, deskripsi) VALUES(?,?,?,?)", (kur_id, "CPL-U1", "Pengetahuan", "CPL Uji"))
cpl_id = conn.execute("SELECT id FROM cpl WHERE kode='CPL-U1'").fetchone()["id"]
conn.execute(
    "INSERT INTO cqi_siklus(kurikulum_id, cpl_id, tahun_akademik, target_persen) VALUES(?,?,?,?)",
    (kur_id, cpl_id, "2023/2024", 70),
)
conn.commit()

client.post(f"/kurikulum/cpl/{cpl_id}/hapus", follow_redirects=True)
cpl_masih_ada = conn.execute("SELECT id FROM cpl WHERE id=?", (cpl_id,)).fetchone()
check("CPL yang masih dipakai siklus CQI TIDAK terhapus", cpl_masih_ada is not None)

conn.execute("DELETE FROM cqi_siklus WHERE cpl_id=?", (cpl_id,))
conn.commit()
client.post(f"/kurikulum/cpl/{cpl_id}/hapus", follow_redirects=True)
cpl_hilang = conn.execute("SELECT id FROM cpl WHERE id=?", (cpl_id,)).fetchone()
check("CPL TANPA siklus CQI tetap bisa dihapus (tidak ada regresi)", cpl_hilang is None)

# =====================================================================
# 3) hapus_tahap — tahap yang SUDAH dirujuk mahasiswa
# =====================================================================
client.post("/pengaturan/tahun-akademik", data={"aksi": "buka_tahun", "kode": "2024/2025", "aktifkan": "Ganjil"})
periode = conn.execute(
    "SELECT pa.id FROM periode_akademik pa JOIN tahun_ajaran ta ON ta.id=pa.tahun_ajaran_id "
    "WHERE ta.kode='2024/2025' AND pa.jenis='Ganjil'"
).fetchone()
pid = periode["id"]
client.post("/pengaturan/tahun-akademik", data={"aksi": "tambah_tahap", "periode_id": str(pid), "nama_tahap": "Tahap Uji"})
tahap = conn.execute("SELECT id FROM tahap_pengajuan WHERE nama='Tahap Uji'").fetchone()
tahap_id = tahap["id"]

conn.execute("INSERT INTO mahasiswa(nim, nama) VALUES('9999999','Mhs Uji Tahap')")
mhs_id = conn.execute("SELECT id FROM mahasiswa WHERE nim='9999999'").fetchone()["id"]
conn.execute(
    "INSERT INTO pengajuan_judul(mahasiswa_id, tahap_pengajuan_id, status_final) VALUES(?,?,?)",
    (mhs_id, tahap_id, "Diajukan"),
)
conn.commit()

client.post("/pengaturan/tahun-akademik", data={"aksi": "hapus_tahap", "tahap_id": str(tahap_id)}, follow_redirects=True)
tahap_masih_ada = conn.execute("SELECT id FROM tahap_pengajuan WHERE id=?", (tahap_id,)).fetchone()
check("Tahap yang masih dirujuk Pengajuan Judul TIDAK terhapus", tahap_masih_ada is not None)

conn.execute("DELETE FROM pengajuan_judul WHERE tahap_pengajuan_id=?", (tahap_id,))
conn.commit()
client.post("/pengaturan/tahun-akademik", data={"aksi": "hapus_tahap", "tahap_id": str(tahap_id)}, follow_redirects=True)
tahap_hilang = conn.execute("SELECT id FROM tahap_pengajuan WHERE id=?", (tahap_id,)).fetchone()
check("Tahap TANPA rujukan tetap bisa dihapus (tidak ada regresi)", tahap_hilang is None)

# =====================================================================
print()
if FAILS:
    print(f"=== {len(FAILS)} GAGAL ===")
    for f in FAILS:
        print(" -", f)
    sys.exit(1)
else:
    print("=== SELESAI ===")
    print("SEMUA TES LULUS.")
