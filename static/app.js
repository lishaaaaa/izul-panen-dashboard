/* ================= Chart.js defaults (matikan animasi) ================= */
Chart.defaults.animation = false;
Chart.defaults.transitions.active = { animation: { duration: 0 } };
Chart.defaults.transitions.show = { animation: { duration: 0 } };
Chart.defaults.transitions.hide = { animation: { duration: 0 } };

/* ================= Utilities ================= */
const $ = (sel, root=document) => root.querySelector(sel);
const el = (tag, attrs={}) => Object.assign(document.createElement(tag), attrs);
const fmt = (n) => (Math.round((n ?? 0) * 100) / 100).toString();

/* state */
const charts = new Map(); // key -> Chart
let lastRows = [];        // cache rows by date (utk bikin daftar seksi)

function destroyChart(key){
  const c = charts.get(key);
  if (c) { try { c.destroy(); } catch{}; charts.delete(key); }
}

/* ================= Fetch helpers ================= */
async function api(path, params){
  const url = new URL(path, window.location.origin);
  if (params) Object.entries(params).forEach(([k,v])=>url.searchParams.set(k, v));
  const r = await fetch(url);
  const j = await r.json();
  if (!j.ok) throw new Error(j.error || 'API error');
  return j;
}

/* ================== Badges & Table ================== */
function renderBadges(grand, totalsBySeksi){
  const wrap = $('#badges');
  wrap.innerHTML = '';
  const bTotal = el('span', { className:'badge', textContent:`Total Tanggal Ini: ${fmt(grand)}`});
  wrap.append(bTotal);

  Object.entries(totalsBySeksi).sort().forEach(([seksi, v])=>{
    wrap.append(el('span', { className:'badge', textContent:`${seksi}: ${fmt(v)}`}));
  });
}

function groupBySeksi(rows){
  const map = {};
  for (const r of rows){
    (map[r.seksi] ||= []).push(r);
  }
  return map;
}

function renderTables(rows){
  const wrap = $('#tablesWrap');
  wrap.innerHTML = '';

  const bySeksi = groupBySeksi(rows);
  const seksiNames = Object.keys(bySeksi).sort();

  if (seksiNames.length === 0){
    wrap.innerHTML = '<p>Tidak ada data pada tanggal ini.</p>';
    return [];
  }

  // urut nama pekerja fix seperti di data
  const order = ["Agus","Bagol","Herman","Keleng","Paeng","Riadi","Supri","Suri","Wagiso"];

  const usedSeksi = [];

  for (const seksi of seksiNames){
    usedSeksi.push(seksi);
    const rowsS = bySeksi[seksi];

    const card = el('div', { className:'card span-12' });
    card.append(el('div', { className:'seksi-title', textContent:`Seksi ${seksi}` }));

    // tabel
    const tbl = el('table');
    const thead = el('thead');
    thead.innerHTML = `<tr><th style="width:50%">Nama Pemanen</th><th>Jumlah Janjang</th></tr>`;
    tbl.appendChild(thead);

    const tb = el('tbody');
    let subtotal = 0;

    // map nama->total
    const mapName = {};
    for (const r of rowsS) mapName[r.nama] = (mapName[r.nama] || 0) + (r.janjang || 0);

    // urut sesuai daftar pekerja
    order.forEach(n=>{
      const v = mapName[n] ?? 0;
      subtotal += v;
      const tr = el('tr');
      tr.innerHTML = `<td>${n}</td><td>${fmt(v)}</td>`;
      tb.appendChild(tr);
    });

    // total row
    const trT = el('tr', { className:'total-row' });
    trT.innerHTML = `<td>Total</td><td>${fmt(subtotal)}</td>`;
    tb.appendChild(trT);

    tbl.appendChild(tb);
    card.appendChild(tbl);
    wrap.appendChild(card);
  }

  return usedSeksi;
}

/* ================== Horizontal Charts ================== */
function renderHorizontalChart({ key, ctx, labels, data, title }){
  destroyChart(key);
  const maxVal = Math.max(0, ...data);
  const suggestedMax = maxVal > 0 ? Math.ceil(maxVal * 1.1) : 1;

  const chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Janjang",
        data,
        borderWidth: 1,
        barThickness: 18,
        categoryPercentage: 0.9
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      animation: false,
      plugins: {
        legend: { display:false },
        title: { display: !!title, text: title, padding:{ bottom:8 } },
        tooltip: { enabled:true }
      },
      scales: {
        x: { beginAtZero:true, suggestedMax, grid:{ color:"rgba(0,0,0,0.05)" }, ticks:{ precision:0 } },
        y: { grid:{ display:false } }
      }
    }
  });

  charts.set(key, chart);
}

function makeChartPanel(seksi){
  const box = el('div', { className:'canvas-box' });
  const c = el('canvas');
  box.appendChild(c);
  const box2 = el('div', { className:'canvas-box' });
  const c2 = el('canvas');
  box2.appendChild(c2);

  const container = el('div');
  container.appendChild(el('div', { style:'font-weight:700;margin:6px 0', textContent:`${seksi}` }));
  container.style.gridColumn = '1 / -1'; // judul seksi
  return { header:container, monthBox:box, monthCanvas:c, yearBox:box2, yearCanvas:c2 };
}

async function renderCharts(seksiList){
  const month = +$('#monthSelect').value;
  const yMonth = +$('#yearSelectMonth').value;
  const yYear  = +$('#yearSelectYear').value;

  const wrap = $('#chartsWrap');
  wrap.innerHTML = '';

  for (const seksi of seksiList){
    // header + dua canvas
    const { header, monthBox, monthCanvas, yearBox, yearCanvas } = makeChartPanel(`Seksi ${seksi}`);
    wrap.appendChild(header);
    wrap.appendChild(monthBox);
    wrap.appendChild(yearBox);

    // BULANAN
    const jm = await api('/api/series/month', { seksi, year:yMonth, month });
    renderHorizontalChart({
      key: `month-${seksi}`,
      ctx: monthCanvas.getContext('2d'),
      labels: jm.labels,
      data: jm.data,
      title: `${seksi} — Bulanan (${yMonth}-${String(month).padStart(2,'0')})`
    });

    // TAHUNAN
    const jy = await api('/api/series/year', { seksi, year:yYear });
    renderHorizontalChart({
      key: `year-${seksi}`,
      ctx: yearCanvas.getContext('2d'),
      labels: jy.labels,
      data: jy.data,
      title: `${seksi} — Tahunan (${yYear})`
    });
  }
}

/* ================== Select helpers (dates / years / months) ================== */
async function fillDates(){
  const j = await api('/api/dates');
  const sel = $('#dateSelect');
  sel.innerHTML = '';
  j.dates.forEach(d => sel.appendChild(el('option', { value:d, textContent:d })));
  // default: terakhir (paling baru)
  if (j.dates.length) sel.value = j.dates[j.dates.length - 1];
}

async function fillYearsMonths(){
  const y1 = await api('/api/years');
  const ys = y1.years.sort((a,b)=>a-b);
  const ySelM = $('#yearSelectMonth');
  const ySelY = $('#yearSelectYear');
  ySelM.innerHTML = ''; ySelY.innerHTML = '';
  ys.forEach(y=>{
    ySelM.appendChild(el('option', { value:y, textContent:y }));
    ySelY.appendChild(el('option', { value:y, textContent:y }));
  });
  if (ys.length){
    ySelM.value = ys[ys.length-1];
    ySelY.value = ys[ys.length-1];
  }

  const mSel = $('#monthSelect');
  mSel.innerHTML = '';
  for (let m=1;m<=12;m++) mSel.appendChild(el('option',{value:m,textContent:m}));
  const now = new Date();
  mSel.value = now.getMonth()+1;
}

/* ================== Main flows ================== */
async function drawForSelectedDate(){
  const date = $('#dateSelect').value;
  const j = await api('/api/by-date', { date });
  lastRows = j.rows || [];

  // badges + table
  renderBadges(j.grand || 0, j.totals || {});
  const seksiList = renderTables(lastRows);

  // jika belum ada list seksi → kosongkan chart wrap
  if (!seksiList.length){
    $('#chartsWrap').innerHTML = '<p>Grafik tidak tersedia karena data kosong.</p>';
  }
  return seksiList;
}

async function init(){
  await fillDates();
  await fillYearsMonths();
  const seksiList = await drawForSelectedDate();

  $('#btnLoad').addEventListener('click', async ()=>{
    const s = await drawForSelectedDate();
    // jangan auto-rerender chart; user klik tombol khusus
  });

  $('#btnLoadCharts').addEventListener('click', async ()=>{
    const s = (lastRows.length ? Array.from(new Set(lastRows.map(r=>r.seksi))).sort() : []);
    await renderCharts(s.length ? s : seksiList);
  });
}

document.addEventListener('DOMContentLoaded', init);
