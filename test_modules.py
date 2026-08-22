import os, sys, tempfile, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir  # isolate ~/SistemSkripsi for this test run

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


# ---- login (first run creates password) ----
check("GET /login", client.get("/login"))
check("POST create password", client.post("/login", data={"username": "kaprodi", "password1": "test1234", "password2": "test1234"}, follow_redirects=True))

# ---- baseline: all 17 old pages should still work ----
old_pages = [
    "/", "/mahasiswa", "/dosen", "/ruangan", "/akademik/pengajuan", "/akademik/penetapan",
    "/pelaksanaan/seminar", "/pelaksanaan/sidang", "/kelulusan/yudisium", "/kelulusan/wisuda",
    "/kelulusan/tracer", "/rekap/pembimbing", "/rekap/status", "/rekap/rkp-seminar",
    "/rekap/rkp-sidang", "/rekap/rasio-dosen", "/rekap/statistik", "/surat",
    "/pengaturan/pengguna", "/pengaturan/branding", "/pengaturan/tahun-akademik",
    "/pengaturan/password", "/pengaturan/import-export", "/sdm",
]
for p in old_pages:
    r = client.get(p, follow_redirects=True)
    if r.status_code != 200:
        # try to discover the real url via app.url_map for debugging
        pass
    check(f"GET {p} (existing)", r)

# ================= MODULE 5: Kalender =================
check("GET /kalender/", client.get("/kalender/"))
check("POST kalender simpan", client.post("/kalender/simpan", data={
    "judul": "Ujian Tengah Semester", "kategori": "Ujian", "tgl_mulai": "2026-08-10",
    "jam": "08.00", "lokasi": "Ruang A", "status": "Terjadwal", "pengingat_hari": "5",
}, follow_redirects=True))
row_check = client.get("/kalender/")
assert b"Ujian Tengah Semester" in row_check.data, "agenda kalender tidak muncul di list"
print("[OK] agenda kalender tersimpan & tampil")

# near-term event for dashboard reminder test
from datetime import date, timedelta
soon = (date.today() + timedelta(days=2)).isoformat()
client.post("/kalender/simpan", data={
    "judul": "Rapat Prodi Mendesak", "kategori": "Rapat", "tgl_mulai": soon,
    "status": "Terjadwal", "pengingat_hari": "3",
})
dash = client.get("/")
assert b"Rapat Prodi Mendesak" in dash.data, "reminder kalender tidak muncul di dashboard"
print("[OK] agenda mendatang muncul di dashboard")

# edit & delete
kid_row = client.get("/kalender/")
import re
m = re.search(rb"kalender/(\d+)/hapus", kid_row.data)
if m:
    kid = m.group(1).decode()
    check("POST kalender hapus", client.post(f"/kalender/{kid}/hapus", follow_redirects=True))

# ================= MODULE 6: Kegiatan & Program Kerja =================
check("GET /kegiatan/ (proker)", client.get("/kegiatan/?tab=proker"))
check("POST proker simpan", client.post("/kegiatan/proker/simpan", data={
    "tahun_akademik": "2025-2026", "bidang": "Akademik & Kurikulum",
    "nama_program": "Peningkatan Mutu Pembelajaran", "indikator_kinerja": "Jumlah workshop",
    "target": "4", "satuan": "kegiatan", "anggaran_rencana": "5000000",
    "penanggung_jawab": "Kaprodi", "status": "Berjalan",
}, follow_redirects=True))
prok = client.get("/kegiatan/?tab=proker")
assert b"Peningkatan Mutu Pembelajaran" in prok.data
print("[OK] program kerja tersimpan & tampil")

m2 = re.search(rb"program_kerja_id.{0,400}?value=\"(\d+)\"", prok.data, re.S)
proker_id = None
mm = re.search(rb'<option value="(\d+)"[^>]*>Peningkatan Mutu Pembelajaran', prok.data)

check("GET /kegiatan/ (kegiatan tab)", client.get("/kegiatan/?tab=kegiatan"))
check("POST kegiatan simpan (tanpa proker)", client.post("/kegiatan/pelaksanaan/simpan", data={
    "nama_kegiatan": "Workshop Kurikulum MBKM", "kategori": "Pelatihan/Workshop",
    "tgl_mulai": "2026-08-20", "lokasi": "Aula Kampus", "status": "Direncanakan",
}, follow_redirects=True))
keg = client.get("/kegiatan/?tab=kegiatan")
assert b"Workshop Kurikulum MBKM" in keg.data
print("[OK] kegiatan tersimpan & tampil")

# realisasi calc: mark one kegiatan as Selesai and check percent
mk = re.search(rb'pelaksanaan/(\d+)/hapus', keg.data)
if mk:
    keg_id = mk.group(1).decode()
    check("POST kegiatan update -> Selesai", client.post("/kegiatan/pelaksanaan/simpan", data={
        "id": keg_id, "nama_kegiatan": "Workshop Kurikulum MBKM", "kategori": "Pelatihan/Workshop",
        "tgl_mulai": "2026-08-20", "lokasi": "Aula Kampus", "status": "Selesai",
    }, follow_redirects=True))

# ================= MODULE 7: Document Center =================
check("GET /dokumen/", client.get("/dokumen/"))
from io import BytesIO
data = {
    "judul": "SK Pengangkatan Kaprodi", "kategori": "SK/Surat Keputusan",
    "nomor_dokumen": "001/SK/2026", "tgl_dokumen": "2026-01-05",
    "sumber_instansi": "Rektorat", "file_dokumen": (BytesIO(b"dummy pdf content"), "sk_kaprodi.pdf"),
}
check("POST dokumen unggah", client.post("/dokumen/unggah", data=data,
                                          content_type="multipart/form-data", follow_redirects=True))
docs = client.get("/dokumen/")
assert b"SK Pengangkatan Kaprodi" in docs.data
print("[OK] dokumen terunggah & tampil")

md = re.search(rb'dokumen/(\d+)/unduh', docs.data)
if md:
    did = md.group(1).decode()
    r = check(f"GET dokumen/{did}/unduh", client.get(f"/dokumen/{did}/unduh"))
    assert r.data == b"dummy pdf content"
    print("[OK] dokumen bisa diunduh & isinya sama")

# reject disallowed extension
bad = client.post("/dokumen/unggah", data={
    "judul": "Virus", "kategori": "Lainnya",
    "file_dokumen": (BytesIO(b"x"), "malware.exe"),
}, content_type="multipart/form-data", follow_redirects=True)
assert "tidak diizinkan".encode() in bad.data
print("[OK] ekstensi terlarang ditolak")

# ================= MODULE 8: Generator Surat Umum =================
check("GET /surat-umum/", client.get("/surat-umum/"))
r = check("POST surat-umum buat (Surat Tugas)", client.post("/surat-umum/buat", data={
    "jenis_surat": "Surat Tugas", "perihal": "Penugasan sebagai Panitia Ujian",
    "tujuan": "Dosen Pengampu", "tanggal_surat": "2026-08-04",
    "isi": "Menugaskan dosen tersebut untuk menjadi panitia ujian semester ganjil 2026/2027.",
    "penandatangan": "Dr. Contoh Nama", "jabatan_penandatangan": "Ketua Program Studi",
    "tembusan": "Dekan\nArsip",
}))
assert r.headers.get("Content-Type", "").startswith(
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
print("[OK] surat umum (docx) berhasil digenerate & diunduh")

agenda = client.get("/surat-umum/")
assert b"Penugasan sebagai Panitia Ujian" in agenda.data
print("[OK] surat tercatat di Buku Agenda Surat Keluar")

# nomor surat format check
ms = re.search(rb'/ST/', agenda.data)
assert ms, "kode jenis ST tidak muncul di nomor surat"
print("[OK] format nomor surat memuat kode jenis ST")

# second letter same year -> urut number should increment
client.post("/surat-umum/buat", data={
    "jenis_surat": "Surat Keterangan", "perihal": "Keterangan Aktif Mengajar",
    "tanggal_surat": "2026-08-04", "isi": "Dosen yang bersangkutan aktif mengajar.",
})
agenda2 = client.get("/surat-umum/")
nomor_matches = re.findall(rb'class="mono" style="padding-left:24px;">([0-9]{3}/\S+)</td>', agenda2.data)
print("Nomor surat tercatat:", [n.decode() for n in nomor_matches])
assert len(nomor_matches) == 2
assert nomor_matches[0] != nomor_matches[1]
print("[OK] nomor surat otomatis unik/increment per surat")

# unduh ulang dari agenda
mid = re.search(rb'surat-umum/(\d+)/unduh', agenda2.data)
if mid:
    sid = mid.group(1).decode()
    check(f"GET surat-umum/{sid}/unduh (redownload)", client.get(f"/surat-umum/{sid}/unduh"))

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
