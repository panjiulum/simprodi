# -*- coding: utf-8 -*-
"""routes/preferensi.py — Preferensi Tampilan (Audit Lanjutan 3).

Aplikasi ini 1 akun/1 komputer (lihat catatan `pengguna` di db.py), jadi
"preferensi pribadi" di sini disimpan sebagai pengaturan aplikasi biasa
lewat get_setting/set_setting (tabel `pengaturan` yang sama dipakai
Identitas & Branding) — bukan per-baris tabel `pengguna` baru, supaya
konsisten dengan pola penyimpanan pengaturan yang sudah ada & langsung
berlaku di semua halaman lewat context_processor (app/__init__.py).

Tiga preferensi di bawah masing-masing benar-benar dipakai (bukan sekadar
tersimpan tanpa efek):
  - pref_densitas    -> class `density-padat` di <body> (style.css)
  - pref_sidebar_mode -> logika default buka/tutup grup sidebar (base.html)
  - pref_agenda_hari  -> rentang "Agenda Mendatang" Dashboard & Pusat
                         Notifikasi (sebelumnya baku 7 hari)
"""

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app import constants as C
from app import db as _db

bp = Blueprint("preferensi", __name__, url_prefix="/preferensi")


@bp.route("/", methods=["GET", "POST"])
def index():
    conn = current_app.get_db()

    if request.method == "POST":
        densitas = request.form.get("pref_densitas", "Nyaman")
        if densitas not in C.PREF_DENSITAS_LIST:
            densitas = "Nyaman"

        sidebar_mode = request.form.get("pref_sidebar_mode", "otomatis")
        if sidebar_mode not in dict(C.PREF_SIDEBAR_MODE_LIST):
            sidebar_mode = "otomatis"

        agenda_hari = request.form.get("pref_agenda_hari", type=int) or 7
        if agenda_hari not in C.PREF_AGENDA_HARI_LIST:
            agenda_hari = 7

        _db.set_setting(conn, "pref_densitas", densitas)
        _db.set_setting(conn, "pref_sidebar_mode", sidebar_mode)
        _db.set_setting(conn, "pref_agenda_hari", str(agenda_hari))
        _db.log(conn, "Ubah Preferensi Tampilan")
        flash("Preferensi tampilan tersimpan.", "ok")
        return redirect(url_for("preferensi.index"))

    nilai = {
        "pref_densitas": _db.get_setting(conn, "pref_densitas", "Nyaman"),
        "pref_sidebar_mode": _db.get_setting(conn, "pref_sidebar_mode", "otomatis"),
        "pref_agenda_hari": int(_db.get_setting(conn, "pref_agenda_hari", "7") or 7),
    }
    return render_template(
        "pengaturan/preferensi.html",
        nilai=nilai,
        PREF_DENSITAS_LIST=C.PREF_DENSITAS_LIST,
        PREF_SIDEBAR_MODE_LIST=C.PREF_SIDEBAR_MODE_LIST,
        PREF_AGENDA_HARI_LIST=C.PREF_AGENDA_HARI_LIST,
    )
