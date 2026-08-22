# Addendum — SK Yudisium per Tahap/Gelombang

Permintaan pengguna: honor dosen (penguji seminar, penguji sidang,
pembimbing skripsi) dibayarkan **per tahap**, dan **SK Yudisium juga
harus dibuat/dikeluarkan per tahap** — bukan lagi satu-satu per
mahasiswa.

## Audit: apa yang sudah ada, apa yang belum

Sebelum menambah kode, ditelusuri dulu modul Pengajuan Judul → Penetapan
Pembimbing → Seminar → Sidang → Yudisium, karena konsep "Tahap" ini
ternyata **sudah ada** sebagian:

| Bagian | Status sebelum addendum ini |
|---|---|
| Master Tahap/Gelombang (`tahap_pengajuan`, per Periode Akademik, jumlah dinamis, dikelola di Pengaturan → Tahun Akademik) | ✅ Sudah ada |
| Pengajuan Judul — kolom `tahap` diisi dari dropdown master Tahap | ✅ Sudah ada |
| Penetapan Pembimbing — kolom `tahap` diisi dari dropdown master Tahap (ini yang jadi acuan tunggal tahap milik satu mahasiswa sepanjang proses skripsinya) | ✅ Sudah ada |
| Rekap Honor Pembimbing — filter per tahap | ✅ Sudah ada (`logic.rekap_pembimbing`) |
| Rekap Honor Penguji Seminar — filter per tahap | ✅ Sudah ada (`logic.rkp_seminar`) |
| Rekap Honor Penguji Sidang + Honor Pembimbing 1/2 — filter per tahap | ✅ Sudah ada (`logic.rkp_sidang`) |
| **Rencana Yudisium** — filter per tahap | ❌ **Belum ada** |
| **Wisuda** — filter per tahap | ❌ **Belum ada** |
| **SK Yudisium** — dibuat per tahap (satu SK utk satu batch kelulusan) | ❌ **Belum ada** — sebelumnya `routes/surat.py::_gen_sk_yudisium` hanya bisa cetak 1 dokumen per 1 mahasiswa, tanpa konsep tahap sama sekali |

Jadi pipeline "tahap" untuk Pengajuan Judul → Penetapan Pembimbing →
rekap honor **sudah lengkap**. Titik yang betul-betul hilang, sesuai
laporan pengguna, adalah ujung pipeline-nya: **Rencana Yudisium & SK
Yudisium**.

## Perubahan yang ditambahkan

Sumber "tahap" untuk seorang mahasiswa **tidak diduplikasi** ke tabel
`yudisium`/`wisuda` (supaya tidak ada 2 sumber kebenaran yang bisa
berbeda) — cukup di-*join* dari `penetapan_pembimbing.tahap` milik
mahasiswa yang sama, identik dengan pola yang sudah dipakai
`rkp_seminar`/`rkp_sidang`/`rekap_pembimbing`.

1. **`app/logic.py`**
   - `rencana_yudisium_rows(conn, tahap_filter=None)` — sekarang JOIN ke
     `penetapan_pembimbing` dan bisa disaring per tahap.
   - `wisuda_rows(conn, tahap_filter=None)` — idem.

2. **`app/routes/kelulusan.py`**
   - `/kelulusan/yudisium` & `/kelulusan/wisuda` — terima `?tahap=...`,
     tab filter tahap (pola sama seperti halaman Rekap Honor).
   - `/kelulusan/yudisium/ekspor` & `/kelulusan/wisuda/ekspor` — ekspor
     Excel ikut tersaring per tahap + kolom baru "Tahap/Gelombang".
   - **Baru:** `POST /kelulusan/yudisium/tetapkan-tahap` — menetapkan
     **satu** No. SK + Tgl Yudisium ke **semua** mahasiswa pada satu
     tahap sekaligus (satu SK Yudisium memang lazimnya berlaku untuk satu
     batch kelulusan, bukan satu SK per mahasiswa). Baris yang No. SK-nya
     sudah diisi manual sebelumnya **tidak ditimpa**, kecuali operator
     mencentang "Timpa data yang sudah ada".

3. **`app/routes/surat.py`**
   - **Baru:** `_gen_sk_yudisium_tahap()` + route
     `GET /surat/sk-yudisium-tahap?tahap=...` — mencetak **satu** dokumen
     Word berisi tabel semua mahasiswa LULUS pada tahap terpilih (NIM,
     Nama, Nilai Huruf, IPK Final, Predikat), dengan satu Nomor SK &
     Tanggal Yudisium untuk seluruh batch.
   - Generator lama `_gen_sk_yudisium()` (satu dokumen per satu
     mahasiswa) **tetap dipertahankan apa adanya** — masih dipakai kalau
     sewaktu-waktu perlu cetak ulang SK 1 mahasiswa secara individual.

4. **Template** `yudisium.html` & `wisuda.html` — tab filter tahap
   (`_tahap_filter.html`, sama seperti Rekap Honor), kolom "Tahap" di
   tabel, dan panel baru di `yudisium.html`: form "Terapkan No. SK ke
   Tahap Ini" + tombol "Cetak SK Yudisium (Tahap Ini)".

## Tidak diubah

- Skema tabel `yudisium`/`wisuda` — tidak ada kolom baru (tahap diambil
  via JOIN, bukan disimpan ulang).
- Rekap Honor Pembimbing/Seminar/Sidang — sudah benar sebelumnya, tidak
  disentuh.
- `_gen_sk_yudisium()` (versi per-mahasiswa) — tidak diubah.

## Verifikasi

Test baru: `test_tahap_yudisium.py` (28 pemeriksaan) — mencakup filter
tahap di `logic.py`, halaman Yudisium/Wisuda, penetapan No. SK per tahap
(termasuk perilaku "tidak menimpa" vs "timpa"), pencetakan SK per tahap
(isi dokumen Word diperiksa langsung, termasuk memastikan mahasiswa dari
tahap lain TIDAK ikut muncul), serta kolom Tahap di ekspor Excel.

```bash
python3 test_tahap_yudisium.py
# atau seluruh suite (termasuk 19 test lama, semua tetap lulus tanpa regresi):
for f in test_*.py; do python3 "$f" || echo "GAGAL: $f"; done
```

## Cara pakai (ringkas)

1. Pengaturan → Tahun Akademik: pastikan Tahap/Gelombang sudah dibuat
   untuk periode aktif (bisa lebih dari 2, mis. 3 tahap per semester).
2. Pengajuan Judul & Penetapan Pembimbing: pilih Tahap yang sesuai saat
   input data mahasiswa — tahap ini otomatis mengalir ke Seminar, Sidang,
   Rekap Honor, dan sekarang juga ke Yudisium.
3. Rencana Yudisium: klik tab tahap yang dituju → isi "No. SK Yudisium" +
   "Tgl Yudisium" sekali di panel kanan → "Terapkan ke Tahap Ini" akan
   mengisi seluruh mahasiswa LULUS pada tahap itu sekaligus.
4. Klik "Cetak SK Yudisium (Tahap Ini)" untuk mengunduh satu dokumen Word
   berisi daftar semua mahasiswa pada tahap tersebut.
