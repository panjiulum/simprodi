# -*- coding: utf-8 -*-
"""routes/tridharma.py — Modul 15: Penelitian, PKM & Publikasi/HKI
(Tri Dharma Program Studi).

PENTING (lihat db.py & docs/INTEGRASI_SITIPRO_SIMPRODI.md §10): modul ini
TIDAK menduplikasi data. Aktivitas Penelitian, PKM, dan Luaran (Publikasi/
HKI/Buku/Prosiding) sudah dikelola per-dosen di routes/sdm.py sejak Fase
Fondasi (tabel aktivitas_penelitian, aktivitas_pkm, luaran_dosen). Modul
ini membaca tabel yang SAMA lintas SEMUA dosen sekaligus — nilai tambahnya
adalah rekap & filter tingkat program studi yang secara struktural tidak
bisa didapat dari sdm.py (navigasinya selalu satu dosen per halaman).

Struktur tab diadaptasi dari TriDharma.tsx SITIPRO (Executive Dashboard/
Penelitian & PKM/Luaran Akademik/Pendidikan & Penunjang), dibangun ulang
sebagai agregasi Flask/SQLite sungguhan atas data Modul 4 — tanpa "AI
Publication Advisor"/"AI Gap Analysis" (teks AI-generated di demo asli,
di luar cakupan aplikasi offline, sama seperti keputusan Chatbot §1):

  - dashboard          : stat program studi + sebaran luaran + dosen belum
                          capai target tahun berjalan + reminder tenggat
                          laporan hibah — semua angka riil dari Modul 4.
  - penelitian_pkm     : daftar gabungan Penelitian+PKM lintas dosen, bisa
                          difilter/dicari, + tinjauan institusional
                          (tridharma_tinjauan — SATU-SATUNYA tabel baru
                          modul ini, terpisah dari status self-report
                          dosen). Edit data asli tetap lewat sdm.py.
  - luaran             : daftar luaran_dosen lintas dosen, baca-saja +
                          filter/cari (edit tetap lewat sdm.py).
  - pendidikan_penunjang: rekap aktivitas_pendidikan & aktivitas_penunjang
                          lintas dosen, baca-saja.
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

bp = Blueprint("tridharma", __name__, url_prefix="/tridharma")

_TABS = ("dashboard", "penelitian_pkm", "luaran", "pendidikan_penunjang")


@bp.route("/")
def index():
    conn = current_app.get_db()
    tab = request.args.get("tab", "dashboard")
    if tab not in _TABS:
        tab = "dashboard"

    ctx = {"tab": tab}
    tahun_aktif = _db.get_setting(conn, "tahun_akademik_aktif", "")
    tahun_singkat = L.tahun_dari_tahun_akademik(tahun_aktif)

    if tab == "dashboard":
        ctx["ringkasan"] = L.tridharma_ringkasan(conn, tahun_aktif)
        ctx["sebaran"] = L.tridharma_sebaran_luaran(conn)
        ctx["dosen_belum_target"] = L.tridharma_dosen_belum_target(conn, tahun_singkat)
        ctx["reminder"] = L.tridharma_reminder_tenggat(conn)
        ctx["tahun_singkat"] = tahun_singkat

    elif tab == "penelitian_pkm":
        jenis_filter = request.args.get("jenis", "")
        status_filter = request.args.get("status", "")
        tahun_filter = request.args.get("tahun", "").strip()
        cari = request.args.get("cari", "").strip()
        rows = L.tridharma_daftar_usulan(conn, jenis_filter, status_filter, tahun_filter, cari)
        ctx["rows"] = rows
        ctx["jenis_filter"] = jenis_filter
        ctx["status_filter"] = status_filter
        ctx["tahun_filter"] = tahun_filter
        ctx["cari"] = cari
        ctx["status_aktivitas_list"] = C.STATUS_AKTIVITAS_SDM_LIST
        ctx["status_tinjauan_list"] = C.STATUS_TINJAUAN_TRIDHARMA_LIST

        sel_jenis = request.args.get("item_jenis", "")
        sel_id = request.args.get("item_id", type=int)
        item_terpilih = None
        if sel_jenis and sel_id:
            item_terpilih = next(
                (r for r in rows if r["jenis"] == sel_jenis and r["id"] == sel_id), None
            )
        ctx["item_terpilih"] = item_terpilih

    elif tab == "luaran":
        jenis_filter = request.args.get("jenis", "")
        status_filter = request.args.get("status", "")
        tahun_filter = request.args.get("tahun", "").strip()
        cari = request.args.get("cari", "").strip()
        ctx["rows"] = L.tridharma_daftar_luaran(
            conn, jenis_filter, status_filter, tahun_filter, cari
        )
        ctx["jenis_filter"] = jenis_filter
        ctx["status_filter"] = status_filter
        ctx["tahun_filter"] = tahun_filter
        ctx["cari"] = cari
        ctx["jenis_luaran_list"] = C.JENIS_LUARAN_LIST
        ctx["status_aktivitas_list"] = C.STATUS_AKTIVITAS_SDM_LIST

    elif tab == "pendidikan_penunjang":
        tahun_filter = request.args.get("tahun", "").strip()
        ctx["tahun_filter"] = tahun_filter
        ctx["pendidikan_rows"] = L.tridharma_rekap_pendidikan(conn, tahun_filter)
        ctx["penunjang_rows"] = L.tridharma_rekap_penunjang(conn, tahun_filter)

    return render_template("tridharma.html", **ctx)


@bp.route("/tinjauan/simpan", methods=["POST"])
def simpan_tinjauan():
    """Simpan/perbarui tinjauan institusional 1 usulan Penelitian/PKM.
    Upsert lewat UNIQUE(penelitian_id)/UNIQUE(pkm_id) — tepat satu dari
    keduanya terisi per baris, sesuai jenis usulan yang ditinjau."""
    conn = current_app.get_db()
    f = request.form
    jenis = f.get("jenis")
    item_id = f.get("item_id", type=int)
    if jenis not in ("Penelitian", "PKM") or not item_id:
        flash("Usulan tidak ditemukan.", "error")
        return redirect(url_for("tridharma.index", tab="penelitian_pkm"))

    status_tinjauan = f.get("status_tinjauan", "Belum Ditinjau")
    if status_tinjauan not in C.STATUS_TINJAUAN_TRIDHARMA_LIST:
        status_tinjauan = "Belum Ditinjau"
    col = "penelitian_id" if jenis == "Penelitian" else "pkm_id"

    try:
        conn.execute(
            f"INSERT INTO tridharma_tinjauan({col}, status_tinjauan, catatan_tinjauan, "
            f"tenggat_laporan, tgl_tinjauan, ditinjau_oleh) VALUES(?,?,?,?,?,?) "
            f"ON CONFLICT({col}) DO UPDATE SET status_tinjauan=excluded.status_tinjauan, "
            f"catatan_tinjauan=excluded.catatan_tinjauan, tenggat_laporan=excluded.tenggat_laporan, "
            f"tgl_tinjauan=excluded.tgl_tinjauan, ditinjau_oleh=excluded.ditinjau_oleh",
            (
                item_id,
                status_tinjauan,
                f.get("catatan_tinjauan", "").strip(),
                f.get("tenggat_laporan", "").strip(),
                f.get("tgl_tinjauan", "").strip(),
                f.get("ditinjau_oleh", "").strip(),
            ),
        )
        conn.commit()
        _db.log(conn, "Simpan Tinjauan Tri Dharma", f"{jenis} #{item_id} -> {status_tinjauan}")
        flash("Tinjauan tersimpan.", "ok")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan tinjauan")
    return redirect(
        url_for("tridharma.index", tab="penelitian_pkm", item_jenis=jenis, item_id=item_id)
    )
