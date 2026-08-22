# Audit Lanjutan 10 — Kerapian Modul Surat (Poin 5)

Lanjutan audit source code SIMPRODI, kali ini menyasar **Poin 5 dari daftar
audit yang belum dikerjakan: kerapian modul Surat Umum** —
`app/routes/surat.py` (360 baris sebelum perbaikan, sekarang 415 baris
setelah ditambal + komentar penjelasan).

Catatan penamaan: file ini secara teknis adalah generator **Surat Tugas
Akhir** (SK Pembimbing, SK Yudisium per-mahasiswa & per-Tahap/Gelombang,
Undangan Seminar/Sidang) — bukan `surat_umum.py` (Modul 8, generator surat
administratif umum di luar Tugas Akhir: Surat Tugas/Keterangan/SK/dst).
Keduanya berbagi gaya kop & blok tanda tangan yang sama (dibaca dari
Pengaturan > Pejabat Struktural), sehingga temuan #1 dan #2 di bawah relevan
untuk dibandingkan dengan pola yang sudah lebih rapi di `surat_umum.py`.

Metodologi: pembacaan menyeluruh baris-demi-baris `surat.py` + perbandingan
pola dengan modul lain yang sudah diaudit (`app/error_utils.py`,
`routes/panduan.py`, `routes/surat_umum.py`, `routes/mutu.py`), setiap
temuan **diverifikasi lewat skrip nyata** (termasuk membongkar XML gaya
tabel bawaan python-docx) sebelum ditambal, lalu diverifikasi lagi lewat
test regresi baru (`test_audit_lanjutan_10_surat_kerapian.py`, 24
pemeriksaan) + **seluruh 28 file test lain yang sudah ada tetap 100% lulus
tanpa satu pun yang perlu diubah**.

---

## Ringkasan temuan

| # | Temuan | Tingkat | Status |
|---|---|---|---|
| 1 | `buat()` & `sk_yudisium_tahap()` tidak dibungkus try/except sama sekali — satu-satunya route penghasil dokumen di seluruh aplikasi yang begitu | **Bug fungsional** | ✅ Ditambal |
| 2 | Tabel data (SK Pembimbing/Yudisium, rekap per-Tahap, Undangan) tidak pernah diberi `table.style` — jatuh ke gaya bawaan "Normal Table" tanpa garis batas sel sama sekali | **Cacat tampilan dokumen resmi** | ✅ Ditambal |
| 3 | `import docx` & submodulnya diimpor ulang identik di 5 fungsi berbeda, padahal modul ini selalu dimuat penuh saat app start | Kerapian/duplikasi | ✅ Ditambal |
| 4 | Daftar 4 jenis surat ditulis manual di 3 tempat terpisah (`JENIS_SURAT`, key `_GENERATORS`, key `_PESAN_KOSONG`) | Kerapian/risiko drift | ✅ Ditambal |
| 5 | Gaya ekspresi ternary utk `judul` di `_gen_undangan` tidak konsisten antara cabang Seminar & Sidang | Kerapian/keterbacaan | ✅ Ditambal |
| 6 | Docstring modul sudah usang (tidak menyebut fitur penandatangan default & hubungannya dgn `surat_umum.py`) | Dokumentasi | ✅ Diperbarui |

Semua komentar penjelasan sudah ditanam langsung di kode sumber (format
`# Audit Lanjutan 10 — ...`) supaya alasannya tetap terbaca di masa depan
tanpa perlu membuka laporan ini.

---

## 1. `buat()` & `sk_yudisium_tahap()` — tanpa try/except sama sekali

### Verifikasi

```
mock.patch.object(surat_mod._db, "get_setting", side_effect=RuntimeError)
POST /surat/buat  ->  500 Internal Server Error (traceback mentah, sebelum ditambal)
```

Sebelum perbaikan, seluruh alur "generate dokumen .docx → catat ke
`_db.log()` → kirim sebagai unduhan" di kedua route ini **tidak dibungkus
apa pun**. Semua route pembuat dokumen lain di aplikasi (`routes/panduan.py`,
`routes/rekap.py`, `routes/surat_umum.py`) memang juga tidak 100% seragam,
tapi `surat.py` adalah satu-satunya yang membaca banyak `get_setting()` +
beberapa `SELECT` bertingkat (mahasiswa, penetapan_pembimbing/seminar/
sidang/yudisium, dosen) sebelum sempat mengirim file — banyak titik yang
bisa gagal karena galat basis data wajar (mis. "database is locked" saat
operator lain sedang menyimpan data di waktu bersamaan), bukan cuma bug
pemrograman.

### Perbaikan

Kedua route dibungkus `try/except Exception as e: EH.flash_gagal_simpan(e, ...)`,
persis pola terpusat yang sudah dipakai 30+ kali di modul lain (lihat
`app/error_utils.py`). Pesan flash yang ditampilkan menyertakan jenis surat
yang gagal dibuat, supaya operator tahu persis surat mana yang perlu dicoba
ulang.

**Diverifikasi**: jalur galat sekarang redirect + flash pesan ramah (bukan
500), DAN jalur sukses (tanpa mock) tetap mengirim dokumen `.docx` yang
valid — try/except baru tidak menelan jalur normal.

---

## 2. Tabel dokumen tanpa garis batas sel sama sekali

### Verifikasi

```python
>>> import docx
>>> d = docx.Document()
>>> t = d.add_table(rows=0, cols=2)
>>> t.style.name
'Normal Table'
```

`doc.add_table()` di python-docx, tanpa `table.style` di-set eksplisit,
jatuh ke gaya bawaan **"Normal Table"** — gaya ini secara definisi tidak
punya elemen `tblBorders` sama sekali. Ini dipakai di 4 tempat di
`surat.py` (`_tabel()` — dipakai SK Pembimbing/Yudisium & Undangan; tabel
rekap 6-kolom di `_gen_sk_yudisium_tahap`; tabel "Susunan Tim" `t2` di
`_gen_undangan`) — **tidak satu pun** yang men-set gaya tabel.

Akibatnya: SK Pembimbing, SK Yudisium (per-mahasiswa maupun per-Tahap), dan
Undangan Seminar/Sidang yang dicetak dan dibuka Kaprodi selama ini tampil
sebagai dua/enam kolom teks rata kiri **tanpa kotak pembatas** — bukan
tabel data formal yang lazim di surat keputusan/undangan resmi institusi.
Bandingkan dengan `routes/panduan.py` yang sudah benar men-set
`table.style = "Light Grid Accent 1"` (atau fallback `"Table Grid"`).

### Perbaikan

Ditambahkan helper `_gaya_tabel(doc)` (logika fallback sama seperti di
`panduan.py`) dan diterapkan ke **seluruh 4 tabel** yang dibuat modul ini.
Sekaligus label kolom kiri di `_tabel()` dibuat **bold** (konsisten dengan
pola label-tebal di `panduan.py`), supaya tabel data di SK/Undangan lebih
mudah dibaca (nama kolom vs isi).

**Diverifikasi** lewat pembacaan ulang dokumen `.docx` hasil generate di
test: `doc.tables[0].style.name` sekarang `"Table Grid"` atau
`"Light Grid Accent 1"` (bukan lagi `"Normal Table"`), untuk SK Pembimbing
maupun kedua tabel di Undangan Seminar.

---

## 3. Duplikasi `import docx` di 5 fungsi

`import docx`, `from docx.enum.text import WD_ALIGN_PARAGRAPH`, dan
`from docx.shared import Pt` sebelumnya diketik ulang **persis sama** di
`_header()`, `_gen_sk_pembimbing()`, `_gen_sk_yudisium()`,
`_gen_sk_yudisium_tahap()`, dan `_gen_undangan()` — 15 baris identik yang
berulang.

Pola *lazy import* docx di dalam fungsi memang konvensi yang dipakai
konsisten di beberapa modul lain (`routes/panduan.py`, `routes/surat_umum.py`)
untuk menghindari beban impor python-docx yang tidak perlu kalau halaman
itu tidak pernah diakses. **Tapi pola itu hanya masuk akal kalau modulnya
sendiri baru diimpor saat dibutuhkan** — sedangkan `app/routes/surat.py`
**selalu** diimpor penuh saat `create_app()` dipanggil (lihat
`app/__init__.py`, blueprint didaftarkan eager di awal, bukan lazy-loaded
per-request). Karena modul ini importnya sendiri sudah tidak bisa
ditunda, menunda `import docx` di dalam tiap fungsi tidak memberi
penghematan startup apa pun dibanding mengimpornya sekali di level modul —
hanya menambah 15 baris duplikasi murni.

### Perbaikan

`import docx`, `WD_ALIGN_PARAGRAPH`, `Pt` diimpor sekali di bagian atas
modul; seluruh 5 blok impor lokal yang identik dihapus.

**Diverifikasi**: seluruh test yang menghasilkan dokumen (SK Pembimbing,
Undangan Seminar/Sidang, SK Yudisium per Tahap) tetap menghasilkan `.docx`
valid — tidak ada regresi dari perubahan lingkup impor ini.

---

## 4. Daftar jenis surat ditulis manual di 3 tempat

Sebelumnya:

```python
JENIS_SURAT = ["SK Pembimbing", "SK Yudisium", "Undangan Seminar", "Undangan Sidang"]
...
_GENERATORS = {"SK Pembimbing": ..., "SK Yudisium": ..., "Undangan Seminar": ..., "Undangan Sidang": ...}
_PESAN_KOSONG = {"SK Pembimbing": ..., "SK Yudisium": ..., "Undangan Seminar": ..., "Undangan Sidang": ...}
```

Tiga struktur data terpisah, ditulis manual, harus selalu sinkron. Kalau
kelak ditambahkan jenis surat ke-5, mudah lupa menambahkan ke salah satu
dari ketiganya (mis. dropdown `JENIS_SURAT` bertambah tapi `_PESAN_KOSONG`
lupa diisi → pesan error jatuh ke fallback generik yang kurang informatif).

### Perbaikan

`JENIS_SURAT` sekarang diturunkan otomatis: `JENIS_SURAT = list(_GENERATORS)`,
ditempatkan setelah `_GENERATORS`/`_PESAN_KOSONG` didefinisikan. Satu
sumber kebenaran — `_GENERATORS` (yang memang wajib ada untuk setiap jenis
surat, karena berisi fungsi generatornya) menjadi acuan tunggal.

**Diverifikasi**: `surat_mod.JENIS_SURAT == list(surat_mod._GENERATORS)`,
dan dropdown di halaman `/surat/` tetap menampilkan keempat opsi seperti
semula.

---

## 5. Ekspresi `judul` tidak konsisten gaya (Seminar vs Sidang)

Sebelumnya:

```python
# Cabang Seminar:
judul = (row["judul_final"] if row else "") or ""
# Cabang Sidang:
judul = (row["judul_sidang"] or row["judul_final"] if row else "") or ""
```

Kedua ekspresi ini **berperilaku benar** (sudah diverifikasi lewat test —
prioritas operator Python membuat `X or Y if row else ""` terparsing
sebagai `(X or Y) if row else ""`, bukan bug), tapi ditulis dengan gaya
berbeda untuk logika yang sejenis (fallback nilai kalau `row` ada), yang
menyulitkan pembaca membandingkan kedua cabang sekilas. Diseragamkan
menjadi bentuk eksplisit `(A or B or "") if row else ""` di kedua cabang,
tanpa mengubah perilaku.

**Diverifikasi**: Undangan Seminar tetap menampilkan `judul_final`
(mis. "Judul Skripsi Uji Kerapian"), Undangan Sidang tetap menampilkan
`judul_sidang` bila ada (mis. "Judul Sidang Uji Kerapian") — sama seperti
sebelum perataan gaya.

---

## 6. Docstring modul usang

Docstring lama menyebut "Logika isi surat porting dari CetakSuratView
versi desktop... **tanpa diubah**" — padahal `_footer_ttd()` sudah diubah
signifikan pada fase Pejabat Struktural (baca dari Pengaturan, bukan lagi
hardcode "Ketua Program Studi,"), dan modul ini kini erat berelasi dengan
`surat_umum.py` (Modul 8) lewat pola kop/tanda-tangan yang sama. Docstring
diperbarui untuk mencerminkan keadaan sekarang dan mengarahkan pembaca ke
`surat_umum.py` untuk konteks yang lebih luas.

---

## Cakupan test baru

`test_audit_lanjutan_10_surat_kerapian.py` (24 pemeriksaan):

- try/except pada `buat()` & `sk_yudisium_tahap()`: galat tak terduga →
  redirect + flash ramah (bukan 500); jalur normal tetap 200 & tidak
  tertelan try/except baru.
- Gaya tabel bergaris pada dokumen SK Pembimbing & kedua tabel Undangan
  Seminar (data + susunan tim).
- Judul yang benar tetap tampil di Undangan Seminar (`judul_final`) &
  Undangan Sidang (`judul_sidang`) setelah perataan gaya ternary.
- `JENIS_SURAT` konsisten otomatis dengan `_GENERATORS`/`_PESAN_KOSONG`,
  dan dropdown `/surat/` menampilkan keempat opsi.
- `docx`/`WD_ALIGN_PARAGRAPH`/`Pt` sudah menjadi atribut level-modul
  (bukti hoisting impor berhasil).

Dijalankan bersama **28 file test lain yang sudah ada** — seluruhnya lulus
tanpa satu baris pun yang perlu diubah (murni penambahan, tidak ada
perubahan perilaku pada jalur normal manapun).
