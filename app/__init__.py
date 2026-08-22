# -*- coding: utf-8 -*-
"""
app/__init__.py — Flask application factory.

Pola koneksi DB: satu koneksi SQLite dibuka per-request (disimpan di
flask.g) dan ditutup otomatis setelah response selesai. Wajar & aman untuk
aplikasi 1 pengguna/1 komputer seperti ini (bukan aplikasi web multi-user
dengan banyak koneksi bersamaan).
"""

import os
import sys
import threading

from flask import Flask, g, redirect, request, session, url_for
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError

from app import backup_core
from app import constants as C
from app import db

# Audit poin 5 (tindak lanjut) — jeda antar pembersihan otomatis. Aplikasi
# ini offline single-tenant (1 proses per komputer, dibuka-tutup manual),
# jadi tidak ada cron/scheduler sistem yang bisa diandalkan — "dijadwalkan
# otomatis" di sini berarti: (1) berjalan sendiri setiap aplikasi start,
# TANPA operator harus klik "Backup Sekarang" dulu, dan (2) kalau proses
# dibiarkan menyala lama (mode --web dibuka berhari-hari), diulang sendiri
# tiap 24 jam lewat thread latar belakang — bukan cuma sekali di awal.
_INTERVAL_RETENSI_BACKUP_DETIK = 24 * 60 * 60


def _resource_path(*parts):
    """Lokasi folder templates/static — robust baik dijalankan sebagai
    skrip Python biasa maupun sudah 'dibungkus' PyInstaller (yang
    mengekstrak file ke folder sementara sys._MEIPASS)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = os.path.join(sys._MEIPASS, "app")
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def create_app(db_path=None):
    app = Flask(
        __name__,
        template_folder=_resource_path("templates"),
        static_folder=_resource_path("static"),
    )
    app.config["DB_PATH"] = db_path or db.get_default_db_path()

    # Audit Lanjutan (Backup & Restore / Import Excel) — temuan: tidak ada
    # batas ukuran unggahan yang ditegakkan Flask sama sekali di seluruh
    # aplikasi (MAX_CONTENT_LENGTH belum pernah diset). Semua endpoint
    # unggah file (Restore .zip/.db, Import Excel migrasi, Import Generik
    # per-modul, unggah logo/dokumen/RPS/dll) menerima body request
    # SEBESAR APA PUN dari jaringan sebelum kode aplikasi sempat menolak
    # berdasarkan ukuran (mis. backup_core.MAKS_UKURAN_RESTORE_ZIP_BYTES
    # baru dicek SETELAH file selesai diterima & ditulis ke disk) — celah
    # DoS sederhana (habiskan RAM/disk cukup dengan 1 request unggahan
    # raksasa). Batas global ditetapkan sedikit di atas batas terbesar
    # yang memang valid di aplikasi ini (Backup Lengkap .zip, 1 GB —
    # lihat backup_core.MAKS_UKURAN_RESTORE_ZIP_BYTES) supaya restore sah
    # tetap bisa lolos, tapi permintaan di luar itu ditolak Flask/Werkzeug
    # sendiri (413) SEBELUM body-nya selesai dibaca ke memori/disk.
    app.config["MAX_CONTENT_LENGTH"] = 1100 * 1024 * 1024  # 1100 MB

    def get_db():
        if "db" not in g:
            g.db = db.connect(app.config["DB_PATH"])
        return g.db

    app.get_db = get_db

    # Audit poin 6.2 temuan #1: SECRET_KEY sebelumnya dibuat ulang setiap
    # kali proses start (`os.urandom(24).hex()` langsung di config), yang
    # memaksa logout semua sesi tiap restart server dan akan gagal random
    # kalau nanti dijalankan multi-worker (gunicorn). Sekarang disimpan di
    # tabel pengaturan (di-generate sekali, dipakai ulang selamanya) —
    # butuh 1 koneksi DB sekali di sini sebelum app context tersedia.
    _bootstrap_conn = db.connect(app.config["DB_PATH"])
    secret = db.get_setting(_bootstrap_conn, "secret_key", "")
    if not secret:
        secret = os.urandom(32).hex()
        db.set_setting(_bootstrap_conn, "secret_key", secret)
    app.config["SECRET_KEY"] = secret
    _bootstrap_conn.close()

    # Audit poin 5 (tindak lanjut) — retensi backup lama (backup_core.
    # bersihkan_backup_lama(), sudah ada sejak modul Backup & Restore
    # dibangun) sebelumnya HANYA terpanggil manual saat tombol "Backup
    # Sekarang" diklik. Sekarang dijadwalkan otomatis: sekali saat aplikasi
    # start (baris di bawah), lalu diulang tiap 24 jam via thread daemon
    # kalau proses dibiarkan menyala lama. Dilewati saat TESTING supaya
    # skrip tes tidak membuka thread latar belakang yang tidak perlu &
    # tidak menyentuh filesystem HOME sementara antar-test-case.
    # Guard tambahan: kalau nanti dijalankan lewat `flask run`/debug reloader
    # (2 proses: monitor + worker), WERKZEUG_RUN_MAIN cuma "true" di proses
    # worker sungguhan — mencegah 2 thread retensi menyala dobel. Kalau
    # reloader tidak dipakai sama sekali (mode normal/pywebview), variabel
    # ini tidak ada (None), jadi tetap dijalankan seperti biasa.
    _reloader_worker_ok = os.environ.get("WERKZEUG_RUN_MAIN") in (None, "true")
    if not app.config.get("TESTING") and _reloader_worker_ok:
        try:
            backup_core.bersihkan_backup_lama()
        except OSError:
            pass  # folder backup belum ada / belum pernah dipakai — aman diabaikan

        def _loop_retensi_backup():
            import time

            while True:
                time.sleep(_INTERVAL_RETENSI_BACKUP_DETIK)
                try:
                    backup_core.bersihkan_backup_lama()
                except OSError:
                    pass

        threading.Thread(target=_loop_retensi_backup, daemon=True).start()

    # Audit poin 6.2 — proteksi CSRF menyeluruh (Flask-WTF) untuk semua
    # form POST/PUT/PATCH/DELETE. Setiap form di templates/ menyertakan
    # token tersembunyi lewat `{{ csrf_token() }}` (disediakan otomatis
    # oleh Flask-WTF sebagai fungsi global Jinja). Skrip pengujian
    # menonaktifkan ini secara eksplisit lewat WTF_CSRF_ENABLED=False,
    # bukan lewat pengecualian tersembunyi di sini.
    csrf = CSRFProtect()
    csrf.init_app(app)

    @app.errorhandler(CSRFError)
    def _csrf_error(e):
        from flask import flash, redirect
        from flask import request as _req

        flash("Sesi formulir sudah kedaluwarsa atau tidak valid — silakan coba lagi.", "error")
        return redirect(_req.referrer or url_for("dashboard.index"))

    # Audit Lanjutan — pasangan dari MAX_CONTENT_LENGTH di atas: tanpa
    # handler ini, unggahan yang melebihi batas akan menampilkan halaman
    # galat 413 mentah bawaan Werkzeug (bukan pesan ramah + flash seperti
    # pola error lain di aplikasi ini).
    @app.errorhandler(413)
    def _terlalu_besar(e):
        from flask import flash, redirect
        from flask import request as _req

        batas_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        flash(f"Berkas yang diunggah terlalu besar (maks {batas_mb} MB).", "error")
        return redirect(_req.referrer or url_for("dashboard.index"))

    @app.teardown_appcontext
    def close_db(exception=None):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    # --- Konteks yang tersedia di semua template (nama institusi, dsb) ---
    @app.context_processor
    def inject_globals():
        import datetime as _dt

        from app.routes.notifikasi import hitung_ringkasan as _notif_ringkasan

        conn = get_db()
        tema_warna = db.get_setting(conn, "tema_warna", "indigo")
        if tema_warna not in [t["kode"] for t in C.TEMA_WARNA_LIST]:
            tema_warna = "indigo"
        return {
            "APP_NAME": C.APP_NAME,
            "APP_SHORT_NAME": C.APP_SHORT_NAME,
            "APP_VERSION": C.APP_VERSION,
            "nama_institusi": db.get_setting(conn, "nama_institusi", ""),
            "nama_prodi": db.get_setting(conn, "nama_prodi", ""),
            "nama_fakultas": db.get_setting(conn, "nama_fakultas", ""),
            "tahun_akademik_aktif": db.get_setting(conn, "tahun_akademik_aktif", ""),
            "logo_path": db.get_setting(conn, "logo_path", ""),
            "tahun_sekarang": _dt.date.today().year,
            # Audit Lanjutan 3 — Preferensi Tampilan, Tema & Pusat Notifikasi.
            # Dibaca di base.html: atribut data-theme, class densitas <body>,
            # mode default grup sidebar, dan badge jumlah di ikon lonceng.
            "tema_warna": tema_warna,
            "pref_densitas": db.get_setting(conn, "pref_densitas", "Nyaman"),
            "pref_sidebar_mode": db.get_setting(conn, "pref_sidebar_mode", "otomatis"),
            "notif_ringkasan": _notif_ringkasan(conn),
        }

    # --- Gerbang login: semua route wajib login, kecuali auth.* & static ---
    # Pengecualian tambahan: pengaturan.logo_preview — supaya logo institusi
    # (kalau sudah diunggah di Pengaturan) bisa tampil di halaman login itu
    # sendiri, sebelum pengguna login. Endpoint ini hanya menyajikan file
    # gambar baca-saja, tidak ada data yang diubah.
    @app.before_request
    def wajib_login():
        if request.endpoint is None:
            return
        if request.endpoint.startswith("auth.") or request.endpoint == "static":
            return
        if request.endpoint == "pengaturan.logo_preview":
            return
        if not session.get("logged_in"):
            return redirect(url_for("auth.login"))

    from app.routes.akademik import bp as akademik_bp
    from app.routes.auth import bp as auth_bp
    from app.routes.backup import bp as backup_bp
    from app.routes.cqi import bp as cqi_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.dokumen import bp as dokumen_bp
    from app.routes.dosen import bp as dosen_bp
    from app.routes.jadwal import bp as jadwal_bp
    from app.routes.kalender import bp as kalender_bp
    from app.routes.kegiatan import bp as kegiatan_bp
    from app.routes.kelulusan import bp as kelulusan_bp
    from app.routes.kerjasama import bp as kerjasama_bp
    from app.routes.kurikulum import bp as kurikulum_bp
    from app.routes.mahasiswa import bp as mahasiswa_bp
    from app.routes.mutu import bp as mutu_bp
    from app.routes.nilai import bp as nilai_bp
    from app.routes.notifikasi import bp as notifikasi_bp
    from app.routes.panduan import bp as panduan_bp
    from app.routes.pelaksanaan import bp as pelaksanaan_bp
    from app.routes.pengaturan import bp as pengaturan_bp
    from app.routes.preferensi import bp as preferensi_bp
    from app.routes.rekap import bp as rekap_bp
    from app.routes.roadmap import bp as roadmap_bp
    from app.routes.rpl import bp as rpl_bp
    from app.routes.ruangan import bp as ruangan_bp
    from app.routes.sdm import bp as sdm_bp
    from app.routes.semester_pendek import bp as sp_bp
    from app.routes.surat import bp as surat_bp
    from app.routes.surat_umum import bp as surat_umum_bp
    from app.routes.tema import bp as tema_bp
    from app.routes.tentang import bp as tentang_bp
    from app.routes.tridharma import bp as tridharma_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(mahasiswa_bp)
    app.register_blueprint(pengaturan_bp)
    app.register_blueprint(dosen_bp)
    app.register_blueprint(ruangan_bp)
    app.register_blueprint(akademik_bp)
    app.register_blueprint(pelaksanaan_bp)
    app.register_blueprint(kelulusan_bp)
    app.register_blueprint(rekap_bp)
    app.register_blueprint(surat_bp)
    app.register_blueprint(sdm_bp)
    app.register_blueprint(kalender_bp)
    app.register_blueprint(kegiatan_bp)
    app.register_blueprint(dokumen_bp)
    app.register_blueprint(surat_umum_bp)
    app.register_blueprint(roadmap_bp)
    app.register_blueprint(kurikulum_bp)
    app.register_blueprint(jadwal_bp)
    app.register_blueprint(nilai_bp)
    app.register_blueprint(cqi_bp)
    app.register_blueprint(sp_bp)
    app.register_blueprint(rpl_bp)
    app.register_blueprint(tridharma_bp)
    app.register_blueprint(kerjasama_bp)
    app.register_blueprint(mutu_bp)
    app.register_blueprint(panduan_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(tentang_bp)
    app.register_blueprint(preferensi_bp)
    app.register_blueprint(tema_bp)
    app.register_blueprint(notifikasi_bp)

    return app
