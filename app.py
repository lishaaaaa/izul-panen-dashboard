# app.py
import os
from flask import (
    Flask, jsonify, request, session, redirect, render_template
)

# ===================== Flask App =====================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

APP_USER = os.getenv("APP_USER", "admin")
APP_PASS = os.getenv("APP_PASS", "admin")

def logged_in() -> bool:
    return session.get("auth") is True


# ===================== Pages =====================
@app.get("/")
def home():
    if not logged_in():
        return (
            "<h3>Izul Panen Dashboard</h3>"
            "<p>Login via <code>POST /login</code> (JSON/form {username, password}) "
            "atau buka <a href='/login-page'>/login-page</a>.</p>"
            "<p>Debug: <a href='/health'>/health</a>, "
            "<a href='/test'>/test</a>, "
            "<a href='/diag_env'>/diag_env</a>, "
            "<a href='/diag_sheets'>/diag_sheets</a></p>",
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )
    return redirect("/dashboard", code=302)

# favicon supaya browser nggak memicu 500
@app.get("/favicon.ico")
def favicon():
    return redirect("/vercel.svg", code=307)

@app.get("/login-page")
def login_page():
    return render_template("login.html", title="Login")

@app.get("/dashboard")
def dashboard():
    if not logged_in():
        return render_template("login.html", title="Login"), 401
    return render_template("dashboard.html", title="Dashboard")


# ===================== Auth =====================
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


# ===================== Health / Diag =====================
@app.get("/health")
def health():
    return "ok", 200

@app.get("/test")
def test_alive():
    return "alive", 200

@app.get("/diag_env")
def diag_env():
    keys = [
        "SHEET_ID", "SHEET_TAB", "COL_TANGGAL", "COL_SEKSI",
        "DATE_ORDER", "GOOGLE_APPLICATION_CREDENTIALS"
    ]
    out = {}
    for k in keys:
        v = os.getenv(k, "")
        out[k] = v if len(v) <= 140 else (v[:60] + "..." + v[-20:])
    return jsonify(out), 200

@app.get("/diag_sheets")
def diag_sheets():
    try:
        # lazy import → kalau ENV salah, halaman lain tetap hidup
        from sheets_io import _client, SHEET_ID
        gc = _client()
        sh = gc.open_by_key(SHEET_ID)
        titles = [ws.title for ws in sh.worksheets()]
        return jsonify({"ok": True, "spreadsheet_title": sh.title, "worksheets": titles}), 200
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ===================== API (dipakai dashboard) =====================
@app.get("/api/dates")
def api_dates():
    try:
        from sheets_io import list_dates_str
        return jsonify({"ok": True, "dates": list_dates_str()}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/api/by-date")
def api_by_date():
    try:
        from sheets_io import rows_by_date_str, totals_per_seksi
        date_str = (request.args.get("date") or "").strip()
        rows = rows_by_date_str(date_str)
        totals, grand = totals_per_seksi(rows)
        return jsonify({"ok": True, "rows": rows, "totals": totals, "grand": grand}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/api/series/section")
def api_series_section():
    try:
        from sheets_io import series_for_section
        seksi = (request.args.get("seksi") or "").strip()
        end_date = (request.args.get("end") or "").strip()
        days = int(request.args.get("days", 7))
        labels, data = series_for_section(seksi, end_date, days)
        return jsonify({"ok": True, "labels": labels, "data": data}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/api/series/month")
def api_series_month():
    try:
        from sheets_io import series_month
        seksi = (request.args.get("seksi") or "").strip()
        year = int(request.args.get("year"))
        month = int(request.args.get("month"))
        labels, data = series_month(seksi, year, month)
        return jsonify({"ok": True, "labels": labels, "data": data}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/api/series/year")
def api_series_year():
    try:
        from sheets_io import series_year
        seksi = (request.args.get("seksi") or "").strip()
        year = int(request.args.get("year"))
        labels, data = series_year(seksi, year)
        return jsonify({"ok": True, "labels": labels, "data": data}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ===================== Run lokal saja =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
