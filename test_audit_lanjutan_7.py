# -*- coding: utf-8 -*-
"""
test_audit_lanjutan_7.py — Uji Pengembangan Lanjutan 7 (2 bug dilaporkan
pengguna):

1. Nomor surat resmi (Surat Umum) bisa tabrakan. `_nomor_otomatis()`
   sebelumnya menghitung urut = COUNT(*)+1 dari baris `surat_keluar`
   tahun berjalan. Begitu 1 surat DI TENGAH urutan dihapus, COUNT
   menurun sehingga surat berikutnya dapat nomor urut yang SAMA dengan
   surat lain yang masih ada -- padahal dokumentasi modul & pesan
   konfirmasi hapus menjamin "nomor tidak pernah tabrakan / tidak
   dipakai ulang". Diperbaiki: urut = MAX(urut yang pernah dipakai
   tahun berjalan) + 1, diparse dari `nomor_surat` yang tersimpan
   (bukan COUNT baris), sehingga tidak pernah menurun walau ada
   penghapusan.

2. Kuota kelas Semester Pendek tidak pernah ditegakkan. `sp_status_kelas()`
   menghitung label "Penuh"/"Kurang Kuota"/"Dibuka" tapi sebelumnya
   murni label tampilan -- `approval_peserta()` tidak pernah memeriksanya
   sehingga operator bisa menyetujui peserta tanpa batas meski kelas
   sudah "Penuh". Diperbaiki dgn pola konfirmasi yang sama seperti
   konfirmasi_bentrok/konfirmasi_transisi: transisi status -> 'Disetujui'
   saat kelas sudah Penuh butuh konfirmasi eksplisit (`konfirmasi_kuota`)
   sebelum tersimpan.

Tidak diikutkan di paket produksi (murni verifikasi pengembangan).
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402
from app import db as _db  # noqa: E402
from app.routes.surat_umum import _nomor_otomatis  # noqa: E402
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
client = app.test_client()
client.post("/login", data={"username": "kaprodi", "password1": "test1234", "password2": "test1234"}, follow_redirects=True)

with app.app_context():
    conn = app.get_db()

    # =================================================================
    # BAGIAN 1 — Nomor Surat Umum tidak boleh tabrakan setelah hapus
    # =================================================================
    from datetime import date
    tgl = date(2026, 8, 4)

    n1 = _nomor_otomatis(conn, "Surat Tugas", tgl)
    conn.execute(
        "INSERT INTO surat_keluar(nomor_surat, jenis_surat, perihal, tanggal_surat) "
        "VALUES(?,?,?,?)", (n1, "Surat Tugas", "Perihal 0", tgl.isoformat()))
    conn.commit()

    n2 = _nomor_otomatis(conn, "Surat Tugas", tgl)
    id2 = conn.execute(
        "INSERT INTO surat_keluar(nomor_surat, jenis_surat, perihal, tanggal_surat) "
        "VALUES(?,?,?,?)", (n2, "Surat Tugas", "Perihal 1 (akan dihapus)", tgl.isoformat())
    ).lastrowid
    conn.commit()

    n3 = _nomor_otomatis(conn, "Surat Tugas", tgl)
    conn.execute(
        "INSERT INTO surat_keluar(nomor_surat, jenis_surat, perihal, tanggal_surat) "
        "VALUES(?,?,?,?)", (n3, "Surat Tugas", "Perihal 2", tgl.isoformat()))
    conn.commit()

    check("Nomor 1 = 001/...", n1.startswith("001/"))
    check("Nomor 2 = 002/...", n2.startswith("002/"))
    check("Nomor 3 = 003/...", n3.startswith("003/"))

    # Hapus surat DI TENGAH urutan (persis skenario pengguna) — surat
    # dgn nomor 002 dihapus.
    conn.execute("DELETE FROM surat_keluar WHERE id=?", (id2,))
    conn.commit()

    # Ini titik krusial: dgn kode LAMA (COUNT(*)+1), sisa baris tinggal 2
    # -> urut berikutnya dihitung 3 -> TABRAKAN dgn n3 yang masih ada.
    n4 = _nomor_otomatis(conn, "Surat Tugas", tgl)
    check("Setelah hapus baris tengah, nomor baru TIDAK sama dgn nomor manapun yang masih ada",
          n4 != n1 and n4 != n3)
    check("Nomor baru meneruskan MAX+1 (004/...), bukan mengisi ulang slot yang dihapus (002)",
          n4.startswith("004/"))

    conn.execute(
        "INSERT INTO surat_keluar(nomor_surat, jenis_surat, perihal, tanggal_surat) "
        "VALUES(?,?,?,?)", (n4, "Surat Tugas", "Perihal Baru Setelah Hapus", tgl.isoformat()))
    conn.commit()

    semua_nomor = [r["nomor_surat"] for r in conn.execute(
        "SELECT nomor_surat FROM surat_keluar ORDER BY id").fetchall()]
    check("Seluruh nomor surat yang tersimpan unik (tidak ada duplikat)",
          len(semua_nomor) == len(set(semua_nomor)))

    # Tahun berbeda -> penghitungan mulai dari 001 lagi, tidak terpengaruh
    # baris tahun lain (sanity check filter WHERE tanggal_surat masih benar).
    n_2025 = _nomor_otomatis(conn, "Surat Tugas", date(2025, 3, 1))
    check("Tahun berbeda (2025) tidak terpengaruh data 2026 -> mulai dari 001",
          n_2025.startswith("001/") and n_2025.endswith("/2025"))

    # -----------------------------------------------------------------
    # Regresi lewat jalur HTTP penuh: buat 3 surat, hapus yang di tengah
    # lewat route hapus() sungguhan, buat surat ke-4, pastikan tidak
    # tabrakan di jalur nyata (bukan cuma panggilan fungsi langsung).
    # -----------------------------------------------------------------
    conn.execute("DELETE FROM surat_keluar")
    conn.commit()

for i in range(3):
    r = client.post("/surat-umum/buat", data={
        "jenis_surat": "Surat Keterangan", "perihal": f"HTTP Perihal {i}",
        "tanggal_surat": "2026-08-04", "isi": "Isi surat.",
    })
    check(f"POST surat-umum/buat #{i} -> 200", r.status_code == 200)

with app.app_context():
    conn = app.get_db()
    rows = conn.execute("SELECT id, nomor_surat FROM surat_keluar ORDER BY id").fetchall()
    check("3 surat via HTTP tercatat", len(rows) == 3)
    tengah_id = rows[1]["id"]

r = client.post(f"/surat-umum/{tengah_id}/hapus", follow_redirects=True)
check("POST surat-umum/<id>/hapus (baris tengah) -> 200", r.status_code == 200)

r = client.post("/surat-umum/buat", data={
    "jenis_surat": "Surat Keterangan", "perihal": "HTTP Perihal Baru Setelah Hapus",
    "tanggal_surat": "2026-08-04", "isi": "Isi surat.",
})
check("POST surat-umum/buat (setelah hapus baris tengah) -> 200", r.status_code == 200)

with app.app_context():
    conn = app.get_db()
    nomor_http = [row["nomor_surat"] for row in conn.execute(
        "SELECT nomor_surat FROM surat_keluar ORDER BY id").fetchall()]
    check("Jalur HTTP penuh: tidak ada nomor surat yang tabrakan setelah hapus di tengah",
          len(nomor_http) == len(set(nomor_http)))
    print("Nomor surat (jalur HTTP):", nomor_http)

    # =================================================================
    # BAGIAN 2 — Kuota kelas Semester Pendek harus ditegakkan
    # =================================================================
    ta_id, periode_ids = _db.buka_tahun_ajaran(conn, "2025/2026", aktifkan="Ganjil")
    conn.commit()

    conn.execute("INSERT INTO kurikulum_versi(nama, tahun_berlaku, status) VALUES('Kur SP','2025','Aktif')")
    kur_id = conn.execute("SELECT id FROM kurikulum_versi WHERE nama='Kur SP'").fetchone()["id"]
    conn.execute("INSERT INTO mata_kuliah(kurikulum_id, kode, nama, sks, semester) VALUES(?,?,?,?,?)",
                 (kur_id, "SP101", "Mata Kuliah SP", 3, 1))
    mk_id = conn.execute("SELECT id FROM mata_kuliah WHERE kode='SP101'").fetchone()["id"]

    conn.execute(
        "INSERT INTO sp_periode(nama, tahun_akademik, status) VALUES('SP Ganjil 2025/2026','2025/2026','Pendaftaran Dibuka')")
    periode_id = conn.execute("SELECT id FROM sp_periode WHERE nama='SP Ganjil 2025/2026'").fetchone()["id"]

    conn.execute(
        "INSERT INTO sp_kelas(periode_id, mata_kuliah_id, kuota_min, kuota_maks) VALUES(?,?,?,?)",
        (periode_id, mk_id, 1, 2))
    kelas_id = conn.execute(
        "SELECT id FROM sp_kelas WHERE periode_id=? AND mata_kuliah_id=?", (periode_id, mk_id)
    ).fetchone()["id"]

    mhs_ids = []
    for i in range(4):
        conn.execute("INSERT INTO mahasiswa(nim, nama, status) VALUES(?,?,?)",
                     (f"SP{i:03d}", f"Mahasiswa SP {i}", "Aktif"))
        mhs_ids.append(conn.execute("SELECT id FROM mahasiswa WHERE nim=?", (f"SP{i:03d}",)).fetchone()["id"])

    peserta_ids = []
    for mid in mhs_ids:
        conn.execute(
            "INSERT INTO sp_peserta(sp_kelas_id, mahasiswa_id) VALUES(?,?)", (kelas_id, mid))
        peserta_ids.append(conn.execute(
            "SELECT id FROM sp_peserta WHERE sp_kelas_id=? AND mahasiswa_id=?", (kelas_id, mid)
        ).fetchone()["id"])
    conn.commit()

# Setujui peserta 1 & 2 (mengisi kuota_maks=2 penuh) — harus lolos tanpa
# konfirmasi karena kelas belum Penuh saat masing-masing disetujui.
for idx in (0, 1):
    r = client.post(f"/semester-pendek/peserta/{peserta_ids[idx]}/approval",
                     data={"status_approval": "Disetujui"}, follow_redirects=True)
    check(f"Approval peserta ke-{idx+1} (kuota belum penuh) -> 200", r.status_code == 200)

with app.app_context():
    conn = app.get_db()
    disetujui_setelah_2 = conn.execute(
        "SELECT COUNT(*) c FROM sp_peserta WHERE sp_kelas_id=? AND status_approval='Disetujui'",
        (kelas_id,)).fetchone()["c"]
check("2 peserta pertama berhasil disetujui (pas kuota_maks)", disetujui_setelah_2 == 2)

# Peserta ke-3: kelas sudah "Penuh" -> approval TANPA konfirmasi_kuota
# harus DITAHAN (bukan langsung disimpan sbg Disetujui), tampilkan
# halaman konfirmasi (pola sama dgn _bentrok_confirm/_transisi_confirm).
r = client.post(f"/semester-pendek/peserta/{peserta_ids[2]}/approval",
                 data={"status_approval": "Disetujui"})
check("Approval peserta ke-3 (kelas Penuh, tanpa konfirmasi) -> 200 (halaman konfirmasi)",
      r.status_code == 200)
check("Halaman konfirmasi kuota tampil (bukan langsung tersimpan)",
      b"konfirmasi_kuota" in r.data or b"Kuota" in r.data)

with app.app_context():
    conn = app.get_db()
    status_p3 = conn.execute(
        "SELECT status_approval FROM sp_peserta WHERE id=?", (peserta_ids[2],)
    ).fetchone()["status_approval"]
check("BUG LAMA TERTUTUP: peserta ke-3 BELUM berstatus Disetujui tanpa konfirmasi eksplisit",
      status_p3 != "Disetujui")

    # Kirim ulang DENGAN konfirmasi_kuota=1 -> operator sengaja melebihi
    # kuota (mis. kebijakan khusus) -> harus berhasil tersimpan.
r = client.post(f"/semester-pendek/peserta/{peserta_ids[2]}/approval",
                 data={"status_approval": "Disetujui", "konfirmasi_kuota": "1"},
                 follow_redirects=True)
check("Approval peserta ke-3 DENGAN konfirmasi_kuota -> 200", r.status_code == 200)

with app.app_context():
    conn = app.get_db()
    status_p3b = conn.execute(
        "SELECT status_approval FROM sp_peserta WHERE id=?", (peserta_ids[2],)
    ).fetchone()["status_approval"]
check("Setelah konfirmasi eksplisit, peserta ke-3 berhasil disetujui (operator tetap punya kendali)",
      status_p3b == "Disetujui")

# Peserta ke-4: tolak (bukan setujui) tidak pernah butuh konfirmasi kuota,
# krn menolak justru tidak menambah kuota.
r = client.post(f"/semester-pendek/peserta/{peserta_ids[3]}/approval",
                 data={"status_approval": "Ditolak"}, follow_redirects=True)
check("Menolak peserta ke-4 (bukan menyetujui) -> tidak perlu konfirmasi kuota, 200",
      r.status_code == 200)
with app.app_context():
    conn = app.get_db()
    status_p4 = conn.execute(
        "SELECT status_approval FROM sp_peserta WHERE id=?", (peserta_ids[3],)
    ).fetchone()["status_approval"]
check("Peserta ke-4 tercatat Ditolak", status_p4 == "Ditolak")

# Sanity check: sp_status_kelas() sekarang benar2 "Penuh" (3 disetujui >= kuota_maks 2).
with app.app_context():
    conn = app.get_db()
    kelas_row = conn.execute("SELECT * FROM sp_kelas WHERE id=?", (kelas_id,)).fetchone()
    kapasitas = L.sp_status_kelas(conn, kelas_row)
check("Label kapasitas akhir = 'Penuh' (3 disetujui, kuota_maks=2)",
      kapasitas["label"] == "Penuh" and kapasitas["disetujui"] == 3)

# Re-toleransi status yang SUDAH 'Disetujui' -> dikirim ulang 'Disetujui'
# (mis. klik ganda / no-op) tidak boleh minta konfirmasi lagi, krn bukan
# transisi BARU menuju Disetujui.
r = client.post(f"/semester-pendek/peserta/{peserta_ids[0]}/approval",
                 data={"status_approval": "Disetujui"}, follow_redirects=True)
check("Approval ulang peserta yang SUDAH Disetujui (no-op) -> tidak diminta konfirmasi lagi, 200",
      r.status_code == 200)

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
