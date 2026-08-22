# -*- coding: utf-8 -*-
"""routes/backup.py — Backup & Restore (Audit poin 5, diperluas di
Audit Lanjutan poin "Backup Menyeluruh").

Menggantikan menu sidebar "💾 Backup & Restore" yang sebelumnya diarahkan
ke halaman placeholder roadmap.modul (slug 'backup-restore').

Default sekarang adalah Backup LENGKAP (.zip — database + seluruh folder
file fisik seperti dokumen, RPS, bukti akreditasi, surat keluar, dsb),
supaya menu ini benar-benar bisa dipakai untuk mencadangkan KESELURUHAN
data aplikasi, bukan cuma isi database. Opsi "Database Saja (cepat)" tetap
disediakan untuk kasus operator hanya butuh salinan data tabel dengan
cepat. Restore mendukung kedua format (.zip lengkap & .db lama) sekaligus,
supaya backup lama dari versi sebelumnya tetap bisa dipulihkan.
"""

import os
import tempfile

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

from app import auth_core, backup_core
from app import db as _db
from app import error_utils as EH
from app.pin_guard import perlu_pin

bp = Blueprint("backup", __name__, url_prefix="/pengaturan/backup")


@bp.route("/")
def index():
    # Filter Backup per Tahun Akademik — nilai dari dropdown adalah salah
    # satu tag apa adanya (kode "2025/2026", atau label khusus "(Belum ada
    # periode aktif)"/"Tidak diketahui"), kosong berarti "Semua Tahun".
    tahun_filter = request.args.get("tahun_akademik", "").strip()
    backups = backup_core.list_backups(
        tahun_akademik=tahun_filter or None, dengan_tag=True
    )
    return render_template(
        "pengaturan/backup.html",
        backups=backups,
        folder_dicadangkan=backup_core.DATA_SUBFOLDERS,
        daftar_tahun_akademik=backup_core.list_tahun_akademik_backup(),
        tahun_filter=tahun_filter,
    )


@bp.route("/sekarang", methods=["POST"])
def backup_sekarang():
    conn = current_app.get_db()
    tipe = request.form.get("tipe", "lengkap")
    try:
        if tipe == "cepat":
            path = backup_core.backup_now(current_app.config["DB_PATH"])
            _db.log(conn, "Backup Database (Cepat, database saja)", os.path.basename(path))
            flash(f"Backup database (cepat) berhasil dibuat: {os.path.basename(path)}", "ok")
        else:
            path = backup_core.backup_now_full(current_app.config["DB_PATH"])
            _db.log(conn, "Backup Lengkap (database + file)", os.path.basename(path))
            flash(f"Backup lengkap berhasil dibuat: {os.path.basename(path)}", "ok")
        backup_core.bersihkan_backup_lama()
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal membuat backup")
    return redirect(url_for("backup.index"))


@bp.route("/unduh/<nama>")
def unduh(nama):
    nama = secure_filename(nama)
    path = os.path.join(backup_core.get_backup_dir(), nama)
    if not os.path.isfile(path):
        flash("File backup tidak ditemukan.", "error")
        return redirect(url_for("backup.index"))
    return send_file(path, as_attachment=True, download_name=nama)


@bp.route("/restore", methods=["POST"])
@perlu_pin
def restore():
    """Endpoint paling sensitif di aplikasi ini: menimpa seluruh database
    (dan, untuk file .zip, seluruh folder file fisik) aktif. Restrukturisasi
    poin 2 menambah @perlu_pin sebagai lapis PALING LUAR (harus lolos PIN
    dulu sebelum request ini diproses). Di bawahnya tetap 3 lapis pengaman
    lama yang tidak diubah — (1) konfirmasi ulang password admin, (2)
    validasi isi file (bukan sekadar ekstensi), (3) backup lengkap otomatis
    file lama sebelum ditimpa (bisa dibatalkan lewat menu ini juga).
    Mendukung dua format: .zip (Backup Lengkap — database + file fisik) &
    .db lama (database saja, kompatibilitas mundur)."""
    conn = current_app.get_db()
    password = request.form.get("password_konfirmasi", "")
    if not auth_core.verify_password(conn, password):
        flash("Password konfirmasi salah — restore dibatalkan.", "error")
        return redirect(url_for("backup.index"))

    file = request.files.get("file_restore")
    if not file or not file.filename:
        flash("Pilih file backup (.zip atau .db) terlebih dahulu.", "error")
        return redirect(url_for("backup.index"))

    fname = secure_filename(file.filename)
    is_zip = fname.lower().endswith(".zip")
    is_db = fname.lower().endswith(".db")
    if not (is_zip or is_db):
        flash(
            "Format file tidak dikenali — gunakan file .zip (Backup Lengkap) atau .db (lama).",
            "error",
        )
        return redirect(url_for("backup.index"))

    tmp_path = os.path.join(tempfile.gettempdir(), f"simprodi_restore_{fname}")
    file.save(tmp_path)
    try:
        if is_zip:
            ok, pesan = backup_core.validasi_file_restore_zip(tmp_path)
        else:
            ok, pesan = backup_core.validasi_file_restore(tmp_path)
        if not ok:
            flash(f"File ditolak: {pesan}", "error")
            return redirect(url_for("backup.index"))

        db_path = current_app.config["DB_PATH"]
        if is_zip:
            cadangan_lama = backup_core.restore_dari_file_zip(tmp_path, db_path)
            aksi = "Restore Lengkap (database + file)"
            pesan_ok = (
                f"Restore lengkap berhasil dari {fname} (database & folder file fisik "
                f"seperti dokumen/surat/RPS ikut dipulihkan)."
            )
        else:
            cadangan_lama = backup_core.restore_dari_file(tmp_path, db_path)
            aksi = "Restore Database (dari file .db lama)"
            pesan_ok = (
                f"Restore database berhasil dari {fname}. Ini adalah restore database "
                f"SAJA (format lama) — folder file fisik (dokumen/surat/RPS) tidak berubah."
            )
        _db.log(conn, aksi, f"dari {fname}, cadangan lama: {os.path.basename(cadangan_lama)}")
        flash(
            f"{pesan_ok} Data sebelumnya otomatis dicadangkan lengkap sebagai "
            f"{os.path.basename(cadangan_lama)} kalau perlu dibatalkan.",
            "ok",
        )
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal restore")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return redirect(url_for("auth.logout"))


# =============================================================================
# Audit UI/UX (permintaan fitur) — Reset Total Data
# =============================================================================
# Operasi PALING destruktif di seluruh aplikasi ini -- lebih dari Restore
# (yang menimpa dengan data lain yang MASIH ADA), reset TIDAK menyisakan
# data apa pun. Karena itu lapisan pengamanannya SATU TINGKAT lebih ketat
# daripada Restore: selain PIN + konfirmasi password (persis pola Restore
# di atas), operator WAJIB mengetik ulang frasa konfirmasi persis
# ("HAPUS SEMUA DATA") -- pola umum untuk aksi yang tidak bisa dibatalkan
# lewat undo biasa (mis. GitHub meminta ketik ulang nama repo sebelum
# menghapusnya). Backup Lengkap otomatis TETAP dibuat sebelum reset
# (persis pola Restore), jadi walau "tidak bisa dibatalkan lewat undo",
# secara praktis tetap bisa dipulihkan lewat menu Restore memakai backup
# yang baru saja dibuat itu.
FRASA_KONFIRMASI_RESET = "HAPUS SEMUA DATA"


@bp.route("/reset", methods=["POST"])
@perlu_pin
def reset_data():
    conn = current_app.get_db()
    password = request.form.get("password_konfirmasi", "")
    if not auth_core.verify_password(conn, password):
        flash("Password konfirmasi salah — reset dibatalkan.", "error")
        return redirect(url_for("backup.index"))

    frasa = request.form.get("frasa_konfirmasi", "").strip()
    if frasa != FRASA_KONFIRMASI_RESET:
        flash(
            f'Frasa konfirmasi tidak cocok — ketik persis "{FRASA_KONFIRMASI_RESET}" '
            "(tanpa tanda kutip) untuk melanjutkan. Reset dibatalkan.",
            "error",
        )
        return redirect(url_for("backup.index"))

    try:
        # Backup Lengkap otomatis SEBELUM reset — jaring pengaman utama:
        # walau reset "tidak bisa dibatalkan" secara harfiah (bukan cuma
        # ditimpa seperti Restore), backup ini membuatnya tetap bisa
        # dipulihkan lewat menu Restore kalau ternyata keliru.
        path_backup = backup_core.backup_now_full(current_app.config["DB_PATH"])
        nama_backup = os.path.basename(path_backup)

        _db.reset_semua_data(conn)

        # Dicatat SETELAH reset (bukan sebelum) -- log_aktivitas ikut
        # dikosongkan oleh reset_semua_data(), jadi baris ini sengaja
        # menjadi entri PERTAMA di jejak audit yang baru, supaya tetap ada
        # jejak institusional kapan & oleh apa reset ini terjadi.
        _db.log(
            conn,
            "Reset Total Data",
            f"Seluruh data dikosongkan & ditabur ulang ke kondisi awal. "
            f"Backup otomatis sebelum reset: {nama_backup}.",
            modul="Pengaturan",
            entitas="Database",
            alasan="Reset Total Data oleh operator (dikonfirmasi PIN + password + frasa)",
        )
        flash(
            f"Reset total berhasil — seluruh data telah dikosongkan dan aplikasi kembali ke "
            f"kondisi baru diinstal. Data lama otomatis dicadangkan lengkap sebagai "
            f"{nama_backup} sebelum direset, bisa dipulihkan lewat menu Restore kalau "
            f"diperlukan. Anda akan diminta membuat ulang akun admin.",
            "ok",
        )
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal melakukan reset total data")
        return redirect(url_for("backup.index"))
    return redirect(url_for("auth.logout"))
