# -*- coding: utf-8 -*-
"""routes/ruangan.py — CRUD Data Ruangan (dipakai untuk deteksi bentrok jadwal)."""

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app import db as _db
from app import error_utils as EH

bp = Blueprint("ruangan", __name__, url_prefix="/ruangan")


@bp.route("/")
def list_view():
    conn = current_app.get_db()
    rows = conn.execute("SELECT * FROM ruangan ORDER BY nama").fetchall()
    edit_id = request.args.get("edit", type=int)
    edit_row = None
    if edit_id:
        edit_row = conn.execute("SELECT * FROM ruangan WHERE id=?", (edit_id,)).fetchone()
    return render_template("ruangan.html", rows=rows, edit_row=edit_row)


@bp.route("/simpan", methods=["POST"])
def simpan():
    conn = current_app.get_db()
    f = request.form
    rid = f.get("id", type=int)
    nama = f.get("nama", "").strip()
    if not nama:
        flash("Nama ruangan wajib diisi.", "error")
        return redirect(url_for("ruangan.list_view"))
    try:
        if rid:
            conn.execute(
                "UPDATE ruangan SET nama=?, kapasitas=?, keterangan=? WHERE id=?",
                (nama, f.get("kapasitas", ""), f.get("keterangan", ""), rid),
            )
            flash("Ruangan diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO ruangan(nama,kapasitas,keterangan) VALUES(?,?,?)",
                (nama, f.get("kapasitas", ""), f.get("keterangan", "")),
            )
            flash(f"Ruangan {nama} ditambahkan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Ruangan", nama)
    except Exception as e:
        EH.flash_gagal_simpan(e, "Nama ruangan mungkin sudah ada")
    return redirect(url_for("ruangan.list_view"))


@bp.route("/<int:rid>/hapus", methods=["POST"])
def hapus(rid):
    conn = current_app.get_db()
    conn.execute("DELETE FROM ruangan WHERE id=?", (rid,))
    conn.commit()
    flash("Ruangan dihapus.", "ok")
    return redirect(url_for("ruangan.list_view"))
