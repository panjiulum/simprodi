import os, sys, tempfile, io
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
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)

# ---------------------------------------------------------------------
# 1. State awal: belum ada akun -> form "buat akun" (is_baru), SEKARANG
#    dengan field username (Restrukturisasi poin 1: kombinasi
#    username + password, bukan password tunggal seperti sebelumnya).
# ---------------------------------------------------------------------
r = client.get("/login")
check("GET /login (belum ada akun) -> 200", r.status_code == 200)
check("Form buat akun (username/password1/password2) tampil",
      b'name="username"' in r.data and b"password1" in r.data and b"password2" in r.data)
check("Tanpa splash/AI decorative text dari demo SITIPRO", b"Loading AI Engine" not in r.data and b"Windows Hello" not in r.data)

# Logo belum ada -> endpoint logo-preview 404, BUKAN redirect ke /login (exemption gerbang login)
r_logo = client.get("/pengaturan/logo-preview")
check("Logo-preview belum ada logo -> 404 (bukan redirect ke login)", r_logo.status_code == 404)

# ---------------------------------------------------------------------
# 2. Validasi form buat akun (username kosong / password pendek / tidak cocok)
# ---------------------------------------------------------------------
r_nouser = client.post("/login", data={"username": "", "password1": "13572468", "password2": "13572468"}, follow_redirects=True)
check("Username kosong ditolak", "Username wajib diisi".encode() in r_nouser.data)

r_short = client.post("/login", data={"username": "admin", "password1": "ab", "password2": "ab"}, follow_redirects=True)
check("Password < 4 karakter ditolak", "minimal 4 karakter".encode() in r_short.data)

r_mismatch = client.post("/login", data={"username": "admin", "password1": "13572468", "password2": "beda1234"}, follow_redirects=True)
check("Konfirmasi password tidak sama ditolak", "tidak sama".encode() in r_mismatch.data)

# ---------------------------------------------------------------------
# 3. Buat akun (username + password) -> otomatis login & masuk dashboard
# ---------------------------------------------------------------------
r_ok = client.post("/login", data={"username": "kaprodi", "password1": "13572468", "password2": "13572468"}, follow_redirects=True)
check("Buat akun berhasil -> masuk ke dashboard", r_ok.status_code == 200 and r_ok.request.path == "/")

# ---------------------------------------------------------------------
# 4. Logout -> state normal (akun sudah ada) -> form username + password
# ---------------------------------------------------------------------
client.get("/logout")
r_normal = client.get("/login")
check("GET /login (akun sudah ada) -> 200", r_normal.status_code == 200)
check("Form login normal (username + password, TANPA password1/2)",
      b'name="username"' in r_normal.data and b'name="password"' in r_normal.data and b'name="password1"' not in r_normal.data)
check("Judul 'Masuk ke SIMPRODI' tampil", "Masuk ke SIMPRODI".encode() in r_normal.data)

r_wrong_pw = client.post("/login", data={"username": "kaprodi", "password": "salah-password"}, follow_redirects=True)
check("Password salah ditolak dengan pesan error", "Username atau password salah".encode() in r_wrong_pw.data)

r_wrong_user = client.post("/login", data={"username": "bukan-kaprodi", "password": "13572468"}, follow_redirects=True)
check("Username salah (password benar) tetap ditolak — kombinasi wajib cocok berdua",
      "Username atau password salah".encode() in r_wrong_user.data)

r_login = client.post("/login", data={"username": "kaprodi", "password": "13572468"}, follow_redirects=True)
check("Login dengan username+password benar -> masuk ke dashboard", r_login.status_code == 200 and r_login.request.path == "/")

# ---------------------------------------------------------------------
# 4b. Login username dibandingkan case-insensitive (bukan rahasia)
# ---------------------------------------------------------------------
client.get("/logout")
r_login_caps = client.post("/login", data={"username": "KAPRODI", "password": "13572468"}, follow_redirects=True)
check("Username case-insensitive tetap berhasil login", r_login_caps.status_code == 200 and r_login_caps.request.path == "/")

client.get("/logout")
client.post("/login", data={"username": "kaprodi", "password": "13572468"}, follow_redirects=True)

# ---------------------------------------------------------------------
# 5. Restrukturisasi poin 2 — PIN Fitur Krusial: menu Import terkunci
#    sampai PIN diatur & diverifikasi.
# ---------------------------------------------------------------------
r_import_first = client.get("/pengaturan/import-export", follow_redirects=True)
check("Menu Import (belum ada PIN) -> diarahkan ke halaman Atur PIN",
      "Atur PIN".encode() in r_import_first.data or "PIN Fitur Krusial".encode() in r_import_first.data)

r_pin_pw_sama = client.post("/pengaturan/pin", data={"pin1": "13572468", "pin2": "13572468"}, follow_redirects=True)
check("PIN sama dengan password login ditolak", "tidak boleh sama dengan password".encode() in r_pin_pw_sama.data)

r_pin_set = client.post("/pengaturan/pin", data={"pin1": "9999", "pin2": "9999"}, follow_redirects=True)
check("PIN berhasil diatur", "PIN berhasil disimpan".encode() in r_pin_set.data)

r_import_after_pin_set = client.get("/pengaturan/import-export")
check("Setelah atur PIN, langsung diarahkan ke tujuan semula (Import) tanpa verifikasi ulang",
      r_import_after_pin_set.status_code == 200 and b"Import" in r_import_after_pin_set.data)

client.get("/logout")
client.post("/login", data={"username": "kaprodi", "password": "13572468"}, follow_redirects=True)

r_import_locked = client.get("/pengaturan/import-export", follow_redirects=True)
check("Sesi baru (PIN belum diverifikasi ulang) -> menu Import minta Verifikasi PIN",
      "Verifikasi PIN".encode() in r_import_locked.data)

r_pin_salah = client.post("/pengaturan/pin/verifikasi", data={"pin": "0000"}, follow_redirects=True)
check("PIN salah ditolak", "PIN salah".encode() in r_pin_salah.data)

r_pin_benar = client.post("/pengaturan/pin/verifikasi", data={"pin": "9999"}, follow_redirects=True)
check("PIN benar -> lolos ke menu Import", r_pin_benar.status_code == 200 and "Import".encode() in r_pin_benar.data)

r_backup_page = client.get("/pengaturan/backup/")
check("Halaman Backup & Restore sendiri TETAP bisa dibuka tanpa PIN (hanya aksi restore yang digerbangi)",
      r_backup_page.status_code == 200)

# ---------------------------------------------------------------------
# 6. Restrukturisasi poin 3 — Edit kode Tahun Ajaran (tanpa fitur hapus)
# ---------------------------------------------------------------------
client.post("/pengaturan/tahun-akademik", data={"aksi": "buka_tahun", "kode": "2025/2025", "aktifkan": "Ganjil"}, follow_redirects=True)
r_ta = client.get("/pengaturan/tahun-akademik")
ta_row_ada = b"2025/2025" in r_ta.data
check("Tahun ajaran 2025/2025 (sengaja salah ketik) berhasil dibuat", ta_row_ada)

check("TIDAK ADA aksi hapus tahun ajaran/periode di halaman ini",
      b'value="hapus_tahun_ajaran"' not in r_ta.data and b'value="hapus_periode"' not in r_ta.data)

import re
m = re.search(rb'name="ta_id" value="(\d+)"[^>]*>\s*<input name="kode_baru" value="2025/2025"', r_ta.data)
check("Form Ubah Kode ditemukan untuk 2025/2025", m is not None)

if m:
    ta_id = m.group(1).decode()
    r_ubah = client.post("/pengaturan/tahun-akademik", data={
        "aksi": "ubah_kode_ta", "ta_id": ta_id, "kode_baru": "2025/2026",
    }, follow_redirects=True)
    check("Ubah kode ke 2025/2026 berhasil", "diperbarui".encode() in r_ubah.data)
    check("Kode baru 2025/2026 tampil", b"2025/2026" in r_ubah.data)
    check("Kode lama 2025/2025 tidak tampil lagi sebagai kode tahun ajaran", b"2025/2025" not in r_ubah.data)

    # buka tahun ajaran lain lalu coba ubah ke kode yang sudah dipakai -> ditolak
    client.post("/pengaturan/tahun-akademik", data={"aksi": "buka_tahun", "kode": "2026/2027", "aktifkan": None}, follow_redirects=True)
    r_ta2 = client.get("/pengaturan/tahun-akademik")
    m2 = re.search(rb'name="ta_id" value="(\d+)"[^>]*>\s*<input name="kode_baru" value="2026/2027"', r_ta2.data)
    if m2:
        ta_id2 = m2.group(1).decode()
        r_bentrok = client.post("/pengaturan/tahun-akademik", data={
            "aksi": "ubah_kode_ta", "ta_id": ta_id2, "kode_baru": "2025/2026",
        }, follow_redirects=True)
        check("Ubah kode ke kode yang sudah dipakai tahun ajaran lain ditolak",
              "sudah dipakai tahun ajaran lain".encode() in r_bentrok.data)

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
