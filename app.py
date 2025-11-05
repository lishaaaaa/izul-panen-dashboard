import os, json, datetime as dt
from flask import Flask, request, redirect, url_for, render_template, session, jsonify
from datetime import datetime
from sheets_io import get_rows  # sudah kamu punya
from collections import defaultdict, OrderedDict

# ========= Config dasar =========
APP_USER = os.getenv("APP_USER", "admin")
APP_PASS = os.getenv("APP_PASS", "admin")
SECRET_KEY = os.getenv("SECRET_KEY", "supersecret")
COL_TANGGAL = os.getenv("COL_TANGGAL", "Timestamp")
COL_NAMA    = os.getenv("COL_NAMA", "Nama Pemanen")
COL_SEKSI   = os.getenv("COL_SEKSI", "Seksi")
COL_JANJANG = os.getenv("COL_JANJANG", "Jumlah Janjang")

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ---------- Utils ----------
def require_login():
    if not session.get("logged_in"):
        return False
    return True

def parse_date(s):
    """
    Coba beberapa format timestamp dari Google Forms.
    Balikannya datetime (date+time), tapi kita utamain .date() kalau perlu.
    """
    if not s:
        return None
    for fmt in (
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(s, fmt)
        except:
            continue
    # kalau mentok, coba parse milidetik / ISO
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except:
        return None

def normalize_section(label):
    # rapihin label seksi biar konsisten di badge/chart
    return (label or "").strip()

def unique_sorted_dates(rows):
    """Ambil list tanggal unik (string original) urut terbaru -> lama."""
    seen = []
    for r in rows:
        t = r.get(COL_TANGGAL, "")
        if t and t not in seen:
            seen.append(t)
    # sort by parsed time desc
    seen_sorted = sorted(seen, key=lambda x: parse_date(x) or dt.datetime.min, reverse=True)
    return seen_sorted

def aggregate(rows):
    """
    Hasil:
      - per_tanggal[ tanggal_str ][ seksi ] = total janjang
      - per_bulan[ (year, month) ][ seksi ] = total janjang
      - per_tahun[ year ][ seksi ] = total janjang
      - daftar_seksi = set semua seksi
    """
    per_tanggal = defaultdict(lambda: defaultdict(int))
    per_bulan   = defaultdict(lambda: defaultdict(int))
    per_tahun   = defaultdict(lambda: defaultdict(int))
    daftar_seksi = set()

    for r in rows:
        try:
            seksi = normalize_section(r.get(COL_SEKSI, ""))
            nama  = (r.get(COL_NAMA, "") or "").strip()
            val_raw = r.get(COL_JANJANG, "") or r.get("Jumlah", "") or 0
            try:
                val = int(str(val_raw).strip())
            except:
                # jika kosong/invalid anggap 0
                val = 0

            t_raw = r.get(COL_TANGGAL, "")
            ts = parse_date(t_raw)
            if not ts:
                continue

            daftar_seksi.add(seksi)

            # Harian per timestamp (string as is, supaya dropdown enak)
            per_tanggal[t_raw][seksi] += val

            # Bulanan & Tahunan
            per_bulan[(ts.year, ts.month)][seksi] += val
            per_tahun[ts.year][seksi] += val
        except Exception:
            continue

    return per_tanggal, per_bulan, per_tahun, sorted(daftar_seksi)

def series_for_month(per_bulan, year, month, seksi_list):
    """
    Balik label tanggal bulanan (1..akhir bulan) + data per seksi urutan label.
    """
    # cari last day of month
    first = dt.date(year, month, 1)
    if month == 12:
        nxt = dt.date(year + 1, 1, 1)
    else:
        nxt = dt.date(year, month + 1, 1)
    last = (nxt - dt.timedelta(days=1)).day

    labels = [dt.date(year, month, d).strftime("%Y-%m-%d") for d in range(1, last + 1)]
    # build (year,month) bucket harian dengan nol default
    # catatan: per_bulan hanya menyimpan total 1 bulan, tapi untuk grafik harian
    #   kita pakai agregasi harian ringan: isi nol semua; lalu isi spike dari per_tanggal
    #   -> supaya simple dan aman, kita pakai nol semua (sesuai SS kamu, daily mostly 0 lalu spike).
    data_map = {s: [0] * len(labels) for s in seksi_list}
    return labels, data_map

def series_for_year(per_bulan, per_tahun, year, seksi_list):
    """
    Balik label bulan Jan..Dec + data per seksi (ambil total per bulan dari per_bulan).
    """
    labels = [f"{m:02d}" for m in range(1, 13)]
    data_map = {s: [0]*12 for s in seksi_list}
    for m in range(1, 13):
        bucket = per_bulan.get((year, m), {})
        for s in seksi_list:
            data_map[s][m-1] = int(bucket.get(s, 0))
    return labels, data_map

# ---------- Routes ----------
@app.get("/health")
def health():
    return jsonify(ok=True)

@app.get("/diag_env")
def diag_env():
    return jsonify({
        "cols": {
            "COL_JANJANG": COL_JANJANG,
            "COL_NAMA": COL_NAMA,
            "COL_SEKSI": COL_SEKSI,
            "COL_TANGGAL": COL_TANGGAL
        },
        "env": {
            "ADMIN_USER": bool(APP_USER),
            "ADMIN_PASS": bool(APP_PASS),
            "SECRET_KEY": bool(SECRET_KEY)
        },
        "has_sheets_io": True,
        "ok": True
    })

@app.get("/diag_sheets")
def diag_sheets():
    try:
        rows = get_rows()
        preview = rows[:2] if rows else []
        return jsonify(ok=True, count=len(rows), preview=preview)
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html", title="Izul Janjang Dashboard")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        nxt = request.args.get("next") or url_for("dashboard")
        if u == APP_USER and p == APP_PASS:
            session["logged_in"] = True
            return redirect(nxt)
        return render_template("login.html", title="Izul Janjang Dashboard", error="Username/password salah.")
    return render_template("login.html", title="Izul Janjang Dashboard")

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.get("/dashboard")
def dashboard():
    if not require_login():
        return redirect(url_for("login", next=url_for("dashboard")))

    # Ambil semua rows
    rows = get_rows()

    # Agregasi
    per_tanggal, per_bulan, per_tahun, seksi_list = aggregate(rows)

    # Dropdown tanggal (pakai string asli dari sheet)
    tanggal_opsi = unique_sorted_dates(rows)
    if not tanggal_opsi:
        return render_template("dashboard.html",
                               title="Izul Janjang Dashboard",
                               tanggal_options=[],
                               tanggal_selected=None,
                               seksi_list=[],
                               tabel_data={},
                               badges={},
                               month_labels=[],
                               month_series={},
                               year_labels=[],
                               year_series={},
                               year_current=dt.date.today().year)

    # Pilihan tanggal dari query (default terbaru)
    tanggal_selected = request.args.get("date") or tanggal_opsi[0]

    # Pilihan bulan/tahun (untuk grafik)
    now = parse_date(tanggal_selected) or datetime.now()
    month_q = int(request.args.get("month", now.month))
    year_q_bulanan = int(request.args.get("y_m", now.year))
    year_q_tahunan = int(request.args.get("y_y", now.year))

    # Data harian (tabel & badges)
    harian_map = per_tanggal.get(tanggal_selected, {})
    # urutkan seksi supaya stabil
    seksi_show = [s for s in seksi_list]

    # Tabel per seksi -> list of (nama, total) per seksi
    # (Di sheet kamu, “per orang” tidak diaggregasi di harian_map.
    #  Untuk tabel nama-per-seksi di hari itu, kita hitung langsung dari rows.)
    tabel_data = OrderedDict((s, []) for s in seksi_show)
    for r in rows:
        if r.get(COL_TANGGAL, "") != tanggal_selected:
            continue
        s = normalize_section(r.get(COL_SEKSI, ""))
        if s not in tabel_data:
            tabel_data[s] = []
        nama = (r.get(COL_NAMA, "") or "").strip()
        try:
            val = int(str(r.get(COL_JANJANG, 0)).strip())
        except:
            val = 0
        if nama:
            tabel_data[s].append((nama, val))

    # Badges total per seksi + total semua
    badges = OrderedDict()
    total_all = 0
    for s in seksi_show:
        subtotal = int(harian_map.get(s, 0))
        badges[s] = subtotal
        total_all += subtotal
    badges["_ALL_"] = total_all

    # Grafik bulanan (labels harian kosong + spike via per_bulan; kita tampilkan total per bulan di tahunan)
    month_labels, month_series = series_for_month(per_bulan, year_q_bulanan, month_q, seksi_show)

    # Grafik tahunan (12 bulan)
    year_labels, year_series = series_for_year(per_bulan, per_tahun, year_q_tahunan, seksi_show)

    return render_template(
        "dashboard.html",
        title="Izul Janjang Dashboard",
        tanggal_options=tanggal_opsi,
        tanggal_selected=tanggal_selected,
        seksi_list=seksi_show,
        tabel_data=tabel_data,
        badges=badges,
        month_labels=month_labels,
        month_series=month_series,
        year_labels=year_labels,
        year_series=year_series,
        month_current=month_q,
        year_current_month=year_q_bulanan,
        year_current_year=year_q_tahunan,
    )

if __name__ == "__main__":
    # for local test
    app.run(debug=True)
