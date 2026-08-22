# -*- coding: utf-8 -*-
"""routes/semester_pendek.py — Modul 13: Semester Pendek (SP).

Struktur tab diadaptasi dari susunan menu ShortSemester.tsx SITIPRO
(Dashboard/Konfigurasi/Kelas/Pendaftaran/Pelaksanaan/Penilaian/Repository),
tapi digabung jadi 5 tab dengan logika Flask/SQLite sungguhan (pola sama
dengan Modul 6/9/10/11 — tab "dashboard" & "repository" SITIPRO dilebur
jadi stat-row di tab pertama + export CSV, bukan tab kosong):

  - periode    : konfigurasi periode SP (timeline, aturan akademik, biaya).
  - kelas      : penawaran kelas SP per periode, mata kuliah dari kurikulum
                 aktif — status kapasitas (Dibuka/Kurang Kuota/Penuh)
                 dihitung on-the-fly, bukan dipilih manual.
  - peserta    : pendaftaran & approval mahasiswa ke kelas SP (syarat utama
                 SP: mengulang mata kuliah bernilai < C, dicatat di
                 alasan_mengulang/nilai_sebelumnya, divalidasi manual oleh
                 Kaprodi — bukan validasi otomatis, supaya tetap ada
                 penilaian profesional per kasus).
  - pertemuan  : log pertemuan + presensi per mahasiswa (dasar syarat
                 kehadiran wajib 80%, logic.sp_persentase_kehadiran()).
  - nilai      : input Tugas/UTS/UAS -> nilai akhir & huruf otomatis
                 (logic.sp_hitung_nilai_akhir()), + rekap/export CSV per
                 kelas sebagai pengganti tab "Repository" SITIPRO.
"""

import csv
import io

from flask import (
    Blueprint,
    Response,
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

bp = Blueprint("sp", __name__, url_prefix="/semester-pendek")

_TABS = ("periode", "kelas", "peserta", "pertemuan", "nilai")


def _mk_kurikulum_aktif(conn):
    kur = _kurikulum_aktif(conn)
    if not kur:
        return []
    return conn.execute(
        "SELECT * FROM mata_kuliah WHERE kurikulum_id=? ORDER BY semester, kode",
        (kur["id"],),
    ).fetchall()


def _daftar_periode(conn):
    return conn.execute("SELECT * FROM sp_periode ORDER BY id DESC").fetchall()


def _periode_terpilih(conn, periode_rows):
    pid = request.args.get("periode", type=int)
    if not pid and periode_rows:
        aktif = [p for p in periode_rows if p["status"] in ("Pendaftaran Dibuka", "Berjalan")]
        pid = (aktif[0] if aktif else periode_rows[0])["id"]
    return conn.execute("SELECT * FROM sp_periode WHERE id=?", (pid,)).fetchone() if pid else None


def _daftar_kelas(conn, periode_id):
    return (
        conn.execute(
            "SELECT k.*, mk.kode AS mk_kode, mk.nama AS mk_nama, mk.sks AS mk_sks, "
            "d.nama AS dosen_nama, r.nama AS ruangan_nama FROM sp_kelas k "
            "JOIN mata_kuliah mk ON mk.id = k.mata_kuliah_id "
            "LEFT JOIN dosen d ON d.id = k.dosen_id "
            "LEFT JOIN ruangan r ON r.id = k.ruangan_id "
            "WHERE k.periode_id=? ORDER BY mk.semester, mk.kode",
            (periode_id,),
        ).fetchall()
        if periode_id
        else []
    )


@bp.route("/")
def index():
    conn = current_app.get_db()
    tab = request.args.get("tab", "periode")
    if tab not in _TABS:
        tab = "periode"

    periode_rows = _daftar_periode(conn)
    periode_terpilih = _periode_terpilih(conn, periode_rows)

    ctx = {
        "tab": tab,
        "periode_rows": periode_rows,
        "periode_terpilih": periode_terpilih,
        "status_sp_periode_list": C.STATUS_SP_PERIODE_LIST,
    }

    if tab == "periode":
        edit_id = request.args.get("edit", type=int)
        ctx["edit_periode"] = (
            conn.execute("SELECT * FROM sp_periode WHERE id=?", (edit_id,)).fetchone()
            if edit_id
            else None
        )
        # Audit poin 1 (tindak lanjut) — dropdown "Periode Akademik" (Tahun
        # Ajaran) terkunci, TIDAK SAMA dengan `periode_rows` di atas (yang
        # berisi periode Semester Pendek sendiri). Nama variabel sengaja
        # dibedakan (`daftar_periode_akademik`) supaya tidak tertukar di
        # template. Pola sama dengan Modul SDM/Kegiatan/Mutu/Jadwal.
        ctx["daftar_periode_akademik"] = _db.get_periode_list(conn)
        ringkasan = []
        for p in periode_rows:
            kelas_list = _daftar_kelas(conn, p["id"])
            total_peserta = sum(L.sp_jumlah_disetujui(conn, k["id"]) for k in kelas_list)
            ringkasan.append(
                {"periode": p, "jumlah_kelas": len(kelas_list), "total_peserta": total_peserta}
            )
        ctx["ringkasan"] = ringkasan

    elif tab == "kelas":
        kelas_list = _daftar_kelas(conn, periode_terpilih["id"] if periode_terpilih else None)
        ctx["kelas_rows"] = [dict(r, kapasitas=L.sp_status_kelas(conn, r)) for r in kelas_list]
        ctx["mk_list"] = _mk_kurikulum_aktif(conn)
        ctx["dosen_list"] = conn.execute(
            "SELECT id, nama FROM dosen WHERE aktif=1 ORDER BY nama"
        ).fetchall()
        ctx["ruangan_list"] = conn.execute("SELECT id, nama FROM ruangan ORDER BY nama").fetchall()
        ctx["hari_list"] = C.HARI_LIST
        edit_id = request.args.get("edit", type=int)
        ctx["edit_kelas"] = (
            conn.execute("SELECT * FROM sp_kelas WHERE id=?", (edit_id,)).fetchone()
            if edit_id
            else None
        )

    elif tab == "peserta":
        kelas_list = _daftar_kelas(conn, periode_terpilih["id"] if periode_terpilih else None)
        ctx["kelas_list"] = kelas_list
        kid = request.args.get("kelas", type=int)
        if not kid and kelas_list:
            kid = kelas_list[0]["id"]
        kelas_terpilih = (
            conn.execute(
                "SELECT k.*, mk.kode AS mk_kode, mk.nama AS mk_nama FROM sp_kelas k "
                "JOIN mata_kuliah mk ON mk.id = k.mata_kuliah_id WHERE k.id=?",
                (kid,),
            ).fetchone()
            if kid
            else None
        )
        ctx["kelas_terpilih"] = kelas_terpilih
        if kelas_terpilih:
            ctx["peserta_rows"] = conn.execute(
                "SELECT sp.*, m.nim, m.nama AS mhs_nama FROM sp_peserta sp "
                "JOIN mahasiswa m ON m.id = sp.mahasiswa_id WHERE sp.sp_kelas_id=? ORDER BY m.nama",
                (kid,),
            ).fetchall()
            ctx["mahasiswa_belum_daftar"] = conn.execute(
                "SELECT id, nim, nama FROM mahasiswa WHERE status='Aktif' AND id NOT IN "
                "(SELECT mahasiswa_id FROM sp_peserta WHERE sp_kelas_id=?) ORDER BY nama",
                (kid,),
            ).fetchall()
        else:
            ctx["peserta_rows"] = []
            ctx["mahasiswa_belum_daftar"] = []
        ctx["status_approval_list"] = C.STATUS_APPROVAL_SP_LIST

    elif tab == "pertemuan":
        kelas_list = _daftar_kelas(conn, periode_terpilih["id"] if periode_terpilih else None)
        ctx["kelas_list"] = kelas_list
        kid = request.args.get("kelas", type=int)
        if not kid and kelas_list:
            kid = kelas_list[0]["id"]
        kelas_terpilih = (
            conn.execute(
                "SELECT k.*, mk.kode AS mk_kode, mk.nama AS mk_nama FROM sp_kelas k "
                "JOIN mata_kuliah mk ON mk.id = k.mata_kuliah_id WHERE k.id=?",
                (kid,),
            ).fetchone()
            if kid
            else None
        )
        ctx["kelas_terpilih"] = kelas_terpilih
        jml_rencana = periode_terpilih["jumlah_pertemuan_rencana"] if periode_terpilih else 8
        if kelas_terpilih:
            ctx["pertemuan_rows"] = conn.execute(
                "SELECT * FROM sp_pertemuan WHERE sp_kelas_id=? ORDER BY pertemuan_ke", (kid,)
            ).fetchall()
            ctx["realisasi"] = L.sp_realisasi_pertemuan(conn, kid, jml_rencana)
            n_next = conn.execute(
                "SELECT COALESCE(MAX(pertemuan_ke),0)+1 n FROM sp_pertemuan WHERE sp_kelas_id=?",
                (kid,),
            ).fetchone()["n"]
            ctx["pertemuan_berikutnya"] = n_next
            ctx["peserta_rows"] = conn.execute(
                "SELECT sp.*, m.nim, m.nama AS mhs_nama FROM sp_peserta sp "
                "JOIN mahasiswa m ON m.id = sp.mahasiswa_id "
                "WHERE sp.sp_kelas_id=? AND sp.status_approval='Disetujui' ORDER BY m.nama",
                (kid,),
            ).fetchall()
            pid_pertemuan = request.args.get("pertemuan", type=int)
            if not pid_pertemuan and ctx["pertemuan_rows"]:
                pid_pertemuan = ctx["pertemuan_rows"][-1]["id"]
            ctx["pertemuan_terpilih"] = (
                conn.execute("SELECT * FROM sp_pertemuan WHERE id=?", (pid_pertemuan,)).fetchone()
                if pid_pertemuan
                else None
            )
            if ctx["pertemuan_terpilih"]:
                hadir_map = {
                    r["sp_peserta_id"]: r["hadir"]
                    for r in conn.execute(
                        "SELECT sp_peserta_id, hadir FROM sp_presensi WHERE sp_pertemuan_id=?",
                        (ctx["pertemuan_terpilih"]["id"],),
                    ).fetchall()
                }
                ctx["hadir_map"] = hadir_map
            else:
                ctx["hadir_map"] = {}
        else:
            ctx["pertemuan_rows"] = []
            ctx["realisasi"] = None
            ctx["pertemuan_berikutnya"] = 1
            ctx["peserta_rows"] = []
            ctx["pertemuan_terpilih"] = None
            ctx["hadir_map"] = {}
        ctx["status_pertemuan_sp_list"] = C.STATUS_PERTEMUAN_SP_LIST

    elif tab == "nilai":
        kelas_list = _daftar_kelas(conn, periode_terpilih["id"] if periode_terpilih else None)
        ctx["kelas_list"] = kelas_list
        kid = request.args.get("kelas", type=int)
        if not kid and kelas_list:
            kid = kelas_list[0]["id"]
        kelas_terpilih = (
            conn.execute(
                "SELECT k.*, mk.kode AS mk_kode, mk.nama AS mk_nama FROM sp_kelas k "
                "JOIN mata_kuliah mk ON mk.id = k.mata_kuliah_id WHERE k.id=?",
                (kid,),
            ).fetchone()
            if kid
            else None
        )
        ctx["kelas_terpilih"] = kelas_terpilih
        if kelas_terpilih:
            rows = conn.execute(
                "SELECT sp.*, m.nim, m.nama AS mhs_nama FROM sp_peserta sp "
                "JOIN mahasiswa m ON m.id = sp.mahasiswa_id "
                "WHERE sp.sp_kelas_id=? AND sp.status_approval='Disetujui' ORDER BY m.nama",
                (kid,),
            ).fetchall()
            ctx["peserta_rows"] = [
                dict(r, kehadiran=L.sp_persentase_kehadiran(conn, r["id"])) for r in rows
            ]
        else:
            ctx["peserta_rows"] = []
        ctx["ambang_kehadiran"] = C.SP_AMBANG_KEHADIRAN
        pid_peserta = request.args.get("peserta", type=int)
        peserta_terpilih = None
        if ctx["peserta_rows"]:
            if pid_peserta:
                peserta_terpilih = next(
                    (p for p in ctx["peserta_rows"] if p["id"] == pid_peserta), None
                )
            if not peserta_terpilih:
                peserta_terpilih = ctx["peserta_rows"][0]
        ctx["peserta_terpilih"] = peserta_terpilih

    return render_template("semester_pendek.html", **ctx)


@bp.route("/periode/simpan", methods=["POST"])
def simpan_periode():
    conn = current_app.get_db()
    f = request.form
    pid = f.get("id", type=int)
    nama = f.get("nama", "").strip()
    if not nama:
        flash("Nama periode wajib diisi.", "error")
        return redirect(url_for("sp.index", tab="periode"))

    status = f.get("status", "Draft")
    if status not in C.STATUS_SP_PERIODE_LIST:
        status = "Draft"

    # Audit poin 1 (tindak lanjut) — dropdown "Periode Akademik (Tahun
    # Ajaran)" terkunci kini jadi sumber kebenaran untuk cache
    # `tahun_akademik` (kolom TEXT lama dipertahankan sebagai cache
    # tampilan). Periode SP boleh tetap dibuat tanpa memilih periode
    # akademik (mis. sebelum wizard "Buka Tahun Ajaran" dipakai) — cache
    # akan kosong, sama seperti sebelumnya.
    periode_akademik_id = f.get("periode_akademik_id", type=int)
    tahun_akademik_cache, _sem = _db.cache_periode(conn, periode_akademik_id)

    vals = (
        nama,
        tahun_akademik_cache,
        f.get("tgl_mulai_daftar", "").strip(),
        f.get("tgl_selesai_daftar", "").strip(),
        f.get("tgl_mulai_kuliah", "").strip(),
        f.get("tgl_selesai_kuliah", "").strip(),
        f.get("maks_sks", type=int) or 9,
        f.get("kuota_min_default", type=int) or 15,
        f.get("biaya_per_sks", type=float) or 0,
        1 if f.get("hanya_mengulang") else 0,
        f.get("jumlah_pertemuan_rencana", type=int) or 8,
        status,
        f.get("keterangan", "").strip(),
        periode_akademik_id,
    )
    try:
        if pid:
            conn.execute(
                "UPDATE sp_periode SET nama=?, tahun_akademik=?, tgl_mulai_daftar=?, "
                "tgl_selesai_daftar=?, tgl_mulai_kuliah=?, tgl_selesai_kuliah=?, maks_sks=?, "
                "kuota_min_default=?, biaya_per_sks=?, hanya_mengulang=?, "
                "jumlah_pertemuan_rencana=?, status=?, keterangan=?, periode_akademik_id=? WHERE id=?",
                vals + (pid,),
            )
            flash("Periode Semester Pendek diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO sp_periode(nama, tahun_akademik, tgl_mulai_daftar, "
                "tgl_selesai_daftar, tgl_mulai_kuliah, tgl_selesai_kuliah, maks_sks, "
                "kuota_min_default, biaya_per_sks, hanya_mengulang, jumlah_pertemuan_rencana, "
                "status, keterangan, periode_akademik_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                vals,
            )
            flash("Periode Semester Pendek ditambahkan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Periode SP", nama)
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan periode SP")
    return redirect(url_for("sp.index", tab="periode"))


@bp.route("/periode/<int:pid>/hapus", methods=["POST"])
def hapus_periode(pid):
    conn = current_app.get_db()
    conn.execute("DELETE FROM sp_periode WHERE id=?", (pid,))
    conn.commit()
    _db.log(conn, "Hapus Periode SP", str(pid))
    flash("Periode SP dihapus (kelas, peserta & pertemuan terkait ikut terhapus).", "ok")
    return redirect(url_for("sp.index", tab="periode"))


@bp.route("/kelas/simpan", methods=["POST"])
def simpan_kelas():
    conn = current_app.get_db()
    f = request.form
    kid = f.get("id", type=int)
    periode_id = f.get("periode_id", type=int)
    mata_kuliah_id = f.get("mata_kuliah_id", type=int)

    if not periode_id or not mata_kuliah_id:
        flash("Periode dan mata kuliah wajib dipilih.", "error")
        return redirect(url_for("sp.index", tab="kelas", periode=periode_id))

    vals = (
        periode_id,
        mata_kuliah_id,
        f.get("dosen_id", type=int),
        f.get("ruangan_id", type=int),
        f.get("kuota_min", type=int),
        f.get("kuota_maks", type=int) or 40,
        f.get("hari", "").strip(),
        f.get("jam_mulai", "").strip(),
        f.get("jam_selesai", "").strip(),
        f.get("keterangan", "").strip(),
    )
    try:
        if kid:
            conn.execute(
                "UPDATE sp_kelas SET periode_id=?, mata_kuliah_id=?, dosen_id=?, ruangan_id=?, "
                "kuota_min=?, kuota_maks=?, hari=?, jam_mulai=?, jam_selesai=?, keterangan=? "
                "WHERE id=?",
                vals + (kid,),
            )
            flash("Kelas SP diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO sp_kelas(periode_id, mata_kuliah_id, dosen_id, ruangan_id, "
                "kuota_min, kuota_maks, hari, jam_mulai, jam_selesai, keterangan) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                vals,
            )
            flash("Kelas SP ditawarkan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Kelas SP", f"periode #{periode_id} mk #{mata_kuliah_id}")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan kelas SP")
    return redirect(url_for("sp.index", tab="kelas", periode=periode_id))


@bp.route("/kelas/<int:kid>/hapus", methods=["POST"])
def hapus_kelas(kid):
    conn = current_app.get_db()
    row = conn.execute("SELECT periode_id FROM sp_kelas WHERE id=?", (kid,)).fetchone()
    conn.execute("DELETE FROM sp_kelas WHERE id=?", (kid,))
    conn.commit()
    _db.log(conn, "Hapus Kelas SP", str(kid))
    flash("Kelas SP dihapus (peserta & pertemuan terkait ikut terhapus).", "ok")
    return redirect(url_for("sp.index", tab="kelas", periode=row["periode_id"] if row else None))


@bp.route("/peserta/tambah", methods=["POST"])
def tambah_peserta():
    conn = current_app.get_db()
    f = request.form
    sp_kelas_id = f.get("sp_kelas_id", type=int)
    mahasiswa_id = f.get("mahasiswa_id", type=int)
    if not sp_kelas_id or not mahasiswa_id:
        flash("Pilih mahasiswa terlebih dahulu.", "error")
        return redirect(url_for("sp.index", tab="peserta", kelas=sp_kelas_id))
    try:
        conn.execute(
            "INSERT INTO sp_peserta(sp_kelas_id, mahasiswa_id, alasan_mengulang, "
            "nilai_sebelumnya) VALUES(?,?,?,?)",
            (
                sp_kelas_id,
                mahasiswa_id,
                f.get("alasan_mengulang", "").strip(),
                f.get("nilai_sebelumnya", "").strip(),
            ),
        )
        conn.commit()
        _db.log(conn, "Daftar Peserta SP", f"mhs #{mahasiswa_id} -> kelas SP #{sp_kelas_id}")
        flash("Mahasiswa didaftarkan ke kelas SP (menunggu approval).", "ok")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal mendaftarkan peserta (mungkin sudah terdaftar)")
    return redirect(url_for("sp.index", tab="peserta", kelas=sp_kelas_id))


@bp.route("/peserta/<int:pid>/approval", methods=["POST"])
def approval_peserta(pid):
    conn = current_app.get_db()
    f = request.form
    status = f.get("status_approval", "Menunggu")
    if status not in C.STATUS_APPROVAL_SP_LIST:
        status = "Menunggu"
    row = conn.execute("SELECT * FROM sp_peserta WHERE id=?", (pid,)).fetchone()
    if not row:
        flash("Data pendaftaran peserta SP tidak ditemukan.", "error")
        return redirect(url_for("sp.index", tab="peserta"))

    # Audit poin (kuota SP) — sp_status_kelas() sebelumnya cuma label
    # tampilan, tidak pernah jadi gerbang validasi di sini, sehingga
    # operator bisa menyetujui peserta tanpa batas meski kelas sudah
    # "Penuh". Ditegakkan sekarang dgn pola konfirmasi yang sama seperti
    # konfirmasi_bentrok/konfirmasi_transisi di modul lain: hanya
    # diperiksa saat transisi MENUJU 'Disetujui' (bukan saat menolak/
    # membatalkan approval, yang justru membebaskan kuota).
    if status == "Disetujui" and row["status_approval"] != "Disetujui":
        kelas = conn.execute("SELECT * FROM sp_kelas WHERE id=?", (row["sp_kelas_id"],)).fetchone()
        if kelas:
            kapasitas = L.sp_status_kelas(conn, kelas)
            if kapasitas["label"] == "Penuh" and not f.get("konfirmasi_kuota"):
                peringatan = [
                    f"Kelas ini sudah Penuh: {kapasitas['disetujui']}/{kapasitas['kuota_maks']} "
                    "peserta berstatus 'Disetujui'. Menyetujui peserta ini akan melebihi kuota_maks."
                ]
                return render_template(
                    "_kuota_confirm.html",
                    peringatan=peringatan,
                    action=url_for("sp.approval_peserta", pid=pid),
                    form=f,
                )

    conn.execute("UPDATE sp_peserta SET status_approval=? WHERE id=?", (status, pid))
    conn.commit()
    _db.log(conn, "Approval Peserta SP", f"#{pid} -> {status}")
    flash(f"Status pendaftaran diubah menjadi '{status}'.", "ok")
    return redirect(url_for("sp.index", tab="peserta", kelas=row["sp_kelas_id"]))


@bp.route("/peserta/<int:pid>/hapus", methods=["POST"])
def hapus_peserta(pid):
    conn = current_app.get_db()
    row = conn.execute("SELECT sp_kelas_id FROM sp_peserta WHERE id=?", (pid,)).fetchone()
    conn.execute("DELETE FROM sp_peserta WHERE id=?", (pid,))
    conn.commit()
    _db.log(conn, "Hapus Peserta SP", str(pid))
    flash("Pendaftaran peserta SP dihapus.", "ok")
    return redirect(url_for("sp.index", tab="peserta", kelas=row["sp_kelas_id"] if row else None))


@bp.route("/pertemuan/simpan", methods=["POST"])
def simpan_pertemuan():
    conn = current_app.get_db()
    f = request.form
    sp_kelas_id = f.get("sp_kelas_id", type=int)
    pertemuan_ke = f.get("pertemuan_ke", type=int)
    if not sp_kelas_id or not pertemuan_ke:
        flash("Kelas dan nomor pertemuan wajib diisi.", "error")
        return redirect(url_for("sp.index", tab="pertemuan", kelas=sp_kelas_id))

    status = f.get("status", "Terlaksana")
    if status not in C.STATUS_PERTEMUAN_SP_LIST:
        status = "Terlaksana"
    try:
        conn.execute(
            "INSERT INTO sp_pertemuan(sp_kelas_id, pertemuan_ke, tanggal, materi, status, catatan) "
            "VALUES(?,?,?,?,?,?)",
            (
                sp_kelas_id,
                pertemuan_ke,
                f.get("tanggal", "").strip(),
                f.get("materi", "").strip(),
                status,
                f.get("catatan", "").strip(),
            ),
        )
        conn.commit()
        _db.log(conn, "Catat Pertemuan SP", f"kelas #{sp_kelas_id} pertemuan {pertemuan_ke}")
        flash(f"Pertemuan ke-{pertemuan_ke} dicatat.", "ok")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal mencatat pertemuan. Pastikan nomor pertemuan belum dipakai")
    return redirect(url_for("sp.index", tab="pertemuan", kelas=sp_kelas_id))


@bp.route("/pertemuan/<int:mid>/hapus", methods=["POST"])
def hapus_pertemuan(mid):
    conn = current_app.get_db()
    row = conn.execute("SELECT sp_kelas_id FROM sp_pertemuan WHERE id=?", (mid,)).fetchone()
    conn.execute("DELETE FROM sp_pertemuan WHERE id=?", (mid,))
    conn.commit()
    _db.log(conn, "Hapus Pertemuan SP", str(mid))
    flash("Catatan pertemuan dihapus.", "ok")
    return redirect(url_for("sp.index", tab="pertemuan", kelas=row["sp_kelas_id"] if row else None))


@bp.route("/presensi/simpan", methods=["POST"])
def simpan_presensi():
    conn = current_app.get_db()
    f = request.form
    sp_pertemuan_id = f.get("sp_pertemuan_id", type=int)
    sp_kelas_id = f.get("sp_kelas_id", type=int)
    if not sp_pertemuan_id:
        flash("Pilih pertemuan terlebih dahulu.", "error")
        return redirect(url_for("sp.index", tab="pertemuan", kelas=sp_kelas_id))

    peserta_rows = conn.execute(
        "SELECT id FROM sp_peserta WHERE sp_kelas_id=? AND status_approval='Disetujui'",
        (sp_kelas_id,),
    ).fetchall()
    for p in peserta_rows:
        hadir = 1 if f.get(f"hadir_{p['id']}") else 0
        conn.execute(
            "INSERT INTO sp_presensi(sp_pertemuan_id, sp_peserta_id, hadir) VALUES(?,?,?) "
            "ON CONFLICT(sp_pertemuan_id, sp_peserta_id) DO UPDATE SET hadir=excluded.hadir",
            (sp_pertemuan_id, p["id"], hadir),
        )
    conn.commit()
    _db.log(conn, "Simpan Presensi SP", f"pertemuan #{sp_pertemuan_id}")
    flash("Presensi pertemuan disimpan.", "ok")
    return redirect(
        url_for("sp.index", tab="pertemuan", kelas=sp_kelas_id, pertemuan=sp_pertemuan_id)
    )


@bp.route("/nilai/simpan", methods=["POST"])
def simpan_nilai():
    conn = current_app.get_db()
    f = request.form
    pid = f.get("id", type=int)
    sp_kelas_id = f.get("sp_kelas_id", type=int)
    if not pid:
        flash("Peserta tidak ditemukan.", "error")
        return redirect(url_for("sp.index", tab="nilai", kelas=sp_kelas_id))

    tugas = f.get("tugas", type=float)
    uts = f.get("uts", type=float)
    uas = f.get("uas", type=float)
    nilai_akhir, nilai_huruf = L.sp_hitung_nilai_akhir(tugas, uts, uas)

    conn.execute(
        "UPDATE sp_peserta SET tugas=?, uts=?, uas=?, nilai_akhir=?, nilai_huruf=?, catatan=? "
        "WHERE id=?",
        (tugas, uts, uas, nilai_akhir, nilai_huruf, f.get("catatan", "").strip(), pid),
    )
    conn.commit()
    _db.log(conn, "Simpan Nilai SP", f"peserta #{pid}")
    flash("Nilai Semester Pendek disimpan.", "ok")
    return redirect(url_for("sp.index", tab="nilai", kelas=sp_kelas_id))


@bp.route("/nilai/export")
def export_nilai():
    """Rekap nilai + kehadiran 1 kelas SP dalam CSV — pengganti tab
    'Repository' SITIPRO (export rekap nilai akhir), tanpa dependensi baru
    (pakai modul csv bawaan Python, pola sama dengan file/data export lain
    di SIMPRODI yang selalu offline)."""
    conn = current_app.get_db()
    kid = request.args.get("kelas", type=int)
    kelas = conn.execute(
        "SELECT k.*, mk.kode AS mk_kode, mk.nama AS mk_nama FROM sp_kelas k "
        "JOIN mata_kuliah mk ON mk.id = k.mata_kuliah_id WHERE k.id=?",
        (kid,),
    ).fetchone()
    if not kelas:
        flash("Kelas SP tidak ditemukan.", "error")
        return redirect(url_for("sp.index", tab="nilai"))

    rows = conn.execute(
        "SELECT sp.*, m.nim, m.nama AS mhs_nama FROM sp_peserta sp "
        "JOIN mahasiswa m ON m.id = sp.mahasiswa_id "
        "WHERE sp.sp_kelas_id=? AND sp.status_approval='Disetujui' ORDER BY m.nama",
        (kid,),
    ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["NIM", "Nama", "Tugas", "UTS", "UAS", "Nilai Akhir", "Grade", "Kehadiran (%)"])
    for r in rows:
        kehadiran = L.sp_persentase_kehadiran(conn, r["id"])
        writer.writerow(
            [
                r["nim"],
                r["mhs_nama"],
                r["tugas"] or "",
                r["uts"] or "",
                r["uas"] or "",
                r["nilai_akhir"] or "",
                r["nilai_huruf"] or "",
                kehadiran["persen"],
            ]
        )
    _db.log(conn, "Export Rekap Nilai SP", f"kelas #{kid}")
    filename = f"rekap-nilai-sp-{kelas['mk_kode']}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
