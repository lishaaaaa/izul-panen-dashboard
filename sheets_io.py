# sheets_io.py
import os, json
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# ===== ENV =====
SHEET_ID   = os.getenv("SHEET_ID", "").strip()
SHEET_TAB  = os.getenv("SHEET_TAB", "").strip() or "Form_Responses 1"
COL_TANGGAL= os.getenv("COL_TANGGAL", "Hari Tanggal Hari ini").strip()

REQ_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# ===== CORE =====
def _client():
    raw = os.getenv("GOOGLE_CREDENTIALS_JSON") or os.getenv("GOOGLE_SERVICE_ACCOUNT") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not raw:
        raise RuntimeError("ENV GOOGLE_CREDENTIALS_JSON tidak ada")
    info = json.loads(raw)
    creds = Credentials.from_service_account_info(info, scopes=REQ_SCOPES)
    gc = gspread.authorize(creds)
    return gc

def _ws():
    if not SHEET_ID:
        raise RuntimeError("ENV SHEET_ID kosong")
    gc = _client()
    sh = gc.open_by_key(SHEET_ID)
    try:
        return sh.worksheet(SHEET_TAB)
    except Exception:
        # fallback: nama tab default Google Form
        return sh.worksheet("Form Responses 1")

def get_rows():
    """Return list of dicts (header -> value), kosongin baris tanpa tanggal."""
    ws = _ws()
    rows = ws.get_all_records(numericise_ignore=["all"])
    out = []
    for r in rows:
        # jaga-jaga key beda kapital/spasi
        keys_norm = {k.strip(): k for k in r.keys()}
        col = keys_norm.get(COL_TANGGAL, None)
        val = r.get(col, "") if col else r.get(COL_TANGGAL, "")
        if str(val).strip():
            out.append(r)
    return out

# ===== Date helpers =====
_FMT_CANDIDATES = ["%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d %m %Y"]

def _try_parse_date(s: str):
    s = str(s).strip()
    for fmt in _FMT_CANDIDATES:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def get_unique_dates():
    """
    Ambil daftar tanggal unik dari kolom COL_TANGGAL.
    Return: list of dict [{label: "10/8/2025", sortkey: date(2025,10,8)}] urut desc.
    """
    rows = get_rows()
    seen = {}
    for r in rows:
        # akses robust untuk kolom tanggal
        val = r.get(COL_TANGGAL)
        if val is None:
            # fallback cari key yang sama persis setelah strip
            k = next((k for k in r.keys() if k.strip() == COL_TANGGAL), None)
            val = r.get(k, "")
        if not str(val).strip():
            continue
        d = _try_parse_date(str(val))
        # simpan label asli agar sama persis dengan isi sheet
        if d:
            seen[str(val).strip()] = d
    items = [{"label": k, "sortkey": v} for k, v in seen.items()]
    items.sort(key=lambda x: x["sortkey"], reverse=True)
    return items

def filter_rows_by_date(date_label: str):
    """Filter baris untuk tanggal exact-match sesuai label di sheet."""
    if not date_label:
        return []
    target = str(date_label).strip()
    out = []
    for r in get_rows():
        val = r.get(COL_TANGGAL)
        if val is None:
            k = next((k for k in r.keys() if k.strip() == COL_TANGGAL), None)
            val = r.get(k, "")
        if str(val).strip() == target:
            out.append(r)
    return out
