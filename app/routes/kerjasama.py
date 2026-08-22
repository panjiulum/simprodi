# -*- coding: utf-8 -*-
"""routes/kerjasama.py — Modul 16: Kerja Sama & Mitra.

Struktur tab diadaptasi dari Cooperation.tsx SITIPRO (Executive Dashboard/
Mitra & Dokumen/Program & Implementasi/Evaluasi & Luaran), dibangun ulang
sebagai modul Flask/SQLite sungguhan — tanpa "AI Partnership Analyst"
(teks AI-generated di demo asli, di luar cakupan aplikasi offline, sama
seperti keputusan Chatbot §1) dan tanpa skor "Indeks Kepuasan Mitra 85%"
statis (di demo tidak berasal dari evaluasi sungguhan — di sini dihitung
riil dari `mitra_program.skor_kepuasan` yang benar-benar diisi pengguna,
lihat logic.mitra_rata_kepuasan()).

PENTING soal relevansi (lihat db.py & docs/INTEGRASI_SITIPRO_SIMPRODI.md
§11): program kerja sama (Implementation Arrangement) bisa ditautkan
OPSIONAL ke PIC dosen (Modul 4) dan ke aktivitas Penelitian/PKM
(Modul 4/15) lewat FK sungguhan — bukan sekadar label kategori teks
seperti "Terintegrasi dengan Modul Tri Dharma" di deskripsi demo SITIPRO.
Dokumen MoU/MoA/IA (mitra_dokumen) SENGAJA punya tabel & upload sendiri,
terpisah dari Document Center (Modul 7), karena butuh siklus hidup
(tgl_berakhir + status) untuk reminder kadaluarsa yang tidak dimiliki
skema `dokumen` yang generik.

  - dashboard : stat program studi + sebaran kategori/skala mitra +
                reminder dokumen MoU/MoA/IA yang segera/sudah berakhir.
  - mitra     : direktori mitra (CRUD) + dokumen MoU/MoA/IA per mitra
                terpilih (setara tab "Mitra & Dokumen" SITIPRO).
  - program   : program/Implementation Arrangement per mitra terpilih,
                dengan tautan opsional ke PIC dosen & aktivitas
                Penelitian/PKM.
  - evaluasi  : luaran kerja sama per program terpilih + rata-rata skor
                kepuasan riil (bukan angka statis).
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

bp = Blueprint("kerjasama", __name__, url_prefix="/kerjasama")

_TABS = ("dashboard", "mitra", "program", "evaluasi")


def _folder():
    folder = os.path.join(_db.home_dir(), "SistemSkripsi", "mitra_dokumen")
    os.makedirs(folder, exist_ok=True)
    return folder


def _daftar_mitra(conn, kategori=None, skala=None, cari=None):
    q = "SELECT * FROM mitra WHERE 1=1"
    params = []
    if kategori:
        q += " AND kategori=?"
        params.append(kategori)
    if skala:
        q += " AND skala=?"
        params.append(skala)
    if cari:
        q += " AND (nama LIKE ? OR alamat LIKE ?)"
        like = f"%{cari}%"
        params += [like, like]
    q += " ORDER BY nama"
    return conn.execute(q, params).fetchall()


@bp.route("/")
def index():
    conn = current_app.get_db()
    tab = request.args.get("tab", "dashboard")
    if tab not in _TABS:
        tab = "dashboard"

    ctx = {"tab": tab}

    if tab == "dashboard":
        ctx["ringkasan"] = L.mitra_ringkasan(conn)
        ctx["sebaran"] = L.mitra_sebaran_kategori(conn)
        ctx["reminder"] = L.mitra_reminder_dokumen(conn)
        ctx["rata_kepuasan"] = L.mitra_rata_kepuasan(conn)

    elif tab == "mitra":
        kategori = request.args.get("kategori", "")
        skala = request.args.get("skala", "")
        cari = request.args.get("cari", "").strip()
        rows = _daftar_mitra(conn, kategori, skala, cari)
        ctx["rows"] = [
            dict(
                r,
                status_terkini=L.mitra_status_terkini(conn, r["id"]),
                n_dokumen_aktif=L.mitra_jumlah_dokumen_aktif(conn, r["id"]),
                n_program=L.mitra_jumlah_program(conn, r["id"]),
            )
            for r in rows
        ]
        ctx["kategori"] = kategori
        ctx["skala"] = skala
        ctx["cari"] = cari
        ctx["kategori_mitra_list"] = C.KATEGORI_MITRA_LIST
        ctx["skala_mitra_list"] = C.SKALA_MITRA_LIST
        edit_id = request.args.get("edit", type=int)
        ctx["edit_row"] = (
            conn.execute("SELECT * FROM mitra WHERE id=?", (edit_id,)).fetchone()
            if edit_id
            else None
        )

        mid = request.args.get("mitra", type=int)
        mitra_terpilih = (
            conn.execute("SELECT * FROM mitra WHERE id=?", (mid,)).fetchone() if mid else None
        )
        ctx["mitra_terpilih"] = mitra_terpilih
        if mitra_terpilih:
            ctx["dokumen_rows"] = conn.execute(
                "SELECT * FROM mitra_dokumen WHERE mitra_id=? ORDER BY tgl_berakhir IS NULL, tgl_berakhir",
                (mid,),
            ).fetchall()
        else:
            ctx["dokumen_rows"] = []
        ctx["jenis_dokumen_mitra_list"] = C.JENIS_DOKUMEN_MITRA_LIST
        ctx["status_dokumen_mitra_list"] = C.STATUS_DOKUMEN_MITRA_LIST

    elif tab == "program":
        ctx["mitra_list"] = conn.execute("SELECT id, nama FROM mitra ORDER BY nama").fetchall()
        mid = request.args.get("mitra", type=int)
        if not mid and ctx["mitra_list"]:
            mid = ctx["mitra_list"][0]["id"]
        mitra_terpilih = (
            conn.execute("SELECT * FROM mitra WHERE id=?", (mid,)).fetchone() if mid else None
        )
        ctx["mitra_terpilih"] = mitra_terpilih
        if mitra_terpilih:
            ctx["program_rows"] = conn.execute(
                "SELECT p.*, d.nama AS pic_nama, "
                "COALESCE(ap.judul, apk.judul) AS terkait_judul "
                "FROM mitra_program p LEFT JOIN dosen d ON d.id = p.pic_dosen_id "
                "LEFT JOIN aktivitas_penelitian ap ON ap.id = p.penelitian_id "
                "LEFT JOIN aktivitas_pkm apk ON apk.id = p.pkm_id "
                "WHERE p.mitra_id=? ORDER BY p.id DESC",
                (mid,),
            ).fetchall()
        else:
            ctx["program_rows"] = []
        ctx["dosen_list"] = conn.execute(
            "SELECT id, nama FROM dosen WHERE aktif=1 ORDER BY nama"
        ).fetchall()
        ctx["penelitian_list"] = conn.execute(
            "SELECT ap.id, ap.judul, d.nama AS dosen_nama FROM aktivitas_penelitian ap "
            "JOIN dosen d ON d.id = ap.dosen_id ORDER BY ap.id DESC LIMIT 100"
        ).fetchall()
        ctx["pkm_list"] = conn.execute(
            "SELECT apk.id, apk.judul, d.nama AS dosen_nama FROM aktivitas_pkm apk "
            "JOIN dosen d ON d.id = apk.dosen_id ORDER BY apk.id DESC LIMIT 100"
        ).fetchall()
        ctx["jenis_program_mitra_list"] = C.JENIS_PROGRAM_MITRA_LIST
        ctx["status_program_mitra_list"] = C.STATUS_PROGRAM_MITRA_LIST
        edit_id = request.args.get("edit", type=int)
        ctx["edit_row"] = (
            conn.execute(
                "SELECT * FROM mitra_program WHERE id=? AND mitra_id=?", (edit_id, mid)
            ).fetchone()
            if edit_id and mid
            else None
        )

    elif tab == "evaluasi":
        ctx["mitra_list"] = conn.execute("SELECT id, nama FROM mitra ORDER BY nama").fetchall()
        mid = request.args.get("mitra", type=int)
        if not mid and ctx["mitra_list"]:
            mid = ctx["mitra_list"][0]["id"]
        mitra_terpilih = (
            conn.execute("SELECT * FROM mitra WHERE id=?", (mid,)).fetchone() if mid else None
        )
        ctx["mitra_terpilih"] = mitra_terpilih
        program_list = (
            conn.execute(
                "SELECT * FROM mitra_program WHERE mitra_id=? ORDER BY nama_program", (mid,)
            ).fetchall()
            if mitra_terpilih
            else []
        )
        ctx["program_list"] = program_list
        pid = request.args.get("program", type=int)
        if not pid and program_list:
            pid = program_list[0]["id"]
        program_terpilih = (
            conn.execute("SELECT * FROM mitra_program WHERE id=?", (pid,)).fetchone()
            if pid
            else None
        )
        ctx["program_terpilih"] = program_terpilih
        ctx["luaran_rows"] = (
            conn.execute(
                "SELECT * FROM mitra_luaran WHERE mitra_program_id=? ORDER BY id DESC", (pid,)
            ).fetchall()
            if program_terpilih
            else []
        )
        ctx["jenis_luaran_kerjasama_list"] = C.JENIS_LUARAN_KERJASAMA_LIST
        ctx["rata_kepuasan_mitra"] = L.mitra_rata_kepuasan(conn, mid) if mitra_terpilih else None

    return render_template("kerjasama.html", **ctx)


@bp.route("/mitra/simpan", methods=["POST"])
def simpan_mitra():
    conn = current_app.get_db()
    f = request.form
    mid = f.get("id", type=int)
    nama = f.get("nama", "").strip()
    if not nama:
        flash("Nama mitra wajib diisi.", "error")
        return redirect(url_for("kerjasama.index", tab="mitra"))

    kategori = f.get("kategori", "Instansi Pemerintah")
    if kategori not in C.KATEGORI_MITRA_LIST:
        kategori = "Instansi Pemerintah"
    skala = f.get("skala", "Nasional")
    if skala not in C.SKALA_MITRA_LIST:
        skala = "Nasional"

    vals = (
        nama,
        kategori,
        skala,
        f.get("negara", "Indonesia").strip() or "Indonesia",
        f.get("alamat", "").strip(),
        f.get("kontak_person", "").strip(),
        f.get("no_hp", "").strip(),
        f.get("email", "").strip(),
        f.get("deskripsi", "").strip(),
        f.get("catatan", "").strip(),
    )
    try:
        if mid:
            conn.execute(
                "UPDATE mitra SET nama=?, kategori=?, skala=?, negara=?, alamat=?, "
                "kontak_person=?, no_hp=?, email=?, deskripsi=?, catatan=? WHERE id=?",
                vals + (mid,),
            )
            flash("Data mitra diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO mitra(nama, kategori, skala, negara, alamat, kontak_person, "
                "no_hp, email, deskripsi, catatan) VALUES(?,?,?,?,?,?,?,?,?,?)",
                vals,
            )
            flash("Mitra baru ditambahkan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Mitra", nama)
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan data mitra")
    return redirect(url_for("kerjasama.index", tab="mitra"))


@bp.route("/mitra/<int:mid>/hapus", methods=["POST"])
def hapus_mitra(mid):
    conn = current_app.get_db()
    rows = conn.execute("SELECT file_path FROM mitra_dokumen WHERE mitra_id=?", (mid,)).fetchall()
    for r in rows:
        if r["file_path"] and os.path.exists(r["file_path"]):
            try:
                os.remove(r["file_path"])
            except OSError:
                pass
    conn.execute("DELETE FROM mitra WHERE id=?", (mid,))
    conn.commit()
    _db.log(conn, "Hapus Mitra", str(mid))
    flash("Mitra dihapus (dokumen, program & luaran terkait ikut terhapus).", "ok")
    return redirect(url_for("kerjasama.index", tab="mitra"))


@bp.route("/dokumen/unggah", methods=["POST"])
def unggah_dokumen():
    conn = current_app.get_db()
    f = request.form
    mitra_id = f.get("mitra_id", type=int)
    if not mitra_id:
        flash("Pilih mitra terlebih dahulu.", "error")
        return redirect(url_for("kerjasama.index", tab="mitra"))

    jenis_dokumen = f.get("jenis_dokumen", "MoU (Nota Kesepahaman)")
    if jenis_dokumen not in C.JENIS_DOKUMEN_MITRA_LIST:
        jenis_dokumen = "MoU (Nota Kesepahaman)"
    status = f.get("status", "Aktif")
    if status not in C.STATUS_DOKUMEN_MITRA_LIST:
        status = "Aktif"

    file = request.files.get("file_dokumen")
    file_path = nama_asli = None
    ukuran_kb = None
    if file and file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in C.EKSTENSI_DOKUMEN_DIIZINKAN:
            flash(
                f"Format .{ext} tidak diizinkan. Format yang didukung: "
                f"{', '.join(sorted(C.EKSTENSI_DOKUMEN_DIIZINKAN))}.",
                "error",
            )
            return redirect(url_for("kerjasama.index", tab="mitra", mitra=mitra_id))
        nama_asli = secure_filename(file.filename)
        nama_unik = f"{uuid.uuid4().hex[:12]}_{nama_asli}"
        file_path = os.path.join(_folder(), nama_unik)
        file.save(file_path)
        ukuran_kb = round(os.path.getsize(file_path) / 1024)

    conn.execute(
        "INSERT INTO mitra_dokumen(mitra_id, jenis_dokumen, nomor_dokumen, judul, tgl_mulai, "
        "tgl_berakhir, status, file_path, nama_file_asli, ukuran_kb, catatan) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            mitra_id,
            jenis_dokumen,
            f.get("nomor_dokumen", "").strip(),
            f.get("judul", "").strip() or jenis_dokumen,
            f.get("tgl_mulai", "").strip(),
            f.get("tgl_berakhir", "").strip(),
            status,
            file_path,
            nama_asli,
            ukuran_kb,
            f.get("catatan", "").strip(),
        ),
    )
    conn.commit()
    _db.log(conn, "Unggah Dokumen Mitra", f"{jenis_dokumen} — mitra #{mitra_id}")
    flash("Dokumen kerja sama tersimpan.", "ok")
    return redirect(url_for("kerjasama.index", tab="mitra", mitra=mitra_id))


@bp.route("/dokumen/<int:did>/unduh")
def unduh_dokumen(did):
    conn = current_app.get_db()
    row = conn.execute("SELECT * FROM mitra_dokumen WHERE id=?", (did,)).fetchone()
    if not row or not row["file_path"] or not os.path.exists(row["file_path"]):
        abort(404)
    return send_file(
        row["file_path"], as_attachment=True, download_name=row["nama_file_asli"] or "dokumen"
    )


@bp.route("/dokumen/<int:did>/hapus", methods=["POST"])
def hapus_dokumen(did):
    conn = current_app.get_db()
    row = conn.execute("SELECT * FROM mitra_dokumen WHERE id=?", (did,)).fetchone()
    mitra_id = row["mitra_id"] if row else None
    if row:
        if row["file_path"] and os.path.exists(row["file_path"]):
            try:
                os.remove(row["file_path"])
            except OSError:
                pass
        conn.execute("DELETE FROM mitra_dokumen WHERE id=?", (did,))
        conn.commit()
        _db.log(conn, "Hapus Dokumen Mitra", row["judul"] or str(did))
    flash("Dokumen dihapus.", "ok")
    return redirect(url_for("kerjasama.index", tab="mitra", mitra=mitra_id))


@bp.route("/program/simpan", methods=["POST"])
def simpan_program():
    conn = current_app.get_db()
    f = request.form
    pid = f.get("id", type=int)
    mitra_id = f.get("mitra_id", type=int)
    nama_program = f.get("nama_program", "").strip()
    if not mitra_id or not nama_program:
        flash("Mitra dan nama program wajib diisi.", "error")
        return redirect(url_for("kerjasama.index", tab="program", mitra=mitra_id))

    jenis_program = f.get("jenis_program", "Pendidikan/MBKM")
    if jenis_program not in C.JENIS_PROGRAM_MITRA_LIST:
        jenis_program = "Pendidikan/MBKM"
    status = f.get("status", "Perencanaan")
    if status not in C.STATUS_PROGRAM_MITRA_LIST:
        status = "Perencanaan"
    skor = f.get("skor_kepuasan", type=int)
    if skor is not None:
        skor = max(0, min(100, skor))

    vals = (
        mitra_id,
        nama_program,
        jenis_program,
        f.get("pic_dosen_id", type=int),
        f.get("penelitian_id", type=int),
        f.get("pkm_id", type=int),
        f.get("tgl_mulai", "").strip(),
        f.get("tgl_selesai", "").strip(),
        status,
        skor,
        f.get("deskripsi", "").strip(),
        f.get("catatan", "").strip(),
    )
    try:
        if pid:
            conn.execute(
                "UPDATE mitra_program SET mitra_id=?, nama_program=?, jenis_program=?, "
                "pic_dosen_id=?, penelitian_id=?, pkm_id=?, tgl_mulai=?, tgl_selesai=?, "
                "status=?, skor_kepuasan=?, deskripsi=?, catatan=? WHERE id=?",
                vals + (pid,),
            )
            flash("Program kerja sama diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO mitra_program(mitra_id, nama_program, jenis_program, pic_dosen_id, "
                "penelitian_id, pkm_id, tgl_mulai, tgl_selesai, status, skor_kepuasan, "
                "deskripsi, catatan) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                vals,
            )
            flash("Program kerja sama ditambahkan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Program Mitra", nama_program)
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan program kerja sama")
    return redirect(url_for("kerjasama.index", tab="program", mitra=mitra_id))


@bp.route("/program/<int:pid>/hapus", methods=["POST"])
def hapus_program(pid):
    conn = current_app.get_db()
    row = conn.execute("SELECT mitra_id FROM mitra_program WHERE id=?", (pid,)).fetchone()
    conn.execute("DELETE FROM mitra_program WHERE id=?", (pid,))
    conn.commit()
    _db.log(conn, "Hapus Program Mitra", str(pid))
    flash("Program kerja sama dihapus (luaran terkait ikut terhapus).", "ok")
    return redirect(
        url_for("kerjasama.index", tab="program", mitra=row["mitra_id"] if row else None)
    )


@bp.route("/luaran/simpan", methods=["POST"])
def simpan_luaran():
    conn = current_app.get_db()
    f = request.form
    mitra_program_id = f.get("mitra_program_id", type=int)
    judul = f.get("judul", "").strip()
    if not mitra_program_id or not judul:
        flash("Program dan judul luaran wajib diisi.", "error")
        return redirect(url_for("kerjasama.index", tab="evaluasi"))

    jenis_luaran = f.get("jenis_luaran", "Lainnya")
    if jenis_luaran not in C.JENIS_LUARAN_KERJASAMA_LIST:
        jenis_luaran = "Lainnya"

    row = conn.execute(
        "SELECT mitra_id FROM mitra_program WHERE id=?", (mitra_program_id,)
    ).fetchone()
    try:
        conn.execute(
            "INSERT INTO mitra_luaran(mitra_program_id, jenis_luaran, judul, jumlah, tanggal, "
            "luaran_dosen_id, catatan) VALUES(?,?,?,?,?,?,?)",
            (
                mitra_program_id,
                jenis_luaran,
                judul,
                f.get("jumlah", type=int),
                f.get("tanggal", "").strip(),
                f.get("luaran_dosen_id", type=int),
                f.get("catatan", "").strip(),
            ),
        )
        conn.commit()
        _db.log(conn, "Simpan Luaran Kerja Sama", judul)
        flash("Luaran kerja sama tersimpan.", "ok")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan luaran kerja sama")
    return redirect(
        url_for(
            "kerjasama.index",
            tab="evaluasi",
            mitra=row["mitra_id"] if row else None,
            program=mitra_program_id,
        )
    )


@bp.route("/luaran/<int:lid>/hapus", methods=["POST"])
def hapus_luaran(lid):
    conn = current_app.get_db()
    row = conn.execute(
        "SELECT l.mitra_program_id, p.mitra_id FROM mitra_luaran l "
        "JOIN mitra_program p ON p.id = l.mitra_program_id WHERE l.id=?",
        (lid,),
    ).fetchone()
    conn.execute("DELETE FROM mitra_luaran WHERE id=?", (lid,))
    conn.commit()
    _db.log(conn, "Hapus Luaran Kerja Sama", str(lid))
    flash("Luaran kerja sama dihapus.", "ok")
    return redirect(
        url_for(
            "kerjasama.index",
            tab="evaluasi",
            mitra=row["mitra_id"] if row else None,
            program=row["mitra_program_id"] if row else None,
        )
    )
