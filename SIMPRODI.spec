# -*- mode: python ; coding: utf-8 -*-
"""
SIMPRODI.spec — konfigurasi PyInstaller.

Cara pakai (biasanya dijalankan otomatis lewat GitHub Actions, lihat
.github/workflows/build-exe.yml — tapi bisa juga manual):

    pip install -r requirements.txt pyinstaller
    pyinstaller SIMPRODI.spec

Hasil: dist/SIMPRODI.exe (Windows) atau dist/SIMPRODI (Linux/Mac) — 1 file
tunggal (onefile), tidak butuh Python terpasang di komputer target.

Kenapa `datas` mencakup app/templates & app/static: keduanya dibaca lewat
`_resource_path()` di app/__init__.py yang sudah dirancang mengenali
sys._MEIPASS (folder ekstrak sementara PyInstaller) — jadi TIDAK perlu
ubah kode app/ sama sekali, cukup pastikan file-file ini ikut dibundel.
"""
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

datas = [
    ("app/templates", "app/templates"),
    ("app/static", "app/static"),
]
# Ikon Anthropic/logo bawaan aplikasi (kalau ada file yang diunggah user
# lewat halaman Pengaturan > Identitas Institusi) TIDAK perlu dibundel di
# sini — itu tersimpan di folder data user (~/SistemSkripsi), bukan di
# dalam paket .exe.

datas += collect_data_files("webview", subdir="lib")  # aset internal pywebview (mis. edgechromium runtime loader di Windows)

hiddenimports = [
    "webview",
    "webview.platforms.winforms",  # Windows (pythonnet + WinForms)
    "webview.platforms.cocoa",     # macOS
    "webview.platforms.gtk",       # Linux
    "flask_wtf",
    "wtforms",
    "openpyxl",
    "docx",
]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SIMPRODI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # jendela desktop, tanpa konsol hitam di belakangnya
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico" if __import__("os").path.exists("icon.ico") else None,
)
