# -*- coding: utf-8 -*-
"""routes/dokumen.py — Modul 7: Document Center.

Arsip dokumen prodi (SK, MoU, kurikulum, akreditasi, dll) offline —
file fisik disimpan di ~/SistemSkripsi/dokumen/, path & metadatanya di
tabel `dokumen`. Pola penyimpanan file mengikuti upload logo di
`pengaturan.py` (secure_filename + folder tetap di luar direktori
aplikasi, supaya aman dibuka lagi setelah update versi PyInstaller).
"""

import os
import uuid

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

from app import constants as C
from app import db as _db

bp = Blueprint("dokumen", __name__, url_prefix="/dokumen")


def _folder():
    folder = os.path.join(_db.home_dir(), "SistemSkripsi", "dokumen")
    os.makedirs(folder, exist_ok=True)
    return folder


@bp.route("/")
def index():
    conn = current_app.get_db()
    kategori_filter = request.args.get("kategori", "")
    cari = request.args.get("cari", "").strip()

    q = "SELECT * FROM dokumen WHERE 1=1"
    params = []
    if kategori_filter:
        q += " AND kategori=?"
        params.append(kategori_filter)
    if cari:
        q += " AND (judul LIKE ? OR nomor_dokumen LIKE ? OR sumber_instansi LIKE ?)"
        like = f"%{cari}%"
        params += [like, like, like]
    q += " ORDER BY diunggah_pada DESC"
    rows = conn.execute(q, params).fetchall()

    jumlah_per_kategori = {
        r["kategori"]: r["c"]
        for r in conn.execute(
            "SELECT kategori, COUNT(*) c FROM dokumen GROUP BY kategori"
        ).fetchall()
    }
    # Audit UI/UX — total dokumen keseluruhan HARUS lepas dari filter yang
    # sedang aktif ("{{ total }} dokumen tersimpan" di judul halaman adalah
    # ringkasan arsip, bukan hasil pencarian). Sebelum perbaikan ini nilai
    # `total` dihitung dari len(rows) (hasil SELECT yang sudah difilter
    # kategori/cari), sehingga subjudul halaman ikut berubah/menyusut
    # setiap kali pengguna memfilter atau mencari — di file ini juga ada
    # rekayasa terpisah di sisi template (`jumlah_per_kategori.values()|sum`)
    # yang justru membuktikan `total` di sini sudah salah sejak awal.
    total_keseluruhan = sum(jumlah_per_kategori.values())
    kategori_terbanyak = (
        max(jumlah_per_kategori, key=jumlah_per_kategori.get) if jumlah_per_kategori else None
    )
    total_ukuran_mb = round(
        (
            conn.execute("SELECT COALESCE(SUM(ukuran_kb),0) s FROM dokumen").fetchone()["s"]
            or 0
        )
        / 1024,
        1,
    )
    bulan_ini = conn.execute(
        "SELECT COUNT(*) c FROM dokumen WHERE strftime('%Y-%m', diunggah_pada)=strftime('%Y-%m','now','localtime')"
    ).fetchone()["c"]

    return render_template(
        "dokumen.html",
        rows=rows,
        kategori_list=C.KATEGORI_DOKUMEN_LIST,
        kategori_filter=kategori_filter,
        cari=cari,
        jumlah_per_kategori=jumlah_per_kategori,
        total=total_keseluruhan,
        total_hasil=len(rows),
        kategori_terbanyak=kategori_terbanyak,
        total_ukuran_mb=total_ukuran_mb,
        bulan_ini=bulan_ini,
    )


@bp.route("/unggah", methods=["POST"])
def unggah():
    conn = current_app.get_db()
    f = request.form
    judul = f.get("judul", "").strip()
    file = request.files.get("file_dokumen")

    if not judul:
        flash("Judul dokumen wajib diisi.", "error")
        return redirect(url_for("dokumen.index"))
    if not file or not file.filename:
        flash("Pilih file dokumen terlebih dahulu.", "error")
        return redirect(url_for("dokumen.index"))

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in C.EKSTENSI_DOKUMEN_DIIZINKAN:
        flash(
            f"Format .{ext} tidak diizinkan. Format yang didukung: "
            f"{', '.join(sorted(C.EKSTENSI_DOKUMEN_DIIZINKAN))}.",
            "error",
        )
        return redirect(url_for("dokumen.index"))

    nama_asli = secure_filename(file.filename)
    nama_unik = f"{uuid.uuid4().hex[:12]}_{nama_asli}"
    dest = os.path.join(_folder(), nama_unik)
    file.save(dest)
    ukuran_kb = round(os.path.getsize(dest) / 1024)

    conn.execute(
        "INSERT INTO dokumen(judul, kategori, nomor_dokumen, tgl_dokumen, sumber_instansi, "
        "file_path, nama_file_asli, ukuran_kb, keterangan) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            judul,
            f.get("kategori", "Lainnya"),
            f.get("nomor_dokumen", "").strip(),
            f.get("tgl_dokumen", "").strip(),
            f.get("sumber_instansi", "").strip(),
            dest,
            nama_asli,
            ukuran_kb,
            f.get("keterangan", "").strip(),
        ),
    )
    conn.commit()
    _db.log(conn, "Unggah Dokumen", judul)
    flash(f"Dokumen '{judul}' berhasil diunggah.", "ok")
    return redirect(url_for("dokumen.index"))


@bp.route("/<int:did>/unduh")
def unduh(did):
    conn = current_app.get_db()
    row = conn.execute("SELECT * FROM dokumen WHERE id=?", (did,)).fetchone()
    if not row or not row["file_path"] or not os.path.exists(row["file_path"]):
        abort(404)
    return send_file(
        row["file_path"], as_attachment=True, download_name=row["nama_file_asli"] or "dokumen"
    )


@bp.route("/<int:did>/hapus", methods=["POST"])
def hapus(did):
    conn = current_app.get_db()
    row = conn.execute("SELECT * FROM dokumen WHERE id=?", (did,)).fetchone()
    if row:
        if row["file_path"] and os.path.exists(row["file_path"]):
            try:
                os.remove(row["file_path"])
            except OSError:
                pass
        conn.execute("DELETE FROM dokumen WHERE id=?", (did,))
        conn.commit()
        _db.log(conn, "Hapus Dokumen", row["judul"])
    flash("Dokumen dihapus.", "ok")
    return redirect(url_for("dokumen.index"))
