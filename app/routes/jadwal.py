# -*- coding: utf-8 -*-
"""routes/jadwal.py — Modul 10: Jadwal Kelas & BAP (Berita Acara Perkuliahan).

Fondasi data akademik tambahan yang sebelumnya belum ada di SIMPRODI (lihat
docs/INTEGRASI_SITIPRO_SIMPRODI.md §7, "Belum tercakup"): jadwal kelas per
tahun akademik/semester, dipakai juga oleh Modul 11 (Nilai & OBE Assessment
Engine) sebagai unit "siapa mengambil mata kuliah apa, di kelas mana".

Dua tab (mirip pola Modul 6 & Modul 9):
  - Jadwal Kelas: CRUD kelas per mata kuliah kurikulum aktif.
  - BAP: log per pertemuan (materi, Sub-CPMK rujukan, kehadiran), realisasi
    dihitung on-the-fly dari logic.realisasi_bap() — bukan angka statis.
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
from app import error_utils as EH
from app import logic as L
from app.routes.kurikulum import _kurikulum_aktif

bp = Blueprint("jadwal", __name__, url_prefix="/jadwal")


def _mk_kurikulum_aktif(conn):
    kur = _kurikulum_aktif(conn)
    if not kur:
        return []
    return conn.execute(
        "SELECT * FROM mata_kuliah WHERE kurikulum_id=? ORDER BY semester, kode",
        (kur["id"],),
    ).fetchall()


@bp.route("/")
def index():
    conn = current_app.get_db()
    tab = request.args.get("tab", "kelas")
    if tab not in ("kelas", "bap"):
        tab = "kelas"

    ctx = {
        "tab": tab,
        "mk_list": _mk_kurikulum_aktif(conn),
        "dosen_list": conn.execute(
            "SELECT id, nama FROM dosen WHERE aktif=1 ORDER BY nama"
        ).fetchall(),
        "ruangan_list": conn.execute("SELECT id, nama FROM ruangan ORDER BY nama").fetchall(),
        "hari_list": C.HARI_LIST,
        "semester_list": C.SEMESTER_LIST,
        "tahun_akademik_aktif": _db.get_setting(conn, "tahun_akademik_aktif", ""),
        # Audit poin 1 (tindak lanjut) — dropdown "Periode Akademik" terkunci,
        # pola sama dengan Modul SDM/Kegiatan/Mutu.
        "daftar_periode": _db.get_periode_list(conn),
    }

    if tab == "kelas":
        tahun_filter = request.args.get("tahun_akademik", "").strip()
        sql = (
            "SELECT jk.*, mk.kode AS mk_kode, mk.nama AS mk_nama, mk.sks AS mk_sks, "
            "d.nama AS dosen_nama, r.nama AS ruangan_nama FROM jadwal_kelas jk "
            "JOIN mata_kuliah mk ON mk.id = jk.mata_kuliah_id "
            "LEFT JOIN dosen d ON d.id = jk.dosen_id "
            "LEFT JOIN ruangan r ON r.id = jk.ruangan_id WHERE 1=1"
        )
        params = []
        if tahun_filter:
            sql += " AND jk.tahun_akademik=?"
            params.append(tahun_filter)
        sql += " ORDER BY jk.tahun_akademik DESC, mk.semester, mk.kode, jk.kelas"
        rows = conn.execute(sql, params).fetchall()
        ctx["rows"] = [
            dict(r, realisasi=L.realisasi_bap(conn, r["id"], r["jumlah_pertemuan_rencana"]))
            for r in rows
        ]
        ctx["tahun_filter"] = tahun_filter
        ctx["daftar_tahun"] = [
            r["tahun_akademik"]
            for r in conn.execute(
                "SELECT DISTINCT tahun_akademik FROM jadwal_kelas ORDER BY tahun_akademik DESC"
            ).fetchall()
        ]

        edit_id = request.args.get("edit", type=int)
        ctx["edit_row"] = (
            conn.execute("SELECT * FROM jadwal_kelas WHERE id=?", (edit_id,)).fetchone()
            if edit_id
            else None
        )

    elif tab == "bap":
        jadwal_rows = conn.execute(
            "SELECT jk.*, mk.kode AS mk_kode, mk.nama AS mk_nama FROM jadwal_kelas jk "
            "JOIN mata_kuliah mk ON mk.id = jk.mata_kuliah_id "
            "ORDER BY jk.tahun_akademik DESC, mk.kode, jk.kelas"
        ).fetchall()
        ctx["jadwal_rows"] = jadwal_rows
        jid = request.args.get("jadwal", type=int)
        if not jid and jadwal_rows:
            jid = jadwal_rows[0]["id"]
        jadwal_terpilih = (
            conn.execute(
                "SELECT jk.*, mk.kode AS mk_kode, mk.nama AS mk_nama, mk.id AS mata_kuliah_id "
                "FROM jadwal_kelas jk JOIN mata_kuliah mk ON mk.id = jk.mata_kuliah_id "
                "WHERE jk.id=?",
                (jid,),
            ).fetchone()
            if jid
            else None
        )
        ctx["jadwal_terpilih"] = jadwal_terpilih
        if jadwal_terpilih:
            ctx["bap_rows"] = conn.execute(
                "SELECT b.*, sc.kode AS sub_cpmk_kode FROM bap b "
                "LEFT JOIN sub_cpmk sc ON sc.id = b.sub_cpmk_id "
                "WHERE b.jadwal_kelas_id=? ORDER BY b.pertemuan_ke",
                (jid,),
            ).fetchall()
            ctx["sub_cpmk_list"] = L.sub_cpmk_untuk_mk(conn, jadwal_terpilih["mata_kuliah_id"])
            ctx["realisasi"] = L.realisasi_bap(
                conn, jid, jadwal_terpilih["jumlah_pertemuan_rencana"]
            )
            n_next = conn.execute(
                "SELECT COALESCE(MAX(pertemuan_ke),0)+1 n FROM bap WHERE jadwal_kelas_id=?", (jid,)
            ).fetchone()["n"]
            ctx["pertemuan_berikutnya"] = n_next
        else:
            ctx["bap_rows"] = []
            ctx["sub_cpmk_list"] = []
            ctx["realisasi"] = None
            ctx["pertemuan_berikutnya"] = 1
        ctx["status_bap_list"] = C.STATUS_BAP_LIST

    return render_template("jadwal.html", **ctx)


@bp.route("/kelas/simpan", methods=["POST"])
def simpan_kelas():
    conn = current_app.get_db()
    f = request.form
    kid = f.get("id", type=int)
    mata_kuliah_id = f.get("mata_kuliah_id", type=int)
    kelas = f.get("kelas", "A").strip() or "A"

    # Audit poin 1 (tindak lanjut) — dropdown "Periode Akademik" terkunci
    # sekarang jadi SATU-SATUNYA cara mengisi tahun_akademik/semester_ajaran
    # (dropdown ini menggantikan input teks bebas & pilihan semester lama di
    # form), pola persis sama dengan Modul SDM/Kegiatan/Mutu (lihat
    # db.cache_periode). Kolom TEXT lama tetap ada sebagai cache tampilan &
    # tetap dipakai apa adanya oleh filter/rekap yang sudah ada.
    periode_id = f.get("periode_akademik_id", type=int)
    tahun_akademik, semester_ajaran = _db.cache_periode(conn, periode_id)

    if not mata_kuliah_id or not periode_id or not tahun_akademik:
        flash("Mata kuliah dan Periode Akademik wajib dipilih.", "error")
        return redirect(url_for("jadwal.index", tab="kelas"))

    hari = f.get("hari", "").strip()
    jam_mulai = f.get("jam_mulai", "").strip()
    jam_selesai = f.get("jam_selesai", "").strip()
    dosen_id = f.get("dosen_id", type=int)
    ruangan_id = f.get("ruangan_id", type=int)

    if hari and jam_mulai and jam_selesai:
        temuan = L.cek_bentrok_kelas(
            conn, hari, jam_mulai, jam_selesai, ruangan_id, dosen_id, periode_id, exclude_id=kid
        )
        errors = [t["pesan"] for t in temuan if t["level"] == "error"]
        if errors and not f.get("konfirmasi_bentrok"):
            return render_template(
                "_bentrok_confirm.html",
                errors=errors,
                action=url_for("jadwal.simpan_kelas"),
                form=f,
            )

    vals = (
        mata_kuliah_id,
        tahun_akademik,
        semester_ajaran,
        kelas,
        f.get("dosen_id", type=int),
        f.get("hari", "").strip(),
        f.get("jam_mulai", "").strip(),
        f.get("jam_selesai", "").strip(),
        f.get("ruangan_id", type=int),
        f.get("jumlah_pertemuan_rencana", type=int) or 16,
        f.get("keterangan", "").strip(),
        periode_id,
    )
    try:
        if kid:
            conn.execute(
                "UPDATE jadwal_kelas SET mata_kuliah_id=?, tahun_akademik=?, semester_ajaran=?, "
                "kelas=?, dosen_id=?, hari=?, jam_mulai=?, jam_selesai=?, ruangan_id=?, "
                "jumlah_pertemuan_rencana=?, keterangan=?, periode_akademik_id=? WHERE id=?",
                vals + (kid,),
            )
            flash("Jadwal kelas diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO jadwal_kelas(mata_kuliah_id, tahun_akademik, semester_ajaran, "
                "kelas, dosen_id, hari, jam_mulai, jam_selesai, ruangan_id, "
                "jumlah_pertemuan_rencana, keterangan, periode_akademik_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                vals,
            )
            flash("Jadwal kelas ditambahkan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Jadwal Kelas", f"{tahun_akademik} kelas {kelas}")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan jadwal kelas")
    return redirect(url_for("jadwal.index", tab="kelas"))


@bp.route("/kelas/<int:kid>/hapus", methods=["POST"])
def hapus_kelas(kid):
    conn = current_app.get_db()
    conn.execute("DELETE FROM jadwal_kelas WHERE id=?", (kid,))
    conn.commit()
    _db.log(conn, "Hapus Jadwal Kelas", str(kid))
    flash("Jadwal kelas dihapus (BAP & KRS terkait ikut terhapus).", "ok")
    return redirect(url_for("jadwal.index", tab="kelas"))


@bp.route("/bap/simpan", methods=["POST"])
def simpan_bap():
    conn = current_app.get_db()
    f = request.form
    bid = f.get("id", type=int)
    jadwal_kelas_id = f.get("jadwal_kelas_id", type=int)
    pertemuan_ke = f.get("pertemuan_ke", type=int)

    if not jadwal_kelas_id or not pertemuan_ke:
        flash("Kelas dan nomor pertemuan wajib diisi.", "error")
        return redirect(url_for("jadwal.index", tab="bap", jadwal=jadwal_kelas_id))

    status = f.get("status", "Terlaksana")
    if status not in C.STATUS_BAP_LIST:
        status = "Terlaksana"
    sub_cpmk_id = f.get("sub_cpmk_id", type=int) or None

    vals = (
        pertemuan_ke,
        f.get("tanggal", "").strip(),
        f.get("materi", "").strip(),
        sub_cpmk_id,
        f.get("jumlah_hadir", type=int),
        f.get("dosen_pengganti", "").strip(),
        f.get("catatan", "").strip(),
        status,
    )
    try:
        if bid:
            conn.execute(
                "UPDATE bap SET pertemuan_ke=?, tanggal=?, materi=?, sub_cpmk_id=?, "
                "jumlah_hadir=?, dosen_pengganti=?, catatan=?, status=? WHERE id=?",
                vals + (bid,),
            )
            flash(f"Pertemuan ke-{pertemuan_ke} diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO bap(jadwal_kelas_id, pertemuan_ke, tanggal, materi, sub_cpmk_id, "
                "jumlah_hadir, dosen_pengganti, catatan, status) VALUES(?,?,?,?,?,?,?,?,?)",
                (jadwal_kelas_id,) + vals,
            )
            flash(f"BAP pertemuan ke-{pertemuan_ke} dicatat.", "ok")
        conn.commit()
        _db.log(conn, "Simpan BAP", f"jadwal #{jadwal_kelas_id} pertemuan {pertemuan_ke}")
    except Exception as e:
        EH.flash_gagal_simpan(
            e, "Gagal menyimpan BAP. Pastikan nomor pertemuan belum dipakai untuk kelas ini"
        )
    return redirect(url_for("jadwal.index", tab="bap", jadwal=jadwal_kelas_id))


@bp.route("/bap/<int:bid>/hapus", methods=["POST"])
def hapus_bap(bid):
    conn = current_app.get_db()
    row = conn.execute("SELECT jadwal_kelas_id FROM bap WHERE id=?", (bid,)).fetchone()
    conn.execute("DELETE FROM bap WHERE id=?", (bid,))
    conn.commit()
    _db.log(conn, "Hapus BAP", str(bid))
    flash("Catatan BAP dihapus.", "ok")
    return redirect(
        url_for("jadwal.index", tab="bap", jadwal=row["jadwal_kelas_id"] if row else None)
    )
