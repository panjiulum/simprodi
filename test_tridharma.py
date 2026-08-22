import os, sys, tempfile, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402

db_path = os.path.join(tmpdir, "test.db")
app = create_app(db_path=db_path)
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False  # skrip tes tidak mengirim token CSRF
client = app.test_client()

FAILS = []
def check(label, resp, expect=(200,)):
    ok = resp.status_code in expect
    print(f"[{'OK' if ok else 'FAIL'}] {label} -> {resp.status_code}")
    if not ok:
        FAILS.append(label)
    return resp

client.get("/login")
client.post("/login", data={"username": "kaprodi", "password1": "test1234", "password2": "test1234"}, follow_redirects=True)

# Atur tahun akademik aktif (dipakai perhitungan publikasi tahun ini & target)
# — memakai wizard "Buka Tahun Ajaran" baru (Audit poin 1), menggantikan
# 3 text-input bebas versi lama.
client.post("/pengaturan/tahun-akademik", data={"aksi": "buka_tahun", "kode": "2026-2027", "aktifkan": "Ganjil"})

# ---- Fondasi: 2 dosen dulu (data Modul 4 -- sumber Modul 15) ----
client.post("/dosen/simpan", data={"nama": "Dr. Andi Wijaya, M.Kom", "nidn": "0011122233", "aktif": "on"})
client.post("/dosen/simpan", data={"nama": "Rahmawati, S.T., M.T.", "nidn": "0022233344", "aktif": "on"})
dosen_page = client.get("/dosen/")
dosen_ids = re.findall(rb"/dosen/\?edit=(\d+)", dosen_page.data)
if len(dosen_ids) < 2:
    dosen_ids = re.findall(rb"/dosen/(\d+)/hapus", dosen_page.data)
dosen1_id, dosen2_id = dosen_ids[0].decode(), dosen_ids[1].decode()

# ---- Aktivitas Penelitian & PKM lewat SDM (Modul 4, TIDAK diubah) ----
check("POST tambah penelitian dosen 1 (via SDM)", client.post(f"/sdm/{dosen1_id}/penelitian/simpan", data={
    "judul": "Model Machine Learning untuk Deteksi Dini Penyakit", "skema": "Hibah Kompetitif Nasional",
    "sumber_dana": "Kemendikbudristek", "nominal": "50000000", "pelaksana": "Ketua",
    "tahun_akademik": "2026-2027", "semester": "Ganjil", "status": "Submitted",
    "jenis_luaran": "Publikasi",
}, follow_redirects=True))
check("POST tambah PKM dosen 2 (via SDM)", client.post(f"/sdm/{dosen2_id}/pkm/simpan", data={
    "judul": "Pelatihan Literasi Digital bagi UMKM", "jenis": "Pelatihan", "skema": "Dana Internal",
    "lokasi": "Desa Mekar Jaya", "mitra": "Karang Taruna", "dana": "5000000",
    "tahun_akademik": "2026-2027", "semester": "Ganjil", "status": "Accepted",
    "jenis_luaran": "Publikasi",
}, follow_redirects=True))
check("POST tambah luaran Publikasi dosen 1", client.post(f"/sdm/{dosen1_id}/luaran/simpan", data={
    "jenis_luaran": "Publikasi", "judul": "Optimization of Neural Networks using Genetic Algorithms",
    "penulis_terkait": "Andi Wijaya, Rahmawati", "tahun_akademik": "2026-2027", "semester": "Ganjil",
    "nomor_identitas": "DOI: 10.1234/ijcs.2026.001", "status": "Published",
}, follow_redirects=True))
check("POST tambah luaran HKI dosen 2", client.post(f"/sdm/{dosen2_id}/luaran/simpan", data={
    "jenis_luaran": "HKI", "judul": "Sistem Informasi Akademik Berbasis Blockchain",
    "penulis_terkait": "Rahmawati", "tahun_akademik": "2026-2027", "semester": "Ganjil",
    "nomor_identitas": "No. EC00202612345", "status": "Selesai",
}, follow_redirects=True))
check("POST tambah aktivitas pendidikan dosen 1", client.post(f"/sdm/{dosen1_id}/pendidikan/simpan", data={
    "tahun_akademik": "2026-2027", "semester": "Ganjil", "mata_kuliah": "Statistika Bisnis",
    "sks": "3", "status": "Berjalan",
}, follow_redirects=True))
check("POST tambah aktivitas penunjang dosen 2", client.post(f"/sdm/{dosen2_id}/penunjang/simpan", data={
    "jenis_penunjang": "Reviewer Jurnal", "nama_kegiatan": "Jurnal Nasional Terakreditasi",
    "tahun_akademik": "2026-2027", "semester": "Ganjil", "status": "Selesai",
}, follow_redirects=True))
check("POST tambah target kinerja dosen 1", client.post(f"/sdm/{dosen1_id}/target/simpan", data={
    "tahun": "2026", "kategori": "Publikasi", "target_angka": "3",
}, follow_redirects=True))

# =====================================================================
# Modul 15 — Tri Dharma (dashboard, penelitian_pkm, luaran, pendidikan_penunjang)
# =====================================================================
dash = check("GET /tridharma/ (tab dashboard)", client.get("/tridharma/"))
assert b"Penelitian Aktif" in dash.data
assert b"1</div>" in dash.data  # minimal 1 kartu bernilai 1 (penelitian/pkm aktif dsb)
print("[OK] Dashboard Tri Dharma menampilkan ringkasan stat")

assert b"Publikasi" in dash.data  # sebaran luaran
print("[OK] Sebaran luaran akademik tampil (data riil dari luaran_dosen)")

assert b"Andi Wijaya" in dash.data  # belum capai target (realisasi 1 < target 3)
print("[OK] Dosen belum capai target kinerja tahun berjalan terdeteksi (1/3 Publikasi)")

pp_page = check("GET /tridharma/?tab=penelitian_pkm", client.get("/tridharma/?tab=penelitian_pkm"))
assert b"Model Machine Learning" in pp_page.data and b"Pelatihan Literasi Digital" in pp_page.data
assert b"Andi Wijaya" in pp_page.data and b"Rahmawati" in pp_page.data
print("[OK] Daftar gabungan Penelitian+PKM lintas dosen tampil dengan benar")

pp_filter = check("GET /tridharma/?tab=penelitian_pkm&jenis=PKM", client.get("/tridharma/?tab=penelitian_pkm&jenis=PKM"))
assert b"Pelatihan Literasi Digital" in pp_filter.data
assert b"Model Machine Learning" not in pp_filter.data
print("[OK] Filter jenis=PKM hanya menampilkan data PKM")

pen_page = client.get("/tridharma/?tab=penelitian_pkm")
item_id = re.search(rb"item_jenis=Penelitian&(?:amp;)?item_id=(\d+)", pen_page.data)
if not item_id:
    item_id = re.search(rb"item_id=(\d+)", pen_page.data)
penelitian_id = item_id.group(1).decode()

check("POST simpan tinjauan institusional (Penelitian)", client.post("/tridharma/tinjauan/simpan", data={
    "jenis": "Penelitian", "item_id": penelitian_id, "status_tinjauan": "Disetujui",
    "ditinjau_oleh": "Kaprodi", "tenggat_laporan": "2026-08-10",
    "catatan_tinjauan": "Proposal layak dilanjutkan ke tahap pelaksanaan.",
}, follow_redirects=True))
tinjauan_page = client.get(f"/tridharma/?tab=penelitian_pkm&item_jenis=Penelitian&item_id={penelitian_id}")
assert b"Disetujui" in tinjauan_page.data
assert b"Proposal layak dilanjutkan" in tinjauan_page.data
print("[OK] Tinjauan institusional tersimpan & tampil (terpisah dari status self-report dosen)")

# Simpan lagi dgn status berbeda -> harus UPDATE (upsert), bukan baris baru
check("POST update tinjauan (upsert)", client.post("/tridharma/tinjauan/simpan", data={
    "jenis": "Penelitian", "item_id": penelitian_id, "status_tinjauan": "Direview",
    "ditinjau_oleh": "GKM", "tenggat_laporan": "2026-08-10",
}, follow_redirects=True))
tinjauan_page2 = client.get(f"/tridharma/?tab=penelitian_pkm&item_jenis=Penelitian&item_id={penelitian_id}")
assert b"Direview" in tinjauan_page2.data
print("[OK] Tinjauan diperbarui (upsert via UNIQUE penelitian_id), bukan duplikat baris")

dash2 = client.get("/tridharma/")
assert b"Segera Jatuh Tempo" in dash2.data or b"2026-08-10" in dash2.data
print("[OK] Reminder tenggat laporan tampil di Dashboard setelah tinjauan diisi")

luaran_page = check("GET /tridharma/?tab=luaran", client.get("/tridharma/?tab=luaran"))
assert b"Optimization of Neural Networks" in luaran_page.data
assert b"Sistem Informasi Akademik Berbasis Blockchain" in luaran_page.data
print("[OK] Daftar luaran lintas dosen tampil (Publikasi & HKI)")

luaran_filter = check("GET /tridharma/?tab=luaran&jenis=HKI", client.get("/tridharma/?tab=luaran&jenis=HKI"))
assert b"Blockchain" in luaran_filter.data
assert b"Neural Networks" not in luaran_filter.data
print("[OK] Filter jenis=HKI pada tab Luaran berfungsi")

edit_link_page = luaran_page.data
assert b"/sdm/" in edit_link_page and b"tab=luaran" in edit_link_page
print("[OK] Tautan edit luaran mengarah balik ke SDM (tidak ada form CRUD duplikat)")

pendpen_page = check("GET /tridharma/?tab=pendidikan_penunjang", client.get("/tridharma/?tab=pendidikan_penunjang"))
assert b"Statistika Bisnis" in pendpen_page.data
assert b"Jurnal Nasional Terakreditasi" in pendpen_page.data
print("[OK] Rekap Pendidikan & Penunjang lintas dosen tampil")

dash3 = check("GET dashboard utama (aditif ringkasan Tri Dharma)", client.get("/"))
# Audit Menyeluruh — PHASE 7 (Dashboard Control Center): kartu per-modul
# "🧪 Penelitian, PKM & Publikasi/HKI" yang berdiri sendiri sudah
# digantikan reorganisasi ke 6 kategori (KPI/Risk/Deadline/Workflow/
# Quality/Evidence) — reminder tenggat laporan hibah sekarang muncul di
# kartu "⏰ Deadline" dengan tautan ke modul Tri Dharma, bukan lagi kartu
# terpisah berjudul "Penelitian, PKM".
assert b"tenggat laporan hibah" in dash3.data
assert b"Tri Dharma" in dash3.data
print("[OK] Ringkasan Tri Dharma (tenggat laporan hibah) tampil di kartu Deadline Dashboard utama")

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
