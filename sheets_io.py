# sheets_io.py
# --------------------------------------------
# Util baca Google Sheets untuk Izul Janjang Dashboard
# Memerlukan ENV:
# - SHEET_ID                -> ID Google Sheet
# - SHEET_TAB               -> Nama worksheet (tab), mis. "Form Responses 1"
# - GOOGLE_SERVICE_ACCOUNT  -> JSON string service account (direkomendasikan)
#   ATAU GOOGLE_SERVICE_ACCOUNT_JSON -> alias kalau variabel di atas beda nama
#
# Output utama:
# - get_rows() -> list[dict] dengan kunci sesuai kolom yang dipakai app
# --------------------------------------------

import json
import os
from typing import List, Dict, Any, Optional

import gspread
from google.oauth2.service_account import Credentials

# ==== Konstanta kolom yang dipakai app (samakan dgn header di Sheet Anda) ====
COL_TANGGAL = "Tanggal"
COL_SEKSI   = "Seksi"
COL_NAMA    = "Nama Pemanen"
COL_JANJANG = "Jumlah Janjang"

# Ekspor juga biar bisa di-import di app.py
__all__ = [
    "COL_TANGGAL", "COL_SEKSI", "COL_NAMA", "COL_JANJANG",
    "get_rows"
]

# ==== Helper auth & worksheet ====

def _service_account_info() -> Dict[str, Any]:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("ENV GOOGLE_SERVICE_ACCOUNT (JSON) tidak ditemukan.")
    try:
        return json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"GOOGLE_SERVICE_ACCOUNT bukan JSON valid: {e}")

def _client():
    info = _service_account_info()
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)

def _worksheet():
    sheet_id = os.getenv("SHEET_ID")
    sheet_tab = os.getenv("SHEET_TAB")
    if not sheet_id:
        raise RuntimeError("ENV SHEET_ID tidak di-set.")
    if not sheet_tab:
        raise RuntimeError("ENV SHEET_TAB tidak di-set.")
    gc = _client()
    sh = gc.open_by_key(sheet_id)
    return sh.worksheet(sheet_tab)

# ==== Fungsi utama yang dibutuhkan app ====

def get_rows() -> List[Dict[str, Any]]:
    """
    Mengembalikan semua baris sebagai list of dict.
    Dict kunci-nya berasal dari header baris pertama di worksheet.
    Wajib ada kolom: COL_TANGGAL, COL_SEKSI, COL_NAMA, COL_JANJANG.
    """
    ws = _worksheet()

    # Gunakan get_all_records untuk langsung dapat list[dict]
    records: List[Dict[str, Any]] = ws.get_all_records()

    # Normalisasi kunci jika ada spasi/variasi (opsional tapi membantu)
    def norm_key(k: str) -> str:
        return (k or "").strip()

    normalized: List[Dict[str, Any]] = []
    for rec in records:
        rec2 = {norm_key(k): v for k, v in rec.items()}
        # pastikan kunci minimal ada; kalau tidak, tetap masukkan biar bisa dilihat di diag
        normalized.append(rec2)

    return normalized

# ====== (Opsional) util cepat untuk diag ======

def sheet_meta() -> Dict[str, Any]:
    """Info ringan untuk endpoint /diag_sheets."""
    try:
        ws = _worksheet()
        headers = ws.row_values(1)
        return {
            "ok": True,
            "sheet_id": os.getenv("SHEET_ID"),
            "sheet_tab": os.getenv("SHEET_TAB"),
            "headers": headers,
            "rows_count": ws.row_count,
            "cols_count": ws.col_count,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
