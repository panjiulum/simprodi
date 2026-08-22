# -*- coding: utf-8 -*-
"""
test_audit_lanjutan_8_cache_ta.py — Uji Pengembangan Lanjutan 8 (celah
kecil sisa Restrukturisasi poin 3, dilaporkan pengguna).

`ubah_kode_tahun_ajaran()` (poin 3) mengganti `tahun_ajaran.kode` dan
mengandalkan `tahun_ajaran_id`/`periode_akademik_id` (INTEGER, tidak
pernah berubah) sebagai relasi — klaim di docstring-nya ("tidak ada
join yang putus") memang benar untuk relasi ID. TAPI 11 tabel
operasional (lihat `db.TABEL_CACHE_TAHUN_AKADEMIK`) juga menyimpan
SALINAN kode sebagai teks bebas di kolom `tahun_akademik` — diisi
otomatis dari `db.cache_periode()` saat baris dibuat/diedit lewat
dropdown periode terkunci (routes/sdm.py, jadwal.py, kegiatan.py,
cqi.py, mutu.py, semester_pendek.py). Sebelum perbaikan ini, cache
tersebut TIDAK ikut diperbarui saat kode diganti -> baris lama tetap
menampilkan kode LAMA di kolom filter/tampilan/rekap walau relasi
ID-nya masih utuh menunjuk ke tahun ajaran yang sama (yang sudah
berganti kode).

Diperbaiki lewat `db._sinkron_cache_tahun_akademik()`, dipanggil dari
dalam `db.ubah_kode_tahun_ajaran()`: menyamakan kolom `tahun_akademik`
di seluruh 11 tabel dengan kode baru, lewat 2 jalur —
1. baris ber-`periode_akademik_id` -> dicocokkan lewat ID (tidak
   bergantung pada teks lama sama sekali);
2. baris lama tanpa `periode_akademik_id` (sebelum dropdown terkunci
   ada) -> fallback dicocokkan lewat teks kode lama (unik).

Tidak diikutkan di paket produksi (murni verifikasi pengembangan).
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

FAILS = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)

with app.app_context():
    conn = _db.connect(db_path)

    # -----------------------------------------------------------------
    # Setup: 2 tahun ajaran (yang mau diubah kodenya, & 1 lainnya sebagai
    # kontrol negatif -> baris di tahun ajaran lain TIDAK BOLEH ikut
    # berubah), tiap satu punya periode Ganjil.
    # -----------------------------------------------------------------
    ta_id, periode_ids = _db.buka_tahun_ajaran(conn, "2025/2025", aktifkan="Ganjil")
    periode_id = periode_ids["Ganjil"]

    ta_id_lain, periode_ids_lain = _db.buka_tahun_ajaran(conn, "2030/2031", aktifkan="Ganjil")
    periode_id_lain = periode_ids_lain["Ganjil"]

    # FK pendukung
    conn.execute("INSERT INTO dosen(nama, nidn, aktif, status_homebase) VALUES(?,?,1,?)",
                 ("Dr. Uji Cache TA", "1234500001", "Homebase"))
    dosen_id = conn.execute("SELECT id FROM dosen WHERE nidn='1234500001'").fetchone()["id"]

    conn.execute("INSERT INTO kurikulum_versi(nama, tahun_berlaku, status) VALUES('Kur Uji Cache','2025','Aktif')")
    kur_id = conn.execute("SELECT id FROM kurikulum_versi WHERE nama='Kur Uji Cache'").fetchone()["id"]
    conn.execute("INSERT INTO cpl(kurikulum_id, kode, kategori, deskripsi) VALUES(?,?,?,?)",
                 (kur_id, "CPL-UJI-1", "Pengetahuan", "CPL Uji Cache TA"))
    cpl_id = conn.execute("SELECT id FROM cpl WHERE kode='CPL-UJI-1'").fetchone()["id"]
    conn.execute(
        "INSERT INTO mata_kuliah(kurikulum_id, kode, nama, sks, semester) VALUES(?,?,?,?,?)",
        (kur_id, "MKUJI001", "MK Uji Cache TA", 3, 1),
    )
    mk_id = conn.execute("SELECT id FROM mata_kuliah WHERE kode='MKUJI001'").fetchone()["id"]
    conn.commit()

    # -----------------------------------------------------------------
    # 1 baris per tabel di TABEL_CACHE_TAHUN_AKADEMIK, tahun ajaran yang
    # AKAN diubah kodenya, tahun_akademik diisi lewat cache_periode() —
    # persis pola yang dipakai routes/*.py, bukan diketik manual.
    # -----------------------------------------------------------------
    ta_text, _sem = _db.cache_periode(conn, periode_id)
    check("Setup: cache_periode mengembalikan kode awal", ta_text == "2025/2025")

    conn.execute(
        "INSERT INTO aktivitas_pendidikan(dosen_id, tahun_akademik, periode_akademik_id, mata_kuliah) "
        "VALUES(?,?,?,?)", (dosen_id, ta_text, periode_id, "MK Uji"),
    )
    conn.execute(
        "INSERT INTO aktivitas_penelitian(dosen_id, judul, tahun_akademik, periode_akademik_id) "
        "VALUES(?,?,?,?)", (dosen_id, "Judul Uji", ta_text, periode_id),
    )
    conn.execute(
        "INSERT INTO aktivitas_pkm(dosen_id, judul, tahun_akademik, periode_akademik_id) "
        "VALUES(?,?,?,?)", (dosen_id, "PKM Uji", ta_text, periode_id),
    )
    conn.execute(
        "INSERT INTO aktivitas_penunjang(dosen_id, nama_kegiatan, tahun_akademik, periode_akademik_id) "
        "VALUES(?,?,?,?)", (dosen_id, "Penunjang Uji", ta_text, periode_id),
    )
    conn.execute(
        "INSERT INTO luaran_dosen(dosen_id, jenis_luaran, judul, tahun_akademik, periode_akademik_id) "
        "VALUES(?,?,?,?,?)", (dosen_id, "Publikasi", "Luaran Uji", ta_text, periode_id),
    )
    conn.execute(
        "INSERT INTO peran_akademik_dosen(dosen_id, jenis_peran, nama_instansi_kegiatan, tahun_akademik, periode_akademik_id) "
        "VALUES(?,?,?,?,?)", (dosen_id, "Reviewer", "Instansi Uji", ta_text, periode_id),
    )
    conn.execute(
        "INSERT INTO program_kerja(tahun_akademik, periode_akademik_id, nama_program) "
        "VALUES(?,?,?)", (ta_text, periode_id, "Proker Uji"),
    )
    conn.execute(
        "INSERT INTO jadwal_kelas(mata_kuliah_id, tahun_akademik, periode_akademik_id) "
        "VALUES(?,?,?)", (mk_id, ta_text, periode_id),
    )
    conn.execute(
        "INSERT INTO cqi_siklus(kurikulum_id, cpl_id, tahun_akademik, periode_akademik_id) "
        "VALUES(?,?,?,?)", (kur_id, cpl_id, ta_text, periode_id),
    )
    conn.execute(
        "INSERT INTO sp_periode(nama, tahun_akademik, periode_akademik_id) "
        "VALUES(?,?,?)", ("SP Uji", ta_text, periode_id),
    )
    conn.execute(
        "INSERT INTO ami_siklus(nama, tahun_akademik, periode_akademik_id) "
        "VALUES(?,?,?)", ("Siklus Uji", ta_text, periode_id),
    )

    # Baris kontrol negatif: tahun ajaran LAIN (2030/2031) — tidak boleh
    # ikut berubah saat 2025/2025 diedit.
    ta_text_lain, _ = _db.cache_periode(conn, periode_id_lain)
    conn.execute(
        "INSERT INTO ami_siklus(nama, tahun_akademik, periode_akademik_id) "
        "VALUES(?,?,?)", ("Siklus Tahun Lain", ta_text_lain, periode_id_lain),
    )

    # Baris "data lama" — dari sebelum dropdown periode terkunci ada:
    # tahun_akademik terisi TEXT bebas, periode_akademik_id NULL.
    conn.execute(
        "INSERT INTO aktivitas_pendidikan(dosen_id, tahun_akademik, periode_akademik_id, mata_kuliah) "
        "VALUES(?,?,NULL,?)", (dosen_id, "2025/2025", "MK Lama Tanpa Periode"),
    )
    conn.commit()

    # -----------------------------------------------------------------
    # Aksi: perbaiki salah ketik kode 2025/2025 -> 2025/2026 (poin 3)
    # -----------------------------------------------------------------
    ok, pesan = _db.ubah_kode_tahun_ajaran(conn, ta_id, "2025/2026")
    check("ubah_kode_tahun_ajaran berhasil", ok and pesan == "")

    for table in _db.TABEL_CACHE_TAHUN_AKADEMIK:
        row = conn.execute(
            f"SELECT tahun_akademik FROM {table} WHERE periode_akademik_id=?", (periode_id,)
        ).fetchone()
        check(f"{table}: cache tahun_akademik ikut jadi '2025/2026' (bukan basi)",
              row is not None and row["tahun_akademik"] == "2025/2026")

    row_lama = conn.execute(
        "SELECT tahun_akademik FROM aktivitas_pendidikan WHERE periode_akademik_id IS NULL"
    ).fetchone()
    check("Baris lama tanpa periode_akademik_id (fallback teks) juga ikut disinkronkan",
          row_lama is not None and row_lama["tahun_akademik"] == "2025/2026")

    row_lain = conn.execute(
        "SELECT tahun_akademik FROM ami_siklus WHERE periode_akademik_id=?", (periode_id_lain,)
    ).fetchone()
    check("Baris tahun ajaran LAIN (2030/2031) tidak ikut berubah (kontrol negatif)",
          row_lain is not None and row_lain["tahun_akademik"] == "2030/2031")

    ta_row = conn.execute("SELECT kode FROM tahun_ajaran WHERE id=?", (ta_id,)).fetchone()
    check("tahun_ajaran.kode sendiri juga sudah 2025/2026", ta_row["kode"] == "2025/2026")

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
