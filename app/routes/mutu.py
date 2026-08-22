# -*- coding: utf-8 -*-
"""routes/mutu.py — Modul 17: Mutu (IKU, Akreditasi & Audit Mutu Internal/SPMI).

PENTING soal sumber adaptasi (lihat db.py & docs/INTEGRASI_SITIPRO_SIMPRODI.md
§13): dari 3 menu roadmap lama (IKU, Akreditasi, Audit & QA), SITIPRO cuma
benar-benar merutekan /audit-qa (AuditQA.tsx) — /iku dan /akreditasi TIDAK
PERNAH punya komponen di demo aslinya. Jadi:
  - IKU & Akreditasi dirancang dari kerangka resmi (8 IKU Kemendikbudristek,
    9 Kriteria LAMEMBA — relevan utk profil program studi S1 Administrasi
    Bisnis/Niaga), bukan "diadaptasi" dari kode yang memang tidak ada.
  - AuditQA.tsx (Data Integrity/Workflow/System Health/Security) diterjemahkan
    ulang total ke konsep yang sungguhan berlaku & bisa dibangun jujur di
    SIMPRODI (aplikasi Flask+SQLite offline single-tenant, bukan sistem
    terdistribusi yang punya "System Health 99.9%"/"Security Alerts"):
    diganti Audit Mutu Internal (AMI/SPMI, siklus PDCA standar mutu — bukan
    hanya OBE/CPL seperti Modul 12 CQI), pemindai Kelengkapan Data (baca
    langsung tabel lintas modul), dan penampil log_aktivitas (tabel yang
    SUDAH ditulis oleh db.log() di hampir setiap route sejak Fase Fondasi,
    baru sekarang punya UI).

Relevansi ke modul lain — 6 dari 8 IKU dihitung on-the-fly dari data yang
SUDAH ada, bukan angka contoh:
  IKU1 <- tracer_study (Modul Kelulusan), IKU2/IKU4/IKU6 <- mitra_luaran/
  mitra_program/mitra (Modul 16), IKU3 <- aktivitas_penunjang (Modul 4),
  IKU5 <- luaran_dosen (Modul 4/15).

  - iku          : 8 IKU Kemendikbudristek, realisasi vs target per tahun.
  - akreditasi   : 9 Kriteria LAMEMBA, status penyusunan + bukti dukung.
  - audit        : Audit Mutu Internal (siklus + temuan + tindak lanjut).
  - kelengkapan  : pemindai kelengkapan data lintas modul (baca-saja).
  - log          : penampil & pencarian log_aktivitas (baca-saja).
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

bp = Blueprint("mutu", __name__, url_prefix="/mutu")

_TABS = ("iku", "akreditasi", "audit", "kelengkapan", "log")


def _folder():
    folder = os.path.join(_db.home_dir(), "SistemSkripsi", "akreditasi_bukti")
    os.makedirs(folder, exist_ok=True)
    return folder


@bp.route("/")
def index():
    conn = current_app.get_db()
    tab = request.args.get("tab", "iku")
    if tab not in _TABS:
        tab = "iku"

    ctx = {"tab": tab}

    if tab == "iku":
        tahun_aktif = _db.get_setting(conn, "tahun_akademik_aktif", "")
        tahun = request.args.get("tahun", "").strip() or L.tahun_dari_tahun_akademik(tahun_aktif)
        ctx["tahun"] = tahun
        ctx["ringkasan"] = L.iku_ringkasan(conn, tahun) if tahun else []

    elif tab == "akreditasi":
        progres = L.akreditasi_progres(conn)
        progres["rows"] = [
            dict(r, n_bukti=L.akreditasi_jumlah_bukti(conn, r["id"])) for r in progres["rows"]
        ]
        ctx["progres"] = progres
        ctx["dosen_list"] = conn.execute(
            "SELECT id, nama FROM dosen WHERE aktif=1 ORDER BY nama"
        ).fetchall()
        ctx["status_kriteria_list"] = C.STATUS_KRITERIA_AKREDITASI_LIST
        kid = request.args.get("kriteria", type=int)
        if not kid and ctx["progres"]["rows"]:
            kid = ctx["progres"]["rows"][0]["id"]
        kriteria_terpilih = (
            conn.execute(
                "SELECT ak.*, d.nama AS pic_nama FROM akreditasi_kriteria ak "
                "LEFT JOIN dosen d ON d.id = ak.pic_dosen_id WHERE ak.id=?",
                (kid,),
            ).fetchone()
            if kid
            else None
        )
        ctx["kriteria_terpilih"] = kriteria_terpilih
        ctx["bukti_rows"] = (
            conn.execute(
                "SELECT * FROM akreditasi_bukti WHERE kriteria_id=? ORDER BY diunggah_pada DESC",
                (kid,),
            ).fetchall()
            if kriteria_terpilih
            else []
        )

    elif tab == "audit":
        ctx["ringkasan"] = L.ami_ringkasan(conn)
        ctx["reminder"] = L.ami_reminder_tenggat(conn)
        ctx["siklus_rows"] = conn.execute("SELECT * FROM ami_siklus ORDER BY id DESC").fetchall()
        ctx["status_ami_siklus_list"] = C.STATUS_AMI_SIKLUS_LIST
        # Audit poin 1 (tindak lanjut) — dropdown Periode Akademik terkunci
        # utk Siklus AMI, menggantikan input teks tahun_akademik bebas.
        ctx["daftar_periode"] = _db.get_periode_list(conn)
        ctx["kategori_temuan_list"] = C.KATEGORI_TEMUAN_AMI_LIST
        ctx["status_temuan_list"] = C.STATUS_TEMUAN_AMI_LIST
        ctx["dosen_list"] = conn.execute(
            "SELECT id, nama FROM dosen WHERE aktif=1 ORDER BY nama"
        ).fetchall()
        edit_id = request.args.get("edit", type=int)
        ctx["edit_siklus"] = (
            conn.execute("SELECT * FROM ami_siklus WHERE id=?", (edit_id,)).fetchone()
            if edit_id
            else None
        )

        sid = request.args.get("siklus", type=int)
        if not sid and ctx["siklus_rows"]:
            sid = ctx["siklus_rows"][0]["id"]
        siklus_terpilih = (
            conn.execute("SELECT * FROM ami_siklus WHERE id=?", (sid,)).fetchone() if sid else None
        )
        ctx["siklus_terpilih"] = siklus_terpilih
        ctx["temuan_rows"] = (
            conn.execute(
                "SELECT t.*, d.nama AS pic_nama FROM ami_temuan t LEFT JOIN dosen d ON d.id = t.pic_dosen_id "
                "WHERE t.siklus_id=? ORDER BY t.id DESC",
                (sid,),
            ).fetchall()
            if siklus_terpilih
            else []
        )

    elif tab == "kelengkapan":
        ctx["checks"] = L.kelengkapan_data_scan(conn)

    elif tab == "log":
        cari = request.args.get("cari", "").strip()
        tanggal_dari = request.args.get("dari", "").strip()
        tanggal_sampai = request.args.get("sampai", "").strip()
        ctx["cari"] = cari
        ctx["tanggal_dari"] = tanggal_dari
        ctx["tanggal_sampai"] = tanggal_sampai
        ctx["rows"] = L.log_aktivitas_daftar(conn, cari, tanggal_dari, tanggal_sampai)
        ctx["ringkasan"] = L.log_aktivitas_ringkasan(conn)

    return render_template("mutu.html", **ctx)


@bp.route("/target-iku/simpan", methods=["POST"])
def simpan_target_iku():
    conn = current_app.get_db()
    f = request.form
    tahun = f.get("tahun", "").strip()
    nomor_iku = f.get("nomor_iku", type=int)
    if not tahun or not nomor_iku:
        flash("Tahun dan nomor IKU wajib ada.", "error")
        return redirect(url_for("mutu.index", tab="iku"))
    try:
        conn.execute(
            "INSERT INTO target_iku(tahun, nomor_iku, target_nilai, realisasi_manual, catatan) "
            "VALUES(?,?,?,?,?) ON CONFLICT(tahun, nomor_iku) DO UPDATE SET "
            "target_nilai=excluded.target_nilai, realisasi_manual=excluded.realisasi_manual, "
            "catatan=excluded.catatan",
            (
                tahun,
                nomor_iku,
                f.get("target_nilai", type=float),
                f.get("realisasi_manual", type=float),
                f.get("catatan", "").strip(),
            ),
        )
        conn.commit()
        _db.log(conn, "Simpan Target IKU", f"IKU {nomor_iku} tahun {tahun}")
        flash(f"Target IKU {nomor_iku} tersimpan.", "ok")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan target IKU")
    return redirect(url_for("mutu.index", tab="iku", tahun=tahun))


@bp.route("/akreditasi/kriteria/simpan", methods=["POST"])
def simpan_kriteria():
    conn = current_app.get_db()
    f = request.form
    kid = f.get("id", type=int)
    status = f.get("status", "Belum Disusun")
    if status not in C.STATUS_KRITERIA_AKREDITASI_LIST:
        status = "Belum Disusun"
    conn.execute(
        "UPDATE akreditasi_kriteria SET pic_dosen_id=?, status=?, catatan=? WHERE id=?",
        (f.get("pic_dosen_id", type=int), status, f.get("catatan", "").strip(), kid),
    )
    conn.commit()
    _db.log(conn, "Simpan Kriteria Akreditasi", f"kriteria #{kid} -> {status}")
    flash("Kriteria akreditasi diperbarui.", "ok")
    return redirect(url_for("mutu.index", tab="akreditasi", kriteria=kid))


@bp.route("/akreditasi/bukti/unggah", methods=["POST"])
def unggah_bukti():
    conn = current_app.get_db()
    f = request.form
    kriteria_id = f.get("kriteria_id", type=int)
    file = request.files.get("file_bukti")
    if not kriteria_id:
        flash("Kriteria tidak ditemukan.", "error")
        return redirect(url_for("mutu.index", tab="akreditasi"))
    if not file or not file.filename:
        flash("Pilih file bukti terlebih dahulu.", "error")
        return redirect(url_for("mutu.index", tab="akreditasi", kriteria=kriteria_id))

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in C.EKSTENSI_DOKUMEN_DIIZINKAN:
        flash(
            f"Format .{ext} tidak diizinkan. Format yang didukung: "
            f"{', '.join(sorted(C.EKSTENSI_DOKUMEN_DIIZINKAN))}.",
            "error",
        )
        return redirect(url_for("mutu.index", tab="akreditasi", kriteria=kriteria_id))

    nama_asli = secure_filename(file.filename)
    nama_unik = f"{uuid.uuid4().hex[:12]}_{nama_asli}"
    dest = os.path.join(_folder(), nama_unik)
    file.save(dest)
    ukuran_kb = round(os.path.getsize(dest) / 1024)

    conn.execute(
        "INSERT INTO akreditasi_bukti(kriteria_id, judul, file_path, nama_file_asli, ukuran_kb) "
        "VALUES(?,?,?,?,?)",
        (kriteria_id, f.get("judul", "").strip() or nama_asli, dest, nama_asli, ukuran_kb),
    )
    conn.commit()
    _db.log(conn, "Unggah Bukti Akreditasi", nama_asli)
    flash(f"Bukti dukung '{nama_asli}' terunggah.", "ok")
    return redirect(url_for("mutu.index", tab="akreditasi", kriteria=kriteria_id))


@bp.route("/akreditasi/bukti/<int:bid>/unduh")
def unduh_bukti(bid):
    conn = current_app.get_db()
    row = conn.execute("SELECT * FROM akreditasi_bukti WHERE id=?", (bid,)).fetchone()
    if not row or not row["file_path"] or not os.path.exists(row["file_path"]):
        abort(404)
    return send_file(
        row["file_path"], as_attachment=True, download_name=row["nama_file_asli"] or "bukti"
    )


@bp.route("/akreditasi/bukti/<int:bid>/hapus", methods=["POST"])
def hapus_bukti(bid):
    conn = current_app.get_db()
    row = conn.execute("SELECT * FROM akreditasi_bukti WHERE id=?", (bid,)).fetchone()
    kriteria_id = row["kriteria_id"] if row else None
    if row:
        if row["file_path"] and os.path.exists(row["file_path"]):
            try:
                os.remove(row["file_path"])
            except OSError:
                pass
        conn.execute("DELETE FROM akreditasi_bukti WHERE id=?", (bid,))
        conn.commit()
        _db.log(conn, "Hapus Bukti Akreditasi", row["judul"] or str(bid))
    flash("Bukti dukung dihapus.", "ok")
    return redirect(url_for("mutu.index", tab="akreditasi", kriteria=kriteria_id))


@bp.route("/audit/siklus/simpan", methods=["POST"])
def simpan_siklus():
    conn = current_app.get_db()
    f = request.form
    sid = f.get("id", type=int)
    nama = f.get("nama", "").strip()
    if not nama:
        flash("Nama siklus AMI wajib diisi.", "error")
        return redirect(url_for("mutu.index", tab="audit"))
    status = f.get("status", "Direncanakan")
    if status not in C.STATUS_AMI_SIKLUS_LIST:
        status = "Direncanakan"
    # Audit poin 1 (tindak lanjut) — periode_akademik_id dari dropdown
    # terkunci jadi sumber kebenaran; tahun_akademik TEXT diturunkan
    # otomatis dari situ (tetap dipertahankan sbg cache filter/tampilan).
    periode_id = f.get("periode_akademik_id", type=int)
    ta_cache, _sem = _db.cache_periode(conn, periode_id)
    vals = (
        nama,
        periode_id,
        ta_cache,
        f.get("tgl_pelaksanaan", "").strip(),
        f.get("auditor", "").strip(),
        status,
        f.get("catatan", "").strip(),
    )
    try:
        if sid:
            conn.execute(
                "UPDATE ami_siklus SET nama=?, periode_akademik_id=?, tahun_akademik=?, tgl_pelaksanaan=?, "
                "auditor=?, status=?, catatan=? WHERE id=?",
                vals + (sid,),
            )
            flash("Siklus AMI diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO ami_siklus(nama, periode_akademik_id, tahun_akademik, tgl_pelaksanaan, auditor, "
                "status, catatan) VALUES(?,?,?,?,?,?,?)",
                vals,
            )
            flash("Siklus AMI ditambahkan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Siklus AMI", nama)
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan siklus AMI")
    return redirect(url_for("mutu.index", tab="audit"))


@bp.route("/audit/siklus/<int:sid>/hapus", methods=["POST"])
def hapus_siklus(sid):
    conn = current_app.get_db()
    conn.execute("DELETE FROM ami_siklus WHERE id=?", (sid,))
    conn.commit()
    _db.log(conn, "Hapus Siklus AMI", str(sid))
    flash("Siklus AMI dihapus (temuan terkait ikut terhapus).", "ok")
    return redirect(url_for("mutu.index", tab="audit"))


@bp.route("/audit/temuan/simpan", methods=["POST"])
def simpan_temuan():
    conn = current_app.get_db()
    f = request.form
    tid = f.get("id", type=int)
    siklus_id = f.get("siklus_id", type=int)
    uraian = f.get("uraian_temuan", "").strip()
    if not siklus_id or not uraian:
        flash("Siklus dan uraian temuan wajib diisi.", "error")
        return redirect(url_for("mutu.index", tab="audit", siklus=siklus_id))

    kategori = f.get("kategori", "Observasi")
    if kategori not in C.KATEGORI_TEMUAN_AMI_LIST:
        kategori = "Observasi"
    status = f.get("status", "Terbuka")
    if status not in C.STATUS_TEMUAN_AMI_LIST:
        status = "Terbuka"
    vals = (
        siklus_id,
        f.get("standar_spmi", "").strip(),
        uraian,
        kategori,
        f.get("akar_masalah", "").strip(),
        f.get("rencana_tindak_lanjut", "").strip(),
        f.get("pic_dosen_id", type=int),
        f.get("tenggat", "").strip(),
        status,
    )
    try:
        if tid:
            conn.execute(
                "UPDATE ami_temuan SET siklus_id=?, standar_spmi=?, uraian_temuan=?, "
                "kategori=?, akar_masalah=?, rencana_tindak_lanjut=?, pic_dosen_id=?, "
                "tenggat=?, status=? WHERE id=?",
                vals + (tid,),
            )
            flash("Temuan AMI diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO ami_temuan(siklus_id, standar_spmi, uraian_temuan, kategori, "
                "akar_masalah, rencana_tindak_lanjut, pic_dosen_id, tenggat, status) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                vals,
            )
            flash("Temuan AMI dicatat.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Temuan AMI", uraian[:80])
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan temuan AMI")
    return redirect(url_for("mutu.index", tab="audit", siklus=siklus_id))


@bp.route("/audit/temuan/<int:tid>/hapus", methods=["POST"])
def hapus_temuan(tid):
    conn = current_app.get_db()
    row = conn.execute("SELECT siklus_id FROM ami_temuan WHERE id=?", (tid,)).fetchone()
    conn.execute("DELETE FROM ami_temuan WHERE id=?", (tid,))
    conn.commit()
    _db.log(conn, "Hapus Temuan AMI", str(tid))
    flash("Temuan AMI dihapus.", "ok")
    return redirect(url_for("mutu.index", tab="audit", siklus=row["siklus_id"] if row else None))
