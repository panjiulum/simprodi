# -*- coding: utf-8 -*-
"""
routes/sdm.py — Modul SDM & Kinerja Dosen.

Menggantikan checklist Kinerja Dosen sederhana milik POM lama secara total
(lihat rancangan-final-modul-sdm-kinerja-dosen.md). Delapan tabel di db.py
(aktivitas_pendidikan/penelitian/pkm/penunjang, luaran_dosen,
peran_akademik_dosen, timeline_karier_dosen, target_kinerja_dosen) memiliki
bentuk yang serupa (log per-dosen dengan beberapa kolom teks), jadi CRUD-nya
ditulis SEKALI secara generik lewat TABEL_CONFIG di bawah, bukan diulang
8 kali — supaya konsisten & mudah dirawat saat kolom bertambah nanti.

Realisasi Target Kinerja & Dashboard Kesiapan SENGAJA dihitung on-the-fly
tiap halaman dibuka (bukan disimpan statis), sesuai keputusan di rancangan,
supaya tidak pernah basi seperti rumus Excel yang bisa lupa di-refresh.
"""

from datetime import date, datetime

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

bp = Blueprint("sdm", __name__, url_prefix="/sdm")

# ---------------------------------------------------------------------------
# Konfigurasi generik: 1 entri per tabel log. `fields` = urutan kolom form
# (selain id & dosen_id), tipe 'text'/'textarea'/'select'/'number'.
# ---------------------------------------------------------------------------
TABEL_CONFIG = {
    "pendidikan": {
        "table": "aktivitas_pendidikan",
        "label": "Pendidikan & Pengajaran",
        "judul_field": "mata_kuliah",
        "fields": [
            ("periode_akademik_id", "Periode Akademik", "periode"),
            ("mata_kuliah", "Mata Kuliah *", "text"),
            ("kode_mk", "Kode MK", "text"),
            ("sks", "SKS", "text"),
            ("jumlah_kelas", "Jumlah Kelas", "text"),
            ("jumlah_mahasiswa", "Jumlah Mahasiswa", "text"),
            ("peran", "Peran", "text"),
            ("status", "Status", "select", C.STATUS_AKTIVITAS_SDM_LIST),
            ("catatan", "Catatan", "textarea"),
        ],
        "kolom_tabel": ["tahun_akademik", "semester", "mata_kuliah", "sks", "status"],
    },
    "penelitian": {
        "table": "aktivitas_penelitian",
        "label": "Penelitian",
        "judul_field": "judul",
        "kode_prefix": "PEN",
        "fields": [
            ("judul", "Judul *", "text"),
            ("skema", "Skema", "select", C.SKEMA_PENELITIAN_PKM_LIST),
            ("sumber_dana", "Sumber Dana", "select", C.SUMBER_DANA_LIST),
            ("nominal", "Nominal", "number"),
            ("pelaksana", "Pelaksana", "text"),
            ("periode_akademik_id", "Periode Akademik", "periode"),
            ("tgl_publish", "Tgl Publish", "text"),
            ("jurnal", "Jurnal", "text"),
            ("jilid", "Jilid", "text"),
            ("volume", "Vol", "text"),
            ("halaman", "Halaman", "text"),
            ("status", "Status", "select", C.STATUS_AKTIVITAS_SDM_LIST),
            ("jenis_luaran", "Jenis Luaran", "select", C.JENIS_LUARAN_LIST),
            ("doi", "DOI", "text"),
            ("issn_isbn", "ISSN/ISBN", "text"),
            ("url", "URL", "text"),
            ("lokasi_bukti", "Lokasi Bukti", "text"),
            ("catatan", "Catatan", "textarea"),
        ],
        "kolom_tabel": ["kode", "judul", "tahun_akademik", "jenis_luaran", "status"],
    },
    "pkm": {
        "table": "aktivitas_pkm",
        "label": "Pengabdian Masyarakat (PKM)",
        "judul_field": "judul",
        "kode_prefix": "PKM",
        "fields": [
            ("judul", "Judul *", "text"),
            ("jenis", "Jenis", "text"),
            ("skema", "Skema", "select", C.SKEMA_PENELITIAN_PKM_LIST),
            ("lokasi", "Lokasi", "text"),
            ("mitra", "Mitra", "text"),
            ("dana", "Dana", "number"),
            ("periode_akademik_id", "Periode Akademik", "periode"),
            ("status", "Status", "select", C.STATUS_AKTIVITAS_SDM_LIST),
            ("jenis_luaran", "Jenis Luaran", "select", C.JENIS_LUARAN_LIST),
            ("url", "URL", "text"),
            ("lokasi_bukti", "Lokasi Bukti", "text"),
            ("catatan", "Catatan", "textarea"),
        ],
        "kolom_tabel": ["kode", "judul", "tahun_akademik", "jenis_luaran", "status"],
    },
    "penunjang": {
        "table": "aktivitas_penunjang",
        "label": "Penunjang",
        "judul_field": "nama_kegiatan",
        "fields": [
            ("jenis_penunjang", "Jenis Penunjang", "text"),
            ("nama_kegiatan", "Nama Kegiatan/Instansi *", "text"),
            ("peran", "Peran", "text"),
            ("tanggal", "Tanggal", "text"),
            ("periode_akademik_id", "Periode Akademik", "periode"),
            ("status", "Status", "select", C.STATUS_AKTIVITAS_SDM_LIST),
            ("url", "URL", "text"),
            ("lokasi_bukti", "Lokasi Bukti", "text"),
            ("catatan", "Catatan", "textarea"),
        ],
        "kolom_tabel": ["jenis_penunjang", "nama_kegiatan", "tahun_akademik", "status"],
    },
    "luaran": {
        "table": "luaran_dosen",
        "label": "Luaran (Publikasi/HKI/Buku/dst)",
        "judul_field": "judul",
        "kode_prefix": "LUR",
        "fields": [
            ("jenis_luaran", "Jenis Luaran *", "select", C.JENIS_LUARAN_LIST),
            ("judul", "Judul/Nama *", "text"),
            ("penulis_terkait", "Penulis/Pihak Terkait", "text"),
            ("periode_akademik_id", "Periode Akademik", "periode"),
            ("nomor_identitas", "DOI/ISSN/ISBN/No.HKI/No.Sertifikat", "text"),
            ("penerbit_instansi", "Penerbit/Instansi", "text"),
            ("sumber_dana", "Sumber Dana", "select", C.SUMBER_DANA_LIST),
            ("status", "Status", "select", C.STATUS_AKTIVITAS_SDM_LIST),
            ("masa_berlaku", "Masa Berlaku (khusus Sertifikat, format YYYY-MM-DD)", "text"),
            ("url", "URL", "text"),
            ("lokasi_bukti", "Lokasi Bukti", "text"),
            ("keterangan_tambahan", "Keterangan Tambahan (peran/tingkat/dll)", "text"),
            ("catatan", "Catatan", "textarea"),
        ],
        "kolom_tabel": ["kode", "jenis_luaran", "judul", "tahun_akademik", "status"],
    },
    "peran_akademik": {
        "table": "peran_akademik_dosen",
        "label": "Peran Akademik",
        "judul_field": "nama_instansi_kegiatan",
        "fields": [
            ("jenis_peran", "Jenis Peran *", "select", C.JENIS_PERAN_AKADEMIK_LIST),
            ("nama_instansi_kegiatan", "Nama Instansi/Kegiatan *", "text"),
            ("peran_jabatan", "Peran/Jabatan", "text"),
            ("tgl_mulai", "Tgl Mulai", "text"),
            ("tgl_selesai", "Tgl Selesai / Masa Berlaku", "text"),
            ("periode_akademik_id", "Periode Akademik", "periode"),
            ("status", "Status", "select", C.STATUS_AKTIVITAS_SDM_LIST),
            ("url", "URL", "text"),
            ("lokasi_bukti", "Lokasi Bukti", "text"),
            ("catatan", "Catatan", "textarea"),
        ],
        "kolom_tabel": [
            "jenis_peran",
            "nama_instansi_kegiatan",
            "tgl_mulai",
            "tgl_selesai",
            "status",
        ],
    },
    "timeline": {
        "table": "timeline_karier_dosen",
        "label": "Timeline Karier",
        "judul_field": "keterangan",
        "fields": [
            ("jenis_perubahan", "Jenis Perubahan *", "select", C.JENIS_PERUBAHAN_KARIER_LIST),
            ("keterangan", "Keterangan/Nama *", "text"),
            ("no_sk", "Nomor SK", "text"),
            ("tgl_mulai", "Tgl Mulai", "text"),
            ("tgl_berakhir_target", "Tgl Berakhir/Target Berikutnya", "text"),
            ("instansi_penerbit", "Instansi Penerbit", "text"),
            ("status", "Status", "select", C.STATUS_AKTIVITAS_SDM_LIST),
            ("lokasi_bukti", "Lokasi Bukti", "text"),
            ("catatan", "Catatan", "textarea"),
        ],
        "kolom_tabel": ["jenis_perubahan", "keterangan", "tgl_mulai", "status"],
    },
    "target": {
        "table": "target_kinerja_dosen",
        "label": "Target Kinerja Tahunan",
        "judul_field": "kategori",
        "fields": [
            ("tahun", "Tahun *", "number"),
            ("kategori", "Kategori *", "select", C.KATEGORI_TARGET_KINERJA_LIST),
            ("target_angka", "Target", "number"),
            ("keterangan", "Keterangan", "textarea"),
        ],
        "kolom_tabel": ["tahun", "kategori", "target_angka"],
    },
}

STATUS_SELESAI = {"Selesai", "Completed", "Published"}


def _generate_kode(conn, table, prefix, tahun_akademik):
    """Format sama dgn workbook asal: PEN-2026-003 (tahun dari tahun_akademik,
    urut per-prefix+tahun, dihitung dari jumlah baris yg sudah ada +1)."""
    tahun = "XXXX"
    if tahun_akademik:
        tahun = str(tahun_akademik).split("/")[0].strip() or "XXXX"
    n = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE kode LIKE ?", (f"{prefix}-{tahun}-%",)
    ).fetchone()[0]
    return f"{prefix}-{tahun}-{n + 1:03d}"


def _hitung_kesiapan(conn, dosen_id):
    """Kesiapan BKD: rasio aktivitas (Pendidikan/Penelitian/PKM/Penunjang)
    berstatus selesai. Kesiapan SISTER: rasio luaran & penelitian/PKM
    berstatus selesai. Lihat rancangan §'Dashboard Kesiapan'."""
    total_bkd = selesai_bkd = 0
    for t in (
        "aktivitas_pendidikan",
        "aktivitas_penelitian",
        "aktivitas_pkm",
        "aktivitas_penunjang",
    ):
        rows = conn.execute(f"SELECT status FROM {t} WHERE dosen_id=?", (dosen_id,)).fetchall()
        total_bkd += len(rows)
        selesai_bkd += sum(1 for r in rows if r["status"] in STATUS_SELESAI)

    total_sister = selesai_sister = 0
    for t in ("luaran_dosen", "aktivitas_penelitian", "aktivitas_pkm"):
        rows = conn.execute(f"SELECT status FROM {t} WHERE dosen_id=?", (dosen_id,)).fetchall()
        total_sister += len(rows)
        selesai_sister += sum(1 for r in rows if r["status"] in STATUS_SELESAI)

    kesiapan_bkd = round(100 * selesai_bkd / total_bkd) if total_bkd else 0
    kesiapan_sister = round(100 * selesai_sister / total_sister) if total_sister else 0
    return kesiapan_bkd, kesiapan_sister


def _hitung_reminder(conn, dosen_id):
    """Reminder Masa Berlaku: sertifikat (luaran_dosen.masa_berlaku) &
    peran akademik dgn tgl_selesai (Jabatan/Organisasi Profesi/dst)."""
    today = date.today()
    out = []

    def _parse(s):
        try:
            return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    rows = conn.execute(
        "SELECT judul AS nama, masa_berlaku AS tgl FROM luaran_dosen "
        "WHERE dosen_id=? AND masa_berlaku IS NOT NULL AND masa_berlaku!=''",
        (dosen_id,),
    ).fetchall()
    rows += conn.execute(
        "SELECT nama_instansi_kegiatan AS nama, tgl_selesai AS tgl FROM peran_akademik_dosen "
        "WHERE dosen_id=? AND tgl_selesai IS NOT NULL AND tgl_selesai!=''",
        (dosen_id,),
    ).fetchall()

    for r in rows:
        d = _parse(r["tgl"])
        if not d:
            continue
        sisa = (d - today).days
        if sisa < 0:
            status = "Kadaluarsa"
        elif sisa <= C.REMINDER_MASA_BERLAKU_HARI:
            status = "Segera Berakhir"
        else:
            continue  # aman, tidak perlu ditampilkan sebagai reminder
        out.append({"nama": r["nama"], "tgl": r["tgl"], "sisa_hari": sisa, "status": status})
    out.sort(key=lambda x: x["sisa_hari"])
    return out


@bp.route("/")
def index():
    conn = current_app.get_db()
    dosen_list = conn.execute("SELECT * FROM dosen WHERE aktif=1 ORDER BY nama").fetchall()
    ringkasan = []
    for d in dosen_list:
        kesiapan_bkd, kesiapan_sister = _hitung_kesiapan(conn, d["id"])
        n_luaran = conn.execute(
            "SELECT COUNT(*) FROM luaran_dosen WHERE dosen_id=?", (d["id"],)
        ).fetchone()[0]
        n_reminder = len(_hitung_reminder(conn, d["id"]))
        ringkasan.append(
            {
                "dosen": d,
                "kesiapan_bkd": kesiapan_bkd,
                "kesiapan_sister": kesiapan_sister,
                "n_luaran": n_luaran,
                "n_reminder": n_reminder,
                "status_homebase": d["status_homebase"] or "Homebase",
            }
        )
    # Audit poin 3: dashboard BKD/SISTER dipisah Homebase vs Dosen Luar —
    # supaya laporan kinerja tidak tercampur antara yang jadi tanggung jawab
    # penuh prodi dan yang cuma numpang mengajar/membimbing.
    ringkasan_homebase = [r for r in ringkasan if r["status_homebase"] == "Homebase"]
    ringkasan_luar = [r for r in ringkasan if r["status_homebase"] != "Homebase"]
    return render_template(
        "sdm_index.html",
        ringkasan=ringkasan,
        ringkasan_homebase=ringkasan_homebase,
        ringkasan_luar=ringkasan_luar,
    )


# Tabel log yang punya kolom `periode_akademik_id` (Audit poin 1, tindak
# lanjut): dropdown "Periode Akademik" di form-nya harus benar-benar
# menulis FK ini, bukan cuma kolom cache tahun_akademik/semester TEXT.
_TAB_PAKAI_PERIODE = {"pendidikan", "penelitian", "pkm", "penunjang", "luaran", "peran_akademik"}


@bp.route("/<int:dosen_id>")
def detail(dosen_id):
    conn = current_app.get_db()
    dosen = conn.execute("SELECT * FROM dosen WHERE id=?", (dosen_id,)).fetchone()
    if not dosen:
        flash("Dosen tidak ditemukan.", "error")
        return redirect(url_for("sdm.index"))

    tab = request.args.get("tab", "pendidikan")
    if tab not in TABEL_CONFIG:
        tab = "pendidikan"
    cfg = TABEL_CONFIG[tab]
    rows = conn.execute(
        f"SELECT * FROM {cfg['table']} WHERE dosen_id=? ORDER BY id DESC", (dosen_id,)
    ).fetchall()

    edit_id = request.args.get("edit", type=int)
    edit_row = None
    if edit_id:
        edit_row = conn.execute(
            f"SELECT * FROM {cfg['table']} WHERE id=? AND dosen_id=?", (edit_id, dosen_id)
        ).fetchone()

    kesiapan_bkd, kesiapan_sister = _hitung_kesiapan(conn, dosen_id)
    reminder = _hitung_reminder(conn, dosen_id)

    # Target Kinerja: realisasi dihitung on-the-fly (bukan kolom statis)
    target_realisasi = []
    if tab == "target":
        for r in rows:
            realisasi = conn.execute(
                "SELECT COUNT(*) FROM luaran_dosen WHERE dosen_id=? AND jenis_luaran=? AND tahun_akademik LIKE ?",
                (dosen_id, r["kategori"], f"%{r['tahun']}%"),
            ).fetchone()[0]
            capaian = round(100 * realisasi / r["target_angka"]) if r["target_angka"] else None
            target_realisasi.append({"row": r, "realisasi": realisasi, "capaian": capaian})

    daftar_periode = _db.get_periode_list(conn) if tab in _TAB_PAKAI_PERIODE else []

    return render_template(
        "sdm_detail.html",
        dosen=dosen,
        tab=tab,
        cfg=cfg,
        tabs=TABEL_CONFIG,
        rows=rows,
        edit_row=edit_row,
        kesiapan_bkd=kesiapan_bkd,
        kesiapan_sister=kesiapan_sister,
        reminder=reminder,
        target_realisasi=target_realisasi,
        daftar_periode=daftar_periode,
    )


@bp.route("/<int:dosen_id>/<jenis>/simpan", methods=["POST"])
def simpan(dosen_id, jenis):
    if jenis not in TABEL_CONFIG:
        flash("Jenis data tidak dikenali.", "error")
        return redirect(url_for("sdm.index"))
    cfg = TABEL_CONFIG[jenis]
    conn = current_app.get_db()
    f = request.form
    item_id = f.get("id", type=int)
    col_names = [fld[0] for fld in cfg["fields"]]

    judul_val = f.get(cfg["judul_field"], "").strip()
    if not judul_val:
        flash("Field wajib (bertanda *) belum diisi.", "error")
        return redirect(url_for("sdm.detail", dosen_id=dosen_id, tab=jenis))

    values = []
    for name, _label, ftype, *_opts in cfg["fields"]:
        if ftype == "periode":
            v = f.get(name, type=int)
        elif ftype == "number":
            v = f.get(name, "").strip() or 0
        else:
            v = f.get(name, "").strip()
        values.append(v)

    # Dropdown "Periode Akademik" (Audit poin 1, tindak lanjut) adalah
    # sumber kebenaran baru — begitu dipilih, kolom cache TEXT lama
    # (tahun_akademik/semester, masih dipakai filter & rekap yang sudah
    # ada) diturunkan otomatis dari situ, bukan diketik manual lagi.
    ta_cache = sem_cache = ""
    if "periode_akademik_id" in col_names:
        periode_id = values[col_names.index("periode_akademik_id")]
        ta_cache, sem_cache = _db.cache_periode(conn, periode_id)

    try:
        if item_id:
            set_clause = ", ".join(f"{c}=?" for c in col_names)
            upd_values = list(values)
            if "periode_akademik_id" in col_names:
                set_clause += ", tahun_akademik=?, semester=?"
                upd_values += [ta_cache, sem_cache]
            conn.execute(
                f"UPDATE {cfg['table']} SET {set_clause} WHERE id=? AND dosen_id=?",
                (*upd_values, item_id, dosen_id),
            )
            _db.log(conn, f"Update {cfg['label']}", judul_val)
            flash("Data diperbarui.", "ok")
        else:
            insert_cols = list(col_names)
            insert_vals = list(values)
            if "periode_akademik_id" in col_names:
                insert_cols += ["tahun_akademik", "semester"]
                insert_vals += [ta_cache, sem_cache]
            if "kode_prefix" in cfg:
                kode = _generate_kode(conn, cfg["table"], cfg["kode_prefix"], ta_cache)
                insert_cols = ["kode"] + insert_cols
                insert_vals = [kode] + insert_vals
            insert_cols = ["dosen_id"] + insert_cols
            insert_vals = [dosen_id] + insert_vals
            placeholders = ", ".join("?" for _ in insert_vals)
            conn.execute(
                f"INSERT INTO {cfg['table']}({', '.join(insert_cols)}) VALUES({placeholders})",
                insert_vals,
            )
            _db.log(conn, f"Tambah {cfg['label']}", judul_val)
            flash("Data ditambahkan.", "ok")
        conn.commit()
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan")
    return redirect(url_for("sdm.detail", dosen_id=dosen_id, tab=jenis))


@bp.route("/<int:dosen_id>/<jenis>/<int:item_id>/hapus", methods=["POST"])
def hapus(dosen_id, jenis, item_id):
    if jenis not in TABEL_CONFIG:
        flash("Jenis data tidak dikenali.", "error")
        return redirect(url_for("sdm.index"))
    cfg = TABEL_CONFIG[jenis]
    conn = current_app.get_db()
    conn.execute(f"DELETE FROM {cfg['table']} WHERE id=? AND dosen_id=?", (item_id, dosen_id))
    conn.commit()
    _db.log(conn, f"Hapus {cfg['label']}", str(item_id))
    flash("Data dihapus.", "ok")
    return redirect(url_for("sdm.detail", dosen_id=dosen_id, tab=jenis))
