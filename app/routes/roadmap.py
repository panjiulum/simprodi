# -*- coding: utf-8 -*-
"""routes/roadmap.py — Modul yang direncanakan tapi belum punya logika &
skema data resmi di SIMPRODI — baik menu asal SITIPRO (demo UI/UX) maupun
menu hasil rekomendasi evaluasi UX/IA lanjutan (mis. restrukturisasi
sidebar) yang dianggap penting untuk sistem tapi sengaja belum dibangun
di sesi ini.

PENTING: SITIPRO adalah acuan tampilan saja, bukan aplikasi produksi, dan
tidak pernah dipakai sebagai sumber logika. Supaya menu di sidebar tetap
jujur (tidak menautkan ke halaman kosong/404 begitu menu ditambahkan),
setiap menu yang belum punya modul backend di SIMPRODI diarahkan ke sini:
satu halaman status "dalam pengembangan" per modul, bukan data tiruan/dummy.

Menambah modul sungguhan (dengan tabel & CRUD) di kemudian hari cukup:
1. Buat routes/<modul>.py + skema di db.py seperti modul lain.
2. Hapus entry-nya dari ROADMAP_MODULES di bawah & dari nav_groups di
   base.html, ganti dengan endpoint modul yang baru.
"""

from flask import Blueprint, abort, render_template

bp = Blueprint("roadmap", __name__, url_prefix="/segera")

# slug -> (judul, deskripsi singkat, kategori nav asal)
# Hasil restrukturisasi sidebar (lihat docs/RESTRUKTURISASI_SIDEBAR.md):
# grup "Pengaturan" baru menyertakan beberapa menu yang secara sadar
# direkomendasikan sebagai kebutuhan sistem info program studi yang lebih
# matang, tapi BELUM dibangun sesi ini (di luar cakupan "reorganisasi
# navigasi") — diarahkan ke sini alih-alih dihilangkan dari peta menu
# atau dibuat sebagai tautan mati.
ROADMAP_MODULES = {
    # "preferensi", "notifikasi" & "tema" DIHAPUS dari sini (Audit Lanjutan
    # 3): ketiganya sudah jadi modul nyata — lihat routes/preferensi.py,
    # routes/notifikasi.py & routes/tema.py — dan nav_groups di base.html
    # sudah diarahkan ke endpoint asli masing-masing (preferensi.index,
    # notifikasi.index, tema.index), bukan lagi ke roadmap.modul. Belum
    # ada modul lain yang masih berstatus roadmap murni saat ini.
}


@bp.route("/<slug>")
def modul(slug):
    data = ROADMAP_MODULES.get(slug)
    if not data:
        abort(404)
    judul, deskripsi, kategori = data
    return render_template("roadmap.html", judul=judul, deskripsi=deskripsi, kategori=kategori)
