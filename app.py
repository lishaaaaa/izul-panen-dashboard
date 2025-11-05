# app.py
# Flask app untuk Vercel (@vercel/python). Entry di vercel.json -> api/index.py yang meng-import app ini.
from __future__ import annotations
import os
import json
from collections import defaultdict
from datetime import datetime, date
from functools import wraps
from typing import Dict, List, Any, Iterable, Tuple

from flask import (
    Flask, render_template, request, session, redirect, url_for,
    jsonify, abort
)

# ====== KONFIGURASI DASHBOARD ======
APP_TITLE = "Izul Panen Dashboard"

# ENV (isi di Vercel → Settings → Environment Variables)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")

# ====== IMPORT LAYER SHEETS ======
# Kita buat import yang "tahan banting" ke berbagai nama fungsi/konstanta di sheets_io.py
try:
    import sheets_io as sio  # file lokal kamu
except Exception as e:
    sio = None
    print("WARNING: sheets_io tidak bisa diimport:", e)

def _col(name: str, default: str) -> str:
    """Ambil nama kolom dari sheets_io bila ada, kalau tidak pakai default."""
    return getattr(sio, name, default) if sio else default

COL_TANGGAL = _col("COL_TANGGAL", "COL_TANGGAL")
COL_NAMA    = _col("COL_NAMA",    "COL_NAMA")
COL_JANJANG = _col("COL_JANJANG", "COL_JANJANG")
COL_SEKSI   = _col("COL_SEKSI",   "COL_SEKSI")

def _fetch_rows() -> List[Dict[str, Any]]:
    """
    Ambil baris dari Google Sheets lewat sheets_io.
    Mencoba beberapa nama fungsi umum agar kompatibel dengan variasi implementasi.
    """
    if sio is None:
        return []
    for fn in ("get_rows", "get_sheet_rows", "fetch_rows", "load_rows", "read_rows"):
        if hasattr(sio, fn):
            rows = getattr(sio, fn)()
            # Normalisasi: pastikan list[dict]
            if isinstance(rows, list):
                return rows
    raise RuntimeError("Tidak menemukan fungsi pembaca data di sheets_io (coba sediakan get_rows()).")


# ====== UTIL ======
def parse_any_date(s: str | date | datetime) -> date | None:
    """Parse berbagai format tanggal umum ke date()."""
    if s is None:
        return None
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if isinstance(s, datetime):
        return s.date()
    t = str(s).strip()
    if not t:
        return None

    # Coba beberapa pola umum
    fmts = [
        "%Y-%m-%d",    # 2025-10-08
        "%Y/%m/%d",
        "%m/%d/%Y",    # 10/08/2025 (US)
        "%d/%m/%Y",    # 08/10/2025 (ID/EU)
        "%-m/%-d/%Y",  # linux-friendly
        "%-d/%-m/%Y",
    ]
    for f in fmts:
        try:
            return datetime.strptime(t, f).date()
        except Exception:
            pass

    # Fallback: split heuristik
    try:
        parts = t.replace("-", "/").split("/")
        parts = [p for p in parts if p]
        if len(parts) == 3:
            a, b, c = parts
            if len(a) == 4:  # yyyy/mm/dd
                return date(int(a), int(b), int(c))
            # Tebak US (mm/dd/yyyy) jika a<=12
            if int(a) <= 12:
                return date(int(c), int(a), int(b))
            # Else EU (dd/mm/yyyy)
            return date(int(c), int(b), int(a))
    except Exception:
        pass
    return None


def require_login(view):
    @wraps(view)
    def _wrap(*args, **kwargs):
        if not session.get("authed"):
            # kalau belum login, arahkan ke /login dan simpan next
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return _wrap


def rows_by_date(rows: Iterable[Dict[str, Any]], tanggal: date) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        d = parse_any_date(r.get(COL_TANGGAL))
        if d == tanggal:
            out.append(r)
    return out


def sum_by_key(rows: Iterable[Dict[str, Any]], group_key: str) -> Dict[str, float]:
    agg = defaultdict(float)
    for r in rows:
        name = str(r.get(group_key, "")).strip()
        try:
            val = float(str(r.get(COL_JANJANG, 0)).replace(",", "").strip() or 0)
        except Exception:
            val = 0.0
        agg[name] += val
    return dict(agg)


def to_month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


# ====== APLIKASI ======
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = SECRET_KEY


# ---------- Landing ----------
@app.get("/")
def home():
    return render_template(
        "index.html",
        title=APP_TITLE,
        debug_links=[("/health","health"), ("/diag_env","diag_env"), ("/diag_sheets","diag_sheets")]
    )


# ---------- Auth ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username", "")
        pwd  = request.form.get("password", "")
        if user == ADMIN_USER and pwd == ADMIN_PASS:
            session["authed"] = True
            nxt = request.args.get("next") or url_for("dashboard")
            return redirect(nxt)
        return render_template("login.html", title=APP_TITLE, error="Username atau password salah.")
    return render_template("login.html", title=APP_TITLE, error=None)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ---------- Dashboard ----------
@app.get("/dashboard")
@require_login
def dashboard():
    """Render dashboard + kirim data agregat untuk tanggal yang dipilih."""
    # Ambil semua baris
    try:
        all_rows = _fetch_rows()
    except Exception as e:
        return f"Gagal membaca data Sheets: {e}", 500

    # Cari tanggal terbaru di data
    all_dates = sorted({parse_any_date(r.get(COL_TANGGAL)) for r in all_rows if r.get(COL_TANGGAL)}, reverse=True)
    latest = next((d for d in all_dates if d is not None), date.today())

    # Ambil pilihan tanggal dari query (default: latest dari data)
    q = request.args.get("tanggal", "")
    picked_date = parse_any_date(q) or latest

    # Data untuk tanggal yang dipilih
    rows_today = rows_by_date(all_rows, picked_date)

    # Total harian seluruh seksi
    total_harian = 0.0
    for r in rows_today:
        try:
            total_harian += float(str(r.get(COL_JANJANG, 0)).replace(",", "").strip() or 0)
        except Exception:
            pass

    # Total per seksi (hari itu)
    per_seksi_today = sum_by_key(rows_today, COL_SEKSI)

    # Data tabel per seksi (kolom: COL_NAMA, COL_JANJANG)
    tabel_per_seksi: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
    for r in rows_today:
        seksi = str(r.get(COL_SEKSI, "")).strip()
        nama  = str(r.get(COL_NAMA, "")).strip()
        try:
            val = float(str(r.get(COL_JANJANG, 0)).replace(",", "").strip() or 0)
        except Exception:
            val = 0.0
        tabel_per_seksi[seksi].append((nama, val))

    # Urutkan tabel nama pemanen per seksi (desc)
    for sx, lst in tabel_per_seksi.items():
        lst.sort(key=lambda x: x[0].lower())

    # Dropdown bulan & tahun untuk grafik
    # (default: bulan & tahun dari picked_date)
    bulan_default = picked_date.month
    tahun_default = picked_date.year

    # Kumpulkan daftar seksi unik untuk loop di template
    seksi_unik = sorted({str(r.get(COL_SEKSI, "")).strip() for r in all_rows if r.get(COL_SEKSI)})

    return render_template(
        "dashboard.html",
        title=APP_TITLE,
        tanggal_str=picked_date.isoformat(),
        total_harian=total_harian,
        per_seksi_today=per_seksi_today,
        tabel_per_seksi=tabel_per_seksi,
        seksi_unik=seksi_unik,
        bulan_default=bulan_default,
        tahun_default=tahun_default,
        # Nama kolom untuk referensi di template/JS jika perlu
        COL_TANGGAL=COL_TANGGAL,
        COL_NAMA=COL_NAMA,
        COL_JANJANG=COL_JANJANG,
        COL_SEKSI=COL_SEKSI,
    )


# ---------- API untuk Grafik ----------
@app.get("/api/sektion/<seksi>/monthly")
@require_login
def api_monthly(seksi: str):
    """
    Series harian untuk bulan & tahun tertentu pada seksi tertentu.
    Param: month=1..12, year=YYYY
    Output: { labels: [YYYY-MM-DD,...], data: [angka,...] }
    """
    month = int(request.args.get("month", "1"))
    year  = int(request.args.get("year",  "1970"))

    try:
        all_rows = _fetch_rows()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    buckets: Dict[date, float] = defaultdict(float)
    for r in all_rows:
        d = parse_any_date(r.get(COL_TANGGAL))
        if not d or d.year != year or d.month != month:
            continue
        if str(r.get(COL_SEKSI, "")).strip() != seksi:
            continue
        try:
            val = float(str(r.get(COL_JANJANG, 0)).replace(",", "").strip() or 0)
        except Exception:
            val = 0.0
        buckets[d] += val

    labels = [dt.isoformat() for dt in sorted(buckets.keys())]
    data   = [buckets[dt] for dt in sorted(buckets.keys())]
    return jsonify({"ok": True, "labels": labels, "data": data})


@app.get("/api/sektion/<seksi>/yearly")
@require_login
def api_yearly(seksi: str):
    """
    Series bulanan untuk tahun tertentu pada seksi tertentu.
    Param: year=YYYY
    Output: { labels: ["2025-01",...,"2025-12"], data: [angka bulanan] }
    """
    year = int(request.args.get("year", "1970"))

    try:
        all_rows = _fetch_rows()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    buckets: Dict[str, float] = defaultdict(float)  # key: YYYY-MM
    for r in all_rows:
        d = parse_any_date(r.get(COL_TANGGAL))
        if not d or d.year != year:
            continue
        if str(r.get(COL_SEKSI, "")).strip() != seksi:
            continue
        try:
            val = float(str(r.get(COL_JANJANG, 0)).replace(",", "").strip() or 0)
        except Exception:
            val = 0.0
        buckets[to_month_key(d)] += val

    # urutkan 12 bulan
    labels = [f"{year:04d}-{m:02d}" for m in range(1, 13)]
    data   = [buckets.get(lbl, 0.0) for lbl in labels]
    return jsonify({"ok": True, "labels": labels, "data": data})


# ---------- DIAG / HEALTH ----------
@app.get("/health")
def health():
    return jsonify({"ok": True, "ts": datetime.utcnow().isoformat()})


@app.get("/diag_env")
def diag_env():
    return jsonify({
        "ok": True,
        "has_sheets_io": sio is not None,
        "cols": {
            "COL_TANGGAL": COL_TANGGAL,
            "COL_NAMA": COL_NAMA,
            "COL_JANJANG": COL_JANJANG,
            "COL_SEKSI": COL_SEKSI,
        },
        "env": {
            "ADMIN_USER": bool(ADMIN_USER),
            "ADMIN_PASS": bool(ADMIN_PASS),
            "SECRET_KEY": bool(SECRET_KEY),
            # jangan bocorkan nilai env
        }
    })


@app.get("/diag_sheets")
def diag_sheets():
    try:
        rows = _fetch_rows()
        preview = rows[:5]
        return jsonify({"ok": True, "count": len(rows), "preview": preview})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ---------- DEV LOCAL ----------
if __name__ == "__main__":
    # Jalankan lokal
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
