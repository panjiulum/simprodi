# -*- coding: utf-8 -*-
"""test_audit_lanjutan_11_surat_umum_kerapian.py — Regresi Audit Lanjutan 11:
`app/routes/surat_umum.py::buat()` (Modul 8, generator Surat Umum
administratif) sebelumnya tidak dibungkus try/except sama sekali —
bug persis sama kelasnya dengan yang ditemukan & ditambal di
`routes/surat.py::buat()` pada Audit Lanjutan 10.
"""

import io
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402
from app.routes import surat_umum as su  # noqa: E402

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


client.post(
    "/login",
    data={"username": "kaprodi", "password1": "test1234", "password2": "test1234"},
    follow_redirects=True,
)

# ---------------------------------------------------------------------
# 1. Galat tak terduga di tengah generate dokumen -> redirect + flash
#    ramah, BUKAN 500 mentah.
# ---------------------------------------------------------------------
_asli_get_setting = su._db.get_setting


def _get_setting_gagal_untuk_nama_institusi(conn, key, default=""):
    if key == "nama_institusi":
        raise RuntimeError("simulasi galat")
    return _asli_get_setting(conn, key, default)


with mock.patch.object(su._db, "get_setting", side_effect=_get_setting_gagal_untuk_nama_institusi):
    r = client.post(
        "/surat-umum/buat",
        data={"jenis_surat": "Surat Tugas", "perihal": "Uji Coba Kerapian"},
    )
    check("POST /surat-umum/buat + galat tak terduga -> redirect (bukan 500)", r.status_code == 302)

r_flash = client.get("/surat-umum/", follow_redirects=True)
check(
    "Flash 'Gagal membuat dokumen Surat Tugas' tampil (pesan ramah, bukan traceback)",
    "Gagal membuat dokumen Surat Tugas".encode() in r_flash.data,
)

# ---------------------------------------------------------------------
# 2. Jalur normal (tanpa mock) tetap berhasil -> try/except baru TIDAK
#    menelan jalur sukses; dokumen valid & tercatat di Buku Agenda.
# ---------------------------------------------------------------------
r_ok = client.post(
    "/surat-umum/buat",
    data={"jenis_surat": "Surat Tugas", "perihal": "Uji Coba Jalur Normal", "tujuan": "Dosen ybs"},
)
check("POST /surat-umum/buat (jalur normal) -> 200", r_ok.status_code == 200)

import docx  # noqa: E402

doc = docx.Document(io.BytesIO(r_ok.data))
teks = "\n".join(p.text for p in doc.paragraphs)
check("Dokumen hasil memuat perihal yang benar", "Uji Coba Jalur Normal" in teks)

with app.test_request_context():
    conn = app.get_db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM surat_keluar WHERE perihal='Uji Coba Jalur Normal'"
    ).fetchone()["c"]
    check("Surat jalur normal tercatat di Buku Agenda (surat_keluar)", n == 1)

print("\n=== SELESAI ===")
if FAILS:
    print(f"{len(FAILS)} GAGAL:")
    for f in FAILS:
        print(" -", f)
    sys.exit(1)
print("SEMUA TES LULUS.")
