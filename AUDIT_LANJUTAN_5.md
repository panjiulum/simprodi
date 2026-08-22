# Audit Lanjutan 5 — Kelulusan/Tracer Study, Kegiatan & Program Kerja,
# Backup & Restore, Import Excel

Lanjutan audit source code SIMPRODI, kali ini menyasar 4 modul yang belum
pernah dibedah secara khusus di iterasi audit sebelumnya:

1. **Kelulusan / Tracer Study** — `app/routes/kelulusan.py` (Rencana
   Yudisium, Wisuda, Tracer Study Alumni)
2. **Kegiatan & Program Kerja** — `app/routes/kegiatan.py`
3. **Backup & Restore** — `app/routes/backup.py` + `app/backup_core.py`
4. **Import Excel** — `app/import_excel.py` (migrasi 1x dari workbook
   lama) + `app/import_generic.py` (import rutin per-modul) +
   route-nya di `app/routes/pengaturan.py`

Metodologi: pembacaan menyeluruh baris-demi-baris tiap file di atas +
template Jinja terkait, dibandingkan dengan pola yang sudah established
di modul-modul lain yang sudah diaudit sebelumnya (terutama pola
try/except seragam di `app/error_utils.py`), lalu tiap temuan diverifikasi
lewat skrip nyata (bukan cuma dugaan) sebelum & sesudah ditambal. Semua
perbaikan diverifikasi lewat test regresi baru (`test_audit_lanjutan_5.py`,
46 pemeriksaan) + **seluruh 14 file test lain yang sudah ada tetap 100%
lulus tanpa ada yang perlu diubah** (kecuali 1 baris fixture di
`test_periode_dropdown.py`, lihat poin 5 di bawah — itu sendiri
mengonfirmasi salah satu temuan).

---

## Ringkasan temuan

| # | Modul | Temuan | Tingkat | Status |
|---|---|---|---|---|
| 1 | Kelulusan | `yudisium_simpan()` tidak dibungkus try/except — IPK bukan angka → 500 mentah | **Bug fungsional** | ✅ Ditambal |
| 2 | Kelulusan | IPK Final & status_yudisium tidak divalidasi rentang/daftar resmi | Integritas data | ✅ Ditambal |
| 3 | Kelulusan | `wisuda_simpan()` tidak dibungkus try/except (inkonsisten pola) | Minor/konsistensi | ✅ Ditambal |
| 4 | Kelulusan | `tracer_hapus()` tidak tercatat ke log aktivitas | Audit trail bolong | ✅ Ditambal |
| 5 | Kelulusan/Rekap | `_kirim_excel()` digandakan persis sama di 2 file (`kelulusan.py` & `rekap.py`) | Duplikasi kode | ✅ Disatukan |
| 6 | (lintas modul) | `app/export_utils.py` adalah **kode mati** sisa versi desktop lama (`import tkinter`) — tidak pernah dipakai, berpotensi crash kalau ter-import | Kode mati/berisiko | ✅ Diisi ulang jadi helper nyata |
| 7 | Kegiatan | `bidang`/`status`/`kategori` tidak divalidasi terhadap daftar resmi sebelum disimpan | Integritas data | ✅ Ditambal |
| 8 | Kegiatan | Anggaran (rencana & realisasi) bisa disimpan negatif | Integritas data | ✅ Ditambal |
| 9 | Backup & Restore | **Zip-slip / path traversal** pada `restore_dari_file_zip()` — `zipfile.extractall()` tanpa validasi nama entri | **Keamanan (serius)** | ✅ Ditambal |
| 10 | Import Excel | `import_generik_proses()` tidak dibungkus try/except — file `.xlsx` palsu/korup → 500 mentah | **Bug fungsional** | ✅ Ditambal |
| 11 | (aplikasi, lintas 4 modul) | Tidak ada `MAX_CONTENT_LENGTH` — semua endpoint upload (Restore, Import Excel/Generik, dokumen, dll) rentan DoS via unggahan raksasa | Keamanan (DoS) | ✅ Ditambal |
| 12 | (semua 4 modul) | Gap cakupan test — sebelumnya cuma smoke-test GET, tidak ada test alur simpan/hapus/validasi | Kualitas | ✅ Ditutup (test baru) |
| 13 | Import Excel (Generik Dosen) | **NIDN/NIP bisa terhapus diam-diam saat re-import** — `_dosen_proses()` menimpa kolom identitas dgn string kosong dari baris impor, walau baris itu cuma cocok lewat fallback nama | **Bug integritas data (serius)** | ✅ Ditambal (laporan terpisah dari pengguna, lihat bagian 13) |

Detail tiap temuan ada di bawah, disertai lokasi file & baris yang
diubah. Semua komentar penjelasan juga sudah ditanam langsung di kode
sumber (format komentar `# Audit Lanjutan — ...`) supaya alasannya tetap
terbaca di masa depan tanpa perlu buka laporan ini.

---

## 1–6. Modul Kelulusan / Tracer Study (`app/routes/kelulusan.py`)

### Temuan #1 (bug fungsional) — `yudisium_simpan()` bisa 500 mentah

Kolom "IPK Final" di `yudisium.html` adalah `<input type="text">` bebas
(bukan `type="number"`). Kode lama:

```python
ipk = f.get("ipk_final", "")
ipk = float(ipk) if ipk else None
```

Kalau operator salah ketik (mis. `"3,75"` dgn koma, atau huruf), `float()`
melempar `ValueError` yang **tidak ditangkap** — beda dari hampir semua
handler simpan lain di aplikasi ini yang seragam dibungkus
`try/except → error_utils.flash_gagal_simpan`. Hasilnya: halaman error
500 Flask mentah, bukan flash pesan ramah.

**Perbaikan**: divalidasi eksplisit (terima juga koma sbg desimal ala
Indonesia), pesan ramah kalau bukan angka, ditolak kalau di luar rentah
0.00–4.00, seluruh fungsi dibungkus try/except.

### Temuan #2 — validasi rentang IPK & status_yudisium

Sebelumnya nilai IPK apa pun diterima mentah (termasuk mis. `40` hasil
salah ketik `4.0`→`40`), dan `status_yudisium` diterima sebagai string
bebas apa pun dari POST langsung (bukan cuma lewat `<select>` HTML yang
sudah dibatasi) — berisiko merusak konsistensi data yang dipakai untuk
logika transisi (`if status == "Terlaksana": ...`) dan laporan/ekspor.
Sekarang divalidasi terhadap `C.STATUS_YUDISIUM_LIST`.

### Temuan #3 — `wisuda_simpan()` tidak konsisten

Sama seperti Temuan #1 tapi risikonya lebih rendah (kolom TEXT semua,
bukan numerik) — tetap dibungkus try/except untuk konsistensi pola +
melindungi dari galat non-numerik lain (mis. "database is locked").

### Temuan #4 — penghapusan Tracer Study tidak tercatat log

`hapus_proker()`/`hapus_kegiatan()` (di `kegiatan.py`) dan hampir semua
aksi hapus lain di aplikasi konsisten memanggil `_db.log(...)` untuk
jejak audit. `tracer_hapus()` sebelumnya **tidak** — kalau data tracer
study terhapus (sengaja/tidak sengaja), tidak ada jejaknya di Log
Aktivitas. Sudah ditambal + dibungkus try/except.

### Temuan #5 & #6 — `_kirim_excel()` digandakan + `export_utils.py` kode mati

`app/export_utils.py` ternyata **sisa kode versi desktop lama**:

```python
import tkinter
from widgets import ...
from tkinter import filedialog
...
filedialog.asksaveasfilename(...)   # dialog GUI desktop, tidak relevan di web
```

Modul `widgets` **tidak ada** di paket ini dan `tkinter` belum tentu
tersedia di server headless — kalau file ini sampai ter-import (mis.
refactor ceroboh di masa depan), aplikasi langsung crash. Diverifikasi:
**tidak ada satu pun route Flask yang mengimpornya** — betul-betul kode
mati.

Sementara itu, fungsi Excel-export yang sungguh dipakai (`_kirim_excel`)
digandakan **persis byte-untuk-byte** di `routes/kelulusan.py` (3 tempat
pakai) dan `routes/rekap.py` (5 tempat pakai) — pola klasik penyebab bug:
kalau suatu saat perlu diperbaiki (mis. lebar kolom, gaya header), mudah
lupa mengubah salah satu salinannya.

**Perbaikan**: `export_utils.py` diisi ulang dengan implementasi TUNGGAL
`kirim_excel(sheet_title, headers, rows)` yang berbasis Flask
(`send_file`), lalu kedua route diarahkan memakainya. Perilaku &
output file **identik** dengan sebelumnya (diverifikasi lewat test).

---

## 7–8. Modul Kegiatan & Program Kerja (`app/routes/kegiatan.py`)

### Temuan #7 — `bidang`/`status`/`kategori` tidak divalidasi

`simpan_proker()` & `simpan_kegiatan()` menerima nilai `bidang`, `status`,
`kategori` langsung dari form tanpa dicocokkan ke daftar resmi
(`C.BIDANG_PROKER_LIST`, `C.STATUS_PROKER_LIST`,
`C.KATEGORI_KEGIATAN_LIST`, `C.STATUS_KEGIATAN_LIST`). Risikonya rendah
selama form HTML memakai `<select>` yang sudah dibatasi pilihannya, tapi
tanpa validasi server-side, POST langsung (curl/Postman, atau `<select>`
yang di-tamper lewat DevTools) bisa menaruh nilai bebas ke kolom yang
seharusnya kategori tetap — merusak konsistensi filter & rekap yang
mengelompokkan per `bidang`/`kategori` (mis. **Rekap Program Kerja** di
`routes/rekap.py` mengelompokkan realisasi per bidang; nilai bidang yang
"nyasar" tidak akan pernah muncul di kelompok manapun secara diam-diam).

Menariknya, saat perbaikan ini diverifikasi lewat test suite yang sudah
ada, ditemukan `test_periode_dropdown.py` memakai nilai fixture
`"bidang": "Akademik"` — **bukan** nilai resmi (yang benar
`"Akademik & Kurikulum"`). Test itu sebelumnya lolos begitu saja justru
**karena** tidak adanya validasi ini. Fixture test sudah diperbaiki jadi
nilai resmi (1 baris) — ini sekaligus bukti nyata temuan #7 valid, bukan
cuma teori.

**Perbaikan**: kedua fungsi sekarang menolak (flash pesan error + tidak
menyimpan) kalau `bidang`/`kategori` di luar daftar resmi;
`status`/`status` yang tidak resmi jatuh ke default `"Direncanakan"`
(konsisten dgn pola yang sudah dipakai `yudisium_simpan()`).

### Temuan #8 — anggaran boleh negatif

`anggaran_rencana` (Program Kerja) dan `anggaran_realisasi` (Kegiatan)
sebelumnya diterima berapa pun termasuk negatif — tidak masuk akal
secara bisnis (anggaran tidak bisa minus) dan bisa merusak perhitungan
rekap/total. Sekarang ditolak dengan pesan error kalau < 0.

---

## 9. Backup & Restore (`app/backup_core.py`) — celah keamanan paling signifikan

### Temuan #9 — Zip-slip / path traversal pada restore `.zip`

`restore_dari_file_zip()` sebelumnya:

```python
with zipfile.ZipFile(uploaded_zip_path) as zf:
    zf.extractall(tmp)
```

Ini mengekstrak **seluruh isi** file `.zip` yang diunggah pengguna tanpa
memvalidasi nama tiap entrinya. Ini pola **"zip slip"** klasik
(mirip prinsip CVE-2007-4559 & turunannya): sebuah entri zip dengan nama
berisi `../../../` (path traversal) atau path absolut bisa membuat file
diekstrak **keluar** dari folder tujuan sementara (`tmp`), berpotensi
menimpa file sembarang di komputer yang menjalankan aplikasi — tergantung
hak akses proses Python yang berjalan. Python `zipfile` **tidak
menjamin** perlindungan penuh dari pola ini di semua versi/skenario.

Risiko ini nyata karena endpoint Restore memang didesain menerima
unggahan file `.zip` dari luar (walau di balik autentikasi single-admin
— defense-in-depth tetap penting untuk fitur yang menerima arsip pihak
ketiga, termasuk skenario admin tanpa sadar mengunggah file yang salah/
berbahaya).

**Perbaikan**: ditambahkan `_anggota_zip_aman()` & `_ekstrak_zip_aman()`
di `backup_core.py` — setiap nama entri divalidasi (ditolak kalau path
absolut, mengandung komponen `..`, atau hasil gabungan path "kabur"
keluar dari folder tujuan setelah dinormalisasi) **sebelum** ekstraksi
dijalankan. Validasi ini juga ditambahkan ke `validasi_file_restore_zip()`
supaya arsip berbahaya ditolak **sedini mungkin** (sebelum operator
sempat konfirmasi password, sebelum backup pra-restore dibuat) — bukan
baru ketahuan di tengah proses restore.

**Diverifikasi nyata** (bukan cuma baca kode): dibuat 1 file `.zip` uji
berisi entri `../../../../tmp/evil_pwned.txt`, dikonfirmasi:
- Sebelum perbaikan (jika ditelusuri manual): `extractall()` akan
  berusaha menulis file itu ke luar folder temp.
- Sesudah perbaikan: `validasi_file_restore_zip()` menolak file tsb
  *sebelum* proses restore dimulai sama sekali, dengan pesan jelas.
- Arsip `.zip` **sah** (hasil Backup Lengkap normal, tanpa entri jahat)
  tetap lolos validasi seperti biasa — tidak ada regresi pada alur
  restore normal (dikonfirmasi lewat test + seluruh test backup lama
  tetap lulus).

---

## 10. Import Excel (`app/import_generic.py`) — bug fungsional kedua

### Temuan #10 — file `.xlsx` palsu/korup → 500 mentah

Rute `import_generik_proses()` di `routes/pengaturan.py` memvalidasi
upload **hanya** lewat ekstensi nama file (`.lower().endswith(".xlsx")`),
lalu memanggil:

```python
hasil = import_generic.proses_upload(modul, file.stream, conn)
```

**tanpa** dibungkus try/except — berbeda dengan `import_export()` (fungsi
tetangganya di file yang sama, untuk migrasi 1x) yang memang sudah
dibungkus. File apa pun yang namanya diganti jadi `*.xlsx` (mis. `.txt`
biasa, atau file `.xlsx` yang korup/setengah terunggah) lolos pemeriksaan
ekstensi lalu meledak di `openpyxl.load_workbook()` sebagai
`zipfile.BadZipFile`/`KeyError`/`InvalidFileException` mentah → 500
Internal Server Error, bukan pesan ramah seperti pola `error_utils.py`
di seluruh aplikasi.

**Perbaikan**: `openpyxl.load_workbook()` di dalam `proses_upload()`
sendiri (bukan di level route) dibungkus try/except, supaya **semua**
pemanggil fungsi ini di masa depan otomatis ikut terlindungi. Galat tak
terduga tetap dicatat ke logger (`error_utils.logger.exception(...)`)
untuk keperluan debugging, tapi pengguna melihat pesan yang jelas &
dapat ditindaklanjuti ("pastikan file benar-benar hasil isian template
.xlsx ... dan tidak korup"), bukan stack trace.

Diverifikasi: unggah file `dosen_palsu.xlsx` berisi teks biasa → sebelum
perbaikan akan 500, sesudah perbaikan tetap 200 dgn flash pesan ramah.

---

## 11. Tidak ada `MAX_CONTENT_LENGTH` (lintas modul, terutama Backup & Import)

Diperiksa di seluruh `app/`: **tidak ada satu pun** tempat yang menetapkan
`app.config["MAX_CONTENT_LENGTH"]`. Artinya Flask/Werkzeug menerima body
request **sebesar apa pun** dari jaringan sebelum kode aplikasi sempat
menolak berdasarkan ukuran. Ini relevan khususnya untuk 2 dari 4 modul
yang diaudit di sini:

- **Restore** — `backup_core.MAKS_UKURAN_RESTORE_ZIP_BYTES` (1 GB) baru
  diperiksa **setelah** file selesai diterima & ditulis ke disk oleh
  `file.save(tmp_path)` di route — jadi batas itu tidak mencegah upload
  raksasa memenuhi disk/RAM lebih dulu.
- **Import Excel/Generik** — tidak ada pemeriksaan ukuran sama sekali
  sebelumnya (hanya ekstensi `.xlsx`).

Ini celah **denial-of-service (DoS)** sederhana: cukup 1 permintaan
unggahan yang sangat besar untuk menghabiskan resource server.

**Perbaikan**: `app.config["MAX_CONTENT_LENGTH"]` ditetapkan secara
eksplisit di `app/__init__.py` (1100 MB — sedikit di atas batas terbesar
yang memang valid, yaitu Backup Lengkap `.zip` 1 GB, supaya restore sah
tetap bisa lolos). Ditambahkan juga `@app.errorhandler(413)` supaya
unggahan yang melebihi batas menampilkan flash pesan ramah ("Berkas yang
diunggah terlalu besar (maks N MB)"), bukan halaman galat 413 mentah
bawaan Werkzeug — konsisten dengan pola `@app.errorhandler(CSRFError)`
yang sudah ada di file yang sama.

---

## 12. Cakupan pengujian sebelumnya

Sebelum audit ini, cakupan test untuk 4 modul ini sangat tipis:
- Kelulusan: hanya smoke-test `GET /kelulusan/yudisium` & `GET .../wisuda`
  (status 200), **tidak ada** test untuk alur simpan/hapus/ekspor/validasi.
- Kegiatan: ada 1 test dasar simpan Program Kerja (dari audit periode
  akademik sebelumnya), **tidak ada** test untuk modul Kegiatan
  (`kegiatan_prodi`) sama sekali, tidak ada test hapus/realisasi/validasi.
- Backup & Restore: ada test reminder & retensi, **tidak ada** test untuk
  alur restore `.zip` (apalagi kasus berbahaya).
- Import Excel/Generik: ada test duplikasi & kode otomatis untuk SDM,
  **tidak ada** test untuk file korup/tidak valid.

**Ditutup** lewat `test_audit_lanjutan_5.py` (baru, 46 pemeriksaan,
seluruhnya lulus), mencakup: alur normal maupun kasus tepi/berbahaya
untuk seluruh 12 temuan di atas, plus regresi eksplisit ke halaman-halaman
utama 4 modul tsb + modul lain yang bersinggungan (Rekap, Dashboard).

---

## 13. Bug dilaporkan pengguna — Import Generik Dosen menghapus NIDN/NIP saat re-import

Ditemukan & dilaporkan (dgn eksekusi nyata utk membuktikan) di iterasi
audit berikutnya, ditambal di file yang sama: `app/import_generic.py`.

### Akar masalah

`_dosen_proses()` mencocokkan baris impor ke dosen yang sudah ada lewat
**2 jalur**: NIDN dulu (kalau baris punya NIDN), fallback ke nama
(case-insensitive) kalau NIDN di baris kosong. Setelah cocok (lewat
jalur mana pun), query `UPDATE` sebelumnya **selalu** menulis ulang
kolom `nidn`(dan `nip`) dengan nilai dari baris impor apa adanya —
termasuk kalau kosong:

```python
nidn = norm(row.get("NIDN"))
...
nilai = (nidn, nama, ..., norm(row.get("NIP")), ...)
conn.execute("UPDATE dosen SET nidn=?, ..., nip=?, ... WHERE id=?", nilai + (existing["id"],))
```

**Skenario nyata**: operator mengunduh template "Import Data Dosen"
untuk memperbarui sebagian data saja (mis. email/No HP berubah), tidak
mengisi ulang kolom NIDN di tiap baris (mengira "kalau kosong ya
dibiarkan, sistem akan cocok lewat nama") — hasilnya NIDN semua dosen
yang kebetulan cocok lewat jalur nama **hilang otomatis dan diam-diam**,
tanpa peringatan apa pun (`hasil['update']` tetap naik normal seperti
update biasa, tidak ada flag "kolom X ikut terhapus"). Serius karena
NIDN adalah kunci identitas resmi dosen yang dipakai banyak sistem
eksternal (Sister/PDDikti).

**Diverifikasi lewat eksekusi nyata** sebelum ditambal:
```
Dosen awal: NIDN='1234567890', email='lama@x.com'
Import ulang: Nama='Dr. Contoh Uji' (sama), NIDN=(kosong), Email='baru@x.com'
Hasil: status='update' (normal, tanpa flag apa pun)
NIDN setelah re-import: ''   <- HILANG
Email setelah re-import: 'baru@x.com'   <- berhasil (memang yang dimaksud)
```

Diperiksa juga: kolom **NIP** (identitas resmi lain, tidak pernah
dipakai sbg kunci pencocokan sama sekali) ternyata punya risiko yang
**lebih luas** — bisa hilang bahkan saat baris dicocokkan langsung lewat
NIDN itu sendiri (bukan cuma lewat fallback nama), karena kolom `nip`
memang ditulis ulang tanpa syarat apa pun di query UPDATE yang sama.

### Perbaikan

Ditambahkan logika "jangan timpa dengan kosong" **khusus untuk 2 kolom
identitas resmi** (`nidn` & `nip`) — persis pola yang direkomendasikan:

```python
nidn_final = nidn or (existing["nidn"] if existing else "")
nip_final  = nip  or (existing["nip"]  if existing else "")
```

Query `SELECT` untuk `existing` diperluas mengikutkan `nidn, nip` (tadinya
cuma `id`) supaya nilai lama tersedia untuk fallback ini. Kolom detail
lain (No HP, Email, Jabatan Fungsional, dst.) **sengaja tidak** diberi
proteksi yang sama — itu memang cara operator mengosongkan kolom
tersebut secara sengaja lewat re-import; hanya identitas resmi yang
butuh proteksi ekstra karena kalau hilang, tidak ada indikasi apa pun ke
operator.

### Importer lain diperiksa — tidak ada bug analog

Sesuai rekomendasi, diperiksa (dan **diverifikasi lewat eksekusi nyata**,
bukan cuma dugaan) apakah importer lain punya pola serupa:

- **Importer SDM (7 tabel log)** — dibangun oleh 1 factory
  `_buat_proses_baris_log_sdm()`. Kunci pencocokannya (`dosen_id` via
  `KOL_DOSEN`, ditambah `wajib_col` seperti "Judul*") **wajib diisi** —
  baris dengan salah satu kosong otomatis berstatus `"lewati"` dan
  **tidak pernah mencapai** query UPDATE. `dosen_id` sendiri juga tidak
  pernah ditulis ulang ke identitas dosen (cuma dipakai sbg referensi
  FK yang sudah diselesaikan di awal). **Tidak ada bug analog.**
- **Importer Mahasiswa** — NIM adalah **satu-satunya** kunci pencocokan,
  wajib diisi (`if not nim: return "lewati"`), **tanpa jalur fallback**
  seperti NIDN→nama di importer Dosen. Baris dengan NIM kosong tidak
  pernah mencapai UPDATE. **Tidak ada bug analog.**

Kesimpulan: bug ini **spesifik** untuk `_dosen_proses()` karena hanya
importer inilah yang punya pola pencocokan 2-jalur (kunci utama + jalur
fallback) — kondisi yang memungkinkan kolom identitas tetap kosong
padahal barisnya berhasil dicocokkan ke data yang sudah ada.

### Verifikasi

Ditambahkan `test_audit_lanjutan_6.py` (15 pemeriksaan): reproduksi bug
persis skenario yang dilaporkan, verifikasi NIP, regresi koreksi NIDN
yang sah (bukan kosong), regresi dosen baru, pembuktian tertulis importer
SDM & Mahasiswa aman, dan 1 pemeriksaan lewat jalur HTTP penuh
(`POST /pengaturan/import-generik/proses`) — bukan cuma panggilan fungsi
langsung. Seluruh 16 file test (14 dari audit sebelumnya + 2 baru) lulus
100%.



| Berkas | Perubahan |
|---|---|
| `app/routes/kelulusan.py` | Perbaikan #1–5 (yudisium/wisuda/tracer + pakai `export_utils`) |
| `app/routes/rekap.py` | Perbaikan #5 (pakai `export_utils` bersama) |
| `app/export_utils.py` | **Diisi ulang total** — kode mati dibuang, jadi helper Excel bersama |
| `app/routes/kegiatan.py` | Perbaikan #7–8 (validasi bidang/status/kategori + anggaran non-negatif) |
| `app/backup_core.py` | Perbaikan #9 (zip-slip) — fungsi baru `_anggota_zip_aman`/`_ekstrak_zip_aman` |
| `app/import_generic.py` | Perbaikan #10 (bungkus `openpyxl.load_workbook` dgn try/except) + Perbaikan #13 (`_dosen_proses`: lindungi NIDN/NIP dari tertimpa kosong) |
| `app/__init__.py` | Perbaikan #11 (`MAX_CONTENT_LENGTH` + errorhandler 413) |
| `test_periode_dropdown.py` | 1 baris fixture diperbaiki (nilai bidang resmi) — imbas temuan #7 |
| `test_audit_lanjutan_5.py` | **Baru** — 46 pemeriksaan regresi utk temuan #1–11 |
| `test_audit_lanjutan_6.py` | **Baru** — 15 pemeriksaan regresi utk temuan #13 (bug NIDN/NIP) |
| `AUDIT_LANJUTAN_5.md` | **Baru** — laporan ini |

## Cara memverifikasi

```bash
pip install -r requirements.txt
python3 test_audit_lanjutan_5.py     # test baru khusus audit ini
# atau seluruh suite:
for f in test_*.py; do python3 "$f" || echo "GAGAL: $f"; done
```

Seluruh **15 file test** (14 lama + 1 baru) lulus 100% tanpa regresi.

## Rekomendasi lanjutan (di luar cakupan/waktu audit kali ini)

Beberapa hal level "nice-to-have" yang teridentifikasi tapi sengaja
**tidak** ditambal karena dampaknya kecil/di luar cakupan 4 modul yang
diminta — dicatat di sini supaya tidak hilang:

- **Zip-bomb pada Import Excel**: `openpyxl.load_workbook()` tidak
  punya proteksi bawaan terhadap file `.xlsx` (yang sejatinya arsip zip)
  yang didesain untuk membengkak luar biasa saat dibuka (decompression
  bomb). Risikonya rendah di aplikasi single-admin offline ini, tapi
  kalau suatu saat dibuka untuk banyak pengguna, layak dipertimbangkan
  batas ukuran per-file yang lebih ketat khusus endpoint import
  (terpisah dari `MAX_CONTENT_LENGTH` global 1100 MB).
- **Kolom "IPK Final" & anggaran** di `yudisium.html`/`kegiatan.html`
  masih `<input type="text">` polos — sudah aman di sisi server (lihat
  temuan #2 & #8), tapi menambahkan `type="number" step="0.01"` di HTML
  akan memberi validasi instan di browser (UX lebih baik, mengurangi
  kemungkinan pesan error server perlu muncul sama sekali).
- **Pagination** — `kegiatan_rows`/`proker_rows` di `kegiatan.py` (dan
  pola serupa di modul lain) memuat seluruh baris sekaligus tanpa
  batas/halaman. Bukan masalah untuk skala data 1 prodi, tapi dicatat
  sebagai batas skalabilitas kalau volume data jadi sangat besar.
