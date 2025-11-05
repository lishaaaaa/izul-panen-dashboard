# sheets_io.py
# Util Google Sheets untuk Izul Panen Dashboard

import os
import json
import base64
import time
from collections import defaultdict, OrderedDict
from datetime import datetime

import gspread
from google.oauth2 import service_account

# =========================
# Konfigurasi & Konstanta
# =========================

SHEET_ID = os.getenv("SHEET_ID", "").strip()
SHEET_TAB = os.getenv("SHEET_TAB", "Form Responses 1").strip()

# Nama kolom (boleh dioverride ENV)
COL_TANGGAL = os.getenv("COL_TANGGAL", "Tanggal").strip()
COL_SEKSI   = os.getenv("COL_SEKSI", "Seksi").strip()
COL_NAMA    = os.getenv("COL_NAMA", "Nama").strip()
COL_JANJANG = os.getenv("COL_JANJANG", "Janjang").strip()

# TTL cache (detik)
CACHE_TTL = int(os.getenv("CACHE_TTL", "60"))

# Urutan seksi untuk tampilan konsisten
SECTION_ORDER = ["A III", "B III", "C II", "D I"]

# =========================
# Auth & Client
# =========================

def _load_service_account():
    """Muat kredensial service account dari ENV GOOGLE_SERVICE_ACCOUNT_JSON.
       Boleh raw JSON atau Base64 dari raw JSON."""
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise RuntimeError("ENV GOOGLE_SERVICE_ACCOUNT_JSON kosong.")
    # Coba deteksi base64
    txt = raw
    try:
        # Jika base64 valid, decode
        decoded = base64.b64decode(raw).decode("utf-8")
        if decoded.strip().startswith("{"):
            txt = decoded
    except Exception:
        # bukan base64, biarkan raw apa adanya
        pass
    data = json.loads(txt)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = service_account.Credentials.from_service_account_info(data, scopes=scopes)
    return creds

_gclient = None

def _client():
    global _gclient
    if _gclient is None:
        creds = _load_service_account()
        _gclient = gspread.authorize(creds)
    return _gclient

# =========================
# Baca sheet + cache
# =========================

_cache = {
    "rows": None,         # list[dict]
    "fetched_at": 0.0,    # epoch
}

def _open_sheet():
    if not SHEET_ID:
        raise RuntimeError("ENV SHEET_ID belum di-set.")
    gc = _client()
    ss = gc.open_by_key(SHEET_ID)
    return ss.worksheet(SHEET_TAB)

def _safe_int(v):
    try:
        if v is None or str(v).strip() == "":
            return 0
        # hilangkan koma/pemisah ribuan
        s = str(v).replace(",", "").strip()
        return int(round(float(s)))
    except Exception:
        return 0

def _to_iso_date(val):
    """Konversi beragam format tanggal -> 'YYYY-MM-DD' (ISO).
       Kembalikan None bila tidak valid."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None

    # Kalau sudah ISO tanggal
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            d = datetime.strptime(s, "%Y-%m-%d")
            return d.strftime("%Y-%m-%d")
    except Exception:
        pass

    # Coba format umum (Indonesia/Spreadsheet)
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            d = datetime.strptime(s, fmt)
            return d.strftime("%Y-%m-%d")
        except Exception:
            continue

    # Coba parse tanggal Excel-like (yyyy-mm-ddThh:mm:ss)
    try:
        if "T" in s:
            d = datetime.fromisoformat(s)
            return d.strftime("%Y-%m-%d")
    except Exception:
        pass

    return None

def _normalize_section(s):
    if not s:
        return ""
    s = str(s).strip()
    # Samakan capitalisasi sederhana
    # (bisa tambah mapping kalau perlu)
    return s

def _get_rows(force=False):
    """Ambil semua baris dari sheet sebagai list of dict
       dgn key: COL_TANGGAL, COL_SEKSI, COL_NAMA, COL_JANJANG (dinormalisasi).
    """
    now = time.time()
    if (not force) and _cache["rows"] is not None and (now - _cache["fetched_at"] < CACHE_TTL):
        return _cache["rows"]

    ws = _open_sheet()
    values = ws.get_all_values()  # list[list]
    if not values:
        _cache["rows"] = []
        _cache["fetched_at"] = now
        return []

    header = values[0]
    data_rows = values[1:]

    # Buat map header->index (case-insensitive)
    hmap = {h.strip().lower(): i for i, h in enumerate(header)}

    def _col_idx(col_name):
        idx = hmap.get(col_name.strip().lower())
        if idx is None:
            raise RuntimeError(f"Kolom '{col_name}' tidak ditemukan di sheet.")
        return idx

    i_tgl = _col_idx(COL_TANGGAL)
    i_sek = _col_idx(COL_SEKSI)
    i_nam = _col_idx(COL_NAMA)
    i_jjg = _col_idx(COL_JANJANG)

    rows = []
    for r in data_rows:
        # Pastikan panjang aman
        if len(r) <= max(i_tgl, i_sek, i_nam, i_jjg):
            continue
        tgl = _to_iso_date(r[i_tgl])
        sek = _normalize_section(r[i_sek])
        nam = (r[i_nam] or "").strip()
        jjg = _safe_int(r[i_jjg])
        if not tgl:
            continue
        rows.append({
            COL_TANGGAL: tgl,
            COL_SEKSI: sek,
            COL_NAMA: nam,
            COL_JANJANG: jjg,
        })

    _cache["rows"] = rows
    _cache["fetched_at"] = now
    return rows

# =========================
# API yang dipakai app.py
# =========================

def get_all_dates():
    """List tanggal unik (ISO) terurut ascending."""
    rows = _get_rows()
    uniq = sorted({r[COL_TANGGAL] for r in rows})
    return uniq

def get_daily_by_section(date_str):
    """Untuk tanggal terpilih: dict[section] -> list[{nama, janjang}] (urut nama).
       Jika satu nama muncul beberapa baris, jumlahkan."""
    rows = _get_rows()
    by_sec_name = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if r[COL_TANGGAL] != date_str:
            continue
        sec = r[COL_SEKSI] or ""
        name = r[COL_NAMA] or ""
        by_sec_name[sec][name] += _safe_int(r[COL_JANJANG])

    result = {}
    for sec, name_map in by_sec_name.items():
        lst = [{"nama": n, "janjang": v} for n, v in name_map.items()]
        # urut nama lalu janjang desc
        lst.sort(key=lambda x: (x["nama"].lower(), -x["janjang"]))
        result[sec] = lst

    # Pastikan semua seksi ada key:
    for s in SECTION_ORDER:
        result.setdefault(s, [])
    return result

def get_totals_for_date(date_str):
    """Total hari itu & total per seksi."""
    rows = _get_rows()
    total_day = 0
    per_section = defaultdict(int)
    for r in rows:
        if r[COL_TANGGAL] != date_str:
            continue
        jjg = _safe_int(r[COL_JANJANG])
        total_day += jjg
        per_section[r[COL_SEKSI]] += jjg

    # Pastikan semua seksi ada, urut rapi
    ordered = OrderedDict()
    for s in SECTION_ORDER:
        ordered[s] = per_section.get(s, 0)

    return {"total_day": total_day, "per_section": ordered}

def get_monthly_series(section, year, month):
    """Data harian untuk grafik bulanan: list[{date:'YYYY-MM-DD', janjang:int}]"""
    rows = _get_rows()
    series = defaultdict(int)  # date -> total
    for r in rows:
        if (r[COL_SEKSI] != section):
            continue
        d = datetime.strptime(r[COL_TANGGAL], "%Y-%m-%d")
        if d.year == year and d.month == month:
            series[r[COL_TANGGAL]] += _safe_int(r[COL_JANJANG])

    # urut tanggal
    out = [{"date": k, "janjang": series[k]} for k in sorted(series.keys())]
    return out

def get_yearly_series(section, year):
    """Data bulanan untuk grafik tahunan: list[{month:'YYYY-MM', janjang:int}]"""
    rows = _get_rows()
    series = defaultdict(int)  # YYYY-MM -> total
    for r in rows:
        if (r[COL_SEKSI] != section):
            continue
        d = datetime.strptime(r[COL_TANGGAL], "%Y-%m-%d")
        if d.year == year:
            key = f"{d.year:04d}-{d.month:02d}"
            series[key] += _safe_int(r[COL_JANJANG])

    # urut month key
    out = [{"month": k, "janjang": series[k]} for k in sorted(series.keys())]
    return out

# =========================
# Optional: modul-scope test
# =========================
if __name__ == "__main__":
    # Tes cepat lokal (butuh ENV terpasang)
    print("Dates:", get_all_dates()[:5])
    if get_all_dates():
        d = get_all_dates()[-1]
        print("Selected date:", d)
        print("Totals:", get_totals_for_date(d))
        print("Daily by section (sample C II):", get_daily_by_section(d).get("C II", [])[:5])
        y = datetime.now().year
        m = datetime.now().month
        print("Monthly C II:", get_monthly_series("C II", y, m)[:5])
        print("Yearly C II:", get_yearly_series("C II", y)[:5])
