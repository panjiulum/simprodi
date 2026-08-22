"""Regresi untuk 2 bug yang ditemukan lewat audit manual (verifikasi eksekusi):

1. logic.sdm_reminder_semua() sebelumnya tidak memfilter dosen non-aktif
   (aktif=0), sehingga dosen yang sudah keluar/tidak aktif tetap muncul di
   Pusat Notifikasi kalau ada sertifikat/peran akademik yang kadaluarsa.
   Halaman SDM asal (sdm.py:index, _hitung_reminder) sengaja hanya
   menghitung dosen WHERE aktif=1 -- sdm_reminder_semua() harus konsisten.

2. logic.tridharma_reminder_tenggat() sebelumnya tidak mengecualikan
   laporan yang tinjauannya sudah selesai (status_tinjauan='Disetujui'
   atau 'Ditolak'), berbeda dengan pola ami_reminder_tenggat() yang benar
   mengecualikan status 'Selesai'/'Terverifikasi'. Akibatnya laporan yang
   sudah kelar direview tetap muncul terus sebagai "Lewat Tenggat".
"""
import os, sys, tempfile, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app, logic  # noqa: E402

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

with app.app_context():
    conn = app.get_db()

    # ------------------------------------------------------------------
    # Bug 1: sdm_reminder_semua() harus mengabaikan dosen aktif=0
    # ------------------------------------------------------------------
    conn.execute("INSERT INTO dosen (nama, nidn, aktif) VALUES ('Dosen Aktif Uji', '1111111111', 1)")
    conn.execute("INSERT INTO dosen (nama, nidn, aktif) VALUES ('Dosen Nonaktif Uji', '2222222222', 0)")
    conn.commit()
    id_aktif = conn.execute("SELECT id FROM dosen WHERE nama='Dosen Aktif Uji'").fetchone()["id"]
    id_nonaktif = conn.execute("SELECT id FROM dosen WHERE nama='Dosen Nonaktif Uji'").fetchone()["id"]

    tgl_lewat = (dt.date.today() - dt.timedelta(days=10)).isoformat()
    conn.execute(
        "INSERT INTO luaran_dosen (dosen_id, jenis_luaran, judul, masa_berlaku) VALUES (?, 'Sertifikat', 'Sertifikat Uji Aktif', ?)",
        (id_aktif, tgl_lewat),
    )
    conn.execute(
        "INSERT INTO luaran_dosen (dosen_id, jenis_luaran, judul, masa_berlaku) VALUES (?, 'Sertifikat', 'Sertifikat Uji Nonaktif', ?)",
        (id_nonaktif, tgl_lewat),
    )
    conn.commit()

    hasil_sdm = logic.sdm_reminder_semua(conn)
    nama_muncul = [r["dosen_nama"] for r in hasil_sdm]
    check("Reminder SDM: dosen AKTIF dengan sertifikat kadaluarsa tetap muncul",
          "Dosen Aktif Uji" in nama_muncul)
    check("Reminder SDM: dosen NON-AKTIF dengan sertifikat kadaluarsa TIDAK muncul (bug #1)",
          "Dosen Nonaktif Uji" not in nama_muncul)

    # ------------------------------------------------------------------
    # Bug 2: tridharma_reminder_tenggat() harus mengabaikan tinjauan
    # yang sudah 'Disetujui'/'Ditolak'
    # ------------------------------------------------------------------
    conn.execute(
        "INSERT INTO aktivitas_penelitian (dosen_id, judul, tahun_akademik) VALUES (?, 'Penelitian Belum Ditinjau', '2026-2027')",
        (id_aktif,),
    )
    conn.execute(
        "INSERT INTO aktivitas_penelitian (dosen_id, judul, tahun_akademik) VALUES (?, 'Penelitian Sudah Disetujui', '2026-2027')",
        (id_aktif,),
    )
    conn.commit()
    pen_belum_id = conn.execute("SELECT id FROM aktivitas_penelitian WHERE judul='Penelitian Belum Ditinjau'").fetchone()["id"]
    pen_disetujui_id = conn.execute("SELECT id FROM aktivitas_penelitian WHERE judul='Penelitian Sudah Disetujui'").fetchone()["id"]

    conn.execute(
        "INSERT INTO tridharma_tinjauan (penelitian_id, status_tinjauan, tenggat_laporan) VALUES (?, 'Belum Ditinjau', ?)",
        (pen_belum_id, tgl_lewat),
    )
    conn.execute(
        "INSERT INTO tridharma_tinjauan (penelitian_id, status_tinjauan, tenggat_laporan) VALUES (?, 'Disetujui', ?)",
        (pen_disetujui_id, tgl_lewat),
    )
    conn.commit()

    hasil_tridharma = logic.tridharma_reminder_tenggat(conn)
    judul_muncul = [r["judul"] for r in hasil_tridharma]
    check("Reminder Tri Dharma: laporan BELUM ditinjau & lewat tenggat tetap muncul",
          "Penelitian Belum Ditinjau" in judul_muncul)
    check("Reminder Tri Dharma: laporan yang sudah DISETUJUI tidak lagi muncul sbg 'Lewat Tenggat' (bug #2)",
          "Penelitian Sudah Disetujui" not in judul_muncul)

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
