# Addendum Audit Lanjutan 6 — Dampak Bug `nilai_angka_ke_huruf()` Meluas ke Dokumen Resmi Yudisium & Wisuda

Laporan tambahan atas temuan pengguna yang mengonfirmasi bahwa bug
`nilai_angka_ke_huruf()` (sebelumnya tanpa grade D/E, sudah ditambal
sebelumnya di `app/constants.py`) ternyata **bukan cuma tampilan
internal** — titik dampaknya jauh lebih luas dan lebih formal.

## Ringkasan temuan

`nilai_angka_ke_huruf()` juga dipakai di `logic.rencana_yudisium_rows()`
dan `logic.wisuda_rows()` untuk mengisi kolom "Nilai Huruf". Dua fungsi
ini dipakai di **tiga** titik resmi:

| Titik pakai | File | Sifat dokumen |
|---|---|---|
| Tabel Rencana Yudisium (layar) | `routes/kelulusan.py::yudisium_list` | Internal |
| **Ekspor Excel "Rencana Yudisium"** | `routes/kelulusan.py::yudisium_ekspor` | **Resmi (institusional)** |
| Tabel Wisuda (layar) | `routes/kelulusan.py::wisuda_list` | Internal |
| **Ekspor Excel "Wisuda"** | `routes/kelulusan.py::wisuda_ekspor` | **Resmi (institusional)** |
| **Dokumen SK Yudisium (Word)** | `routes/surat.py::_gen_sk_yudisium` | **Resmi (dokumen keputusan)** — ditemukan tambahan saat penelusuran, tidak disebutkan di laporan awal pengguna |

Akar masalah: baris di `rencana_yudisium_rows()`/`wisuda_rows()` **dijamin**
berasal dari mahasiswa yang `sidang.status_kelulusan = 'LULUS'` — itu
difilter di `logic.sync_yudisium_dari_sidang()` saat baris draft yudisium
dibuat. `status_kelulusan` adalah **keputusan manual tim penguji**,
independen dari `nilai_angka` — lumrah dalam sidang skripsi Indonesia,
kelulusan sering jadi keputusan panel meski nilai sidang pas-pasan atau
rendah.

Sebelum perbaikan ini: nilai sidang rendah (mis. 30, di bawah ambang C)
dikonversi apa adanya lewat `nilai_angka_ke_huruf()` biasa → hasilnya
**"D" atau "E"**. Padahal secara definisi aplikasi sendiri
(`constants.NILAI_HURUF_LULUS`), huruf D/E berarti **GAGAL/tidak lulus**.
Akibatnya, baris yang sama, di dokumen resmi yang sama, sekaligus
menyatakan:

- Mahasiswa **LULUS** (itulah premis dia bisa muncul di tabel Yudisium
  sama sekali), **dan**
- Nilai Huruf **"E"** (=tidak lulus, menurut definisi aplikasi sendiri)

Kontradiksi ini tertanam di dokumen yang dipakai untuk proses
yudisium/wisuda institusional (ekspor Excel) dan bahkan di draf **Surat
Keputusan Yudisium** (Word) — bukan sekadar tampilan internal yang bisa
diabaikan.

## Perbaikan

Ditambahkan fungsi konversi baru **khusus konteks yudisium**,
`constants.nilai_angka_ke_huruf_yudisium()`:

```python
def nilai_angka_ke_huruf_yudisium(nilai):
    huruf = nilai_angka_ke_huruf(nilai)
    if huruf in ("D", "E"):
        return "C"
    return huruf
```

Prinsipnya:

- **`nilai_angka` mentah tidak disentuh** — kolom "Nilai Angka" di
  ekspor/dokumen tetap tampil apa adanya, transparan penuh. Tidak ada
  data yang disembunyikan atau dipalsukan.
- Hanya **kolom turunan "Nilai Huruf"** yang di-floor ke `"C"` (huruf
  lulus terendah) kalau hasil konversi mentah jatuh ke D/E — persis
  karena baris tersebut sudah dipastikan LULUS oleh keputusan panel.
- **`nilai_angka_ke_huruf()` asli TIDAK diubah** dan tetap dipakai apa
  adanya di modul Nilai biasa (`routes/nilai.py`,
  `templates/semester_pendek.html`, dsb) — di situ tidak ada keputusan
  panel yang menimpa nilai per mata kuliah, jadi D/E memang berarti
  tidak lulus sungguhan dan harus tetap ditampilkan sebagai D/E.

Diterapkan di kedua titik sumber (`logic.rencana_yudisium_rows()` dan
`logic.wisuda_rows()`), sehingga otomatis ikut memperbaiki **ketiga**
titik pakai resmi di atas (Excel Yudisium, Excel Wisuda, SK Yudisium
Word) tanpa perlu menyentuh `routes/kelulusan.py` atau `routes/surat.py`
sama sekali — keduanya cukup memanggil fungsi `logic.py` yang sudah
diperbaiki.

## Verifikasi

Test baru: `test_audit_lanjutan_6_yudisium.py` (18 pemeriksaan), mencakup:

1. Unit fungsi baru (`nilai_angka_ke_huruf_yudisium`) — D/E di-floor ke
   C, huruf lulus lain tidak berubah, kosong tetap kosong.
2. Skenario nyata: mahasiswa LULUS dgn nilai sidang rendah (55) & sangat
   rendah (30) → `nilai_huruf` = "C" di `rencana_yudisium_rows()`, dan
   `nilai_angka` mentah tetap tampil apa adanya (tidak dipalsukan).
3. Baris yg sama juga benar di `wisuda_rows()` (via sinkronisasi
   Yudisium→Wisuda).
4. Regresi: mahasiswa nilai tinggi (88) tidak terdampak fix (tetap "A").
5. Regresi: `nilai_angka_ke_huruf()` **asli** tidak ikut berubah — D/E
   tetap D/E untuk konteks nilai mata kuliah biasa.
6. Jalur HTTP penuh: `GET /kelulusan/yudisium/ekspor` — isi file Excel
   yang benar-benar diunduh diperiksa langsung, kolom "Nilai Huruf" = "C".
7. Jalur HTTP penuh: `POST /surat/buat` (jenis "SK Yudisium") — isi
   dokumen Word yang benar-benar dihasilkan diperiksa langsung, baris
   "Nilai Huruf" = "C" (bukan "E").

**Seluruh 18 file test (17 lama + 1 baru) lulus 100% tanpa regresi**,
termasuk `test_audit_lanjutan_6.py` (fix NIDN/NIP) dan seluruh suite
audit sebelumnya.

## File yang diubah

| File | Perubahan |
|---|---|
| `app/constants.py` | Fungsi baru `nilai_angka_ke_huruf_yudisium()` (setelah `nilai_huruf_lulus()`) |
| `app/logic.py` | Import fungsi baru; `rencana_yudisium_rows()` & `wisuda_rows()` memakainya, bukan `nilai_angka_ke_huruf()` biasa |
| `test_audit_lanjutan_6_yudisium.py` | **Baru** — 18 pemeriksaan regresi (lihat di atas) |
| `ADDENDUM_YUDISIUM_WISUDA.md` | **Baru** — laporan ini |

Tidak ada perubahan skema database, tidak ada perubahan pada
`routes/kelulusan.py` atau `routes/surat.py` (keduanya otomatis ikut
benar karena memanggil `logic.py`).

## Cara memverifikasi

```bash
pip install -r requirements.txt
python3 test_audit_lanjutan_6_yudisium.py     # test baru khusus temuan ini
# atau seluruh suite:
for f in test_*.py; do python3 "$f" || echo "GAGAL: $f"; done
```
