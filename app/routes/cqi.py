# -*- coding: utf-8 -*-
"""routes/cqi.py — Modul 12: Siklus CQI (Continuous Quality Improvement).

Item terakhir dari "Belum tercakup" di docs/INTEGRASI_SITIPRO_SIMPRODI.md §7.
Dibangun DI ATAS OBE Assessment Engine (Modul 11): Gap Analysis membaca
capaian_cpl_program() apa adanya (baca-saja, tidak mengubah logika Modul 11),
lalu Kaprodi/tim kurikulum membekukan capaian itu sebagai snapshot saat
membuka 1 siklus CQI per CPL per tahun akademik — snapshot disengaja supaya
rencana tindak lanjut tidak "bergeser" kalau ada nilai baru masuk kemudian
(evaluasi ulang dilakukan lewat siklus BARU pada tahun akademik berikutnya,
bukan menimpa capaian siklus yang sudah berjalan).

Dua tab:
  - Gap Analysis: capaian CPL program saat ini vs target -> tombol buka siklus.
  - Siklus CQI: riwayat & pengelolaan rencana tindak lanjut per siklus (PDCA).
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
from app import logic as L
from app.routes.kurikulum import _kurikulum_aktif

bp = Blueprint("cqi", __name__, url_prefix="/cqi")


@bp.route("/")
def index():
    conn = current_app.get_db()
    tab = request.args.get("tab", "gap-analysis")
    if tab not in ("gap-analysis", "siklus"):
        tab = "gap-analysis"

    kur = _kurikulum_aktif(conn)
    ctx = {"tab": tab, "kur": kur}

    if tab == "gap-analysis":
        # Audit poin 1 (tindak lanjut) — dropdown Periode Akademik terkunci
        # menggantikan setting tahun_akademik_aktif TEXT bebas sbg sumber
        # "periode yang sedang dievaluasi" di Gap Analysis. Default ke
        # periode berstatus 'Berjalan'; operator boleh memilih periode lain
        # (mis. mengevaluasi retrospektif semester yang sudah lewat).
        daftar_periode = _db.get_periode_list(conn)
        periode_id = request.args.get("periode_id", type=int)
        periode_terpilih = (
            _db.get_periode_by_id(conn, periode_id) if periode_id else _db.get_periode_aktif(conn)
        )
        tahun_aktif = (
            periode_terpilih["kode_tahun_ajaran"]
            if periode_terpilih
            else _db.get_setting(conn, "tahun_akademik_aktif", "")
        )
        ctx["tahun_aktif"] = tahun_aktif
        ctx["daftar_periode"] = daftar_periode
        ctx["periode_terpilih"] = periode_terpilih
        capaian = L.capaian_cpl_program(conn, kur["id"]) if kur else []
        existing = {}
        if kur:
            for r in conn.execute(
                "SELECT * FROM cqi_siklus WHERE kurikulum_id=? AND tahun_akademik=?",
                (kur["id"], tahun_aktif),
            ).fetchall():
                existing[r["cpl_id"]] = r
        rows = []
        for c in capaian:
            siklus = existing.get(c["cpl"]["id"])
            target = siklus["target_persen"] if siklus else C.TARGET_CAPAIAN_CPL_DEFAULT
            gap = None
            if c["persen_tuntas"] is not None:
                gap = round(target - c["persen_tuntas"], 1)
            rows.append({**c, "target": target, "gap": gap, "siklus": siklus})
        ctx["rows"] = rows

    elif tab == "siklus":
        tahun_filter = request.args.get("tahun_akademik", "").strip()
        sql = (
            "SELECT s.*, c.kode AS cpl_kode, c.kategori AS cpl_kategori, "
            "c.deskripsi AS cpl_deskripsi FROM cqi_siklus s "
            "JOIN cpl c ON c.id = s.cpl_id WHERE 1=1"
        )
        params = []
        if tahun_filter:
            sql += " AND s.tahun_akademik=?"
            params.append(tahun_filter)
        sql += " ORDER BY s.tahun_akademik DESC, s.dibuat_pada DESC"
        ctx["rows"] = conn.execute(sql, params).fetchall()
        ctx["tahun_filter"] = tahun_filter
        ctx["daftar_tahun"] = [
            r["tahun_akademik"]
            for r in conn.execute(
                "SELECT DISTINCT tahun_akademik FROM cqi_siklus ORDER BY tahun_akademik DESC"
            ).fetchall()
        ]
        edit_id = request.args.get("edit", type=int)
        ctx["edit_row"] = (
            conn.execute(
                "SELECT s.*, c.kode AS cpl_kode FROM cqi_siklus s JOIN cpl c ON c.id = s.cpl_id "
                "WHERE s.id=?",
                (edit_id,),
            ).fetchone()
            if edit_id
            else None
        )
        ctx["status_list"] = C.STATUS_CQI_LIST

    return render_template("cqi.html", **ctx)


@bp.route("/gap-analysis/buka", methods=["POST"])
def buka_siklus():
    conn = current_app.get_db()
    f = request.form
    kur = _kurikulum_aktif(conn)
    cpl_id = f.get("cpl_id", type=int)
    # Audit poin 1 (tindak lanjut) — periode_akademik_id dari dropdown
    # terkunci di tab Gap Analysis jadi sumber kebenaran; tahun_akademik
    # TEXT diturunkan otomatis (tetap dipertahankan sbg cache filter/rekap).
    periode_id = f.get("periode_akademik_id", type=int)
    tahun_akademik, _sem = _db.cache_periode(conn, periode_id)
    if not tahun_akademik:
        tahun_akademik = f.get("tahun_akademik", "").strip()  # fallback data lama
    target_persen = f.get("target_persen", type=float) or C.TARGET_CAPAIAN_CPL_DEFAULT

    if not kur or not cpl_id or not tahun_akademik:
        flash("Data tidak lengkap untuk membuka siklus CQI — pilih Periode Akademik dulu.", "error")
        return redirect(url_for("cqi.index", tab="gap-analysis"))

    # Capaian dihitung ulang di server (bukan dipercaya dari form) supaya
    # snapshot yang dibekukan selalu benar-benar mencerminkan data terkini
    # saat siklus dibuka.
    capaian = L.capaian_cpl_program(conn, kur["id"])
    capaian_row = next((c for c in capaian if c["cpl"]["id"] == cpl_id), None)
    capaian_persen = capaian_row["persen_tuntas"] if capaian_row else None

    existing = conn.execute(
        "SELECT id FROM cqi_siklus WHERE kurikulum_id=? AND cpl_id=? AND tahun_akademik=?",
        (kur["id"], cpl_id, tahun_akademik),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE cqi_siklus SET target_persen=?, capaian_persen=?, periode_akademik_id=? WHERE id=?",
            (target_persen, capaian_persen, periode_id, existing["id"]),
        )
        sid = existing["id"]
        flash("Siklus CQI diperbarui dengan capaian terkini.", "ok")
    else:
        cur = conn.execute(
            "INSERT INTO cqi_siklus(kurikulum_id, cpl_id, tahun_akademik, target_persen, "
            "capaian_persen, status, periode_akademik_id) VALUES(?,?,?,?,?,'Direncanakan',?)",
            (kur["id"], cpl_id, tahun_akademik, target_persen, capaian_persen, periode_id),
        )
        sid = cur.lastrowid
        flash("Siklus CQI dibuka. Lengkapi rencana tindak lanjut di tab Siklus CQI.", "ok")
    conn.commit()
    _db.log(conn, "Buka Siklus CQI", f"CPL #{cpl_id} {tahun_akademik}")
    return redirect(url_for("cqi.index", tab="siklus", edit=sid))


@bp.route("/siklus/simpan", methods=["POST"])
def simpan_siklus():
    conn = current_app.get_db()
    f = request.form
    sid = f.get("id", type=int)
    if not sid:
        flash("Siklus CQI tidak ditemukan.", "error")
        return redirect(url_for("cqi.index", tab="siklus"))

    status = f.get("status", "Direncanakan")
    if status not in C.STATUS_CQI_LIST:
        status = "Direncanakan"

    # Audit Phase 4 (retrofit Phase 6) — nilai lama status siklus, utk
    # audit event kalau berubah (mis. "Berjalan -> Selesai" saat rencana
    # tindak lanjut PDCA dinyatakan tuntas).
    sebelum = conn.execute("SELECT status FROM cqi_siklus WHERE id=?", (sid,)).fetchone()
    status_lama = sebelum["status"] if sebelum else None

    conn.execute(
        "UPDATE cqi_siklus SET akar_masalah=?, rencana_tindak_lanjut=?, "
        "penanggung_jawab=?, tenggat=?, status=?, evaluasi_hasil=? WHERE id=?",
        (
            f.get("akar_masalah", "").strip(),
            f.get("rencana_tindak_lanjut", "").strip(),
            f.get("penanggung_jawab", "").strip(),
            f.get("tenggat", "").strip(),
            status,
            f.get("evaluasi_hasil", "").strip(),
            sid,
        ),
    )
    conn.commit()
    if status_lama != status:
        _db.log(
            conn, "Simpan Siklus CQI", str(sid),
            modul="CQI", entitas="Siklus CQI", entitas_id=sid,
            nilai_lama=status_lama, nilai_baru=status,
        )
    else:
        _db.log(conn, "Simpan Siklus CQI", str(sid), modul="CQI", entitas="Siklus CQI", entitas_id=sid)
    flash("Rencana tindak lanjut CQI disimpan.", "ok")
    return redirect(url_for("cqi.index", tab="siklus"))


@bp.route("/siklus/<int:sid>/hapus", methods=["POST"])
def hapus_siklus(sid):
    conn = current_app.get_db()
    row = conn.execute("SELECT status FROM cqi_siklus WHERE id=?", (sid,)).fetchone()
    if not row:
        flash("Siklus CQI tidak ditemukan.", "error")
        return redirect(url_for("cqi.index", tab="siklus"))
    # Audit Menyeluruh — PHASE 6 (mengikuti pola proteksi arsip Phase 1/5):
    # siklus CQI yang sudah "Selesai" adalah bukti PDCA yang biasanya
    # dilampirkan langsung ke borang akreditasi (akar masalah, rencana
    # tindak lanjut, DAN evaluasi hasilnya) — tidak boleh hilang begitu
    # saja. Siklus yang masih Direncanakan/Berjalan (belum jadi bukti
    # final) tetap boleh dihapus normal (mis. salah buka siklus).
    if row["status"] == "Selesai":
        flash(
            "Siklus CQI ini sudah berstatus Selesai (bukti PDCA lengkap dgn evaluasi hasil) — "
            "tidak bisa dihapus. Kalau perlu revisi, ubah datanya lewat tombol Ubah, jangan Hapus.",
            "error",
        )
        return redirect(url_for("cqi.index", tab="siklus"))
    conn.execute("DELETE FROM cqi_siklus WHERE id=?", (sid,))
    conn.commit()
    _db.log(conn, "Hapus Siklus CQI", str(sid), modul="CQI", entitas="Siklus CQI", entitas_id=sid)
    flash("Siklus CQI dihapus.", "ok")
    return redirect(url_for("cqi.index", tab="siklus"))
