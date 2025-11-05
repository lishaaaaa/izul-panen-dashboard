import os
import json
from datetime import datetime, date
from collections import defaultdict, OrderedDict

from flask import Flask, render_template, request, redirect, url_for, session, jsonify

import sheets_io as sio  # gunakan versi yang sudah dikirim sebelumnya

# ================== APP CONFIG ==================
APP_TITLE   = "Izul Janjang Dashboard"
SECRET_KEY  = os.getenv("SECRET_KEY", "dev-secret-please-change")
APP_USER    = os.getenv("APP_USER", "admin")
APP_PASS    = os.getenv("APP_PASS", "admin")

# Nama kolom ENV (lihat Settings > Environment Variables di Vercel)
COL_TANGGAL = os.getenv("COL_TANGGAL", "Hari Tanggal Hari ini").strip()
COL_SEKSI   = os.getenv("COL_SEKSI", "Masukkan Lokasi Seksi yang di Input").strip()

# Daftar seksi yang ingin ditampilkan urut
SECTIONS_ORDER = ["A III", "B III", "C II", "D I"]

app = Flask(__name__)
app.secret_key = SECRET_KEY


# ================== SMALL HELPERS ==================
_FMT_CANDIDATES = ["%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]

def _try_parse_date(s: str):
    s = str(s).strip()
    for fmt in _FMT_CANDIDATES:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def _is_number(x):
    try:
        if x is None: 
            return False
        s = str(x).strip()
        if not s: 
            return False
        float(s)
        return True
    except Exception:
        return False

def _meta_columns():
    # kolom yang BUKAN nama pemanen (silakan tambahkan kalau ada kolom meta lain)
    return set(["Timestamp", "timestamp", COL_TANGGAL, COL_SEKSI])

def _sum_people_in_row(row: dict) -> int:
    """Jumlahkan semua nilai numerik orang dalam satu baris (exclude kolom meta)."""
    meta = _meta_columns()
    total = 0
    for k, v in row.items():
        if k in meta:
            continue
        if _is_number(v):
            total += float(v)
    return int(total)

def _people_counts_from_row(row: dict) -> list[tuple[str, int]]:
    """
    Ambil pasangan (nama, jumlah) dari satu baris (lebar). 
    Semua kolom non-meta yang bernilai numerik dianggap nama pemanen.
    """
    meta = _meta_columns()
    out = []
    for k, v in row.items():
        if k in meta:
            continue
        if _is_number(v):
            val = int(float(v))
            if val != 0:
                out.append((k, val))
    return out

def _section_of_row(row: dict) -> str:
    # akses robust untuk kolom seksi
    if COL_SEKSI in row:
        return str(row[COL_SEKSI]).strip()
    # fallback: cari key yang sama setelah strip
    for k in row.keys():
        if k.strip() == COL_SEKSI:
            return str(row[k]).strip()
    return ""


# ================== ROUTES (BASIC) ==================
@app.route("/")
def home():
    # Halaman depan ringkas: link ke login/dashboard + debug
    return render_template("index.html", title=APP_TITLE)

@app.route("/health")
def health():
    return jsonify(ok=True, app=APP_TITLE)

@app.route("/diag_env")
def diag_env():
    info = {
        "env": {
            "ADMIN_USER": bool(APP_USER),
            "ADMIN_PASS": bool(APP_PASS),
            "SECRET_KEY": bool(SECRET_KEY),
        },
        "cols": {
            "COL_TANGGAL": COL_TANGGAL,
            "COL_SEKSI": COL_SEKSI,
        },
        "has_sheets_io": True
    }
    return jsonify({"ok": True, **info})

@app.route("/diag_sheets")
def diag_sheets():
    try:
        rows = sio.get_rows()
        preview = rows[:2] if rows else []
        return jsonify(ok=True, count=len(rows), preview=preview)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ================== AUTH ==================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        if u == APP_USER and p == APP_PASS:
            session["logged_in"] = True
            nxt = request.args.get("next") or url_for("dashboard")
            return redirect(nxt)
        return render_template("login.html", title=APP_TITLE, error="Username/Password salah.")
    # GET
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    return render_template("login.html", title=APP_TITLE, error=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ================== DASHBOARD ==================
@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login", next="/dashboard"))

    # Ambil daftar tanggal unik dari kolom COL_TANGGAL (desc)
    dates = sio.get_unique_dates()  # [{'label': '10/8/2025', 'sortkey': date(...)}]
    if not dates:
        return render_template(
            "dashboard.html",
            title=APP_TITLE,
            dates=[],
            selected_date=None,
            sections_order=SECTIONS_ORDER,
            sections_table={s: [] for s in SECTIONS_ORDER},
            sections_total={s: 0 for s in SECTIONS_ORDER},
            day_total=0,
            rows_compact=[],
            message="Tidak ada data."
        )

    # Pilihan tanggal (default = terbaru)
    selected = request.args.get("date") or dates[0]["label"]

    # Baris untuk hari terpilih
    rows_today = sio.filter_rows_by_date(selected)

    # ====== Build tabel (per seksi → daftar (nama, jumlah)) ======
    sections_table = {s: [] for s in SECTIONS_ORDER}
    # gunakan dict agregat nama->jumlah per seksi
    agg = {s: defaultdict(int) for s in SECTIONS_ORDER}
    day_total = 0

    for r in rows_today:
        section = _section_of_row(r)
        if not section:
            continue
        people = _people_counts_from_row(r)  # [(nama, jumlah), ...]
        # total harian (semua seksi)
        for _, v in people:
            day_total += v
        if section not in agg:
            # seksi yang di sheet tidak ada di urutan default → buatkan slot
            agg.setdefault(section, defaultdict(int))
            sections_table.setdefault(section, [])

        for name, val in people:
            agg[section][name] += val

    # Konversi ke list & total per seksi
    sections_total = {}
    for sec, mapping in agg.items():
        # urutkan nama alfabet
        items = sorted(mapping.items(), key=lambda x: x[0].lower())
        sections_table[sec] = items
        sections_total[sec] = sum(v for _, v in items)

    # Pastikan seksi yang tidak ada datanya tetap ada di tabel
    for s in SECTIONS_ORDER:
        sections_table.setdefault(s, [])
        sections_total.setdefault(s, 0)

    # ====== Siapkan data kompak utk grafik (dari SELURUH rows) ======
    all_rows = sio.get_rows()
    rows_compact = []
    for r in all_rows:
        # tanggal ISO untuk JS (agar parsing konsisten)
        lbl = r.get(COL_TANGGAL)
        if lbl is None:
            # fallback cari key setelah strip
            k = next((k for k in r.keys() if k.strip() == COL_TANGGAL), None)
            lbl = r.get(k, "")
        d = _try_parse_date(str(lbl))
        iso = d.isoformat() if d else None

        sec = _section_of_row(r)
        total_row = _sum_people_in_row(r)
        rows_compact.append({
            "date_iso": iso,
            "section": sec,
            "total": total_row
        })

    # Untuk filter grafik bulan & tahun di sisi klien
    sd = _try_parse_date(selected)
    selected_year  = sd.year if sd else date.today().year
    selected_month = sd.month if sd else date.today().month

    return render_template(
        "dashboard.html",
        title=APP_TITLE,
        dates=dates,
        selected_date=selected,
        sections_order=SECTIONS_ORDER,
        sections_table=sections_table,
        sections_total=sections_total,
        day_total=day_total,
        rows_compact=rows_compact,
        col_tanggal=COL_TANGGAL,
        col_seksi=COL_SEKSI,
        selected_year=selected_year,
        selected_month=selected_month,
        message=None if rows_today else "Tidak ada data untuk tanggal yang dipilih."
    )


# ============== MINIMAL INDEX TEMPLATE FALLBACK ==============
# (Jika kamu belum punya templates/index.html, render sederhana di sini)
@app.route("/index-fallback")
def index_fallback():
    return f"{APP_TITLE} • Login di /login atau langsung /dashboard bila sudah login. Debug: /health, /diag_env, /diag_sheets"


if __name__ == "__main__":
    # Dev run
    app.run(debug=True)
