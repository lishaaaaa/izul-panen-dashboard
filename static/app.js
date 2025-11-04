/* global Chart */
const fmt = new Intl.NumberFormat('id-ID');

// ===== helper DOM =====
const el = (id) => document.getElementById(id);
const tb = (id) => document.getElementById(id);

// ===== endpoints =====
async function getJSON(url) {
  const r = await fetch(url, { credentials: 'include' });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ====== TABEL HARIAN ======
const SEKSI = [
  { key: 'A III', body: 'tb-a', sum: 'sum-a', pill: 'ttl-a' },
  { key: 'B III', body: 'tb-b', sum: 'sum-b', pill: 'ttl-b' },
  { key: 'C II', body: 'tb-c', sum: 'sum-c', pill: 'ttl-c' },
  { key: 'D I', body: 'tb-d', sum: 'sum-d', pill: 'ttl-d' },
];

function fillTable(tbodyId, rows) {
  const tbody = tb(tbodyId);
  tbody.innerHTML = '';
  rows.forEach(r => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${r.nama}</td><td>${fmt.format(r.janjang)}</td>`;
    tbody.appendChild(tr);
  });
}

function sum(rows) {
  return rows.reduce((s, r) => s + (r.janjang || 0), 0);
}

async function loadDaily(dateStr) {
  const data = await getJSON(`/api/daily?date=${encodeURIComponent(dateStr)}`);
  // data = { by_seksi: { 'A III': [...], ... }, total_all, total_per_seksi }
  el('total-ttl').textContent = fmt.format(data.total_all || 0);

  SEKSI.forEach(s => {
    const rows = (data.by_seksi[s.key] || []);
    fillTable(s.body, rows);
    tb(s.sum).textContent = fmt.format(sum(rows));
    el(s.pill).textContent = fmt.format(sum(rows));
  });
}

// ====== GRAFIK ======
const chartRefs = {};

function makeLineConfig(labels, data) {
  return {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Janjang',
        data,
        fill: true,
        borderWidth: 2,
        pointRadius: 2,
        tension: 0.2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,               // << anti “gerak-gerak”
      plugins: {
        legend: { display: false },
        tooltip: { intersect: false, mode: 'index' }
      },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true }
      }
    }
  };
}

function renderChart(canvasId, labels, data) {
  if (chartRefs[canvasId]) {
    chartRefs[canvasId].data.labels = labels;
    chartRefs[canvasId].data.datasets[0].data = data;
    chartRefs[canvasId].update();
  } else {
    chartRefs[canvasId] = new Chart(document.getElementById(canvasId), makeLineConfig(labels, data));
  }
}

async function loadChartsForSection(seksi, yBulanan, mBulanan, yTahunan) {
  const qM = new URLSearchParams({ seksi, year: yBulanan, month: mBulanan });
  const qY = new URLSearchParams({ seksi, year: yTahunan });

  const month = await getJSON(`/api/series_month?${qM}`);
  const year = await getJSON(`/api/series_year?${qY}`);
  // month = { labels:[], data:[] }
  renderChart(`ch-${seksi[0].toLowerCase()}-month`, month.labels, month.data);
  renderChart(`ch-${seksi[0].toLowerCase()}-year`,  year.labels,  year.data);
}

// ====== INIT ======
async function init() {
  // set default tanggal = hari ini (UTC → local)
  const today = new Date();
  const iso = today.toISOString().slice(0,10);
  el('tanggal').value = iso;

  // dropdown bulan & tahun
  const selBln = el('sel-bulan');
  for (let i=1;i<=12;i++){ const o=document.createElement('option'); o.value=i; o.textContent=i; selBln.appendChild(o); }
  selBln.value = today.getMonth()+1;

  const years = await getJSON('/api/list_years'); // { years:[2024,2025,...] }
  const selThBul = el('sel-tahun-bulanan');
  const selThTah = el('sel-tahun-tahunan');
  years.years.forEach(y=>{
    const o1=document.createElement('option'); o1.value=y; o1.textContent=y; selThBul.appendChild(o1);
    const o2=document.createElement('option'); o2.value=y; o2.textContent=y; selThTah.appendChild(o2);
  });
  selThBul.value = today.getFullYear();
  selThTah.value = today.getFullYear();

  // pertama: muat tabel harian
  await loadDaily(iso);

  // pertama: muat grafik semua seksi
  const m = selBln.value, yb = selThBul.value, yt = selThTah.value;
  await Promise.all([
    loadChartsForSection('A III', yb, m, yt),
    loadChartsForSection('B III', yb, m, yt),
    loadChartsForSection('C II', yb, m, yt),
    loadChartsForSection('D I', yb, m, yt),
  ]);

  // tombol2
  el('btn-apply').addEventListener('click', async ()=>{
    await loadDaily(el('tanggal').value);
  });

  el('btn-grafik').addEventListener('click', async ()=>{
    const mm = el('sel-bulan').value;
    const ybm = el('sel-tahun-bulanan').value;
    const yt  = el('sel-tahun-tahunan').value;
    await Promise.all([
      loadChartsForSection('A III', ybm, mm, yt),
      loadChartsForSection('B III', ybm, mm, yt),
      loadChartsForSection('C II', ybm, mm, yt),
      loadChartsForSection('D I', ybm, mm, yt),
    ]);
  });
}

init().catch(err=>console.error(err));
