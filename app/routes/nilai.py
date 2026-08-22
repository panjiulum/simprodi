# -*- coding: utf-8 -*-
"""routes/nilai.py — Modul 11: Nilai Mahasiswa & OBE Assessment Engine.

Fondasi data akademik tambahan kedua yang sebelumnya belum ada di SIMPRODI
(lihat docs/INTEGRASI_SITIPRO_SIMPRODI.md §7, "Belum tercakup"): nilai per
mahasiswa per CPMK, dipetakan lewat cpmk_cpl (Modul 9) untuk menghasilkan
capaian CPL individu & program — rantai keterlacakan OBE lengkap:
CPL -> CPMK -> nilai_cpmk (per mahasiswa) -> capaian CPL.

Empat tab:
  - Peserta Kelas: kelola KRS (mahasiswa terdaftar di 1 jadwal_kelas).
  - Input Nilai: nilai per CPMK per mahasiswa terdaftar + nilai akhir kelas.
  - Capaian CPL Individu: rekap capaian OBE 1 mahasiswa (lintas mata kuliah).
  - Capaian CPL Program: rekap capaian OBE tingkat program (Assessment Engine).
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

bp = Blueprint("nilai", __name__, url_prefix="/nilai")


def _daftar_jadwal(conn):
    return conn.execute(
        "SELECT jk.*, mk.kode AS mk_kode, mk.nama AS mk_nama, mk.id AS mata_kuliah_id "
        "FROM jadwal_kelas jk JOIN mata_kuliah mk ON mk.id = jk.mata_kuliah_id "
        "ORDER BY jk.tahun_akademik DESC, mk.kode, jk.kelas"
    ).fetchall()


@bp.route("/")
def index():
    conn = current_app.get_db()
    tab = request.args.get("tab", "peserta")
    if tab not in ("peserta", "input", "capaian-individu", "capaian-program"):
        tab = "peserta"

    ctx = {"tab": tab, "jadwal_rows": _daftar_jadwal(conn)}

    if tab in ("peserta", "input"):
        jid = request.args.get("jadwal", type=int)
        if not jid and ctx["jadwal_rows"]:
            jid = ctx["jadwal_rows"][0]["id"]
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

        if tab == "peserta" and jadwal_terpilih:
            ctx["peserta_rows"] = conn.execute(
                "SELECT k.*, m.nim, m.nama AS mhs_nama FROM krs k "
                "JOIN mahasiswa m ON m.id = k.mahasiswa_id "
                "WHERE k.jadwal_kelas_id=? ORDER BY m.nama",
                (jid,),
            ).fetchall()
            ctx["mahasiswa_belum_ikut"] = conn.execute(
                "SELECT id, nim, nama FROM mahasiswa WHERE status='Aktif' AND id NOT IN "
                "(SELECT mahasiswa_id FROM krs WHERE jadwal_kelas_id=?) ORDER BY nama",
                (jid,),
            ).fetchall()

        if tab == "input" and jadwal_terpilih:
            ctx["peserta_rows"] = conn.execute(
                "SELECT k.*, m.nim, m.nama AS mhs_nama FROM krs k "
                "JOIN mahasiswa m ON m.id = k.mahasiswa_id "
                "WHERE k.jadwal_kelas_id=? ORDER BY m.nama",
                (jid,),
            ).fetchall()
            kid = request.args.get("krs", type=int)
            if not kid and ctx["peserta_rows"]:
                kid = ctx["peserta_rows"][0]["id"]
            krs_terpilih = (
                conn.execute(
                    "SELECT k.*, m.nim, m.nama AS mhs_nama FROM krs k "
                    "JOIN mahasiswa m ON m.id = k.mahasiswa_id WHERE k.id=?",
                    (kid,),
                ).fetchone()
                if kid
                else None
            )
            ctx["krs_terpilih"] = krs_terpilih
            # Audit Menyeluruh — PHASE 6: OBE & CQI — pemilih instrumen
            # asesmen (Assessment step di rantai OBE). Default "Nilai
            # Akhir" supaya alur input satu-nilai-per-CPMK yang sudah ada
            # tetap identik kalau operator tidak memilih instrumen lain.
            jenis_asesmen = request.args.get("asesmen", "Nilai Akhir")
            if jenis_asesmen not in C.JENIS_ASESMEN_LIST:
                jenis_asesmen = "Nilai Akhir"
            ctx["jenis_asesmen_list"] = C.JENIS_ASESMEN_LIST
            ctx["jenis_asesmen_terpilih"] = jenis_asesmen
            if krs_terpilih:
                cpmk_rows = conn.execute(
                    "SELECT * FROM cpmk WHERE mata_kuliah_id=? ORDER BY kode",
                    (jadwal_terpilih["mata_kuliah_id"],),
                ).fetchall()
                nilai_map = {
                    r["cpmk_id"]: r["nilai_angka"]
                    for r in conn.execute(
                        "SELECT cpmk_id, nilai_angka FROM nilai_cpmk WHERE krs_id=? AND jenis_asesmen=?",
                        (kid, jenis_asesmen),
                    ).fetchall()
                }
                ctx["cpmk_rows"] = cpmk_rows
                ctx["nilai_map"] = nilai_map
                # Rekap ringkas instrumen apa saja yang SUDAH terisi utk tiap
                # CPMK peserta ini (lintas semua jenis_asesmen) -- traceability
                # "Assessment -> Nilai" tanpa perlu berpindah-pindah dropdown.
                ctx["asesmen_terisi"] = {}
                for r in conn.execute(
                    "SELECT cpmk_id, jenis_asesmen FROM nilai_cpmk "
                    "WHERE krs_id=? AND nilai_angka IS NOT NULL",
                    (kid,),
                ).fetchall():
                    ctx["asesmen_terisi"].setdefault(r["cpmk_id"], []).append(r["jenis_asesmen"])
            else:
                ctx["cpmk_rows"] = []
                ctx["nilai_map"] = {}
                ctx["asesmen_terisi"] = {}

    elif tab == "capaian-individu":
        kur = _kurikulum_aktif(conn)
        ctx["kur"] = kur
        ctx["mahasiswa_list"] = conn.execute(
            "SELECT id, nim, nama FROM mahasiswa ORDER BY nama"
        ).fetchall()
        mid = request.args.get("mahasiswa", type=int)
        ctx["mahasiswa_terpilih"] = (
            conn.execute("SELECT * FROM mahasiswa WHERE id=?", (mid,)).fetchone() if mid else None
        )
        if mid and kur:
            ctx["capaian"] = L.capaian_cpl_mahasiswa(conn, mid, kur["id"])
        else:
            ctx["capaian"] = []

    elif tab == "capaian-program":
        kur = _kurikulum_aktif(conn)
        ctx["kur"] = kur
        ctx["capaian"] = L.capaian_cpl_program(conn, kur["id"]) if kur else []
        ctx["kkm"] = C.KKM_CPMK

    return render_template("nilai.html", **ctx)


@bp.route("/peserta/tambah", methods=["POST"])
def tambah_peserta():
    conn = current_app.get_db()
    f = request.form
    jadwal_kelas_id = f.get("jadwal_kelas_id", type=int)
    mahasiswa_id = f.get("mahasiswa_id", type=int)
    if not jadwal_kelas_id or not mahasiswa_id:
        flash("Pilih mahasiswa terlebih dahulu.", "error")
        return redirect(url_for("nilai.index", tab="peserta", jadwal=jadwal_kelas_id))
    try:
        conn.execute(
            "INSERT INTO krs(mahasiswa_id, jadwal_kelas_id) VALUES(?,?)",
            (mahasiswa_id, jadwal_kelas_id),
        )
        conn.commit()
        _db.log(conn, "Tambah Peserta Kelas", f"mhs #{mahasiswa_id} -> jadwal #{jadwal_kelas_id}")
        flash("Mahasiswa ditambahkan sebagai peserta kelas.", "ok")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menambahkan peserta (mungkin sudah terdaftar)")
    return redirect(url_for("nilai.index", tab="peserta", jadwal=jadwal_kelas_id))


@bp.route("/peserta/<int:kid>/hapus", methods=["POST"])
def hapus_peserta(kid):
    conn = current_app.get_db()
    row = conn.execute("SELECT jadwal_kelas_id FROM krs WHERE id=?", (kid,)).fetchone()
    conn.execute("DELETE FROM krs WHERE id=?", (kid,))
    conn.commit()
    _db.log(conn, "Hapus Peserta Kelas", str(kid))
    flash("Peserta dihapus dari kelas (nilai CPMK terkait ikut terhapus).", "ok")
    return redirect(
        url_for("nilai.index", tab="peserta", jadwal=row["jadwal_kelas_id"] if row else None)
    )


@bp.route("/input/simpan", methods=["POST"])
def simpan_nilai():
    conn = current_app.get_db()
    f = request.form
    krs_id = f.get("krs_id", type=int)
    jadwal_kelas_id = f.get("jadwal_kelas_id", type=int)
    if not krs_id:
        flash("Peserta kelas tidak ditemukan.", "error")
        return redirect(url_for("nilai.index", tab="input", jadwal=jadwal_kelas_id))

    # Audit Menyeluruh — PHASE 6: OBE & CQI — instrumen asesmen yang sedang
    # diisi (Tugas/Kuis/UTS/UAS/Proyek/Praktikum/Nilai Akhir). Default
    # "Nilai Akhir" menjaga perilaku lama (satu nilai final per CPMK) tetap
    # identik kalau operator tidak pernah menyentuh dropdown instrumen.
    jenis_asesmen = f.get("jenis_asesmen", "Nilai Akhir")
    if jenis_asesmen not in C.JENIS_ASESMEN_LIST:
        jenis_asesmen = "Nilai Akhir"

    nilai_akhir_raw = f.get("nilai_akhir", "").strip()
    nilai_akhir = None
    if nilai_akhir_raw:
        try:
            nilai_akhir = float(nilai_akhir_raw)
        except ValueError:
            flash(
                f"Nilai akhir '{nilai_akhir_raw}' bukan angka yang valid — tidak disimpan.", "error"
            )
            return redirect(
                url_for("nilai.index", tab="input", jadwal=jadwal_kelas_id, krs=krs_id, asesmen=jenis_asesmen)
            )
        if not (0 <= nilai_akhir <= 100):
            flash("Nilai akhir harus di antara 0 dan 100 — tidak disimpan.", "error")
            return redirect(
                url_for("nilai.index", tab="input", jadwal=jadwal_kelas_id, krs=krs_id, asesmen=jenis_asesmen)
            )

    conn.execute(
        "UPDATE krs SET nilai_akhir=?, nilai_huruf=? WHERE id=?",
        (nilai_akhir, L_nilai_huruf(nilai_akhir), krs_id),
    )

    for key, value in f.items():
        if not key.startswith("cpmk_"):
            continue
        cpmk_id = key.replace("cpmk_", "")
        if not cpmk_id.isdigit():
            continue
        value = value.strip()
        if not value:
            nilai_angka = None
        else:
            try:
                nilai_angka = float(value)
            except ValueError:
                flash(f"Nilai CPMK '{value}' bukan angka yang valid — dilewati.", "error")
                continue
            if not (0 <= nilai_angka <= 100):
                flash("Nilai CPMK harus di antara 0 dan 100 — dilewati.", "error")
                continue
        conn.execute(
            "INSERT INTO nilai_cpmk(krs_id, cpmk_id, jenis_asesmen, nilai_angka) VALUES(?,?,?,?) "
            "ON CONFLICT(krs_id, cpmk_id, jenis_asesmen) DO UPDATE SET nilai_angka=excluded.nilai_angka",
            (krs_id, int(cpmk_id), jenis_asesmen, nilai_angka),
        )
    conn.commit()
    _db.log(
        conn, "Simpan Nilai CPMK", f"krs #{krs_id}",
        modul="Nilai", entitas="Nilai CPMK", entitas_id=krs_id,
        alasan=f"instrumen: {jenis_asesmen}",
    )
    flash(f"Nilai ({jenis_asesmen}) disimpan.", "ok")
    return redirect(
        url_for("nilai.index", tab="input", jadwal=jadwal_kelas_id, krs=krs_id, asesmen=jenis_asesmen)
    )


def L_nilai_huruf(nilai_akhir):
    from app.constants import nilai_angka_ke_huruf

    if not nilai_akhir:
        return None
    try:
        return nilai_angka_ke_huruf(float(nilai_akhir))
    except ValueError:
        return None
