# -*- coding: utf-8 -*-
"""routes/kalender.py — Modul 5: Akademik Operasional & Kalender.

Agenda akademik prodi (ujian, rapat, libur, deadline, kegiatan) yang tadinya
tersebar di POM (Electron/JSON) & tidak nyambung dengan modul TA — di sini
disatukan dalam 1 tabel `kalender_akademik` dan 1 kalender bulanan, dengan
pola CRUD (split-table/split-form) yang identik dengan `ruangan.py` supaya
konsisten dengan modul lama.

Tampilan kalender bulanan dibangun murni dari `calendar` (stdlib), tanpa
dependensi baru.
"""

import calendar
from datetime import date, datetime, timedelta

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
from app import error_utils as EH

bp = Blueprint("kalender", __name__, url_prefix="/kalender")

BULAN_NAMA = [
    "",
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
]
HARI_NAMA = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]


def _parse_iso(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def acara_mendatang(conn, hari=7):
    """Dipakai halaman kalender & bisa dipakai modul lain (mis. Dashboard)
    tanpa perlu mengubah logic.py lama — daftar acara H-0 s/d H+`hari`,
    status masih 'Terjadwal'."""
    today = date.today()
    batas = today + timedelta(days=hari)
    rows = conn.execute(
        "SELECT * FROM kalender_akademik WHERE status='Terjadwal' ORDER BY tgl_mulai"
    ).fetchall()
    out = []
    for r in rows:
        d = _parse_iso(r["tgl_mulai"])
        if d and today <= d <= batas:
            out.append(r)
    return out


@bp.route("/")
def index():
    conn = current_app.get_db()
    today = date.today()
    tahun = request.args.get("tahun", type=int) or today.year
    bulan = request.args.get("bulan", type=int) or today.month
    if bulan < 1:
        bulan, tahun = 12, tahun - 1
    elif bulan > 12:
        bulan, tahun = 1, tahun + 1

    kategori_filter = request.args.get("kategori", "")
    q = "SELECT * FROM kalender_akademik"
    params = []
    if kategori_filter:
        q += " WHERE kategori=?"
        params.append(kategori_filter)
    q += " ORDER BY tgl_mulai, jam"
    semua = conn.execute(q, params).fetchall()

    # Kelompokkan per tanggal (tgl_mulai) untuk sel-sel kalender bulan ini
    per_tanggal = {}
    for r in semua:
        d = _parse_iso(r["tgl_mulai"])
        if d and d.year == tahun and d.month == bulan:
            per_tanggal.setdefault(d.day, []).append(r)

    cal = calendar.Calendar(firstweekday=0)  # Senin
    minggu_list = cal.monthdayscalendar(tahun, bulan)

    edit_id = request.args.get("edit", type=int)
    edit_row = None
    if edit_id:
        edit_row = conn.execute("SELECT * FROM kalender_akademik WHERE id=?", (edit_id,)).fetchone()

    daftar_akan_datang = acara_mendatang(conn, hari=14)

    prev_b, prev_t = (12, tahun - 1) if bulan == 1 else (bulan - 1, tahun)
    next_b, next_t = (1, tahun + 1) if bulan == 12 else (bulan + 1, tahun)

    return render_template(
        "kalender.html",
        tahun=tahun,
        bulan=bulan,
        nama_bulan=BULAN_NAMA[bulan],
        hari_nama=HARI_NAMA,
        minggu_list=minggu_list,
        per_tanggal=per_tanggal,
        today=today,
        prev_b=prev_b,
        prev_t=prev_t,
        next_b=next_b,
        next_t=next_t,
        semua=semua,
        edit_row=edit_row,
        kategori_list=C.KATEGORI_KALENDER_LIST,
        status_list=C.STATUS_KALENDER_LIST,
        kategori_filter=kategori_filter,
        warna_kategori=C.WARNA_KATEGORI_KALENDER,
        daftar_akan_datang=daftar_akan_datang,
    )


@bp.route("/simpan", methods=["POST"])
def simpan():
    conn = current_app.get_db()
    f = request.form
    rid = f.get("id", type=int)
    judul = f.get("judul", "").strip()
    tgl_mulai = f.get("tgl_mulai", "").strip()
    if not judul or not tgl_mulai:
        flash("Judul dan Tanggal Mulai wajib diisi.", "error")
        return redirect(url_for("kalender.index"))

    data = (
        judul,
        f.get("kategori", "Akademik"),
        tgl_mulai,
        f.get("tgl_selesai", "").strip() or None,
        f.get("jam", "").strip(),
        f.get("lokasi", "").strip(),
        f.get("deskripsi", "").strip(),
        f.get("status", "Terjadwal"),
        f.get("pengingat_hari", type=int) or 3,
    )
    try:
        if rid:
            conn.execute(
                "UPDATE kalender_akademik SET judul=?, kategori=?, tgl_mulai=?, tgl_selesai=?, "
                "jam=?, lokasi=?, deskripsi=?, status=?, pengingat_hari=? WHERE id=?",
                (*data, rid),
            )
            flash("Agenda diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO kalender_akademik(judul, kategori, tgl_mulai, tgl_selesai, jam, "
                "lokasi, deskripsi, status, pengingat_hari) VALUES(?,?,?,?,?,?,?,?,?)",
                data,
            )
            flash("Agenda ditambahkan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Agenda Kalender", judul)
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan")

    d = _parse_iso(tgl_mulai) or date.today()
    return redirect(url_for("kalender.index", tahun=d.year, bulan=d.month))


@bp.route("/<int:kid>/hapus", methods=["POST"])
def hapus(kid):
    conn = current_app.get_db()
    conn.execute("DELETE FROM kalender_akademik WHERE id=?", (kid,))
    conn.commit()
    _db.log(conn, "Hapus Agenda Kalender", str(kid))
    flash("Agenda dihapus.", "ok")
    return redirect(url_for("kalender.index"))
