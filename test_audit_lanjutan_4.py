# -*- coding: utf-8 -*-
"""
test_audit_lanjutan_4.py — Uji Pengembangan Lanjutan 4 (Preferensi
Tampilan, Pusat Notifikasi & Tema Tampilan).

Latar belakang: 3 menu di grup "⚙️ Pengaturan" sebelumnya diarahkan ke
routes/roadmap.py (placeholder "dalam pengembangan") — audit ini
menutup gap tsb dengan 3 modul nyata:
  - Preferensi Tampilan (routes/preferensi.py): densitas tabel, mode
    default grup sidebar, rentang hari Agenda Mendatang — semuanya
    benar-benar dipakai (bukan sekadar tersimpan tanpa efek).
  - Pusat Notifikasi (routes/notifikasi.py): mengumpulkan SEMUA sumber
    reminder yang sudah ada (get_notifikasi, acara_mendatang,
    sdm_reminder_semua BARU di logic.py, tridharma_reminder_tenggat,
    mitra_reminder_dokumen, ami_reminder_tenggat) jadi satu daftar +
    form ambang hari per kategori.
  - Tema Tampilan (routes/tema.py): aksen warna via atribut data-theme,
    tanpa mengubah kontras/keterbacaan (bukan mode gelap).

Tidak diikutkan di paket produksi (murni verifikasi pengembangan).
"""
import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402

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

# ---------------------------------------------------------------------
# 1. Preferensi Tampilan — tersimpan & benar-benar dipakai
# ---------------------------------------------------------------------
r = client.get("/preferensi/")
check("GET /preferensi/ -> 200", r.status_code == 200)

r = client.post("/preferensi/", data={
    "pref_densitas": "Padat", "pref_sidebar_mode": "buka_semua", "pref_agenda_hari": "14",
}, follow_redirects=True)
check("POST /preferensi/ (simpan) -> 200", r.status_code == 200)

home = client.get("/").data
check("Densitas 'Padat' -> class density-padat di <body>", b"density-padat" in home)
check("Mode sidebar 'buka_semua' -> data-sidebar-mode di <body>", b'data-sidebar-mode="buka_semua"' in home)

with app.app_context():
    conn = app.get_db()
    besok = (date.today() + timedelta(days=10)).isoformat()
    conn.execute(
        "INSERT INTO kalender_akademik(judul, kategori, tgl_mulai, status) VALUES(?,?,?,?)",
        ("Rapat Uji Prodi", "Akademik", besok, "Terjadwal"),
    )
    conn.commit()
home2 = client.get("/").data
check("Rentang Agenda 14 hari -> agenda H+10 ikut tampil di Dashboard", b"Rapat Uji Prodi" in home2)
check("Label '14 hari ke depan' tampil dinamis di kartu Agenda Kalender", b"14 hari ke depan" in home2)

# kembalikan ke baku untuk tidak mengganggu tes berikutnya
client.post("/preferensi/", data={"pref_densitas": "Nyaman", "pref_sidebar_mode": "otomatis", "pref_agenda_hari": "7"})

# ---------------------------------------------------------------------
# 2. Tema Tampilan — tersimpan & diterapkan lewat data-theme
# ---------------------------------------------------------------------
r = client.get("/tema/")
check("GET /tema/ -> 200", r.status_code == 200)
check("Menampilkan 6 pilihan aksen warna", r.data.count(b"tema-swatch") >= 6)

r = client.post("/tema/", data={"tema_warna": "rose"}, follow_redirects=True)
check("POST /tema/ (simpan tema rose) -> 200", r.status_code == 200)
check("<html data-theme=\"rose\"> diterapkan di semua halaman", b'data-theme="rose"' in client.get("/").data)

r = client.post("/tema/", data={"tema_warna": "kode-tidak-valid"}, follow_redirects=True)
check("Kode tema tidak dikenal -> jatuh ke 'indigo' (bukan error)", b'data-theme="indigo"' in client.get("/").data)

# ---------------------------------------------------------------------
# 3. Pusat Notifikasi — agregasi lintas modul + ambang bisa diatur
# ---------------------------------------------------------------------
with app.app_context():
    conn = app.get_db()
    # Dosen + luaran dgn masa_berlaku sudah lewat -> harus muncul sbg 'danger'
    conn.execute("INSERT INTO dosen(nidn, nama) VALUES('9999999999','Dr. Uji Notifikasi')")
    dosen_id = conn.execute("SELECT id FROM dosen WHERE nidn='9999999999'").fetchone()["id"]
    lewat = (date.today() - timedelta(days=5)).isoformat()
    conn.execute(
        "INSERT INTO luaran_dosen(dosen_id, jenis_luaran, judul, masa_berlaku) VALUES(?,?,?,?)",
        (dosen_id, "Sertifikat", "Sertifikat Uji Kadaluarsa", lewat),
    )
    conn.commit()

r = client.get("/notifikasi/")
check("GET /notifikasi/ -> 200", r.status_code == 200)
check("Item SDM kadaluarsa (lewat tenggat) muncul di Pusat Notifikasi", b"Sertifikat Uji Kadaluarsa" in r.data)
check("Kartu ringkasan jumlah (notif-summary) tampil", b"notif-summary" in r.data)

r_danger = client.get("/notifikasi/?level=danger")
check("Filter level=danger -> item kadaluarsa tetap tampil", b"Sertifikat Uji Kadaluarsa" in r_danger.data)
r_info = client.get("/notifikasi/?level=info")
check("Filter level=info -> item danger tidak ikut tampil", b"Sertifikat Uji Kadaluarsa" not in r_info.data)

r = client.post("/notifikasi/", data={
    "notif_ambang_sdm": "3", "notif_ambang_tridharma": "14",
    "notif_ambang_mitra": "30", "notif_ambang_ami": "14",
}, follow_redirects=True)
check("POST ambang notifikasi -> 200 & nilai baru (3) tersimpan di form", r.status_code == 200 and b'value="3"' in r.data)

# ---------------------------------------------------------------------
# 4. Badge lonceng topbar & kaitan dgn ringkasan notifikasi
# ---------------------------------------------------------------------
r = client.get("/")
check("Ikon lonceng topbar mengarah ke notifikasi.index (bukan lagi kalender.index)",
      b'href="/notifikasi/"' in r.data)
check("Badge jumlah tampil di ikon lonceng saat ada item perlu perhatian",
      b"topbar-icon-badge" in r.data)

# ---------------------------------------------------------------------
# 5. Regresi — modul lama tidak tersentuh (Dashboard, SDM, Kalender)
# ---------------------------------------------------------------------
check("Dashboard tetap 200 setelah semua perubahan di atas", client.get("/").status_code == 200)
check("Halaman SDM tetap 200 (regresi)", client.get("/sdm/").status_code == 200)
check("Halaman Kalender tetap 200 (regresi)", client.get("/kalender/").status_code == 200)
check("Halaman Kerja Sama tetap 200 (regresi)", client.get("/kerjasama/").status_code == 200)

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
