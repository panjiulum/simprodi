# -*- coding: utf-8 -*-
"""routes/rpl.py — Modul 14: RPL (Rekognisi Pembelajaran Lampau).

Struktur tab diadaptasi dari RPL.tsx SITIPRO (Dashboard/Data Asesmen/DMS &
AI Scanner), dibangun ulang sebagai modul Flask/SQLite sungguhan — tanpa
"AI OCR Extractor" (di luar cakupan aplikasi offline, lihat README asli
& docs/INTEGRASI_SITIPRO_SIMPRODI.md §1 soal Chatbot/fitur cloud lain yang
sengaja tidak diporting):

  - pendaftar : dashboard ringkas (stat-row) + CRUD data pendaftar RPL dan
                status asesmen (Verifikasi Berkas -> Asesmen Portofolio ->
                Disetujui/Ditolak).
  - asesmen   : konversi SKS per mata kuliah untuk 1 pendaftar terpilih —
                total SKS diakui dihitung on-the-fly
                (logic.rpl_total_sks_diakui()), bukan angka statis.
  - dokumen   : DMS sederhana (upload/unduh/hapus) untuk 1 pendaftar
                terpilih, pola sama dengan Document Center Modul 7
                (folder terpisah, nama file unik dengan prefix UUID).

Catatan penting (lihat db.py): modul ini TIDAK otomatis membuat baris
`mahasiswa` saat status RPL "Disetujui" — pendaftaran mahasiswa resmi
(NIM dsb) tetap lewat modul Data Mahasiswa seperti biasa, cukup dengan
skema='RPL'. Field rpl_pendaftar.mahasiswa_id tersedia untuk ditautkan
manual setelah itu, supaya riwayat asesmen RPL tetap terhubung ke data
mahasiswa resminya.
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
from app import error_utils as EH
from app import logic as L

bp = Blueprint("rpl", __name__, url_prefix="/rpl")

_TABS = ("pendaftar", "asesmen", "dokumen")


def _folder():
    folder = os.path.join(_db.home_dir(), "SistemSkripsi", "rpl_dokumen")
    os.makedirs(folder, exist_ok=True)
    return folder


def _mk_kurikulum_aktif(conn):
    from app.routes.kurikulum import _kurikulum_aktif

    kur = _kurikulum_aktif(conn)
    if not kur:
        return []
    return conn.execute(
        "SELECT * FROM mata_kuliah WHERE kurikulum_id=? ORDER BY semester, kode",
        (kur["id"],),
    ).fetchall()


def _daftar_pendaftar(conn, status_filter=None, cari=None):
    q = "SELECT * FROM rpl_pendaftar WHERE 1=1"
    params = []
    if status_filter:
        q += " AND status=?"
        params.append(status_filter)
    if cari:
        q += " AND (nama LIKE ? OR asal_instansi_pendidikan LIKE ?)"
        like = f"%{cari}%"
        params += [like, like]
    q += " ORDER BY tgl_daftar DESC"
    return conn.execute(q, params).fetchall()


@bp.route("/")
def index():
    conn = current_app.get_db()
    tab = request.args.get("tab", "pendaftar")
    if tab not in _TABS:
        tab = "pendaftar"

    ctx = {"tab": tab, "status_rpl_list": C.STATUS_RPL_LIST}

    if tab == "pendaftar":
        status_filter = request.args.get("status", "")
        cari = request.args.get("cari", "").strip()
        rows = _daftar_pendaftar(conn, status_filter, cari)
        ctx["rows"] = rows
        ctx["status_filter"] = status_filter
        ctx["cari"] = cari
        ctx["jumlah_per_status"] = {
            r["status"]: r["c"]
            for r in conn.execute(
                "SELECT status, COUNT(*) c FROM rpl_pendaftar GROUP BY status"
            ).fetchall()
        }
        ctx["total"] = conn.execute("SELECT COUNT(*) c FROM rpl_pendaftar").fetchone()["c"]
        ctx["jenis_pengakuan_list"] = C.JENIS_PENGAKUAN_RPL_LIST
        edit_id = request.args.get("edit", type=int)
        ctx["edit_row"] = (
            conn.execute("SELECT * FROM rpl_pendaftar WHERE id=?", (edit_id,)).fetchone()
            if edit_id
            else None
        )

    elif tab in ("asesmen", "dokumen"):
        ctx["pendaftar_list"] = conn.execute(
            "SELECT id, nama, status FROM rpl_pendaftar ORDER BY nama"
        ).fetchall()
        pid = request.args.get("pendaftar", type=int)
        if not pid and ctx["pendaftar_list"]:
            pid = ctx["pendaftar_list"][0]["id"]
        pendaftar_terpilih = (
            conn.execute("SELECT * FROM rpl_pendaftar WHERE id=?", (pid,)).fetchone()
            if pid
            else None
        )
        ctx["pendaftar_terpilih"] = pendaftar_terpilih

        if tab == "asesmen":
            ctx["mk_list"] = _mk_kurikulum_aktif(conn)
            if pendaftar_terpilih:
                ctx["konversi_rows"] = conn.execute(
                    "SELECT rk.*, mk.kode AS mk_kode, mk.nama AS mk_nama, mk.sks AS mk_sks "
                    "FROM rpl_konversi rk JOIN mata_kuliah mk ON mk.id = rk.mata_kuliah_id "
                    "WHERE rk.rpl_pendaftar_id=? ORDER BY mk.semester, mk.kode",
                    (pid,),
                ).fetchall()
                ctx["total_sks_diakui"] = L.rpl_total_sks_diakui(conn, pid)
            else:
                ctx["konversi_rows"] = []
                ctx["total_sks_diakui"] = 0

        elif tab == "dokumen":
            ctx["jenis_dokumen_rpl_list"] = C.JENIS_DOKUMEN_RPL_LIST
            ctx["dokumen_rows"] = (
                conn.execute(
                    "SELECT * FROM rpl_dokumen WHERE rpl_pendaftar_id=? ORDER BY diunggah_pada DESC",
                    (pid,),
                ).fetchall()
                if pendaftar_terpilih
                else []
            )

    return render_template("rpl.html", **ctx)


@bp.route("/pendaftar/simpan", methods=["POST"])
def simpan_pendaftar():
    conn = current_app.get_db()
    f = request.form
    pid = f.get("id", type=int)
    nama = f.get("nama", "").strip()
    if not nama:
        flash("Nama pendaftar wajib diisi.", "error")
        return redirect(url_for("rpl.index", tab="pendaftar"))

    jenis = f.get("jenis_pengakuan", "Pengalaman Kerja")
    if jenis not in C.JENIS_PENGAKUAN_RPL_LIST:
        jenis = "Pengalaman Kerja"
    status = f.get("status", "Verifikasi Berkas")
    if status not in C.STATUS_RPL_LIST:
        status = "Verifikasi Berkas"

    vals = (
        nama,
        f.get("no_identitas", "").strip(),
        f.get("no_hp", "").strip(),
        f.get("email", "").strip(),
        jenis,
        f.get("asal_instansi_pendidikan", "").strip(),
        f.get("lama_pengalaman", "").strip(),
        status,
        f.get("catatan_asesor", "").strip(),
        f.get("mahasiswa_id", type=int),
    )
    try:
        if pid:
            conn.execute(
                "UPDATE rpl_pendaftar SET nama=?, no_identitas=?, no_hp=?, email=?, "
                "jenis_pengakuan=?, asal_instansi_pendidikan=?, lama_pengalaman=?, status=?, "
                "catatan_asesor=?, mahasiswa_id=? WHERE id=?",
                vals + (pid,),
            )
            flash("Data pendaftar RPL diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO rpl_pendaftar(nama, no_identitas, no_hp, email, jenis_pengakuan, "
                "asal_instansi_pendidikan, lama_pengalaman, status, catatan_asesor, mahasiswa_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                vals,
            )
            flash("Pendaftar RPL ditambahkan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Pendaftar RPL", nama)
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan data pendaftar RPL")
    return redirect(url_for("rpl.index", tab="pendaftar"))


@bp.route("/pendaftar/<int:pid>/hapus", methods=["POST"])
def hapus_pendaftar(pid):
    conn = current_app.get_db()
    rows = conn.execute(
        "SELECT file_path FROM rpl_dokumen WHERE rpl_pendaftar_id=?", (pid,)
    ).fetchall()
    for r in rows:
        if r["file_path"] and os.path.exists(r["file_path"]):
            try:
                os.remove(r["file_path"])
            except OSError:
                pass
    conn.execute("DELETE FROM rpl_pendaftar WHERE id=?", (pid,))
    conn.commit()
    _db.log(conn, "Hapus Pendaftar RPL", str(pid))
    flash("Pendaftar RPL dihapus (dokumen & data konversi terkait ikut terhapus).", "ok")
    return redirect(url_for("rpl.index", tab="pendaftar"))


@bp.route("/konversi/simpan", methods=["POST"])
def simpan_konversi():
    conn = current_app.get_db()
    f = request.form
    rpl_pendaftar_id = f.get("rpl_pendaftar_id", type=int)
    mata_kuliah_id = f.get("mata_kuliah_id", type=int)
    if not rpl_pendaftar_id or not mata_kuliah_id:
        flash("Pendaftar dan mata kuliah wajib dipilih.", "error")
        return redirect(url_for("rpl.index", tab="asesmen", pendaftar=rpl_pendaftar_id))
    try:
        conn.execute(
            "INSERT INTO rpl_konversi(rpl_pendaftar_id, mata_kuliah_id, sks_diakui, "
            "nilai_konversi, dasar_pengakuan, catatan) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(rpl_pendaftar_id, mata_kuliah_id) DO UPDATE SET "
            "sks_diakui=excluded.sks_diakui, nilai_konversi=excluded.nilai_konversi, "
            "dasar_pengakuan=excluded.dasar_pengakuan, catatan=excluded.catatan",
            (
                rpl_pendaftar_id,
                mata_kuliah_id,
                f.get("sks_diakui", type=int) or 0,
                f.get("nilai_konversi", "").strip(),
                f.get("dasar_pengakuan", "").strip(),
                f.get("catatan", "").strip(),
            ),
        )
        conn.commit()
        _db.log(
            conn, "Simpan Konversi SKS RPL", f"pendaftar #{rpl_pendaftar_id} mk #{mata_kuliah_id}"
        )
        flash("Konversi SKS disimpan.", "ok")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan konversi SKS")
    return redirect(url_for("rpl.index", tab="asesmen", pendaftar=rpl_pendaftar_id))


@bp.route("/konversi/<int:kid>/hapus", methods=["POST"])
def hapus_konversi(kid):
    conn = current_app.get_db()
    row = conn.execute("SELECT rpl_pendaftar_id FROM rpl_konversi WHERE id=?", (kid,)).fetchone()
    conn.execute("DELETE FROM rpl_konversi WHERE id=?", (kid,))
    conn.commit()
    _db.log(conn, "Hapus Konversi SKS RPL", str(kid))
    flash("Baris konversi SKS dihapus.", "ok")
    return redirect(
        url_for("rpl.index", tab="asesmen", pendaftar=row["rpl_pendaftar_id"] if row else None)
    )


@bp.route("/dokumen/unggah", methods=["POST"])
def unggah_dokumen():
    conn = current_app.get_db()
    f = request.form
    rpl_pendaftar_id = f.get("rpl_pendaftar_id", type=int)
    file = request.files.get("file_dokumen")

    if not rpl_pendaftar_id:
        flash("Pilih pendaftar terlebih dahulu.", "error")
        return redirect(url_for("rpl.index", tab="dokumen"))
    if not file or not file.filename:
        flash("Pilih file dokumen terlebih dahulu.", "error")
        return redirect(url_for("rpl.index", tab="dokumen", pendaftar=rpl_pendaftar_id))

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in C.EKSTENSI_DOKUMEN_DIIZINKAN:
        flash(
            f"Format .{ext} tidak diizinkan. Format yang didukung: "
            f"{', '.join(sorted(C.EKSTENSI_DOKUMEN_DIIZINKAN))}.",
            "error",
        )
        return redirect(url_for("rpl.index", tab="dokumen", pendaftar=rpl_pendaftar_id))

    nama_asli = secure_filename(file.filename)
    nama_unik = f"{uuid.uuid4().hex[:12]}_{nama_asli}"
    dest = os.path.join(_folder(), nama_unik)
    file.save(dest)
    ukuran_kb = round(os.path.getsize(dest) / 1024)

    conn.execute(
        "INSERT INTO rpl_dokumen(rpl_pendaftar_id, jenis_dokumen, judul, file_path, "
        "nama_file_asli, ukuran_kb) VALUES(?,?,?,?,?,?)",
        (
            rpl_pendaftar_id,
            f.get("jenis_dokumen", "Lainnya"),
            f.get("judul", "").strip() or nama_asli,
            dest,
            nama_asli,
            ukuran_kb,
        ),
    )
    conn.commit()
    _db.log(conn, "Unggah Dokumen RPL", nama_asli)
    flash(f"Dokumen '{nama_asli}' berhasil diunggah.", "ok")
    return redirect(url_for("rpl.index", tab="dokumen", pendaftar=rpl_pendaftar_id))


@bp.route("/dokumen/<int:did>/unduh")
def unduh_dokumen(did):
    conn = current_app.get_db()
    row = conn.execute("SELECT * FROM rpl_dokumen WHERE id=?", (did,)).fetchone()
    if not row or not row["file_path"] or not os.path.exists(row["file_path"]):
        abort(404)
    return send_file(
        row["file_path"], as_attachment=True, download_name=row["nama_file_asli"] or "dokumen"
    )


@bp.route("/dokumen/<int:did>/hapus", methods=["POST"])
def hapus_dokumen(did):
    conn = current_app.get_db()
    row = conn.execute("SELECT * FROM rpl_dokumen WHERE id=?", (did,)).fetchone()
    pendaftar_id = row["rpl_pendaftar_id"] if row else None
    if row:
        if row["file_path"] and os.path.exists(row["file_path"]):
            try:
                os.remove(row["file_path"])
            except OSError:
                pass
        conn.execute("DELETE FROM rpl_dokumen WHERE id=?", (did,))
        conn.commit()
        _db.log(conn, "Hapus Dokumen RPL", row["nama_file_asli"] or str(did))
    flash("Dokumen dihapus.", "ok")
    return redirect(url_for("rpl.index", tab="dokumen", pendaftar=pendaftar_id))
