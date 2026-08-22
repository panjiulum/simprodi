import os, sys, tempfile, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp()
os.environ["HOME"] = tmpdir

from app import create_app  # noqa: E402

db_path = os.path.join(tmpdir, "test.db")
app = create_app(db_path=db_path)
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False  # skrip tes tidak mengirim token CSRF
client = app.test_client()

FAILS = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)

client.get("/login")
client.post("/login", data={"username": "kaprodi", "password1": "test1234", "password2": "test1234"}, follow_redirects=True)
# Restrukturisasi poin 2: verifikasi PIN dulu supaya tautan sidebar yang
# digerbangi PIN (Import & Export Data) tetap bisa dites 200 langsung
# tanpa redirect, sama seperti tautan lain di pengecekan "broken link" ini.
client.post("/pengaturan/pin", data={"pin1": "246810", "pin2": "246810"}, follow_redirects=True)

html = client.get("/").data.decode()

# ---------------------------------------------------------------------
# 1. Struktur grup baru tampil dengan label & urutan yang benar
# ---------------------------------------------------------------------
groups = [name for _cls, name in re.findall(r'<div class="nav-group([^"]*)"\s+data-group="([^"]+)">', html)]
expected_groups = [
    # Audit lanjutan (redesain sidebar): label grup tak lagi diawali emoji —
    # tiap grup kini punya ikon SVG garis terpisah (lihat _icons.html) yang
    # dirender sebagai elemen <svg> sendiri sebelum label, bukan lagi bagian
    # dari teks label itu sendiri.
    "Utama", "Akademik", "Mahasiswa", "Tugas Akhir", "SDM",
    "Tri Dharma", "Kerja Sama", "Mutu &amp; Analytics", "Operasional",
    "Administrasi", "Pengaturan",
]
check(f"11 grup sidebar tampil sesuai urutan baru (didapat {len(groups)})", groups == expected_groups)

# ---------------------------------------------------------------------
# 2. Semua tautan sidebar merespons 200 (termasuk placeholder roadmap)
# ---------------------------------------------------------------------
hrefs = re.findall(r'class="nav-item[^"]*"\s+href="([^"]+)"', html)
# Audit poin 5 & 6 (lanjutan): "Tentang Aplikasi" sekarang modul nyata juga
# (bukan lagi placeholder roadmap, menyusul "Backup & Restore" sebelumnya)
# — total tautan sidebar tidak berubah, cuma placeholder roadmap -1.
# Audit lanjutan (fix menu "Kerja Sama" tidak expand): grup ini sebelumnya
# cuma 1 tautan generik ke kerjasama.index, padahal halamannya sendiri
# sudah punya 4 tab (Dashboard/Mitra & Dokumen/Program & Implementasi/
# Evaluasi & Luaran) — dipecah jadi 4 tautan persis pola Tri Dharma,
# net +3 tautan (51 -> 54).
# Audit Modul Pelaksanaan (Seminar/Sidang) — ditambahkan 2 tautan baru:
# "Rekap Honor Keuangan" (grup Operasional) & "Tarif Honor" (grup
# Administrasi), net +2 tautan (54 -> 56).
# Fase Pejabat Struktural — ditambahkan 1 tautan baru: "Pejabat Struktural"
# (grup Administrasi), net +1 tautan (56 -> 57).
# Restrukturisasi poin 2 — ditambahkan 1 tautan baru: "PIN Fitur Krusial"
# (grup Pengaturan, mendampingi "Ubah Username & Password"), net +1
# tautan (57 -> 58).
check("58 tautan total di sidebar (setelah tambah PIN Fitur Krusial, 57+1)", len(hrefs) == 58)

fails = []
roadmap_links = []
for h in hrefs:
    r = client.get(h)
    if r.status_code != 200:
        fails.append((h, r.status_code))
    if "/segera/" in h:
        roadmap_links.append(h)
check("Seluruh tautan sidebar merespons HTTP 200", not fails)
check("0 placeholder roadmap tersisa (Preferensi/Notifikasi/Tema kini modul nyata — Audit Lanjutan 3)", len(roadmap_links) == 0)

# ---------------------------------------------------------------------
# 3. Tidak ada fitur yang hilang — endpoint lama tetap semua ada di
#    daftar tautan baru (hanya dikelompokkan ulang, bukan dihapus)
# ---------------------------------------------------------------------
endpoint_paths_required = [
    "/kurikulum/", "/jadwal/", "/nilai/", "/cqi/", "/mahasiswa/", "/kalender/",
    "/akademik/pengajuan", "/akademik/penetapan", "/pelaksanaan/seminar",
    "/pelaksanaan/sidang", "/kelulusan/yudisium", "/kelulusan/wisuda",
    "/kelulusan/tracer", "/semester-pendek/", "/rpl/", "/dosen/", "/sdm/",
    "/ruangan/", "/tridharma/", "/kerjasama/", "/mutu/", "/rekap/pembimbing",
    "/rekap/status", "/rekap/rasio-dosen", "/rekap/statistik", "/kegiatan/",
    "/dokumen/", "/rekap/rkp-seminar", "/rekap/rkp-sidang", "/surat/",
    "/surat-umum/", "/pengaturan/pengguna", "/pengaturan/tahun-akademik",
    "/pengaturan/branding", "/pengaturan/import-export", "/pengaturan/password",
    "/panduan/", "/preferensi/", "/notifikasi/", "/tema/",
]
gabungan_href = " ".join(hrefs)
hilang = [p for p in endpoint_paths_required if p not in gabungan_href]
check(f"Tidak ada endpoint modul lama yang hilang dari sidebar (hilang: {hilang})", not hilang)

# ---------------------------------------------------------------------
# 4. Highlight menu aktif presisi untuk endpoint yang dipakai berulang
#    (tridharma.index & mutu.index dipakai oleh beberapa entri menu)
# ---------------------------------------------------------------------
html_pkm = client.get("/tridharma/?tab=penelitian_pkm&jenis=PKM").data.decode()
active_pkm = re.findall(r'<a class="nav-item active"[^>]*href="([^"]+)"', html_pkm)
check("Highlight menu PKM presisi (hanya 1 item aktif, bukan Penelitian/Publikasi)",
      len(active_pkm) == 1 and "jenis=PKM" in active_pkm[0])

html_akred = client.get("/mutu/?tab=akreditasi").data.decode()
active_akred = re.findall(r'<a class="nav-item active"[^>]*href="([^"]+)"', html_akred)
check("Highlight menu Akreditasi presisi (bukan IKU/Audit/Log Aktivitas)",
      len(active_akred) == 1 and "tab=akreditasi" in active_akred[0])

# ---------------------------------------------------------------------
# 5. Audit Lanjutan 3 — Preferensi Tampilan, Pusat Notifikasi & Tema
#    Tampilan kini modul nyata (form yang benar-benar menyimpan &
#    memberi efek), BUKAN lagi placeholder roadmap "dalam pengembangan".
# ---------------------------------------------------------------------
r_pref = client.get("/preferensi/")
check("Modul 'Preferensi Tampilan' (kini nyata) merespons 200", r_pref.status_code == 200)
check("Preferensi Tampilan punya form yang benar-benar menyimpan (bukan placeholder)",
      b'<form method="post">' in r_pref.data)

r_tema = client.get("/tema/")
check("Modul 'Tema Tampilan' (kini nyata) merespons 200", r_tema.status_code == 200)
check("Tema Tampilan menampilkan pilihan aksen warna", b"tema-swatch" in r_tema.data)
r_tema_post = client.post("/tema/", data={"tema_warna": "emerald"}, follow_redirects=True)
check("Tema Tampilan benar-benar tersimpan & diterapkan (data-theme berubah di <html>)",
      b'data-theme="emerald"' in client.get("/").data)
client.post("/tema/", data={"tema_warna": "indigo"})  # kembalikan ke baku untuk tes berikutnya

r_notif = client.get("/notifikasi/")
check("Modul 'Pusat Notifikasi' (kini nyata) merespons 200", r_notif.status_code == 200)
check("Pusat Notifikasi mengumpulkan reminder lintas modul (bukan cuma 1 sumber)",
      b"notif-summary" in r_notif.data)

r_tentang = client.get("/tentang/")
check("Modul 'Tentang Aplikasi' (kini nyata, bukan roadmap) merespons 200",
      r_tentang.status_code == 200)
check("Tentang Aplikasi menampilkan versi aplikasi", b"Versi" in r_tentang.data)
check("Tentang Aplikasi menampilkan jumlah modul aktif (dihitung otomatis, bukan teks statis)",
      b"Modul Aktif" in r_tentang.data)

r_backup_gone = client.get("/segera/backup-restore")
check("Slug roadmap lama 'backup-restore' sudah tidak terdaftar -> 404 (sudah jadi modul nyata)",
      r_backup_gone.status_code == 404)
r_tentang_gone = client.get("/segera/tentang-aplikasi")
check("Slug roadmap lama 'tentang-aplikasi' sudah tidak terdaftar -> 404 (sudah jadi modul nyata)",
      r_tentang_gone.status_code == 404)
r_tema_gone = client.get("/segera/tema")
check("Slug roadmap lama 'tema' sudah tidak terdaftar -> 404 (sudah jadi modul nyata, Audit Lanjutan 3)",
      r_tema_gone.status_code == 404)

r_404 = client.get("/segera/slug-tidak-ada")
check("Slug roadmap yang tidak terdaftar -> 404 (bukan 200 halaman kosong)",
      r_404.status_code == 404)

# ---------------------------------------------------------------------
# 6. Log Aktivitas kini punya tautan sidebar langsung (sebelumnya cuma
#    bisa diakses lewat navigasi tab internal Modul 17)
# ---------------------------------------------------------------------
check("Tautan langsung 'Log Aktivitas' ada di sidebar (Pengaturan)",
      any("tab=log" in h and "/mutu/" in h for h in hrefs))

# ---------------------------------------------------------------------
# 7. Sidebar expand/collapse (accordion) — grup berisi >1 item dapat
#    dilipat, grup aktif (berisi halaman yang sedang dibuka) selalu
#    terbuka secara default, grup 1-item tidak diberi tombol lipat.
# ---------------------------------------------------------------------
group_blocks = re.findall(r'<div class="nav-group([^"]*)"\s+data-group="([^"]+)"', html)
check("Ada grup collapsible (>1 item) di sidebar", any("collapsible" in cls for cls, _ in group_blocks))
utama_block = [cls for cls, name in group_blocks if name == "Utama"]
check("Grup 'Utama' (1 item) tidak diberi class collapsible", utama_block and "collapsible" not in utama_block[0])

html_kurikulum = client.get("/kurikulum/").data.decode()
groups_kurikulum = re.findall(r'<div class="nav-group([^"]*)"\s+data-group="([^"]+)"', html_kurikulum)
akademik_state = [cls for cls, name in groups_kurikulum if name == "Akademik"]
mahasiswa_state = [cls for cls, name in groups_kurikulum if name == "Mahasiswa"]
check("Grup aktif ('Akademik') otomatis terbuka (tanpa class 'collapsed') saat halaman Kurikulum dibuka",
      akademik_state and "collapsed" not in akademik_state[0])
check("Grup tidak aktif ('Mahasiswa') default tertutup (class 'collapsed') saat halaman Kurikulum dibuka",
      mahasiswa_state and "collapsed" in mahasiswa_state[0])
check("Ada kontrol toggleNavGroup() untuk buka/tutup grup lewat klik/keyboard",
      "toggleNavGroup" in html)

# ---------------------------------------------------------------------
# 8. Modul baru: Panduan Penggunaan Aplikasi (grup Pengaturan)
# ---------------------------------------------------------------------
r_panduan = client.get("/panduan/")
check("Modul Panduan Penggunaan merespons 200", r_panduan.status_code == 200)
panduan_html = r_panduan.data.decode()
check("Panduan memuat penjelasan langkah pemakaian modul",
      "Langkah pemakaian".encode() in r_panduan.data)
check("Panduan mencakup seluruh grup sidebar (kecuali Utama)",
      all(g in panduan_html for g in [
          "🎓 Akademik", "👤 Mahasiswa", "📚 Tugas Akhir", "🧑‍🏫 SDM", "🧪 Tri Dharma",
          "🤝 Kerja Sama", "📊 Mutu &amp; Analytics", "📁 Operasional", "⚙️ Administrasi",
          "⚙️ Pengaturan",
      ]))
check("Panduan Penggunaan ada di sidebar grup Pengaturan (menu nyata, bukan placeholder roadmap)",
      any("/panduan/" in h for h in hrefs) and "/segera/" not in [h for h in hrefs if "/panduan/" in h][0])

# ---------------------------------------------------------------------
# 9. Kontrol "Buka semua / Tutup semua" di sidebar utama
# ---------------------------------------------------------------------
check("Tombol 'Buka semua'/'Tutup semua' ada di sidebar utama", "sidebar-bulk-toggle" in html and "setAllNavGroups" in html)

# ---------------------------------------------------------------------
# 10. Highlight kata kunci pencarian & tombol cetak/PDF di halaman Panduan
# ---------------------------------------------------------------------
check("Halaman Panduan punya fungsi highlight pencarian (panduanHighlight)", "panduanHighlight" in panduan_html)
check("Halaman Panduan punya tombol cetak/simpan PDF (panduanPrint)",
      "panduanPrint" in panduan_html and "Cetak / Simpan PDF" in panduan_html)
check("Halaman Panduan punya tombol 'Unduh Dokumen Resmi (.docx)' (dokumen Word sungguhan, bukan cuma print)",
      "panduan/unduh" in panduan_html and "Unduh Dokumen Resmi" in panduan_html)

print("\n=== SELESAI ===")
if FAILS:
    print("ADA YANG GAGAL:", FAILS)
    sys.exit(1)
else:
    print("SEMUA TES LULUS.")
