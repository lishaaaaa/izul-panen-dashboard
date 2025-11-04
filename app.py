import os
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dotenv import load_dotenv
from sheets_io import (
    list_dates_str, rows_by_date_str, totals_per_seksi,
    series_for_section, list_years, list_months, series_month, series_year
)

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY","dev")

SECTIONS = ["A III","B III","C II","D I"]

# ========== AUTH ==========
APP_USER = os.getenv("APP_USER","admin")
APP_PASS = os.getenv("APP_PASS","admin")

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username","")
        p = request.form.get("password","")
        if u == APP_USER and p == APP_PASS:
            session["user"] = u
            dst = request.args.get("next") or url_for("index")
            return redirect(dst)
        return render_template("login.html", error="Username/Password salah")
    return render_template("login.html")

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ========== PAGES ==========
@app.get("/")
@login_required
def index():
    return render_template("index.html", sections=SECTIONS)

# ========== APIs (data) ==========
@app.get("/api/dates")
@login_required
def api_dates():
    return jsonify(list_dates_str())

@app.get("/api/panen")
@login_required
def api_panen():
    d = request.args.get("date")
    if not d: return jsonify({"error":"missing ?date="}), 400
    rows = rows_by_date_str(d)
    groups = {s: [] for s in SECTIONS}
    for r in rows:
        if r["seksi"] in groups:
            groups[r["seksi"]].append({"nama": r["nama"], "janjang": r["janjang"]})
    totals, grand = totals_per_seksi(rows)
    return jsonify({"date": d, "groups": groups, "totals": totals, "grand_total": grand})

# existing rolling-window series (30/365) tetap ada
@app.get("/api/series")
@login_required
def api_series():
    seksi = request.args.get("seksi"); d = request.args.get("date"); window = int(request.args.get("window","30"))
    if not seksi: return jsonify({"error":"missing ?seksi="}), 400
    labels, data = series_for_section(seksi, d, window)
    return jsonify({"labels":labels, "data":data})

# === NEW: dropdown bulan/tahun ===
@app.get("/api/years")
@login_required
def api_years():
    return jsonify(list_years())

@app.get("/api/months")
@login_required
def api_months():
    y = request.args.get("year")
    return jsonify(list_months(y) if y else list_months())

@app.get("/api/series_month")
@login_required
def api_series_month():
    seksi = request.args.get("seksi"); y = request.args.get("year"); m = request.args.get("month")
    if not (seksi and y and m): return jsonify({"error":"need ?seksi=&year=&month="}), 400
    labels, data = series_month(seksi, y, m)
    return jsonify({"labels":labels, "data":data})

@app.get("/api/series_year")
@login_required
def api_series_year():
    seksi = request.args.get("seksi"); y = request.args.get("year")
    if not (seksi and y): return jsonify({"error":"need ?seksi=&year="}), 400
    labels, data = series_year(seksi, y)
    return jsonify({"labels":labels, "data":data})
    
@app.get("/health")
def health(): return "ok", 200

if __name__ == "__main__":
    app.run(debug=True)
