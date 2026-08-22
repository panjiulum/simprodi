# Audit Lanjutan 12 — Audit UI/UX Menyeluruh Seluruh Modul

Dilakukan atas permintaan: **"audit kembali terhadap keseluruhan modul,
terutama dari sisi UI dan UX — memastikan setiap modul/fitur berfungsi,
layout tidak berantakan, dan seluruh UI & UX terimplementasi seragam."**

Berbeda dari Audit Lanjutan 11 (fokus keamanan backend), audit ini
menyasar **fungsionalitas end-to-end tiap halaman** dan **konsistensi
struktur/visual** di seluruh 31 modul (blueprint) & 61 file template.
Metodologi tetap sama: setiap klaim **diverifikasi lewat skrip nyata**
(crawl otomatis + parsing HTML sungguhan), bukan tinjauan visual manual
semata (tidak memungkinkan di lingkungan tanpa browser).

**Hasil akhir: tidak ditemukan bug atau inkonsistensi apa pun.** Tidak
ada kode yang diubah pada audit ini — seluruh 30 file test yang sudah ada
tetap lulus tanpa modifikasi.

---

## 1. Crawl fungsional — apakah setiap fitur benar-benar berjalan?

Skrip crawler dibuat untuk: login → isi data uji ke hampir seluruh tabel
utama (mahasiswa, dosen, ruangan, kurikulum, mata kuliah, CPL/CPMK,
jadwal kelas, KRS, BAP, pembimbing, seminar, sidang, kalender, program
kerja, dokumen, mitra/kerjasama, siklus CQI, pendaftar RPL, surat keluar,
tracer study) → **akses seluruh 81 rute GET yang terdaftar** (termasuk
rute berparameter, diisi dengan ID data uji yang sungguhan tersimpan) →
periksa tiap respons.

Yang diperiksa di tiap halaman:
- Status HTTP (harus 200, atau redirect wajar — bukan 500).
- Traceback Python yang bocor ke HTML (tanda try/except gagal menangkap
  dengan benar).
- Error `UndefinedError` Jinja (tanda variabel template hilang/typo).
- Struktur HTML dasar (halaman post-login harus mengandung kerangka
  standar `<html>`, sidebar/nav).
- Endpoint ekspor/unduh (Excel/Word) — dipastikan tidak mengembalikan
  body kosong secara diam-diam.

**Hasil**: **0 masalah** dari 81 rute. 9 peringatan awal — semuanya
diverifikasi wajar setelah diperiksa manual (mis. `404` untuk ID dokumen
uji yang memang belum ada file fisiknya di disk, `/login` memang tidak
punya sidebar karena belum login).

*(Catatan proses: percobaan pertama sempat melaporkan puluhan "redirect
ke /login" — setelah ditelusuri, ini murni bug di skrip crawler saya
sendiri, bukan aplikasi: `/logout` ikut ter-crawl secara alfabetis di
tengah proses dan menghapus sesi test client, sehingga semua rute
sesudahnya ikut redirect. Setelah `/logout` diuji terpisah di akhir,
seluruh 81 rute lain kembali bersih.)*

---

## 2. Validitas struktur HTML — apakah ada layout yang "berantakan"?

52 halaman HTML hasil render (dari 81 rute, sisanya respons file
binary/redirect) diuraikan dengan parser HTML untuk mendeteksi:
- Tag tidak seimbang (pembuka tanpa penutup, atau sebaliknya) — penyebab
  paling umum layout "berantakan"/elemen keluar dari kontainer.
- `id` HTML duplikat dalam 1 halaman (bisa merusak JS yang menarget id
  tertentu, atau CSS yang tidak konsisten).

**Hasil**: 1 flag awal (`pengaturan/pejabat.html`, tag `<option>` di
dalam `<datalist>` tanpa `</option>` eksplisit) — diverifikasi **bukan
bug**: itu justru HTML5 valid (elemen `<option>` termasuk kategori
*optional end tag*, browser menutupnya otomatis; keterbatasan parser
sederhana yang saya pakai, bukan masalah di kode aplikasi). Selain itu:
**0 tag tak seimbang, 0 id duplikat** di seluruh 52 halaman.

---

## 3. Konsistensi komponen UI lintas modul

| Komponen | Cara verifikasi | Hasil |
|---|---|---|
| Pewarisan layout | Semua template modul wajib `{% extends "base.html" %}` | ✅ 57/57 (pengecualian yang wajar: `base.html` sendiri, `login.html` yang sengaja berdiri sendiri karena belum ada sesi, 2 file partial/macro `_icons.html` & `_tahap_filter.html`) |
| Header halaman | Pola `<div class="eyebrow">...</div><div class="page-head">...</div>` | ✅ 57/57 template modul memakainya secara konsisten |
| Tombol | Kelas `btn-primary` / `btn-outline` (+ modifier `btn-block`) | ✅ Tidak ada varian penamaan lain (bukan `.button`, `.btn-secondary`, dst yang tidak konsisten) |
| Kartu/panel | Kelas `card` / `card-sub` | ✅ Dipakai 313× secara konsisten, tanpa varian nyeleneh |
| Badge status | Kelas `badge` + modifier `ok`/`warn`/`danger` | ✅ Pola sama dipakai di 15+ file berbeda (kelulusan, mutu, RPL, SDM, dst) |
| Pesan flash | 1 titik implementasi (`base.html`), direplikasi identik di `login.html` (karena berdiri sendiri) | ✅ Tidak ada implementasi flash ganda/berbeda di tempat lain |
| Kelas CSS dipakai vs terdefinisi | Bandingkan setiap `class="..."` di 61 template terhadap `style.css` | ✅ 2 kandidat awal (`btn-label`, `flash-`) — keduanya diverifikasi bukan masalah (`flash-` adalah pola dinamis `flash-ok`/`flash-error` yang memang ada di CSS; `btn-label` adalah `<span>` semantik yang tata letaknya sudah ditangani `display:flex` di elemen induk `.login-submit`, tidak butuh gaya sendiri) |
| Viewport responsif | Meta tag `viewport` di setiap halaman mandiri | ✅ Ada & identik di `base.html` maupun `login.html` |
| Sidebar/navigasi | `test_sidebar.py` (sudah ada, 26 pemeriksaan) | ✅ Lulus — semua modul tercantum, grup collapsible konsisten, tidak ada slug roadmap basi yang nyasar |
| Template yatim (dibuat tapi tak terpakai) | Bandingkan seluruh file `.html` vs referensi `render_template`/`include`/`extends`/`import` di source | ✅ 0 ditemukan — tiap 1 dari 61 file template benar-benar dipakai |

---

## Ringkasan akhir

- **81 rute GET** dicrawl dengan data uji nyata di hampir seluruh tabel
  utama → **0 bug fungsional** (tidak ada 500, tidak ada traceback bocor,
  tidak ada halaman kosong/rusak).
- **52 halaman HTML** diuraikan strukturnya → **0 tag tak seimbang, 0 id
  duplikat** → tidak ada indikasi layout pecah/berantakan.
- **Konsistensi UI/UX**: pola header, tombol, kartu, badge, flash
  message, dan pewarisan layout **seragam 100%** di seluruh 31 modul —
  tidak ditemukan modul yang "menyimpang" gaya dari yang lain.
- **0 template yatim**, viewport responsif konsisten di semua halaman
  mandiri.
- **Tidak ada perubahan kode** pada audit ini (murni verifikasi) — 30
  file test yang sudah ada tetap lulus 100% tanpa modifikasi apa pun.

**Kesimpulan**: dari sisi UI/UX & fungsionalitas end-to-end, tidak
ditemukan celah maupun inkonsistensi. Source code (identik dengan yang
sudah dikirim sebelumnya, `simprodi_rebuilt.zip`) tetap siap diupload ke
GitHub untuk dibuild jadi `.exe`.
