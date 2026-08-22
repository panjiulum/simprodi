# -*- coding: utf-8 -*-
"""
logic.py — Rekap & laporan otomatis.

Setiap fungsi di sini adalah versi Python dari formula Excel yang SUDAH
diperbaiki menurut sheet CHANGELOG/AUDIT REPORT pada file asal, contoh:
  - Rekap Pembimbing: status sidang pakai logika "LULUS-priority"
    (COUNTIFS+MATCH) bukan MATCH pertama saja -> mahasiswa sidang ulang
    yang akhirnya LULUS tidak lagi salah tampil TIDAK LULUS.
  - Dashboard: tidak ada lagi nilai sentinel (9999) yang bocor ke tampilan.
  - Taksonomi status: satu kamus resmi (constants.py), tidak lagi rawan
    beda ejaan antar-sheet seperti pada file Excel asal.
"""

import datetime

from app import backup_core
from app import constants as C
from app import datetools as dt
from app.constants import ipk_ke_predikat, nilai_angka_ke_huruf_yudisium


def dosen_nama(conn, dosen_id):
    if not dosen_id:
        return ""
    row = conn.execute("SELECT nama FROM dosen WHERE id=?", (dosen_id,)).fetchone()
    return row["nama"] if row else ""


def status_seminar_mahasiswa(conn, mahasiswa_id):
    """Antisipasi 'seminar ulang' — sama seperti status_sidang_mahasiswa()
    di bawah, dipakai logika 'Selesai-priority': kalau mahasiswa PERNAH
    seminar dgn status 'Selesai' di baris manapun, status akhirnya
    'Selesai' (tidak peduli ada baris seminar lain yang 'Batal', dst).
    Kalau belum pernah 'Selesai', ambil baris terakhir (ORDER BY id)."""
    rows = conn.execute(
        "SELECT status FROM seminar WHERE mahasiswa_id=? ORDER BY id", (mahasiswa_id,)
    ).fetchall()
    if not rows:
        return "Belum Seminar"
    for r in rows:
        if r["status"] == "Selesai":
            return "Selesai"
    return rows[-1]["status"] or "Belum Seminar"


def status_sidang_mahasiswa(conn, mahasiswa_id):
    """Logika LULUS-priority: jika mahasiswa PERNAH lulus sidang (di baris
    manapun), status akhirnya LULUS. Jika tidak, ambil sidang terakhir."""
    rows = conn.execute(
        "SELECT status_kelulusan FROM sidang WHERE mahasiswa_id=? ORDER BY id",
        (mahasiswa_id,),
    ).fetchall()
    if not rows:
        return "Belum Sidang"
    for r in rows:
        if r["status_kelulusan"] == "LULUS":
            return "LULUS"
    return rows[-1]["status_kelulusan"] or "Belum Sidang"


def _status_seminar_batch(conn, mahasiswa_ids):
    """Audit Rekap & Statistik (temuan N+1) — versi BATCH dari
    status_seminar_mahasiswa(): SATU query utk sekumpulan mahasiswa
    sekaligus (lewat IN (...)), bukan satu query per mahasiswa_id di dalam
    loop seperti sebelumnya. Dipakai di rekap_rasio_dosen(),
    rekap_pembimbing(), rekap_status_mahasiswa() -- ketiganya sebelumnya
    memanggil status_seminar_mahasiswa() satu-satu per mahasiswa di dalam
    loop per dosen/baris (pola N+1 klasik: jumlah query bertumbuh sebanding
    dosen x mahasiswa_bimbingan, bukan konstan). Kontrak hasil PERSIS sama
    dgn status_seminar_mahasiswa() dipanggil satu-satu.

    Antisipasi 'seminar ulang' — tabel `seminar` sekarang boleh punya
    lebih dari 1 baris per mahasiswa (lihat _rebuild_seminar_tanpa_unique
    di db.py), jadi versi batch ini mereplikasi logika 'Selesai-priority'
    yang sama seperti status_seminar_mahasiswa() di atas (dan seperti pola
    LULUS-priority pada _status_sidang_batch() di bawah), bukan lagi
    asumsi 1 baris = 1 mahasiswa. Return dict {mahasiswa_id: status}."""
    mahasiswa_ids = [mid for mid in mahasiswa_ids if mid]
    if not mahasiswa_ids:
        return {}
    placeholders = ",".join("?" * len(mahasiswa_ids))
    rows = conn.execute(
        f"SELECT mahasiswa_id, status FROM seminar WHERE mahasiswa_id IN ({placeholders}) "
        "ORDER BY id",
        list(mahasiswa_ids),
    ).fetchall()
    selesai_ids = set()
    terakhir = {}
    for r in rows:
        mid = r["mahasiswa_id"]
        terakhir[mid] = r["status"] or "Belum Seminar"
        if r["status"] == "Selesai":
            selesai_ids.add(mid)
    out = {}
    for mid in set(mahasiswa_ids):
        if mid in selesai_ids:
            out[mid] = "Selesai"
        elif mid in terakhir:
            out[mid] = terakhir[mid]
    return out


def _status_sidang_batch(conn, mahasiswa_ids):
    """Audit Rekap & Statistik (temuan N+1) — versi BATCH dari
    status_sidang_mahasiswa(), SATU query (bukan satu per mahasiswa),
    mereplikasi PERSIS logika LULUS-priority aslinya: kalau mahasiswa
    PERNAH lulus di baris manapun -> 'LULUS' menang, kalau tidak -> ambil
    baris terakhir (urutan ORDER BY id dipertahankan lewat pemrosesan
    berurutan di Python). Lihat _status_seminar_batch() di atas utk alasan
    lengkap kenapa versi batch ini dibutuhkan. Return dict
    {mahasiswa_id: status}, mahasiswa_id yg tidak ada baris sidang-nya
    TIDAK muncul di dict (pemanggil pakai .get(mid, 'Belum Sidang'),
    sama seperti fallback status_sidang_mahasiswa() aslinya)."""
    mahasiswa_ids = [mid for mid in mahasiswa_ids if mid]
    if not mahasiswa_ids:
        return {}
    placeholders = ",".join("?" * len(mahasiswa_ids))
    rows = conn.execute(
        f"SELECT mahasiswa_id, status_kelulusan FROM sidang WHERE mahasiswa_id IN ({placeholders}) "
        "ORDER BY id",
        list(mahasiswa_ids),
    ).fetchall()
    lulus_ids = set()
    terakhir = {}
    for r in rows:
        mid = r["mahasiswa_id"]
        terakhir[mid] = r["status_kelulusan"] or "Belum Sidang"
        if r["status_kelulusan"] == "LULUS":
            lulus_ids.add(mid)
    out = {}
    for mid in set(mahasiswa_ids):
        if mid in lulus_ids:
            out[mid] = "LULUS"
        elif mid in terakhir:
            out[mid] = terakhir[mid]
    return out


def validasi_transisi_status(conn, mahasiswa_id, tujuan):
    """Audit poin 6.3 — cegah alur mundur yang tidak masuk akal (mis. dosen
    input Sidang padahal Seminar belum "Selesai"). Mengembalikan list pesan
    peringatan (string) — TIDAK melempar exception; route pemanggil yang
    memutuskan apakah ini blocking (minta konfirmasi ulang, mengikuti pola
    UX 'konfirmasi bentrok' yang sudah ada) atau sekadar ditampilkan.

    `tujuan` salah satu: "Seminar", "Sidang"."""
    peringatan = []
    if tujuan == "Sidang":
        status_seminar = status_seminar_mahasiswa(conn, mahasiswa_id)
        if status_seminar != "Selesai":
            peringatan.append(
                f'Mahasiswa ini belum menyelesaikan Seminar Proposal (status saat ini: "{status_seminar}"). '
                f"Biasanya Sidang baru dijadwalkan setelah Seminar berstatus Selesai."
            )
    return peringatan


# Audit Menyeluruh — P0 #1, #2, #3 (bug status_ta setelah sidang dihapus +
# state machine status_ta yang tersebar di banyak route).
#
# SEBELUM perbaikan ini, status_ta dihitung/ditulis lewat 4 jalur berbeda
# yang tidak saling tahu satu sama lain:
#   - routes/akademik.py::pengajuan_simpan()  (UPDATE ... WHERE status_ta=lama)
#   - routes/akademik.py::penetapan_simpan()  (TIDAK PERNAH menyentuh status_ta
#     sama sekali -- SK Pembimbing terbit tapi status mahasiswa bisa tetap
#     "Mengajukan Judul")
#   - routes/pelaksanaan.py::_sync_status_ta_sidang()  (HANYA melihat tabel
#     sidang; kalau baris sidang satu-satunya seorang mahasiswa dihapus,
#     status_sidang_mahasiswa() mengembalikan "Belum Sidang", yang TIDAK ADA
#     di dict mapping-nya -> jatuh ke default STATUS_TA_SUDAH_SIDANG. Bug
#     nyata: hapus sidang mestinya MENGEMBALIKAN status_ta ke sebelum
#     sidang, bukan malah menaikkannya jadi "Sudah Sidang".)
#   - mahasiswa_form.html <select name="status_ta"> -- operator bisa
#     menimpa status_ta manual lewat form Data Mahasiswa, lepas dari histori
#     pengajuan/pembimbing/seminar/sidang yang sebenarnya.
#
# recalculate_status_ta() di bawah ini menggantikan SEMUA jalur penulisan
# status_ta yang berasal dari histori TA (form Data Mahasiswa sengaja
# dijadikan read-only, lihat mahasiswa_form.html) -- satu fungsi, satu
# aturan prioritas, dipanggil ULANG (bukan cuma "maju") setiap kali salah
# satu dari pengajuan_judul / penetapan_pembimbing / seminar / sidang
# ditambah, diedit, ATAU DIHAPUS, supaya status_ta selalu mencerminkan
# histori yang BENAR-BENAR ADA di database saat ini -- termasuk mundur.
_STATUS_TA_DARI_SIDANG = {
    "LULUS": C.STATUS_TA_LULUS,
    "TIDAK LULUS": C.STATUS_TA_TIDAK_LULUS,
    "TUNDA": C.STATUS_TA_TUNDA,
}


def recalculate_status_ta(conn, mahasiswa_id, dipicu_oleh=None):
    """Hitung ulang & simpan status_ta mahasiswa dari histori TA yang
    sebenarnya ada di database. Aman dipanggil berkali-kali (idempoten) dan
    aman dipanggil setelah operasi HAPUS (akan mundur dengan benar, bukan
    diam-diam melompat ke status yang lebih tinggi seperti bug lama).

    Prioritas, dari yang paling akhir ke paling awal:
      1. Sidang berstatus LULUS / TIDAK LULUS / TUNDA (baris manapun,
         LULUS menang jika pernah LULUS -- lihat status_sidang_mahasiswa)
      2. Seminar "Selesai" ATAU sudah ada SK Penetapan Pembimbing -> Proses
         Bimbingan
      3. Ada baris Pengajuan Judul berstatus final "Disetujui" -> Proses
         Bimbingan; ada baris Pengajuan Judul (status apa pun) -> Mengajukan
         Judul
      4. Tidak ada histori TA sama sekali -> Belum Mengajukan Judul

    "Menunggu Wisuda" SENGAJA tidak ditimpa balik ke LULUS oleh fungsi ini:
    itu tahap administratif setelah sidang yang dikelola khusus oleh modul
    Yudisium (kelulusan.py::yudisium_simpan), bukan bagian dari rantai
    pengajuan->pembimbing->seminar->sidang yang dihitung di sini.

    Audit Phase 3 (TA Workflow Engine) — parameter `dipicu_oleh` (teks
    bebas singkat, mis. "Sidang disimpan", "SK Pembimbing dihapus") dicatat
    ke status_ta_riwayat lewat workflow_ta.catat_transisi() HANYA saat
    status_ta benar-benar berubah nilainya, bukan setiap kali fungsi ini
    dipanggil -- fungsi ini dipanggil sangat sering (setiap simpan/hapus di
    4 modul berbeda), sebagian besar panggilan tidak menghasilkan
    perubahan apa pun."""
    row = conn.execute("SELECT status_ta FROM mahasiswa WHERE id=?", (mahasiswa_id,)).fetchone()
    if not row:
        return
    status_saat_ini = row["status_ta"]

    status_sidang = status_sidang_mahasiswa(conn, mahasiswa_id)
    if status_sidang in _STATUS_TA_DARI_SIDANG:
        if status_saat_ini == C.STATUS_TA_MENUNGGU_WISUDA:
            return  # sudah diproses lanjut oleh modul Yudisium, jangan mundur
        baru = _STATUS_TA_DARI_SIDANG[status_sidang]
        if baru != status_saat_ini:
            conn.execute("UPDATE mahasiswa SET status_ta=? WHERE id=?", (baru, mahasiswa_id))
            conn.commit()
            from app import workflow_ta

            workflow_ta.catat_transisi(conn, mahasiswa_id, status_saat_ini, baru, dipicu_oleh)
        sync_yudisium_dari_sidang(conn)
        sync_wisuda_dari_yudisium(conn)
        return

    # Tidak ada baris sidang yang menyimpulkan (kasus normal: belum sidang
    # sama sekali, ATAU baris sidang satu-satunya baru saja dihapus) ->
    # tentukan status dari bukti pra-sidang yang tersisa.
    status_seminar = status_seminar_mahasiswa(conn, mahasiswa_id)
    ada_sk_pembimbing = conn.execute(
        "SELECT 1 FROM penetapan_pembimbing WHERE mahasiswa_id=? LIMIT 1", (mahasiswa_id,)
    ).fetchone()
    pengajuan_terakhir = conn.execute(
        "SELECT status_final FROM pengajuan_judul WHERE mahasiswa_id=? ORDER BY id DESC LIMIT 1",
        (mahasiswa_id,),
    ).fetchone()

    if status_seminar == "Selesai" or ada_sk_pembimbing:
        baru = C.STATUS_TA_BIMBINGAN
    elif pengajuan_terakhir:
        baru = (
            C.STATUS_TA_BIMBINGAN
            if pengajuan_terakhir["status_final"] == "Disetujui"
            else C.STATUS_TA_MENGAJUKAN
        )
    else:
        baru = C.STATUS_TA_BELUM

    if baru != status_saat_ini:
        conn.execute("UPDATE mahasiswa SET status_ta=? WHERE id=?", (baru, mahasiswa_id))
        conn.commit()
        from app import workflow_ta

        workflow_ta.catat_transisi(conn, mahasiswa_id, status_saat_ini, baru, dipicu_oleh)


def rekap_pembimbing(conn, tahap_filter=None):
    """Setara sheet 'Rekap Pembimbing': per dosen pembimbing1/pembimbing2,
    daftar mahasiswa + status seminar + status sidang (auto-sync)."""
    q = """
        SELECT pp.*, m.nama AS nama_mhs, m.nim
        FROM penetapan_pembimbing pp
        JOIN mahasiswa m ON m.id = pp.mahasiswa_id
    """
    params = []
    if tahap_filter and tahap_filter != "Semua":
        q += " WHERE pp.tahap LIKE ?"
        params.append(f"%{tahap_filter}%")
    rows = conn.execute(q, params).fetchall()

    # Audit Rekap & Statistik (temuan N+1) — status seminar/sidang diambil
    # BATCH sekali di awal (lihat _status_seminar_batch/_status_sidang_batch),
    # bukan dipanggil satu-satu di dalam loop per baris seperti sebelumnya.
    semua_mid = [r["mahasiswa_id"] for r in rows]
    status_seminar_map = _status_seminar_batch(conn, semua_mid)
    status_sidang_map = _status_sidang_batch(conn, semua_mid)

    by_dosen = {}
    for r in rows:
        for role, dosen_id in (
            ("pembimbing_1", r["pembimbing1_id"]),
            ("pembimbing_2", r["pembimbing2_id"]),
        ):
            if not dosen_id:
                continue
            # Audit Rekap & Statistik (temuan N+1, ikut ditambal) —
            # dosen_nama() dulu dipanggil TANPA SYARAT di setiap baris
            # (1 query per baris walau dosen yg sama sudah pernah
            # dicatat), sekarang cuma dipanggil sekali per dosen baru
            # (saat entry belum ada di by_dosen).
            if dosen_id not in by_dosen:
                by_dosen[dosen_id] = {
                    "nama": dosen_nama(conn, dosen_id),
                    "pembimbing_1": [],
                    "pembimbing_2": [],
                }
            entry = by_dosen[dosen_id]
            entry[role].append(
                {
                    "nim": r["nim"],
                    "nama": r["nama_mhs"],
                    "status_seminar": status_seminar_map.get(r["mahasiswa_id"], "Belum Seminar"),
                    "status_sidang": status_sidang_map.get(r["mahasiswa_id"], "Belum Sidang"),
                }
            )
    return by_dosen


def rekap_status_mahasiswa(conn):
    """Setara sheet 'Rekap Status Mahasiswa': ringkasan total ber-SK
    pembimbing, sudah/belum seminar, sudah/belum sidang, lulus/tidak/tunda."""
    ids = [
        r["mahasiswa_id"]
        for r in conn.execute("SELECT mahasiswa_id FROM penetapan_pembimbing").fetchall()
    ]
    total = len(ids)
    sudah_sem = belum_sem = sudah_sid = belum_sid = lulus = tidak_lulus = tunda = 0
    detail = []
    if ids:
        # Audit Rekap & Statistik (temuan N+1) — mahasiswa + status
        # seminar/sidang diambil BATCH (bukan satu query per mid di dalam
        # loop), lihat _status_seminar_batch/_status_sidang_batch di atas.
        placeholders = ",".join("?" * len(ids))
        mhs_map = {
            r["id"]: r
            for r in conn.execute(
                f"SELECT id, nim, nama FROM mahasiswa WHERE id IN ({placeholders})", ids
            ).fetchall()
        }
        status_seminar_map = _status_seminar_batch(conn, ids)
        status_sidang_map = _status_sidang_batch(conn, ids)
    else:
        mhs_map, status_seminar_map, status_sidang_map = {}, {}, {}
    for mid in ids:
        m = mhs_map[mid]
        ss = status_seminar_map.get(mid, "Belum Seminar")
        sd = status_sidang_map.get(mid, "Belum Sidang")
        if ss == "Selesai":
            sudah_sem += 1
        else:
            belum_sem += 1
        if sd == "Belum Sidang":
            belum_sid += 1
        else:
            sudah_sid += 1
            if sd == "LULUS":
                lulus += 1
            elif sd == "TIDAK LULUS":
                tidak_lulus += 1
            elif sd == "TUNDA":
                tunda += 1
        detail.append(
            {"nim": m["nim"], "nama": m["nama"], "status_seminar": ss, "status_sidang": sd}
        )
    return {
        "total": total,
        "sudah_seminar": sudah_sem,
        "belum_seminar": belum_sem,
        "sudah_sidang": sudah_sid,
        "belum_sidang": belum_sid,
        "lulus": lulus,
        "tidak_lulus": tidak_lulus,
        "tunda": tunda,
        "detail": detail,
    }


def dashboard_counts(conn):
    """Setara kartu KPI 'DASHBOARD' — dihitung dari status_ta resmi
    (bukan lagi rentan salah kolom seperti bug I7 vs K7 pada file asal)."""
    from app.constants import STATUS_TA_LIST

    counts = {s: 0 for s in STATUS_TA_LIST}
    for r in conn.execute("SELECT status_ta, COUNT(*) c FROM mahasiswa GROUP BY status_ta"):
        if r["status_ta"] in counts:
            counts[r["status_ta"]] = r["c"]
    counts["total"] = sum(counts[s] for s in STATUS_TA_LIST)

    nilai_row = conn.execute(
        "SELECT MIN(nilai_angka) mn, MAX(nilai_angka) mx, AVG(nilai_angka) av "
        "FROM sidang WHERE status_kelulusan='LULUS' AND nilai_angka IS NOT NULL"
    ).fetchone()
    counts["nilai_terendah"] = nilai_row["mn"] if nilai_row["mn"] is not None else None
    counts["nilai_tertinggi"] = nilai_row["mx"] if nilai_row["mx"] is not None else None
    counts["nilai_rata2"] = round(nilai_row["av"], 2) if nilai_row["av"] is not None else None
    counts["jml_dosen"] = conn.execute("SELECT COUNT(*) c FROM dosen WHERE aktif=1").fetchone()["c"]
    return counts


def sync_yudisium_dari_sidang(conn):
    """Setara sheet 'Rencana Yudisium' (auto dari Sidang berstatus LULUS):
    memastikan setiap mahasiswa LULUS punya baris draft yudisium, tanpa
    menimpa data yang sudah diisi manual (tgl_yudisium, no_sk, status)."""
    lulus_ids = [
        r["mahasiswa_id"]
        for r in conn.execute(
            "SELECT DISTINCT mahasiswa_id FROM sidang WHERE status_kelulusan='LULUS'"
        ).fetchall()
    ]
    for mid in lulus_ids:
        exists = conn.execute("SELECT id FROM yudisium WHERE mahasiswa_id=?", (mid,)).fetchone()
        if not exists:
            sidang_row = conn.execute(
                "SELECT id FROM sidang WHERE mahasiswa_id=? AND status_kelulusan='LULUS' "
                "ORDER BY id DESC LIMIT 1",
                (mid,),
            ).fetchone()
            conn.execute(
                "INSERT INTO yudisium(mahasiswa_id, sidang_id, status_yudisium) " "VALUES(?,?,?)",
                (mid, sidang_row["id"], "Direncanakan"),
            )
    conn.commit()


def sync_wisuda_dari_yudisium(conn):
    """Setara sheet 'Wisuda' (auto ketika Status Yudisium=Terlaksana DAN
    No. SK sudah diisi)."""
    rows = conn.execute(
        "SELECT mahasiswa_id FROM yudisium WHERE status_yudisium='Terlaksana' "
        "AND no_sk IS NOT NULL AND TRIM(no_sk) <> ''"
    ).fetchall()
    for r in rows:
        exists = conn.execute(
            "SELECT id FROM wisuda WHERE mahasiswa_id=?", (r["mahasiswa_id"],)
        ).fetchone()
        if not exists:
            conn.execute("INSERT INTO wisuda(mahasiswa_id) VALUES(?)", (r["mahasiswa_id"],))
    conn.commit()


def rencana_yudisium_rows(conn, tahap_filter=None):
    """`tahap_filter` (opsional) — Tahap/Gelombang pengajuan yang tercatat di
    `penetapan_pembimbing` untuk mahasiswa tsb (sumber tahap yang sama dgn
    rkp_seminar/rkp_sidang/rekap_pembimbing), supaya Rencana Yudisium & SK
    Yudisium juga bisa dikeluarkan per tahap, bukan cuma per angkatan."""
    sync_yudisium_dari_sidang(conn)
    q = """
        SELECT y.*, m.nim, m.nama, m.jk, s.nilai_angka, s.judul_sidang, s.tgl_sidang,
               pp.tahap
        FROM yudisium y
        JOIN mahasiswa m ON m.id = y.mahasiswa_id
        LEFT JOIN sidang s ON s.id = y.sidang_id
        LEFT JOIN penetapan_pembimbing pp ON pp.mahasiswa_id = y.mahasiswa_id
    """
    params = []
    if tahap_filter and tahap_filter != "Semua":
        q += " WHERE pp.tahap LIKE ?"
        params.append(f"%{tahap_filter}%")
    q += " ORDER BY m.nama"
    out = []
    for r in conn.execute(q, params).fetchall():
        d = dict(r)
        # Audit Lanjutan 6 (temuan tambahan) — pakai konversi KHUSUS
        # yudisium (bukan nilai_angka_ke_huruf() polos), lihat komentar
        # lengkap di constants.nilai_angka_ke_huruf_yudisium(). Baris di
        # sini dijamin sudah status_kelulusan='LULUS' (filter di
        # sync_yudisium_dari_sidang di atas), jadi "Nilai Huruf" tidak
        # boleh jatuh ke D/E (=tidak lulus) walau nilai_angka rendah.
        d["nilai_huruf"] = nilai_angka_ke_huruf_yudisium(d["nilai_angka"])
        d["predikat"] = ipk_ke_predikat(d["ipk_final"])
        out.append(d)
    return out


def wisuda_rows(conn, tahap_filter=None):
    """`tahap_filter` — sama seperti di rencana_yudisium_rows() (lihat komentar
    di sana), diambil dari penetapan_pembimbing.tahap milik mahasiswa."""
    sync_wisuda_dari_yudisium(conn)
    q = """
        SELECT w.*, m.nim, m.nama, m.jk, y.ipk_final, y.tgl_yudisium, s.nilai_angka, s.judul_sidang,
               pp.tahap
        FROM wisuda w
        JOIN mahasiswa m ON m.id = w.mahasiswa_id
        LEFT JOIN yudisium y ON y.mahasiswa_id = w.mahasiswa_id
        LEFT JOIN sidang s ON s.id = y.sidang_id
        LEFT JOIN penetapan_pembimbing pp ON pp.mahasiswa_id = w.mahasiswa_id
    """
    params = []
    if tahap_filter and tahap_filter != "Semua":
        q += " WHERE pp.tahap LIKE ?"
        params.append(f"%{tahap_filter}%")
    q += " ORDER BY m.nama"
    out = []
    for r in conn.execute(q, params).fetchall():
        d = dict(r)
        # Audit Lanjutan 6 (temuan tambahan) — sama seperti
        # rencana_yudisium_rows() di atas: baris di sini juga dijamin
        # berasal dari mahasiswa status_kelulusan='LULUS' (via
        # sync_wisuda_dari_yudisium <- yudisium <- sidang LULUS).
        d["nilai_huruf"] = nilai_angka_ke_huruf_yudisium(d["nilai_angka"])
        d["predikat"] = ipk_ke_predikat(d["ipk_final"])
        out.append(d)
    return out


def rkp_seminar(conn, tahap_filter=None, tarif=None):
    """Honor penguji seminar: dihitung dari peran ketua/anggota1/anggota2
    pada seminar berstatus 'Selesai', dikali tarif per peran (flat rate,
    identik dengan formula asli RKP Seminar kolom G = *Panduan!$B$54).

    Audit Modul Pelaksanaan — `tahap_filter` sekarang dicocokkan ke
    `seminar.tahap` (tahap MILIK BARIS SEMINAR itu sendiri, diisi di
    /pelaksanaan/seminar), BUKAN lagi ke `penetapan_pembimbing.tahap`
    (tahap SK Pembimbing/pengajuan judul). Seminar & sidang berjalan
    beberapa kali per semester sedangkan SK Pembimbing cuma sekali di
    awal, jadi keduanya tidak boleh disamakan — kalau masih dipakai,
    rekap honor per tahap bisa salah kelompok.

    Tarif yang dipakai per baris mengikuti snapshot
    `seminar.tarif_honor_diterapkan` (diisi otomatis saat status diset
    'Selesai') supaya honor tahap lama tidak berubah kalau tarif di
    Pengaturan diubah belakangan. Baris lama yang belum punya snapshot
    (NULL) jatuh balik ke tarif aktif saat rekap dijalankan/`tarif`
    yang diberikan eksplisit."""
    from app.db import get_setting

    if tarif is None:
        tarif_default = float(get_setting(conn, "tarif_honor_seminar", "20000"))
    else:
        tarif_default = tarif
    q = """
        SELECT s.*, m.nama AS nama_mhs
        FROM seminar s
        JOIN mahasiswa m ON m.id = s.mahasiswa_id
        WHERE s.status = 'Selesai'
    """
    params = []
    if tahap_filter and tahap_filter != "Semua":
        q += " AND s.tahap LIKE ?"
        params.append(f"%{tahap_filter}%")
    rows = conn.execute(q, params).fetchall()

    tally = {}
    for r in rows:
        tarif_baris = r["tarif_honor_diterapkan"] if r["tarif_honor_diterapkan"] else tarif_default
        for role_col in ("penguji_ketua_id", "penguji_anggota1_id", "penguji_anggota2_id"):
            did = r[role_col]
            if not did:
                continue
            nama = dosen_nama(conn, did)
            tally.setdefault(did, {"nama": nama, "jumlah": 0, "honor": 0.0})
            tally[did]["jumlah"] += 1
            tally[did]["honor"] += tarif_baris
    out = []
    for did, v in sorted(tally.items(), key=lambda kv: kv[1]["nama"]):
        out.append(
            {
                "dosen_id": did,
                "nama": v["nama"],
                "jumlah": v["jumlah"],
                "honor": v["honor"],
            }
        )
    return out


def rkp_sidang(conn, tahap_filter=None, tarif_penguji=None, tarif_pemb1=None, tarif_pemb2=None):
    """Bagian 1: honor penguji sidang (ketua+sekretaris+anggota1-3, flat rate).
    Bagian 2: honor pembimbing 1 & 2, HANYA untuk mahasiswa berstatus LULUS
    (identik formula asli RKP Sidang Bagian 2).

    Audit Modul Pelaksanaan — `tahap_filter` sekarang dicocokkan ke
    `sidang.tahap` (tahap MILIK BARIS SIDANG itu sendiri, diisi di
    /pelaksanaan/sidang) untuk KEDUA bagian, bukan lagi ke
    `penetapan_pembimbing.tahap`. Honor pembimbing sesungguhnya "cair"
    pada saat mahasiswa bimbingannya LULUS SIDANG di suatu tahap
    tertentu, jadi tahap sidang itulah yang relevan buat rekap ke
    keuangan — bukan tahap saat SK Pembimbing pertama kali terbit
    (yang bisa berbeda tahap, bahkan berbeda semester).

    Tarif per baris mengikuti snapshot `sidang.tarif_penguji_diterapkan`
    / `tarif_pemb1_diterapkan` / `tarif_pemb2_diterapkan` (diisi otomatis
    saat baris sidang disimpan), jatuh balik ke tarif aktif kalau NULL
    (baris lama sebelum fitur ini ada, atau tarif eksplisit diberikan)."""
    from app.db import get_setting

    if tarif_penguji is None:
        tarif_penguji_default = float(get_setting(conn, "tarif_honor_penguji_sidang", "30000"))
    else:
        tarif_penguji_default = tarif_penguji
    if tarif_pemb1 is None:
        tarif_pemb1_default = float(get_setting(conn, "tarif_honor_pembimbing_1", "300000"))
    else:
        tarif_pemb1_default = tarif_pemb1
    if tarif_pemb2 is None:
        tarif_pemb2_default = float(get_setting(conn, "tarif_honor_pembimbing_2", "200000"))
    else:
        tarif_pemb2_default = tarif_pemb2

    q = "SELECT sd.* FROM sidang sd"
    params = []
    if tahap_filter and tahap_filter != "Semua":
        q += " WHERE sd.tahap LIKE ?"
        params.append(f"%{tahap_filter}%")
    rows = conn.execute(q, params).fetchall()

    penguji_tally = {}
    for r in rows:
        tarif_baris = r["tarif_penguji_diterapkan"] if r["tarif_penguji_diterapkan"] else tarif_penguji_default
        for role_col in ("ketua_id", "sekretaris_id", "anggota1_id", "anggota2_id", "anggota3_id"):
            did = r[role_col]
            if not did:
                continue
            penguji_tally.setdefault(did, {"nama": dosen_nama(conn, did), "jumlah": 0, "honor": 0.0})
            penguji_tally[did]["jumlah"] += 1
            penguji_tally[did]["honor"] += tarif_baris
    bagian1 = [
        {
            "dosen_id": d,
            "nama": v["nama"],
            "jumlah": v["jumlah"],
            "honor": v["honor"],
        }
        for d, v in sorted(penguji_tally.items(), key=lambda kv: kv[1]["nama"])
    ]

    q2 = """
        SELECT pp.pembimbing1_id, pp.pembimbing2_id, sd.tahap, sd.status_kelulusan,
               sd.tarif_pemb1_diterapkan, sd.tarif_pemb2_diterapkan
        FROM penetapan_pembimbing pp
        JOIN sidang sd ON sd.mahasiswa_id = pp.mahasiswa_id AND sd.status_kelulusan='LULUS'
    """
    params2 = []
    if tahap_filter and tahap_filter != "Semua":
        q2 += " WHERE sd.tahap LIKE ?"
        params2.append(f"%{tahap_filter}%")
    rows2 = conn.execute(q2, params2).fetchall()
    pemb_tally = {}
    for r in rows2:
        tarif_p1 = r["tarif_pemb1_diterapkan"] if r["tarif_pemb1_diterapkan"] else tarif_pemb1_default
        tarif_p2 = r["tarif_pemb2_diterapkan"] if r["tarif_pemb2_diterapkan"] else tarif_pemb2_default
        if r["pembimbing1_id"]:
            d = r["pembimbing1_id"]
            pemb_tally.setdefault(d, {"nama": dosen_nama(conn, d), "p1": 0, "p2": 0, "honor": 0.0})
            pemb_tally[d]["p1"] += 1
            pemb_tally[d]["honor"] += tarif_p1
        if r["pembimbing2_id"]:
            d = r["pembimbing2_id"]
            pemb_tally.setdefault(d, {"nama": dosen_nama(conn, d), "p1": 0, "p2": 0, "honor": 0.0})
            pemb_tally[d]["p2"] += 1
            pemb_tally[d]["honor"] += tarif_p2
    bagian2 = []
    for d, v in sorted(pemb_tally.items(), key=lambda kv: kv[1]["nama"]):
        bagian2.append(
            {
                "dosen_id": d,
                "nama": v["nama"],
                "sbg_pemb1": v["p1"],
                "sbg_pemb2": v["p2"],
                "honor": v["honor"],
            }
        )
    return {"bagian1": bagian1, "bagian2": bagian2}


def rekap_honor_keuangan(conn, tahap_filter=None):
    """Rekap gabungan honor Seminar + Sidang (penguji & pembimbing) per
    DOSEN x TAHAP x KATEGORI — dibuat khusus supaya bagian keuangan tidak
    perlu menjumlahkan sendiri dari 2 laporan terpisah (RKP Seminar & RKP
    Sidang). Satu baris = satu dosen pada satu tahap untuk satu kategori
    honor, lengkap dengan jumlah peran & nominal, plus grand total di
    akhir. `tahap_filter` "Semua"/None = tampilkan semua tahap sekaligus
    (baris tetap dipecah per tahap, bukan digabung, supaya keuangan bisa
    lihat rincian per gelombang pencairan)."""
    rows_out = []

    # --- Seminar (penguji) ---
    q = "SELECT s.*, m.nama AS nama_mhs FROM seminar s JOIN mahasiswa m ON m.id=s.mahasiswa_id WHERE s.status='Selesai'"
    params = []
    if tahap_filter and tahap_filter != "Semua":
        q += " AND s.tahap LIKE ?"
        params.append(f"%{tahap_filter}%")
    from app.db import get_setting

    tarif_seminar_default = float(get_setting(conn, "tarif_honor_seminar", "20000"))
    for r in conn.execute(q, params).fetchall():
        tarif_baris = r["tarif_honor_diterapkan"] if r["tarif_honor_diterapkan"] else tarif_seminar_default
        tahap = r["tahap"] or "(Tanpa Tahap)"
        for role_col in ("penguji_ketua_id", "penguji_anggota1_id", "penguji_anggota2_id"):
            did = r[role_col]
            if not did:
                continue
            rows_out.append(
                {
                    "dosen_id": did,
                    "nama": dosen_nama(conn, did),
                    "tahap": tahap,
                    "kategori": "Seminar - Penguji",
                    "jumlah": 1,
                    "tarif": tarif_baris,
                    "honor": tarif_baris,
                }
            )

    # --- Sidang (penguji) ---
    q = "SELECT sd.* FROM sidang sd"
    params = []
    if tahap_filter and tahap_filter != "Semua":
        q += " WHERE sd.tahap LIKE ?"
        params.append(f"%{tahap_filter}%")
    tarif_penguji_default = float(get_setting(conn, "tarif_honor_penguji_sidang", "30000"))
    for r in conn.execute(q, params).fetchall():
        tarif_baris = r["tarif_penguji_diterapkan"] if r["tarif_penguji_diterapkan"] else tarif_penguji_default
        tahap = r["tahap"] or "(Tanpa Tahap)"
        for role_col in ("ketua_id", "sekretaris_id", "anggota1_id", "anggota2_id", "anggota3_id"):
            did = r[role_col]
            if not did:
                continue
            rows_out.append(
                {
                    "dosen_id": did,
                    "nama": dosen_nama(conn, did),
                    "tahap": tahap,
                    "kategori": "Sidang - Penguji",
                    "jumlah": 1,
                    "tarif": tarif_baris,
                    "honor": tarif_baris,
                }
            )

    # --- Sidang (pembimbing 1 & 2, hanya LULUS) ---
    q2 = (
        "SELECT pp.pembimbing1_id, pp.pembimbing2_id, sd.tahap, "
        "sd.tarif_pemb1_diterapkan, sd.tarif_pemb2_diterapkan "
        "FROM penetapan_pembimbing pp "
        "JOIN sidang sd ON sd.mahasiswa_id = pp.mahasiswa_id AND sd.status_kelulusan='LULUS'"
    )
    params2 = []
    if tahap_filter and tahap_filter != "Semua":
        q2 += " WHERE sd.tahap LIKE ?"
        params2.append(f"%{tahap_filter}%")
    tarif_pemb1_default = float(get_setting(conn, "tarif_honor_pembimbing_1", "300000"))
    tarif_pemb2_default = float(get_setting(conn, "tarif_honor_pembimbing_2", "200000"))
    for r in conn.execute(q2, params2).fetchall():
        tahap = r["tahap"] or "(Tanpa Tahap)"
        tarif_p1 = r["tarif_pemb1_diterapkan"] if r["tarif_pemb1_diterapkan"] else tarif_pemb1_default
        tarif_p2 = r["tarif_pemb2_diterapkan"] if r["tarif_pemb2_diterapkan"] else tarif_pemb2_default
        if r["pembimbing1_id"]:
            rows_out.append(
                {
                    "dosen_id": r["pembimbing1_id"],
                    "nama": dosen_nama(conn, r["pembimbing1_id"]),
                    "tahap": tahap,
                    "kategori": "Sidang - Pembimbing 1",
                    "jumlah": 1,
                    "tarif": tarif_p1,
                    "honor": tarif_p1,
                }
            )
        if r["pembimbing2_id"]:
            rows_out.append(
                {
                    "dosen_id": r["pembimbing2_id"],
                    "nama": dosen_nama(conn, r["pembimbing2_id"]),
                    "tahap": tahap,
                    "kategori": "Sidang - Pembimbing 2",
                    "jumlah": 1,
                    "tarif": tarif_p2,
                    "honor": tarif_p2,
                }
            )

    # Agregasi per (dosen, tahap, kategori) — baris di atas masih 1 baris
    # per peran per kejadian, digabung supaya keuangan lihat total per sel.
    agg = {}
    for r in rows_out:
        key = (r["dosen_id"], r["tahap"], r["kategori"])
        a = agg.setdefault(
            key,
            {
                "dosen_id": r["dosen_id"],
                "nama": r["nama"],
                "tahap": r["tahap"],
                "kategori": r["kategori"],
                "jumlah": 0,
                "tarif": r["tarif"],
                "honor": 0.0,
            },
        )
        a["jumlah"] += r["jumlah"]
        a["honor"] += r["honor"]

    hasil = sorted(agg.values(), key=lambda a: (a["nama"], a["tahap"], a["kategori"]))
    total = sum(a["honor"] for a in hasil)
    return hasil, total


def rekap_rasio_dosen_cached(conn):
    """Cache per-request (flask.g) untuk rekap_rasio_dosen(ambang=None,
    hanya_homebase=True) — parameter baku yang dipakai get_notifikasi()
    maupun dashboard.index() untuk badge/angka overload.

    Audit lanjutan (Dashboard, temuan #7, diukur langsung) — dalam SATU
    kali load Dashboard, rekap_rasio_dosen() dipanggil 3x dengan parameter
    identik: get_notifikasi() (badge notifikasi), dashboard.index()
    (overload_n), dan context processor global inject_globals()->
    hitung_ringkasan()->kumpulkan()->get_notifikasi() lagi — beban itu
    ditanggung SETIAP halaman, bukan cuma Dashboard, karena lewat context
    processor. Query batch di dalamnya sendiri sudah konstan (bukan N+1
    lagi, lihat catatan di rekap_rasio_dosen()), jadi tidak salah/berat
    per panggilan — tapi tetap sia-sia dihitung ulang 3x persis sama.

    Mengikuti pola cache per-request yang sudah dipakai di
    routes/notifikasi.py::kumpulkan_cached() — dikunci ke g, bersih
    otomatis di akhir request, jadi tidak berisiko data basi lintas
    request. Dipakai HANYA oleh pemanggil yang butuh parameter baku;
    pemanggilan rekap_rasio_dosen() langsung dengan parameter kustom
    (mis. halaman Rekap Rasio Dosen itu sendiri, atau kode
    test/skrip) tetap menghitung ulang seperti biasa, jadi tidak pernah
    melihat hasil basi walau data berubah di tengah proses."""
    try:
        from flask import g, has_app_context

        if has_app_context():
            if "_cache_rekap_rasio_dosen_baku" not in g:
                g._cache_rekap_rasio_dosen_baku = rekap_rasio_dosen(conn)
            return g._cache_rekap_rasio_dosen_baku
    except RuntimeError:
        pass
    return rekap_rasio_dosen(conn)


def get_notifikasi(conn):
    """Kumpulan peringatan operasional — pengganti kebiasaan lama 'menyisir
    manual satu-satu sheet' di Excel. Dipakai di Dashboard & panel Notifikasi."""
    out = []

    overload = [r for r in rekap_rasio_dosen_cached(conn) if r["status"].startswith("⚠️")]
    if overload:
        out.append(
            {
                "level": "warning",
                "judul": f"{len(overload)} dosen melebihi ambang beban",
                "detail": ", ".join(r["nama"] for r in overload[:5])
                + (" ..." if len(overload) > 5 else ""),
            }
        )

    menunggu_review = conn.execute(
        "SELECT COUNT(*) c FROM pengajuan_judul WHERE status_final='Diajukan'"
    ).fetchone()["c"]
    if menunggu_review:
        out.append(
            {
                "level": "info",
                "judul": f"{menunggu_review} pengajuan judul menunggu review",
                "detail": "Buka modul Pengajuan & Review Judul.",
            }
        )

    belum_sk = conn.execute(
        "SELECT COUNT(*) c FROM mahasiswa m WHERE m.status_ta IN (?, ?) AND NOT EXISTS "
        "(SELECT 1 FROM penetapan_pembimbing pp WHERE pp.mahasiswa_id = m.id)",
        ("Mengajukan Judul", "Proses Bimbingan"),
    ).fetchone()["c"]
    if belum_sk:
        out.append(
            {
                "level": "info",
                "judul": f"{belum_sk} mahasiswa proses TA belum punya SK Pembimbing",
                "detail": "Lengkapi di modul Penetapan Pembimbing.",
            }
        )

    sk_tidak_lengkap = conn.execute(
        "SELECT COUNT(*) c FROM penetapan_pembimbing WHERE pembimbing1_id IS NULL "
        "OR no_sk IS NULL OR TRIM(no_sk)=''"
    ).fetchone()["c"]
    if sk_tidak_lengkap:
        out.append(
            {
                "level": "warning",
                "judul": f"{sk_tidak_lengkap} SK Pembimbing belum lengkap (No. SK / Pembimbing 1 kosong)",
                "detail": "Periksa modul Penetapan Pembimbing.",
            }
        )

    tunda = conn.execute("SELECT COUNT(*) c FROM sidang WHERE status_kelulusan='TUNDA'").fetchone()[
        "c"
    ]
    if tunda:
        out.append(
            {
                "level": "warning",
                "judul": f"{tunda} mahasiswa berstatus TUNDA pada sidang",
                "detail": "Perlu tindak lanjut jadwal sidang ulang.",
            }
        )

    siap_yudisium = conn.execute(
        "SELECT COUNT(*) c FROM yudisium WHERE status_yudisium='Direncanakan'"
    ).fetchone()["c"]
    if siap_yudisium:
        out.append(
            {
                "level": "info",
                "judul": f"{siap_yudisium} mahasiswa siap diproses ke Yudisium",
                "detail": "Lengkapi Tgl Yudisium & No. SK di modul Rencana Yudisium.",
            }
        )

    # Audit poin 5 (tindak lanjut) — reminder backup lama tampil otomatis di
    # Dashboard/Notifikasi, bukan cuma bisa diketahui dgn membuka menu
    # Backup & Restore lebih dulu. Retensi (bersihkan_backup_lama) berjalan
    # otomatis tiap start aplikasi (lihat app/__init__.py) — reminder ini
    # murni informasi "kapan terakhir backup", independen dari retensi.
    bstatus = backup_core.status_reminder()
    if bstatus["perlu_reminder"]:
        out.append(
            {
                "level": "warning" if bstatus["ada_backup"] else "danger",
                "judul": (
                    "Belum pernah backup database"
                    if not bstatus["ada_backup"]
                    else f"Backup database sudah {bstatus['hari_sejak_terakhir']} hari tidak diperbarui"
                ),
                "detail": "Buka menu Pengaturan → Backup & Restore untuk membuat backup baru.",
            }
        )

    if not out:
        out.append(
            {
                "level": "ok",
                "judul": "Tidak ada peringatan saat ini",
                "detail": "Semua data terpantau normal.",
            }
        )
    return out


def dosen_terlibat_seminar(conn, row):
    """Set id dosen yang 'hadir' pada satu sesi seminar: tim penguji +
    dosen pembimbing mahasiswa ybs (asumsi pembimbing turut hadir)."""
    ids = set()
    for col in ("penguji_ketua_id", "penguji_anggota1_id", "penguji_anggota2_id"):
        if row[col]:
            ids.add(row[col])
    pp = conn.execute(
        "SELECT pembimbing1_id, pembimbing2_id FROM penetapan_pembimbing WHERE mahasiswa_id=?",
        (row["mahasiswa_id"],),
    ).fetchone()
    if pp:
        if pp["pembimbing1_id"]:
            ids.add(pp["pembimbing1_id"])
        if pp["pembimbing2_id"]:
            ids.add(pp["pembimbing2_id"])
    return ids


def dosen_terlibat_sidang(conn, row):
    """Set id dosen yang 'hadir' pada satu sesi sidang: tim penguji
    terlaksana + dosen pembimbing mahasiswa ybs."""
    ids = set()
    for col in ("ketua_id", "sekretaris_id", "anggota1_id", "anggota2_id", "anggota3_id"):
        if row[col]:
            ids.add(row[col])
    pp = conn.execute(
        "SELECT pembimbing1_id, pembimbing2_id FROM penetapan_pembimbing WHERE mahasiswa_id=?",
        (row["mahasiswa_id"],),
    ).fetchone()
    if pp:
        if pp["pembimbing1_id"]:
            ids.add(pp["pembimbing1_id"])
        if pp["pembimbing2_id"]:
            ids.add(pp["pembimbing2_id"])
    return ids


def _semua_sesi_terjadwal(conn):
    """Kumpulan seluruh sesi (seminar + sidang) yang punya tanggal, dipakai
    sebagai basis pengecekan bentrok & tampilan Jadwal."""
    from app.db import get_setting

    dur_sem = int(float(get_setting(conn, "durasi_seminar_menit", "60")))
    dur_sid = int(float(get_setting(conn, "durasi_sidang_menit", "90")))
    out = []
    for r in conn.execute(
        "SELECT s.*, m.nim, m.nama FROM seminar s JOIN mahasiswa m ON m.id=s.mahasiswa_id "
        "WHERE s.tgl_seminar IS NOT NULL AND TRIM(s.tgl_seminar) <> ''"
    ).fetchall():
        start, end = dt.session_interval(r["tgl_seminar"], r["jam"], dur_sem)
        out.append(
            {
                "jenis": "Seminar",
                "id": r["id"],
                "mahasiswa_id": r["mahasiswa_id"],
                "nim": r["nim"],
                "nama": r["nama"],
                "tgl": r["tgl_seminar"],
                "jam": r["jam"],
                "ruangan_id": r["ruangan_id"],
                "start": start,
                "end": end,
                "dosen_ids": dosen_terlibat_seminar(conn, r),
            }
        )
    for r in conn.execute(
        "SELECT sd.*, m.nim, m.nama FROM sidang sd JOIN mahasiswa m ON m.id=sd.mahasiswa_id "
        "WHERE sd.tgl_sidang IS NOT NULL AND TRIM(sd.tgl_sidang) <> ''"
    ).fetchall():
        start, end = dt.session_interval(r["tgl_sidang"], r["jam_sidang"], dur_sid)
        out.append(
            {
                "jenis": "Sidang",
                "id": r["id"],
                "mahasiswa_id": r["mahasiswa_id"],
                "nim": r["nim"],
                "nama": r["nama"],
                "tgl": r["tgl_sidang"],
                "jam": r["jam_sidang"],
                "ruangan_id": r["ruangan_id"],
                "start": start,
                "end": end,
                "dosen_ids": dosen_terlibat_sidang(conn, r),
            }
        )
    return out


def ruangan_nama(conn, ruangan_id):
    if not ruangan_id:
        return ""
    r = conn.execute("SELECT nama FROM ruangan WHERE id=?", (ruangan_id,)).fetchone()
    return r["nama"] if r else ""


def cek_bentrok(
    conn,
    jenis,
    mahasiswa_id,
    tgl_text,
    jam_text,
    ruangan_id,
    dosen_ids,
    exclude_jenis=None,
    exclude_id=None,
):
    """Deteksi bentrok jadwal untuk SATU sesi (dipanggil sebelum simpan).

    Mengembalikan list dict {'level','pesan'} — bisa lebih dari satu temuan.
    Bentrok yang dicek: dosen yang sama, ruangan yang sama, dan mahasiswa
    yang sama dijadwalkan pada dua sesi dengan waktu tumpang-tindih.
    Bila tanggal ATAU jam sesi ini tidak bisa diparse, deteksi dilewati
    (dilaporkan sebagai catatan info, bukan blokir) karena tidak bisa
    dipastikan tumpang tindih atau tidak.
    """
    from app.db import get_setting

    durasi = int(
        float(
            get_setting(
                conn,
                "durasi_seminar_menit" if jenis == "Seminar" else "durasi_sidang_menit",
                "60" if jenis == "Seminar" else "90",
            )
        )
    )
    start, end = dt.session_interval(tgl_text, jam_text, durasi)
    if not start:
        return [
            {
                "level": "info",
                "pesan": "Tanggal/jam belum bisa dibaca sistem (format tidak dikenali) — "
                "deteksi bentrok dilewati untuk sesi ini. Gunakan format 'dd Mon yyyy' "
                "dan jam 'HH.MM'.",
            }
        ]

    hasil = []
    for sesi in _semua_sesi_terjadwal(conn):
        if exclude_jenis and sesi["jenis"] == exclude_jenis and sesi["id"] == exclude_id:
            continue
        if not sesi["start"]:
            continue
        if not dt.overlaps(start, end, sesi["start"], sesi["end"]):
            continue

        overlap_dosen = dosen_ids & sesi["dosen_ids"]
        for did in overlap_dosen:
            hasil.append(
                {
                    "level": "error",
                    "pesan": f"Dosen '{dosen_nama(conn, did)}' sudah dijadwalkan di "
                    f"{sesi['jenis']} {sesi['nim']} - {sesi['nama']} "
                    f"({sesi['tgl']} {sesi['jam']})",
                }
            )

        if ruangan_id and sesi["ruangan_id"] == ruangan_id:
            hasil.append(
                {
                    "level": "error",
                    "pesan": f"Ruangan '{ruangan_nama(conn, ruangan_id)}' sudah dipakai untuk "
                    f"{sesi['jenis']} {sesi['nim']} - {sesi['nama']} "
                    f"({sesi['tgl']} {sesi['jam']})",
                }
            )

        if mahasiswa_id and sesi["mahasiswa_id"] == mahasiswa_id:
            hasil.append(
                {
                    "level": "error",
                    "pesan": f"Mahasiswa ini sudah punya jadwal {sesi['jenis']} lain pada waktu "
                    f"yang tumpang tindih ({sesi['tgl']} {sesi['jam']})",
                }
            )
    return hasil


def _mk_label(row):
    kode = row["mk_kode"] or ""
    nama = row["mk_nama"] or ""
    kelas = row["kelas"] or ""
    label = f"{kode} - {nama}".strip(" -")
    if kelas:
        label += f" (Kelas {kelas})"
    return label


def cek_bentrok_kelas(
    conn,
    hari,
    jam_mulai_text,
    jam_selesai_text,
    ruangan_id,
    dosen_id,
    periode_akademik_id,
    exclude_id=None,
):
    """Deteksi bentrok jadwal kelas reguler mingguan (dipanggil sebelum
    simpan_kelas commit) — versi cek_bentrok() khusus pola "hari + jam
    berulang" (bukan tanggal spesifik seperti Seminar/Sidang).

    Membandingkan (hari, jam_mulai, jam_selesai, ruangan_id/dosen_id) antar
    baris jadwal_kelas pada periode akademik yang sama. Mengembalikan list
    dict {'level','pesan'}, mengikuti pola cek_bentrok() di atas supaya bisa
    dipakai lewat template _bentrok_confirm.html yang sama.
    """
    hari = (hari or "").strip()
    t_mulai = dt.parse_jam(jam_mulai_text)
    t_selesai = dt.parse_jam(jam_selesai_text)
    if not hari or not t_mulai or not t_selesai:
        return [
            {
                "level": "info",
                "pesan": "Hari/jam mulai/jam selesai belum lengkap atau belum bisa dibaca "
                "sistem — deteksi bentrok dilewati untuk kelas ini. Gunakan jam "
                "berformat 'HH.MM' atau 'HH:MM'.",
            }
        ]
    if t_selesai <= t_mulai:
        return [
            {
                "level": "info",
                "pesan": "Jam selesai harus setelah jam mulai — deteksi bentrok dilewati "
                "untuk kelas ini.",
            }
        ]

    # Waktu dibungkus tanggal patokan yang sama (bukan tanggal sungguhan,
    # karena jadwal kelas berulang tiap minggu berbasis 'hari', bukan
    # tanggal spesifik) supaya dt.overlaps() bisa dipakai ulang.
    anchor = datetime.date(2000, 1, 1)
    start = datetime.datetime.combine(anchor, t_mulai)
    end = datetime.datetime.combine(anchor, t_selesai)

    rows = conn.execute(
        "SELECT jk.*, mk.kode AS mk_kode, mk.nama AS mk_nama FROM jadwal_kelas jk "
        "JOIN mata_kuliah mk ON mk.id = jk.mata_kuliah_id "
        "WHERE jk.periode_akademik_id=? AND jk.hari=?",
        (periode_akademik_id, hari),
    ).fetchall()

    hasil = []
    for r in rows:
        if exclude_id and r["id"] == exclude_id:
            continue
        t2_mulai = dt.parse_jam(r["jam_mulai"])
        t2_selesai = dt.parse_jam(r["jam_selesai"])
        if not t2_mulai or not t2_selesai:
            continue
        r_start = datetime.datetime.combine(anchor, t2_mulai)
        r_end = datetime.datetime.combine(anchor, t2_selesai)
        if not dt.overlaps(start, end, r_start, r_end):
            continue

        label = _mk_label(r)
        jadwal_txt = f"{hari}, {r['jam_mulai']}-{r['jam_selesai']}"
        if dosen_id and r["dosen_id"] == dosen_id:
            hasil.append(
                {
                    "level": "error",
                    "pesan": f"Dosen '{dosen_nama(conn, dosen_id)}' sudah mengajar kelas "
                    f"{label} pada {jadwal_txt}",
                }
            )
        if ruangan_id and r["ruangan_id"] == ruangan_id:
            hasil.append(
                {
                    "level": "error",
                    "pesan": f"Ruangan '{ruangan_nama(conn, ruangan_id)}' sudah dipakai untuk "
                    f"kelas {label} pada {jadwal_txt}",
                }
            )
    return hasil


# =============================================================================
# Modul 10 — Jadwal Kelas & BAP (Berita Acara Perkuliahan)
# =============================================================================
def realisasi_bap(conn, jadwal_kelas_id, jumlah_rencana=None):
    """Realisasi materi dihitung on-the-fly dari COUNT(bap) berstatus apa pun
    yang sudah dicatat (Terlaksana/Ditunda/Dosen Pengganti dianggap tetap
    'ada BAP-nya') dibanding jumlah pertemuan rencana — bukan angka statis,
    supaya tidak pernah basi seperti realisasi_target_kinerja & proker."""
    if jumlah_rencana is None:
        row = conn.execute(
            "SELECT jumlah_pertemuan_rencana FROM jadwal_kelas WHERE id=?",
            (jadwal_kelas_id,),
        ).fetchone()
        jumlah_rencana = row["jumlah_pertemuan_rencana"] if row else 16
    terlaksana = conn.execute(
        "SELECT COUNT(*) c FROM bap WHERE jadwal_kelas_id=? AND status='Terlaksana'",
        (jadwal_kelas_id,),
    ).fetchone()["c"]
    tercatat = conn.execute(
        "SELECT COUNT(*) c FROM bap WHERE jadwal_kelas_id=?", (jadwal_kelas_id,)
    ).fetchone()["c"]
    persen = round((terlaksana / jumlah_rencana) * 100) if jumlah_rencana else 0
    return {
        "rencana": jumlah_rencana,
        "terlaksana": terlaksana,
        "tercatat": tercatat,
        "persen": min(persen, 100),
    }


def sub_cpmk_untuk_mk(conn, mata_kuliah_id):
    """Daftar Sub-CPMK (gabungan semua CPMK) milik satu mata kuliah — dipakai
    dropdown rujukan materi per pertemuan di form BAP."""
    return conn.execute(
        "SELECT sc.*, c.kode AS cpmk_kode FROM sub_cpmk sc "
        "JOIN cpmk c ON c.id = sc.cpmk_id WHERE c.mata_kuliah_id=? "
        "ORDER BY c.kode, sc.urutan, sc.kode",
        (mata_kuliah_id,),
    ).fetchall()


# =============================================================================
# Modul 11 — Nilai Mahasiswa & OBE Assessment Engine
# CPL -> CPMK -> nilai_cpmk (per mahasiswa) -> capaian CPL individu/program.
# Capaian dihitung sebagai rata-rata nilai_angka (skala 0-100) dari seluruh
# nilai_cpmk yang CPMK-nya dipetakan ke CPL tsb — bukan hanya persen lulus
# KKM, supaya sensitif terhadap seberapa jauh di atas/bawah KKM nilainya.
#
# Audit Menyeluruh — PHASE 6 (re-check, bug ditemukan & diperbaiki): sejak
# nilai_cpmk bisa punya BEBERAPA baris per (krs_id, cpmk_id) -- satu per
# jenis_asesmen (Tugas/UTS/UAS/dst, lihat constants.JENIS_ASESMEN_LIST) --
# query lama yang langsung merata-ratakan SEMUA baris nilai_angka apa
# adanya jadi bias: mahasiswa yang instrumen asesmennya lebih lengkap
# tercatat (mis. 3 baris: Tugas+UTS+UAS) ikut "memberi bobot" 3x lipat
# dibanding mahasiswa yang baru sempat dicatat 1 instrumen, dan (lebih
# serius) `persen_tuntas` di capaian_cpl_program() jadi menghitung "persen
# BARIS NILAI yang tuntas KKM", bukan "persen MAHASISWA yang tuntas" --
# padahal itu label yang ditampilkan ke pengguna. Kedua fungsi di bawah
# sekarang menggabungkan (AVG) dulu seluruh instrumen asesmen per
# (mahasiswa, CPMK) jadi SATU titik data representatif per CPMK, BARU
# dipakai utk rata-rata & persen tuntas per CPL -- memulihkan semantik
# "satu skor per CPMK per mahasiswa" yang berlaku sebelum kolom
# jenis_asesmen ditambahkan, terlepas dari berapa banyak instrumen yang
# sudah diinput utk CPMK itu.
# =============================================================================
def capaian_cpl_mahasiswa(conn, mahasiswa_id, kurikulum_id):
    """Capaian CPL individu satu mahasiswa untuk satu kurikulum: rata-rata
    nilai_cpmk yang sudah diinput, dikelompokkan per CPL lewat cpmk_cpl.
    Beberapa instrumen asesmen (jenis_asesmen) pada CPMK yang sama
    digabung (AVG) dulu jadi satu skor per CPMK sebelum dirata-ratakan
    lintas CPMK -> CPL."""
    cpl_rows = conn.execute(
        "SELECT * FROM cpl WHERE kurikulum_id=? ORDER BY kategori, urutan, kode",
        (kurikulum_id,),
    ).fetchall()
    out = []
    for cpl in cpl_rows:
        nilai_rows = conn.execute(
            "SELECT AVG(nc.nilai_angka) AS skor_cpmk FROM nilai_cpmk nc "
            "JOIN krs k ON k.id = nc.krs_id "
            "JOIN cpmk_cpl cc ON cc.cpmk_id = nc.cpmk_id "
            "WHERE k.mahasiswa_id=? AND cc.cpl_id=? AND nc.nilai_angka IS NOT NULL "
            "GROUP BY nc.cpmk_id",
            (mahasiswa_id, cpl["id"]),
        ).fetchall()
        nilai_list = [r["skor_cpmk"] for r in nilai_rows]
        rata = round(sum(nilai_list) / len(nilai_list), 1) if nilai_list else None
        out.append({"cpl": cpl, "rata_rata": rata, "jumlah_nilai": len(nilai_list)})
    return out


def capaian_cpl_program(conn, kurikulum_id):
    """Capaian CPL tingkat program (semua mahasiswa/kelas digabung) — dasar
    OBE Assessment Engine untuk Dashboard OBE & Gap Analysis Modul 12.
    Beberapa instrumen asesmen pada CPMK yang sama, milik mahasiswa yang
    sama, digabung (AVG) dulu jadi satu skor per (mahasiswa, CPMK) --
    "jumlah_nilai" & "persen_tuntas" jadi benar-benar mencerminkan jumlah
    mahasiswa/penilaian CPMK yang tuntas, bukan jumlah baris asesmen."""
    cpl_rows = conn.execute(
        "SELECT * FROM cpl WHERE kurikulum_id=? ORDER BY kategori, urutan, kode",
        (kurikulum_id,),
    ).fetchall()
    from app.constants import KKM_CPMK

    out = []
    for cpl in cpl_rows:
        nilai_rows = conn.execute(
            "SELECT AVG(nc.nilai_angka) AS skor_cpmk FROM nilai_cpmk nc "
            "JOIN cpmk_cpl cc ON cc.cpmk_id = nc.cpmk_id "
            "WHERE cc.cpl_id=? AND nc.nilai_angka IS NOT NULL "
            "GROUP BY nc.krs_id, nc.cpmk_id",
            (cpl["id"],),
        ).fetchall()
        nilai_list = [r["skor_cpmk"] for r in nilai_rows]
        rata = round(sum(nilai_list) / len(nilai_list), 1) if nilai_list else None
        tuntas = sum(1 for n in nilai_list if n >= KKM_CPMK)
        persen_tuntas = round((tuntas / len(nilai_list)) * 100) if nilai_list else None
        out.append(
            {
                "cpl": cpl,
                "rata_rata": rata,
                "jumlah_nilai": len(nilai_list),
                "persen_tuntas": persen_tuntas,
            }
        )
    return out


def jadwal_mendatang(conn, hari=7):
    """Sesi seminar/sidang dalam N hari ke depan dari hari ini — dipakai
    di panel Dashboard."""
    import datetime as _dt

    today = _dt.date.today()
    limit = today + _dt.timedelta(days=hari)
    out = []
    for sesi in _semua_sesi_terjadwal(conn):
        if not sesi["start"]:
            continue
        tgl = sesi["start"].date()
        if today <= tgl <= limit:
            out.append(sesi)
    out.sort(key=lambda s: s["start"])
    return out


def rekap_rasio_dosen(conn, ambang=None, hanya_homebase=True):
    """Setara sheet 'Rekap Rasio Dosen': gabungan beban bimbingan + tugas
    penguji per dosen, dengan penanda '⚠️ Overload' bila melewati ambang.

    Audit poin 3: rasio dosen:mahasiswa resmi (BAN-PT/LAM & PDDikti/BKD)
    hanya menghitung dosen HOMEBASE sebagai basis rasio prodi — dosen luar
    prodi/fakultas/PT dikecualikan secara default. `hanya_homebase=False`
    tetap tersedia untuk keperluan operasional harian (lihat beban semua
    dosen yang aktif mengajar/membimbing, termasuk dosen luar).

    Audit Rekap & Statistik (temuan N+1, laporan pengguna) — SEBELUMNYA
    fungsi ini menjalankan query terpisah PER DOSEN di dalam loop
    (pemb1, pemb2, 4 query COUNT tugas penguji), DITAMBAH
    status_seminar_mahasiswa()/status_sidang_mahasiswa() dipanggil satu-satu
    PER MAHASISWA BIMBINGAN di dalam loop dosen itu -- pola N+1 klasik,
    jumlah query bertumbuh sebanding dosen x mahasiswa_bimbingan, bukan
    konstan. Fungsi ini dipanggil di SETIAP page load lewat
    get_notifikasi() -> routes/notifikasi.py::kumpulkan() -> badge
    notifikasi global (topbar, app/__init__.py::inject_globals), jadi
    beban itu ditanggung SEMUA halaman, bukan cuma saat membuka halaman
    Rekap Rasio Dosen itu sendiri.

    Diperbaiki: seluruh data mentah (penetapan_pembimbing, seminar, sidang)
    dibaca lewat SEJUMLAH KECIL query batch (jumlahnya KONSTAN, tidak lagi
    bergantung jumlah dosen/mahasiswa), lalu dihitung & digabung per dosen
    di Python memakai dict lookup (O(1)) -- bukan query database berulang."""
    from app.db import get_setting

    if ambang is None:
        ambang = float(get_setting(conn, "ambang_beban_dosen", "10"))

    sql = "SELECT id, nama, status_homebase FROM dosen WHERE aktif=1"
    if hanya_homebase:
        sql += " AND (status_homebase='Homebase' OR status_homebase IS NULL OR status_homebase='')"
    sql += " ORDER BY nama"
    dosen_rows = conn.execute(sql).fetchall()
    if not dosen_rows:
        return []

    pp_rows = conn.execute(
        "SELECT mahasiswa_id, pembimbing1_id, pembimbing2_id, pembahas1_id, "
        "pembahas2_id, pembahas3_id, ketua_sidang_id FROM penetapan_pembimbing"
    ).fetchall()
    pemb1_map, pemb2_map = {}, {}
    pembahas_count, ketua_sidang_count = {}, {}
    for r in pp_rows:
        if r["pembimbing1_id"]:
            pemb1_map.setdefault(r["pembimbing1_id"], []).append(r["mahasiswa_id"])
        if r["pembimbing2_id"]:
            pemb2_map.setdefault(r["pembimbing2_id"], []).append(r["mahasiswa_id"])
        for pid in (r["pembahas1_id"], r["pembahas2_id"], r["pembahas3_id"]):
            if pid:
                pembahas_count[pid] = pembahas_count.get(pid, 0) + 1
        if r["ketua_sidang_id"]:
            ketua_sidang_count[r["ketua_sidang_id"]] = (
                ketua_sidang_count.get(r["ketua_sidang_id"], 0) + 1
            )

    seminar_penguji_count = {}
    for r in conn.execute(
        "SELECT penguji_ketua_id, penguji_anggota1_id, penguji_anggota2_id FROM seminar"
    ).fetchall():
        for pid in (r["penguji_ketua_id"], r["penguji_anggota1_id"], r["penguji_anggota2_id"]):
            if pid:
                seminar_penguji_count[pid] = seminar_penguji_count.get(pid, 0) + 1

    sidang_penguji_count = {}
    for r in conn.execute(
        "SELECT ketua_id, sekretaris_id, anggota1_id, anggota2_id, anggota3_id FROM sidang"
    ).fetchall():
        for pid in (
            r["ketua_id"],
            r["sekretaris_id"],
            r["anggota1_id"],
            r["anggota2_id"],
            r["anggota3_id"],
        ):
            if pid:
                sidang_penguji_count[pid] = sidang_penguji_count.get(pid, 0) + 1

    semua_mid = set()
    for ids in pemb1_map.values():
        semua_mid.update(ids)
    for ids in pemb2_map.values():
        semua_mid.update(ids)
    status_seminar_map = _status_seminar_batch(conn, semua_mid)
    status_sidang_map = _status_sidang_batch(conn, semua_mid)

    out = []
    for d in dosen_rows:
        did = d["id"]
        bimb1_ids = pemb1_map.get(did, [])
        bimb2_ids = pemb2_map.get(did, [])
        semua_bimb_ids = bimb1_ids + bimb2_ids
        total_bimb = len(semua_bimb_ids)
        sudah_sem = sum(
            1 for mid in semua_bimb_ids if status_seminar_map.get(mid, "Belum Seminar") == "Selesai"
        )
        sudah_sid = sum(
            1
            for mid in semua_bimb_ids
            if status_sidang_map.get(mid, "Belum Sidang") not in ("Belum Sidang",)
        )

        pembahas_penetapan = pembahas_count.get(did, 0)
        penguji_seminar_terlaksana = seminar_penguji_count.get(did, 0)
        ketua_sidang_penetapan = ketua_sidang_count.get(did, 0)
        penguji_sidang_terlaksana = sidang_penguji_count.get(did, 0)

        total_tugas_penguji = (
            pembahas_penetapan
            + penguji_seminar_terlaksana
            + ketua_sidang_penetapan
            + penguji_sidang_terlaksana
        )
        total_keterlibatan = total_bimb + total_tugas_penguji
        status = "⚠️ Overload" if total_keterlibatan > ambang else "✅ Normal"

        out.append(
            {
                "nama": d["nama"],
                "status_homebase": d["status_homebase"] or "Homebase",
                "pemb1": len(bimb1_ids),
                "pemb2": len(bimb2_ids),
                "total_bimb": total_bimb,
                "sudah_seminar": sudah_sem,
                "persen_seminar": round(sudah_sem / total_bimb * 100, 1) if total_bimb else 0,
                "sudah_sidang": sudah_sid,
                "persen_sidang": round(sudah_sid / total_bimb * 100, 1) if total_bimb else 0,
                "pembahas_penetapan": pembahas_penetapan,
                "penguji_seminar_terlaksana": penguji_seminar_terlaksana,
                "ketua_sidang_penetapan": ketua_sidang_penetapan,
                "penguji_sidang_terlaksana": penguji_sidang_terlaksana,
                "total_tugas_penguji": total_tugas_penguji,
                "total_keterlibatan": total_keterlibatan,
                "status": status,
            }
        )
    return out


# =============================================================================
# Modul 13 — Semester Pendek (SP)
# =============================================================================
def sp_jumlah_disetujui(conn, sp_kelas_id):
    return conn.execute(
        "SELECT COUNT(*) c FROM sp_peserta WHERE sp_kelas_id=? AND status_approval='Disetujui'",
        (sp_kelas_id,),
    ).fetchone()["c"]


def sp_status_kelas(conn, kelas_row):
    """Status kapasitas kelas SP dihitung on-the-fly dari jumlah peserta
    berstatus 'Disetujui' dibanding kuota_min/kuota_maks — bukan kolom
    statis, sama prinsipnya dengan realisasi_bap & realisasi program kerja.
    kelas_row minimal punya kolom: id, kuota_min, kuota_maks.

    Dipakai untuk 2 hal: (1) label tampilan di tab Kelas, dan (2) gerbang
    validasi di routes/semester_pendek.py::approval_peserta() -- label
    "Penuh" memicu konfirmasi sebelum peserta baru disetujui melebihi
    kuota_maks (pola sama dengan konfirmasi_bentrok/konfirmasi_transisi)."""
    disetujui = sp_jumlah_disetujui(conn, kelas_row["id"])
    kuota_min = kelas_row["kuota_min"]
    kuota_maks = kelas_row["kuota_maks"]
    if kuota_maks and disetujui >= kuota_maks:
        label = "Penuh"
    elif kuota_min and disetujui < kuota_min:
        label = "Kurang Kuota"
    else:
        label = "Dibuka"
    return {
        "disetujui": disetujui,
        "kuota_min": kuota_min,
        "kuota_maks": kuota_maks,
        "label": label,
    }


def sp_realisasi_pertemuan(conn, sp_kelas_id, jumlah_rencana):
    """Realisasi pertemuan SP — pola sama dengan realisasi_bap (Modul 10),
    dihitung on-the-fly dari COUNT(sp_pertemuan) berstatus 'Terlaksana'."""
    terlaksana = conn.execute(
        "SELECT COUNT(*) c FROM sp_pertemuan WHERE sp_kelas_id=? AND status='Terlaksana'",
        (sp_kelas_id,),
    ).fetchone()["c"]
    tercatat = conn.execute(
        "SELECT COUNT(*) c FROM sp_pertemuan WHERE sp_kelas_id=?", (sp_kelas_id,)
    ).fetchone()["c"]
    persen = round((terlaksana / jumlah_rencana) * 100) if jumlah_rencana else 0
    return {
        "rencana": jumlah_rencana,
        "terlaksana": terlaksana,
        "tercatat": tercatat,
        "persen": min(persen, 100),
    }


def sp_persentase_kehadiran(conn, sp_peserta_id):
    """Persentase kehadiran 1 peserta SP = jumlah sp_presensi.hadir=1 dibagi
    jumlah pertemuan 'Terlaksana' yang sudah tercatat untuk kelasnya —
    inilah dasar syarat kehadiran wajib SP (constants.SP_AMBANG_KEHADIRAN)."""
    row = conn.execute("SELECT sp_kelas_id FROM sp_peserta WHERE id=?", (sp_peserta_id,)).fetchone()
    if not row:
        return {"hadir": 0, "total": 0, "persen": 0}
    total = conn.execute(
        "SELECT COUNT(*) c FROM sp_pertemuan WHERE sp_kelas_id=? AND status='Terlaksana'",
        (row["sp_kelas_id"],),
    ).fetchone()["c"]
    hadir = conn.execute(
        "SELECT COUNT(*) c FROM sp_presensi sp JOIN sp_pertemuan p ON p.id = sp.sp_pertemuan_id "
        "WHERE sp.sp_peserta_id=? AND sp.hadir=1 AND p.status='Terlaksana'",
        (sp_peserta_id,),
    ).fetchone()["c"]
    persen = round((hadir / total) * 100) if total else 0
    return {"hadir": hadir, "total": total, "persen": persen}


def sp_hitung_nilai_akhir(tugas, uts, uas):
    """Nilai akhir SP = bobot Tugas 30% + UTS 30% + UAS 40% (constants.
    SP_BOBOT_*), dikembalikan (nilai_akhir, nilai_huruf) atau (None, None)
    kalau salah satu komponen belum lengkap — supaya tidak menampilkan
    angka semu dari data yang belum penuh."""
    from app.constants import (
        SP_BOBOT_TUGAS,
        SP_BOBOT_UAS,
        SP_BOBOT_UTS,
        nilai_angka_ke_huruf,
    )

    if tugas is None or uts is None or uas is None:
        return None, None
    nilai_akhir = round(tugas * SP_BOBOT_TUGAS + uts * SP_BOBOT_UTS + uas * SP_BOBOT_UAS, 1)
    return nilai_akhir, nilai_angka_ke_huruf(nilai_akhir)


# =============================================================================
# Modul 14 — RPL (Rekognisi Pembelajaran Lampau)
# =============================================================================
def rpl_total_sks_diakui(conn, rpl_pendaftar_id):
    """Total SKS diakui dihitung on-the-fly dari SUM(rpl_konversi.sks_diakui)
    — bukan kolom statis di rpl_pendaftar, supaya selalu sinkron dengan
    baris konversi per mata kuliah yang sesungguhnya."""
    row = conn.execute(
        "SELECT COALESCE(SUM(sks_diakui),0) t FROM rpl_konversi WHERE rpl_pendaftar_id=?",
        (rpl_pendaftar_id,),
    ).fetchone()
    return row["t"]


# =============================================================================
# Modul 15 — Penelitian, PKM & Publikasi/HKI (Tri Dharma Program Studi)
# Seluruh query di bawah membaca tabel Modul 4 (aktivitas_penelitian,
# aktivitas_pkm, luaran_dosen, aktivitas_pendidikan, aktivitas_penunjang)
# lintas SEMUA dosen — tidak ada data yang ditulis ulang/diduplikasi di
# sini, murni agregasi & join baca-saja (kecuali tridharma_tinjauan, satu-
# satunya tabel baru modul ini).
# =============================================================================
# Status yang dianggap "selesai" — SENGAJA disalin persis dari
# routes/sdm.py STATUS_SELESAI (bukan di-import) supaya routes/sdm.py yang
# sudah teruji tidak perlu disentuh sama sekali untuk modul baru ini.
_STATUS_SELESAI_TRIDHARMA = {"Selesai", "Completed", "Published"}


def tahun_dari_tahun_akademik(tahun_akademik):
    """'2025-2026' -> '2025' (tahun awal) — dipakai mencocokkan
    tahun_akademik bebas-teks di aktivitas_penelitian/pkm/luaran_dosen
    terhadap tahun aktif pengaturan aplikasi."""
    if not tahun_akademik:
        return ""
    return str(tahun_akademik).replace("/", "-").split("-")[0].strip()


def tridharma_ringkasan(conn, tahun_akademik_aktif=""):
    """Stat ringkas tingkat program studi untuk Dashboard Modul 15 — semua
    dihitung langsung dari tabel Modul 4, bukan angka contoh seperti demo
    SITIPRO (yang menampilkan Scopus/SINTA palsu tanpa field pendukung)."""
    tahun = tahun_dari_tahun_akademik(tahun_akademik_aktif)
    penelitian_aktif = conn.execute(
        "SELECT COUNT(*) c FROM aktivitas_penelitian WHERE status NOT IN "
        "('Selesai','Completed','Published')"
    ).fetchone()["c"]
    pkm_aktif = conn.execute(
        "SELECT COUNT(*) c FROM aktivitas_pkm WHERE status NOT IN "
        "('Selesai','Completed','Published')"
    ).fetchone()["c"]
    publikasi_tahun_ini = (
        conn.execute(
            "SELECT COUNT(*) c FROM luaran_dosen WHERE jenis_luaran='Publikasi' "
            "AND tahun_akademik LIKE ?",
            (f"%{tahun}%",),
        ).fetchone()["c"]
        if tahun
        else 0
    )
    hki_terdaftar = conn.execute(
        "SELECT COUNT(*) c FROM luaran_dosen WHERE jenis_luaran='HKI'"
    ).fetchone()["c"]
    return {
        "penelitian_aktif": penelitian_aktif,
        "pkm_aktif": pkm_aktif,
        "publikasi_tahun_ini": publikasi_tahun_ini,
        "hki_terdaftar": hki_terdaftar,
    }


def tridharma_sebaran_luaran(conn):
    """Sebaran luaran per jenis_luaran (Publikasi/HKI/Buku/Prosiding/...) —
    angka riil dari COUNT(luaran_dosen), bukan sub-kategori Scopus/SINTA
    yang tidak punya kolom pendukung di skema (lihat catatan Modul 9 soal
    tidak memakai data AI-generated/tebakan)."""
    rows = conn.execute(
        "SELECT jenis_luaran, COUNT(*) c FROM luaran_dosen GROUP BY jenis_luaran ORDER BY c DESC"
    ).fetchall()
    maksimum = max([r["c"] for r in rows], default=0)
    return [
        {
            "jenis_luaran": r["jenis_luaran"],
            "jumlah": r["c"],
            "persen": round((r["c"] / maksimum) * 100) if maksimum else 0,
        }
        for r in rows
    ]


def tridharma_dosen_belum_target(conn, tahun):
    """Dosen yang realisasi luaran-nya (COUNT luaran_dosen per kategori,
    tahun berjalan) masih di bawah target_kinerja_dosen tahun tsb — pola
    hitung sama persis dengan realisasi Target Kinerja per-dosen di
    sdm.py (tab 'target'), digabung di sini lintas SEMUA dosen sekaligus
    untuk kebutuhan monitoring program studi."""
    if not tahun:
        return []
    rows = conn.execute(
        "SELECT t.*, d.nama AS dosen_nama FROM target_kinerja_dosen t "
        "JOIN dosen d ON d.id = t.dosen_id WHERE t.tahun=? ORDER BY d.nama, t.kategori",
        (tahun,),
    ).fetchall()
    out = []
    for r in rows:
        realisasi = conn.execute(
            "SELECT COUNT(*) c FROM luaran_dosen WHERE dosen_id=? AND jenis_luaran=? "
            "AND tahun_akademik LIKE ?",
            (r["dosen_id"], r["kategori"], f"%{tahun}%"),
        ).fetchone()["c"]
        if r["target_angka"] and realisasi < r["target_angka"]:
            out.append(
                {
                    "dosen_nama": r["dosen_nama"],
                    "kategori": r["kategori"],
                    "target": r["target_angka"],
                    "realisasi": realisasi,
                }
            )
    return out


def tridharma_reminder_tenggat(conn, ambang_hari=None):
    """Reminder tenggat laporan hibah (tridharma_tinjauan.tenggat_laporan)
    — pola sama dengan _hitung_reminder di sdm.py, tapi lintas semua
    dosen & tabel penelitian+PKM sekaligus."""
    import datetime as _dt

    from app.constants import AMBANG_TENGGAT_LAPORAN_HARI

    ambang = ambang_hari if ambang_hari is not None else AMBANG_TENGGAT_LAPORAN_HARI
    today = _dt.date.today()
    rows = conn.execute(
        "SELECT tt.*, "
        "COALESCE(ap.judul, apk.judul) AS judul, "
        "COALESCE(dp.nama, dpk.nama) AS dosen_nama, "
        "CASE WHEN tt.penelitian_id IS NOT NULL THEN 'Penelitian' ELSE 'PKM' END AS jenis "
        "FROM tridharma_tinjauan tt "
        "LEFT JOIN aktivitas_penelitian ap ON ap.id = tt.penelitian_id "
        "LEFT JOIN dosen dp ON dp.id = ap.dosen_id "
        "LEFT JOIN aktivitas_pkm apk ON apk.id = tt.pkm_id "
        "LEFT JOIN dosen dpk ON dpk.id = apk.dosen_id "
        "WHERE tt.tenggat_laporan IS NOT NULL AND tt.tenggat_laporan != '' "
        "AND tt.status_tinjauan NOT IN ('Disetujui','Ditolak')"
    ).fetchall()
    out = []
    for r in rows:
        try:
            d = _dt.datetime.strptime(str(r["tenggat_laporan"])[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        sisa = (d - today).days
        if sisa > ambang:
            continue
        out.append(
            {
                "judul": r["judul"],
                "dosen_nama": r["dosen_nama"],
                "jenis": r["jenis"],
                "tenggat": r["tenggat_laporan"],
                "sisa_hari": sisa,
                "status": "Lewat Tenggat" if sisa < 0 else "Segera Jatuh Tempo",
            }
        )
    out.sort(key=lambda x: x["sisa_hari"])
    return out


def tridharma_daftar_usulan(
    conn, jenis_filter=None, status_filter=None, tahun_filter=None, cari=None
):
    """Gabungan aktivitas_penelitian ('Penelitian') + aktivitas_pkm ('PKM')
    lintas SEMUA dosen dalam satu daftar terurut — inilah yang membuat
    modul ini bernilai tambah dibanding sdm.py (yang navigasinya selalu
    per-dosen satu per satu): rekap & filter tingkat program studi.
    LEFT JOIN tridharma_tinjauan untuk status tinjauan institusional."""
    out = []
    if jenis_filter in (None, "", "Penelitian"):
        rows = conn.execute(
            "SELECT ap.*, d.nama AS dosen_nama, tt.id AS tinjauan_id, "
            "tt.status_tinjauan, tt.tenggat_laporan, tt.catatan_tinjauan, tt.ditinjau_oleh "
            "FROM aktivitas_penelitian ap JOIN dosen d ON d.id = ap.dosen_id "
            "LEFT JOIN tridharma_tinjauan tt ON tt.penelitian_id = ap.id ORDER BY ap.id DESC"
        ).fetchall()
        out += [dict(r, jenis="Penelitian") for r in rows]
    if jenis_filter in (None, "", "PKM"):
        rows = conn.execute(
            "SELECT apk.*, d.nama AS dosen_nama, tt.id AS tinjauan_id, "
            "tt.status_tinjauan, tt.tenggat_laporan, tt.catatan_tinjauan, tt.ditinjau_oleh "
            "FROM aktivitas_pkm apk JOIN dosen d ON d.id = apk.dosen_id "
            "LEFT JOIN tridharma_tinjauan tt ON tt.pkm_id = apk.id ORDER BY apk.id DESC"
        ).fetchall()
        out += [dict(r, jenis="PKM") for r in rows]

    if status_filter:
        out = [r for r in out if r["status"] == status_filter]
    if tahun_filter:
        out = [r for r in out if tahun_filter in (r["tahun_akademik"] or "")]
    if cari:
        needle = cari.lower()
        out = [
            r
            for r in out
            if needle in (r["judul"] or "").lower()
            or needle in (r["dosen_nama"] or "").lower()
            or needle in (r.get("skema") or "").lower()
        ]
    out.sort(key=lambda r: (r["tahun_akademik"] or "", r["judul"] or ""), reverse=True)
    return out


def tridharma_daftar_luaran(
    conn, jenis_filter=None, status_filter=None, tahun_filter=None, cari=None
):
    """luaran_dosen lintas semua dosen, dengan filter — dasar tab 'Luaran
    Akademik' Modul 15 (setara LuaranTab SITIPRO, tersinkron ke portofolio
    dosen persis seperti disebutkan di komentar demo aslinya)."""
    q = "SELECT ld.*, d.nama AS dosen_nama FROM luaran_dosen ld JOIN dosen d ON d.id = ld.dosen_id WHERE 1=1"
    params = []
    if jenis_filter:
        q += " AND ld.jenis_luaran=?"
        params.append(jenis_filter)
    if status_filter:
        q += " AND ld.status=?"
        params.append(status_filter)
    if tahun_filter:
        q += " AND ld.tahun_akademik LIKE ?"
        params.append(f"%{tahun_filter}%")
    if cari:
        q += " AND (ld.judul LIKE ? OR d.nama LIKE ? OR ld.nomor_identitas LIKE ?)"
        like = f"%{cari}%"
        params += [like, like, like]
    q += " ORDER BY ld.tahun_akademik DESC, ld.judul"
    return conn.execute(q, params).fetchall()


def tridharma_rekap_pendidikan(conn, tahun_filter=None):
    """Rekap Pendidikan & Pengajaran (aktivitas_pendidikan) per dosen —
    dasar tab 'Pendidikan & Penunjang' Modul 15."""
    q = (
        "SELECT ap.*, d.nama AS dosen_nama FROM aktivitas_pendidikan ap "
        "JOIN dosen d ON d.id = ap.dosen_id WHERE 1=1"
    )
    params = []
    if tahun_filter:
        q += " AND ap.tahun_akademik LIKE ?"
        params.append(f"%{tahun_filter}%")
    q += " ORDER BY d.nama, ap.tahun_akademik DESC"
    return conn.execute(q, params).fetchall()


def tridharma_rekap_penunjang(conn, tahun_filter=None):
    """Rekap Aktivitas Penunjang (reviewer/organisasi profesi/narasumber,
    aktivitas_penunjang) lintas dosen."""
    q = (
        "SELECT apn.*, d.nama AS dosen_nama FROM aktivitas_penunjang apn "
        "JOIN dosen d ON d.id = apn.dosen_id WHERE 1=1"
    )
    params = []
    if tahun_filter:
        q += " AND apn.tahun_akademik LIKE ?"
        params.append(f"%{tahun_filter}%")
    q += " ORDER BY d.nama, apn.tahun_akademik DESC"
    return conn.execute(q, params).fetchall()


# =============================================================================
# Modul 16 — Kerja Sama & Mitra
# =============================================================================
def mitra_jumlah_dokumen_aktif(conn, mitra_id):
    return conn.execute(
        "SELECT COUNT(*) c FROM mitra_dokumen WHERE mitra_id=? AND status='Aktif'",
        (mitra_id,),
    ).fetchone()["c"]


def mitra_jumlah_program(conn, mitra_id):
    return conn.execute(
        "SELECT COUNT(*) c FROM mitra_program WHERE mitra_id=?", (mitra_id,)
    ).fetchone()["c"]


def mitra_status_terkini(conn, mitra_id):
    """Status dokumen terkini 1 mitra untuk badge di direktori: 'Berakhir'
    kalau ada dokumen aktif yang sudah lewat tgl_berakhir, 'Segera
    Berakhir' kalau dalam ambang, 'Aktif' kalau ada dokumen berstatus
    Aktif & belum kadaluarsa, atau 'Belum Ada Dokumen'."""
    import datetime as _dt

    from app.constants import AMBANG_KADALUARSA_MOU_HARI

    today = _dt.date.today()
    rows = conn.execute(
        "SELECT tgl_berakhir FROM mitra_dokumen WHERE mitra_id=? AND status='Aktif'",
        (mitra_id,),
    ).fetchall()
    if not rows:
        total = conn.execute(
            "SELECT COUNT(*) c FROM mitra_dokumen WHERE mitra_id=?", (mitra_id,)
        ).fetchone()["c"]
        return "Belum Ada Dokumen" if not total else "Tidak Ada Dokumen Aktif"
    label = "Aktif"
    for r in rows:
        try:
            d = _dt.datetime.strptime(str(r["tgl_berakhir"])[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        sisa = (d - today).days
        if sisa < 0:
            return "Berakhir"
        if sisa <= AMBANG_KADALUARSA_MOU_HARI:
            label = "Segera Berakhir"
    return label


def mitra_ringkasan(conn):
    """Stat ringkas Dashboard Modul 16 — semua angka riil dari tabel
    mitra/mitra_dokumen/mitra_program, bukan angka contoh seperti demo."""
    total_mitra = conn.execute("SELECT COUNT(*) c FROM mitra").fetchone()["c"]
    dokumen_aktif = conn.execute(
        "SELECT COUNT(*) c FROM mitra_dokumen WHERE status='Aktif'"
    ).fetchone()["c"]
    program_berjalan = conn.execute(
        "SELECT COUNT(*) c FROM mitra_program WHERE status='Berjalan'"
    ).fetchone()["c"]
    segera_berakhir = len(mitra_reminder_dokumen(conn))
    return {
        "total_mitra": total_mitra,
        "dokumen_aktif": dokumen_aktif,
        "program_berjalan": program_berjalan,
        "segera_berakhir": segera_berakhir,
    }


def mitra_sebaran_kategori(conn):
    """Sebaran mitra per kategori & skala (Nasional/Internasional) — angka
    riil dari GROUP BY, pengganti 'Sebaran Mitra Kategori IKU 6' demo
    SITIPRO yang datanya statis/contoh."""
    kategori = conn.execute(
        "SELECT kategori, COUNT(*) c FROM mitra GROUP BY kategori ORDER BY c DESC"
    ).fetchall()
    internasional = conn.execute(
        "SELECT COUNT(*) c FROM mitra WHERE skala='Internasional'"
    ).fetchone()["c"]
    return {"per_kategori": kategori, "internasional": internasional}


def mitra_reminder_dokumen(conn, ambang_hari=None):
    """Reminder dokumen MoU/MoA/IA yang segera/sudah berakhir — pola sama
    dengan reminder masa berlaku sertifikat (Modul 4) & tenggat laporan
    Tri Dharma (Modul 15), kali ini untuk dokumen kerja sama."""
    import datetime as _dt

    from app.constants import AMBANG_KADALUARSA_MOU_HARI

    ambang = ambang_hari if ambang_hari is not None else AMBANG_KADALUARSA_MOU_HARI
    today = _dt.date.today()
    rows = conn.execute(
        "SELECT md.*, m.nama AS mitra_nama FROM mitra_dokumen md "
        "JOIN mitra m ON m.id = md.mitra_id "
        "WHERE md.status='Aktif' AND md.tgl_berakhir IS NOT NULL AND md.tgl_berakhir != ''"
    ).fetchall()
    out = []
    for r in rows:
        try:
            d = _dt.datetime.strptime(str(r["tgl_berakhir"])[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        sisa = (d - today).days
        if sisa > ambang:
            continue
        out.append(
            {
                "mitra_nama": r["mitra_nama"],
                "jenis_dokumen": r["jenis_dokumen"],
                "judul": r["judul"] or r["jenis_dokumen"],
                "tgl_berakhir": r["tgl_berakhir"],
                "sisa_hari": sisa,
                "status": "Sudah Berakhir" if sisa < 0 else "Segera Berakhir",
            }
        )
    out.sort(key=lambda x: x["sisa_hari"])
    return out


def mitra_rata_kepuasan(conn, mitra_id=None):
    """Rata-rata skor kepuasan mitra (mitra_program.skor_kepuasan) dari
    program yang SUDAH diisi skornya saja — None kalau belum ada satupun
    yang diisi, supaya tidak menampilkan angka semu seperti 85% statis
    di demo SITIPRO (yang tidak berasal dari input evaluasi sungguhan)."""
    q = "SELECT skor_kepuasan FROM mitra_program WHERE skor_kepuasan IS NOT NULL"
    params = []
    if mitra_id:
        q += " AND mitra_id=?"
        params.append(mitra_id)
    rows = conn.execute(q, params).fetchall()
    nilai = [r["skor_kepuasan"] for r in rows]
    if not nilai:
        return None
    return round(sum(nilai) / len(nilai))


# =============================================================================
# Modul 17 — Mutu: IKU, Akreditasi & Audit Mutu Internal (SPMI)
# =============================================================================
def _iku_derived(conn, nomor, tahun):
    """Realisasi 6 dari 8 IKU dihitung on-the-fly lintas modul yang sudah
    ada (lihat komentar db.py Modul 17) — mengembalikan (nilai, satuan,
    detail) atau (None, satuan, detail) kalau penyebutnya 0 (belum bisa
    dihitung, bukan 0%)."""
    if nomor == 1:
        # Audit bug baru — sebelumnya TIDAK difilter per tahun sama sekali
        # (tracer_study tidak punya kolom tahun/tanggal sendiri), sementara
        # IKU2/3/5/6 semuanya konsisten memfilter. Sekarang diikat ke tahun
        # KELULUSAN (yudisium.tgl_yudisium) mahasiswa yang bersangkutan —
        # konsisten dengan cara IKU lain memfilter tanggal via LIKE '%tahun%',
        # dan sejalan dengan praktik pelaporan BAN-PT/LAMEMBA yang melacak
        # IKU1 per kohort tahun lulus, bukan seluruh histori tracer study.
        total = conn.execute(
            "SELECT COUNT(*) c FROM tracer_study t "
            "JOIN yudisium y ON y.mahasiswa_id = t.mahasiswa_id "
            "WHERE y.tgl_yudisium LIKE ?",
            (f"%{tahun}%",),
        ).fetchone()["c"]
        layak = conn.execute(
            "SELECT COUNT(*) c FROM tracer_study t "
            "JOIN yudisium y ON y.mahasiswa_id = t.mahasiswa_id "
            "WHERE y.tgl_yudisium LIKE ? AND t.status_saat_ini IN "
            "('Bekerja - Sesuai Bidang','Wiraswasta')",
            (f"%{tahun}%",),
        ).fetchone()["c"]
        nilai = round(layak / total * 100, 1) if total else None
        return (
            nilai,
            "%",
            f"{layak}/{total} responden tracer study lulusan tahun {tahun} bekerja layak/wiraswasta",
        )
    if nomor == 2:
        numerator = conn.execute(
            "SELECT COALESCE(SUM(jumlah),0) c FROM mitra_luaran WHERE jenis_luaran="
            "'Mahasiswa Magang/MBKM' AND tanggal LIKE ?",
            (f"%{tahun}%",),
        ).fetchone()["c"]
        denom = conn.execute("SELECT COUNT(*) c FROM mahasiswa WHERE status='Aktif'").fetchone()[
            "c"
        ]
        nilai = round(numerator / denom * 100, 1) if denom else None
        return nilai, "%", f"{numerator} mahasiswa MBKM dari {denom} mahasiswa aktif"
    if nomor == 3:
        numerator = conn.execute(
            "SELECT COUNT(DISTINCT dosen_id) c FROM aktivitas_penunjang WHERE tahun_akademik LIKE ?",
            (f"%{tahun}%",),
        ).fetchone()["c"]
        denom = conn.execute("SELECT COUNT(*) c FROM dosen WHERE aktif=1").fetchone()["c"]
        nilai = round(numerator / denom * 100, 1) if denom else None
        return (
            nilai,
            "%",
            f"{numerator} dari {denom} dosen aktif berkegiatan penunjang di luar kampus",
        )
    if nomor == 4:
        n = conn.execute(
            "SELECT COUNT(*) c FROM mitra_program WHERE jenis_program='Praktisi Mengajar' "
            "AND tgl_mulai LIKE ?",
            (f"%{tahun}%",),
        ).fetchone()["c"]
        return n, "program", f"{n} program praktisi mengajar tercatat tahun ini"
    if nomor == 5:
        n = conn.execute(
            "SELECT COUNT(*) c FROM luaran_dosen WHERE jenis_luaran IN ('Publikasi','HKI') "
            "AND tahun_akademik LIKE ?",
            (f"%{tahun}%",),
        ).fetchone()["c"]
        return n, "luaran", f"{n} publikasi/HKI dosen tahun ini"
    if nomor == 6:
        n = conn.execute(
            "SELECT COUNT(DISTINCT m.id) c FROM mitra m JOIN mitra_dokumen d ON d.mitra_id=m.id "
            "WHERE m.skala='Internasional' AND d.status='Aktif'"
        ).fetchone()["c"]
        return n, "mitra", f"{n} mitra internasional dengan dokumen kerja sama aktif"
    return None, "", ""


def iku_ringkasan(conn, tahun):
    """Gabungan 8 IKU: 6 dihitung otomatis (_iku_derived), 2 diisi manual
    (target_iku.realisasi_manual) karena SIMPRODI belum punya sumber data
    untuk itu — lihat constants.DAFTAR_IKU untuk penanda DERIVED/MANUAL."""
    from app.constants import DAFTAR_IKU

    out = []
    for nomor, nama, cara in DAFTAR_IKU:
        target_row = conn.execute(
            "SELECT * FROM target_iku WHERE tahun=? AND nomor_iku=?", (tahun, nomor)
        ).fetchone()
        if cara == "DERIVED":
            nilai, satuan, detail = _iku_derived(conn, nomor, tahun)
        else:
            nilai = target_row["realisasi_manual"] if target_row else None
            satuan = "%"
            detail = "Diisi manual oleh Kaprodi (belum ada sumber data otomatis di SIMPRODI)"
        out.append(
            {
                "nomor": nomor,
                "nama": nama,
                "cara": cara,
                "nilai": nilai,
                "satuan": satuan,
                "detail": detail,
                "target": target_row["target_nilai"] if target_row else None,
                "catatan": target_row["catatan"] if target_row else "",
            }
        )
    return out


def akreditasi_progres(conn):
    """Progres akreditasi dihitung on-the-fly dari jumlah kriteria
    berstatus 'Final' dibanding total 9 kriteria LAMEMBA — bukan angka
    manual yang bisa telat diperbarui."""
    rows = conn.execute(
        "SELECT ak.*, d.nama AS pic_nama FROM akreditasi_kriteria ak "
        "LEFT JOIN dosen d ON d.id = ak.pic_dosen_id ORDER BY ak.nomor_kriteria"
    ).fetchall()
    total = len(rows)
    final = len([r for r in rows if r["status"] == "Final"])
    persen = round((final / total) * 100) if total else 0
    return {"rows": rows, "total": total, "final": final, "persen": persen}


def akreditasi_jumlah_bukti(conn, kriteria_id):
    return conn.execute(
        "SELECT COUNT(*) c FROM akreditasi_bukti WHERE kriteria_id=?", (kriteria_id,)
    ).fetchone()["c"]


def ami_ringkasan(conn):
    siklus_berjalan = conn.execute(
        "SELECT COUNT(*) c FROM ami_siklus WHERE status='Berjalan'"
    ).fetchone()["c"]
    temuan_terbuka = conn.execute(
        "SELECT COUNT(*) c FROM ami_temuan WHERE status IN ('Terbuka','Proses Tindak Lanjut')"
    ).fetchone()["c"]
    temuan_mayor_terbuka = conn.execute(
        "SELECT COUNT(*) c FROM ami_temuan WHERE kategori='KTS Mayor' "
        "AND status IN ('Terbuka','Proses Tindak Lanjut')"
    ).fetchone()["c"]
    return {
        "siklus_berjalan": siklus_berjalan,
        "temuan_terbuka": temuan_terbuka,
        "temuan_mayor_terbuka": temuan_mayor_terbuka,
    }


def ami_reminder_tenggat(conn, ambang_hari=14):
    """Reminder tenggat tindak lanjut temuan AMI yang belum Selesai/
    Terverifikasi — pola sama dengan reminder tenggat laporan Tri Dharma
    (Modul 15) & kadaluarsa dokumen mitra (Modul 16)."""
    import datetime as _dt

    today = _dt.date.today()
    rows = conn.execute(
        "SELECT t.*, s.nama AS siklus_nama, d.nama AS pic_nama FROM ami_temuan t "
        "JOIN ami_siklus s ON s.id = t.siklus_id LEFT JOIN dosen d ON d.id = t.pic_dosen_id "
        "WHERE t.status NOT IN ('Selesai','Terverifikasi') "
        "AND t.tenggat IS NOT NULL AND t.tenggat != ''"
    ).fetchall()
    out = []
    for r in rows:
        try:
            d = _dt.datetime.strptime(str(r["tenggat"])[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        sisa = (d - today).days
        if sisa > ambang_hari:
            continue
        out.append(
            {
                "uraian": r["uraian_temuan"],
                "siklus_nama": r["siklus_nama"],
                "pic_nama": r["pic_nama"],
                "kategori": r["kategori"],
                "tenggat": r["tenggat"],
                "sisa_hari": sisa,
                "status": "Lewat Tenggat" if sisa < 0 else "Segera Jatuh Tempo",
            }
        )
    out.sort(key=lambda x: x["sisa_hari"])
    return out


def sdm_reminder_semua(conn, ambang_hari=None):
    """Reminder Masa Berlaku lintas SEMUA dosen (sertifikat/luaran &
    peran akademik) — versi agregat dari sdm._hitung_reminder() (yang
    dipakai per-dosen di sdm_detail.html). Dipakai Pusat Notifikasi
    terpusat, pola sama dengan tridharma_reminder_tenggat/
    mitra_reminder_dokumen/ami_reminder_tenggat di atas."""
    import datetime as _dt

    from app.constants import REMINDER_MASA_BERLAKU_HARI

    ambang = ambang_hari if ambang_hari is not None else REMINDER_MASA_BERLAKU_HARI
    today = _dt.date.today()
    rows = conn.execute(
        "SELECT d.nama AS dosen_nama, l.judul AS nama, l.masa_berlaku AS tgl "
        "FROM luaran_dosen l JOIN dosen d ON d.id = l.dosen_id "
        "WHERE d.aktif=1 AND l.masa_berlaku IS NOT NULL AND l.masa_berlaku != ''"
    ).fetchall()
    rows += conn.execute(
        "SELECT d.nama AS dosen_nama, p.nama_instansi_kegiatan AS nama, p.tgl_selesai AS tgl "
        "FROM peran_akademik_dosen p JOIN dosen d ON d.id = p.dosen_id "
        "WHERE d.aktif=1 AND p.tgl_selesai IS NOT NULL AND p.tgl_selesai != ''"
    ).fetchall()
    out = []
    for r in rows:
        try:
            d = _dt.datetime.strptime(str(r["tgl"])[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        sisa = (d - today).days
        if sisa > ambang:
            continue
        out.append(
            {
                "dosen_nama": r["dosen_nama"],
                "nama": r["nama"],
                "tgl": r["tgl"],
                "sisa_hari": sisa,
                "status": "Kadaluarsa" if sisa < 0 else "Segera Berakhir",
            }
        )
    out.sort(key=lambda x: x["sisa_hari"])
    return out


def kelengkapan_data_scan(conn):
    """Pemindai Kelengkapan Data — padanan jujur untuk 'Data Integrity'
    di demo SITIPRO (yang cuma angka statis '124 issues'): membaca
    LANGSUNG tabel-tabel lintas modul yang sudah ada dan menghitung
    celah data riil yang relevan untuk kesiapan akreditasi/pelaporan."""
    checks = []
    kur = conn.execute("SELECT id FROM kurikulum_versi WHERE status='Aktif' LIMIT 1").fetchone()
    if kur:
        n = conn.execute(
            "SELECT COUNT(*) c FROM mata_kuliah WHERE kurikulum_id=? AND rps_status != 'Disahkan'",
            (kur["id"],),
        ).fetchone()["c"]
        checks.append(
            {
                "label": "Mata kuliah kurikulum aktif dengan RPS belum disahkan",
                "jumlah": n,
                "endpoint": "kurikulum.index",
                "params": {"tab": "struktur"},
            }
        )
        n2 = conn.execute(
            "SELECT COUNT(*) c FROM mata_kuliah mk WHERE mk.kurikulum_id=? "
            "AND NOT EXISTS (SELECT 1 FROM cpmk c WHERE c.mata_kuliah_id = mk.id)",
            (kur["id"],),
        ).fetchone()["c"]
        checks.append(
            {
                "label": "Mata kuliah kurikulum aktif tanpa CPMK terpetakan",
                "jumlah": n2,
                "endpoint": "kurikulum.index",
                "params": {"tab": "cpmk"},
            }
        )
    n3 = conn.execute(
        "SELECT COUNT(*) c FROM dosen WHERE aktif=1 AND (nidn IS NULL OR nidn='')"
    ).fetchone()["c"]
    checks.append(
        {"label": "Dosen aktif tanpa NIDN", "jumlah": n3, "endpoint": "dosen.index", "params": {}}
    )
    n4 = conn.execute(
        "SELECT COUNT(*) c FROM mahasiswa m JOIN wisuda w ON w.mahasiswa_id = m.id "
        "WHERE m.id NOT IN (SELECT mahasiswa_id FROM tracer_study)"
    ).fetchone()["c"]
    checks.append(
        {
            "label": "Alumni (sudah wisuda) tanpa data tracer study",
            "jumlah": n4,
            "endpoint": "kelulusan.tracer_list",
            "params": {},
        }
    )
    n5 = conn.execute(
        "SELECT COUNT(*) c FROM mitra_dokumen WHERE file_path IS NULL OR file_path=''"
    ).fetchone()["c"]
    checks.append(
        {
            "label": "Dokumen kerja sama (MoU/MoA/IA) tanpa file terlampir",
            "jumlah": n5,
            "endpoint": "kerjasama.index",
            "params": {"tab": "mitra"},
        }
    )
    n6 = conn.execute(
        "SELECT COUNT(*) c FROM sp_peserta WHERE status_approval='Disetujui' AND nilai_akhir IS NULL"
    ).fetchone()["c"]
    checks.append(
        {
            "label": "Peserta Semester Pendek disetujui, nilai akhir belum diisi",
            "jumlah": n6,
            "endpoint": "sp.index",
            "params": {"tab": "nilai"},
        }
    )
    return checks


def log_aktivitas_daftar(conn, cari=None, tanggal_dari=None, tanggal_sampai=None, limit=300):
    """Menampilkan log_aktivitas — tabel yang sudah ditulis oleh
    db.log() di HAMPIR SETIAP route sejak Fase Fondasi, tapi baru di
    Modul 17 ini punya UI baca/pencarian. Padanan jujur untuk 'Security
    & Logs' di demo SITIPRO.

    Audit Menyeluruh Phase 4 — pencarian `cari` diperluas mencakup kolom
    `entitas` (mis. cari "Sidang" akan menemukan semua audit event yang
    entitasnya Sidang), selain aksi/detail seperti sebelumnya."""
    q = "SELECT * FROM log_aktivitas WHERE 1=1"
    params = []
    if cari:
        q += " AND (aksi LIKE ? OR detail LIKE ? OR entitas LIKE ?)"
        like = f"%{cari}%"
        params += [like, like, like]
    if tanggal_dari:
        q += " AND waktu >= ?"
        params.append(tanggal_dari)
    if tanggal_sampai:
        q += " AND waktu <= ?"
        params.append(f"{tanggal_sampai} 23:59:59")
    q += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return conn.execute(q, params).fetchall()


def log_aktivitas_ringkasan(conn):
    import datetime as _dt

    total = conn.execute("SELECT COUNT(*) c FROM log_aktivitas").fetchone()["c"]
    today = _dt.date.today().isoformat()
    hari_ini = conn.execute(
        "SELECT COUNT(*) c FROM log_aktivitas WHERE waktu LIKE ?", (f"{today}%",)
    ).fetchone()["c"]
    return {"total": total, "hari_ini": hari_ini}
