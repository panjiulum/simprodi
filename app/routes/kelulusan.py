# -*- coding: utf-8 -*-
"""routes/kelulusan.py — Rencana Yudisium, Wisuda, Tracer Study Alumni.
Yudisium & Wisuda listnya auto-generate (lewat logic.sync_*), operator
tinggal melengkapi beberapa kolom manual."""

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
from app import export_utils
from app import logic as L

bp = Blueprint("kelulusan", __name__, url_prefix="/kelulusan")


def _tahap_opsi(conn):
    """Daftar opsi filter tahap — sama seperti routes/rekap.py::_tahap_opsi,
    dipakai supaya Rencana Yudisium/Wisuda/SK Yudisium juga bisa disaring
    dan diproses per tahap/gelombang, konsisten dengan rekap honor."""
    tahap_rows = list(_db.get_tahap_list(conn))
    if tahap_rows:
        return ["Semua"] + [t["nama"] for t in tahap_rows]
    lama = [_db.get_setting(conn, "nama_tahap_1"), _db.get_setting(conn, "nama_tahap_2")]
    return ["Semua"] + [t for t in lama if t]


# ------------------------------------------------------------------ Yudisium
@bp.route("/yudisium")
def yudisium_list():
    conn = current_app.get_db()
    L.sync_yudisium_dari_sidang(conn)
    conn.commit()
    tahap = request.args.get("tahap", "Semua")
    rows = L.rencana_yudisium_rows(conn, tahap if tahap != "Semua" else None)
    edit_mid = request.args.get("edit", type=int)
    edit_row = None
    edit_mhs = None
    if edit_mid:
        edit_row = conn.execute(
            "SELECT * FROM yudisium WHERE mahasiswa_id=?", (edit_mid,)
        ).fetchone()
        edit_mhs = conn.execute(
            "SELECT nim, nama FROM mahasiswa WHERE id=?", (edit_mid,)
        ).fetchone()
    return render_template(
        "yudisium.html",
        rows=rows,
        edit_row=edit_row,
        edit_mhs=edit_mhs,
        edit_mid=edit_mid,
        STATUS_YUDISIUM_LIST=C.STATUS_YUDISIUM_LIST,
        tahap=tahap,
        tahap_opsi=_tahap_opsi(conn),
    )


@bp.route("/yudisium/tetapkan-tahap", methods=["POST"])
def yudisium_tetapkan_tahap():
    """Menetapkan No. SK Yudisium + Tgl Yudisium sekaligus untuk SEMUA
    mahasiswa pada satu Tahap/Gelombang (satu SK Yudisium memang lazimnya
    berlaku untuk satu batch/tahap kelulusan, bukan per-mahasiswa satu-satu).
    Baris yang No. SK-nya sudah diisi manual sebelumnya TIDAK ditimpa,
    kecuali operator mencentang 'Timpa data yang sudah ada'."""
    conn = current_app.get_db()
    f = request.form
    tahap = (f.get("tahap") or "").strip()
    no_sk = (f.get("no_sk_batch") or "").strip()
    tgl = (f.get("tgl_yudisium_batch") or "").strip()
    timpa = f.get("timpa") == "1"
    if not tahap or tahap == "Semua":
        flash("Pilih Tahap/Gelombang tertentu dahulu (bukan \"Semua\") untuk menetapkan No. SK per tahap.", "error")
        return redirect(url_for("kelulusan.yudisium_list"))
    if not no_sk:
        flash("No. SK Yudisium wajib diisi.", "error")
        return redirect(url_for("kelulusan.yudisium_list", tahap=tahap))
    try:
        rows = L.rencana_yudisium_rows(conn, tahap)
        jumlah = 0
        for r in rows:
            if not timpa and (r["no_sk"] or "").strip():
                continue
            conn.execute(
                "UPDATE yudisium SET no_sk=?, tgl_yudisium=?, "
                "status_yudisium=CASE WHEN status_yudisium='Direncanakan' THEN 'Terlaksana' "
                "ELSE status_yudisium END WHERE mahasiswa_id=?",
                (no_sk, tgl, r["mahasiswa_id"]),
            )
            jumlah += 1
        conn.commit()
        _db.log(conn, "Tetapkan SK Yudisium per Tahap", f"{tahap} ({jumlah} mahasiswa)")
        L.sync_wisuda_dari_yudisium(conn)
        conn.commit()
        flash(f"No. SK Yudisium diterapkan ke {jumlah} mahasiswa pada tahap \"{tahap}\".", "ok")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menetapkan No. SK per tahap")
    return redirect(url_for("kelulusan.yudisium_list", tahap=tahap))


@bp.route("/yudisium/simpan", methods=["POST"])
def yudisium_simpan():
    """Audit Lanjutan (Kelulusan/Tracer Study) — temuan: berbeda dari
    hampir semua handler simpan lain di aplikasi ini (yang seragam
    dibungkus try/except -> error_utils.flash_gagal_simpan, lihat
    tracer_simpan di bawah atau kegiatan.py), fungsi ini SEBELUMNYA tidak
    dibungkus sama sekali. Konversi `float(ipk)` bisa melempar ValueError
    kalau operator salah ketik di kolom IPK Final (input teks bebas di
    yudisium.html, bukan <input type="number">) -> 500 Internal Server
    Error mentah, bukan pesan ramah seperti pola di seluruh modul lain.
    Sekaligus divalidasi: IPK harus dalam rentang wajar 0.00-4.00 (dulu
    nilai apa pun diterima mentah-mentah termasuk mis. "40" hasil salah
    ketik), dan status_yudisium harus salah satu dari daftar resmi
    (dulu string bebas apa pun diterima langsung ke kolom status)."""
    conn = current_app.get_db()
    f = request.form
    mid = f.get("mahasiswa_id", type=int)
    if not mid:
        flash("Data tidak valid.", "error")
        return redirect(url_for("kelulusan.yudisium_list"))
    ipk_raw = (f.get("ipk_final") or "").strip()
    if ipk_raw:
        try:
            ipk = float(ipk_raw.replace(",", "."))
        except ValueError:
            flash(
                f'IPK Final "{ipk_raw}" bukan angka yang valid — gunakan format desimal (mis. 3.75).',
                "error",
            )
            return redirect(url_for("kelulusan.yudisium_list", edit=mid))
        if not (0 <= ipk <= 4):
            flash("IPK Final harus di antara 0.00 dan 4.00.", "error")
            return redirect(url_for("kelulusan.yudisium_list", edit=mid))
    else:
        ipk = None
    status = f.get("status_yudisium") or "Direncanakan"
    if status not in C.STATUS_YUDISIUM_LIST:
        status = "Direncanakan"
    try:
        # Audit Phase 4 — nilai lama status_yudisium, utk audit event.
        sebelum = conn.execute("SELECT status_yudisium FROM yudisium WHERE mahasiswa_id=?", (mid,)).fetchone()
        status_yudisium_lama = sebelum["status_yudisium"] if sebelum else None
        conn.execute(
            "UPDATE yudisium SET ipk_final=?, tgl_yudisium=?, no_sk=?, status_yudisium=? WHERE mahasiswa_id=?",
            (ipk, f.get("tgl_yudisium", ""), f.get("no_sk", ""), status, mid),
        )
        if status_yudisium_lama != status:
            _db.log(
                conn, "Update Yudisium", str(mid),
                modul="Kelulusan", entitas="Yudisium", entitas_id=mid,
                nilai_lama=status_yudisium_lama, nilai_baru=status,
            )
        else:
            _db.log(conn, "Update Yudisium", str(mid), modul="Kelulusan", entitas="Yudisium", entitas_id=mid)
        if status == "Terlaksana":
            # Audit Phase 3 (re-check) — transisi status_ta ke "Menunggu
            # Wisuda" sebelumnya lewat UPDATE langsung, TIDAK PERNAH lewat
            # workflow_ta.catat_transisi() seperti transisi status_ta
            # lainnya (lihat logic.recalculate_status_ta) -- artinya
            # riwayat di halaman Ubah Data Mahasiswa akan punya "lubang"
            # persis di titik paling penting (kelulusan final). Diperbaiki
            # supaya transisi ini juga tercatat, konsisten dgn semua
            # transisi status_ta lainnya.
            row_mhs = conn.execute("SELECT status_ta FROM mahasiswa WHERE id=?", (mid,)).fetchone()
            status_ta_lama = row_mhs["status_ta"] if row_mhs else None
            if status_ta_lama != C.STATUS_TA_MENUNGGU_WISUDA:
                conn.execute(
                    "UPDATE mahasiswa SET status_ta=? WHERE id=?", (C.STATUS_TA_MENUNGGU_WISUDA, mid)
                )
                conn.commit()
                from app import workflow_ta

                workflow_ta.catat_transisi(
                    conn, mid, status_ta_lama, C.STATUS_TA_MENUNGGU_WISUDA,
                    dipicu_oleh="Yudisium ditetapkan Terlaksana",
                )
        conn.commit()
        L.sync_wisuda_dari_yudisium(conn)
        conn.commit()
        flash("Data yudisium disimpan.", "ok")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan data yudisium")
    return redirect(url_for("kelulusan.yudisium_list"))


@bp.route("/yudisium/ekspor")
def yudisium_ekspor():
    conn = current_app.get_db()
    tahap = request.args.get("tahap", "Semua")
    rows = L.rencana_yudisium_rows(conn, tahap if tahap != "Semua" else None)
    headers = [
        "NIM",
        "Nama",
        "J/K",
        "Tahap/Gelombang",
        "Judul Skripsi",
        "Nilai Angka",
        "Nilai Huruf",
        "IPK Final",
        "Predikat",
        "Tgl Yudisium",
        "No SK",
        "Status",
    ]
    data = [
        (
            r["nim"],
            r["nama"],
            r["jk"],
            r["tahap"] or "",
            r["judul_sidang"] or "",
            r["nilai_angka"],
            r["nilai_huruf"],
            r["ipk_final"],
            r["predikat"],
            r["tgl_yudisium"] or "",
            r["no_sk"] or "",
            r["status_yudisium"],
        )
        for r in rows
    ]
    return export_utils.kirim_excel("Rencana Yudisium", headers, data)


# --------------------------------------------------------------------- Wisuda
@bp.route("/wisuda")
def wisuda_list():
    conn = current_app.get_db()
    L.sync_wisuda_dari_yudisium(conn)
    conn.commit()
    tahap = request.args.get("tahap", "Semua")
    rows = L.wisuda_rows(conn, tahap if tahap != "Semua" else None)
    edit_mid = request.args.get("edit", type=int)
    edit_row = None
    edit_mhs = None
    if edit_mid:
        edit_row = conn.execute("SELECT * FROM wisuda WHERE mahasiswa_id=?", (edit_mid,)).fetchone()
        edit_mhs = conn.execute(
            "SELECT nim, nama FROM mahasiswa WHERE id=?", (edit_mid,)
        ).fetchone()
    return render_template(
        "wisuda.html",
        rows=rows,
        edit_row=edit_row,
        edit_mhs=edit_mhs,
        edit_mid=edit_mid,
        tahap=tahap,
        tahap_opsi=_tahap_opsi(conn),
    )


@bp.route("/wisuda/simpan", methods=["POST"])
def wisuda_simpan():
    """Audit Lanjutan — dibungkus try/except utk konsisten dgn seluruh
    handler simpan lain di aplikasi (lihat catatan di yudisium_simpan di
    atas): walau ketiga kolom di sini murni TEXT (risiko error lebih
    rendah dari IPK numerik di Yudisium), tetap ada celah realistis, mis.
    galat OSError/"database is locked" saat commit — sebelumnya akan
    lolos jadi 500 mentah, bukan flash pesan ramah seperti modul lain."""
    conn = current_app.get_db()
    f = request.form
    mid = f.get("mahasiswa_id", type=int)
    if not mid:
        flash("Data tidak valid.", "error")
        return redirect(url_for("kelulusan.wisuda_list"))
    try:
        conn.execute(
            "UPDATE wisuda SET tgl_wisuda=?, no_ijazah=?, catatan=? WHERE mahasiswa_id=?",
            (f.get("tgl_wisuda", ""), f.get("no_ijazah", ""), f.get("catatan", ""), mid),
        )
        conn.commit()
        _db.log(conn, "Update Wisuda", str(mid))
        flash("Data wisuda disimpan.", "ok")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan data wisuda")
    return redirect(url_for("kelulusan.wisuda_list"))


@bp.route("/wisuda/ekspor")
def wisuda_ekspor():
    conn = current_app.get_db()
    tahap = request.args.get("tahap", "Semua")
    rows = L.wisuda_rows(conn, tahap if tahap != "Semua" else None)
    headers = [
        "NIM",
        "Nama",
        "J/K",
        "Tahap/Gelombang",
        "Judul Skripsi",
        "IPK Final",
        "Predikat",
        "Tgl Yudisium",
        "Tgl Wisuda",
        "No Ijazah",
        "Catatan",
    ]
    data = [
        (
            r["nim"],
            r["nama"],
            r["jk"],
            r["tahap"] or "",
            r["judul_sidang"] or "",
            r["ipk_final"],
            r["predikat"],
            r["tgl_yudisium"] or "",
            r["tgl_wisuda"] or "",
            r["no_ijazah"] or "",
            r["catatan"] or "",
        )
        for r in rows
    ]
    return export_utils.kirim_excel("Wisuda", headers, data)


# --------------------------------------------------------------- Tracer Study
@bp.route("/tracer")
def tracer_list():
    conn = current_app.get_db()
    rows = conn.execute(
        "SELECT t.*, m.nim, m.nama FROM tracer_study t JOIN mahasiswa m ON m.id=t.mahasiswa_id ORDER BY m.nama"
    ).fetchall()
    alumni = conn.execute(
        "SELECT m.id, m.nim, m.nama FROM mahasiswa m JOIN wisuda w ON w.mahasiswa_id=m.id ORDER BY m.nama"
    ).fetchall()
    edit_id = request.args.get("edit", type=int)
    edit_row = None
    if edit_id:
        edit_row = conn.execute("SELECT * FROM tracer_study WHERE id=?", (edit_id,)).fetchone()
    return render_template(
        "tracer.html",
        rows=rows,
        alumni=alumni,
        edit_row=edit_row,
        STATUS_KERJA_LIST=C.STATUS_KERJA_LIST,
        STUDI_LANJUT_LIST=C.STUDI_LANJUT_LIST,
    )


@bp.route("/tracer/simpan", methods=["POST"])
def tracer_simpan():
    conn = current_app.get_db()
    f = request.form
    tid = f.get("id", type=int)
    mid = f.get("mahasiswa_id", type=int)
    if not mid:
        flash("Pilih alumni terlebih dahulu.", "error")
        return redirect(url_for("kelulusan.tracer_list"))
    data = (
        mid,
        f.get("status_saat_ini", ""),
        f.get("nama_instansi", ""),
        f.get("posisi", ""),
        f.get("kesesuaian_bidang", ""),
        f.get("waktu_tunggu", ""),
        f.get("studi_lanjut", ""),
        f.get("program_lanjut", ""),
        f.get("no_hp", ""),
        f.get("catatan", ""),
    )
    try:
        if tid:
            conn.execute(
                "UPDATE tracer_study SET mahasiswa_id=?,status_saat_ini=?,nama_instansi=?,posisi=?,"
                "kesesuaian_bidang=?,waktu_tunggu=?,studi_lanjut=?,program_lanjut=?,no_hp=?,catatan=? "
                "WHERE id=?",
                data + (tid,),
            )
            flash("Data tracer study diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO tracer_study(mahasiswa_id,status_saat_ini,nama_instansi,posisi,"
                "kesesuaian_bidang,waktu_tunggu,studi_lanjut,program_lanjut,no_hp,catatan) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                data,
            )
            flash("Data tracer study disimpan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Tracer Study", str(mid))
    except Exception as e:
        EH.flash_gagal_simpan(e, "Alumni ini mungkin sudah punya data tracer study")
    return redirect(url_for("kelulusan.tracer_list"))


@bp.route("/tracer/<int:tid>/hapus", methods=["POST"])
def tracer_hapus(tid):
    """Audit Lanjutan — temuan: berbeda dari hapus_proker()/hapus_kegiatan()
    di kegiatan.py (juga hapus di modul lain), penghapusan di sini
    SEBELUMNYA tidak tercatat ke _db.log() sama sekali, jadi ada jejak
    audit yang bolong utk aksi destruktif ini. Ditambahkan agar konsisten
    dan dilindungi try/except (mis. galat OSError saat commit)."""
    conn = current_app.get_db()
    try:
        row = conn.execute("SELECT mahasiswa_id FROM tracer_study WHERE id=?", (tid,)).fetchone()
        conn.execute("DELETE FROM tracer_study WHERE id=?", (tid,))
        conn.commit()
        _db.log(conn, "Hapus Tracer Study", str(row["mahasiswa_id"]) if row else str(tid))
        flash("Data tracer study dihapus.", "ok")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menghapus data tracer study")
    return redirect(url_for("kelulusan.tracer_list"))


@bp.route("/tracer/ekspor")
def tracer_ekspor():
    conn = current_app.get_db()
    rows = conn.execute(
        "SELECT m.nim, m.nama, t.status_saat_ini, t.nama_instansi, t.posisi, t.kesesuaian_bidang,"
        " t.waktu_tunggu, t.studi_lanjut, t.program_lanjut, t.no_hp, t.catatan "
        "FROM tracer_study t JOIN mahasiswa m ON m.id=t.mahasiswa_id ORDER BY m.nama"
    ).fetchall()
    headers = [
        "NIM",
        "Nama",
        "Status Saat Ini",
        "Instansi",
        "Posisi",
        "Kesesuaian Bidang",
        "Waktu Tunggu",
        "Studi Lanjut",
        "Program Lanjut",
        "No HP",
        "Catatan",
    ]
    return export_utils.kirim_excel("Tracer Study Alumni", headers, [tuple(r) for r in rows])
