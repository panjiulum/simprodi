# -*- coding: utf-8 -*-
"""
datetools.py — Parsing tanggal & jam yang toleran terhadap format campuran
Indonesia/Inggris ("31 Jan 2026", "05 Mei 2026", "09.00", "13:00").

Dipakai terutama oleh logic.py untuk deteksi bentrok jadwal — tanpa
parsing yang andal, jadwal tidak bisa dibandingkan satu sama lain.
"""

import datetime
import re

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "mei": 5,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "agu": 8,
    "aug": 8,
    "sep": 9,
    "okt": 10,
    "oct": 10,
    "nov": 11,
    "des": 12,
    "dec": 12,
}
MONTHS_ID = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "Mei",
    6: "Jun",
    7: "Jul",
    8: "Agu",
    9: "Sep",
    10: "Okt",
    11: "Nov",
    12: "Des",
}

_DATE_RE = re.compile(r"^\s*(\d{1,2})\s+([A-Za-z]{3,})\.?\s+(\d{4})\s*$")
_DATE_NUM_RE = re.compile(r"^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\s*$")
# Format ISO "YYYY-MM-DD" — ini yang selalu dikirim browser untuk
# <input type="date">. WAJIB dicek terpisah dari _DATE_NUM_RE: pola itu
# mengasumsikan urutan dd/mm/yyyy (gaya Indonesia), jadi kalau dipakai
# untuk "2026-08-15" hasilnya salah tafsir (bahkan gagal total karena
# token pertama 4 digit tidak cocok dengan {1,2} pada _DATE_NUM_RE, lalu
# parse_tanggal diam-diam mengembalikan None). Sebelum perbaikan ini,
# form yang field tanggalnya diisi otomatis dengan nilai ISO (mis. nilai
# default `date.today().isoformat()` di Generator Surat Umum) akan gagal
# di-parse begitu pengguna mengetik ulang tanggal lain dalam format yang
# sama persis dengan contoh yang ditampilkan — dan gagal itu senyap,
# langsung fallback ke tanggal hari ini tanpa pesan error apa pun.
_DATE_ISO_RE = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*$")
_TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})")


def parse_tanggal(s):
    """'31 Jan 2026' / '05 Mei 2026' / '31/01/2026' / '2026-08-15' (ISO,
    format bawaan <input type="date">) -> datetime.date atau None."""
    if not s:
        return None
    if isinstance(s, datetime.date):
        return s
    s = str(s).strip()
    m = _DATE_ISO_RE.match(s)
    if m:
        year, mon, day = m.groups()
        try:
            return datetime.date(int(year), int(mon), int(day))
        except ValueError:
            return None
    m = _DATE_RE.match(s)
    if m:
        day, mon_txt, year = m.groups()
        key = mon_txt[:3].lower()
        mon = MONTHS.get(key)
        if mon:
            try:
                return datetime.date(int(year), mon, int(day))
            except ValueError:
                return None
    m = _DATE_NUM_RE.match(s)
    if m:
        a, b, c = m.groups()
        year = int(c) if len(c) == 4 else 2000 + int(c)
        try:
            return datetime.date(year, int(b), int(a))
        except ValueError:
            return None
    return None


def parse_jam(s):
    """'13.00' / '13:00' / '9:00 WIB' -> datetime.time atau None."""
    if not s:
        return None
    if isinstance(s, datetime.time):
        return s
    s = str(s).strip()
    m = _TIME_RE.match(s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return datetime.time(h, mi)
    return None


def format_tanggal(d):
    if not d:
        return ""
    return f"{d.day:02d} {MONTHS_ID[d.month]} {d.year}"


def normalize_tanggal_text(s):
    """Dipakai saat menyimpan form: kalau bisa diparse, kembalikan bentuk
    baku 'dd MMM yyyy'; kalau tidak, kembalikan teks aslinya apa adanya
    (supaya operator tidak kehilangan data yang formatnya di luar dugaan)."""
    d = parse_tanggal(s)
    return format_tanggal(d) if d else (s or "")


def session_interval(tgl_text, jam_text, durasi_menit):
    """-> (datetime.datetime mulai, datetime.datetime selesai) atau (None, None)
    bila tanggal ATAU jam tidak bisa diparse."""
    d = parse_tanggal(tgl_text)
    t = parse_jam(jam_text)
    if not d or not t:
        return None, None
    start = datetime.datetime.combine(d, t)
    end = start + datetime.timedelta(minutes=durasi_menit)
    return start, end


def overlaps(start1, end1, start2, end2):
    return start1 < end2 and start2 < end1


_ROMAWI_BULAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def bulan_ke_romawi(bulan):
    """1 -> 'I', 7 -> 'VII', dst — dipakai format nomor surat resmi Indonesia
    (mis. 001/ST/IAKS/VIII/2026)."""
    try:
        return _ROMAWI_BULAN[int(bulan)]
    except (IndexError, ValueError, TypeError):
        return ""
