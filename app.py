import os, json
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, make_response
)
from jinja2 import TemplateNotFound

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
)

TITLE = "Izul Janjang Dashboard"

# ---- ENV (login & sheets) ----
APP_USER = (os.getenv("APP_USER") or "").strip()
APP_PASS = (os.getenv("APP_PASS") or "").strip()
DEBUG_KEY = os.getenv("DEBUG_KEY", "")  # opsional, untuk force login testing

SHEET_ID  = os.getenv("SHEET_ID", "")
SHEET_TAB = os.getenv("SHEET_TAB", "Form Responses 1")

COL_TANGGAL = os.getenv("COL_TANGGAL", "Tanggal")
COL_SEKSI   = os.getenv("COL_SEKSI", "Seksi")
COL_NAMA    = os.getenv("COL_NAMA", "Nama Pemanen")
COL_JANJANG = os.getenv("COL_JANJANG", "Jumlah Janjang")
DATE_ORDER  = (os.getenv("DATE_ORDER") or "dmy").lower()

# ---- import sheets_io.get_rows() ----
try:
    from sheets_io import get_rows   # harus ada di repo-mu
    HAS_SHEETS = True
except Exception as e:
    HAS_SHEETS = False
    _import_err = str(e)
    def get_rows(*args, **kwargs):
        raise RuntimeError("get_rows() tidak tersedia: " + _import_err)

# ---- helpers ----
def _parse_date(s: str):
    if not s: return None
    s = str(s).strip()
    fmts = {
        "dmy": ["%d/%m/%Y","%d-%m-%Y","%Y-%m-%d","%m/%d/%Y"],
        "mdy": ["%m/%d/%Y","%m-%d-%Y","%Y-%m-%d","%d/%m/%Y"],
        "ymd": ["%Y-%m-%d","%d/%m/%Y","%m/%d/%Y"],
    }[DATE_ORDER if DATE_ORDER in ("dmy","mdy","ymd") else "dmy"]
    for f in fmts:
        try: return datetime.strptime(s, f)
        except ValueError: pass
    return None

def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not session.get("auth"):
            nxt = request.path if request.method == "GET" else url_for("dashboard")
            return redirect(url_for("login", next=nxt))
        return view(*a, **kw)
    return wrapped

# ---- diagnostics ----
@app.route("/health")
def health(): return {"ok": True, "app": "izul-janjang-dashboard"}

@app.route("/diag_env")
def diag_env():
    return jsonify({
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
    })

@app.route("/diag_sheets")
def diag_sheets():
    if not HAS_SHEETS:
        return jsonify({"ok": False, "error": "get_rows() tidak tersedia di sheets_io"})
    if not SHEET_ID:
        return jsonify({"ok": False, "error": "ENV SHEET_ID belum diisi"})
    try:
        rows = get_rows(SHEET_ID, SHEET_TAB)
        return jsonify({"ok": True, "count": len(rows), "preview": rows[:3]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# ---- landing ----
@app.route("/")
def index():
    try:
        return render_template("index.html", title=TITLE)
    except Exception:
        return f"""{TITLE} — Login via /login atau langsung /dashboard bila sudah login.
Debug: /health, /diag_env, /diag_sheets"""

# ---- auth ----
@app.route("/login", methods=["GET","POST"])
def login():
    if session.get("auth"):
        return redirect(request.args.get("next") or url_for("dashboard"))

    error = None
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = (request.form.get("password") or "").strip()
        next_from_form = (request.form.get("next") or "").strip()
        if APP_USER and APP_PASS and u == APP_USER and p == APP_PASS:
            session["auth"] = True
            return redirect(next_from_form or request.args.get("next") or url_for("dashboard"))
        else:
            error = "Username atau password salah."
    return render_template("login.html", title=TITLE, error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---- optional: paksa login untuk tes (akses: /_debug_login?key=XXX) ----
@app.route("/_debug_login")
def _debug_login():
    key = request.args.get("key","")
    if DEBUG_KEY and key == DEBUG_KEY:
        session["auth"] = True
        return redirect(url_for("dashboard"))
    return "Forbidden", 403

# ---- dashboard ----
def _load_rows():
    if not HAS_SHEETS or not SHEET_ID: return []
    rows = get_rows(SHEET_ID, SHEET_TAB)
    # normalisasi tanggal
    out = []
    for r in rows:
        r2 = dict(r)
        r2["_tanggal_parsed"] = _parse_date(r.get(COL_TANGGAL, ""))
        out.append(r2)
    return out

@app.route("/dashboard")
@login_required
def dashboard():
    rows = []
    try:
        rows = _load_rows()
    except Exception as e:
        # kalau gagal ambil data, tetap render template dengan error
        try:
            return render_template("dashboard.html",
                                   title=TITLE, error=str(e),
                                   rows=[], cols={
                                       "tanggal": COL_TANGGAL,
                                       "seksi": COL_SEKSI,
                                       "nama": COL_NAMA,
                                       "janjang": COL_JANJANG,
                                   })
        except TemplateNotFound:
            # fallback safe view
            return _safe_dashboard([], error=str(e))

    # filter opsional ?date=YYYY-MM-DD
    qdate = (request.args.get("date") or "").strip()
    if qdate:
        try:
            want = datetime.strptime(qdate, "%Y-%m-%d").date()
            rows = [r for r in rows if r["_tanggal_parsed"] and r["_tanggal_parsed"].date() == want]
        except ValueError:
            pass

    # coba render template dashboard milikmu
    try:
        return render_template("dashboard.html",
                               title=TITLE, error=None,
                               rows=rows, cols={
                                   "tanggal": COL_TANGGAL,
                                   "seksi": COL_SEKSI,
                                   "nama": COL_NAMA,
                                   "janjang": COL_JANJANG,
                               })
    except TemplateNotFound:
        # kalau file tidak ada -> fallback aman
        return _safe_dashboard(rows)

def _safe_dashboard(rows, error=None):
    # HTML simple supaya SELALU kebuka
    head = f"<h1 style='margin:10px 0'>{TITLE}</h1>"
    note = f"<p style='color:#b91c1c'>{error}</p>" if error else ""
    table_head = f"""
    <table border="1" cellpadding="6" cellspacing="0">
      <thead><tr>
        <th>{COL_TANGGAL}</th><th>{COL_SEKSI}</th><th>{COL_NAMA}</th><th>{COL_JANJANG}</th>
      </tr></thead><tbody>
    """
    body_rows = []
    for r in rows[:300]:  # batasi tampilan
        body_rows.append(
            f"<tr><td>{r.get(COL_TANGGAL,'')}</td>"
            f"<td>{r.get(COL_SEKSI,'')}</td>"
            f"<td>{r.get(COL_NAMA,'')}</td>"
            f"<td>{r.get(COL_JANJANG,'')}</td></tr>"
        )
    html = head + note + table_head + "".join(body_rows) + "</tbody></table>"
    return html

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
