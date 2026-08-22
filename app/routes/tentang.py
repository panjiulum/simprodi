# -*- coding: utf-8 -*-
"""routes/tentang.py — Tentang Aplikasi (About).

Sebelumnya menu ini diarahkan ke routes/roadmap.py (placeholder "dalam
pengembangan"). Audit lanjutan (lihat FONDASI.md) menandai halaman ini
sebagai salah satu yang perlu dicek ulang kesesuaiannya — dan kesimpulannya:
informasi yang seharusnya ditampilkan (versi, identitas instansi, status
database, status backup, cakupan modul) semuanya SUDAH tersedia di
aplikasi, hanya belum disatukan jadi satu halaman ringkas. Modul ini murni
read-only — tidak ada tabel baru, tidak ada endpoint yang menulis data —
semua angka diambil langsung dari sumber yang sudah ada (constants.py,
tabel pengaturan, file database, folder backup, dan daftar blueprint yang
sungguh-sungguh terdaftar) supaya halaman ini TIDAK BISA basi seperti teks
statis biasa.
"""

import os

from flask import Blueprint, current_app, render_template

from app import backup_core
from app.routes.roadmap import ROADMAP_MODULES

bp = Blueprint("tentang", __name__, url_prefix="/tentang")


def _ukuran_manusiawi(byte_count):
    for satuan in ("B", "KB", "MB", "GB"):
        if byte_count < 1024:
            return f"{byte_count:.0f} {satuan}" if satuan == "B" else f"{byte_count:.1f} {satuan}"
        byte_count /= 1024
    return f"{byte_count:.1f} TB"


@bp.route("/")
def index():
    conn = current_app.get_db()

    db_path = current_app.config["DB_PATH"]
    ukuran_db = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    jumlah_tabel = conn.execute(
        "SELECT COUNT(*) c FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()["c"]

    ringkasan_data = {}
    for label, tabel in [
        ("Dosen", "dosen"),
        ("Mahasiswa", "mahasiswa"),
        ("Program Kerja", "program_kerja"),
        ("Dokumen", "dokumen"),
        ("Surat Keluar", "surat_keluar"),
    ]:
        try:
            ringkasan_data[label] = conn.execute(f"SELECT COUNT(*) c FROM {tabel}").fetchone()["c"]
        except Exception:
            ringkasan_data[label] = (
                None  # tabel belum ada di skema versi ini — jangan sampai halaman error
            )

    # Cakupan modul dihitung LANGSUNG dari blueprint yang sungguh terdaftar
    # di aplikasi berjalan (bukan daftar manual yang bisa basi) — jumlah
    # modul roadmap diambil dari ROADMAP_MODULES yang sama dgn yang
    # dipakai sidebar, supaya kedua modul ini tidak pernah tidak sinkron.
    blueprint_names = sorted(n for n in current_app.blueprints if n not in ("roadmap", "static"))
    jumlah_modul_aktif = len(blueprint_names)
    jumlah_modul_roadmap = len(ROADMAP_MODULES)

    status_backup = backup_core.status_reminder()
    jumlah_file_backup = len(backup_core.list_backups())

    return render_template(
        "tentang.html",
        db_path=db_path,
        ukuran_db=_ukuran_manusiawi(ukuran_db),
        jumlah_tabel=jumlah_tabel,
        ringkasan_data=ringkasan_data,
        jumlah_modul_aktif=jumlah_modul_aktif,
        jumlah_modul_roadmap=jumlah_modul_roadmap,
        status_backup=status_backup,
        jumlah_file_backup=jumlah_file_backup,
        retensi_hari=30,  # default parameter bersihkan_backup_lama() di backup_core.py
    )
