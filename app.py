# app.py
import os
from flask import Flask, jsonify, request, session, redirect, url_for

# ====== IMPORT DATA LAYER (dari sheets_io.py) ======
# pastikan sheets_io.py ada fungsi/variabel berikut:
# _client, SHEET_ID, SHEET_TAB,
# list_dates_str, rows_by_date_str, totals_per_seksi,
# list_years, list_months, series_month, series_year, series_for_section
from sheets_io import (
    _client, SHEET_ID, SHEET_TAB,
    list_dates_str, rows_by_date_str, totals_per_seksi,
    list_years, list_months, series_month, series_year, series_for_section
)

# ====== APP & CONFIG ======
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

APP_USER = os.getenv("APP_USER", "admin")
APP_PASS = os.getenv("APP_PASS", "admin")

# ====== AUTH SEDERHANA (SESSION) ======
def logged_in():
    return session.get("auth") is True

@app.post("/login")
def login():
    data = request.get_json(silent=True) or request.form
    u = (data.get("username") or "").strip()
    p = (data.get("password") or "").strip()
    if u == APP_USER and p == APP_PASS:
        session["auth"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Invalid credentials"}), 401

@app.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})

# ====== HALAMAN ROOT (boleh kamu ganti render_template ke dashboard-mu) ======
@app.get("/")
def home():
    if not logged_in():
        # Sederhana: info login (frontend kamu bisa ganti dengan template)
        return (
            "<h3>Izul Panen Dashboard</h3>"
            "<p>POST /login dengan form/json {username, password}, lalu refresh.</p>"
            "<p>Routes data: /api/dates, /api/by-date?date=..., /api/series/section, /api/series/month, /api/series/year</p>",
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )
    return (
        "<h3>Logged in ✅</h3>"
        "<ul>"
        "<li><a href='/health'>/health</a></li>"
        "<li><a href='/test'>/test</a></li>"
        "<li><a href='/diag_env'>/diag_env</a></li>"
        "<li><a href='/diag_sheets'>/diag_sheets</a></li>"
        "<li><a href='/api/dates'>/api/dates</a></li>"
        "</ul>",
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )

# ====== ENDPOINT DIAG (NO.3) – WAJIB UNTUK DEBUG DEPLOY ======
@app.get("/health")
def health():
    return "ok", 200

@app.get("/test")
def test_alive():
    # tidak menyentuh Google Sheets — memastikan fungsi serverless hidup
    return "alive", 200

@app.get("/diag_env")
def diag_env():
    # tampilkan nilai ENV penting (tanpa rahasia)
    keys = [
        "SHEET_ID", "SHEET_TAB", "COL_TANGGAL", "COL_SEKSI",
        "DATE_ORDER", "GOOGLE_APPLICATION_CREDENTIALS"
    ]
    out = {}
    for k in keys:
        v = os.getenv(k, "")
        # batasi panjang biar aman tampil
        out[k] = (v if len(v) <= 140 else (v[:60] + "..." + v[-20:]))
    return jsonify(out), 200

@app.get("/diag_sheets")
def diag_sheets():
    # cek koneksi ke Google Sheets & daftar tabs
    try:
        gc = _client()
        sh = gc.open_by_key(SHEET_ID)
        titles = [ws.title for ws in sh.worksheets()]
        return jsonify({
            "ok": True,
            "spreadsheet_title": sh.title,
            "worksheets": titles
        }), 200
    except Exception as e:
        import traceback
        return jsonify({
            "ok": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500

# ====== API DATA (opsional: dipakai frontend dashboard-mu) ======
@app.get("/api/dates")
def api_dates():
    try:
        return jsonify({"ok": True, "dates": list_dates_str()}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/api/by-date")
def api_by_date():
    date_str = (request.args.get("date") or "").strip()
    try:
        rows = rows_by_date_str(date_str)
        totals, grand = totals_per_seksi(rows)
        return jsonify({"ok": True, "rows": rows, "totals": totals, "grand": grand}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/api/series/section")
def api_series_section():
    seksi = (request.args.get("seksi") or "").strip()
    end_date = (request.args.get("end") or "").strip()
    days = int(request.args.get("days", 7))
    try:
        labels, data = series_for_section(seksi, end_date, days)
        return jsonify({"ok": True, "labels": labels, "data": data}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/api/series/month")
def api_series_month():
    seksi = (request.args.get("seksi") or "").strip()
    year = int(request.args.get("year"))
    month = int(request.args.get("month"))
    try:
        labels, data = series_month(seksi, year, month)
        return jsonify({"ok": True, "labels": labels, "data": data}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/api/series/year")
def api_series_year():
    seksi = (request.args.get("seksi") or "").strip()
    year = int(request.args.get("year"))
    try:
        labels, data = series_year(seksi, year)
        return jsonify({"ok": True, "labels": labels, "data": data}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/api/meta")
def api_meta():
    try:
        years = list_years()
        months_all = {y: list_months(y) for y in years}
        return jsonify({"ok": True, "years": years, "months_by_year": months_all}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ====== RUN LOKAL (Vercel akan abaikan ini) ======
if __name__ == "__main__":
    # Untuk run lokal/dev
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)

