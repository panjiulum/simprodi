# -*- coding: utf-8 -*-
"""routes/pelaksanaan.py — Seminar Proposal & Sidang Skripsi, termasuk
deteksi bentrok jadwal (pakai logic.cek_bentrok yang sudah teruji)."""

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
from app import datetools as dtools
from app import db as _db
from app import error_utils as EH
from app import logic as L

bp = Blueprint("pelaksanaan", __name__, url_prefix="/pelaksanaan")


def _mhs_dengan_sk(conn):
    return conn.execute(
        "SELECT m.id, m.nim, m.nama FROM mahasiswa m "
        "JOIN penetapan_pembimbing pp ON pp.mahasiswa_id=m.id ORDER BY m.nama"
    ).fetchall()


def _dosen_lookup(conn):
    return conn.execute("SELECT id, nama FROM dosen WHERE aktif=1 ORDER BY nama").fetchall()


def _ruangan_lookup(conn):
    return conn.execute("SELECT id, nama FROM ruangan ORDER BY nama").fetchall()


# Audit Modul Pelaksanaan — Seminar & Sidang sebelumnya TIDAK punya filter
# semester/tahap apa pun (semua mahasiswa yang pernah didaftarkan tampil
# sekaligus dalam 1 tabel panjang), padahal seminar & sidang berjalan
# beberapa gelombang/tahap per semester (beda dari pengajuan judul yang
# cuma 1x di awal). Helper di bawah mengikuti pola yang SAMA PERSIS dengan
# routes/akademik.py::_tahap_list & routes/rekap.py::_tahap_opsi, supaya
# konsisten dengan modul lain yang sudah pakai tahap_pengajuan dinamis.
def _tahap_list(conn):
    rows = _db.get_tahap_list(conn)
    if rows:
        return [r["nama"] for r in rows]
    lama = [_db.get_setting(conn, "nama_tahap_1"), _db.get_setting(conn, "nama_tahap_2")]
    return [t for t in lama if t]


def _tahap_opsi(conn):
    return ["Semua"] + _tahap_list(conn)


# --------------------------------------------------------------------- Seminar
@bp.route("/seminar")
def seminar_list():
    conn = current_app.get_db()
    tahap = request.args.get("tahap", "Semua")
    q = "SELECT s.*, m.nim, m.nama FROM seminar s JOIN mahasiswa m ON m.id=s.mahasiswa_id"
    params = []
    if tahap and tahap != "Semua":
        q += " WHERE s.tahap LIKE ?"
        params.append(f"%{tahap}%")
    q += " ORDER BY m.nama"
    rows = conn.execute(q, params).fetchall()
    edit_id = request.args.get("edit", type=int)
    edit_row = None
    if edit_id:
        edit_row = conn.execute("SELECT * FROM seminar WHERE id=?", (edit_id,)).fetchone()
    return render_template(
        "seminar.html",
        rows=rows,
        edit_row=edit_row,
        mhs_list=_mhs_dengan_sk(conn),
        dosen_list=_dosen_lookup(conn),
        ruangan_list=_ruangan_lookup(conn),
        checklist=C.SEMINAR_CHECKLIST,
        STATUS_SEMINAR_LIST=C.STATUS_SEMINAR_LIST,
        ruangan_nama=lambda rid: L.ruangan_nama(conn, rid),
        tahap=tahap,
        tahap_opsi=_tahap_opsi(conn),
        tahap_list=_tahap_list(conn),
        daftar_periode=_db.get_periode_list(conn),
    )


def _validasi_status_seminar(status):
    """Audit P0 #10 — sebelumnya `f.get("status", "Terdaftar")` diterima
    APA PUN yang dikirim form/klien HTTP langsung ke kolom `status`, tanpa
    dicek terhadap C.STATUS_SEMINAR_LIST. Karena rekap honor & dashboard
    membandingkan status pakai string exact-match ("== 'Selesai'"), status
    typo/asing akan lolos tersimpan tapi diam-diam tidak pernah terhitung
    di rekap mana pun, tanpa ada peringatan apa pun ke operator."""
    return status if status in C.STATUS_SEMINAR_LIST else "Terdaftar"


@bp.route("/seminar/simpan", methods=["POST"])
def seminar_simpan():
    conn = current_app.get_db()
    f = request.form
    sid = f.get("id", type=int)
    mid = f.get("mahasiswa_id", type=int)
    if not mid:
        flash("Pilih mahasiswa terlebih dahulu (harus sudah ber-SK Pembimbing).", "error")
        return redirect(url_for("pelaksanaan.seminar_list"))

    def gid(name):
        v = f.get(name, "")
        return int(v) if v else None

    tgl = dtools.normalize_tanggal_text(f.get("tgl_seminar", ""))
    jam = f.get("jam", "")
    ruangan_id = gid("ruangan_id")
    dosen_ids = {
        i
        for i in (gid("penguji_ketua_id"), gid("penguji_anggota1_id"), gid("penguji_anggota2_id"))
        if i
    }

    if tgl and jam:
        temuan = L.cek_bentrok(
            conn,
            "Seminar",
            mid,
            tgl,
            jam,
            ruangan_id,
            dosen_ids,
            exclude_jenis="Seminar",
            exclude_id=sid,
        )
        errors = [t["pesan"] for t in temuan if t["level"] == "error"]
        if errors and not f.get("konfirmasi_bentrok"):
            return render_template(
                "_bentrok_confirm.html",
                errors=errors,
                action=url_for("pelaksanaan.seminar_simpan"),
                form=f,
            )

    # Audit Modul Pelaksanaan — tahap MILIK BARIS SEMINAR sendiri (lihat
    # komentar di _tahap_list di atas), bukan diwariskan dari tahap SK
    # Pembimbing. periode_akademik_id/tahap_pengajuan_id dicoba diisi kalau
    # kombinasi periode+nama tahap yang dipilih memang terdaftar di master
    # tahap_pengajuan; kolom `tahap` TEXT tetap jadi sumber filter (sama
    # seperti pola pengajuan_judul/penetapan_pembimbing).
    status = _validasi_status_seminar(f.get("status", "Terdaftar"))
    periode_id = f.get("periode_akademik_id", type=int)
    tahap_nama = f.get("tahap", "")
    tahap_pengajuan_id = None
    if periode_id and tahap_nama:
        trow = conn.execute(
            "SELECT id FROM tahap_pengajuan WHERE periode_akademik_id=? AND nama=?",
            (periode_id, tahap_nama),
        ).fetchone()
        tahap_pengajuan_id = trow["id"] if trow else None

    # Snapshot tarif honor SAAT status diset 'Selesai' — sekali dibekukan,
    # tidak ditimpa lagi walau baris ini diedit lagi nanti (supaya honor
    # yang sudah direkap ke keuangan untuk tahap ybs tidak berubah kalau
    # tarif di Pengaturan direvisi belakangan). Baris baru yang belum
    # 'Selesai' dibiarkan NULL sampai statusnya benar-benar 'Selesai'.
    tarif_snapshot = None
    if sid:
        existing = conn.execute(
            "SELECT tarif_honor_diterapkan FROM seminar WHERE id=?", (sid,)
        ).fetchone()
        tarif_snapshot = existing["tarif_honor_diterapkan"] if existing else None
    if status == "Selesai" and not tarif_snapshot:
        tarif_snapshot = float(_db.get_setting(conn, "tarif_honor_seminar", "20000"))

    chk = [1 if f.get(k) == "on" else 0 for k, _ in C.SEMINAR_CHECKLIST]
    data = tuple(
        [status, f.get("tgl_daftar", ""), tgl, jam]
        + chk
        + [
            f.get("judul_diseminarkan", ""),
            f.get("ada_perubahan", "Tidak"),
            gid("penguji_ketua_id"),
            gid("penguji_anggota1_id"),
            gid("penguji_anggota2_id"),
            ruangan_id,
            periode_id,
            tahap_pengajuan_id,
            tahap_nama,
            tarif_snapshot,
            mid,
        ]
    )
    try:
        if sid:
            # Audit Phase 4 — nilai lama status seminar, utk audit event
            # "status: X -> Y" kalau memang berubah (sama pola dgn sidang).
            sebelum = conn.execute("SELECT status FROM seminar WHERE id=?", (sid,)).fetchone()
            status_lama = sebelum["status"] if sebelum else None
            conn.execute(
                "UPDATE seminar SET status=?,tgl_daftar=?,tgl_seminar=?,jam=?,chk_persetujuan=?,"
                "chk_bukti_bayar=?,chk_mendeley=?,chk_krs=?,chk_bimbingan=?,chk_hardcopy=?,"
                "chk_turnitin=?,judul_diseminarkan=?,ada_perubahan=?,penguji_ketua_id=?,"
                "penguji_anggota1_id=?,penguji_anggota2_id=?,ruangan_id=?,periode_akademik_id=?,"
                "tahap_pengajuan_id=?,tahap=?,tarif_honor_diterapkan=?,mahasiswa_id=? WHERE id=?",
                data + (sid,),
            )
            if status_lama != status:
                _db.log(
                    conn, "Update Seminar", str(mid),
                    modul="Pelaksanaan", entitas="Seminar", entitas_id=sid,
                    nilai_lama=status_lama, nilai_baru=status,
                )
            else:
                _db.log(conn, "Update Seminar", str(mid), modul="Pelaksanaan", entitas="Seminar", entitas_id=sid)
            flash("Data seminar diperbarui.", "ok")
        else:
            cur = conn.execute(
                "INSERT INTO seminar(status,tgl_daftar,tgl_seminar,jam,chk_persetujuan,"
                "chk_bukti_bayar,chk_mendeley,chk_krs,chk_bimbingan,chk_hardcopy,chk_turnitin,"
                "judul_diseminarkan,ada_perubahan,penguji_ketua_id,penguji_anggota1_id,"
                "penguji_anggota2_id,ruangan_id,periode_akademik_id,tahap_pengajuan_id,tahap,"
                "tarif_honor_diterapkan,mahasiswa_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                data,
            )
            _db.log(
                conn, "Tambah Seminar", str(mid),
                modul="Pelaksanaan", entitas="Seminar", entitas_id=cur.lastrowid,
                nilai_lama=None, nilai_baru=status,
            )
            # Antisipasi 'seminar ulang' — mahasiswa boleh punya lebih dari 1
            # baris seminar (lihat _rebuild_seminar_tanpa_unique di db.py),
            # jadi pesan ini TIDAK lagi menyiratkan seminar hanya sekali.
            flash(
                "Data seminar disimpan. Mahasiswa boleh punya lebih dari 1 baris "
                "seminar (seminar ulang) bila memang diperlukan.",
                "ok",
            )
        conn.commit()
        # Audit P0 #3 — status_ta harus ikut disinkronkan saat seminar
        # berubah (bukan cuma saat sidang berubah); "Selesai"-nya seminar
        # adalah salah satu syarat status_ta naik ke "Proses Bimbingan".
        L.recalculate_status_ta(conn, mid, dipicu_oleh="Seminar disimpan")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Terjadi kendala saat menyimpan data seminar")
    return redirect(url_for("pelaksanaan.seminar_list"))


@bp.route("/seminar/<int:sid>/hapus", methods=["POST"])
def seminar_hapus(sid):
    conn = current_app.get_db()
    row = conn.execute("SELECT mahasiswa_id FROM seminar WHERE id=?", (sid,)).fetchone()
    conn.execute("DELETE FROM seminar WHERE id=?", (sid,))
    conn.commit()
    if row:
        # Audit P0 #1 — recalculate_status_ta() menggantikan tidak-adanya
        # sinkronisasi sama sekali di sini sebelumnya: kalau baris seminar
        # "Selesai" yang jadi dasar status_ta="Proses Bimbingan" dihapus,
        # status_ta perlu dihitung ulang, bisa jadi mundur ke "Mengajukan
        # Judul" kalau tidak ada SK Pembimbing/seminar lain yang tersisa.
        L.recalculate_status_ta(conn, row["mahasiswa_id"], dipicu_oleh="Seminar dihapus")
    flash("Data seminar dihapus.", "ok")
    return redirect(url_for("pelaksanaan.seminar_list"))


# ---------------------------------------------------------------------- Sidang
@bp.route("/sidang")
def sidang_list():
    conn = current_app.get_db()
    tahap = request.args.get("tahap", "Semua")
    q = "SELECT sd.*, m.nim, m.nama FROM sidang sd JOIN mahasiswa m ON m.id=sd.mahasiswa_id"
    params = []
    if tahap and tahap != "Semua":
        q += " WHERE sd.tahap LIKE ?"
        params.append(f"%{tahap}%")
    q += " ORDER BY sd.id DESC"
    rows = conn.execute(q, params).fetchall()
    edit_id = request.args.get("edit", type=int)
    edit_row = None
    if edit_id:
        edit_row = conn.execute("SELECT * FROM sidang WHERE id=?", (edit_id,)).fetchone()
    return render_template(
        "sidang.html",
        rows=rows,
        edit_row=edit_row,
        mhs_list=_mhs_dengan_sk(conn),
        dosen_list=_dosen_lookup(conn),
        ruangan_list=_ruangan_lookup(conn),
        STATUS_KELULUSAN_SIDANG=C.STATUS_KELULUSAN_SIDANG,
        ruangan_nama=lambda rid: L.ruangan_nama(conn, rid),
        tahap=tahap,
        tahap_opsi=_tahap_opsi(conn),
        tahap_list=_tahap_list(conn),
        daftar_periode=_db.get_periode_list(conn),
    )


@bp.route("/sidang/simpan", methods=["POST"])
def sidang_simpan():
    conn = current_app.get_db()
    f = request.form
    sid = f.get("id", type=int)
    mid = f.get("mahasiswa_id", type=int)
    if not mid:
        flash("Pilih mahasiswa terlebih dahulu (harus sudah ber-SK Pembimbing).", "error")
        return redirect(url_for("pelaksanaan.sidang_list"))
    if not f.get("status_kelulusan") or f.get("status_kelulusan") not in C.STATUS_KELULUSAN_SIDANG:
        # Audit P0 #10 — sebelumnya hanya dicek "ada isinya" (`not f.get(...)`),
        # bukan dicek terhadap C.STATUS_KELULUSAN_SIDANG. Nilai di luar
        # LULUS/TIDAK LULUS/TUNDA bisa lolos tersimpan dan merusak seluruh
        # rantai turunannya: status_sidang_mahasiswa() (LULUS-priority),
        # recalculate_status_ta(), sync_yudisium_dari_sidang(), rekap honor.
        flash("Status Kelulusan wajib dipilih dari daftar yang tersedia (LULUS/TIDAK LULUS/TUNDA).", "error")
        return redirect(url_for("pelaksanaan.sidang_list"))

    def gid(name):
        v = f.get(name, "")
        return int(v) if v else None

    tgl = dtools.normalize_tanggal_text(f.get("tgl_sidang", ""))
    jam = f.get("jam_sidang", "")
    ruangan_id = gid("ruangan_id")
    dosen_ids = {
        i
        for i in (
            gid("ketua_id"),
            gid("sekretaris_id"),
            gid("anggota1_id"),
            gid("anggota2_id"),
            gid("anggota3_id"),
        )
        if i
    }

    if tgl and jam:
        temuan = L.cek_bentrok(
            conn,
            "Sidang",
            mid,
            tgl,
            jam,
            ruangan_id,
            dosen_ids,
            exclude_jenis="Sidang",
            exclude_id=sid,
        )
        errors = [t["pesan"] for t in temuan if t["level"] == "error"]
        if errors and not f.get("konfirmasi_bentrok"):
            return render_template(
                "_bentrok_confirm.html",
                errors=errors,
                action=url_for("pelaksanaan.sidang_simpan"),
                form=f,
            )

    # Audit poin 6.3 — validasi urutan tahapan: Sidang baru dijadwalkan
    # setelah Seminar "Selesai". Hanya mahasiswa BARU sekali sidang (sid
    # kosong) yang diperiksa — mahasiswa dengan sidang ulang (baris ke-2+)
    # sudah pasti lolos Seminar sebelumnya.
    if not sid:
        peringatan = L.validasi_transisi_status(conn, mid, tujuan="Sidang")
        if peringatan and not f.get("konfirmasi_transisi"):
            return render_template(
                "_transisi_confirm.html",
                peringatan=peringatan,
                action=url_for("pelaksanaan.sidang_simpan"),
                form=f,
            )

    nilai = f.get("nilai_angka", "")
    nilai = float(nilai) if nilai else None
    status_kelulusan = f.get("status_kelulusan")

    # Audit Modul Pelaksanaan — tahap MILIK BARIS SIDANG sendiri, sama
    # seperti Seminar di atas (lihat komentar _tahap_list). Honor penguji
    # sidang cair untuk SETIAP baris sidang (termasuk sidang ulang, tidak
    # peduli lulus/tidak), jadi tarif_penguji_diterapkan dibekukan setiap
    # kali baris disimpan pertama kali. Honor pembimbing 1 & 2 baru cair
    # kalau mahasiswa LULUS di baris sidang ini, jadi tarif pembimbingnya
    # dibekukan hanya sekali saat status_kelulusan pertama kali jadi LULUS.
    periode_id = f.get("periode_akademik_id", type=int)
    tahap_nama = f.get("tahap", "")
    tahap_pengajuan_id = None
    if periode_id and tahap_nama:
        trow = conn.execute(
            "SELECT id FROM tahap_pengajuan WHERE periode_akademik_id=? AND nama=?",
            (periode_id, tahap_nama),
        ).fetchone()
        tahap_pengajuan_id = trow["id"] if trow else None

    tarif_penguji_snapshot = None
    tarif_pemb1_snapshot = None
    tarif_pemb2_snapshot = None
    if sid:
        existing = conn.execute(
            "SELECT tarif_penguji_diterapkan, tarif_pemb1_diterapkan, tarif_pemb2_diterapkan "
            "FROM sidang WHERE id=?",
            (sid,),
        ).fetchone()
        if existing:
            tarif_penguji_snapshot = existing["tarif_penguji_diterapkan"]
            tarif_pemb1_snapshot = existing["tarif_pemb1_diterapkan"]
            tarif_pemb2_snapshot = existing["tarif_pemb2_diterapkan"]
    if not tarif_penguji_snapshot:
        tarif_penguji_snapshot = float(_db.get_setting(conn, "tarif_honor_penguji_sidang", "30000"))
    if status_kelulusan == "LULUS":
        if not tarif_pemb1_snapshot:
            tarif_pemb1_snapshot = float(_db.get_setting(conn, "tarif_honor_pembimbing_1", "300000"))
        if not tarif_pemb2_snapshot:
            tarif_pemb2_snapshot = float(_db.get_setting(conn, "tarif_honor_pembimbing_2", "200000"))

    data = (
        mid,
        tgl,
        jam,
        f.get("judul_sidang", ""),
        f.get("ada_perubahan", "Tidak"),
        f.get("keterangan_perubahan", ""),
        gid("ketua_id"),
        gid("sekretaris_id"),
        gid("anggota1_id"),
        gid("anggota2_id"),
        gid("anggota3_id"),
        nilai,
        status_kelulusan,
        ruangan_id,
        periode_id,
        tahap_pengajuan_id,
        tahap_nama,
        tarif_penguji_snapshot,
        tarif_pemb1_snapshot,
        tarif_pemb2_snapshot,
    )
    if sid:
        # Audit Phase 4 — ambil nilai LAMA sebelum ditimpa UPDATE, supaya
        # bisa dicatat sebagai audit event "status_kelulusan: X -> Y"
        # persis seperti contoh di dokumen audit (Sidang #128 dst).
        sebelum = conn.execute(
            "SELECT status_kelulusan FROM sidang WHERE id=?", (sid,)
        ).fetchone()
        status_lama = sebelum["status_kelulusan"] if sebelum else None
        try:
            conn.execute(
                "UPDATE sidang SET mahasiswa_id=?,tgl_sidang=?,jam_sidang=?,judul_sidang=?,"
                "ada_perubahan=?,keterangan_perubahan=?,ketua_id=?,sekretaris_id=?,anggota1_id=?,"
                "anggota2_id=?,anggota3_id=?,nilai_angka=?,status_kelulusan=?,ruangan_id=?,"
                "periode_akademik_id=?,tahap_pengajuan_id=?,tahap=?,tarif_penguji_diterapkan=?,"
                "tarif_pemb1_diterapkan=?,tarif_pemb2_diterapkan=? WHERE id=?",
                data + (sid,),
            )
        except Exception as e:
            # Audit Phase 1-2 (re-check) — sebelum perbaikan ini, INSERT/UPDATE
            # sidang TIDAK dibungkus try/except sama sekali (beda dari
            # seminar_simpan/pengajuan_simpan/penetapan_simpan di modul lain
            # yang sudah lebih dulu memakai EH.flash_gagal_simpan). Sejak
            # Phase 1 menambahkan FK RESTRICT ketua_id/sekretaris_id/anggota*_id
            # ke dosen dan Phase 2 menambahkan CHECK ke status_kelulusan,
            # celah ini jadi lebih nyata: dosen penguji yang ID-nya sudah
            # tidak valid (jarang, tapi mis. lewat request yang di-tamper)
            # akan membuat rute ini crash 500 mentah, bukan pesan ramah.
            EH.flash_gagal_simpan(e, "Gagal menyimpan data sidang")
            return redirect(url_for("pelaksanaan.sidang_list"))
        if status_lama != status_kelulusan:
            _db.log(
                conn, "Update Sidang", str(mid),
                modul="Pelaksanaan", entitas="Sidang", entitas_id=sid,
                nilai_lama=status_lama, nilai_baru=status_kelulusan,
            )
        else:
            _db.log(conn, "Update Sidang", str(mid), modul="Pelaksanaan", entitas="Sidang", entitas_id=sid)
        flash("Data sidang diperbarui.", "ok")
    else:
        try:
            cur = conn.execute(
                "INSERT INTO sidang(mahasiswa_id,tgl_sidang,jam_sidang,judul_sidang,ada_perubahan,"
                "keterangan_perubahan,ketua_id,sekretaris_id,anggota1_id,anggota2_id,anggota3_id,"
                "nilai_angka,status_kelulusan,ruangan_id,periode_akademik_id,tahap_pengajuan_id,tahap,"
                "tarif_penguji_diterapkan,tarif_pemb1_diterapkan,tarif_pemb2_diterapkan) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                data,
            )
        except Exception as e:
            EH.flash_gagal_simpan(e, "Gagal menyimpan data sidang")
            return redirect(url_for("pelaksanaan.sidang_list"))
        _db.log(
            conn, "Tambah Sidang", str(mid),
            modul="Pelaksanaan", entitas="Sidang", entitas_id=cur.lastrowid,
            nilai_lama=None, nilai_baru=status_kelulusan,
        )
        flash(
            "Data sidang disimpan. Mahasiswa boleh punya lebih dari 1 baris sidang (sidang ulang).",
            "ok",
        )
    conn.commit()
    # Audit P0 #1 — diganti dari _sync_status_ta_sidang() (buggy: default ke
    # STATUS_TA_SUDAH_SIDANG saat tidak ada baris sidang sama sekali) ke
    # logic.recalculate_status_ta() yang mundur dengan benar ke status
    # pra-sidang bila perlu.
    L.recalculate_status_ta(
        conn, mid, dipicu_oleh=f"Sidang disimpan (status kelulusan: {status_kelulusan})"
    )
    return redirect(url_for("pelaksanaan.sidang_list"))


@bp.route("/sidang/<int:sid>/hapus", methods=["POST"])
def sidang_hapus(sid):
    conn = current_app.get_db()
    row = conn.execute("SELECT mahasiswa_id FROM sidang WHERE id=?", (sid,)).fetchone()
    if not row:
        flash("Data sidang tidak ditemukan.", "error")
        return redirect(url_for("pelaksanaan.sidang_list"))

    # Audit P0 #4-#7 (efek samping yang harus ditangani di sini) — sejak
    # yudisium.sidang_id sekarang ber-FK ON DELETE RESTRICT ke sidang(id),
    # menghapus baris sidang yang sudah dipakai logic.sync_yudisium_dari_
    # sidang() untuk membuat baris di tabel yudisium akan ditolak SQLite.
    # Itu memang perilaku yang benar (dulu operasi ini "berhasil" tapi
    # meninggalkan yudisium.sidang_id yatim — persis bug referential
    # integrity yang diperbaiki), tapi kalau tidak dicegat di sini
    # operator akan melihat error 500 mentah, bukan pesan yang jelas.
    # Mengikuti pola guard hapus_mk() di routes/kurikulum.py.
    dipakai_yudisium = conn.execute(
        "SELECT id FROM yudisium WHERE sidang_id=?", (sid,)
    ).fetchone()
    if dipakai_yudisium:
        flash(
            "Data sidang ini tidak bisa dihapus — mahasiswa sudah lulus sidang dan sudah "
            "tercatat di Rencana Yudisium. Kalau memang ada kesalahan input, perbaiki nilai/"
            "status kelulusan lewat tombol Ubah di baris sidang ini, jangan dihapus.",
            "error",
        )
        return redirect(url_for("pelaksanaan.sidang_list"))

    conn.execute("DELETE FROM sidang WHERE id=?", (sid,))
    conn.commit()
    # Audit P0 #1 — INI adalah skenario persis yang menimbulkan bug:
    # menghapus satu-satunya baris sidang seorang mahasiswa. Fungsi
    # lama menyetel status_ta jadi "Sudah Sidang" (salah); fungsi baru
    # menghitung ulang dari histori pengajuan/pembimbing/seminar yang
    # tersisa (mis. mundur ke "Proses Bimbingan").
    L.recalculate_status_ta(conn, row["mahasiswa_id"], dipicu_oleh="Sidang dihapus")
    flash("Data sidang dihapus.", "ok")
    return redirect(url_for("pelaksanaan.sidang_list"))
