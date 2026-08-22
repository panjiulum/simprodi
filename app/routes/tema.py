# -*- coding: utf-8 -*-
"""routes/tema.py — Tema Tampilan (Audit Lanjutan 3).

Hanya mengganti aksen warna aplikasi (variabel CSS --primary/--primary-dark/
--primary-soft/--violet/--violet-soft lewat atribut `data-theme` di <html>,
lihat blok `html[data-theme=...]` di style.css) — BUKAN mode gelap, supaya
kontras teks & keterbacaan tabel/rekap yang sudah ada tidak berubah sama
sekali di tema manapun. "indigo" = palet asal SIMPRODI, tanpa override.
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

bp = Blueprint("tema", __name__, url_prefix="/tema")


@bp.route("/", methods=["GET", "POST"])
def index():
    conn = current_app.get_db()
    kode_valid = [t["kode"] for t in C.TEMA_WARNA_LIST]

    if request.method == "POST":
        kode = request.form.get("tema_warna", "indigo")
        if kode not in kode_valid:
            kode = "indigo"
        _db.set_setting(conn, "tema_warna", kode)
        _db.log(conn, "Ubah Tema Tampilan", kode)
        flash("Tema tampilan diperbarui.", "ok")
        return redirect(url_for("tema.index"))

    aktif = _db.get_setting(conn, "tema_warna", "indigo")
    if aktif not in kode_valid:
        aktif = "indigo"
    return render_template("pengaturan/tema.html", aktif=aktif, TEMA_WARNA_LIST=C.TEMA_WARNA_LIST)
