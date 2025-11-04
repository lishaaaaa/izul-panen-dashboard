# sheets_io.py
# Util Google Sheets untuk Flask/Vercel

import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

import gspread
from google.oauth2.service_account import Credentials


# =========
# ENV & Kolom
# =========

# ID spreadsheet & nama worksheet
SHEET_ID: str = os.getenv("SHEET_ID", "").strip()
SHEET_TAB: str = os.getenv("SHEET_TAB", "Form Responses 1").strip()

# Nama kolom (boleh dioverride via ENV agar fleksibel)
COL_TANGGAl_DEFAULT = "Hari Tanggal Hari ini"   # catatan: nama kolom sesuai contohmu
COL_SEKSI_DEFAULT   = "Masukkan Lokasi Seksi yang di Input"
COL_NAMA_DEFAULT    = "Nama"
COL_JANJANG_DEFAULT = "Jumlah Janjang"

COL_TANGGAL: str = os.getenv("COL_TANGGAL", COL_TANGGAl_DEFAULT).strip()
COL_SEKSI:   str = os.getenv("COL_SEKSI",   COL_SEKSI_DEFAULT).strip()
COL_NAMA:    str = os.getenv("COL_NAMA",    COL_NAMA_DEFAULT).strip()
COL_JANJANG: str = os.getenv("COL_JANJANG", COL_JANJANG_DEFAULT).strip()

# Path default file kredensial di Vercel (pakai /tmp)
DEFAULT_SA_PATH = "/tmp/service_account.json"

# Scopes standar untuk Sheets & (opsional) Drive readonly
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


# =========
# Kredensial & Client
# =========

def _ensure_creds_file() -> str:
    """
    Pastikan file service account tersedia.
    Skenario yang didukung:
    1) GOOGLE_CREDENTIALS_JSON = string JSON SA → ditulis ke /tmp/service_account.json
    2) GOOGLE_APPLICATION_CREDENTIALS = path ke file JSON yang valid
    """
    # 1) Jika user menaruh JSON string di ENV
    json_env = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if json_env:
        p = Path(DEFAULT_SA_PATH)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            # validasi minimal bisa di-load sebagai JSON
            try:
                obj = json.loads(json_env)
                with p.open("w", encoding="utf-8") as f:
                    json.dump(obj, f)
            except Exception as e:
                raise RuntimeError(f"Gagal parse GOOGLE_CREDENTIALS_JSON: {e}")
        # set juga var standar agar lib google memakainya
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = DEFAULT_SA_PATH
        return DEFAULT_SA_PATH

    # 2) Kalau user sudah set path file
    path_env = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", DEFAULT_SA_PATH).strip()
    if Path(path_env).exists():
        return path_env

    # Tidak ada kredensial yang valid
    raise RuntimeError(
        "Kredensial Google tidak ditemukan. "
        "Set salah satu: GOOGLE_CREDENTIALS_JSON (isi JSON) atau "
        "GOOGLE_APPLICATION_CREDENTIALS (path file)."
    )


def _client() -> gspread.client.Client:
    """Bangun gspread client dengan Service Account."""
    sa_path = _ensure_creds_file()
    creds = Credentials.from_service_account_file(sa_path, scopes=_SCOPES)
    return gspread.authorize(creds)


# =========
# Helper akses Sheet
# =========

def get_sheet():
    """
    Return worksheet (gspread.models.Worksheet) sesuai SHEET_ID & SHEET_TAB.
    """
    if not SHEET_ID:
        raise RuntimeError("SHEET_ID belum di-set di ENV.")
    gc = _client()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(SHEET_TAB)
    return ws


def list_worksheets() -> List[str]:
    """
    Kembalikan daftar nama worksheet di spreadsheet.
    """
    if not SHEET_ID:
        raise RuntimeError("SHEET_ID belum di-set di ENV.")
    gc = _client()
    sh = gc.open_by_key(SHEET_ID)
    return [w.title for w in sh.worksheets()]


def fetch_records() -> List[Dict[str, Any]]:
    """
    Ambil semua baris sebagai list of dict (header = baris pertama).
    Aman untuk read-only dashboard.
    """
    ws = get_sheet()
    return ws.get_all_records()  # type: ignore[no-any-return]


def fetch_rows_values() -> List[List[Any]]:
    """
    Ambil semua nilai mentah (tanpa header dict), untuk kebutuhan tertentu.
    """
    ws = get_sheet()
    return ws.get_all_values()  # type: ignore[no-any-return]


def diag_info() -> Dict[str, Any]:
    """
    Informasi singkat untuk endpoint /diag_sheets
    """
    gc = _client()
    sh = gc.open_by_key(SHEET_ID)
    info = {
        "ok": True,
        "spreadsheet_title": sh.title,
        "worksheets": [w.title for w in sh.worksheets()],
    }
    return info


# Ekspor yang dipakai modul lain
__all__ = [
    # konstanta kolom
    "COL_TANGGAL", "COL_SEKSI", "COL_NAMA", "COL_JANJANG",
    # sheet config
    "SHEET_ID", "SHEET_TAB",
    # utilities
    "_client", "get_sheet", "list_worksheets", "fetch_records",
    "fetch_rows_values", "diag_info",
]
