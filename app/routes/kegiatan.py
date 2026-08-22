# -*- coding: utf-8 -*-
"""routes/kegiatan.py — Modul 6: Kegiatan & Program Kerja Prodi.

Dua tabel yang saling terkait (`program_kerja` 1 -> N `kegiatan_prodi`),
ditampilkan sebagai 1 halaman dengan 2 tab (mirip pola tab Modul SDM),
supaya Kaprodi bisa melihat rencana program kerja tahunan sekaligus
realisasi pelaksanaannya di kegiatan konkret tanpa pindah halaman.

Realisasi program kerja dihitung on-the-fly dari rasio kegiatan berstatus
'Selesai' terhadap total kegiatan yang terhubung ke program tsb — prinsip
yang sama dengan Realisasi Target Kinerja di Modul SDM (tidak disimpan
statis, supaya tidak pernah basi).
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

bp = Blueprint("kegiatan", __name__, url_prefix="/kegiatan")

STATUS_SELESAI = {"Selesai"}


def _hitung_realisasi(conn, program_id):
    rows = conn.execute(
        "SELECT status FROM kegiatan_prodi WHERE program_kerja_id=?", (program_id,)
    ).fetchall()
    total = len(rows)
    selesai = sum(1 for r in rows if r["status"] in STATUS_SELESAI)
    persen = round(100 * selesai / total) if total else 0
    return total, selesai, persen


@bp.route("/")
def index():
    conn = current_app.get_db()
    tab = request.args.get("tab", "proker")
    if tab not in ("proker", "kegiatan"):
        tab = "proker"
    tahun_filter = request.args.get("tahun_akademik", "")

    proker_rows = conn.execute(
        "SELECT * FROM program_kerja"
        + (" WHERE tahun_akademik=?" if tahun_filter else "")
        + " ORDER BY tahun_akademik DESC, bidang, nama_program",
        (tahun_filter,) if tahun_filter else (),
    ).fetchall()
    proker_ringkasan = []
    for p in proker_rows:
        total, selesai, persen = _hitung_realisasi(conn, p["id"])
        proker_ringkasan.append({"row": p, "total": total, "selesai": selesai, "persen": persen})

    kegiatan_rows = conn.execute(
        "SELECT k.*, p.nama_program FROM kegiatan_prodi k "
        "LEFT JOIN program_kerja p ON p.id=k.program_kerja_id "
        "ORDER BY k.tgl_mulai DESC, k.id DESC"
    ).fetchall()

    daftar_proker_dropdown = conn.execute(
        "SELECT id, nama_program, tahun_akademik FROM program_kerja ORDER BY tahun_akademik DESC, nama_program"
    ).fetchall()

    tahun_list = [
        r["tahun_akademik"]
        for r in conn.execute(
            "SELECT DISTINCT tahun_akademik FROM program_kerja WHERE tahun_akademik IS NOT NULL "
            "AND tahun_akademik != '' ORDER BY tahun_akademik DESC"
        ).fetchall()
    ]

    edit_id = request.args.get("edit", type=int)
    edit_proker = edit_kegiatan = None
    if edit_id and tab == "proker":
        edit_proker = conn.execute("SELECT * FROM program_kerja WHERE id=?", (edit_id,)).fetchone()
    elif edit_id and tab == "kegiatan":
        edit_kegiatan = conn.execute(
            "SELECT * FROM kegiatan_prodi WHERE id=?", (edit_id,)
        ).fetchone()

    return render_template(
        "kegiatan.html",
        tab=tab,
        proker_ringkasan=proker_ringkasan,
        kegiatan_rows=kegiatan_rows,
        daftar_proker_dropdown=daftar_proker_dropdown,
        tahun_list=tahun_list,
        tahun_filter=tahun_filter,
        edit_proker=edit_proker,
        edit_kegiatan=edit_kegiatan,
        bidang_list=C.BIDANG_PROKER_LIST,
        status_proker_list=C.STATUS_PROKER_LIST,
        kategori_kegiatan_list=C.KATEGORI_KEGIATAN_LIST,
        status_kegiatan_list=C.STATUS_KEGIATAN_LIST,
        # Audit poin 1 (tindak lanjut) — dropdown Periode Akademik terkunci
        # utk Program Kerja, menggantikan input teks tahun_akademik bebas.
        daftar_periode=_db.get_periode_list(conn),
    )


@bp.route("/proker/simpan", methods=["POST"])
def simpan_proker():
    """Audit Lanjutan (Kegiatan & Program Kerja) — temuan: `bidang` &
    `status` sebelumnya diterima APA ADANYA dari form tanpa dicocokkan ke
    daftar resmi (C.BIDANG_PROKER_LIST / C.STATUS_PROKER_LIST), berbeda
    dari pola validasi yang sudah dipakai di import_generic.py utk kolom
    sejenis. Risikonya rendah selama form HTML memakai <select> yang
    sudah dibatasi, tapi tanpa validasi server-side, POST langsung (mis.
    lewat curl/Postman, atau <select> yang di-tamper di DevTools) bisa
    menaruh nilai bebas ke kolom yang seharusnya berupa kategori tetap —
    merusak konsistensi filter/rekap yang mengandalkan nilai persis dari
    daftar resmi (mis. Rekap Program Kerja di routes/rekap.py mengelompokkan
    per `bidang`). Anggaran rencana juga sekarang ditolak kalau negatif,
    bukan diam-diam disimpan sebagai angka minus."""
    conn = current_app.get_db()
    f = request.form
    rid = f.get("id", type=int)
    nama = f.get("nama_program", "").strip()
    if not nama:
        flash("Nama Program wajib diisi.", "error")
        return redirect(url_for("kegiatan.index", tab="proker"))
    bidang = f.get("bidang", "")
    if bidang not in C.BIDANG_PROKER_LIST:
        flash("Bidang tidak dikenal — pilih dari daftar yang tersedia.", "error")
        return redirect(url_for("kegiatan.index", tab="proker", edit=rid))
    status = f.get("status", "Direncanakan")
    if status not in C.STATUS_PROKER_LIST:
        status = "Direncanakan"
    anggaran_rencana = f.get("anggaran_rencana", type=float) or 0
    if anggaran_rencana < 0:
        flash("Anggaran Rencana tidak boleh bernilai negatif.", "error")
        return redirect(url_for("kegiatan.index", tab="proker", edit=rid))
    # Audit poin 1 (tindak lanjut) — periode_akademik_id dari dropdown
    # terkunci jadi sumber kebenaran; tahun_akademik TEXT diturunkan
    # otomatis dari situ (tetap dipertahankan sbg cache filter/tampilan).
    periode_id = f.get("periode_akademik_id", type=int)
    ta_cache, _sem_cache = _db.cache_periode(conn, periode_id)
    data = (
        periode_id,
        ta_cache,
        bidang,
        nama,
        f.get("indikator_kinerja", "").strip(),
        f.get("target", "").strip(),
        f.get("satuan", "").strip(),
        anggaran_rencana,
        f.get("penanggung_jawab", "").strip(),
        status,
        f.get("catatan", "").strip(),
    )
    try:
        if rid:
            conn.execute(
                "UPDATE program_kerja SET periode_akademik_id=?, tahun_akademik=?, bidang=?, nama_program=?, "
                "indikator_kinerja=?, target=?, satuan=?, anggaran_rencana=?, penanggung_jawab=?, "
                "status=?, catatan=? WHERE id=?",
                (*data, rid),
            )
            flash("Program kerja diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO program_kerja(periode_akademik_id, tahun_akademik, bidang, nama_program, indikator_kinerja, "
                "target, satuan, anggaran_rencana, penanggung_jawab, status, catatan) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                data,
            )
            flash("Program kerja ditambahkan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Program Kerja", nama)
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan")
    return redirect(url_for("kegiatan.index", tab="proker"))


@bp.route("/proker/<int:pid>/hapus", methods=["POST"])
def hapus_proker(pid):
    conn = current_app.get_db()
    conn.execute("DELETE FROM program_kerja WHERE id=?", (pid,))
    conn.commit()
    _db.log(conn, "Hapus Program Kerja", str(pid))
    flash("Program kerja dihapus.", "ok")
    return redirect(url_for("kegiatan.index", tab="proker"))


@bp.route("/pelaksanaan/simpan", methods=["POST"])
def simpan_kegiatan():
    """Audit Lanjutan — validasi server-side utk `kategori`/`status`
    terhadap daftar resmi (lihat catatan lengkap di simpan_proker() di
    atas) + anggaran_realisasi tidak boleh negatif."""
    conn = current_app.get_db()
    f = request.form
    rid = f.get("id", type=int)
    nama = f.get("nama_kegiatan", "").strip()
    if not nama:
        flash("Nama Kegiatan wajib diisi.", "error")
        return redirect(url_for("kegiatan.index", tab="kegiatan"))
    kategori = f.get("kategori", "")
    if kategori not in C.KATEGORI_KEGIATAN_LIST:
        flash("Kategori kegiatan tidak dikenal — pilih dari daftar yang tersedia.", "error")
        return redirect(url_for("kegiatan.index", tab="kegiatan", edit=rid))
    status = f.get("status", "Direncanakan")
    if status not in C.STATUS_KEGIATAN_LIST:
        status = "Direncanakan"
    anggaran_realisasi = f.get("anggaran_realisasi", type=float) or 0
    if anggaran_realisasi < 0:
        flash("Anggaran Realisasi tidak boleh bernilai negatif.", "error")
        return redirect(url_for("kegiatan.index", tab="kegiatan", edit=rid))
    data = (
        f.get("program_kerja_id", type=int) or None,
        nama,
        kategori,
        f.get("tgl_mulai", "").strip(),
        f.get("tgl_selesai", "").strip(),
        f.get("lokasi", "").strip(),
        f.get("penanggung_jawab", "").strip(),
        f.get("jumlah_peserta", "").strip(),
        anggaran_realisasi,
        f.get("sumber_dana", "").strip(),
        status,
        f.get("lokasi_bukti", "").strip(),
        f.get("catatan", "").strip(),
    )
    try:
        if rid:
            conn.execute(
                "UPDATE kegiatan_prodi SET program_kerja_id=?, nama_kegiatan=?, kategori=?, "
                "tgl_mulai=?, tgl_selesai=?, lokasi=?, penanggung_jawab=?, jumlah_peserta=?, "
                "anggaran_realisasi=?, sumber_dana=?, status=?, lokasi_bukti=?, catatan=? WHERE id=?",
                (*data, rid),
            )
            flash("Kegiatan diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO kegiatan_prodi(program_kerja_id, nama_kegiatan, kategori, tgl_mulai, "
                "tgl_selesai, lokasi, penanggung_jawab, jumlah_peserta, anggaran_realisasi, "
                "sumber_dana, status, lokasi_bukti, catatan) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                data,
            )
            flash("Kegiatan ditambahkan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Kegiatan Prodi", nama)
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan")
    return redirect(url_for("kegiatan.index", tab="kegiatan"))


@bp.route("/pelaksanaan/<int:kid>/hapus", methods=["POST"])
def hapus_kegiatan(kid):
    conn = current_app.get_db()
    conn.execute("DELETE FROM kegiatan_prodi WHERE id=?", (kid,))
    conn.commit()
    _db.log(conn, "Hapus Kegiatan Prodi", str(kid))
    flash("Kegiatan dihapus.", "ok")
    return redirect(url_for("kegiatan.index", tab="kegiatan"))
