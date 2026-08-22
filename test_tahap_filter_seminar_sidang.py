import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402
from app import db as _db  # noqa: E402
from app import logic as L  # noqa: E402

db_path = os.path.join(tmpdir, "test.db")
app = create_app(db_path=db_path)
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False

client = app.test_client()
client.get("/login")
client.post("/login", data={"username": "kaprodi", "password1": "test1234", "password2": "test1234"}, follow_redirects=True)

with app.test_request_context():
    conn = app.get_db()
    ta_id, periode_ids = _db.buka_tahun_ajaran(conn, "2025/2026", aktifkan="Ganjil")
    periode_id = periode_ids["Ganjil"]
    conn.execute(
        "INSERT INTO tahap_pengajuan(periode_akademik_id, urutan, nama) VALUES(?,1,?)",
        (periode_id, "Tahap 1 2025/2026"),
    )
    conn.execute(
        "INSERT INTO tahap_pengajuan(periode_akademik_id, urutan, nama) VALUES(?,2,?)",
        (periode_id, "Tahap 2 2025/2026"),
    )
    conn.commit()
    tahap1_id = conn.execute("SELECT id FROM tahap_pengajuan WHERE nama='Tahap 1 2025/2026'").fetchone()["id"]
    tahap2_id = conn.execute("SELECT id FROM tahap_pengajuan WHERE nama='Tahap 2 2025/2026'").fetchone()["id"]

    conn.execute("INSERT INTO dosen(nama, aktif) VALUES('Dr. Andi', 1)")
    conn.execute("INSERT INTO dosen(nama, aktif) VALUES('Dr. Budi', 1)")
    dosen_a = conn.execute("SELECT id FROM dosen WHERE nama='Dr. Andi'").fetchone()["id"]
    dosen_b = conn.execute("SELECT id FROM dosen WHERE nama='Dr. Budi'").fetchone()["id"]

    for nim, nama in [("001", "Mhs Satu"), ("002", "Mhs Dua")]:
        conn.execute("INSERT INTO mahasiswa(nim, nama) VALUES(?,?)", (nim, nama))
    m1 = conn.execute("SELECT id FROM mahasiswa WHERE nim='001'").fetchone()["id"]
    m2 = conn.execute("SELECT id FROM mahasiswa WHERE nim='002'").fetchone()["id"]

    # Kedua mahasiswa punya SK Pembimbing di TAHAP 1 (sengaja SAMA), tapi
    # nanti seminar mereka akan didaftarkan di TAHAP BERBEDA — inilah kasus
    # yang sebelumnya bikin rekap honor salah kelompok kalau masih pakai
    # pp.tahap.
    for mid in (m1, m2):
        conn.execute(
            "INSERT INTO penetapan_pembimbing(mahasiswa_id, tahap, pembimbing1_id) VALUES(?,?,?)",
            (mid, "Tahap 1 2025/2026", dosen_a),
        )
    conn.execute("INSERT INTO pengaturan(key, value) VALUES('tarif_honor_seminar','20000') "
                 "ON CONFLICT(key) DO UPDATE SET value='20000'")
    conn.commit()

print("=== Simpan seminar mhs-1 di TAHAP 1, status Selesai ===")
r = client.post(
    "/pelaksanaan/seminar/simpan",
    data={
        "mahasiswa_id": str(m1),
        "periode_akademik_id": str(periode_id),
        "tahap": "Tahap 1 2025/2026",
        "status": "Selesai",
        "penguji_ketua_id": str(dosen_a),
    },
    follow_redirects=True,
)
print("status:", r.status_code)

print("=== Simpan seminar mhs-2 di TAHAP 2 (beda dari tahap SK-nya), status Selesai ===")
r = client.post(
    "/pelaksanaan/seminar/simpan",
    data={
        "mahasiswa_id": str(m2),
        "periode_akademik_id": str(periode_id),
        "tahap": "Tahap 2 2025/2026",
        "status": "Selesai",
        "penguji_ketua_id": str(dosen_b),
    },
    follow_redirects=True,
)
print("status:", r.status_code)

with app.test_request_context():
    conn = app.get_db()
    seminar_rows = conn.execute("SELECT mahasiswa_id, tahap, tarif_honor_diterapkan FROM seminar").fetchall()
    for r in seminar_rows:
        print("seminar row:", dict(r))

    # --- Tes 1: filter tahap halaman list ---
    honor_t1 = L.rkp_seminar(conn, "Tahap 1 2025/2026")
    honor_t2 = L.rkp_seminar(conn, "Tahap 2 2025/2026")
    print("Honor seminar Tahap 1 (harus cuma Dr. Andi):", honor_t1)
    print("Honor seminar Tahap 2 (harus cuma Dr. Budi):", honor_t2)
    assert len(honor_t1) == 1 and honor_t1[0]["nama"] == "Dr. Andi", "GAGAL: filter tahap 1 salah"
    assert len(honor_t2) == 1 and honor_t2[0]["nama"] == "Dr. Budi", "GAGAL: filter tahap 2 salah"
    print("LULUS Tes 1: rkp_seminar mengelompokkan berdasarkan tahap SEMINAR (bukan tahap SK Pembimbing).")

# --- Tes 2: halaman list terfilter tab tahap ---
def _tbody(html):
    return html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]

r1 = client.get("/pelaksanaan/seminar?tahap=Tahap+1+2025%2F2026")
tbody1 = _tbody(r1.get_data(as_text=True))
r2 = client.get("/pelaksanaan/seminar?tahap=Tahap+2+2025%2F2026")
tbody2 = _tbody(r2.get_data(as_text=True))
print("Tabel Tahap 1 -> NIM 001 muncul:", "001" in tbody1, " | NIM 002 muncul:", "002" in tbody1)
print("Tabel Tahap 2 -> NIM 002 muncul:", "002" in tbody2, " | NIM 001 muncul:", "001" in tbody2)
assert "001" in tbody1 and "002" not in tbody1, "GAGAL: tab filter Tahap 1 salah"
assert "002" in tbody2 and "001" not in tbody2, "GAGAL: tab filter Tahap 2 salah"
print("LULUS Tes 2: tab filter tahap di /pelaksanaan/seminar bekerja (tabel, bukan dropdown mahasiswa).")

# --- Tes 3: rekap honor keuangan gabungan ---
with app.test_request_context():
    conn = app.get_db()
    rows, total = L.rekap_honor_keuangan(conn)
    print("Rekap Honor Keuangan (semua tahap):", rows)
    assert total == 40000, f"GAGAL: total honor keuangan harus 40000, dapat {total}"
    print("LULUS Tes 3: rekap_honor_keuangan menjumlahkan honor lintas kategori dengan benar.")

print("\nSEMUA TES SEMINAR LULUS.\n")

# =====================================================================
# BAGIAN 2 — SIDANG: honor penguji (semua baris) + honor pembimbing
# (hanya LULUS), dan skenario tahap SK Pembimbing beda dari tahap Sidang.
# =====================================================================
with app.test_request_context():
    conn = app.get_db()
    conn.execute("INSERT INTO dosen(nama, aktif) VALUES('Dr. Citra', 1)")  # pembimbing2
    conn.commit()
    dosen_c = conn.execute("SELECT id FROM dosen WHERE nama='Dr. Citra'").fetchone()["id"]
    conn.execute(
        "UPDATE penetapan_pembimbing SET pembimbing2_id=? WHERE mahasiswa_id IN (?,?)",
        (dosen_c, m1, m2),
    )
    conn.commit()

print("=== Simpan sidang mhs-1 di TAHAP 1, LULUS (pembimbing 1=Andi, pembimbing2=Citra) ===")
r = client.post(
    "/pelaksanaan/sidang/simpan",
    data={
        "mahasiswa_id": str(m1),
        "periode_akademik_id": str(periode_id),
        "tahap": "Tahap 1 2025/2026",
        "ketua_id": str(dosen_b),
        "status_kelulusan": "LULUS",
    },
    follow_redirects=True,
)
print("status:", r.status_code)

print("=== Simpan sidang mhs-2 di TAHAP 2 (beda dari tahap SK-nya), TIDAK LULUS ===")
r = client.post(
    "/pelaksanaan/sidang/simpan",
    data={
        "mahasiswa_id": str(m2),
        "periode_akademik_id": str(periode_id),
        "tahap": "Tahap 2 2025/2026",
        "ketua_id": str(dosen_a),
        "status_kelulusan": "TIDAK LULUS",
    },
    follow_redirects=True,
)
print("status:", r.status_code)

with app.test_request_context():
    conn = app.get_db()
    for r in conn.execute(
        "SELECT mahasiswa_id, tahap, status_kelulusan, tarif_penguji_diterapkan, "
        "tarif_pemb1_diterapkan, tarif_pemb2_diterapkan FROM sidang"
    ).fetchall():
        print("sidang row:", dict(r))

    d1 = L.rkp_sidang(conn, "Tahap 1 2025/2026")
    d2 = L.rkp_sidang(conn, "Tahap 2 2025/2026")
    print("RKP Sidang Tahap 1:", d1)
    print("RKP Sidang Tahap 2:", d2)

    # Bagian 1 (penguji): baris tahap 1 -> ketua Dr. Budi; tahap 2 -> ketua Dr. Andi.
    assert len(d1["bagian1"]) == 1 and d1["bagian1"][0]["nama"] == "Dr. Budi", "GAGAL: penguji tahap 1 salah"
    assert len(d2["bagian1"]) == 1 and d2["bagian1"][0]["nama"] == "Dr. Andi", "GAGAL: penguji tahap 2 salah"
    print("LULUS Tes 4: honor penguji sidang dikelompokkan per TAHAP SIDANG (bukan tahap SK Pembimbing).")

    # Bagian 2 (pembimbing): HANYA muncul untuk sidang yg LULUS -> hanya tahap 1
    # (mhs-1, pembimbing1=Andi & pembimbing2=Citra -> 2 baris beda dosen).
    # Mhs-2 TIDAK LULUS jadi tidak menghasilkan honor pembimbing sama sekali,
    # meski tahap 2 di-filter.
    assert len(d1["bagian2"]) == 2, "GAGAL: honor pembimbing tahap 1 (LULUS) harus muncul utk 2 dosen"
    nama_pemb = {r["nama"] for r in d1["bagian2"]}
    assert nama_pemb == {"Dr. Andi", "Dr. Citra"}
    assert len(d2["bagian2"]) == 0, "GAGAL: mhs TIDAK LULUS tidak boleh menghasilkan honor pembimbing"
    print("LULUS Tes 5: honor pembimbing HANYA cair untuk mahasiswa berstatus LULUS.")

# --- Tes 6: tab filter tahap juga bekerja di /pelaksanaan/sidang ---
def _tbody(html):
    return html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]

rs1 = client.get("/pelaksanaan/sidang?tahap=Tahap+1+2025%2F2026")
tb1 = _tbody(rs1.get_data(as_text=True))
rs2 = client.get("/pelaksanaan/sidang?tahap=Tahap+2+2025%2F2026")
tb2 = _tbody(rs2.get_data(as_text=True))
assert "001" in tb1 and "002" not in tb1, "GAGAL: tab filter sidang Tahap 1 salah"
assert "002" in tb2 and "001" not in tb2, "GAGAL: tab filter sidang Tahap 2 salah"
print("LULUS Tes 6: tab filter tahap di /pelaksanaan/sidang bekerja.")

# --- Tes 7: rekap_honor_keuangan gabungan (Seminar+Sidang penguji+pembimbing) ---
with app.test_request_context():
    conn = app.get_db()
    rows, total = L.rekap_honor_keuangan(conn)
    print("Rekap Honor Keuangan gabungan (semua tahap):")
    for r in rows:
        print(" -", r)
    print("Total:", total)
    # 2 seminar (20rb x2=40rb) + 2 sidang penguji (30rb x2=60rb) + 1 pembimbing1 (300rb) + 1 pembimbing2 (200rb)
    expected = 20000 * 2 + 30000 * 2 + 300000 + 200000
    assert total == expected, f"GAGAL: total gabungan harus {expected}, dapat {total}"
    kategori_set = {r["kategori"] for r in rows}
    assert kategori_set == {
        "Seminar - Penguji",
        "Sidang - Penguji",
        "Sidang - Pembimbing 1",
        "Sidang - Pembimbing 2",
    }, f"GAGAL: kategori tidak lengkap: {kategori_set}"
    print("LULUS Tes 7: rekap_honor_keuangan menggabungkan 4 kategori honor dengan benar.")

# --- Tes 8: halaman Rekap Honor Keuangan & Pengaturan Tarif Honor render OK ---
rh = client.get("/rekap/honor-keuangan")
print("GET /rekap/honor-keuangan ->", rh.status_code)
assert rh.status_code == 200
body_rh = rh.get_data(as_text=True)
for nm in ["Dr. Andi", "Dr. Budi", "Sidang - Pembimbing 1", "Sidang - Pembimbing 2", "Grand Total"]:
    assert nm in body_rh, f"GAGAL: '{nm}' tidak muncul di halaman Rekap Honor Keuangan"
print("LULUS Tes 8a: halaman /rekap/honor-keuangan render lengkap.")

rp = client.get("/pengaturan/honor")
print("GET /pengaturan/honor ->", rp.status_code)
assert rp.status_code == 200
assert "Tarif Honor" in rp.get_data(as_text=True)
print("LULUS Tes 8b: halaman /pengaturan/honor render OK.")

# --- Tes 9: ubah tarif honor lewat UI, pastikan honor BARU pakai tarif baru
# tapi honor LAMA (sudah dibekukan/snapshot) TIDAK berubah retroaktif. ---
client.post(
    "/pengaturan/honor",
    data={
        "tarif_honor_seminar": "99000",
        "tarif_honor_penguji_sidang": "30000",
        "tarif_honor_pembimbing_1": "300000",
        "tarif_honor_pembimbing_2": "200000",
    },
    follow_redirects=True,
)
with app.test_request_context():
    conn = app.get_db()
    honor_lama = L.rkp_seminar(conn, "Tahap 1 2025/2026")
    assert honor_lama[0]["honor"] == 20000.0, "GAGAL: honor lama berubah retroaktif setelah tarif diubah!"
    print("LULUS Tes 9: honor Tahap 1 yang sudah 'Selesai' TETAP Rp20.000 walau tarif diubah jadi Rp99.000.")

print("\nSEMUA TES (SEMINAR + SIDANG + REKAP HONOR KEUANGAN + TARIF) LULUS.")

