# -*- coding: utf-8 -*-
"""
test_audit_lanjutan_6.py — Uji Pengembangan Lanjutan 6 (bug dilaporkan:
Import Generik Dosen bisa MENGHAPUS NIDN/NIP yang sudah ada saat re-import
dgn kolom tsb dikosongkan).

Latar belakang: `import_generic._dosen_proses()` mencocokkan baris impor
ke dosen yang sudah ada lewat 2 jalur (NIDN dulu, fallback ke nama kalau
NIDN di baris kosong), tapi query UPDATE-nya SEBELUMNYA selalu menulis
ulang kolom `nidn`/`nip` dgn nilai dari baris impor apa adanya —
termasuk kosong. Operator yang re-upload template hanya utk memperbarui
sebagian kolom (mis. email) tanpa mengisi ulang NIDN di tiap baris akan
membuat NIDN (kunci identitas resmi dosen) hilang diam-diam tanpa
peringatan apa pun.

Diperbaiki dgn "jangan timpa dengan kosong" khusus utk nidn & nip (lihat
komentar lengkap di app/import_generic.py::_dosen_proses). Test ini
memverifikasi: (1) bug tsb sungguh sudah tertambal utk kedua kolom & kedua
jalur pencocokan, (2) koreksi data yang SAH (NIDN baru, bukan kosong)
tetap berfungsi normal, (3) importer lain (SDM 7-tabel & Mahasiswa) sudah
diverifikasi TIDAK memiliki bug analog krn kunci pencocokan mereka wajib
diisi (baris dgn kunci kosong otomatis "dilewati", tidak pernah mencapai
UPDATE) — dibuktikan juga di sini, bukan cuma diklaim.

Tidak diikutkan di paket produksi (murni verifikasi pengembangan).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402
from app import import_generic  # noqa: E402

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
client.post("/pengaturan/pin", data={"pin1": "246810", "pin2": "246810"}, follow_redirects=True)

with app.app_context():
    conn = app.get_db()

    # -------------------------------------------------------------
    # 1. Skenario persis seperti dilaporkan: match via fallback NAMA
    #    (NIDN di baris impor kosong) -> NIDN lama HARUS dipertahankan
    # -------------------------------------------------------------
    conn.execute("INSERT INTO dosen(nidn,nama,email) VALUES(?,?,?)",
                 ("1234567890", "Dr. Contoh Uji", "lama@x.com"))
    conn.commit()
    status, pesan = import_generic._dosen_proses(
        conn, {"Nama*": "Dr. Contoh Uji", "NIDN": "", "Email": "baru@x.com"}, 2)
    conn.commit()
    r = conn.execute("SELECT nidn, email FROM dosen WHERE nama='Dr. Contoh Uji'").fetchone()
    check("Re-import match via nama (NIDN baris kosong) -> status 'update'", status == "update")
    check("NIDN lama TIDAK hilang (dipertahankan)", r["nidn"] == "1234567890")
    check("Kolom lain (email) tetap ikut ter-update seperti biasa", r["email"] == "baru@x.com")

    # -------------------------------------------------------------
    # 2. NIP (kolom identitas lain, tidak pernah dipakai sbg kunci
    #    pencocokan sama sekali) -> juga harus terlindungi, bahkan saat
    #    match terjadi lewat NIDN itu sendiri (bukan fallback nama)
    # -------------------------------------------------------------
    conn.execute("INSERT INTO dosen(nidn,nama,nip) VALUES(?,?,?)",
                 ("9999999999", "Dr. Contoh NIP", "198501012010121001"))
    conn.commit()
    status2, _ = import_generic._dosen_proses(
        conn, {"Nama*": "Dr. Contoh NIP", "NIDN": "9999999999", "NIP": ""}, 3)
    conn.commit()
    r2 = conn.execute("SELECT nip FROM dosen WHERE nama='Dr. Contoh NIP'").fetchone()
    check("NIP lama TIDAK hilang walau match via NIDN itu sendiri", r2["nip"] == "198501012010121001")

    # -------------------------------------------------------------
    # 3. Regresi — koreksi NIDN yang SAH (bukan kosong, mis. salah ketik
    #    sebelumnya) harus tetap berhasil ditimpa dgn nilai baru
    # -------------------------------------------------------------
    conn.execute("INSERT INTO dosen(nidn,nama) VALUES(?,?)", ("1111111111", "Dr. Contoh Koreksi"))
    conn.commit()
    status3, _ = import_generic._dosen_proses(
        conn, {"Nama*": "Dr. Contoh Koreksi", "NIDN": "2222222222"}, 4)
    conn.commit()
    r3 = conn.execute("SELECT nidn FROM dosen WHERE nama='Dr. Contoh Koreksi'").fetchone()
    check("Koreksi NIDN yang SAH (bukan kosong) tetap berfungsi normal", r3["nidn"] == "2222222222")

    # -------------------------------------------------------------
    # 4. Regresi — dosen BARU (INSERT, bukan update) tanpa NIDN tetap
    #    wajar tersimpan kosong (belum ada nilai lama utk dipertahankan)
    # -------------------------------------------------------------
    status4, _ = import_generic._dosen_proses(conn, {"Nama*": "Dr. Dosen Baru Tanpa NIDN"}, 5)
    conn.commit()
    r4 = conn.execute("SELECT nidn FROM dosen WHERE nama='Dr. Dosen Baru Tanpa NIDN'").fetchone()
    check("Dosen baru tanpa NIDN -> status 'tambah' (bukan diblokir)", status4 == "tambah")
    check("Dosen baru tanpa NIDN -> NIDN wajar kosong (bukan bug)", r4["nidn"] == "")

    # -------------------------------------------------------------
    # 5. Verifikasi tertulis: importer SDM (7 tabel log) TIDAK punya bug
    #    analog -- kolom identitas dosen (KOL_DOSEN) wajib terisi utk
    #    mencapai baris UPDATE, jadi tidak pernah bisa ditimpa kosong.
    # -------------------------------------------------------------
    conn.execute("INSERT INTO dosen(nidn,nama) VALUES(?,?)", ("5555555555", "Dr. Cek SDM"))
    conn.commit()
    did = conn.execute("SELECT id FROM dosen WHERE nama='Dr. Cek SDM'").fetchone()["id"]
    proses_penelitian = import_generic.IMPORTERS["sdm_penelitian"]["proses_baris"]
    row_awal = {
        import_generic.KOL_DOSEN: "5555555555", import_generic.KOL_TAHUN_AJARAN: "2025/2026",
        import_generic.KOL_SEMESTER: "Ganjil", "Judul*": "Penelitian Uji Cek Wipe",
        "Sumber Dana (Internal/Eksternal/Mandiri)": "Internal", "Nominal": "1000000",
    }
    import_generic.IMPORTERS["sdm_penelitian"]["proses_baris"](conn, row_awal, 2)
    conn.commit()
    row_dosen_kosong = dict(row_awal)
    row_dosen_kosong[import_generic.KOL_DOSEN] = ""
    status_sdm, pesan_sdm = proses_penelitian(conn, row_dosen_kosong, 3)
    check("Importer SDM (Penelitian): kolom dosen dikosongkan -> 'lewati' (aman, bukan wipe)",
          status_sdm == "lewati")
    row_update = dict(row_awal)
    row_update["Nominal"] = "2000000"
    status_sdm2, _ = proses_penelitian(conn, row_update, 4)
    conn.commit()
    r5 = conn.execute(
        "SELECT dosen_id, nominal FROM aktivitas_penelitian WHERE judul='Penelitian Uji Cek Wipe'"
    ).fetchone()
    check("Importer SDM: update normal tetap jalan, dosen_id tidak berubah", r5["dosen_id"] == did)
    check("Importer SDM: nominal ikut ter-update", r5["nominal"] == 2000000.0)

    # -------------------------------------------------------------
    # 6. Verifikasi tertulis: importer Mahasiswa TIDAK punya bug analog
    #    -- NIM adalah satu-satunya kunci (wajib, tanpa fallback).
    # -------------------------------------------------------------
    status_m, _ = import_generic._mahasiswa_proses(
        conn, {"NIM*": "2023010099", "Nama*": "Mhs Cek NIM", "Angkatan": "2023"}, 2)
    conn.commit()
    status_m2, pesan_m2 = import_generic._mahasiswa_proses(
        conn, {"NIM*": "", "Nama*": "Mhs Cek NIM"}, 3)
    check("Importer Mahasiswa: NIM dikosongkan -> 'lewati' (aman, bukan wipe)", status_m2 == "lewati")
    r6 = conn.execute("SELECT nim FROM mahasiswa WHERE nama='Mhs Cek NIM'").fetchone()
    check("Importer Mahasiswa: NIM lama tidak pernah tersentuh", r6["nim"] == "2023010099")

# -------------------------------------------------------------
# 7. Regresi lewat jalur HTTP penuh (route Import Generik) -- memastikan
#    perbaikan bekerja di alur nyata, bukan cuma panggilan fungsi langsung
# -------------------------------------------------------------
import io
import openpyxl

wb = openpyxl.Workbook()
ws = wb.active
ws.append(import_generic.DOSEN_HEADER)
ws.append(["", "Dr. Contoh Uji", "", "via-http@x.com", "", "", "", "", "Homebase", "", "", "", "Y"])
buf = io.BytesIO()
wb.save(buf)
buf.seek(0)
r = client.post("/pengaturan/import-generik/proses", data={
    "modul": "dosen", "file_excel": (buf, "dosen_update.xlsx"),
}, content_type="multipart/form-data", follow_redirects=True)
check("POST import-generik/proses (dosen, NIDN kosong di file) -> 200", r.status_code == 200)
with app.app_context():
    r7 = app.get_db().execute("SELECT nidn, email FROM dosen WHERE nama='Dr. Contoh Uji'").fetchone()
check("Lewat jalur HTTP penuh: NIDN tetap dipertahankan", r7["nidn"] == "1234567890")
check("Lewat jalur HTTP penuh: email tetap ter-update", r7["email"] == "via-http@x.com")

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
