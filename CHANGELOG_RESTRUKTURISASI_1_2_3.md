# Restrukturisasi Poin 1–3 (Audit SIMPRODI)

Perubahan pada source code hasil audit sebelumnya, mencakup 3 poin.
Seluruh 26 file `test_*.py` di repo ini (lama + yang diperbarui) lolos
setelah perubahan ini (`python3 test_nama.py` untuk masing-masing, exit
code 0 / "SEMUA TES LULUS").

## Poin 1 — Login Username + Password

- Login sekarang wajib kombinasi **username + password** (sebelumnya
  hanya 1 password bersama).
- File yang berubah: `app/auth_core.py` (fungsi `set_credentials`,
  `verify_credentials`, `get_username`, `set_username`, ditambahkan;
  lockout digeneralisasi lewat parameter `prefix`), `app/routes/auth.py`
  (wizard "buat akun" & form login menambah field username),
  `app/templates/login.html`, `app/routes/pengaturan.py` +
  `app/templates/pengaturan/password.html` (username sekarang juga bisa
  diganti di menu Ubah Username & Password).
- Pesan gagal login **sengaja** tidak membedakan "username salah" vs
  "password salah" (anti *username enumeration*).
- Username dibandingkan case-insensitive (bukan rahasia, hanya
  identitas) — password tetap dibandingkan lewat hash seperti semula.

## Poin 2 — PIN Fitur Krusial

- Modul baru `app/pin_guard.py`: decorator `@perlu_pin` untuk
  menggerbangi route sensitif dengan PIN terpisah dari password login.
- Dipasang di: `pengaturan.import_export`, `pengaturan.import_generik`,
  `pengaturan.import_generik_proses` (menu Import — persis contoh yang
  diminta), dan `backup.restore` (Restore Backup, yang di kodenya
  sendiri sudah disebut endpoint "paling sensitif").
- PIN & password login divalidasi **tidak boleh sama** saat diatur.
- Alur: PIN belum diset -> diarahkan ke `pengaturan.pin_atur`. PIN sudah
  diset tapi sesi belum terverifikasi (atau kedaluwarsa, 15 menit) ->
  diarahkan ke `pengaturan.pin_verifikasi`. Setelah lolos, otomatis
  kembali ke halaman tujuan semula.
- Lockout 5x gagal -> kunci 5 menit, sama seperti login, tapi terhitung
  terpisah (tidak saling mengunci dengan lockout login).
- Halaman baru: `app/templates/pengaturan/pin_atur.html`,
  `app/templates/pengaturan/pin_verifikasi.html`. Tautan baru di sidebar
  ("PIN Fitur Krusial", grup Pengaturan) — lihat `app/templates/base.html`.

## Poin 3 — Edit Kode Tahun Ajaran (Tanpa Fitur Hapus)

- Fungsi baru `db.ubah_kode_tahun_ajaran(conn, ta_id, kode_baru)` di
  `app/db.py` — validasi kode tidak kosong & unik, lalu `UPDATE` kolom
  `kode` saja.
- Aman dilakukan kapan pun (termasuk setelah periode aktif & data
  tersinkron) karena semua tabel anak merujuk lewat
  `tahun_ajaran_id`/`periode_akademik_id` (integer, primary key) —
  **bukan** `kode` (teks) — jadi tidak ada relasi yang putus.
- Aksi baru `ubah_kode_ta` di `pengaturan.tahun_akademik()` (route yang
  sama, tidak ada endpoint baru).
- **Sengaja tidak ada** dan tidak ditambahkan aksi hapus tahun
  ajaran/periode di mana pun.
- UI: tombol "✎ Ubah Kode" di setiap kartu tahun ajaran, lihat
  `app/templates/pengaturan/tahun_akademik.html`.

## File Test yang Ikut Diperbarui

Semua file test yang login lewat `client.post("/login", data={...})`
diperbarui menambahkan field `username` (kontrak login berubah), dan
4 file yang memanggil route Import/Restore ditambah 1 baris setup PIN
setelah login. `test_login.py` ditulis ulang total untuk mencakup
skenario baru (username+password, PIN, edit kode tahun ajaran) —
30 pengecekan, semua lolos. `test_sidebar.py` diperbarui jumlah tautan
sidebar (57 -> 58, tautan PIN baru) dan menambah setup PIN sebelum
pengecekan "semua tautan sidebar 200".
