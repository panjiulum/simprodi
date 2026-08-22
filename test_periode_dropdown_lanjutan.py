"""Lanjutan dari test_periode_dropdown.py — menguji 4 tabel inti TA yang
sebelumnya sudah punya kolom `periode_akademik_id` (ditambahkan lewat
_migrate() di db.py) tapi belum diwire ke form/route: `pengajuan_judul`,
`penetapan_pembimbing`, `jadwal_kelas`, `sp_periode`. Pola pengujian sama
persis dengan test_periode_dropdown.py (yang menguji 9 tabel tambahan)."""
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

# ------------------------------------------------------- Buka tahun ajaran
client.post("/pengaturan/tahun-akademik", data={"aksi": "buka_tahun", "kode": "2025/2026", "aktifkan": "Ganjil"})
periode_ganjil = conn.execute(
    "SELECT pa.id FROM periode_akademik pa JOIN tahun_ajaran ta ON ta.id=pa.tahun_ajaran_id "
    "WHERE ta.kode='2025/2026' AND pa.jenis='Ganjil'"
).fetchone()
pid = periode_ganjil["id"]
check("Periode Ganjil 2025/2026 berhasil dibuka", bool(pid))

# ------------------------------------------------------------- Data dasar
client.post("/mahasiswa/tambah", data={"nim": "2201001", "nama": "Mhs Uji Periode"})
mhs_id = conn.execute("SELECT id FROM mahasiswa WHERE nim='2201001'").fetchone()["id"]

client.post("/dosen/simpan", data={"nama": "Dr. Pembimbing Uji", "nidn": "0099998888", "aktif": "on"})
dosen_id = conn.execute("SELECT id FROM dosen WHERE nidn='0099998888'").fetchone()["id"]

# ===================================================== 1) pengajuan_judul
pengajuan_page = client.get("/akademik/pengajuan")
check("Halaman Pengajuan Judul -> 200", pengajuan_page.status_code == 200)
check("Dropdown Periode Akademik tampil di form Pengajuan Judul", b'name="periode_akademik_id"' in pengajuan_page.data)
check("Opsi periode 2025/2026 - Ganjil ada di dropdown Pengajuan Judul", b"2025/2026 - Ganjil" in pengajuan_page.data)

client.post("/akademik/pengajuan/simpan", data={
    "mahasiswa_id": str(mhs_id), "periode_akademik_id": str(pid),
    "judul1": "Judul Uji Periode 1", "status_final": "Diajukan",
}, follow_redirects=True)
row_pj = conn.execute("SELECT * FROM pengajuan_judul WHERE mahasiswa_id=?", (mhs_id,)).fetchone()
check("pengajuan_judul tersimpan", bool(row_pj))
check("pengajuan_judul.periode_akademik_id terisi FK asli (bukan cache doang)", row_pj["periode_akademik_id"] == pid)
check("pengajuan_judul.semester ikut ter-cache otomatis (gabungan 'tahun - jenis')", row_pj["semester"] == "2025/2026 - Ganjil")

edit_pj = client.get(f"/akademik/pengajuan?edit={row_pj['id']}")
check(
    "Form edit Pengajuan Judul men-preselect periode yang tersimpan",
    f'value="{pid}"'.encode() in edit_pj.data and b"selected" in edit_pj.data,
)

# =================================================== 2) penetapan_pembimbing
penetapan_page = client.get("/akademik/penetapan")
check("Halaman Penetapan Pembimbing -> 200", penetapan_page.status_code == 200)
check("Dropdown Periode Akademik tampil di form Penetapan Pembimbing", b'name="periode_akademik_id"' in penetapan_page.data)

client.post("/akademik/penetapan/simpan", data={
    "mahasiswa_id": str(mhs_id), "periode_akademik_id": str(pid),
    "judul_final": "Judul Final Uji Periode", "pembimbing1_id": str(dosen_id),
}, follow_redirects=True)
row_pp = conn.execute("SELECT * FROM penetapan_pembimbing WHERE mahasiswa_id=?", (mhs_id,)).fetchone()
check("penetapan_pembimbing tersimpan", bool(row_pp))
check("penetapan_pembimbing.periode_akademik_id terisi FK asli", row_pp["periode_akademik_id"] == pid)
check("penetapan_pembimbing.semester ikut ter-cache otomatis", row_pp["semester"] == "2025/2026 - Ganjil")

# ============================================================ 3) jadwal_kelas
# Butuh kurikulum aktif + mata kuliah supaya dropdown Mata Kuliah tidak kosong.
client.post("/kurikulum/versi/simpan", data={"nama": "Kurikulum Uji 2025", "tahun_mulai": "2025", "status": "Aktif"})
kur_id = conn.execute("SELECT id FROM kurikulum_versi WHERE nama='Kurikulum Uji 2025'").fetchone()["id"]
client.post("/kurikulum/mk/simpan", data={
    "kurikulum_id": str(kur_id), "kode": "MKU001", "nama": "Mata Kuliah Uji Periode", "sks": "3", "semester": "1",
})
mk_id = conn.execute("SELECT id FROM mata_kuliah WHERE kode='MKU001'").fetchone()["id"]

jadwal_page = client.get("/jadwal/?tab=kelas")
check("Halaman Jadwal Kelas -> 200", jadwal_page.status_code == 200)
check("Dropdown Periode Akademik tampil di form Jadwal Kelas", b'name="periode_akademik_id"' in jadwal_page.data)
check("Input teks bebas 'Tahun Akademik' TIDAK ada lagi (diganti dropdown periode)", b'name="tahun_akademik"' not in jadwal_page.data)

# Tanpa periode -> ditolak (Audit poin 1: periode wajib, bukan opsional lagi)
r_gagal = client.post("/jadwal/kelas/simpan", data={"mata_kuliah_id": str(mk_id), "kelas": "A"}, follow_redirects=True)
check("Simpan Jadwal Kelas tanpa Periode Akademik -> ditolak dengan pesan error", "wajib dipilih".encode() in r_gagal.data)

client.post("/jadwal/kelas/simpan", data={
    "mata_kuliah_id": str(mk_id), "periode_akademik_id": str(pid), "kelas": "A",
}, follow_redirects=True)
row_jk = conn.execute("SELECT * FROM jadwal_kelas WHERE mata_kuliah_id=? AND kelas='A'", (mk_id,)).fetchone()
check("jadwal_kelas tersimpan", bool(row_jk))
check("jadwal_kelas.periode_akademik_id terisi FK asli", row_jk["periode_akademik_id"] == pid)
check("jadwal_kelas.tahun_akademik ikut ter-cache otomatis dari periode", row_jk["tahun_akademik"] == "2025/2026")
check("jadwal_kelas.semester_ajaran ikut ter-cache otomatis dari periode", row_jk["semester_ajaran"] == "Ganjil")

edit_jk = client.get(f"/jadwal/?tab=kelas&edit={row_jk['id']}")
check(
    "Form edit Jadwal Kelas men-preselect periode yang tersimpan",
    f'value="{pid}"'.encode() in edit_jk.data and b"selected" in edit_jk.data,
)

# ================================================================ 4) sp_periode
sp_page = client.get("/semester-pendek/?tab=periode")
check("Halaman Periode Semester Pendek -> 200", sp_page.status_code == 200)
check("Dropdown Periode Akademik (Tahun Ajaran) tampil di form Periode SP", b'name="periode_akademik_id"' in sp_page.data)

client.post("/semester-pendek/periode/simpan", data={
    "nama": "SP Uji Periode 2025/2026", "periode_akademik_id": str(pid), "status": "Draft",
}, follow_redirects=True)
row_sp = conn.execute("SELECT * FROM sp_periode WHERE nama='SP Uji Periode 2025/2026'").fetchone()
check("sp_periode tersimpan", bool(row_sp))
check("sp_periode.periode_akademik_id terisi FK asli", row_sp["periode_akademik_id"] == pid)
check("sp_periode.tahun_akademik ikut ter-cache otomatis dari periode", row_sp["tahun_akademik"] == "2025/2026")

# Periode SP tetap boleh dibuat TANPA periode akademik terkunci (mis. sebelum
# wizard Buka Tahun Ajaran dipakai) -> cache kosong, bukan error.
client.post("/semester-pendek/periode/simpan", data={"nama": "SP Tanpa Periode", "status": "Draft"}, follow_redirects=True)
row_sp2 = conn.execute("SELECT * FROM sp_periode WHERE nama='SP Tanpa Periode'").fetchone()
check("sp_periode boleh disimpan tanpa periode akademik (opsional, tidak error)", bool(row_sp2))
check("sp_periode.tahun_akademik kosong bila periode tidak dipilih (bukan error/exception)", row_sp2["tahun_akademik"] in ("", None))

# =============================================== Regresi: modul lama tetap OK
check("Halaman Mahasiswa tetap 200 (regresi)", client.get("/mahasiswa/").status_code == 200)
check("Halaman SDM tetap 200 (regresi, tidak tersentuh perubahan ini)", client.get(f"/sdm/{dosen_id}").status_code == 200)
check("Halaman Kegiatan tetap 200 (regresi)", client.get("/kegiatan/?tab=proker").status_code == 200)

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
