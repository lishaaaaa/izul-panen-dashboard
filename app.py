import os, json, traceback
from datetime import timedelta
from flask import Flask, request, session, redirect, url_for, render_template, jsonify, send_from_directory, abort

# ===== Flask App =====
app = Flask(__name__, static_folder="static", template_folder="templates")

# SECRET_KEY & Session
app.secret_key = os.getenv("SECRET_KEY", "devsecret")
app.permanent_session_lifetime = timedelta(hours=12)

# Kredensial login (dari ENV)
APP_USER = os.getenv("APP_USER", "admin")
APP_PASS = os.getenv("APP_PASS", "dedi123")

# ====== Sheets helper ======
# Pastikan sheets_io.py mengekspor nama-nama di bawah ini
try:
    from sheets_io import (
        _client, SHEET_ID, SHEET_TAB,
        COL_TANGGAL, COL_NAMA, COL_SEKSI, COL_JANJANG
    )
except Exception as e:
    # Biar /diag_sheets tetap bisa kasih jejak error waktu import gagal
    _IMPORT_ERR = e
else:
    _IMPORT_ERR = None


# ---------- Utils ----------
def login_required(fn):
    def _wrap(*args, **kwargs):
        if not session.get("auth"):
            return abort(401)
        return fn(*args, **kwargs)
    _wrap.__name__ = fn.__name__
    return _wrap


# ---------- Home ----------
@app.get("/")
def home():
    return """
    <h3>Izul Panen Dashboard</h3>
    <p><a href="/login">Login</a> · <a href="/dashboard">Dashboard</a></p>
    <p>Debug:
      <a href="/health">/health</a>,
      <a href="/test">/test</a>,
      <a href="/diag_env">/diag_env</a>,
      <a href="/diag_sheets">/diag_sheets</a>
    </p>
    """, 200


# ---------- Auth ----------
@app.get("/login")
def login_form():
    return """
    <h3>Login</h3>
    <form method="post" action="/login">
      <label>Username</label><br/>
      <input name="username" autocomplete="username"/><br/><br/>
      <label>Password</label><br/>
      <input name="password" type="password" autocomplete="current-password"/><br/><br/>
      <button type="submit">Masuk</button>
    </form>
    """, 200


@app.post("/login")
def login_post():
    # Terima form atau JSON
    user = request.form.get("username") if request.form else None
    pwd  = request.form.get("password") if request.form else None
    if request.is_json:
        j = request.get_json(silent=True) or {}
        user = j.get("username", user)
        pwd  = j.get("password", pwd)

    if user == APP_USER and pwd == APP_PASS:
        session.permanent = True
        session["auth"] = True
        return redirect("/dashboard")
    return ("Unauthorized", 401)


@app.post("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------- Pages ----------
@app.get("/dashboard")
@login_required
def dashboard_page():
    """
    Render template 'dashboard.html'.
    - Pastikan file ada di folder /templates/dashboard.html
    - Static JS/CSS di /static/...
    """
    try:
        return render_template("dashboard.html",
                               title="Dashboard Izul Janjang",
                               COL_TANGGAL=COL_TANGGAL,
                               COL_SEKSI=COL_SEKSI,
                               COL_NAMA=COL_NAMA,
                               COL_JANJANG=COL_JANJANG)
    except Exception:
        # Fallback kalau belum ada templatenya: kirim file statis kalau kamu menyimpan HTML di /static
        index_static = os.path.join(app.static_folder or "static", "dashboard.html")
        if os.path.exists(index_static):
            return send_from_directory(app.static_folder, "dashboard.html")
        return ("Template 'dashboard.html' tidak ditemukan.", 500)


# ---------- Diagnostics ----------
@app.get("/health")
def health():
    return "ok", 200


@app.get("/test")
def test_alive():
    return "alive", 200


@app.get("/diag_env")
def diag_env():
    # Tampilkan env non-sensitif yang dipakai aplikasi
    env_ok = {
        "SHEET_ID": os.getenv("SHEET_ID"),
        "SHEET_TAB": os.getenv("SHEET_TAB"),
        "COL_TANGGAL": os.getenv("COL_TANGGAL"),
        "COL_SEKSI": os.getenv("COL_SEKSI"),
        "COL_NAMA": os.getenv("COL_NAMA"),
        "COL_JANJANG": os.getenv("COL_JANJANG"),
        "DATE_ORDER": os.getenv("DATE_ORDER"),
        "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
    }
    return (json.dumps(env_ok), 200, {"Content-Type": "application/json"})


@app.get("/diag_sheets")
def diag_sheets():
    # Kasus import error dari sheets_io
    if _IMPORT_ERR is not None:
        return jsonify({
            "ok": False,
            "error": f"ImportError: {str(_IMPORT_ERR)}",
            "trace": traceback.format_exc()
        }), 500
    try:
        gc = _client()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(SHEET_TAB)
        info = {
            "ok": True,
            "spreadsheet_title": sh.title,
            "worksheets": [w.title for w in sh.worksheets()],
            "worksheet_title": ws.title,
            "rows": ws.row_count,
            "cols": ws.col_count,
        }
        return jsonify(info), 200
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "trace": traceback.format_exc(),
        }), 500


# ---------- Static helper (optional) ----------
@app.get("/static/<path:fname>")
def _static(fname):
    return send_from_directory(app.static_folder, fname)


# ---------- Local run ----------
if __name__ == "__main__":
    # Jalankan lokal untuk debug
    app.run(debug=True)
