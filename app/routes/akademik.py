# -*- coding: utf-8 -*-
"""routes/akademik.py — Pengajuan & Review Judul, Penetapan Pembimbing."""

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

bp = Blueprint("akademik", __name__, url_prefix="/akademik")


def _mhs_lookup(conn):
    return conn.execute("SELECT id, nim, nama FROM mahasiswa ORDER BY nama").fetchall()


def _dosen_lookup(conn):
    return conn.execute("SELECT id, nama FROM dosen WHERE aktif=1 ORDER BY nama").fetchall()


def _tahap_list(conn):
    """Daftar nama tahap/gelombang pendaftaran — dinamis dari tahap_pengajuan
    (Audit poin 2, klarifikasi a: jumlah tahap bebas, bukan 2 field
    hardcode nama_tahap_1/2 lagi). Jatuh balik ke pengaturan lama kalau
    prodi belum pernah memakai wizard "Buka Tahun Ajaran"."""
    rows = _db.get_tahap_list(conn)
    if rows:
        return [r["nama"] for r in rows]
    lama = [_db.get_setting(conn, "nama_tahap_1"), _db.get_setting(conn, "nama_tahap_2")]
    return [t for t in lama if t]


# ------------------------------------------------------------ Pengajuan Judul
@bp.route("/pengajuan")
def pengajuan_list():
    conn = current_app.get_db()
    rows = conn.execute(
        "SELECT p.*, m.nim, m.nama FROM pengajuan_judul p "
        "JOIN mahasiswa m ON m.id=p.mahasiswa_id ORDER BY p.id DESC"
    ).fetchall()
    edit_id = request.args.get("edit", type=int)
    edit_row = None
    if edit_id:
        edit_row = conn.execute("SELECT * FROM pengajuan_judul WHERE id=?", (edit_id,)).fetchone()
    return render_template(
        "pengajuan.html",
        rows=rows,
        edit_row=edit_row,
        mhs_list=_mhs_lookup(conn),
        STATUS_REVIEW_LIST=C.STATUS_REVIEW_LIST,
        tahap_list=_tahap_list(conn),
        daftar_periode=_db.get_periode_list(conn),
    )


@bp.route("/pengajuan/simpan", methods=["POST"])
def pengajuan_simpan():
    conn = current_app.get_db()
    f = request.form
    pid = f.get("id", type=int)
    mid = f.get("mahasiswa_id", type=int)
    if not mid:
        flash("Pilih mahasiswa terlebih dahulu.", "error")
        return redirect(url_for("akademik.pengajuan_list"))
    status_final = f.get("status_final", "Diajukan")
    # Audit poin 1 (tindak lanjut) — dropdown "Periode Akademik" terkunci
    # kini jadi sumber kebenaran untuk kolom `semester`, sama seperti pola
    # yang sudah dipakai di Modul SDM/Kegiatan/Mutu (lihat db.cache_periode_
    # gabungan). Kolom TEXT `semester` tetap ada sebagai cache tampilan.
    periode_id = f.get("periode_akademik_id", type=int)
    semester_cache = _db.cache_periode_gabungan(conn, periode_id)
    data = (
        f.get("kode_pengajuan", ""),
        f.get("tgl_pengajuan", ""),
        mid,
        semester_cache,
        f.get("tahap", ""),
        f.get("jml_sks", ""),
        f.get("ipk", ""),
        f.get("judul1", ""),
        f.get("judul2", ""),
        f.get("rev1_ket", ""),
        f.get("rev2_ket", ""),
        f.get("rev3_ket", ""),
        status_final,
        f.get("tgl_review", ""),
        f.get("catatan_reviewer", ""),
        f.get("judul_final", ""),
        periode_id,
    )
    try:
        if pid:
            conn.execute(
                "UPDATE pengajuan_judul SET kode_pengajuan=?,tgl_pengajuan=?,mahasiswa_id=?,"
                "semester=?,tahap=?,jml_sks=?,ipk=?,judul1=?,judul2=?,rev1_ket=?,rev2_ket=?,"
                "rev3_ket=?,status_final=?,tgl_review=?,catatan_reviewer=?,judul_final=?,"
                "periode_akademik_id=? WHERE id=?",
                data + (pid,),
            )
            _db.log(conn, "Update Pengajuan Judul", data[0] or "")
            flash("Pengajuan judul diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO pengajuan_judul(kode_pengajuan,tgl_pengajuan,mahasiswa_id,semester,"
                "tahap,jml_sks,ipk,judul1,judul2,rev1_ket,rev2_ket,rev3_ket,status_final,"
                "tgl_review,catatan_reviewer,judul_final,periode_akademik_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                data,
            )
            _db.log(conn, "Tambah Pengajuan Judul", data[0] or "")
            flash("Pengajuan judul disimpan.", "ok")
        # Audit P0 #1-#3 — status_ta sekarang SATU-SATUNYA dihitung lewat
        # logic.recalculate_status_ta() (menggantikan 2 UPDATE ... WHERE
        # status_ta=lama yang tadinya di sini: satu utk baris baru, satu
        # lagi khusus saat status_final berubah jadi "Disetujui"). Dipanggil
        # SETELAH commit supaya melihat data pengajuan yang baru saja
        # ditulis.
        conn.commit()
        L.recalculate_status_ta(conn, mid, dipicu_oleh="Pengajuan judul disimpan")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan pengajuan judul")
    return redirect(url_for("akademik.pengajuan_list"))


@bp.route("/pengajuan/<int:pid>/hapus", methods=["POST"])
def pengajuan_hapus(pid):
    conn = current_app.get_db()
    row = conn.execute("SELECT mahasiswa_id FROM pengajuan_judul WHERE id=?", (pid,)).fetchone()
    conn.execute("DELETE FROM pengajuan_judul WHERE id=?", (pid,))
    conn.commit()
    if row:
        # Audit P0 #1-#3 — sebelumnya TIDAK disinkronkan sama sekali di
        # sini: menghapus satu-satunya pengajuan judul seorang mahasiswa
        # tidak mengubah status_ta-nya balik ke "Belum Mengajukan Judul".
        L.recalculate_status_ta(conn, row["mahasiswa_id"], dipicu_oleh="Pengajuan judul dihapus")
    flash("Pengajuan judul dihapus.", "ok")
    return redirect(url_for("akademik.pengajuan_list"))


# ------------------------------------------------------- Penetapan Pembimbing
@bp.route("/penetapan")
def penetapan_list():
    conn = current_app.get_db()
    rows = conn.execute(
        "SELECT pp.*, m.nim, m.nama, d1.nama AS p1, d2.nama AS p2 "
        "FROM penetapan_pembimbing pp JOIN mahasiswa m ON m.id=pp.mahasiswa_id "
        "LEFT JOIN dosen d1 ON d1.id=pp.pembimbing1_id "
        "LEFT JOIN dosen d2 ON d2.id=pp.pembimbing2_id ORDER BY m.nama"
    ).fetchall()
    edit_id = request.args.get("edit", type=int)
    edit_row = None
    if edit_id:
        edit_row = conn.execute(
            "SELECT * FROM penetapan_pembimbing WHERE id=?", (edit_id,)
        ).fetchone()
    return render_template(
        "penetapan.html",
        rows=rows,
        edit_row=edit_row,
        mhs_list=_mhs_lookup(conn),
        dosen_list=_dosen_lookup(conn),
        tahap_list=_tahap_list(conn),
        daftar_periode=_db.get_periode_list(conn),
    )


_PENETAPAN_FIELDS = [
    "semester",
    "tahap",
    "judul_final",
    "pembimbing1_id",
    "pembimbing2_id",
    "tgl_penetapan",
    "no_sk",
    "pembahas1_id",
    "pembahas2_id",
    "pembahas3_id",
    "ketua_sidang_id",
    "penguji1_id",
    "penguji2_id",
    "penguji3_id",
    "penguji4_id",
    "link_sk",
]
_PENETAPAN_ID_FIELDS = {
    "pembimbing1_id",
    "pembimbing2_id",
    "pembahas1_id",
    "pembahas2_id",
    "pembahas3_id",
    "ketua_sidang_id",
    "penguji1_id",
    "penguji2_id",
    "penguji3_id",
    "penguji4_id",
}


@bp.route("/penetapan/simpan", methods=["POST"])
def penetapan_simpan():
    conn = current_app.get_db()
    f = request.form
    pid = f.get("id", type=int)
    mid = f.get("mahasiswa_id", type=int)
    if not mid:
        flash("Pilih mahasiswa terlebih dahulu.", "error")
        return redirect(url_for("akademik.penetapan_list"))
    # Audit poin 1 (tindak lanjut) — sama seperti pengajuan_simpan() di atas:
    # dropdown "Periode Akademik" terkunci jadi sumber kebenaran, kolom
    # `semester` TEXT jadi cache turunan otomatis.
    periode_id = f.get("periode_akademik_id", type=int)
    semester_cache = _db.cache_periode_gabungan(conn, periode_id)
    values = []
    for k in _PENETAPAN_FIELDS:
        if k == "semester":
            values.append(semester_cache)
            continue
        v = f.get(k, "")
        if k in _PENETAPAN_ID_FIELDS:
            values.append(int(v) if v else None)
        else:
            values.append(v)
    data = tuple([mid] + values + [periode_id])
    try:
        if pid:
            conn.execute(
                "UPDATE penetapan_pembimbing SET mahasiswa_id=?,semester=?,tahap=?,judul_final=?,"
                "pembimbing1_id=?,pembimbing2_id=?,tgl_penetapan=?,no_sk=?,pembahas1_id=?,"
                "pembahas2_id=?,pembahas3_id=?,ketua_sidang_id=?,penguji1_id=?,penguji2_id=?,"
                "penguji3_id=?,penguji4_id=?,link_sk=?,periode_akademik_id=? WHERE id=?",
                data + (pid,),
            )
            _db.log(conn, "Update Penetapan Pembimbing", str(mid))
            flash("Penetapan pembimbing diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO penetapan_pembimbing(mahasiswa_id,semester,tahap,judul_final,"
                "pembimbing1_id,pembimbing2_id,tgl_penetapan,no_sk,pembahas1_id,pembahas2_id,"
                "pembahas3_id,ketua_sidang_id,penguji1_id,penguji2_id,penguji3_id,penguji4_id,"
                "link_sk,periode_akademik_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                data,
            )
            _db.log(conn, "Tambah Penetapan Pembimbing", str(mid))
            flash("SK Penetapan pembimbing disimpan.", "ok")
        # Audit P0 #1-#3 — sebelumnya SK Pembimbing terbit tanpa PERNAH
        # menyentuh status_ta sama sekali: mahasiswa bisa sudah punya SK
        # Pembimbing tapi status_ta-nya masih "Mengajukan Judul" selamanya
        # kalau operator lupa mengubahnya manual. recalculate_status_ta()
        # menaikkan ke "Proses Bimbingan" begitu SK ini tersimpan.
        conn.commit()
        L.recalculate_status_ta(conn, mid, dipicu_oleh="SK Penetapan pembimbing disimpan")
    except Exception as e:
        EH.flash_gagal_simpan(
            e,
            "Gagal menyimpan penetapan pembimbing (mahasiswa ini mungkin sudah punya SK Pembimbing)",
        )
    return redirect(url_for("akademik.penetapan_list"))


@bp.route("/penetapan/<int:pid>/hapus", methods=["POST"])
def penetapan_hapus(pid):
    conn = current_app.get_db()
    row = conn.execute(
        "SELECT mahasiswa_id FROM penetapan_pembimbing WHERE id=?", (pid,)
    ).fetchone()
    if not row:
        flash("Data SK Penetapan pembimbing tidak ditemukan.", "error")
        return redirect(url_for("akademik.penetapan_list"))

    # Audit Phase 1-2 (re-check) — sebelum perbaikan ini, SK Pembimbing bisa
    # dihapus kapan pun tanpa syarat, bahkan setelah mahasiswanya SUDAH
    # menjalani sidang (LULUS/TIDAK LULUS/TUNDA). recalculate_status_ta()
    # tetap aman secara STATUS (prioritas bukti sidang > SK pembimbing, jadi
    # status_ta tidak salah mundur), TAPI menghapus SK di titik ini
    # menghilangkan jejak arsip resmi (siapa pembimbing 1 & 2) untuk
    # mahasiswa yang kelulusannya sudah final -- data itu biasanya juga
    # dibutuhkan utk berkas akreditasi/audit. Guard ini mengikuti pola yang
    # sama dgn sidang_hapus(): kalau sidang sudah pernah dilaksanakan utk
    # mahasiswa ini, arahkan ke Ubah (bukan Hapus) supaya arsipnya tetap ada.
    sudah_sidang = conn.execute(
        "SELECT 1 FROM sidang WHERE mahasiswa_id=? AND status_kelulusan IS NOT NULL LIMIT 1",
        (row["mahasiswa_id"],),
    ).fetchone()
    if sudah_sidang:
        flash(
            "SK Penetapan pembimbing ini tidak bisa dihapus — mahasiswa sudah menjalani sidang. "
            "Kalau ada kesalahan input (mis. nama pembimbing), gunakan tombol Ubah, jangan Hapus, "
            "supaya arsip SK-nya tetap lengkap.",
            "error",
        )
        return redirect(url_for("akademik.penetapan_list"))

    conn.execute("DELETE FROM penetapan_pembimbing WHERE id=?", (pid,))
    conn.commit()
    # Audit P0 #1-#3 — kalau SK Pembimbing dihapus (mis. salah input)
    # dan mahasiswa itu belum ada bukti seminar/sidang, status_ta-nya
    # perlu mundur balik ke status pengajuan-judul yang sesuai.
    L.recalculate_status_ta(conn, row["mahasiswa_id"], dipicu_oleh="SK Penetapan pembimbing dihapus")
    flash("SK Penetapan pembimbing dihapus.", "ok")
    return redirect(url_for("akademik.penetapan_list"))
