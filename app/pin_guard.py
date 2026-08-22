# -*- coding: utf-8 -*-
"""
pin_guard.py — Gerbang PIN untuk fitur krusial (Restrukturisasi poin 2).

Beberapa menu berdampak besar/berisiko kalau diklik tidak sengaja atau
diakses orang yang kebetulan memegang laptop dalam keadaan sudah login
(mis. Import Data & Restore Backup) diberi lapis proteksi TAMBAHAN di
luar password login: PIN terpisah, wajib dimasukkan sebelum halaman itu
dibuka. Ini bukan pengganti password login, melainkan lapisan kedua
khusus untuk aksi yang berisiko mengubah/menimpa data dalam jumlah besar.

Alur:
1. Route sensitif dipasangi @perlu_pin.
2. Kalau PIN belum pernah diset sama sekali -> arahkan dulu ke halaman
   "Atur PIN" (pengaturan.pin_atur), supaya operator tidak terkunci dari
   fitur yang belum sempat dikonfigurasi.
3. Kalau PIN sudah pernah diset tapi sesi belum diverifikasi (atau masa
   berlaku verifikasi sudah lewat) -> arahkan ke halaman "Verifikasi PIN"
   (pengaturan.pin_verifikasi). Begitu benar, sesi ditandai valid selama
   MASA_BERLAKU_PIN_DETIK supaya operator tidak perlu mengetik ulang PIN
   di setiap klik selama masih dalam 1 sesi kerja yang sama.
"""

import time
from functools import wraps

from flask import current_app, redirect, request, session, url_for

from app import auth_core

# Berapa lama verifikasi PIN dianggap masih berlaku dalam 1 sesi browser,
# sebelum diminta memasukkan PIN lagi.
MASA_BERLAKU_PIN_DETIK = 15 * 60  # 15 menit


def pin_terverifikasi():
    hingga = session.get("pin_ok_hingga", 0)
    return time.time() < hingga


def tandai_pin_terverifikasi():
    session["pin_ok_hingga"] = time.time() + MASA_BERLAKU_PIN_DETIK


def perlu_pin(view_func):
    """Decorator: pasang di route sensitif. Menu yang sudah wajib login
    (lihat gerbang wajib_login() di app/__init__.py) TETAP butuh PIN di
    atasnya kalau dipasangi ini."""

    @wraps(view_func)
    def _wrapped(*args, **kwargs):
        conn = current_app.get_db()
        if not auth_core.has_pin(conn):
            session["pin_tujuan"] = request.url
            return redirect(url_for("pengaturan.pin_atur", wajib=1))
        if not pin_terverifikasi():
            session["pin_tujuan"] = request.url
            return redirect(url_for("pengaturan.pin_verifikasi"))
        return view_func(*args, **kwargs)

    return _wrapped
