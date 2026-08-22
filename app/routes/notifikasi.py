# -*- coding: utf-8 -*-
"""routes/notifikasi.py — Pusat Notifikasi (Audit Lanjutan 3).

Sebelumnya reminder tersebar di tiap modul & Dashboard (get_notifikasi(),
acara_mendatang(), _hitung_reminder() per-dosen di sdm_detail, dan reminder
lintas-dosen Tri Dharma/Kerja Sama/AMI yang cuma tampil sebagai angka
ringkasan di kartu Dashboard). Modul ini TIDAK mengganti sumber data —
setiap fungsi di atas tetap satu-satunya sumber kebenaran & tetap dipakai
apa adanya (dashboard.py tidak diubah) — modul ini hanya mengumpulkan
semuanya jadi satu daftar & satu tempat mengatur ambang harinya, sesuai
deskripsi placeholder roadmap.py yang digantikan.
"""

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from app import constants as C
from app import db as _db
from app import logic as L
from app.routes.kalender import acara_mendatang

bp = Blueprint("notifikasi", __name__, url_prefix="/notifikasi")


def _ambang(conn, key, default):
    """Ambang hari per kategori — dibaca dari `pengaturan` (bisa ditimpa
    lewat form di halaman ini), jatuh ke konstanta baku fungsi asal kalau
    belum pernah diisi/di-reset."""
    v = _db.get_setting(conn, key, "")
    try:
        return int(v) if v != "" else default
    except (TypeError, ValueError):
        return default


def kumpulkan(conn):
    """Menggabungkan semua sumber reminder/peringatan yang sudah ada di
    SIMPRODI jadi satu daftar ternormalisasi: {kategori, level, judul,
    detail, sisa_hari (opsional), url}. level: info/warning/danger/ok."""
    out = []

    # 1) Peringatan operasional umum (sudah dipakai di Dashboard apa adanya)
    for n in L.get_notifikasi(conn):
        # Audit poin 5 — filter berdasarkan level "ok" (kontrak eksplisit
        # get_notifikasi(), lihat logic.py), BUKAN mencocokkan teks judul
        # placeholder secara harfiah. Filter berbasis string diam-diam
        # gagal kalau kalimat placeholder-nya berubah sedikit saja nanti.
        if n["level"] == "ok":
            continue  # placeholder "aman" milik get_notifikasi, tidak relevan di sini
        out.append(
            {
                "kategori": "Operasional",
                "level": n["level"],
                "judul": n["judul"],
                "detail": n["detail"],
                "sisa_hari": None,
                "url": None,
            }
        )

    # 2) Agenda kalender akademik mendatang
    hari_agenda = int(_db.get_setting(conn, "pref_agenda_hari", "7") or 7)
    for a in acara_mendatang(conn, hari=hari_agenda):
        out.append(
            {
                "kategori": "Agenda Kalender",
                "level": "info",
                "judul": a["judul"],
                "detail": f"{a['kategori']}"
                + (f" · {a['jam']}" if a["jam"] else "")
                + f" · {a['tgl_mulai']}",
                "sisa_hari": None,
                "url": url_for("kalender.index"),
            }
        )

    # 3) SDM — masa berlaku sertifikat/peran akademik (lintas semua dosen)
    ambang_sdm = _ambang(conn, "notif_ambang_sdm", C.REMINDER_MASA_BERLAKU_HARI)
    for r in L.sdm_reminder_semua(conn, ambang_hari=ambang_sdm):
        out.append(
            {
                "kategori": "SDM — Masa Berlaku",
                "level": "danger" if r["sisa_hari"] < 0 else "warning",
                "judul": f"{r['nama']} ({r['dosen_nama']})",
                "detail": f"{r['status']} · {r['tgl']} · {abs(r['sisa_hari'])} hari",
                "sisa_hari": r["sisa_hari"],
                "url": url_for("sdm.index"),
            }
        )

    # 4) Tri Dharma — tenggat laporan hibah penelitian/PKM
    ambang_tri = _ambang(conn, "notif_ambang_tridharma", C.AMBANG_TENGGAT_LAPORAN_HARI)
    for r in L.tridharma_reminder_tenggat(conn, ambang_hari=ambang_tri):
        out.append(
            {
                "kategori": "Tri Dharma — Tenggat Laporan",
                "level": "danger" if r["sisa_hari"] < 0 else "warning",
                "judul": f"{r['judul']} ({r['dosen_nama']})",
                "detail": f"{r['jenis']} · {r['status']} · {r['tenggat']}",
                "sisa_hari": r["sisa_hari"],
                "url": url_for("tridharma.index"),
            }
        )

    # 5) Kerja Sama — dokumen MoU/MoA/IA
    ambang_mitra = _ambang(conn, "notif_ambang_mitra", C.AMBANG_KADALUARSA_MOU_HARI)
    for r in L.mitra_reminder_dokumen(conn, ambang_hari=ambang_mitra):
        out.append(
            {
                "kategori": "Kerja Sama — Dokumen",
                "level": "danger" if r["sisa_hari"] < 0 else "warning",
                "judul": f"{r['judul']} ({r['mitra_nama']})",
                "detail": f"{r['jenis_dokumen']} · {r['status']} · {r['tgl_berakhir']}",
                "sisa_hari": r["sisa_hari"],
                "url": url_for("kerjasama.index"),
            }
        )

    # 6) Mutu — tenggat tindak lanjut temuan AMI
    ambang_ami = _ambang(conn, "notif_ambang_ami", 14)
    for r in L.ami_reminder_tenggat(conn, ambang_hari=ambang_ami):
        out.append(
            {
                "kategori": "Mutu — Temuan AMI",
                "level": "danger" if r["sisa_hari"] < 0 else "warning",
                "judul": r["uraian"],
                "detail": f"{r['siklus_nama']} · {r['status']} · PIC: {r['pic_nama'] or '-'} · {r['tenggat']}",
                "sisa_hari": r["sisa_hari"],
                "url": url_for("mutu.index", tab="audit"),
            }
        )

    urutan_level = {"danger": 0, "warning": 1, "info": 2, "ok": 3}
    out.sort(
        key=lambda x: (
            urutan_level.get(x["level"], 9),
            x["sisa_hari"] if x["sisa_hari"] is not None else 0,
        )
    )
    return out


def kumpulkan_cached(conn):
    """Audit poin 3 — cache per-request (flask.g) untuk kumpulkan().

    kumpulkan() menjalankan ±6 query lintas modul (termasuk
    rekap_rasio_dosen() di semua dosen lewat get_notifikasi()). Tanpa cache,
    fungsi ini bisa terpanggil berkali-kali dalam satu request yang sama —
    misalnya di halaman /notifikasi/ sendiri: sekali di index() untuk
    "semua", sekali lagi di hitung_ringkasan() (dipanggil manual oleh
    index()), dan sekali lagi lewat context processor global
    (app/__init__.py inject_globals). g dibersihkan otomatis oleh Flask di
    akhir tiap request, jadi tidak ada risiko data basi antar-request."""
    if "notif_kumpulan_cache" not in g:
        g.notif_kumpulan_cache = kumpulkan(conn)
    return g.notif_kumpulan_cache


def hitung_ringkasan(conn):
    """Ringkasan jumlah per level — dipakai badge lonceng di topbar
    (app/__init__.py inject_globals), murni membaca ulang kumpulkan()
    (lewat cache per-request, lihat kumpulkan_cached)."""
    data = kumpulkan_cached(conn)
    danger = len([d for d in data if d["level"] == "danger"])
    warning = len([d for d in data if d["level"] == "warning"])
    return {
        "total": len(data),
        "danger": danger,
        "warning": warning,
        "perlu_perhatian": danger + warning,
    }


@bp.route("/", methods=["GET", "POST"])
def index():
    conn = current_app.get_db()

    if request.method == "POST":
        # Audit poin 4 — validasi ambang sebelumnya HANYA di client (atribut
        # min="1" max="365" pada <input> di notifikasi.html); sisi server
        # cuma cek .isdigit(), jadi POST langsung (mis. notif_ambang_
        # tridharma=999999) tersimpan tanpa batas dan bisa membanjiri
        # daftar notifikasi dengan item yang temponya sebenarnya masih jauh.
        # Sekarang rentang 1..365 ditegakkan juga di server; field dengan
        # nilai di luar rentang/non-angka dilewati (nilai lama dipertahankan)
        # dan pengguna diberi tahu lewat flash.
        ada_tidak_valid = False
        for key, _label, _default in C.NOTIF_AMBANG_FIELDS:
            nilai = request.form.get(key, "").strip()
            if nilai.isdigit() and C.NOTIF_AMBANG_MIN <= int(nilai) <= C.NOTIF_AMBANG_MAX:
                _db.set_setting(conn, key, nilai)
            else:
                ada_tidak_valid = True
        _db.log(conn, "Ubah Ambang Pusat Notifikasi")
        if ada_tidak_valid:
            flash(
                f"Sebagian ambang tidak disimpan — nilai harus berupa angka bulat "
                f"antara {C.NOTIF_AMBANG_MIN} dan {C.NOTIF_AMBANG_MAX} hari.",
                "error",
            )
        else:
            flash("Ambang notifikasi tersimpan.", "ok")
        return redirect(url_for("notifikasi.index"))

    semua = kumpulkan_cached(conn)

    kategori_filter = request.args.get("kategori", "")
    level_filter = request.args.get("level", "")
    tampil = semua
    if kategori_filter:
        tampil = [d for d in tampil if d["kategori"] == kategori_filter]
    if level_filter:
        tampil = [d for d in tampil if d["level"] == level_filter]

    kategori_list = sorted({d["kategori"] for d in semua})
    ambang_nilai = {
        key: _ambang(conn, key, default) for key, _label, default in C.NOTIF_AMBANG_FIELDS
    }

    return render_template(
        "pengaturan/notifikasi.html",
        semua=semua,
        tampil=tampil,
        kategori_list=kategori_list,
        kategori_filter=kategori_filter,
        level_filter=level_filter,
        ringkasan=hitung_ringkasan(conn),
        NOTIF_AMBANG_FIELDS=C.NOTIF_AMBANG_FIELDS,
        ambang_nilai=ambang_nilai,
    )
