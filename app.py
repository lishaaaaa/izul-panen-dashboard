import os
from datetime import datetime
from collections import defaultdict

from flask import (
    Flask, request, jsonify, render_template, redirect,
    url_for, session
)

# --- Flask base ---
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", "dev")

APP_USER = os.getenv("APP_USER", "admin")
APP_PASS = os.getenv("APP_PASS", "dedi123")

# ---- helpers: lazy import (hindari crash saat module import) ----
def _sheets_mod():
    """
    Import sheets_io hanya saat dipakai supaya kalau kredensial/Sheets error,
    halaman lain tidak 500. Semua error dibungkus di route.
    """
    from sheets_io import (
        _client, SHEET_ID, SHEET_TAB,
        COL_TANGGAL, COL_SEKSI, COL_NAMA, COL_JANJANG
    )
    import gspread
    return _client, SHEET_ID, SHEET_TAB, COL_TANGGAL, COL_SEKSI, COL_NAMA, COL_JANJANG, gspread

def _env_small():
    allow = ["SHEET_ID", "SHEET_TAB", "GOOGLE_APPLICATION_CREDENTIALS",
             "COL_TANGGAL", "COL_SEKSI", "COL_NAMA", "COL_JANJANG", "DATE_ORDER"]
    return {k: os.getenv(k) for k in allow if os.getenv(k) is not None}

def _login_required():
    return session.get("auth_ok") is True

# ---------- BASIC / DIAG ----------
@app.get("/health")
def health():
    return "ok", 200

@app.get("/test")
def test_alive():
    return "alive", 200

@app.get("/")
def home():
    # landing super ringan
    return (
        "Izul Panen Dashboard<br>"
        "Login via <code>POST /login</code> (username, password).<br>"
        'Debug: <a href="/health">/health</a>, '
        '<a href="/test">/test</a>, '
        '<a href="/diag_env">/diag_env</a>, '
        '<a href="/diag_sheets">/diag_sheets</a>',
        200,
    )

@app.get("/diag_env")
def diag_env():
    try:
        return jsonify(_env_small()), 200
    except Exception as e:
        app.logger.exception("diag_env")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/diag_sheets")
def diag_sheets():
    """
    Cek koneksi & worksheet. Tidak akan crash app; kalau error, dikembalikan sebagai JSON.
    """
    try:
        _client, SHEET_ID, SHEET_TAB, *_ = _sheets_mod()
        gc = _client()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(SHEET_TAB)
        info = {
            "ok": True,
            "spreadsheet_title": sh.title,
            "worksheets": [w.title for w in sh.worksheets()],
            "rows": ws.row_count,
            "cols": ws.col_count,
        }
        return jsonify(info), 200
    except Exception as e:
        import traceback
        app.logger.exception("diag_sheets failed")
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500

# ---------- AUTH ----------
@app.post("/login")
def login():
    u = request.form.get("username") or (request.is_json and request.json.get("username"))
    p = request.form.get("password") or (request.is_json and request.json.get("password"))
    if u == APP_USER and p == APP_PASS:
        session["auth_ok"] = True
        return jsonify({"ok": True, "redirect": url_for("dashboard")})
    return jsonify({"ok": False, "error": "Invalid credentials"}), 401

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

# ---------- UTIL DATA ----------
def _parse_date_str(s):
    # biar fleksibel: 2025-10-08 atau 10/08/2025
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def _read_all_rows():
    """
    Ambil semua rows dari worksheet sebagai list of dict.
    Tak dianggap fatal: kalau error, raise ke pemanggil lalu ditangani try/except route.
    """
    _client, SHEET_ID, SHEET_TAB, COL_TANGGAL, COL_SEKSI, COL_NAMA, COL_JANJANG, _ = _sheets_mod()
    gc = _client()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(SHEET_TAB)
    recs = ws.get_all_records()  # list[dict]
    return recs, (COL_TANGGAL, COL_SEKSI, COL_NAMA, COL_JANJANG)

def _filter_rows_by_date(recs, col_tanggal, target_date):
    out = []
    for r in recs:
        val = str(r.get(col_tanggal, "")).strip()
        d = _parse_date_str(val)
        if d and d == target_date:
            out.append(r)
    return out

def _totals_by_seksi(recs, col_seksi, col_janjang):
    total = defaultdict(int)
    for r in recs:
        seksi = str(r.get(col_seksi, "")).strip()
        try:
            jj = int(str(r.get(col_janjang, "0")).replace(".", "").replace(",", ""))
        except Exception:
            jj = 0
        total[seksi] += jj
    return dict(total)

def _table_by_seksi(recs, col_seksi, col_nama, col_janjang):
    """
    { "A III": [{"nama":..., "janjang":...}, ...], ... }, plus total per seksi
    """
    tables = defaultdict(list)
    totals = defaultdict(int)
    for r in recs:
        seksi = str(r.get(col_seksi, "")).strip()
        nama = str(r.get(col_nama, "")).strip()
        try:
            jj = int(str(r.get(col_janjang, "0")).replace(".", "").replace(",", ""))
        except Exception:
            jj = 0
        tables[seksi].append({"nama": nama, "janjang": jj})
        totals[seksi] += jj
    # urutkan nama biar stabil
    for s in tables:
        tables[s].sort(key=lambda x: x["nama"])
    return dict(tables), dict(totals)

def _series_month_and_year(recs, col_seksi, col_tanggal, col_janjang, month, year_bulanan, year_tahunan):
    """
    Bangun seri (per hari untuk bulan, per bulan untuk tahun) untuk masing2 seksi.
    Output:
      {
        "A III": {
           "bulanan": [{"x": "2025-10-01", "y": 12}, ...],
           "tahunan": [{"x": "2025-01", "y": 123}, ...]
        }, ...
      }
    """
    # kumpulkan date & seksi
    bulanan = defaultdict(lambda: defaultdict(int))   # seksi -> date -> total
    tahunan = defaultdict(lambda: defaultdict(int))   # seksi -> ym   -> total
    for r in recs:
        d = _parse_date_str(str(r.get(col_tanggal, "")).strip())
        if not d:
            continue
        seksi = str(r.get(col_seksi, "")).strip()
        try:
            jj = int(str(r.get(col_janjang, "0")).replace(".", "").replace(",", ""))
        except Exception:
            jj = 0

        # bulanan
        if d.month == month and d.year == year_bulanan:
            bulanan[seksi][d.isoformat()] += jj
        # tahunan
        if d.year == year_tahunan:
            ym = f"{d.year:04d}-{d.month:02d}"
            tahunan[seksi][ym] += jj

    def to_xy(dmap, sort_key):
        return [{"x": k, "y": dmap[k]} for k in sorted(dmap.keys(), key=sort_key)]

    out = {}
    all_seksi = set(list(bulanan.keys()) + list(tahunan.keys()))
    for s in all_seksi:
        out[s] = {
            "bulanan": to_xy(bulanan[s], sort_key=lambda x: x),
            "tahunan": to_xy(tahunan[s], sort_key=lambda x: x),
        }
    return out

# ---------- DASHBOARD HTML ----------
@app.get("/dashboard")
def dashboard():
    if not _login_required():
        return redirect(url_for("home"))

    # ambil tanggal dari query (?date=YYYY-MM-DD) atau default: hari ini di data (jika ada)
    qdate = request.args.get("date")
    try:
        recs, (COL_TANGGAL, COL_SEKSI, COL_NAMA, COL_JANJANG) = _read_all_rows()
        target_date = _parse_date_str(qdate) if qdate else None

        # kalau tidak diberi query, pakai tanggal terbaru yang ada di sheet
        if not target_date:
            dates = []
            for r in recs:
                d = _parse_date_str(str(r.get(COL_TANGGAL, "")).strip())
                if d:
                    dates.append(d)
            target_date = max(dates) if dates else None

        rows_today = _filter_rows_by_date(recs, COL_TANGGAL, target_date) if target_date else []
        total_hari_ini = sum(
            int(str(r.get(COL_JANJANG, "0")).replace(".", "").replace(",", "")) or 0
            for r in rows_today
        )
        seksi_totals_today = _totals_by_seksi(rows_today, COL_SEKSI, COL_JANJANG)
        tabel_data, tabel_totals = _table_by_seksi(rows_today, COL_SEKSI, COL_NAMA, COL_JANJANG)

        # default control grafik
        now = datetime.now()
        chart_opts = {
            "month": now.month,
            "yearBulanan": now.year,
            "yearTahunan": now.year,
        }

        return render_template(
            "dashboard.html",
            title="Dashboard Izul Janjang",
            date_display=target_date.isoformat() if target_date else "-",
            total_hari_ini=total_hari_ini,
            seksi_totals=seksi_totals_today,
            tabel_data=tabel_data,
            tabel_totals=tabel_totals,
            chart_opts=chart_opts,
        ), 200

    except Exception as e:
        app.logger.exception("dashboard render failed")
        # Jangan 500: render halaman minimal supaya user bisa lihat pesan
        return render_template(
            "dashboard.html",
            title="Dashboard Izul Janjang",
            ui_error=str(e),
            date_display="-",
            total_hari_ini=0,
            seksi_totals={},
            tabel_data={},
            tabel_totals={},
            chart_opts={"month": 1, "yearBulanan": 2025, "yearTahunan": 2025},
        ), 200

# ---------- DATA API UTK GRAFIK ----------
@app.get("/api/series")
def api_series():
    if not _login_required():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    try:
        month = int(request.args.get("month", 1))
        year_b = int(request.args.get("yearBulanan", datetime.now().year))
        year_t = int(request.args.get("yearTahunan", datetime.now().year))

        recs, (COL_TANGGAL, COL_SEKSI, COL_NAMA, COL_JANJANG) = _read_all_rows()
        data = _series_month_and_year(
            recs, COL_SEKSI, COL_TANGGAL, COL_JANJANG, month, year_b, year_t
        )
        return jsonify({"ok": True, "data": data}), 200
    except Exception as e:
        app.logger.exception("api_series failed")
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------- MAIN (local run only) ----------
if __name__ == "__main__":
    app.run(debug=True)
