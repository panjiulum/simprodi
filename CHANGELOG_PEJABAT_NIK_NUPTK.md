# Changelog — Pejabat Struktural & NIK/NUPTK Dosen

Ringkasan perubahan yang ditambahkan di atas basis kode SIMPRODI yang ada,
mengikuti gaya dokumentasi audit yang sudah dipakai di proyek ini
(FONDASI.md, ADDENDUM_*.md).

## 1. Data Dosen: NIP → NIK + NUPTK (struktur data SISTER)

**Masalah**: Form & import Data Dosen memakai kolom **NIP** (Nomor Induk
Pegawai) sebagai satu-satunya identitas kepegawaian. Struktur data SISTER
(PDDIKTI/Kemdikbudristek) tidak memakai NIP untuk dosen — yang dipakai
adalah **NIK** (Nomor Induk Kependudukan, wajib untuk dosen PNS maupun
non-PNS/swasta) dan **NUPTK** (Nomor Unik Pendidik & Tenaga Kependidikan).

**Perubahan**:
- `app/db.py` — tambah kolom `dosen.nik` & `dosen.nuptk` (CREATE TABLE
  untuk instalasi baru + migrasi `ALTER TABLE` idempoten untuk database
  lama). Kolom `dosen.nip` lama **dipertahankan apa adanya** di skema agar
  data lama tidak hilang, tapi sudah tidak dipakai lagi di form/import/
  ekspor.
- `app/routes/dosen.py` — form simpan pakai `nik`/`nuptk`; validasi lunak
  (peringatan, bukan blokir) kalau bukan 16 digit angka.
- `app/templates/dosen.html` — field NIP diganti field NIK + NUPTK; kolom
  NIK ditambahkan ke tabel daftar dosen.
- `app/import_generic.py` — template Excel & logika impor/pembaruan Data
  Dosen diubah dari NIP → NIK + NUPTK, termasuk proteksi "jangan ditimpa
  kosong" untuk kolom identitas resmi (sebelumnya hanya melindungi
  NIDN & NIP).
- `app/error_utils.py` — tambah label ramah untuk pesan galat kolom NIK/NUPTK.
- `app/routes/pengaturan.py` — ekspor Data Dosen (`/pengaturan/export/dosen`)
  sekarang menyertakan kolom NIK & NUPTK.

## 2. Pengaturan Pejabat Struktural (Rektor/Dekan/Kaprodi)

**Fitur baru**: halaman **Pengaturan → Pejabat Struktural**
(`/pengaturan/pejabat`) — direktori pejabat struktural institusi (Rektor,
Wakil Rektor, Dekan, Wakil Dekan, Ketua Program Studi/Kaprodi, Sekretaris
Prodi, dst), masing-masing dengan jabatan, unit, nama lengkap (+gelar),
NIP/NIDN, no. SK pengangkatan, TMT, akhir masa jabatan, dan status aktif.

- `app/db.py` — tabel baru `pejabat_struktural`.
- `app/constants.py` — daftar saran nama jabatan (`DAFTAR_JABATAN_STRUKTURAL`,
  ditampilkan lewat `<datalist>` — bukan pembatas keras, tetap bisa diketik
  bebas) + setting baru `nip_nidn_penandatangan_default`.
- `app/routes/pengaturan.py` — route CRUD (`pejabat`, `pejabat_simpan`,
  `pejabat_hapus`) + **"Jadikan Default Penandatangan"**
  (`pejabat_jadikan_default`), yang menyinkronkan pejabat terpilih ke 3
  kunci pengaturan (`nama_penandatangan_default`,
  `jabatan_penandatangan_default`, `nip_nidn_penandatangan_default`).
- `app/templates/pengaturan/pejabat.html` — halaman baru (daftar + form).
- `app/templates/base.html` — tautan sidebar baru di grup Administrasi.
- `app/routes/panduan.py` — entri panduan penggunaan baru untuk modul ini.

### Bug nyata yang ditemukan & diperbaiki sekalian

`_footer_ttd()` di `app/routes/surat.py` (dipakai oleh **SK Pembimbing, SK
Yudisium, Undangan Seminar, Undangan Sidang**) ternyata **selalu
hardcode** `"Ketua Program Studi,"` dengan baris nama penandatangan
**kosong** — 2 pengaturan yang sudah ada sebelumnya
(`nama_penandatangan_default`/`jabatan_penandatangan_default`, sudah
dipakai normal di Generator Surat Umum) sama sekali **tidak pernah
dibaca** di sini. Artinya Kaprodi harus menulis tangan nama penandatangan
di setiap dokumen SK/undangan yang dicetak.

Sekarang `_footer_ttd()` membaca ketiga setting di atas (termasuk NIP/NIDN
yang baru), dengan fallback ke perilaku lama kalau belum pernah diisi
sehingga tidak ada baris kosong yang membingungkan. Generator Surat Umum
(`routes/surat_umum.py`) juga diperbarui agar NIP/NIDN pejabat ikut
tercetak di bawah nama penandatangan.

## Tes

Dua skrip tes baru ditambahkan mengikuti pola `test_*.py` yang sudah ada:

- `test_dosen_nik_nuptk.py` — form, simpan, validasi lunak, template
  import, dan ekspor Data Dosen memakai NIK/NUPTK (bukan NIP lagi).
- `test_pejabat_struktural.py` — CRUD pejabat, validasi wajib isi, sinkron
  "Jadikan Default Penandatangan", dan **verifikasi end-to-end**: cetak SK
  Pembimbing sungguhan menghasilkan dokumen Word dengan nama, jabatan, dan
  NIP/NIDN Kaprodi yang benar tercetak di blok tanda tangan.

`test_sidebar.py` diperbarui (jumlah tautan sidebar +1) karena penambahan
menu baru.

Seluruh 25 skrip `test_*.py` di root proyek (termasuk 2 yang baru) LULUS.
