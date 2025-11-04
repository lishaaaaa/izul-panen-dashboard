let chart;

async function fetchJSON(url){
  const res = await fetch(url);
  return res.json();
}

async function loadDates(){
  const j = await fetchJSON('/api/dates');
  const sel = document.getElementById('dateSelect');
  sel.innerHTML = '';
  (j.dates || []).forEach(d=>{
    const opt = document.createElement('option');
    opt.value = d; opt.textContent = d;
    sel.appendChild(opt);
  });
}

function renderTotals(totals, grand){
  const wrap = document.getElementById('totals');
  wrap.innerHTML = '';
  Object.entries(totals || {}).forEach(([seksi, val])=>{
    const div = document.createElement('div');
    div.textContent = `${seksi}: ${val}`;
    wrap.appendChild(div);
  });
  document.getElementById('grandTotal').textContent = grand ?? 0;
}

function renderRows(rows){
  const tb = document.getElementById('rowsBody'); tb.innerHTML = '';
  (rows || []).forEach(r=>{
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${r.tanggal_str}</td><td>${r.seksi}</td><td>${r.nama}</td><td>${r.janjang}</td>`;
    tb.appendChild(tr);
  });
}

function renderChart(rows){
  const labels = rows.map(r=>r.nama);
  const data = rows.map(r=>r.janjang);
  const ctx = document.getElementById('chart');
  if(chart){ chart.destroy(); }
  chart = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets:[{ label:'Janjang', data }] },
    options: { responsive:true, maintainAspectRatio:false }
  });
}

async function loadByDate(){
  const date = document.getElementById('dateSelect').value;
  const j = await fetchJSON(`/api/by-date?date=${encodeURIComponent(date)}`);
  if(!j.ok){ alert(j.error || 'Gagal load data'); return; }
  renderTotals(j.totals, j.grand);
  renderRows(j.rows);
  renderChart(j.rows);
}

document.addEventListener('DOMContentLoaded', async ()=>{
  if(document.getElementById('dateSelect')){
    await loadDates();
    document.getElementById('btnLoad').addEventListener('click', loadByDate);
    // auto load pertama kali
    setTimeout(loadByDate, 300);
  }
});
