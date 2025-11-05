import os
import json
import traceback
from datetime import datetime
from flask import Flask, request, render_template, redirect, url_for, session, abort

# ---------- KONFIG ----------
APP_TITLE = "Izul Janjang Dashboard"
ADMIN_USER = os.getenv("APP_USER", "admin")
ADMIN_PASS = os.getenv("APP_PASS", "admin")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
DATE_ORDER = os.getenv("DATE_ORDER", "DMY")  # tidak dipakai keras, tapi disimpan bila perlu

# ENV nama kolom (opsional). Jika tidak cocok, kita auto-deteksi.
COL_TANGGAL = os.getenv("COL_TANGGAL", "").strip()
COL_SEKSI   = os.getenv("COL_SEKSI", "").strip()
COL_NAMA    = os.getenv("COL_NAMA", "").strip()     # tidak dipakai langsung (nama di sheet adalah kolom-kolom dinamis)
COL_JANJANG = os.getenv("COL_JANJANG", "").strip()  # tidak dipakai langsung (nilai adalah angka di kolom nama)

# ---------- IMPORT SHEETS IO ----------
try:
    from sheets_io import get_rows  # harus mengembalikan list[dict]
    HAS_SHEETS = True
except Exception:
    HAS_SHEETS = False
    get_rows = None

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ---------- UTIL ----------
def _is_date_like_key(k: str) -> bool:
    ks = k.lower().strip()
    return ("tanggal" in ks) or ("date" in ks)

def _is_seksi_like_key(k: str) -> bool:
    ks = k.lower().strip()
    return ("seksi" in ks)

def _safe_to_int(x):
    try:
        if x is None or str(x).strip() == "":
            return 0
        return int(float(str(x).strip()))
    except:
        return 0

def melt_rows(rows, col_tanggal_hint="", col_seksi_hint=""):
    """
    rows: list[dict] dari sheets_io.get_rows()
    return:
      - melted: list dict {tanggal, seksi, nama, janjang}
      - meta   : dict {date_keys, seksi_keys, worker_keys, warnings}
    """
    meta = {"warnings": []}
    if not rows:
        return [], {"warnings": ["Tidak ada data dari Sheets."]}

    # 1) Tentukan kolom tanggal
    keys = list(rows[0].keys())
    date_key = col_tanggal_hint if col_tanggal_hint in keys else ""
    if not date_key:
        for k in keys:
            if _is_date_like_key(k):
                date_key = k
                break
    if not date_key:
        meta["warnings"].append("Kolom tanggal tidak ditemukan. Pastikan ENV COL_TANGGAL atau ada kolom mengandung kata 'Tanggal/Date'.")
        date_key = keys[0]  # fallback agar tidak KeyError

    # 2) Tentukan kolom seksi
    seksi_key = col_seksi_hint if col_seksi_hint in keys else ""
    if not seksi_key:
        for k in keys:
            if _is_seksi_like_key(k):
                seksi_key = k
                break
    if not seksi_key:
        meta["warnings"].append("Kolom seksi tidak ditemukan. Pastikan ENV COL_SEKSI atau ada kolom mengandung kata 'Seksi'.")
        # jika tidak ada, buat kolom seksi default kosong
        seksi_key = None

    # 3) Tentukan kolom "worker" = semua kolom selain timestamp-ish & meta
    meta_like = set([date_key])
    if seksi_key:
        meta_like.add(seksi_key)
    # tambahkan kemungkinan kolom timestamp agar tak dihitung worker
    for k in keys:
        kl = k.lower()
        if "timestamp" in kl:
            meta_like.add(k)

    worker_keys = [k for k in keys if k not in meta_like]
    meta["date_key"] = date_key
    meta["seksi_key"] = seksi_key
    meta["worker_keys"] = worker_keys

    melted = []
    for r in rows:
        tanggal_val = str(r.get(date_key, "")).strip()
        seksi_val = str(r.get(seksi_key, "")).strip() if seksi_key else ""
        for wk in worker_keys:
            nama = wk
            janjang = _safe_to_int(r.get(wk))
            if janjang > 0:
                melted.append({
                    "tanggal": tanggal_val,
                    "seksi": seksi_val,
                    "nama": nama,
                    "janjang": janjang
                })

    return melted, meta

def group_by_seksi(melted, tanggal_filter=""):
    """
    Kembalikan struktur:
    {
      "A III": {"total": 123, "rows":[{"nama":"Agus","janjang":...}, ...]},
      "B III": {...},
      ...
    }
    """
    from collections import defaultdict
    hasil = defaultdict(lambda: {"total": 0, "rows": []})
    total_hari_ini = 0

    for it in melted:
        if tanggal_filter and str(it["tanggal"]) != str(tanggal_filter):
            continue
        seksi = it["seksi"] or "Tanpa Seksi"
        hasil[seksi]["rows"].append({"nama": it["nama"], "janjang": it["janjang"]})
        hasil[seksi]["total"] += it["janjang"]
        total_hari_ini += it["janjang"]

    # sort rows per seksi by nama asc
    for s in hasil:
        hasil[s]["rows"].sort(key=lambda x: x["nama"].lower())

    # urutkan seksi by nama
    seksi_sorted = dict(sorted(hasil.items(), key=lambda x: x[0]))
    return seksi_sorted, total_hari_ini

# ---------- ROUTES ----------
@app.route("/")
def index():
    return render_template("index.html", title=APP_TITLE)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        if u == ADMIN_USER and p == ADMIN_PASS:
            session["logged_in"] = True
            next_url = request.args.get("next") or url_for("dashboard")
            return redirect(next_url)
        else:
            return render_template("login.html", title=APP_TITLE, error="Username / password salah.")
    return render_template("login.html", title=APP_TITLE)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login", next=url_for("dashboard")))
    if not HAS_SHEETS or get_rows is None:
        return render_template("dashboard.html",
                               title=APP_TITLE,
                               error="Modul sheets_io tidak tersedia / tidak dapat diimpor.",
                               tanggal_list=[],
                               tanggal_selected="",
                               total_hari_ini=0,
                               seksi_blocks={})

    error_msg = ""
    try:
        rows = get_rows()
        melted, meta = melt_rows(rows, COL_TANGGAL, COL_SEKSI)

        # daftar tanggal unik
        tanggal_list = sorted(list({str(x["tanggal"]) for x in melted if str(x["tanggal"]).strip() != ""}))
        # default pilih tanggal terakhir
        tanggal_selected = request.args.get("tanggal") or (tanggal_list[-1] if tanggal_list else "")

        seksi_blocks, total_hari_ini = group_by_seksi(melted, tanggal_selected)

        # info meta/warning (tampil kecil di atas)
        if meta.get("warnings"):
            error_msg = " | ".join(meta["warnings"])

        return render_template("dashboard.html",
                               title=APP_TITLE,
                               error=error_msg,
                               tanggal_list=tanggal_list,
                               tanggal_selected=tanggal_selected,
                               total_hari_ini=total_hari_ini,
                               seksi_blocks=seksi_blocks)
    except Exception as e:
        tb = traceback.format_exc()
        error_msg = f"Gagal memuat dashboard: {e}\n{tb}"
        return render_template("dashboard.html",
                               title=APP_TITLE,
                               error=error_msg,
                               tanggal_list=[],
                               tanggal_selected="",
                               total_hari_ini=0,
                               seksi_blocks={})

# ---------- DEBUG ----------
@app.route("/health")
def health():
    return {"ok": True, "app": APP_TITLE}

@app.route("/diag_env")
def diag_env():
    return {
        "cols": {
            "COL_TANGGAL": COL_TANGGAL,
            "COL_SEKSI": COL_SEKSI,
            "COL_NAMA": COL_NAMA,
            "COL_JANJANG": COL_JANJANG
        },
        "env": {
            "ADMIN_USER": bool(ADMIN_USER),
            "ADMIN_PASS": bool(ADMIN_PASS),
            "SECRET_KEY": bool(SECRET_KEY)
        },
        "has_sheets_io": HAS_SHEETS,
        "ok": True
    }

@app.route("/diag_sheets")
def diag_sheets():
    if not HAS_SHEETS or get_rows is None:
        return {"ok": False, "error": "sheets_io tidak tersedia"}
    try:
        data = get_rows()
        preview = data[:3]
        return {"ok": True, "count": len(data), "preview": preview}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# Vercel Python 4 mengharapkan 'app' sebagai WSGI callable
# tidak perlu __main__ guard
