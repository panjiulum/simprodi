# -*- coding: utf-8 -*-
"""
backup_core.py — Modul Backup & Restore (Audit poin 5, diperluas di
Audit Lanjutan poin "Backup Menyeluruh").

Sebelumnya menu "💾 Backup & Restore" di sidebar mengarah ke halaman
placeholder roadmap ("dalam pengembangan") — satu-satunya cara mencadangkan
data adalah menyalin manual file .db di luar aplikasi. Modul ini
membangun Backup/Restore Utuh (level file), memakai SQLite Online Backup
API resmi (bukan shutil.copy mentah), supaya aman walau ada transaksi
berjalan.

Temuan Audit Lanjutan: backup versi awal (`backup_now`/`backup_dari_file`,
masih dipertahankan di bawah untuk kompatibilitas mundur) HANYA mencadangkan
file database (data_prodi.db). Padahal banyak modul menyimpan file FISIK
di luar database — dokumen (Document Center), bukti akreditasi (Mutu),
dokumen kerjasama, RPS (Kurikulum), dokumen RPL, surat keluar yang sudah
di-generate (Surat Umum), dan logo/branding institusi. Kalau operator
me-restore backup lama ke komputer baru, seluruh file itu HILANG walau
baris metadata-nya (nama file, path) masih ada di database — tautan jadi
rusak/patah. Fungsi `backup_now_full` / `restore_dari_file_zip` di bawah
menutup celah ini: SATU file .zip berisi database + seluruh folder file
fisik, supaya "Backup Sekarang" benar-benar mencadangkan KESELURUHAN data
aplikasi, bukan cuma isi tabel.

Catatan keamanan (menyambung ke Audit poin 6): endpoint restore adalah
yang PALING SENSITIF di seluruh aplikasi — divalidasi ekstensi + isi file
(magic bytes SQLite utk .db, struktur zip + manifest utk .zip), dibatasi
ukuran, dan wajib backup-otomatis file lama SEBELUM restore (jaga-jaga
restore salah file / tidak ada jalan mundur). Konfirmasi ulang password
ditegakkan di routes/backup.py (perlu akses ke auth_core & session), bukan
di sini.

Filter Backup per Tahun Akademik: setiap backup ditandai (tag) kode tahun
ajaran yang periode-nya berstatus 'Berjalan' saat backup itu dibuat, dipakai
UNTUK MENYARING daftar Riwayat Backup — BUKAN untuk memisah/mengekspor data
per tahun (1 backup tetap selalu mencadangkan KESELURUHAN data aplikasi,
tidak ada mode "backup hanya 1 tahun ajaran"). Mode .db & .zip membaca tag
lewat jalur berbeda (lihat `_tag_db_dari_file` vs `_tag_zip_dari_manifest`)
supaya membuka Riwayat Backup tidak perlu mengekstrak isi file .zip
berulang kali.
"""

import datetime as _dt
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile

SQLITE_MAGIC = b"SQLite format 3\x00"
MAKS_UKURAN_RESTORE_BYTES = 200 * 1024 * 1024  # 200 MB — file .db saja
MAKS_UKURAN_RESTORE_ZIP_BYTES = (
    1024 * 1024 * 1024
)  # 1 GB — .zip lengkap (bisa berisi banyak dokumen/surat)

# Tabel inti yang WAJIB ada di file yang mau di-restore — pemeriksaan skema
# minimal supaya file .db dari aplikasi lain / rusak tidak lolos ditimpakan.
TABEL_INTI_WAJIB = ["mahasiswa", "dosen", "pengaturan", "pengguna", "seminar", "sidang"]

# Folder-folder file fisik di luar database yang perlu ikut dicadangkan
# (Audit Lanjutan). Path selalu relatif terhadap get_data_root() — kalau
# ada modul baru di masa depan yang menambah folder upload sendiri, cukup
# tambahkan nama foldernya di sini supaya otomatis ikut ter-backup.
DATA_SUBFOLDERS = [
    ("dokumen", "Document Center (SK/MoU/kurikulum/akreditasi, dll)"),
    ("mitra_dokumen", "Dokumen Kerjasama/Mitra"),
    ("rps", "RPS Kurikulum"),
    ("akreditasi_bukti", "Bukti Dukung Mutu/Akreditasi"),
    ("rpl_dokumen", "Dokumen RPL"),
    ("surat_keluar", "Arsip Surat Keluar (Generator Surat Umum)"),
    ("branding", "Logo & Identitas Institusi"),
]

MANIFEST_NAME = "manifest.json"
DB_ARCNAME = "data_prodi.db"
FILES_PREFIX = "files"

# Label tag tahun akademik (Filter Backup per Tahun Akademik) untuk 2 kasus
# yang BUKAN kode sungguhan ("2025/2026") — dibedakan supaya operator tidak
# salah paham antara "memang belum ada tahun ajaran aktif saat itu" (kondisi
# normal, mis. backup dibuat sebelum wizard Buka Tahun Ajaran pernah dipakai)
# vs "tidak bisa ditentukan sama sekali" (file sangat lama / rusak / bukan
# database SIMPRODI yang skemanya dikenali).
TAG_TIDAK_ADA_PERIODE_AKTIF = "(Belum ada periode aktif)"
TAG_TIDAK_DIKETAHUI = "Tidak diketahui"


def get_data_root():
    from app.db import home_dir
    return os.path.join(home_dir(), "SistemSkripsi")


def get_backup_dir():
    folder = os.path.join(get_data_root(), "backup")
    os.makedirs(folder, exist_ok=True)
    return folder


def _timestamp():
    # Presisi mikrodetik (bukan cuma detik) — mencegah 2 backup yang dibuat
    # sangat berdekatan (mis. backup manual & backup pra-restore otomatis
    # dalam 1 detik yang sama) kebetulan memakai nama file yang identik,
    # yang kalau terjadi bisa saling menimpa.
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _snapshot_db_to(db_path, dest_path):
    """Salin database ke `dest_path` lewat SQLite Online Backup API — aman
    dijalankan walau ada transaksi/koneksi lain sedang aktif, tidak seperti
    shutil.copy file mentah yang bisa menyalin file setengah-tulis."""
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest_path)
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()


def _baca_kode_periode_berjalan(db_file_path):
    """Baca kode tahun ajaran yang periode-nya berstatus 'Berjalan' dari isi
    sebuah file database SQLite (query yang sama dengan `db.get_periode_
    aktif()`, ditulis ulang di sini pakai sqlite3 langsung supaya modul ini
    tidak perlu bergantung ke `app.db` untuk hal sesederhana ini).

    Mengembalikan kode (str) kalau ketemu, atau None kalau file bisa dibuka
    & skemanya dikenali tapi memang tidak ada periode yang 'Berjalan' saat
    itu (kondisi normal). Melempar `sqlite3.Error`/`OSError` kalau file
    tidak bisa dibuka sama sekali atau skemanya tidak dikenali (tabel
    `tahun_ajaran`/`periode_akademik` tidak ada) — sengaja TIDAK ditangkap
    di sini, biar pemanggil yang memutuskan artinya (lihat pemakaian di
    `list_backups` vs `backup_now_full`)."""
    conn = sqlite3.connect(f"file:{db_file_path}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT ta.kode FROM periode_akademik pa "
            "JOIN tahun_ajaran ta ON ta.id = pa.tahun_ajaran_id "
            "WHERE pa.status='Berjalan' ORDER BY pa.id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def backup_now(db_path, backup_dir=None):
    """Backup Database Saja (cepat) — versi awal, dipertahankan untuk
    kompatibilitas mundur & dipakai juga sebagai langkah internal
    "cadangkan dulu sebelum restore". Untuk cadangan rutin operator
    sehari-hari, gunakan `backup_now_full` (menyertakan file fisik)."""
    backup_dir = backup_dir or get_backup_dir()
    os.makedirs(backup_dir, exist_ok=True)
    dest_name = f"backup_{_timestamp()}.db"
    dest_path = os.path.join(backup_dir, dest_name)
    _snapshot_db_to(db_path, dest_path)
    return dest_path


def backup_now_full(db_path, backup_dir=None, data_root=None):
    """Backup LENGKAP (Audit Lanjutan): database + seluruh folder file fisik
    (DATA_SUBFOLDERS) dibungkus jadi SATU file .zip, supaya "Backup Sekarang"
    sungguh-sungguh mencadangkan keseluruhan data aplikasi. Ini adalah mode
    default yang dipakai tombol "Backup Sekarang" di UI."""
    backup_dir = backup_dir or get_backup_dir()
    data_root = data_root or get_data_root()
    os.makedirs(backup_dir, exist_ok=True)
    dest_name = f"backup_lengkap_{_timestamp()}.zip"
    dest_path = os.path.join(backup_dir, dest_name)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_db = os.path.join(tmp, DB_ARCNAME)
        _snapshot_db_to(db_path, tmp_db)

        # Filter Backup per Tahun Akademik — tag disimpan di manifest SAAT
        # backup dibuat (bukan dibaca ulang tiap kali .zip ini ditampilkan
        # di Riwayat Backup, beda dari mode .db — lihat komentar
        # `_tag_zip_dari_manifest`). Dibaca dari snapshot yang BARU saja
        # dibuat (bukan langsung dari db_path) supaya konsisten dengan isi
        # data_prodi.db yang sungguh-sungguh ikut masuk ke dalam arsip ini.
        try:
            tahun_akademik_saat_ini = _baca_kode_periode_berjalan(tmp_db)
        except (sqlite3.Error, OSError):
            # Praktis tidak pernah terjadi (snapshot baru dari db aplikasi
            # yang sedang berjalan, skemanya pasti dikenali) — tapi dijaga
            # supaya proses backup tidak pernah gagal gara-gara ini.
            tahun_akademik_saat_ini = None

        manifest = {
            "format": "simprodi-backup-lengkap",
            "versi": 1,
            "dibuat_pada": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tahun_akademik": tahun_akademik_saat_ini,
            "folder": [],
        }
        tmp_zip = dest_path + ".part"
        try:
            with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(tmp_db, arcname=DB_ARCNAME)
                for folder, deskripsi in DATA_SUBFOLDERS:
                    src_folder = os.path.join(data_root, folder)
                    jumlah = 0
                    if os.path.isdir(src_folder):
                        for root, _dirs, files in os.walk(src_folder):
                            for fname in files:
                                full = os.path.join(root, fname)
                                rel = os.path.relpath(full, data_root)
                                zf.write(full, arcname=f"{FILES_PREFIX}/{rel}".replace(os.sep, "/"))
                                jumlah += 1
                    manifest["folder"].append(
                        {"nama": folder, "deskripsi": deskripsi, "jumlah_file": jumlah}
                    )
                zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False))
            os.replace(tmp_zip, dest_path)
        finally:
            if os.path.exists(tmp_zip):
                try:
                    os.remove(tmp_zip)
                except OSError:
                    pass
    return dest_path


def baca_manifest(zip_path):
    """Baca manifest.json dari sebuah backup .zip (untuk ditampilkan di UI
    riwayat backup — jumlah file per folder dsb). Mengembalikan dict atau
    None kalau bukan backup lengkap / tidak ada manifest."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            if MANIFEST_NAME not in zf.namelist():
                return None
            with zf.open(MANIFEST_NAME) as fh:
                return json.loads(fh.read().decode("utf-8"))
    except (zipfile.BadZipFile, OSError, ValueError):
        return None


def _tag_db_dari_file(full_path):
    """Tag tahun akademik utk backup .db — dibaca LANGSUNG dari isi file
    itu sendiri tiap kali dipanggil (tidak disimpan terpisah di mana pun),
    karena file backup .db memang sudah snapshot utuh yang tidak pernah
    berubah lagi setelah dibuat, jadi tidak ada risiko cache basi."""
    try:
        kode = _baca_kode_periode_berjalan(full_path)
    except (sqlite3.Error, OSError):
        return TAG_TIDAK_DIKETAHUI
    return kode or TAG_TIDAK_ADA_PERIODE_AKTIF


def _tag_zip_dari_manifest(full_path):
    """Tag tahun akademik utk backup .zip — dibaca dari `manifest.json`
    yang sudah disimpan SAAT backup dibuat (lihat `backup_now_full`),
    BUKAN dengan membuka lagi `data_prodi.db` di dalam arsip tiap kali
    daftar riwayat ditampilkan (lebih murah — cukup baca 1 entri kecil
    dari zip, bukan buka koneksi SQLite baru per backup). Backup .zip
    LAMA dari sebelum fitur ini ada tidak punya kunci "tahun_akademik"
    sama sekali di manifest-nya -> otomatis masuk TAG_TIDAK_DIKETAHUI,
    bukan dianggap error."""
    manifest = baca_manifest(full_path)
    if manifest is None or "tahun_akademik" not in manifest:
        return TAG_TIDAK_DIKETAHUI
    return manifest["tahun_akademik"] or TAG_TIDAK_ADA_PERIODE_AKTIF


def list_backups(backup_dir=None, tahun_akademik=None, dengan_tag=None):
    """Daftar file backup di `backup_dir`, terbaru dulu.

    `dengan_tag` (Filter Backup per Tahun Akademik): membaca & menyertakan
    tag tahun akademik per file (`entry["tahun_akademik"]`) — sengaja opt-in
    (default None -> otomatis True hanya kalau `tahun_akademik` diisi),
    karena membaca tag berarti buka file .db/.zip satu-satu (lihat
    `_tag_db_dari_file`/`_tag_zip_dari_manifest`). Pemanggil yang cuma
    butuh nama/ukuran/tanggal — `status_reminder()` (jalan di SETIAP page
    load lewat notifikasi) & `bersihkan_backup_lama()` — TIDAK mengaktifkan
    ini, supaya tidak menambah beban baca file di jalur yang sering
    dipanggil itu.

    `tahun_akademik`: kalau diisi, hanya kembalikan backup dengan tag PERSIS
    sama (termasuk label khusus `TAG_TIDAK_ADA_PERIODE_AKTIF`/
    `TAG_TIDAK_DIKETAHUI`, dipakai apa adanya sebagai nilai filter).
    """
    backup_dir = backup_dir or get_backup_dir()
    if not os.path.isdir(backup_dir):
        return []
    perlu_tag = bool(dengan_tag) or bool(tahun_akademik)
    out = []
    for fname in os.listdir(backup_dir):
        low = fname.lower()
        if low.endswith(".zip"):
            tipe = "Lengkap (database + file)"
        elif low.endswith(".db"):
            tipe = "Database saja"
        else:
            continue
        full = os.path.join(backup_dir, fname)
        try:
            stat = os.stat(full)
        except OSError:
            continue
        entry = {
            "nama": fname,
            "path": full,
            "tipe": tipe,
            "ukuran_kb": round(stat.st_size / 1024, 1),
            "dibuat_pada": _dt.datetime.fromtimestamp(stat.st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }
        if perlu_tag:
            entry["tahun_akademik"] = (
                _tag_zip_dari_manifest(full) if low.endswith(".zip") else _tag_db_dari_file(full)
            )
            if tahun_akademik and entry["tahun_akademik"] != tahun_akademik:
                continue
        out.append(entry)
    out.sort(key=lambda r: r["dibuat_pada"], reverse=True)
    return out


def list_tahun_akademik_backup(backup_dir=None):
    """Daftar tag tahun akademik yang BENAR-BENAR muncul di antara file
    backup yang ada saat ini di `backup_dir` — dipakai mengisi dropdown
    filter di halaman Riwayat Backup, supaya operator tidak disodori opsi
    tahun yang tidak punya backup sama sekali. Kode asli (mis. "2025/2026")
    diurutkan terbaru dulu (pola sama dengan filter tahun akademik di
    modul lain); label khusus (tidak ada periode aktif / tidak diketahui)
    selalu ditaruh paling akhir."""
    tags = {b["tahun_akademik"] for b in list_backups(backup_dir, dengan_tag=True)}
    label_khusus = [t for t in (TAG_TIDAK_ADA_PERIODE_AKTIF, TAG_TIDAK_DIKETAHUI) if t in tags]
    kode_asli = sorted(tags - set(label_khusus), reverse=True)
    return kode_asli + label_khusus


def bersihkan_backup_lama(backup_dir=None, retensi_hari=30):
    """Retensi otomatis: hapus backup lebih tua dari `retensi_hari` hari,
    tapi selalu sisakan minimal 3 file terbaru walau semuanya lebih tua
    (jaga-jaga prodi jarang buka aplikasi tapi backupnya tetap perlu ada)."""
    backups = list_backups(backup_dir)
    if len(backups) <= 3:
        return 0
    batas = _dt.datetime.now() - _dt.timedelta(days=retensi_hari)
    dihapus = 0
    for b in backups[3:]:
        try:
            waktu = _dt.datetime.strptime(b["dibuat_pada"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if waktu < batas:
            try:
                os.remove(b["path"])
                dihapus += 1
            except OSError:
                pass
    return dihapus


AMBANG_REMINDER_HARI = 7  # ambang "sudah lama tidak backup" -> tampil di Notifikasi/Dashboard


def status_reminder(backup_dir=None, ambang_hari=AMBANG_REMINDER_HARI):
    """Cek kesehatan backup untuk ditampilkan sbg notifikasi UI (Audit
    poin 5, tindak lanjut): kapan backup terakhir dibuat & apakah sudah
    melewati ambang wajar. Dipanggil dari logic.get_notifikasi() supaya
    tampil otomatis di Dashboard & panel Notifikasi tanpa operator harus
    membuka menu Backup & Restore lebih dulu untuk tahu keadaannya."""
    backups = list_backups(backup_dir)
    if not backups:
        return {
            "ada_backup": False,
            "hari_sejak_terakhir": None,
            "backup_terakhir": None,
            "perlu_reminder": True,
            "pesan": "Belum pernah ada backup database dibuat sama sekali.",
        }
    terbaru = backups[0]
    try:
        waktu = _dt.datetime.strptime(terbaru["dibuat_pada"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return {
            "ada_backup": True,
            "hari_sejak_terakhir": None,
            "backup_terakhir": terbaru["nama"],
            "perlu_reminder": False,
            "pesan": "",
        }
    hari = (_dt.datetime.now() - waktu).days
    perlu = hari >= ambang_hari
    pesan = (
        f"Backup terakhir {hari} hari lalu ({terbaru['nama']}) — sebaiknya " f"buat backup baru."
        if perlu
        else ""
    )
    return {
        "ada_backup": True,
        "hari_sejak_terakhir": hari,
        "backup_terakhir": terbaru["nama"],
        "perlu_reminder": perlu,
        "pesan": pesan,
    }


def validasi_file_restore(file_path):
    """Validasi ekstensi + isi (magic bytes) + skema minimal SEBELUM file
    dipakai untuk apa pun. Mengembalikan (ok: bool, pesan: str).
    Ini untuk file .db mentah (backup "cepat" / versi lama)."""
    if not file_path.lower().endswith(".db"):
        return False, "File harus berekstensi .db"
    try:
        ukuran = os.path.getsize(file_path)
    except OSError:
        return False, "File tidak bisa dibaca."
    if ukuran == 0:
        return False, "File kosong."
    if ukuran > MAKS_UKURAN_RESTORE_BYTES:
        return False, f"File terlalu besar (maks {MAKS_UKURAN_RESTORE_BYTES // (1024*1024)} MB)."
    try:
        with open(file_path, "rb") as fh:
            header = fh.read(16)
    except OSError:
        return False, "File tidak bisa dibaca."
    if header != SQLITE_MAGIC:
        return False, "Isi file bukan database SQLite yang valid (magic bytes tidak cocok)."
    try:
        conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
        existing = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        conn.close()
    except sqlite3.Error as e:
        return False, f"File rusak atau bukan database SIMPRODI: {e}"
    hilang = [t for t in TABEL_INTI_WAJIB if t not in existing]
    if hilang:
        return False, f"Skema tidak cocok — tabel inti tidak ditemukan: {', '.join(hilang)}"
    return True, "Valid."


def restore_dari_file(uploaded_path, db_path, backup_dir=None):
    """Restore dari file .db mentah (database saja) — WAJIB backup otomatis
    LENGKAP file lama dulu (jaga-jaga file salah upload / perlu dibatalkan),
    baru menimpa. Validasi (validasi_file_restore) harus sudah dipanggil &
    lolos SEBELUM fungsi ini dipanggil (dipisah supaya route bisa
    menampilkan pesan error validasi tanpa efek samping apa pun).
    Catatan: mode ini TIDAK menyentuh folder file fisik (dokumen/surat/dst)
    — kalau file restorasi berasal dari backup .db lama, dokumen fisik
    tetap seperti yang ada di komputer ini sekarang."""
    # Isolasi file upload ke folder sementara SENDIRI dulu (bukan dipakai
    # langsung dari lokasi aslinya) — jaga-jaga kalau lokasi itu ternyata
    # sama dengan folder backup (mis. operator meng-upload ulang file yang
    # sebelumnya diunduh dari menu ini sendiri), supaya proses backup
    # pra-restore di bawah TIDAK PERNAH bisa menimpa file yang justru
    # sedang dipakai sebagai sumber restore.
    with tempfile.TemporaryDirectory() as tmp_isolasi:
        aman_path = os.path.join(tmp_isolasi, "sumber_restore.db")
        shutil.copyfile(uploaded_path, aman_path)
        backup_pra_restore = backup_now_full(db_path, backup_dir)
        src = sqlite3.connect(aman_path)
        dst = sqlite3.connect(db_path)
        try:
            with dst:
                src.backup(dst)
        finally:
            src.close()
            dst.close()
    return backup_pra_restore


def _anggota_zip_aman(nama_entri, dest_dir):
    """Audit Lanjutan (Backup & Restore) — temuan keamanan: `restore_dari_
    file_zip()` sebelumnya memanggil `zipfile.ZipFile.extractall(tmp)`
    langsung terhadap isi file .zip yang DIUNGGAH PENGGUNA, tanpa
    memvalidasi nama tiap entri di dalamnya. Ini pola "zip slip" klasik
    (CVE-2007-4559 & turunannya) — sebuah entri zip dengan nama berisi
    `../../../` (path traversal) atau path absolut (mis. `/etc/passwd`
    atau `C:\\Windows\\...`) bisa membuat file diekstrak KELUAR dari
    folder tujuan yang dimaksud, berpotensi menimpa file sembarang di
    komputer yang menjalankan aplikasi ini. Python `zipfile` TIDAK
    menjamin perlindungan penuh dari ini di semua versi — jadi setiap
    nama entri divalidasi manual di sini sebelum diizinkan diekstrak:
    ditolak kalau path absolut, mengandung komponen `..`, atau kalau
    path hasil gabungan ternyata "kabur" keluar dari `dest_dir` setelah
    dinormalisasi. Dipakai sebelum ekstraksi zip backup restore (mode
    zip TIDAK dianggap tepercaya walau lolos validasi struktur/skema,
    karena skema hanya memeriksa isi data_prodi.db, bukan nama entri
    lain di dalam arsip)."""
    if os.path.isabs(nama_entri) or nama_entri.startswith(("/", "\\")):
        return False
    normalisasi = os.path.normpath(nama_entri)
    if normalisasi.startswith("..") or os.path.isabs(normalisasi):
        return False
    target = os.path.normpath(os.path.join(dest_dir, normalisasi))
    dest_abs = os.path.normpath(dest_dir)
    return target == dest_abs or target.startswith(dest_abs + os.sep)


def _ekstrak_zip_aman(zf, dest_dir):
    """Ekstrak seluruh isi `zf` ke `dest_dir`, menolak (melempar ValueError)
    kalau ada entri yang mencoba keluar dari `dest_dir` (lihat
    `_anggota_zip_aman`). Pengganti `zf.extractall(dest_dir)` mentah."""
    for info in zf.infolist():
        if not _anggota_zip_aman(info.filename, dest_dir):
            raise ValueError(
                f"Arsip zip berisi entri tidak aman ('{info.filename}') — "
                "kemungkinan mencoba menulis file di luar folder tujuan, "
                "restore dibatalkan demi keamanan."
            )
    zf.extractall(dest_dir)


def validasi_file_restore_zip(file_path):
    """Validasi file .zip hasil Backup Lengkap SEBELUM dipakai untuk apa
    pun: ekstensi, ukuran, struktur zip valid, wajib berisi data_prodi.db,
    dan isi database di dalamnya wajib lolos pemeriksaan skema minimal yang
    sama dengan restore .db biasa. Mengembalikan (ok: bool, pesan: str)."""
    if not file_path.lower().endswith(".zip"):
        return False, "File harus berekstensi .zip (hasil unduhan Backup Lengkap)."
    try:
        ukuran = os.path.getsize(file_path)
    except OSError:
        return False, "File tidak bisa dibaca."
    if ukuran == 0:
        return False, "File kosong."
    if ukuran > MAKS_UKURAN_RESTORE_ZIP_BYTES:
        return (
            False,
            f"File terlalu besar (maks {MAKS_UKURAN_RESTORE_ZIP_BYTES // (1024*1024)} MB).",
        )
    try:
        with zipfile.ZipFile(file_path) as zf:
            bad = zf.testzip()
            if bad is not None:
                return False, f"Arsip zip rusak pada entri: {bad}"
            names = zf.namelist()
            if DB_ARCNAME not in names:
                return (
                    False,
                    "File zip tidak berisi data_prodi.db — bukan hasil Backup Lengkap SIMPRODI yang sah.",
                )
            # Audit Lanjutan (Backup & Restore) — tolak arsip yang berisi
            # entri "tidak aman" (path absolut / ../ path traversal, lihat
            # _anggota_zip_aman) SEDINI mungkin, sebelum operator sempat
            # mengonfirmasi password & sebelum backup pra-restore dibuat,
            # bukan baru ketahuan saat proses ekstraksi sudah berjalan.
            with tempfile.TemporaryDirectory() as _tmp_cek:
                entri_tak_aman = [n for n in names if not _anggota_zip_aman(n, _tmp_cek)]
            if entri_tak_aman:
                return False, (
                    "Arsip zip berisi entri path yang tidak aman "
                    f"('{entri_tak_aman[0]}') — kemungkinan bukan backup sah, restore ditolak."
                )
            with tempfile.TemporaryDirectory() as tmp:
                zf.extract(DB_ARCNAME, tmp)
                ok, pesan = validasi_file_restore(os.path.join(tmp, DB_ARCNAME))
                if not ok:
                    return False, f"Database di dalam zip tidak valid: {pesan}"
    except zipfile.BadZipFile:
        return False, "File rusak atau bukan format .zip yang valid."
    return True, "Valid."


def restore_dari_file_zip(uploaded_zip_path, db_path, backup_dir=None, data_root=None):
    """Restore LENGKAP dari file .zip (database + seluruh folder file
    fisik). WAJIB backup-lengkap-otomatis dulu sebelum menimpa apa pun
    (jaga-jaga file salah upload / perlu dibatalkan). Validasi
    (validasi_file_restore_zip) harus sudah dipanggil & lolos SEBELUM
    fungsi ini dipanggil. Folder file fisik yang ADA di dalam zip akan
    MENGGANTI folder yang sama di komputer ini (bukan digabung) — folder
    yang TIDAK ADA di dalam zip (mis. backup lama sebelum modul tsb ada)
    dibiarkan apa adanya, tidak dihapus."""
    data_root = data_root or get_data_root()
    with tempfile.TemporaryDirectory() as tmp:
        # Ekstrak isi zip sumber restore LEBIH DULU ke folder sementara —
        # supaya proses backup pra-restore di bawah (yang membuat file .zip
        # BARU di backup_dir) tidak pernah bisa menimpa/mengganggu file zip
        # sumber aslinya, sekalipun sumbernya kebetulan berada di backup_dir
        # yang sama (mis. operator meng-upload ulang file yang sebelumnya
        # diunduh dari menu Riwayat Backup ini sendiri).
        with zipfile.ZipFile(uploaded_zip_path) as zf:
            _ekstrak_zip_aman(zf, tmp)

        backup_pra_restore = backup_now_full(db_path, backup_dir)

        tmp_db = os.path.join(tmp, DB_ARCNAME)
        src = sqlite3.connect(tmp_db)
        dst = sqlite3.connect(db_path)
        try:
            with dst:
                src.backup(dst)
        finally:
            src.close()
            dst.close()

        tmp_files_root = os.path.join(tmp, FILES_PREFIX)
        if os.path.isdir(tmp_files_root):
            for folder, _deskripsi in DATA_SUBFOLDERS:
                src_folder = os.path.join(tmp_files_root, folder)
                if not os.path.isdir(src_folder):
                    continue  # folder ini tidak ada di dalam backup — jangan sentuh yang ada sekarang
                dest_folder = os.path.join(data_root, folder)
                if os.path.isdir(dest_folder):
                    shutil.rmtree(dest_folder)
                shutil.copytree(src_folder, dest_folder)
    return backup_pra_restore
