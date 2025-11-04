# app.py
# Flask app untuk Izul Panen Dashboard
# Catatan:
# - Pastikan sheets_io.py menyediakan fungsi-fungsi yang dipanggil di sini.
# - File template ada di /templates dan asset di /static (default Flask).
# - Untuk deploy di Vercel, file /api/index.py akan meng-import `app` dari sini.

from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime
import os

# ==== import util ke Google Sheets (punyamu) ====
# Wajib ada di sheets_io.py (sudah kamu commit sebelumnya):
#   get_all_dates() -> list[str 'YYYY-MM-DD']
#   get_daily_by_section(date_str) -> dict[str_section -> list[{'nama': str, 'janjang': int}]]
#   get_totals_for_date(date_str) -> {'total_day': int, 'per_section': {section: int}}
#   get_monthly_series(section, year, month) -> list[{'date': 'YYYY-MM-DD', 'janjang': int}]
#   get_yearly_series(section, year) -> list[{'month': 'YYYY-MM', 'janjang': int}]
#   COL_TANGGAL, COL_SEKSI, COL_NAMA, COL_JANJANG (konstanta kolom)
from sheets_io import (
    get_all_dates,
    get_daily_by_section,
    get_totals_for_date,
    get_monthly_series,
    get_yearly_series,
    COL_TANGGAL, COL_SEKSI, COL_NAMA, COL_JANJANG
)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-key")

# Urutan seksi untuk tampilan
SECTIONS = ["A III", "B III", "C II", "D I"]

# ===== Helper kecil =====
def _default_year_month():
    now = datetime.now()
    return now.year, now.month

def _ensure_login():
    return "user" in session

# ====== Auth sederhana (optional) ======
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", title="Login — Izul Panen")
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    # kredensial dari ENV (opsional)
    u_ok = os.getenv("APP_USERNAME", "admin")
    p_ok = os.getenv("APP_PASSWORD", "admin123")
    if username == u_ok and password == p_ok:
        session["user"] = username
        return redirect(url_for("dashboard"))
    return render_template("login.html", title="Login — Izul Panen", error="Username/Password salah")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ===== Root info ringkas =====
@app.route("/")
def index():
    return "Izul Panen Dashboard\nLogin di /login atau langsung /dashboard bila sudah login.\nDebug: /health, /diag_env, /diag_sheets"

# ====== Halaman utama dashboard ======
@app.route("/dashboard")
def dashboard():
    # kalau mau wajib login, aktifkan blok ini:
    # if not _ensure_login():
    #     return redirect(url_for("login"))

    # ambil list tanggal dari Sheets (untuk dropdown)
    dates = get_all_dates()  # list 'YYYY-MM-DD'
    dates_sorted = sorted(dates)  # ascending
    if not dates_sorted:
        # Jika sheet kosong
        return render_template(
            "dashboard.html",
            title="Dashboard Izul Janjang",
            available_dates=[],
            selected_date=None,
            total_today=0,
            totals_section={s: 0 for s in SECTIONS},
            tables_by_section={s: [] for s in SECTIONS},
            default_month=_default_year_month()[1],
            default_year=_default_year_month()[0],
        )

    # pilih tanggal: dari query ?tanggal=..., kalau kosong pakai terbaru
    selected_date = request.args.get("tanggal")
    if not selected_date or selected_date not in dates_sorted:
        selected_date = dates_sorted[-1]  # terbaru

    # data tabel per seksi untuk tanggal terpilih
    tables_by_section = get_daily_by_section(selected_date)  # dict[section] -> list[{nama, janjang}]
    # pastikan semua seksi ada key
    for s in SECTIONS:
        tables_by_section.setdefault(s, [])

    # total-total
    totals = get_totals_for_date(selected_date)  # {'total_day': int, 'per_section': {...}}
    total_today = totals.get("total_day", 0)
    totals_section = totals.get("per_section", {})
    for s in SECTIONS:
        totals_section.setdefault(s, 0)

    # default dropdown grafik (bulan & tahun)
    def_year, def_month = _default_year_month()

    return render_template(
        "dashboard.html",
        title="Dashboard Izul Janjang",
        available_dates=dates_sorted[::-1],   # descending biar terbaru di atas
        selected_date=selected_date,
        total_today=total_today,
        totals_section=totals_section,
        tables_by_section=tables_by_section,
        default_month=def_month,
        default_year=def_year,
        sections=SECTIONS,
        COL_TANGGAL=COL_TANGGAL, COL_SEKSI=COL_SEKSI, COL_NAMA=COL_NAMA, COL_JANJANG=COL_JANJANG
    )

# ====== Endpoint data grafik (AJAX dari dashboard.html) ======
@app.route("/chart_data/monthly")
def chart_data_monthly():
    # Query: ?section=C%20II&year=2025&month=10
    section = request.args.get("section", SECTIONS[0])
    year = int(request.args.get("year", _default_year_month()[0]))
    month = int(request.args.get("month", _default_year_month()[1]))
    series = get_monthly_series(section, year, month)  # list[{date, janjang}]
    # kembalikan format aman untuk chart (x: tanggal, y: nilai)
    data = [{"x": row["date"], "y": int(row.get("janjang", 0))} for row in series]
    return jsonify({"ok": True, "section": section, "year": year, "month": month, "data": data})

@app.route("/chart_data/yearly")
def chart_data_yearly():
    # Query: ?section=C%20II&year=2025
    section = request.args.get("section", SECTIONS[0])
    year = int(request.args.get("year", _default_year_month()[0]))
    series = get_yearly_series(section, year)  # list[{month:'YYYY-MM', janjang:int}]
    data = [{"x": row["month"], "y": int(row.get("janjang", 0))} for row in series]
    return jsonify({"ok": True, "section": section, "year": year, "data": data})

# ====== Debug / Health ======
@app.route("/health")
def health():
    try:
        _ = get_all_dates()
        return jsonify({"ok": True, "msg": "healthy"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/diag_env")
def diag_env():
    return jsonify({
        "PY_VER": os.getenv("PYTHON_VERSION", "runtime-managed"),
        "HAS_SECRET": bool(os.getenv("SECRET_KEY")),
        "HAS_SA": bool(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")),
    })

@app.route("/diag_sheets")
def diag_sheets():
    try:
        dates = get_all_dates()
        return jsonify({
            "ok": True,
            "dates_sample": dates[:5],
            "cols": {
                "COL_TANGGAL": COL_TANGGAL,
                "COL_SEKSI": COL_SEKSI,
                "COL_NAMA": COL_NAMA,
                "COL_JANJANG": COL_JANJANG
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# Tidak perlu `if __name__ == "__main__":` untuk Vercel (runtime yang jalankan).
# Kalau mau jalankan lokal:
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5000, debug=True)
