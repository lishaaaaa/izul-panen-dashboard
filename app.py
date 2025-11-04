#App.py
import os, json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import pandas as pd

# ====== ENV ======
APP_USER = os.getenv("APP_USER", "admin")
APP_PASS = os.getenv("APP_PASS", "admin")
COL_TGL   = os.getenv("COL_TANGGAL", "Hari Tanggal Hari ini")
COL_SEKSI = os.getenv("COL_SEKSI", "Masukkan Lokasi Seksi yang di Input")
COL_NAMA  = os.getenv("COL_NAMA", "Nama")
COL_JJG   = os.getenv("COL_JANJANG", "Jumlah Janjang")
DATE_ORDER = os.getenv("DATE_ORDER", "MDY")  # "MDY" atau "DMY"

# ====== SHEETS CLIENT ======
# gunakan modul kamu yang sudah OK kemarin
from sheets_io import _client, SHEET_ID, SHEET_TAB

def _parse_date(s: str) -> datetime.date:
    """
    Parse tanggal dari Google Form sesuai DATE_ORDER.
    Disini kita toleran terhadap '10/8/2025' atau '2025-10-08'.
    """
    s = str(s).strip()
    # ISO first
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # Form style
    if DATE_ORDER.upper() == "DMY":
        return datetime.strptime(s, "%d/%m/%Y").date()
    else:
        return datetime.strptime(s, "%m/%d/%Y").date()  # MDY default

def get_df():
    """
    Ambil data mentah dari sheet lalu normalisasi kolom, tipe, dan hilangkan baris kosong.
    """
    gc = _client()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(SHEET_TAB)
    rows = ws.get_all_records()  # list of dict
    if not rows:
        return pd.DataFrame(columns=[COL_TGL, COL_SEKSI, COL_NAMA, COL_JJG])

    df = pd.DataFrame(rows)

    # Pastikan kolom ada
    for col in [COL_TGL, COL_SEKSI, COL_NAMA, COL_JJG]:
        if col not in df.columns:
            df[col] = None

    # Bersihkan tipe
    df = df[[COL_TGL, COL_SEKSI, COL_NAMA, COL_JJG]].copy()
    df[COL_TGL] = df[COL_TGL].map(_parse_date)
    # angka janjang
    def _to_int(x):
        try:
            if x is None or x == "":
                return 0
            return int(str(x).replace(",", "").strip())
        except:
            try:
                return int(float(x))
            except:
                return 0
    df[COL_JJG] = df[COL_JJG].map(_to_int)

    # normalisasi seksi/nama
    df[COL_SEKSI] = df[COL_SEKSI].fillna("").astype(str).str.strip()
    df[COL_NAMA]  = df[COL_NAMA].fillna("").astype(str).str.strip()

    return df

# ====== FLASK ======
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", "dev")

# ---------- Auth sederhana ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username") or request.json.get("username")
        p = request.form.get("password") or request.json.get("password")
        if u == APP_USER and p == APP_PASS:
            session["auth"] = True
            return redirect(url_for("dashboard"))
        return "Unauthorized", 401
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

def _need_auth():
    return not session.get("auth")

# ---------- Dashboard ----------
def _latest_date(df: pd.DataFrame):
    if df.empty:
        return None
    return df[COL_TGL].max()

def _unique_dates(df: pd.DataFrame):
    return sorted(df[COL_TGL].dropna().unique().tolist())

def _summary_for_date(df: pd.DataFrame, day):
    dfd = df[df[COL_TGL] == day].copy()
    total_harian = int(dfd[COL_JJG].sum()) if not dfd.empty else 0

    # ringkas seksi
    seksi_totals = (
        dfd.groupby(COL_SEKSI)[COL_JJG].sum().to_dict() if not dfd.empty else {}
    )

    # tabel per seksi: list of {nama, janjang}
    tables = {}
    for seksi in sorted(dfd[COL_SEKSI].unique()):
        sub = dfd[dfd[COL_SEKSI] == seksi].groupby(COL_NAMA)[COL_JJG].sum().reset_index()
        sub = sub.sort_values(COL_NAMA, key=lambda s: s.str.lower())
        tables[seksi] = {
            "rows": sub.to_dict(orient="records"),
            "total": int(sub[COL_JJG].sum()) if not sub.empty else 0,
        }
    return total_harian, seksi_totals, tables

@app.route("/")
def root():
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
def dashboard():
    if _need_auth():
        return redirect(url_for("login"))

    df = get_df()
    if df.empty:
        return render_template(
            "dashboard.html",
            title="Dashboard Izul Janjang",
            dates=[],
            selected_date=None,
            total_harian=0,
            seksi_totals={},
            tables={},
            bulan_options=list(range(1,13)),
            tahun_options=[]
        )

    # tanggal dipilih dari query ?date=YYYY-MM-DD, default latest
    qdate = request.args.get("date")
    if qdate:
        try:
            selected = datetime.strptime(qdate, "%Y-%m-%d").date()
        except:
            selected = _latest_date(df)
    else:
        selected = _latest_date(df)

    total_harian, seksi_totals, tables = _summary_for_date(df, selected)

    tahun_options = sorted({d.year for d in df[COL_TGL]})
    ctx = {
        "title": "Dashboard Izul Janjang",
        "dates": _unique_dates(df),
        "selected_date": selected,
        "total_harian": total_harian,
        "seksi_totals": seksi_totals,
        "tables": tables,
        "bulan_options": list(range(1,13)),
        "tahun_options": tahun_options,
    }
    return render_template("dashboard.html", **ctx)

# ---------- API untuk grafik ----------
@app.get("/api/series")
def api_series():
    """
    Query params:
      seksi   = nama seksi persis (contoh: "A III")
      month   = 1..12   (untuk grafik bulanan)
      year    = 2025    (untuk grafik bulanan & tahunan)
    return:
      { daily: [{x:'2025-10-01', y:123}, ...],
        monthly: [{x:'2025-01', y:999}, ...] }
    """
    if _need_auth():
        return jsonify({"error":"unauthorized"}), 401

    seksi = request.args.get("seksi","").strip()
    month = int(request.args.get("month", 1))
    year  = int(request.args.get("year", 2025))

    df = get_df()
    if df.empty or seksi == "":
        return jsonify({"daily": [], "monthly": []})

    df = df[df[COL_SEKSI].str.lower()==seksi.lower()].copy()
    if df.empty:
        return jsonify({"daily": [], "monthly": []})

    # ===== Bulanan: semua hari pada (year, month) =====
    dfm = df[(df[COL_TGL].dt.year==year) & (df[COL_TGL].dt.month==month)]
    daily = []
    if not dfm.empty:
        dday = dfm.groupby(COL_TGL)[COL_JJG].sum().reset_index().sort_values(COL_TGL)
        daily = [{"x": d.strftime("%Y-%m-%d"), "y": int(v)} for d,v in zip(dday[COL_TGL], dday[COL_JJG])]

    # ===== Tahunan: agregat per-bulan untuk year =====
    dft = df[df[COL_TGL].dt.year==year]
    monthly = []
    if not dft.empty:
        dft["_ym"] = dft[COL_TGL].dt.to_period("M")
        mon = dft.groupby("_ym")[COL_JJG].sum().reset_index()
        mon = mon.sort_values("_ym")
        monthly = [{"x": str(p), "y": int(v)} for p,v in zip(mon["_ym"].astype(str), mon[COL_JJG])]

    return jsonify({"daily": daily, "monthly": monthly})

# --------- Debug kecil yang kamu suka ---------
@app.get("/health")
def health(): return "ok", 200

@app.get("/test")
def test_alive(): return "alive", 200
