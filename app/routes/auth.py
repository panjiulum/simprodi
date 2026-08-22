# -*- coding: utf-8 -*-
"""routes/auth.py — Login / logout.

Restrukturisasi poin 1: login sekarang memakai kombinasi USERNAME +
PASSWORD (sebelumnya 1 password bersama tanpa username). Alur wizard
setup pertama kali dipertahankan sama seperti semula (kalau akun admin
belum pernah dibuat, tampilkan form "buat akun" dulu) — hanya field-nya
yang bertambah (username + password, bukan password saja).
"""

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app import auth_core
from app import db as _db

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    conn = current_app.get_db()
    is_baru = not auth_core.has_credentials(conn)
    lockout_sisa = auth_core.cek_lockout(conn, prefix="login") if not is_baru else 0

    if request.method == "POST" and lockout_sisa:
        flash(
            f"Terlalu banyak percobaan gagal. Coba lagi dalam {lockout_sisa // 60 + 1} menit.",
            "error",
        )
    elif request.method == "POST":
        if is_baru:
            username = request.form.get("username", "").strip()
            pw1 = request.form.get("password1", "")
            pw2 = request.form.get("password2", "")
            if not username:
                flash("Username wajib diisi.", "error")
            elif len(pw1) < 4:
                flash("Password minimal 4 karakter.", "error")
            elif pw1 != pw2:
                flash("Konfirmasi password tidak sama.", "error")
            else:
                auth_core.set_credentials(conn, username, pw1)
                session["logged_in"] = True
                _db.log(conn, "Login", f"Akun admin dibuat pertama kali ({username})")
                return redirect(url_for("dashboard.index"))
        else:
            username = request.form.get("username", "")
            pw = request.form.get("password", "")
            if auth_core.verify_credentials(conn, username, pw):
                auth_core.reset_percobaan_gagal(conn, prefix="login")
                session["logged_in"] = True
                _db.log(conn, "Login", "Login berhasil")
                return redirect(url_for("dashboard.index"))
            else:
                auth_core.catat_percobaan_gagal(conn, prefix="login")
                sisa = auth_core.cek_lockout(conn, prefix="login")
                if sisa:
                    flash(
                        f"Terlalu banyak percobaan gagal. Login dikunci {sisa // 60 + 1} menit.",
                        "error",
                    )
                else:
                    # Sengaja tidak membedakan "username salah" vs "password
                    # salah" supaya tidak membocorkan info ke penebak.
                    flash("Username atau password salah.", "error")

    return render_template("login.html", is_baru=is_baru, lockout_sisa=lockout_sisa)


@bp.route("/logout")
def logout():
    # session.clear() menghapus SEMUA isi session, termasuk pesan flash yg
    # baru saja di-flash oleh aksi sebelum redirect ke sini (mis. restore
    # backup) — flash disimpan lewat mekanisme session juga. Simpan &
    # kembalikan pesan flash-nya supaya tetap tampil di halaman login,
    # sisanya (status login, verifikasi PIN, dsb) tetap bersih seperti semula.
    pesan_flash = session.get("_flashes")
    session.clear()
    if pesan_flash:
        session["_flashes"] = pesan_flash
    return redirect(url_for("auth.login"))
