import os
import json
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, make_response
)

# --- App init & config ---
app = Flask(__name__)

# SECRET_KEY wajib ada untuk session
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

# Cookie aman di Vercel (HTTPS); ketika run lokal, ini tetap aman
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
)

TITLE = "Izul Janjang Dashboard"

# --- ENV bindings (kolom & kredensial) ---
APP_USER = (os.getenv("APP_USER") or "").strip()
APP_PASS = (os.getenv("APP_PASS") or "").strip()

SHEET_ID  = os.getenv("SHEET_ID", "")
SHEET_TAB = os.getenv("SHEET_TAB", "Form Responses 1")

COL_TANGGAL = os.getenv("COL_TANGGAL", "Tanggal")
COL_SEKSI   = os.getenv("COL_SEKSI", "Seksi")
COL_NAMA    = os.getenv("COL_NAMA", "Nama Pemanen")
COL_JANJANG = os.getenv("COL_JANJANG", "Jumlah Janjang")
DATE_ORDER  = (os.getenv("DATE_ORDER") or "dmy").lower()  # "dmy" | "mdy" | "ymd"

# --- Sheets helper (menggunakan modul sheets_io milikmu) ---
# Harus tersedia: get_rows() -> List[Dict]
try:
    from sheets_io import get_rows  # kamu sudah punya file ini
    HAS_SHEETS = True
except Exception as e:
    HAS_SHEETS = False
    _import_err = str(e)
    def get_rows(*args, **kwargs):
        raise RuntimeError("get_rows() belum tersedia: " + _import_err)

# --- Utilities ---
def _parse_date(s: str) -> datetime | None:
    """Parse tanggal dari string sesuai DATE_ORDER env. kembalikan None jika gagal."""
    if not s:
        return None
    s = s.strip()
    fmts = []
    if DATE_ORDER == "dmy":
        fmts = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y"]
    elif DATE_ORDER == "mdy":
        fmts = ["%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%d/%m/%Y"]
    else:  # ymd default
        fmts = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("auth"):
            nxt = request.path if request.method == "GET" else url_for("dashboard")
            return redirect(url_for("login", next=nxt))
        return view(*args, **kwargs)
    return wrapped

# --- Diagnostics ---
@app.route("/health")
def health():
    return {"ok": True, "app": "izul-janjiang-dashboard"}

@app.route("/diag_env")
def diag_env():
    data = {
        "cols": {
            "COL_JANJANG": COL_JANJANG,
            "COL_NAMA": COL_NAMA,
            "COL_SEKSI": COL_SEKSI,
            "COL_TANGGAL": COL_TANGGAL,
        },
        "env": {
            "ADMIN_USER": bool(APP_USER),
            "ADMIN_PASS": bool(APP_PASS),
            "SECRET_KEY": bool(app.secret_key),
        },
        "has_sheets_io": HAS_SHEETS,
        "ok": True
    }
    return jsonify(data)

@app.route("/diag_sheets")
def diag_sheets():
    if not HAS_SHEETS:
        return jsonify({"ok": False, "error": "Fungsi get_rows() tidak tersedia di sheets_io."})

    if not SHEET_ID:
        return jsonify({"ok": False, "error": "ENV SHEET_ID belum diisi."})

    try:
        rows = get_rows(SHEET_ID, SHEET_TAB)
        preview = rows[:3]
        return jsonify({"ok": True, "count": len(rows), "preview": preview})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/test_auth")
def test_auth():
    return {"auth": bool(session.get("auth"))}

# --- Home / Landing ---
@app.route("/")
def index():
    # Halaman landing yang simpel; tombol ke /login & /dashboard biasanya ada di index.html kamu
    # Jika kamu tidak punya index.html, fallback text sederhana:
    try:
        return render_template("index.html", title=TITLE)
    except Exception:
        return (
            f"{TITLE} — Login via /login atau langsung /dashboard bila sudah login. "
            f"Debug: /health, /diag_env, /diag_sheets"
        )

# --- Auth ---
@app.route("/login", methods=["GET", "POST"])
def login():
    # Jika sudah login, langsung ke tujuan
    if session.get("auth"):
        target = request.args.get("next") or url_for("dashboard")
        return redirect(target)

    error = None
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = (request.form.get("password") or "").strip()
        if APP_USER and APP_PASS and u == APP_USER and p == APP_PASS:
            session["auth"] = True
            target = request.args.get("next") or url_for("dashboard")
            return redirect(target)
        else:
            error = "Username atau password salah."

    return render_template("login.html", title=TITLE, error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- Dashboard ---
def _load_all_rows():
    """Ambil seluruh data dari Google Sheets."""
    if not HAS_SHEETS:
        return []
    rows = get_rows(SHEET_ID, SHEET_TAB)
    return rows

def _normalize_rows(rows):
    """Tambahkan kolom tanggal_parsed untuk memudahkan filter."""
    out = []
    for r in rows:
        # Ambil tanggal dari kolom environment
        tgl = r.get(COL_TANGGAL, "") if isinstance(r, dict) else ""
        dt = _parse_date(str(tgl))
        r2 = dict(r)
        r2["_tanggal_parsed"] = dt
        out.append(r2)
    return out

@app.route("/dashboard")
@login_required
def dashboard():
    """
    Dashboard menampilkan data + title.
    Kamu sudah punya 'templates/dashboard.html' — kita hanya kirim title dan data dasar.
    """
    rows = []
    try:
        rows = _normalize_rows(_load_all_rows())
    except Exception as e:
        # Tampilkan template dengan pesan error ringan
        return render_template(
            "dashboard.html",
            title=TITLE,
            error=str(e),
            rows=[],
        )

    # Filter per tanggal (opsional) -> ?date=YYYY-MM-DD
    qdate = request.args.get("date", "").strip()
    if qdate:
        try:
            target = datetime.strptime(qdate, "%Y-%m-%d").date()
            rows = [r for r in rows if r.get("_tanggal_parsed") and r["_tanggal_parsed"].date() == target]
        except ValueError:
            # Abaikan jika format salah
            pass

    # Kirim variabel umum yang aman untuk template-mu
    ctx = {
        "title": TITLE,
        "rows": rows,
        "cols": {
            "tanggal": COL_TANGGAL,
            "seksi": COL_SEKSI,
            "nama": COL_NAMA,
            "janjang": COL_JANJANG,
        },
    }
    return render_template("dashboard.html", **ctx)

# --- Local run ---
if __name__ == "__main__":
    # Jalankan lokal: FLASK_ENV=development python app.py
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
