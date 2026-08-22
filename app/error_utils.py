# -*- coding: utf-8 -*-
"""app/error_utils.py — Audit: penanganan galat basis data yang seragam.

Latar belakang: hampir setiap handler POST yang menyimpan data punya pola
berulang di seluruh basis kode (33+ kejadian di 15+ file app/routes/):

    except Exception as e:
        flash(f"Gagal menyimpan: {e}", "error")

Pola ini punya dua masalah sistemik:

1. Pesan mentah dari SQLite (mis. "UNIQUE constraint failed: dosen.nidn"
   atau "NOT NULL constraint failed: mahasiswa.nim") langsung ditampilkan
   ke pengguna (Kaprodi, bukan programmer) — tidak actionable.
2. `except Exception` menangkap SEMUA jenis error, termasuk bug pemrograman
   (TypeError/AttributeError/KeyError). Kesalahan logika yang seharusnya
   kelihatan & gagal saat testing malah tertelan diam-diam, hanya muncul
   sebagai flash message generik yang menyesatkan (seolah-olah "salah
   input", padahal sebenarnya bug).

Modul ini menyediakan SATU titik terpusat untuk:
- Menerjemahkan galat basis data yang WAJAR (constraint gagal karena input
  pengguna: UNIQUE/NOT NULL/FOREIGN KEY/CHECK) ke bahasa manusia, dengan
  fallback aman untuk kolom yang belum dikenal secara eksplisit.
- Memisahkannya dari galat TAK TERDUGA (kemungkinan bug), yang tetap
  dicatat penuh (traceback) ke logger aplikasi supaya tidak lolos tanpa
  jejak — pengguna tetap dapat pesan ramah, tapi developer tetap bisa
  melacak akar masalahnya lewat log.
"""

import logging
import re
import sqlite3

from flask import flash

logger = logging.getLogger("simprodi")

# Label kolom yang sering memicu constraint UNIQUE/NOT NULL, dipetakan ke
# istilah yang dikenal pengguna. Kolom yang tidak terdaftar di sini tetap
# mendapat pesan yang layak lewat fallback otomatis (lihat _label()).
_LABEL_KOLOM = {
    "nidn": "NIDN",
    "nim": "NIM",
    "nip": "NIP",
    "nik": "NIK",
    "nuptk": "NUPTK",
    "no_sk": "Nomor SK",
    "kode_mk": "Kode Mata Kuliah",
    "kode": "Kode",
    "nama": "Nama",
    "email": "Email",
    "email_nik": "Email/NIK",
    "username": "Nama pengguna",
    "no_hp": "No. HP",
    "nomor": "Nomor",
    "no_urut": "Nomor urut",
    "no_dokumen": "Nomor dokumen",
    "no_seri_ijazah": "Nomor seri ijazah",
}


def _label(kolom: str) -> str:
    kolom = kolom.strip()
    if kolom in _LABEL_KOLOM:
        return _LABEL_KOLOM[kolom]
    return kolom.replace("_", " ").strip().capitalize()


def pesan_ramah_db(exc: Exception):
    """Terjemahkan pesan galat sqlite3 mentah jadi kalimat berbahasa
    manusia. Mengembalikan None kalau polanya tidak dikenali sama sekali
    (pemanggil memakai fallback generiknya sendiri)."""
    teks = str(exc)

    m = re.search(r"UNIQUE constraint failed: (\S+)", teks)
    if m:
        kolom_list = [c.strip().split(".")[-1] for c in m.group(1).split(",")]
        labels = [_label(k) for k in kolom_list]
        return f"{' / '.join(labels)} ini sudah terdaftar sebelumnya — gunakan nilai lain."

    m = re.search(r"NOT NULL constraint failed: (\S+)", teks)
    if m:
        kolom = _label(m.group(1).split(".")[-1])
        return f'Kolom "{kolom}" wajib diisi.'

    if "FOREIGN KEY constraint failed" in teks:
        return (
            "Data terkait tidak ditemukan atau masih dipakai data lain — "
            "periksa kembali pilihan yang dipilih di formulir ini."
        )

    m = re.search(r"CHECK constraint failed: (\S+)", teks)
    if m:
        return "Nilai yang dimasukkan tidak sesuai aturan yang diizinkan untuk data ini."

    if isinstance(exc, sqlite3.IntegrityError):
        return "Data yang dimasukkan bertentangan dengan data yang sudah ada."
    if isinstance(exc, sqlite3.OperationalError):
        return "Basis data sedang tidak bisa diakses (mungkin sedang dipakai proses lain). Coba lagi sesaat lagi."

    # Galat berkas/OS — relevan untuk routes/backup.py (backup/restore) dan
    # modul lain yang menulis file (unggah dokumen, ekspor, dsb).
    if isinstance(exc, PermissionError):
        return "Tidak ada izin akses ke berkas/folder tujuan. Periksa hak akses folder aplikasi."
    if isinstance(exc, FileNotFoundError):
        return "Berkas yang dituju tidak ditemukan — mungkin sudah dipindah atau dihapus."
    if isinstance(exc, OSError):
        errno_val = getattr(exc, "errno", None)
        if errno_val == 28:  # ENOSPC
            return "Ruang penyimpanan penuh — kosongkan sebagian ruang disk lalu coba lagi."
        return (
            "Terjadi kendala pada berkas/sistem (mis. disk penuh atau berkas terkunci proses lain)."
        )
    return None


def flash_gagal_simpan(exc: Exception, konteks: str = "Gagal menyimpan data"):
    """Titik terpusat penanganan galat pada handler POST simpan/hapus.

    - sqlite3.IntegrityError / sqlite3.OperationalError (galat basis data
      yang WAJAR karena input pengguna) -> diterjemahkan ke bahasa manusia
      lewat pesan_ramah_db(), ditampilkan lewat flash dengan `konteks` di
      depan sebagai judul singkat.
    - Exception lain (kemungkinan bug pemrograman) -> TIDAK ditelan diam-
      diam jadi flash generik. Dicatat penuh (traceback) ke logger aplikasi
      (kelihatan di konsol/log saat pengembangan & pengujian), pengguna
      tetap dapat pesan ramah tanpa detail teknis mentah.
    """
    if isinstance(exc, (sqlite3.IntegrityError, sqlite3.OperationalError, OSError)):
        detail = pesan_ramah_db(exc)
        if detail:
            flash(f"{konteks} — {detail}", "error")
        else:
            flash(f"{konteks} — data bertentangan dengan aturan yang berlaku.", "error")
        return

    # Galat tak terduga (bug pemrograman) — jangan ditelan diam-diam.
    logger.exception("%s (galat tak terduga)", konteks)
    flash(f"{konteks} — terjadi kesalahan tak terduga. Silakan coba lagi.", "error")


def pesan_ramah_import(exc: Exception) -> str:
    """Varian ringkas untuk laporan impor massal (import_excel.py,
    import_generic.py) — dipakai per-baris di ringkasan hasil impor, jadi
    tetap butuh cukup detail bagi operator untuk mengenali baris yang
    bermasalah, tapi tanpa istilah SQL mentah kalau bisa diterjemahkan."""
    ramah = pesan_ramah_db(exc)
    if ramah:
        return ramah
    return f"gagal diproses ({exc})"
