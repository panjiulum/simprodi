# -*- coding: utf-8 -*-
"""
run.py — Titik masuk (entry point) aplikasi SIMPRODI.

File ini SENGAJA dipisah dari `app/` (application factory Flask) supaya:
1. `app/` tetap murni jadi package Flask yang bisa diuji langsung lewat
   `create_app()` (dipakai semua file test_*.py di root project) tanpa
   ikut membuka jendela GUI atau server sungguhan.
2. PyInstaller (lihat SIMPRODI.spec) tinggal menunjuk 1 file ini sebagai
   titik masuk untuk dibungkus jadi .exe.

Dua mode menjalankan:
- Mode NORMAL (default, dipakai user akhir) — server Flask dijalankan di
  thread latar belakang pada port lokal bebas, lalu dibuka di jendela
  aplikasi native (pywebview) — TIDAK butuh browser terpisah, terasa
  seperti aplikasi desktop biasa.
- Mode `--web` — server dijalankan seperti web app biasa (bisa diakses
  dari browser manapun di jaringan lokal via --host/--port), tanpa
  jendela pywebview. Berguna untuk debugging atau kalau pywebview tidak
  tersedia/gagal di sistem operasi tertentu.

Database & lokasi file lain TIDAK dipengaruhi oleh mode ini — keduanya
memakai `db.get_default_db_path()` yang sama persis (folder
~/SistemSkripsi/data_prodi.db), sesuai catatan di app/db.py.
"""
import argparse
import socket
import sys
import threading
import webbrowser

from app import create_app


def _cari_port_bebas(preferred=5000):
    """Coba port pilihan dulu; kalau sudah dipakai proses lain, minta OS
    pilihkan port bebas apa saja (port 0 -> OS auto-assign)."""
    for port in (preferred, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
        except OSError:
            continue
    raise RuntimeError("Tidak ada port lokal yang bisa dipakai.")


def _jalankan_server(app, host, port):
    """Server bawaan Flask — aman untuk aplikasi offline single-user seperti
    ini (1 proses, 1 pengguna, tanpa beban konkurensi web publik)."""
    app.run(host=host, port=port, threaded=True, use_reloader=False)


def _mode_web(args):
    app = create_app()
    print(f"SIMPRODI berjalan di http://{args.host}:{args.port}  (Ctrl+C untuk berhenti)")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()
    _jalankan_server(app, args.host, args.port)


def _mode_desktop(args):
    """Jendela aplikasi native lewat pywebview — pengalaman standar untuk
    user akhir yang menjalankan file .exe hasil build."""
    import webview

    # WAJIB di-set SEBELUM create_window(): pywebview defaultnya
    # ALLOW_DOWNLOADS = False, artinya SEMUA link unduhan (Content-Disposition:
    # attachment) di seluruh aplikasi — template import, ekspor Excel,
    # unduh surat/dokumen, backup, dst — akan diklik tapi TIDAK TERJADI
    # APA-APA di jendela desktop (tanpa error, tanpa dialog), karena
    # webview diam-diam menolak trigger download-nya. Ini root cause bug
    # "tombol unduh tidak berfungsi" yang hanya muncul di mode desktop
    # (mode --web tidak kena, karena itu browser asli).
    webview.settings["ALLOW_DOWNLOADS"] = True

    app = create_app()
    port = _cari_port_bebas()

    server_thread = threading.Thread(
        target=_jalankan_server, args=(app, "127.0.0.1", port), daemon=True
    )
    server_thread.start()

    webview.create_window(
        "SIMPRODI",
        f"http://127.0.0.1:{port}",
        width=1280,
        height=800,
        min_size=(1024, 640),
    )
    webview.start()


def main():
    parser = argparse.ArgumentParser(description="SIMPRODI — Sistem Informasi Manajemen Prodi")
    parser.add_argument(
        "--web", action="store_true",
        help="Jalankan sebagai web app biasa (diakses via browser), bukan jendela desktop.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Alamat host untuk mode --web.")
    parser.add_argument("--port", type=int, default=5000, help="Port untuk mode --web.")
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Mode --web: jangan buka browser otomatis (server saja).",
    )
    args = parser.parse_args()

    if args.web:
        _mode_web(args)
    else:
        try:
            _mode_desktop(args)
        except ImportError:
            print(
                "pywebview tidak terpasang/tidak didukung di sistem ini — "
                "beralih otomatis ke mode --web.",
                file=sys.stderr,
            )
            args.host, args.port = "127.0.0.1", args.port or 8765
            _mode_web(args)


if __name__ == "__main__":
    main()
