# -*- coding: utf-8 -*-
"""routes/dosen.py — CRUD Data Dosen."""

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

bp = Blueprint("dosen", __name__, url_prefix="/dosen")


@bp.route("/", methods=["GET"])
def list_view():
    conn = current_app.get_db()
    q = request.args.get("q", "").strip()
    homebase_filter = request.args.get("homebase", "").strip()
    sql = "SELECT * FROM dosen WHERE 1=1"
    params = []
    if q:
        sql += " AND (nama LIKE ? OR nidn LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if homebase_filter:
        sql += " AND status_homebase=?"
        params.append(homebase_filter)
    sql += " ORDER BY nama"
    rows = conn.execute(sql, params).fetchall()
    edit_id = request.args.get("edit", type=int)
    edit_row = None
    if edit_id:
        edit_row = conn.execute("SELECT * FROM dosen WHERE id=?", (edit_id,)).fetchone()
    return render_template(
        "dosen.html",
        rows=rows,
        q=q,
        edit_row=edit_row,
        homebase_filter=homebase_filter,
        STATUS_HOMEBASE_LIST=C.STATUS_HOMEBASE_LIST,
        STATUS_KEPEGAWAIAN_DOSEN_LIST=C.STATUS_KEPEGAWAIAN_DOSEN_LIST,
    )


@bp.route("/simpan", methods=["POST"])
def simpan():
    conn = current_app.get_db()
    f = request.form
    did = f.get("id", type=int)
    nama = f.get("nama", "").strip()
    if not nama:
        flash("Nama dosen wajib diisi.", "error")
        return redirect(url_for("dosen.list_view"))
    status_homebase = f.get("status_homebase", "Homebase") or "Homebase"
    if status_homebase not in C.STATUS_HOMEBASE_LIST:
        status_homebase = "Homebase"

    # Struktur data SISTER (PDDIKTI) — NIK & NUPTK masing-masing 16 digit;
    # dicek lunak (peringatan, bukan blokir) karena data lapangan kadang
    # belum lengkap/masih dalam proses pengurusan NUPTK, jadi operator
    # tetap harus bisa menyimpan data dosen tanpa NUPTK dulu.
    nik = f.get("nik", "").strip()
    nuptk = f.get("nuptk", "").strip()
    peringatan = []
    if nik and (not nik.isdigit() or len(nik) != 16):
        peringatan.append("NIK biasanya 16 digit angka — mohon dicek kembali.")
    if nuptk and (not nuptk.isdigit() or len(nuptk) != 16):
        peringatan.append("NUPTK biasanya 16 digit angka — mohon dicek kembali.")

    try:
        # Audit Phase 5 — status_kepegawaian (Aktif/Nonaktif/Pindah/Pensiun)
        # sekarang SATU-SATUNYA sumber kebenaran siklus hidup dosen; `aktif`
        # (boolean lama, dipakai di ~19 query `WHERE aktif=1` di seluruh
        # aplikasi utk dropdown pemilihan dosen) DITURUNKAN otomatis dari
        # sini, bukan lagi field independen yang bisa tidak sinkron.
        status_kepegawaian = f.get("status_kepegawaian", "Aktif")
        if status_kepegawaian not in C.STATUS_KEPEGAWAIAN_DOSEN_LIST:
            status_kepegawaian = "Aktif"
        aktif_baru = 1 if status_kepegawaian == "Aktif" else 0
        if did:
            # Audit Phase 4 — nilai lama status kepegawaian, utk audit
            # event kalau berubah. Nonaktifkan/Pindah/Pensiun dosen adalah
            # pengganti hard-delete sejak guard Phase 1 (P0 #9), jadi
            # perubahan ini cukup penting utk direkam siapa & kapan.
            sebelum = conn.execute(
                "SELECT status_kepegawaian FROM dosen WHERE id=?", (did,)
            ).fetchone()
            status_lama = sebelum["status_kepegawaian"] if sebelum else None
            conn.execute(
                "UPDATE dosen SET nidn=?, nama=?, no_hp=?, email=?, aktif=?, status_kepegawaian=?, "
                "nik=?, nuptk=?, jabatan_fungsional=?, pendidikan_terakhir=?, bidang_keahlian=?, "
                "status_homebase=?, unit_asal=?, prodi_homebase=?, sk_penugasan=? WHERE id=?",
                (
                    f.get("nidn", ""),
                    nama,
                    f.get("no_hp", ""),
                    f.get("email", ""),
                    aktif_baru,
                    status_kepegawaian,
                    nik,
                    nuptk,
                    f.get("jabatan_fungsional", ""),
                    f.get("pendidikan_terakhir", ""),
                    f.get("bidang_keahlian", ""),
                    status_homebase,
                    f.get("unit_asal", ""),
                    f.get("prodi_homebase", ""),
                    f.get("sk_penugasan", ""),
                    did,
                ),
            )
            if status_lama != status_kepegawaian:
                _db.log(
                    conn, "Update Dosen", nama,
                    modul="SDM", entitas="Dosen", entitas_id=did,
                    nilai_lama=status_lama, nilai_baru=status_kepegawaian,
                )
            else:
                _db.log(conn, "Update Dosen", nama, modul="SDM", entitas="Dosen", entitas_id=did)
            flash("Data dosen diperbarui.", "ok")
        else:
            conn.execute(
                "INSERT INTO dosen(nidn,nama,no_hp,email,aktif,status_kepegawaian,nik,nuptk,"
                "jabatan_fungsional,pendidikan_terakhir,bidang_keahlian,status_homebase,unit_asal,"
                "prodi_homebase,sk_penugasan) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f.get("nidn", ""),
                    nama,
                    f.get("no_hp", ""),
                    f.get("email", ""),
                    aktif_baru,
                    status_kepegawaian,
                    nik,
                    nuptk,
                    f.get("jabatan_fungsional", ""),
                    f.get("pendidikan_terakhir", ""),
                    f.get("bidang_keahlian", ""),
                    status_homebase,
                    f.get("unit_asal", ""),
                    f.get("prodi_homebase", ""),
                    f.get("sk_penugasan", ""),
                ),
            )
            _db.log(conn, "Tambah Dosen", nama, modul="SDM", entitas="Dosen")
            flash(f"Dosen {nama} ditambahkan.", "ok")
        conn.commit()
        for p in peringatan:
            flash(p, "error")
    except Exception as e:
        EH.flash_gagal_simpan(e, "Gagal menyimpan")
    return redirect(url_for("dosen.list_view"))


@bp.route("/<int:did>/hapus", methods=["POST"])
def hapus(did):
    conn = current_app.get_db()
    row = conn.execute("SELECT nama FROM dosen WHERE id=?", (did,)).fetchone()
    if not row:
        flash("Data dosen tidak ditemukan.", "error")
        return redirect(url_for("dosen.list_view"))

    # Audit P0 #9 — pasangan guard hapus mahasiswa di atas. `dosen(id)`
    # dirujuk oleh BANYAK tabel (jadwal mengajar, pembimbing/penguji TA,
    # kinerja tridharma, kemitraan, akreditasi, AMI) yang TIDAK satu pun
    # punya FOREIGN KEY eksplisit ke dosen (lihat Audit §5) — jadi sebelum
    # perbaikan ini, `DELETE FROM dosen` tidak akan gagal walau dosennya
    # masih dirujuk di mana-mana; ia hanya meninggalkan ID yatim yang bikin
    # nama dosen hilang senyap dari jadwal/rekap/SK yang sudah terbit.
    # Dosen sudah punya kolom `aktif` (dipakai di seluruh dropdown pemilihan
    # dosen lewat `WHERE aktif=1`) — itulah cara yang benar utk "menghapus"
    # dosen dari pemakaian baru tanpa merusak histori lama.
    pemakaian = {
        "Jadwal Mengajar": "SELECT COUNT(*) n FROM jadwal_kelas WHERE dosen_id=?",
        "Kelas Semester Pendek": "SELECT COUNT(*) n FROM sp_kelas WHERE dosen_id=?",
        "Penguji/Pembimbing Seminar": (
            "SELECT COUNT(*) n FROM seminar WHERE penguji_ketua_id=? OR "
            "penguji_anggota1_id=? OR penguji_anggota2_id=?"
        ),
        "Penguji/Pembimbing Sidang": (
            "SELECT COUNT(*) n FROM sidang WHERE ketua_id=? OR sekretaris_id=? OR "
            "anggota1_id=? OR anggota2_id=? OR anggota3_id=?"
        ),
        "SK Penetapan Pembimbing/Penguji": (
            "SELECT COUNT(*) n FROM penetapan_pembimbing WHERE pembimbing1_id=? OR "
            "pembimbing2_id=? OR pembahas1_id=? OR pembahas2_id=? OR pembahas3_id=? OR "
            "ketua_sidang_id=? OR penguji1_id=? OR penguji2_id=? OR penguji3_id=? OR penguji4_id=?"
        ),
        "Kinerja Tridharma (Pendidikan/Penelitian/PKM/Penunjang)": (
            "SELECT (SELECT COUNT(*) FROM aktivitas_pendidikan WHERE dosen_id=?) + "
            "(SELECT COUNT(*) FROM aktivitas_penelitian WHERE dosen_id=?) + "
            "(SELECT COUNT(*) FROM aktivitas_pkm WHERE dosen_id=?) + "
            "(SELECT COUNT(*) FROM aktivitas_penunjang WHERE dosen_id=?) n"
        ),
        "Luaran & Peran Akademik Dosen": (
            "SELECT (SELECT COUNT(*) FROM luaran_dosen WHERE dosen_id=?) + "
            "(SELECT COUNT(*) FROM peran_akademik_dosen WHERE dosen_id=?) n"
        ),
        "Histori Karier & Target Kinerja": (
            "SELECT (SELECT COUNT(*) FROM timeline_karier_dosen WHERE dosen_id=?) + "
            "(SELECT COUNT(*) FROM target_kinerja_dosen WHERE dosen_id=?) n"
        ),
        "Program/Kegiatan Kerja Sama": (
            "SELECT COUNT(*) n FROM mitra_program WHERE pic_dosen_id=?"
        ),
        "Akreditasi & AMI": (
            "SELECT (SELECT COUNT(*) FROM akreditasi_kriteria WHERE pic_dosen_id=?) + "
            "(SELECT COUNT(*) FROM ami_temuan WHERE pic_dosen_id=?) n"
        ),
    }
    rincian = []
    for label, sql in pemakaian.items():
        jumlah_placeholder = sql.count("?")
        n = conn.execute(sql, (did,) * jumlah_placeholder).fetchone()["n"] or 0
        if n:
            rincian.append(f"{label} ({n})")
    if rincian:
        flash(
            f'Dosen "{row["nama"]}" tidak bisa dihapus permanen — masih dirujuk di: '
            + ", ".join(rincian) +
            ". Menghapusnya akan meninggalkan data rujukan yatim (nama dosen hilang dari "
            'jadwal/SK/rekap yang sudah ada). Gunakan centang "Aktif" di form Ubah Data untuk '
            "menonaktifkan dosen ini dari pemilihan baru tanpa kehilangan histori lama.",
            "error",
        )
        return redirect(url_for("dosen.list_view"))

    conn.execute("DELETE FROM dosen WHERE id=?", (did,))
    conn.commit()
    _db.log(conn, "Hapus Dosen", row["nama"], modul="SDM", entitas="Dosen", entitas_id=did)
    flash("Data dosen dihapus.", "ok")
    return redirect(url_for("dosen.list_view"))
