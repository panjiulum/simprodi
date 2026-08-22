# -*- coding: utf-8 -*-
"""
auth_core.py — Logika hash password & PIN (porting murni dari auth.py versi
desktop, tanpa bagian dialog Tkinter). Password & PIN disimpan sebagai hash
(PBKDF2-SHA256 + salt acak) di tabel 'pengaturan' pada file .db yang sama —
tidak ada data yang dikirim keluar perangkat.

Restrukturisasi poin 1 — Login Username + Password:
Sebelumnya login hanya memakai 1 password bersama. Sekarang wajib kombinasi
USERNAME + PASSWORD. Username BUKAN rahasia (hanya identitas, dibandingkan
case-insensitive & disimpan apa adanya di kunci `auth_username`) — yang
tetap di-hash hanya password, persis mekanisme lama, supaya tidak ada
migrasi skema tambahan (masih 1 file .db, kunci baru di tabel `pengaturan`
yang sudah ada).

Restrukturisasi poin 2 — PIN Fitur Krusial:
PIN tambahan (terpisah total dari password login — hash & salt sendiri,
kunci pengaturan sendiri: `pin_hash`/`pin_salt`) untuk membuka menu
sensitif seperti Import Data & Restore Backup. Lihat app/pin_guard.py
untuk decorator `@perlu_pin` yang memakai fungsi-fungsi PIN di bawah.

Mekanisme lockout percobaan-gagal yang sebelumnya khusus login sekarang
digeneralisasi lewat parameter `prefix` (default "login"), supaya
verifikasi PIN bisa memakai ulang logic yang identik (5x gagal -> kunci
5 menit) tanpa menduplikasi kode — percobaan gagal login dan percobaan
gagal PIN dihitung & dikunci terpisah (prefix "login" vs "pin"), supaya
1 tidak ikut mengunci yang lain.
"""

import hashlib
import os
import time

from app import db

ITERASI_HASH = 200_000

MAKS_PERCOBAAN_GAGAL = 5
DURASI_LOCKOUT_DETIK = 5 * 60  # 5 menit


def _now_ts():
    return int(time.time())


def cek_lockout(conn, prefix="login"):
    """Mengembalikan sisa detik lockout untuk `prefix` (login/pin) — 0
    kalau boleh mencoba sekarang."""
    hingga = db.get_setting(conn, f"{prefix}_lockout_hingga", "0")
    try:
        hingga = int(hingga)
    except ValueError:
        hingga = 0
    return max(hingga - _now_ts(), 0)


def catat_percobaan_gagal(conn, prefix="login"):
    """Tambah hitungan gagal untuk `prefix`; begitu mencapai ambang,
    kunci sementara (khusus prefix itu saja)."""
    key_gagal = f"{prefix}_percobaan_gagal"
    key_hingga = f"{prefix}_lockout_hingga"
    gagal = db.get_setting(conn, key_gagal, "0")
    try:
        gagal = int(gagal)
    except ValueError:
        gagal = 0
    gagal += 1
    db.set_setting(conn, key_gagal, str(gagal))
    if gagal >= MAKS_PERCOBAAN_GAGAL:
        db.set_setting(conn, key_hingga, str(_now_ts() + DURASI_LOCKOUT_DETIK))
        db.set_setting(conn, key_gagal, "0")


def reset_percobaan_gagal(conn, prefix="login"):
    db.set_setting(conn, f"{prefix}_percobaan_gagal", "0")
    db.set_setting(conn, f"{prefix}_lockout_hingga", "0")


def _hash(rahasia, salt=None):
    salt = salt or os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", rahasia.encode("utf-8"), bytes.fromhex(salt), ITERASI_HASH)
    return h.hex(), salt


# --------------------------------------------------------- Username & Password
def has_credentials(conn):
    """True kalau akun admin (username + password) sudah pernah dibuat.
    Dipakai routes/auth.py untuk menentukan tampilan wizard setup awal
    vs form login normal."""
    return bool(db.get_setting(conn, "auth_username", "")) and bool(
        db.get_setting(conn, "auth_hash", "")
    )


def has_password(conn):
    """Dipertahankan terpisah dari has_credentials() untuk tempat yang
    hanya perlu memastikan password sudah pernah diset (mis. alur ubah
    password di Pengaturan tidak perlu tahu soal username)."""
    return bool(db.get_setting(conn, "auth_hash", ""))


def get_username(conn):
    return db.get_setting(conn, "auth_username", "")


def set_credentials(conn, username, password):
    """Membuat/mengganti akun admin (username + password) sekaligus —
    dipakai saat setup pertama kali."""
    db.set_setting(conn, "auth_username", username.strip())
    h, salt = _hash(password)
    db.set_setting(conn, "auth_hash", h)
    db.set_setting(conn, "auth_salt", salt)


def set_username(conn, username):
    """Ganti username saja, password tidak berubah."""
    db.set_setting(conn, "auth_username", username.strip())


def set_password(conn, password):
    """Ganti password saja, username tidak berubah."""
    h, salt = _hash(password)
    db.set_setting(conn, "auth_hash", h)
    db.set_setting(conn, "auth_salt", salt)


def verify_password(conn, password):
    salt = db.get_setting(conn, "auth_salt", "")
    stored = db.get_setting(conn, "auth_hash", "")
    if not stored or not salt:
        return False
    h, _ = _hash(password, salt)
    return h == stored


def verify_credentials(conn, username, password):
    """Kombinasi username + password wajib cocok berdua (Restrukturisasi
    poin 1). Username dibandingkan case-insensitive & trim spasi (bukan
    rahasia, hanya identitas); password tetap dibandingkan lewat hash.
    Pesan gagal di routes/auth.py SENGAJA tidak membedakan mana yang
    salah (username atau password) supaya tidak membocorkan info ke
    penebak (mencegah username enumeration)."""
    username_tersimpan = get_username(conn)
    if not username_tersimpan:
        return False
    if username.strip().lower() != username_tersimpan.strip().lower():
        return False
    return verify_password(conn, password)


# --------------------------------------------------------- PIN (fitur krusial)
def has_pin(conn):
    return bool(db.get_setting(conn, "pin_hash", ""))


def set_pin(conn, pin):
    h, salt = _hash(pin)
    db.set_setting(conn, "pin_hash", h)
    db.set_setting(conn, "pin_salt", salt)


def verify_pin(conn, pin):
    salt = db.get_setting(conn, "pin_salt", "")
    stored = db.get_setting(conn, "pin_hash", "")
    if not stored or not salt:
        return False
    h, _ = _hash(pin, salt)
    return h == stored
