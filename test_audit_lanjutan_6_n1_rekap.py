# -*- coding: utf-8 -*-
"""
test_audit_lanjutan_6_n1_rekap.py — Uji Pengembangan Lanjutan 6 (temuan
tambahan, laporan pengguna): `logic.rekap_rasio_dosen()` (dipakai
Dashboard, Rekap, DAN badge notifikasi global lewat get_notifikasi() ->
routes/notifikasi.py::kumpulkan(), yang jalan di SETIAP page load lewat
context processor app/__init__.py::inject_globals) menjalankan query
terpisah PER DOSEN di dalam loop, ditambah status_seminar_mahasiswa()/
status_sidang_mahasiswa() dipanggil satu-satu PER MAHASISWA BIMBINGAN --
pola N+1 klasik: jumlah query bertumbuh sebanding dosen x
mahasiswa_bimbingan, bukan konstan.

Diperbaiki dgn membaca seluruh data mentah lewat sejumlah kecil query
batch (konstan) lalu menghitung per dosen di Python (dict lookup). Dua
fungsi lain dgn pola identik (rekap_pembimbing(), rekap_status_mahasiswa())
ikut dibetulkan sekalian krn memakai helper batch yang sama
(_status_seminar_batch/_status_sidang_batch).

Test ini memverifikasi DUA hal: (1) HASIL akhir identik dgn logika lama
(dihitung manual dari data yg disiapkan, bukan dibandingkan ke kode lama
yg sudah dihapus), dan (2) JUMLAH QUERY SQL benar-benar konstan --
diukur langsung lewat sqlite3 Connection.set_trace_callback(), dibandingkan
antara dataset kecil vs dataset besar (dosen & mahasiswa bimbingan jauh
lebih banyak). Kalau perbaikan gagal/regresi ke pola lama, jumlah query
pada dataset besar akan jauh lebih tinggi dari dataset kecil -- test akan
menangkap itu, bukan cuma percaya komentar kode.

Tidak diikutkan di paket produksi (murni verifikasi pengembangan).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402
from app import logic as L  # noqa: E402

FAILS = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)


db_path = os.path.join(tmpdir, "test.db")
app = create_app(db_path=db_path)
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False


def hitung_query(conn, fn, *a, **kw):
    """Hitung berapa kali sqlite3 benar-benar mengeksekusi statement SQL
    selama pemanggilan fn(*a, **kw), lewat set_trace_callback (bukan
    perkiraan/mock -- ini query SUNGGUHAN yg dikirim ke sqlite3)."""
    n = [0]

    def _cb(stmt):
        n[0] += 1
    conn.set_trace_callback(_cb)
    try:
        hasil = fn(conn, *a, **kw)
    finally:
        conn.set_trace_callback(None)
    return hasil, n[0]


def siapkan_dataset(conn, jumlah_dosen, mhs_per_dosen, prefix):
    """Bikin `jumlah_dosen` dosen homebase, masing-masing membimbing
    `mhs_per_dosen` mahasiswa (sbg pembimbing1), separuhnya sudah Seminar
    'Selesai' & sidang 'LULUS', separuhnya belum -- supaya angka rekap
    tidak nol & bisa diverifikasi manual."""
    dosen_ids = []
    for di in range(jumlah_dosen):
        conn.execute(
            "INSERT INTO dosen(nama, aktif, status_homebase) VALUES(?,1,'Homebase')",
            (f"{prefix} Dosen {di}",))
        dosen_ids.append(conn.execute("SELECT last_insert_rowid() id").fetchone()["id"])

    total_selesai_seminar = 0
    total_lulus_sidang = 0
    for di, did in enumerate(dosen_ids):
        for mi in range(mhs_per_dosen):
            nim = f"{prefix}-{di}-{mi}"
            conn.execute("INSERT INTO mahasiswa(nim, nama) VALUES(?,?)", (nim, f"Mhs {nim}"))
            mid = conn.execute("SELECT id FROM mahasiswa WHERE nim=?", (nim,)).fetchone()["id"]
            conn.execute(
                "INSERT INTO penetapan_pembimbing(mahasiswa_id, pembimbing1_id) VALUES(?,?)",
                (mid, did))
            if mi % 2 == 0:
                conn.execute(
                    "INSERT INTO seminar(mahasiswa_id, status) VALUES(?, 'Selesai')", (mid,))
                total_selesai_seminar += 1
                conn.execute(
                    "INSERT INTO sidang(mahasiswa_id, nilai_angka, status_kelulusan) "
                    "VALUES(?, 80, 'LULUS')", (mid,))
                total_lulus_sidang += 1
            else:
                conn.execute(
                    "INSERT INTO seminar(mahasiswa_id, status) VALUES(?, 'Terdaftar')", (mid,))
    conn.commit()
    return dosen_ids, total_selesai_seminar, total_lulus_sidang


with app.app_context():
    conn = app.get_db()

    # -------------------------------------------------------------
    # 1. Dataset KECIL (3 dosen x 4 mahasiswa) vs BESAR (3 dosen x 40
    #    mahasiswa) -- kalau pola N+1 masih ada, jumlah query pada dataset
    #    besar akan jauh lebih tinggi (10x mahasiswa -> ~10x lebih banyak
    #    query). Kalau sudah diperbaiki, jumlah query harus KONSTAN
    #    (sama persis, karena jumlah query tidak bergantung isi data).
    # -------------------------------------------------------------
    siapkan_dataset(conn, jumlah_dosen=3, mhs_per_dosen=4, prefix="KECIL")
    _, n_query_kecil = hitung_query(conn, L.rekap_rasio_dosen)

    siapkan_dataset(conn, jumlah_dosen=3, mhs_per_dosen=40, prefix="BESAR")
    _, n_query_besar = hitung_query(conn, L.rekap_rasio_dosen)

    print(f"    (info) jumlah query rekap_rasio_dosen() -- dataset kecil: {n_query_kecil}, "
          f"dataset besar (10x mahasiswa lebih banyak, ditambah dosen dataset kecil): {n_query_besar}")
    check("rekap_rasio_dosen(): jumlah query TIDAK bertumbuh signifikan walau mahasiswa "
          "jauh lebih banyak (bukti pola N+1 sudah hilang)",
          n_query_besar <= n_query_kecil + 3)
    check("rekap_rasio_dosen(): jumlah query kecil & wajar (query batch, bukan ratusan)",
          n_query_besar < 20)

    # -------------------------------------------------------------
    # 2. Verifikasi HASIL rekap_rasio_dosen() benar (bukan cuma cepat) --
    #    dihitung manual dari data yg disiapkan di atas.
    # -------------------------------------------------------------
    rows = L.rekap_rasio_dosen(conn)
    row_besar = next(r for r in rows if r["nama"] == "BESAR Dosen 0")
    check("rekap_rasio_dosen(): total_bimb benar (40 mahasiswa bimbingan)",
          row_besar["total_bimb"] == 40)
    check("rekap_rasio_dosen(): sudah_seminar benar (separuh = 20, status 'Selesai')",
          row_besar["sudah_seminar"] == 20)
    check("rekap_rasio_dosen(): sudah_sidang benar (separuh = 20, status 'LULUS')",
          row_besar["sudah_sidang"] == 20)
    check("rekap_rasio_dosen(): persen_seminar benar (20/40 = 50.0)",
          row_besar["persen_seminar"] == 50.0)

    # -------------------------------------------------------------
    # 3. rekap_pembimbing() -- sama-sama diperbaiki, cek query & hasil.
    # -------------------------------------------------------------
    _, n_query_pembimbing = hitung_query(conn, L.rekap_pembimbing)
    check("rekap_pembimbing(): jumlah query kecil & wajar (batch, bukan per-mahasiswa)",
          n_query_pembimbing < 20)
    by_dosen = L.rekap_pembimbing(conn)
    did_besar0 = next(d for d in by_dosen if by_dosen[d]["nama"] == "BESAR Dosen 0")
    entri = by_dosen[did_besar0]
    check("rekap_pembimbing(): jumlah mahasiswa pembimbing_1 benar (40)",
          len(entri["pembimbing_1"]) == 40)
    selesai_seminar_pembimbing = sum(
        1 for x in entri["pembimbing_1"] if x["status_seminar"] == "Selesai")
    lulus_sidang_pembimbing = sum(
        1 for x in entri["pembimbing_1"] if x["status_sidang"] == "LULUS")
    check("rekap_pembimbing(): status_seminar per mahasiswa benar (20 'Selesai')",
          selesai_seminar_pembimbing == 20)
    check("rekap_pembimbing(): status_sidang per mahasiswa benar (20 'LULUS')",
          lulus_sidang_pembimbing == 20)

    # -------------------------------------------------------------
    # 4. rekap_status_mahasiswa() -- sama-sama diperbaiki, cek query & hasil.
    # -------------------------------------------------------------
    _, n_query_status = hitung_query(conn, L.rekap_status_mahasiswa)
    check("rekap_status_mahasiswa(): jumlah query kecil & wajar (batch, bukan per-mahasiswa)",
          n_query_status < 20)
    ringkasan = L.rekap_status_mahasiswa(conn)
    total_mhs = (3 * 4) + (3 * 40)  # dataset kecil + besar
    check("rekap_status_mahasiswa(): total benar (gabungan kedua dataset)",
          ringkasan["total"] == total_mhs)
    total_selesai_sem_expect = (3 * 2) + (3 * 20)  # separuh tiap dosen di tiap dataset
    check("rekap_status_mahasiswa(): sudah_seminar benar (gabungan)",
          ringkasan["sudah_seminar"] == total_selesai_sem_expect)
    check("rekap_status_mahasiswa(): lulus benar (gabungan)",
          ringkasan["lulus"] == total_selesai_sem_expect)

    # -------------------------------------------------------------
    # 5. Regresi fungsi single (non-batch) yg masih dipakai di tempat lain
    #    (mis. sdm_detail, validasi_transisi_status) -- pastikan TIDAK
    #    diubah perilakunya oleh refactor batch di atas.
    # -------------------------------------------------------------
    mid_cek = conn.execute("SELECT id FROM mahasiswa WHERE nim='BESAR-0-0'").fetchone()["id"]
    check("status_seminar_mahasiswa() (versi single, tetap ada) -> 'Selesai' utk mi=0 (genap)",
          L.status_seminar_mahasiswa(conn, mid_cek) == "Selesai")
    check("status_sidang_mahasiswa() (versi single, tetap ada) -> 'LULUS' utk mi=0 (genap)",
          L.status_sidang_mahasiswa(conn, mid_cek) == "LULUS")
    mid_cek2 = conn.execute("SELECT id FROM mahasiswa WHERE nim='BESAR-0-1'").fetchone()["id"]
    check("status_seminar_mahasiswa() (versi single) -> 'Terdaftar' utk mi=1 (ganjil)",
          L.status_seminar_mahasiswa(conn, mid_cek2) == "Terdaftar")
    check("status_sidang_mahasiswa() (versi single) -> 'Belum Sidang' utk mi=1 (ganjil, "
          "belum ada baris sidang)", L.status_sidang_mahasiswa(conn, mid_cek2) == "Belum Sidang")

    # -------------------------------------------------------------
    # 6. Kasus tepi: mahasiswa sidang ULANG (>1 baris), pernah TIDAK LULUS
    #    lalu akhirnya LULUS -- logika "LULUS-priority" harus tetap benar
    #    di versi batch (_status_sidang_batch), sama seperti versi single.
    # -------------------------------------------------------------
    conn.execute("INSERT INTO mahasiswa(nim, nama) VALUES('EDGE-001','Mhs Sidang Ulang')")
    mid_edge = conn.execute("SELECT id FROM mahasiswa WHERE nim='EDGE-001'").fetchone()["id"]
    conn.execute("INSERT INTO sidang(mahasiswa_id, nilai_angka, status_kelulusan) "
                 "VALUES(?, 50, 'TIDAK LULUS')", (mid_edge,))
    conn.execute("INSERT INTO sidang(mahasiswa_id, nilai_angka, status_kelulusan) "
                 "VALUES(?, 78, 'LULUS')", (mid_edge,))
    conn.commit()
    batch_hasil = L._status_sidang_batch(conn, [mid_edge])
    check("_status_sidang_batch(): logika LULUS-priority benar (pernah TIDAK LULUS, akhirnya "
          "LULUS -> 'LULUS', bukan status baris terakhir apa adanya secara naif)",
          batch_hasil.get(mid_edge) == "LULUS")
    check("status_sidang_mahasiswa() versi single: hasil identik dgn versi batch",
          L.status_sidang_mahasiswa(conn, mid_edge) == batch_hasil.get(mid_edge))

    # -------------------------------------------------------------
    # 7. Jalur HTTP penuh -- pastikan badge notifikasi (dipanggil di
    #    SETIAP halaman) & halaman Rekap tetap 200 setelah refactor.
    # -------------------------------------------------------------
    client = app.test_client()
    client.post("/login", data={"username": "kaprodi", "password1": "test1234", "password2": "test1234"},
                follow_redirects=True)
    r1 = client.get("/")
    check("GET / (dashboard, memicu badge notifikasi -> get_notifikasi -> "
          "rekap_rasio_dosen) -> 200", r1.status_code == 200)
    r2 = client.get("/rekap/rasio-dosen")
    check("GET /rekap/rasio-dosen -> 200", r2.status_code == 200)
    r3 = client.get("/rekap/pembimbing")
    check("GET /rekap/pembimbing -> 200", r3.status_code == 200)
    r4 = client.get("/rekap/status")
    check("GET /rekap/status -> 200", r4.status_code == 200)

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
