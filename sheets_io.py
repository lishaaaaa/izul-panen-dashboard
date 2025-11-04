# sheets_io.py
import os, time
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from dateutil import parser as dparser
from datetime import datetime, timedelta, date
from calendar import monthrange

load_dotenv()

# ====== KONFIGURASI ENV ======
# Scopes cukup read-only; tambah Drive read-only bila pakai open_by_url
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Path kredensial: di Vercel wajib /tmp; di lokal boleh file biasa
CREDS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "/tmp/service_account.json"
JSON_ENV   = os.getenv("GOOGLE_CREDENTIALS_JSON")

SHEET_ID   = os.getenv("SHEET_ID")
SHEET_TAB  = os.getenv("SHEET_TAB", "Form Responses 1")

# Sumber tanggal & seksi (header persis seperti di sheet)
COL_TANGGAL = os.getenv("COL_TANGGAL", "Hari Tanggal Hari ini")
COL_SEKSI   = os.getenv("COL_SEKSI", "Masukkan Lokasi Seksi yang di Input")

# Urutan tanggal preferensi: MDY / DMY
DATE_ORDER  = (os.getenv("DATE_ORDER", "DMY") or "DMY").upper()

# Worker list: bisa dari ENV "WORKERS=Agus,Bagol,Herman,..."
WORKERS_ENV = [w.strip() for w in (os.getenv("WORKERS", "")).split(",") if w.strip()]
WORKERS = WORKERS_ENV or ["Agus","Bagol","Herman","Keleng","Paeng","Riadi","Supri","Suri","Wagiso"]

# Cache sederhana (biar gak spam Google API)
_cache = {"at": 0, "rows": []}
TTL = int(os.getenv("CACHE_TTL", "30"))  # detik

# ====== SIAPKAN KREDENSIAL (ENV → FILE) ======
if JSON_ENV and not os.path.exists(CREDS_PATH):
    try:
        os.makedirs(os.path.dirname(CREDS_PATH), exist_ok=True)
    except Exception:
        pass
    with open(CREDS_PATH, "w", encoding="utf-8") as f:
        f.write(JSON_ENV)

# ====== UTIL ======
def _client():
    creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    return gspread.authorize(creds)

def _parse_date(v):
    """Parse tanggal robust dengan preferensi DATE_ORDER (MDY/DMY)."""
    if isinstance(v, (datetime, date)):
        return datetime.combine(v, datetime.min.time())

    s = str(v).strip()
    if not s:
        return None

    s_norm = s.replace("-", "/").strip()
    patterns_MDY = ["%m/%d/%Y", "%m/%d/%y"]
    patterns_DMY = ["%d/%m/%Y", "%d/%m/%y"]
    patterns = (patterns_MDY + patterns_DMY) if DATE_ORDER == "MDY" else (patterns_DMY + patterns_MDY)

    for fmt in patterns:
        try:
            dt = datetime.strptime(s_norm, fmt)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception:
            pass

    try:
        dayfirst = (DATE_ORDER != "MDY")
        dt = dparser.parse(s, dayfirst=dayfirst)
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    except Exception:
        return None

def _to_num(v):
    s = str(v).strip()
    if s == "":
        return None
    try:
        return float(s.replace(",", "."))
    except Exception:
        return None

# ====== LOAD SHEET: format wide → long ======
def _rows():
    """
    Baca sheet 'wide' (tiap nama pemanen adalah kolom) → list dict:
    {tanggal(datetime), tanggal_str, seksi, nama, janjang(float)}
    """
    now = time.time()
    if now - _cache["at"] < TTL and _cache["rows"]:
        return _cache["rows"]

    ws = _client().open_by_key(SHEET_ID).worksheet(SHEET_TAB)
    vals = ws.get_all_values()
    if not vals:
        _cache.update(at=now, rows=[])
        return []

    header = [h.strip() for h in vals[0]]
    try:
        i_tgl   = header.index(COL_TANGGAL)
        i_seksi = header.index(COL_SEKSI)
    except ValueError:
        # Kolom penting tidak ditemukan
        _cache.update(at=now, rows=[])
        return []

    # deteksi kolom pekerja berdasarkan daftar WORKERS
    worker_idx = []
    for i, h in enumerate(header):
        hs = h.strip()
        if hs in WORKERS:
            worker_idx.append((i, hs))

    out = []
    for row in vals[1:]:
        if len(row) <= max(i_tgl, i_seksi):
            continue

        tgl_str = row[i_tgl].strip()
        seksi   = row[i_seksi].strip()
        if not tgl_str or not seksi:
            continue

        tgl = _parse_date(tgl_str)
        if not tgl:
            continue

        for i, wname in worker_idx:
            val = row[i].strip() if i < len(row) else ""
            j = _to_num(val)
            if j is None:  # kalau mau anggap kosong=0, ganti ke: j = 0.0
                continue
            out.append({
                "tanggal": tgl,
                "tanggal_str": tgl_str,
                "seksi": seksi,
                "nama": wname,
                "janjang": j
            })

    out.sort(key=lambda x: (x["tanggal"], x["seksi"], x["nama"]))
    _cache.update(at=now, rows=out)
    return out

# ====== API: Harian ======
def list_dates_str():
    """Daftar tanggal unik (string asal sheet) berurutan kronologis."""
    seen = {}
    for r in _rows():
        s = r["tanggal_str"]
        if s not in seen:
            seen[s] = r["tanggal"]
    return [k for k, _ in sorted(seen.items(), key=lambda kv: kv[1])]

def rows_by_date_str(date_str):
    key = str(date_str).strip()
    return [r for r in _rows() if str(r["tanggal_str"]).strip() == key]

def totals_per_seksi(rows):
    tot = {}
    for r in rows:
        tot[r["seksi"]] = tot.get(r["seksi"], 0) + (r["janjang"] or 0)
    grand = sum(tot.values())
    return tot, grand

# ====== API: Rolling window (N hari terakhir) ======
def series_for_section(seksi, end_date, days_window):
    rows = [r for r in _rows() if r["seksi"] == seksi]
    if not rows:
        return [], []
    end_dt = _parse_date(end_date) or max(r["tanggal"] for r in rows)
    start_dt = end_dt - timedelta(days=days_window - 1)

    bucket = {}
    for r in rows:
        if start_dt <= r["tanggal"] <= end_dt:
            k = r["tanggal"].date().isoformat()
            bucket[k] = bucket.get(k, 0) + (r["janjang"] or 0)

    labels, data = [], []
    cur = start_dt
    while cur <= end_dt:
        k = cur.date().isoformat()
        labels.append(k)
        data.append(bucket.get(k, 0))
        cur += timedelta(days=1)
    return labels, data

# ====== API: Dropdown Bulan/Tahun + Seri ======
def list_years():
    return sorted({ r["tanggal"].year for r in _rows() })

def list_months(year=None):
    rs = _rows()
    if year:
        rs = [r for r in rs if r["tanggal"].year == int(year)]
    return sorted({ r["tanggal"].month for r in rs })

def series_month(seksi, year, month):
    y, m = int(year), int(month)
    rs = [r for r in _rows() if r["seksi"]==seksi and r["tanggal"].year==y and r["tanggal"].month==m]
    days = monthrange(y, m)[1]
    bucket = { d:0 for d in range(1, days+1) }
    for r in rs:
        bucket[r["tanggal"].day] += (r["janjang"] or 0)
    labels = [f"{y}-{m:02d}-{d:02d}" for d in range(1, days+1)]
    data   = [bucket[d] for d in range(1, days+1)]
    return labels, data

def series_year(seksi, year):
    y = int(year)
    rs = [r for r in _rows() if r["seksi"]==seksi and r["tanggal"].year==y]
    bucket = { m:0 for m in range(1,13) }
    for r in rs:
        bucket[r["tanggal"].month] += (r["janjang"] or 0)
    labels = [f"{y}-{m:02d}" for m in range(1,13)]
    data   = [bucket[m] for m in range(1,13)]
    return labels, data
