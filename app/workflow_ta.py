# -*- coding: utf-8 -*-
"""
workflow_ta.py — Audit Menyeluruh, PHASE 3: TA Workflow Engine.

Sebelum modul ini ada, aturan "status_ta boleh berubah dari mana ke mana"
tersirat begitu saja di dalam logic.py::recalculate_status_ta() sebagai
urutan if/elif — benar secara perilaku (sudah diperbaiki di Phase 1: P0
#1-#3), tapi tidak ada satu tempat yang secara EKSPLISIT mendokumentasikan
graf transisi yang dianggap wajar, dan tidak ada jejak riwayat kapan/kenapa
sebuah mahasiswa berpindah status.

Modul ini menambahkan dua hal di atas fondasi Phase 1, TANPA mengubah
logika penentuan status itu sendiri (itu tetap tanggung jawab
recalculate_status_ta — modul ini hanya "membungkus" hasilnya):

1. TRANSISI_TA — peta eksplisit status -> {status tujuan yang wajar}.
   Dipakai untuk MENANDAI (bukan MEMBLOKIR) transisi yang di luar peta
   sebagai `wajar=0` di riwayat. Sengaja tidak memblokir: aplikasi ini
   1 admin offline (lihat PERAN_KAPRODI), dan operator harus tetap bisa
   membetulkan data yang salah input tanpa dihalangi mesin state — yang
   penting transisi ganjil itu TERCATAT dan TERLIHAT, bukan tersembunyi.
2. catat_transisi() — audit event: setiap kali status_ta BENAR-BENAR
   berubah nilainya, dicatat ke tabel status_ta_riwayat (status lama, baru,
   pemicu, wajar/tidak, waktu). Ini pelengkap log_aktivitas yang generik
   (aksi+detail bebas teks) dengan jejak terstruktur khusus status_ta yang
   bisa ditelusuri per mahasiswa.
"""

from app import constants as C

# Graf transisi yang dianggap WAJAR dalam alur normal. Dibaca sebagai
# "dari status X, tujuan yang wajar adalah salah satu dari set berikut".
# Tidak dipakai untuk mem-veto apa pun (lihat catatan modul di atas) —
# hanya untuk memberi label wajar/tidak-wajar di riwayat.
TRANSISI_TA = {
    C.STATUS_TA_BELUM: {C.STATUS_TA_MENGAJUKAN},
    C.STATUS_TA_MENGAJUKAN: {C.STATUS_TA_BIMBINGAN, C.STATUS_TA_BELUM},
    C.STATUS_TA_BIMBINGAN: {
        C.STATUS_TA_LULUS,
        C.STATUS_TA_TIDAK_LULUS,
        C.STATUS_TA_TUNDA,
        C.STATUS_TA_MENGAJUKAN,
    },
    C.STATUS_TA_TUNDA: {C.STATUS_TA_LULUS, C.STATUS_TA_TIDAK_LULUS, C.STATUS_TA_BIMBINGAN},
    C.STATUS_TA_TIDAK_LULUS: {C.STATUS_TA_LULUS, C.STATUS_TA_BIMBINGAN},
    C.STATUS_TA_LULUS: {C.STATUS_TA_MENUNGGU_WISUDA, C.STATUS_TA_BIMBINGAN},
    C.STATUS_TA_MENUNGGU_WISUDA: {C.STATUS_TA_LULUS},
    # STATUS_TA_SUDAH_SIDANG dipertahankan di STATUS_TA_LIST demi kompatibilitas
    # data lama (mis. hasil impor Excel era sebelum audit ini), tapi
    # recalculate_status_ta() TIDAK PERNAH lagi menghasilkan nilai ini sejak
    # Phase 1 (P0 #1) — tidak butuh entri transisi keluar di sini.
}


def transisi_wajar(status_lama, status_baru):
    """True kalau (status_lama -> status_baru) ada di TRANSISI_TA, atau
    kalau status_lama None (baris mahasiswa baru, belum punya riwayat sama
    sekali — bukan "transisi", jadi selalu wajar)."""
    if status_lama is None or status_lama == status_baru:
        return True
    return status_baru in TRANSISI_TA.get(status_lama, set())


def catat_transisi(conn, mahasiswa_id, status_lama, status_baru, dipicu_oleh=None):
    """Audit event Phase 3 — dipanggil oleh logic.recalculate_status_ta()
    HANYA saat status_ta benar-benar berubah (status_lama != status_baru).
    `dipicu_oleh` adalah teks bebas singkat yang menjelaskan asal
    perubahan (mis. "Sidang disimpan — LULUS", "SK Pembimbing dihapus"),
    diisi oleh pemanggil recalculate_status_ta() di masing-masing route."""
    conn.execute(
        "INSERT INTO status_ta_riwayat(mahasiswa_id, status_lama, status_baru, dipicu_oleh, wajar) "
        "VALUES(?,?,?,?,?)",
        (
            mahasiswa_id,
            status_lama,
            status_baru,
            dipicu_oleh,
            1 if transisi_wajar(status_lama, status_baru) else 0,
        ),
    )
    conn.commit()


def riwayat_mahasiswa(conn, mahasiswa_id):
    """Riwayat transisi status_ta 1 mahasiswa, urut kronologis (lama -> baru
    di layar, sesuai kebiasaan timeline)."""
    return conn.execute(
        "SELECT * FROM status_ta_riwayat WHERE mahasiswa_id=? ORDER BY id ASC",
        (mahasiswa_id,),
    ).fetchall()
