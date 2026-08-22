# -*- coding: utf-8 -*-
"""routes/kurikulum.py — Modul 9: Kurikulum & OBE (Outcome-Based Education).

Struktur tab (Dashboard OBE / Struktur Kurikulum / Pemetaan CPL-CPMK /
RPS & Perangkat) diadaptasi dari susunan menu acuan UI/UX SITIPRO
(`Curriculum.tsx`), tetapi seluruh isinya dibangun ulang sebagai modul
Flask/SQLite sungguhan: tidak ada angka contoh/AI-generated seperti pada
demo — semua data berasal dari input CPL, mata kuliah, dan CPMK yang
disimpan lewat form di modul ini sendiri.

Kaidah akademik yang dipakai:
  - Kategori CPL mengikuti 4 unsur SN-DIKTI (Sikap, Pengetahuan,
    Keterampilan Umum, Keterampilan Khusus) — sama dengan unsur yang
    dinilai pada instrumen akreditasi LAMEMBA.
  - Rantai keterlacakan OBE: CPL -> CPMK (per mata kuliah) -> status RPS.
    Pemetaan CPMK-ke-CPL disimpan sebagai tabel relasi (matrix), bukan
    teks bebas, supaya bisa direkap sebagai matriks untuk borang akreditasi.
  - Kelengkapan RPS dihitung dari status resmi (Belum Disusun/Draft/
    Review GKM/Disahkan) per mata kuliah — konsisten dengan pola status
    terkontrol (dropdown, bukan ketik bebas) yang dipakai di seluruh
    SIMPRODI (lihat constants.py).
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

bp = Blueprint("kurikulum", __name__, url_prefix="/kurikulum")


def _folder():
    folder = os.path.join(_db.home_dir(), "SistemSkripsi", "rps")
    os.makedirs(folder, exist_ok=True)
    return folder


def _kurikulum_aktif(conn):
    """Kurikulum berstatus Aktif jika ada; kalau tidak ada (mis. semua
    diubah manual jadi Draft/Non-aktif), jatuh ke kurikulum yang dibuat
    duluan — supaya modul tetap punya konteks kerja, tidak pernah None."""
    row = conn.execute(
        "SELECT * FROM kurikulum_versi WHERE status='Aktif' ORDER BY id LIMIT 1"
    ).fetchone()
    if row:
        return row
    return conn.execute("SELECT * FROM kurikulum_versi ORDER BY id LIMIT 1").fetchone()


def _kurikulum_terkunci(conn, kurikulum_id):
    """Audit Menyeluruh — PHASE 5, Versioning Kurikulum (Audit §24):
    "Ketika versi sudah Active, jangan melakukan perubahan destruktif."
    Dipakai oleh rute hapus_cpl/hapus_mk/hapus_cpmk/hapus_sub_cpmk sebagai
    guard TERAKHIR sebelum DELETE — kurikulum berstatus Aktif (sedang jadi
    acuan resmi) atau Diarsipkan (riwayatnya harus tetap utuh utk
    akreditasi) tidak boleh diubah strukturnya lagi lewat modul ini; kalau
    memang perlu revisi struktural, gunakan Clone Version untuk membuat
    versi Draft baru dulu. Mengembalikan nama kurikulum (str) kalau
    terkunci, atau None kalau boleh diubah."""
    row = conn.execute(
        "SELECT nama, status FROM kurikulum_versi WHERE id=?", (kurikulum_id,)
    ).fetchone()
    if row and row["status"] in C.STATUS_KURIKULUM_TERKUNCI:
        return f"{row['nama']} (status: {row['status']})"
    return None


def _stats(conn, kurikulum_id):
    cpl_rows = conn.execute(
        "SELECT * FROM cpl WHERE kurikulum_id=? ORDER BY kategori, urutan, kode",
        (kurikulum_id,),
    ).fetchall()
    mk_rows = conn.execute(
        "SELECT * FROM mata_kuliah WHERE kurikulum_id=? ORDER BY semester, kode",
        (kurikulum_id,),
    ).fetchall()

    cpl_per_kategori = {k: 0 for k in C.KATEGORI_CPL_LIST}
    for r in cpl_rows:
        if r["kategori"] in cpl_per_kategori:
            cpl_per_kategori[r["kategori"]] += 1

    total_mk = len(mk_rows)
    total_sks = sum(r["sks"] or 0 for r in mk_rows)

    rps_per_status = {s: 0 for s in C.STATUS_RPS_LIST}
    for r in mk_rows:
        if r["rps_status"] in rps_per_status:
            rps_per_status[r["rps_status"]] += 1
    rps_disahkan = rps_per_status.get("Disahkan", 0)
    rps_persen = round((rps_disahkan / total_mk) * 100) if total_mk else 0

    mk_tanpa_cpmk = 0
    if total_mk:
        ids = [r["id"] for r in mk_rows]
        placeholders = ",".join("?" * len(ids))
        punya_cpmk = {
            r["mata_kuliah_id"]
            for r in conn.execute(
                f"SELECT DISTINCT mata_kuliah_id FROM cpmk WHERE mata_kuliah_id IN ({placeholders})",
                ids,
            ).fetchall()
        }
        mk_tanpa_cpmk = total_mk - len(punya_cpmk)

    semester_map = {}
    for r in mk_rows:
        s = r["semester"] or 0
        semester_map.setdefault(s, {"jumlah_mk": 0, "sks": 0})
        semester_map[s]["jumlah_mk"] += 1
        semester_map[s]["sks"] += r["sks"] or 0
    per_semester = [{"semester": s, **v} for s, v in sorted(semester_map.items())]

    return {
        "total_cpl": len(cpl_rows),
        "cpl_per_kategori": cpl_per_kategori,
        "total_mk": total_mk,
        "total_sks": total_sks,
        "rps_per_status": rps_per_status,
        "rps_persen": rps_persen,
        "mk_tanpa_cpmk": mk_tanpa_cpmk,
        "per_semester": per_semester,
    }


@bp.route("/")
def index():
    conn = current_app.get_db()
    kur = _kurikulum_aktif(conn)
    tab = request.args.get("tab", "dashboard")

    if not kur:
        # Baris pertama sudah diseed otomatis di db.py — kondisi ini
        # seharusnya tidak pernah terjadi, tapi dijaga supaya tidak error.
        return render_template("kurikulum.html", kur=None, tab=tab)

    ctx = {
        "kur": kur,
        "tab": tab,
        "daftar_kurikulum": conn.execute(
            "SELECT * FROM kurikulum_versi ORDER BY id DESC"
        ).fetchall(),
        "status_kurikulum_list": C.STATUS_KURIKULUM_LIST,
    }

    if tab == "dashboard":
        ctx["stats"] = _stats(conn, kur["id"])

    elif tab == "struktur":
        edit_cpl_id = request.args.get("edit_cpl", type=int)
        edit_mk_id = request.args.get("edit_mk", type=int)
        ctx["cpl_rows"] = conn.execute(
            "SELECT * FROM cpl WHERE kurikulum_id=? ORDER BY kategori, urutan, kode",
            (kur["id"],),
        ).fetchall()
        ctx["mk_rows"] = conn.execute(
            "SELECT * FROM mata_kuliah WHERE kurikulum_id=? ORDER BY semester, kode",
            (kur["id"],),
        ).fetchall()
        ctx["edit_cpl"] = (
            conn.execute("SELECT * FROM cpl WHERE id=?", (edit_cpl_id,)).fetchone()
            if edit_cpl_id
            else None
        )
        ctx["edit_mk"] = (
            conn.execute("SELECT * FROM mata_kuliah WHERE id=?", (edit_mk_id,)).fetchone()
            if edit_mk_id
            else None
        )
        ctx["kategori_list"] = C.KATEGORI_CPL_LIST
        ctx["jenis_mk_list"] = C.JENIS_MK_LIST

    elif tab == "pemetaan":
        ctx["mk_rows"] = conn.execute(
            "SELECT * FROM mata_kuliah WHERE kurikulum_id=? ORDER BY semester, kode",
            (kur["id"],),
        ).fetchall()
        mk_id = request.args.get("mk", type=int)
        if not mk_id and ctx["mk_rows"]:
            mk_id = ctx["mk_rows"][0]["id"]
        ctx["mk_terpilih"] = (
            conn.execute("SELECT * FROM mata_kuliah WHERE id=?", (mk_id,)).fetchone()
            if mk_id
            else None
        )
        ctx["cpl_rows"] = conn.execute(
            "SELECT * FROM cpl WHERE kurikulum_id=? ORDER BY kategori, urutan, kode",
            (kur["id"],),
        ).fetchall()
        if mk_id:
            cpmk_rows = conn.execute(
                "SELECT * FROM cpmk WHERE mata_kuliah_id=? ORDER BY kode", (mk_id,)
            ).fetchall()
            mapped = {}
            sub_counts = {}
            for c in cpmk_rows:
                mapped[c["id"]] = {
                    r["cpl_id"]
                    for r in conn.execute(
                        "SELECT cpl_id FROM cpmk_cpl WHERE cpmk_id=?", (c["id"],)
                    ).fetchall()
                }
                sub_counts[c["id"]] = conn.execute(
                    "SELECT COUNT(*) c FROM sub_cpmk WHERE cpmk_id=?", (c["id"],)
                ).fetchone()["c"]
            ctx["cpmk_rows"] = cpmk_rows
            ctx["cpmk_mapped"] = mapped
            ctx["sub_counts"] = sub_counts
        else:
            ctx["cpmk_rows"] = []
            ctx["cpmk_mapped"] = {}
            ctx["sub_counts"] = {}

        cpmk_id = request.args.get("cpmk", type=int)
        ctx["cpmk_terpilih"] = (
            conn.execute("SELECT * FROM cpmk WHERE id=?", (cpmk_id,)).fetchone()
            if cpmk_id
            else None
        )
        ctx["sub_cpmk_rows"] = (
            conn.execute(
                "SELECT * FROM sub_cpmk WHERE cpmk_id=? ORDER BY urutan, kode", (cpmk_id,)
            ).fetchall()
            if cpmk_id
            else []
        )

    elif tab == "rps":
        status_filter = request.args.get("status", "")
        q = "SELECT * FROM mata_kuliah WHERE kurikulum_id=?"
        params = [kur["id"]]
        if status_filter:
            q += " AND rps_status=?"
            params.append(status_filter)
        q += " ORDER BY semester, kode"
        ctx["mk_rows"] = conn.execute(q, params).fetchall()
        ctx["status_filter"] = status_filter
        ctx["status_list"] = C.STATUS_RPS_LIST

    return render_template("kurikulum.html", **ctx)


@bp.route("/versi/simpan", methods=["POST"])
def simpan_versi():
    conn = current_app.get_db()
    f = request.form
    kid = f.get("id", type=int)
    nama = f.get("nama", "").strip()
    if not nama:
        flash("Nama kurikulum wajib diisi.", "error")
        return redirect(url_for("kurikulum.index"))
    status_baru = f.get("status", "Draft")
    if status_baru not in C.STATUS_KURIKULUM_LIST:
        status_baru = "Draft"

    if kid:
        # Audit Phase 4 — nilai lama, utk audit event kalau status berubah.
        sebelum = conn.execute("SELECT status FROM kurikulum_versi WHERE id=?", (kid,)).fetchone()
        status_lama = sebelum["status"] if sebelum else None
        if status_baru == "Aktif":
            # Hanya satu kurikulum yang boleh Aktif sekaligus, supaya
            # dashboard/struktur/pemetaan/RPS tidak ambigu sedang mengacu
            # ke versi kurikulum yang mana. Audit Phase 5 (perbaikan bug):
            # sebelumnya menyetel 'Non-aktif' -- nama status dari skema
            # 3-status yang lama, TIDAK ADA lagi di STATUS_KURIKULUM_LIST
            # sejak diperluas jadi 5 status, jadi ini akan melanggar CHECK
            # constraint Phase 2 (baris ini sebelumnya tidak pernah
            # tereksekusi di kondisi normal karena hanya terpicu saat
            # operator benar-benar mengaktifkan kurikulum lain -- baru
            # ketahuan sekarang saat status_kurikulum_list diperluas).
            # 'Diarsipkan' adalah padanan yang benar: kurikulum lama yang
            # digantikan otomatis jadi arsip, bukan "non-aktif" yang
            # ambigu.
            conn.execute(
                "UPDATE kurikulum_versi SET status='Diarsipkan' WHERE status='Aktif' AND id!=?",
                (kid,),
            )
        conn.execute(
            "UPDATE kurikulum_versi SET nama=?, tahun_berlaku=?, status=?, keterangan=? WHERE id=?",
            (
                nama,
                f.get("tahun_berlaku", "").strip(),
                status_baru,
                f.get("keterangan", "").strip(),
                kid,
            ),
        )
        conn.commit()
        if status_lama != status_baru:
            _db.log(
                conn, "Simpan Kurikulum", nama,
                modul="Kurikulum", entitas="Kurikulum", entitas_id=kid,
                nilai_lama=status_lama, nilai_baru=status_baru,
            )
        else:
            _db.log(conn, "Simpan Kurikulum", nama, modul="Kurikulum", entitas="Kurikulum", entitas_id=kid)
        flash("Kurikulum diperbarui.", "ok")
    else:
        cur = conn.execute(
            "INSERT INTO kurikulum_versi(nama, tahun_berlaku, status, keterangan) VALUES(?,?,?,?)",
            (nama, f.get("tahun_berlaku", "").strip(), "Draft", f.get("keterangan", "").strip()),
        )
        conn.commit()
        _db.log(
            conn, "Simpan Kurikulum", nama,
            modul="Kurikulum", entitas="Kurikulum", entitas_id=cur.lastrowid,
            nilai_lama=None, nilai_baru="Draft",
        )
        flash(f"Kurikulum '{nama}' ditambahkan sebagai Draft.", "ok")
    return redirect(url_for("kurikulum.index", tab="dashboard"))


@bp.route("/versi/<int:kid>/klon", methods=["POST"])
def klon_versi(kid):
    """Audit Menyeluruh — PHASE 5, Versioning Kurikulum (Audit §24):
    "Kurikulum 2025 -> Clone Version -> Kurikulum 2027". Menyalin seluruh
    struktur (CPL, Mata Kuliah, CPMK, Sub-CPMK, pemetaan CPMK-CPL) dari
    kurikulum sumber ke kurikulum BARU berstatus Draft — supaya revisi
    struktural terhadap kurikulum yang sudah Aktif/Diarsipkan tidak perlu
    mengubah versi lama (yang dikunci _kurikulum_terkunci utk Diarsipkan,
    dan dilindungi guard pemakaian nyata utk Aktif), cukup dikerjakan di
    versi baru lalu diaktifkan saat sudah siap.

    File RPS SENGAJA TIDAK ikut disalin (rps_file/rps_nama_file_asli/
    rps_revisi/rps_tanggal_sahkan direset ke kosong/'Belum Disusun') --
    RPS versi baru harus disusun ulang secara sadar (dosen pengampu, isi
    materi, dst. bisa berbeda dari versi sebelumnya), bukan mewarisi file
    lama yang mengklaim sudah "Disahkan" padahal belum pernah ditinjau utk
    versi baru ini."""
    conn = current_app.get_db()
    sumber = conn.execute("SELECT * FROM kurikulum_versi WHERE id=?", (kid,)).fetchone()
    if not sumber:
        flash("Kurikulum sumber tidak ditemukan.", "error")
        return redirect(url_for("kurikulum.index", tab="dashboard"))

    nama_baru = request.form.get("nama_baru", "").strip() or f"{sumber['nama']} (Salinan)"
    tahun_baru = request.form.get("tahun_berlaku_baru", "").strip() or sumber["tahun_berlaku"]

    try:
        cur = conn.execute(
            "INSERT INTO kurikulum_versi(nama, tahun_berlaku, status, keterangan) VALUES(?,?,?,?)",
            (nama_baru, tahun_baru, "Draft", f"Hasil Clone Version dari \"{sumber['nama']}\""),
        )
        kid_baru = cur.lastrowid

        peta_cpl = {}
        for cpl in conn.execute(
            "SELECT * FROM cpl WHERE kurikulum_id=? ORDER BY id", (kid,)
        ).fetchall():
            c2 = conn.execute(
                "INSERT INTO cpl(kurikulum_id, kode, kategori, deskripsi, urutan) VALUES(?,?,?,?,?)",
                (kid_baru, cpl["kode"], cpl["kategori"], cpl["deskripsi"], cpl["urutan"]),
            )
            peta_cpl[cpl["id"]] = c2.lastrowid

        n_mk = n_cpmk = n_subcpmk = n_pemetaan = 0
        for mk in conn.execute(
            "SELECT * FROM mata_kuliah WHERE kurikulum_id=? ORDER BY id", (kid,)
        ).fetchall():
            mk2 = conn.execute(
                "INSERT INTO mata_kuliah(kurikulum_id, kode, nama, sks, semester, jenis, "
                "kelompok_mk, rps_status, keterangan) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    kid_baru, mk["kode"], mk["nama"], mk["sks"], mk["semester"],
                    mk["jenis"], mk["kelompok_mk"], "Belum Disusun", mk["keterangan"],
                ),
            )
            mk_id_baru = mk2.lastrowid
            n_mk += 1
            for cpmk in conn.execute(
                "SELECT * FROM cpmk WHERE mata_kuliah_id=? ORDER BY id", (mk["id"],)
            ).fetchall():
                cpmk2 = conn.execute(
                    "INSERT INTO cpmk(mata_kuliah_id, kode, deskripsi) VALUES(?,?,?)",
                    (mk_id_baru, cpmk["kode"], cpmk["deskripsi"]),
                )
                cpmk_id_baru = cpmk2.lastrowid
                n_cpmk += 1
                for pemetaan in conn.execute(
                    "SELECT cpl_id FROM cpmk_cpl WHERE cpmk_id=?", (cpmk["id"],)
                ).fetchall():
                    cpl_id_baru = peta_cpl.get(pemetaan["cpl_id"])
                    if cpl_id_baru:
                        conn.execute(
                            "INSERT OR IGNORE INTO cpmk_cpl(cpmk_id, cpl_id) VALUES(?,?)",
                            (cpmk_id_baru, cpl_id_baru),
                        )
                        n_pemetaan += 1
                for sub in conn.execute(
                    "SELECT * FROM sub_cpmk WHERE cpmk_id=? ORDER BY id", (cpmk["id"],)
                ).fetchall():
                    conn.execute(
                        "INSERT INTO sub_cpmk(cpmk_id, kode, deskripsi, urutan) VALUES(?,?,?,?)",
                        (cpmk_id_baru, sub["kode"], sub["deskripsi"], sub["urutan"]),
                    )
                    n_subcpmk += 1
        conn.commit()
        _db.log(
            conn, "Clone Kurikulum", f"{sumber['nama']} -> {nama_baru}",
            modul="Kurikulum", entitas="Kurikulum", entitas_id=kid_baru,
            nilai_lama=sumber["nama"], nilai_baru=nama_baru,
            alasan=f"{len(peta_cpl)} CPL, {n_mk} MK, {n_cpmk} CPMK, {n_subcpmk} Sub-CPMK, {n_pemetaan} pemetaan CPL disalin",
        )
        flash(
            f"Kurikulum \"{nama_baru}\" dibuat sebagai Draft — hasil Clone Version dari "
            f"\"{sumber['nama']}\" ({len(peta_cpl)} CPL, {n_mk} MK, {n_cpmk} CPMK, {n_subcpmk} "
            "Sub-CPMK disalin; RPS perlu disusun ulang di versi baru ini).",
            "ok",
        )
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal meng-clone kurikulum")
    return redirect(url_for("kurikulum.index", tab="dashboard"))


@bp.route("/cpl/simpan", methods=["POST"])
def simpan_cpl():
    conn = current_app.get_db()
    kur = _kurikulum_aktif(conn)
    f = request.form
    cid = f.get("id", type=int)
    kode = f.get("kode", "").strip()
    deskripsi = f.get("deskripsi", "").strip()
    if not kode or not deskripsi:
        flash("Kode dan deskripsi CPL wajib diisi.", "error")
        return redirect(url_for("kurikulum.index", tab="struktur"))
    # Audit Menyeluruh — PHASE 5 (re-check): guard anti-destruktif Audit §24
    # sebelumnya HANYA dipasang di rute hapus_cpl, padahal TAMBAH/EDIT CPL
    # di kurikulum yang sudah Diarsipkan sama-sama melanggar prinsip "arsip
    # historis harus beku" -- kurikulum lama seharusnya jadi cerminan persis
    # apa yang berlaku saat itu, bukan bisa disisipi CPL baru bertahun-tahun
    # kemudian. Guard yang sama sekarang dipasang juga di simpan_cpl/mk/
    # cpmk/sub_cpmk, bukan cuma di jalur hapus.
    kurikulum_id_target = conn.execute(
        "SELECT kurikulum_id FROM cpl WHERE id=?", (cid,)
    ).fetchone()["kurikulum_id"] if cid else (kur["id"] if kur else None)
    terkunci = _kurikulum_terkunci(conn, kurikulum_id_target) if kurikulum_id_target else None
    if terkunci:
        flash(
            f"CPL tidak bisa disimpan — kurikulum induknya ({terkunci}) sudah tidak boleh diubah "
            "strukturnya. Gunakan Clone Version untuk membuat versi Draft baru kalau memang perlu "
            "revisi struktural.",
            "error",
        )
        return redirect(url_for("kurikulum.index", tab="struktur"))
    try:
        if cid:
            conn.execute(
                "UPDATE cpl SET kode=?, kategori=?, deskripsi=?, urutan=? WHERE id=?",
                (
                    kode,
                    f.get("kategori", "Pengetahuan"),
                    deskripsi,
                    f.get("urutan", type=int) or 0,
                    cid,
                ),
            )
            flash(f"{kode} diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO cpl(kurikulum_id, kode, kategori, deskripsi, urutan) VALUES(?,?,?,?,?)",
                (
                    kur["id"],
                    kode,
                    f.get("kategori", "Pengetahuan"),
                    deskripsi,
                    f.get("urutan", type=int) or 0,
                ),
            )
            flash(f"{kode} ditambahkan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan CPL", kode)
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan CPL")
    return redirect(url_for("kurikulum.index", tab="struktur"))


@bp.route("/cpl/<int:cid>/hapus", methods=["POST"])
def hapus_cpl(cid):
    """Audit Kontinuitas: CPL adalah induk cascade (cpl -> cqi_siklus ON
    DELETE CASCADE, db.py). Sebelum audit ini, menghapus 1 CPL yang sudah
    dipakai di siklus CQI/PDCA tahun-tahun sebelumnya akan ikut menghapus
    seluruh riwayat siklus itu tanpa peringatan. Sekarang: ditolak dulu
    kalau masih dipakai, operator diarahkan untuk menghapus/menutup siklus
    CQI terkait secara sadar lewat modul CQI sebelum CPL boleh dihapus."""
    conn = current_app.get_db()
    row = conn.execute("SELECT kode, kurikulum_id FROM cpl WHERE id=?", (cid,)).fetchone()
    if not row:
        flash("CPL tidak ditemukan.", "error")
        return redirect(url_for("kurikulum.index", tab="struktur"))
    terkunci = _kurikulum_terkunci(conn, row["kurikulum_id"])
    if terkunci:
        flash(
            f'CPL "{row["kode"]}" tidak bisa dihapus — kurikulum induknya ({terkunci}) sudah tidak '
            "boleh diubah strukturnya. Gunakan Clone Version untuk membuat versi Draft baru kalau "
            "memang perlu revisi struktural.",
            "error",
        )
        return redirect(url_for("kurikulum.index", tab="struktur"))
    jumlah_cqi = conn.execute(
        "SELECT COUNT(*) n FROM cqi_siklus WHERE cpl_id=?", (cid,)
    ).fetchone()["n"]
    if jumlah_cqi:
        flash(
            f"CPL \"{row['kode']}\" tidak bisa dihapus — masih dipakai di "
            f"{jumlah_cqi} siklus CQI/PDCA (termasuk yang sudah tercatat "
            "di tahun akademik sebelumnya). Hapus/pindahkan siklus CQI "
            "terkait dulu lewat modul Siklus CQI, baru CPL ini bisa dihapus.",
            "error",
        )
        return redirect(url_for("kurikulum.index", tab="struktur"))
    conn.execute("DELETE FROM cpl WHERE id=?", (cid,))
    conn.commit()
    _db.log(conn, "Hapus CPL", row["kode"])
    flash("CPL dihapus (pemetaan CPMK terkait ikut terhapus).", "ok")
    return redirect(url_for("kurikulum.index", tab="struktur"))


@bp.route("/mk/simpan", methods=["POST"])
def simpan_mk():
    conn = current_app.get_db()
    kur = _kurikulum_aktif(conn)
    f = request.form
    mid = f.get("id", type=int)
    kode = f.get("kode", "").strip()
    nama = f.get("nama", "").strip()
    if not kode or not nama:
        flash("Kode dan nama mata kuliah wajib diisi.", "error")
        return redirect(url_for("kurikulum.index", tab="struktur"))
    kurikulum_id_target = conn.execute(
        "SELECT kurikulum_id FROM mata_kuliah WHERE id=?", (mid,)
    ).fetchone()["kurikulum_id"] if mid else (kur["id"] if kur else None)
    terkunci = _kurikulum_terkunci(conn, kurikulum_id_target) if kurikulum_id_target else None
    if terkunci:
        flash(
            f"Mata kuliah tidak bisa disimpan — kurikulum induknya ({terkunci}) sudah tidak boleh "
            "diubah strukturnya. Gunakan Clone Version untuk membuat versi Draft baru kalau memang "
            "perlu revisi struktural.",
            "error",
        )
        return redirect(url_for("kurikulum.index", tab="struktur"))
    try:
        if mid:
            conn.execute(
                "UPDATE mata_kuliah SET kode=?, nama=?, sks=?, semester=?, jenis=?, "
                "kelompok_mk=?, keterangan=? WHERE id=?",
                (
                    kode,
                    nama,
                    f.get("sks", type=int) or 0,
                    f.get("semester", type=int) or 1,
                    f.get("jenis", "Wajib"),
                    f.get("kelompok_mk", "").strip(),
                    f.get("keterangan", "").strip(),
                    mid,
                ),
            )
            flash(f"{kode} diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO mata_kuliah(kurikulum_id, kode, nama, sks, semester, jenis, "
                "kelompok_mk, keterangan) VALUES(?,?,?,?,?,?,?,?)",
                (
                    kur["id"],
                    kode,
                    nama,
                    f.get("sks", type=int) or 0,
                    f.get("semester", type=int) or 1,
                    f.get("jenis", "Wajib"),
                    f.get("kelompok_mk", "").strip(),
                    f.get("keterangan", "").strip(),
                ),
            )
            flash(f"{kode} — {nama} ditambahkan.", "ok")
        conn.commit()
        _db.log(conn, "Simpan Mata Kuliah", kode)
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan mata kuliah")
    return redirect(url_for("kurikulum.index", tab="struktur"))


@bp.route("/mk/<int:mid>/hapus", methods=["POST"])
def hapus_mk(mid):
    """Audit Kontinuitas: mata_kuliah adalah induk rantai cascade terpanjang
    di skema ini (mata_kuliah -> jadwal_kelas -> bap & krs -> nilai_cpmk,
    semuanya ON DELETE CASCADE, lihat db.py). Sebelum audit ini, mata
    kuliah yang sudah pernah dibuka sebagai kelas di semester manapun bisa
    dihapus tanpa cek — otomatis ikut menghapus permanen seluruh jadwal
    kelas, presensi (BAP), dan NILAI mahasiswa dari SEMUA tahun akademik
    yang pernah memakai mata kuliah itu, dan pesan konfirmasinya pun tidak
    menyebut risiko sesungguhnya. Sekarang: ditolak dulu kalau sudah pernah
    dibuka sebagai kelas — operator harus menghapus kelasnya satu-satu
    secara sadar (lewat modul Jadwal Kelas) kalau memang bermaksud
    menghapus seluruh riwayatnya, bukan terjadi otomatis lewat 1 klik di
    sini. Mata kuliah yang BELUM PERNAH dibuka sebagai kelas (baru dibuat/
    salah ketik) tetap bisa langsung dihapus seperti sebelumnya."""
    conn = current_app.get_db()
    row = conn.execute(
        "SELECT kode, rps_file, kurikulum_id FROM mata_kuliah WHERE id=?", (mid,)
    ).fetchone()
    if not row:
        flash("Mata kuliah tidak ditemukan.", "error")
        return redirect(url_for("kurikulum.index", tab="struktur"))
    terkunci = _kurikulum_terkunci(conn, row["kurikulum_id"])
    if terkunci:
        flash(
            f'Mata kuliah "{row["kode"]}" tidak bisa dihapus — kurikulum induknya ({terkunci}) sudah '
            "tidak boleh diubah strukturnya. Gunakan Clone Version untuk membuat versi Draft baru "
            "kalau memang perlu revisi struktural.",
            "error",
        )
        return redirect(url_for("kurikulum.index", tab="struktur"))
    jumlah_kelas = conn.execute(
        "SELECT COUNT(*) n FROM jadwal_kelas WHERE mata_kuliah_id=?", (mid,)
    ).fetchone()["n"]
    if jumlah_kelas:
        tahun_terpakai = conn.execute(
            "SELECT DISTINCT tahun_akademik FROM jadwal_kelas WHERE mata_kuliah_id=? "
            "ORDER BY tahun_akademik",
            (mid,),
        ).fetchall()
        daftar_tahun = ", ".join(r["tahun_akademik"] for r in tahun_terpakai if r["tahun_akademik"])
        flash(
            f"Mata kuliah \"{row['kode']}\" tidak bisa dihapus — sudah pernah "
            f"dibuka sebagai {jumlah_kelas} kelas"
            + (f" (tahun akademik: {daftar_tahun})" if daftar_tahun else "")
            + ". Menghapusnya akan ikut menghapus permanen jadwal, presensi "
            "(BAP), dan nilai mahasiswa dari kelas-kelas tersebut. Hapus "
            "kelasnya satu per satu lewat modul Jadwal Kelas terlebih dahulu "
            "kalau memang bermaksud menghapus seluruh riwayatnya.",
            "error",
        )
        return redirect(url_for("kurikulum.index", tab="struktur"))
    if row["rps_file"] and os.path.exists(row["rps_file"]):
        try:
            os.remove(row["rps_file"])
        except OSError:
            pass
    conn.execute("DELETE FROM mata_kuliah WHERE id=?", (mid,))
    conn.commit()
    _db.log(conn, "Hapus Mata Kuliah", row["kode"])
    flash("Mata kuliah dihapus (CPMK & pemetaan CPL terkait ikut terhapus).", "ok")
    return redirect(url_for("kurikulum.index", tab="struktur"))


@bp.route("/cpmk/simpan", methods=["POST"])
def simpan_cpmk():
    conn = current_app.get_db()
    f = request.form
    mk_id = f.get("mata_kuliah_id", type=int)
    cid = f.get("id", type=int)
    kode = f.get("kode", "").strip()
    deskripsi = f.get("deskripsi", "").strip()
    cpl_ids = request.form.getlist("cpl_ids", type=int)

    if not mk_id:
        flash("Pilih mata kuliah terlebih dahulu.", "error")
        return redirect(url_for("kurikulum.index", tab="pemetaan"))
    if not kode or not deskripsi:
        flash("Kode dan deskripsi CPMK wajib diisi.", "error")
        return redirect(url_for("kurikulum.index", tab="pemetaan", mk=mk_id))

    mk_row = conn.execute("SELECT kurikulum_id FROM mata_kuliah WHERE id=?", (mk_id,)).fetchone()
    terkunci = _kurikulum_terkunci(conn, mk_row["kurikulum_id"]) if mk_row else None
    if terkunci:
        flash(
            f"CPMK tidak bisa disimpan — kurikulum induknya ({terkunci}) sudah tidak boleh diubah "
            "strukturnya. Gunakan Clone Version untuk membuat versi Draft baru kalau memang perlu "
            "revisi struktural.",
            "error",
        )
        return redirect(url_for("kurikulum.index", tab="pemetaan", mk=mk_id))

    if cid:
        conn.execute("UPDATE cpmk SET kode=?, deskripsi=? WHERE id=?", (kode, deskripsi, cid))
    else:
        cur = conn.execute(
            "INSERT INTO cpmk(mata_kuliah_id, kode, deskripsi) VALUES(?,?,?)",
            (mk_id, kode, deskripsi),
        )
        cid = cur.lastrowid

    conn.execute("DELETE FROM cpmk_cpl WHERE cpmk_id=?", (cid,))
    for cpl_id in cpl_ids:
        conn.execute("INSERT OR IGNORE INTO cpmk_cpl(cpmk_id, cpl_id) VALUES(?,?)", (cid, cpl_id))
    conn.commit()
    _db.log(conn, "Simpan CPMK", f"{kode} ({len(cpl_ids)} CPL dipetakan)")
    flash(f"{kode} disimpan dengan {len(cpl_ids)} pemetaan CPL.", "ok")
    return redirect(url_for("kurikulum.index", tab="pemetaan", mk=mk_id))


@bp.route("/cpmk/<int:cid>/hapus", methods=["POST"])
def hapus_cpmk(cid):
    conn = current_app.get_db()
    row = conn.execute(
        "SELECT cpmk.*, mk.kurikulum_id AS kurikulum_id FROM cpmk "
        "JOIN mata_kuliah mk ON mk.id = cpmk.mata_kuliah_id WHERE cpmk.id=?",
        (cid,),
    ).fetchone()
    mk_id = row["mata_kuliah_id"] if row else None
    if row:
        terkunci = _kurikulum_terkunci(conn, row["kurikulum_id"])
        if terkunci:
            flash(
                f'CPMK "{row["kode"]}" tidak bisa dihapus — kurikulum induknya ({terkunci}) sudah '
                "tidak boleh diubah strukturnya. Gunakan Clone Version untuk membuat versi Draft "
                "baru kalau memang perlu revisi struktural.",
                "error",
            )
            return redirect(url_for("kurikulum.index", tab="pemetaan", mk=mk_id))
    conn.execute("DELETE FROM cpmk WHERE id=?", (cid,))
    conn.commit()
    if row:
        _db.log(conn, "Hapus CPMK", row["kode"])
    flash("CPMK dihapus.", "ok")
    return redirect(url_for("kurikulum.index", tab="pemetaan", mk=mk_id))


@bp.route("/subcpmk/simpan", methods=["POST"])
def simpan_sub_cpmk():
    conn = current_app.get_db()
    f = request.form
    cpmk_id = f.get("cpmk_id", type=int)
    sid = f.get("id", type=int)
    kode = f.get("kode", "").strip()
    deskripsi = f.get("deskripsi", "").strip()
    mk_id = f.get("mk_id", type=int)

    if not cpmk_id:
        flash("CPMK induk tidak ditemukan.", "error")
        return redirect(url_for("kurikulum.index", tab="pemetaan", mk=mk_id))
    if not kode or not deskripsi:
        flash("Kode dan deskripsi Sub-CPMK wajib diisi.", "error")
        return redirect(url_for("kurikulum.index", tab="pemetaan", mk=mk_id, cpmk=cpmk_id))

    cpmk_row = conn.execute(
        "SELECT mk.kurikulum_id AS kurikulum_id FROM cpmk "
        "JOIN mata_kuliah mk ON mk.id = cpmk.mata_kuliah_id WHERE cpmk.id=?",
        (cpmk_id,),
    ).fetchone()
    terkunci = _kurikulum_terkunci(conn, cpmk_row["kurikulum_id"]) if cpmk_row else None
    if terkunci:
        flash(
            f"Sub-CPMK tidak bisa disimpan — kurikulum induknya ({terkunci}) sudah tidak boleh "
            "diubah strukturnya. Gunakan Clone Version untuk membuat versi Draft baru kalau memang "
            "perlu revisi struktural.",
            "error",
        )
        return redirect(url_for("kurikulum.index", tab="pemetaan", mk=mk_id, cpmk=cpmk_id))

    if sid:
        conn.execute(
            "UPDATE sub_cpmk SET kode=?, deskripsi=?, urutan=? WHERE id=?",
            (kode, deskripsi, f.get("urutan", type=int) or 0, sid),
        )
        flash(f"{kode} diperbarui.", "ok")
    else:
        conn.execute(
            "INSERT INTO sub_cpmk(cpmk_id, kode, deskripsi, urutan) VALUES(?,?,?,?)",
            (cpmk_id, kode, deskripsi, f.get("urutan", type=int) or 0),
        )
        flash(f"{kode} ditambahkan.", "ok")
    conn.commit()
    _db.log(conn, "Simpan Sub-CPMK", kode)
    return redirect(url_for("kurikulum.index", tab="pemetaan", mk=mk_id, cpmk=cpmk_id))


@bp.route("/subcpmk/<int:sid>/hapus", methods=["POST"])
def hapus_sub_cpmk(sid):
    conn = current_app.get_db()
    f = request.form
    mk_id = f.get("mk_id", type=int)
    cpmk_id = f.get("cpmk_id", type=int)
    row = conn.execute(
        "SELECT sub_cpmk.*, mk.kurikulum_id AS kurikulum_id FROM sub_cpmk "
        "JOIN cpmk ON cpmk.id = sub_cpmk.cpmk_id "
        "JOIN mata_kuliah mk ON mk.id = cpmk.mata_kuliah_id WHERE sub_cpmk.id=?",
        (sid,),
    ).fetchone()
    if row:
        terkunci = _kurikulum_terkunci(conn, row["kurikulum_id"])
        if terkunci:
            flash(
                f'Sub-CPMK "{row["kode"]}" tidak bisa dihapus — kurikulum induknya ({terkunci}) '
                "sudah tidak boleh diubah strukturnya. Gunakan Clone Version untuk membuat versi "
                "Draft baru kalau memang perlu revisi struktural.",
                "error",
            )
            return redirect(url_for("kurikulum.index", tab="pemetaan", mk=mk_id, cpmk=cpmk_id))
    conn.execute("DELETE FROM sub_cpmk WHERE id=?", (sid,))
    conn.commit()
    if row:
        _db.log(conn, "Hapus Sub-CPMK", row["kode"])
    flash("Sub-CPMK dihapus.", "ok")
    return redirect(url_for("kurikulum.index", tab="pemetaan", mk=mk_id, cpmk=cpmk_id))


@bp.route("/rps/<int:mid>/update", methods=["POST"])
def update_rps(mid):
    conn = current_app.get_db()
    f = request.form
    row = conn.execute("SELECT * FROM mata_kuliah WHERE id=?", (mid,)).fetchone()
    if not row:
        abort(404)

    rps_status = f.get("rps_status", "Belum Disusun")
    if rps_status not in C.STATUS_RPS_LIST:
        rps_status = "Belum Disusun"
    rps_revisi = f.get("rps_revisi", "").strip()
    rps_tanggal_sahkan = f.get("rps_tanggal_sahkan", "").strip()

    file = request.files.get("rps_file")
    file_path = row["rps_file"]
    file_nama_asli = row["rps_nama_file_asli"]
    if file and file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in C.EKSTENSI_RPS_DIIZINKAN:
            flash(f"Format .{ext} tidak diizinkan untuk RPS. Gunakan PDF/DOC/DOCX.", "error")
            return redirect(url_for("kurikulum.index", tab="rps"))
        if row["rps_file"] and os.path.exists(row["rps_file"]):
            try:
                os.remove(row["rps_file"])
            except OSError:
                pass
        nama_asli = secure_filename(file.filename)
        nama_unik = f"{uuid.uuid4().hex[:12]}_{nama_asli}"
        file_path = os.path.join(_folder(), nama_unik)
        file.save(file_path)
        file_nama_asli = nama_asli

    conn.execute(
        "UPDATE mata_kuliah SET rps_status=?, rps_revisi=?, rps_tanggal_sahkan=?, "
        "rps_file=?, rps_nama_file_asli=? WHERE id=?",
        (rps_status, rps_revisi, rps_tanggal_sahkan, file_path, file_nama_asli, mid),
    )
    conn.commit()
    _db.log(conn, "Update Status RPS", f"{row['kode']} -> {rps_status}")
    flash(f"Status RPS {row['kode']} diperbarui menjadi '{rps_status}'.", "ok")
    return redirect(url_for("kurikulum.index", tab="rps"))


@bp.route("/rps/<int:mid>/unduh")
def unduh_rps(mid):
    conn = current_app.get_db()
    row = conn.execute("SELECT * FROM mata_kuliah WHERE id=?", (mid,)).fetchone()
    if not row or not row["rps_file"] or not os.path.exists(row["rps_file"]):
        abort(404)
    return send_file(
        row["rps_file"],
        as_attachment=True,
        download_name=row["rps_nama_file_asli"] or f"RPS_{row['kode']}",
    )
