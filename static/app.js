let charts = {}; // simpan instance Chart per seksi

async function jget(url){
  const r = await fetch(url);
  return r.json();
}

function groupBy(arr, keyFn){
  const map = {};
  arr.forEach(x=>{
    const k = keyFn(x);
    (map[k] ||= []).push(x);
  });
  return map;
}

function fmt(num){
  if(num == null) return "0";
  return Number(num).toLocaleString("id-ID");
}

async function initDates(){
  const j = await jget('/api/dates');
  const sel = document.getElementById('dateSelect');
  sel.innerHTML = '';
  (j.dates || []).forEach(d=>{
    const o = document.createElement('option'); o.value=d; o.textContent=d;
    sel.appendChild(o);
  });
}

async function initYearMonth(){
  // years
  const jy = await jget('/api/years');
  const ys1 = document.getElementById('yearSelectMonth');
  const ys2 = document.getElementById('yearSelectYear');
  [ys1, ys2].forEach(sel=>{
    sel.innerHTML = '';
    (jy.years || []).forEach(y=>{
      const o = document.createElement('option'); o.value=y; o.textContent=y;
      sel.appendChild(o);
    });
  });

  // months (default: pakai yearSelectMonth value)
  await fillMonths();
}

async function fillMonths(){
  const y = document.getElementById('yearSelectMonth').value;
  const jm = await jget('/api/months?year='+encodeURIComponent(y));
  const ms = document.getElementById('monthSelect');
  ms.innerHTML = '';
  const months = jm.months && jm.months.length ? jm.months : [1,2,3,4,5,6,7,8,9,10,11,12];
  months.forEach(m=>{
    const o = document.createElement('option'); o.value=m; o.textContent=m.toString().padStart(2,'0');
    ms.appendChild(o);
  });
}

function renderBadges(rows){
  const badgeWrap = document.getElementById('badges');
  // hapus semua badge seksi lama (selain first “Total Tanggal Ini”)
  Array.from(badgeWrap.querySelectorAll('.badge.seksi')).forEach(el=>el.remove());

  const grand = rows.reduce((a,b)=>a+(b.janjang||0),0);
  document.getElementById('badgeTotal').textContent = 'Total Tanggal Ini: '+fmt(grand);

  const bySeksi = groupBy(rows, r=>r.seksi);
  Object.keys(bySeksi).sort().forEach(seksi=>{
    const tot = bySeksi[seksi].reduce((a,b)=>a+(b.janjang||0),0);
    const span = document.createElement('span');
    span.className = 'badge seksi';
    span.textContent = `${seksi}: ${fmt(tot)}`;
    badgeWrap.appendChild(span);
  });
}

function renderTables(rows){
  const wrap = document.getElementById('tablesWrap');
  wrap.innerHTML = '';

  const bySeksi = groupBy(rows, r=>r.seksi);
  Object.keys(bySeksi).sort().forEach(seksi=>{
    const list = bySeksi[seksi];

    const title = document.createElement('div');
    title.className = 'seksi-title';
    title.textContent = 'Seksi ' + seksi;
    wrap.appendChild(title);

    const table = document.createElement('table');
    table.innerHTML = `
      <thead><tr><th>Nama Pemanen</th><th>Jumlah Janjang</th></tr></thead>
      <tbody></tbody>`;
    const tb = table.querySelector('tbody');

    // urut nama
    const byNama = groupBy(list, r=>r.nama);
    const names = Object.keys(byNama).sort();

    names.forEach(n=>{
      const sum = byNama[n].reduce((a,b)=>a+(b.janjang||0),0);
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${n}</td><td>${fmt(sum)}</td>`;
      tb.appendChild(tr);
    });

    // total
    const tot = list.reduce((a,b)=>a+(b.janjang||0),0);
    const trTot = document.createElement('tr');
    trTot.className = 'total-row';
    trTot.innerHTML = `<td>Total</td><td>${fmt(tot)}</td>`;
    tb.appendChild(trTot);

    wrap.appendChild(table);
  });
}

async function loadByDate(){
  const d = document.getElementById('dateSelect').value;
  const j = await jget('/api/by-date?date='+encodeURIComponent(d));
  if(!j.ok){ alert(j.error||'Gagal'); return; }
  renderBadges(j.rows || []);
  renderTables(j.rows || []);
}

function ensureChart(id){
  const canvas = document.getElementById(id);
  if(!charts[id]) return null;
  charts[id].destroy();
  charts[id] = null;
  return canvas;
}

async function loadCharts(){
  const yearMonth = parseInt(document.getElementById('yearSelectMonth').value,10);
  const month     = parseInt(document.getElementById('monthSelect').value,10);
  const yearOnly  = parseInt(document.getElementById('yearSelectYear').value,10);

  // seksi diambil dari tabel/badges terbaru
  const badgeWrap = document.getElementById('badges');
  const seksiNames = Array.from(badgeWrap.querySelectorAll('.badge.seksi')).map(b=>b.textContent.split(':')[0]);

  const chartsWrap = document.getElementById('chartsWrap');
  chartsWrap.innerHTML = '';

  for(const seksi of seksiNames){
    const boxL = document.createElement('div'); boxL.className='canvas-box';
    const boxR = document.createElement('div'); boxR.className='canvas-box';
    const idMonth = `chart_m_${seksi.replace(/\s+/g,'_')}`;
    const idYear  = `chart_y_${seksi.replace(/\s+/g,'_')}`;
    boxL.innerHTML = `<b>${seksi}</b> — Bulanan (${yearMonth}-${String(month).padStart(2,'0')})<br/><canvas id="${idMonth}" height="180"></canvas>`;
    boxR.innerHTML = `<b>${seksi}</b> — Tahunan (${yearOnly})<br/><canvas id="${idYear}" height="180"></canvas>`;
    chartsWrap.appendChild(boxL);
    chartsWrap.appendChild(boxR);

    const jm = await jget(`/api/series/month?seksi=${encodeURIComponent(seksi)}&year=${yearMonth}&month=${month}`);
    const jy = await jget(`/api/series/year?seksi=${encodeURIComponent(seksi)}&year=${yearOnly}`);

    // Bulanan
    if(jm.ok){
      ensureChart(idMonth);
      const ctx = document.getElementById(idMonth).getContext('2d');
      charts[idMonth] = new Chart(ctx, {
        type: 'line',
        data: { labels: jm.labels, datasets:[{ label:'Janjang', data: jm.data, fill:true }] },
        options: { responsive:true, maintainAspectRatio:false,
          scales:{ y:{ beginAtZero:true } }
        }
      });
    }

    // Tahunan
    if(jy.ok){
      ensureChart(idYear);
      const ctx2 = document.getElementById(idYear).getContext('2d');
      charts[idYear] = new Chart(ctx2, {
        type: 'line',
        data: { labels: jy.labels, datasets:[{ label:'Janjang', data: jy.data, fill:true }] },
        options: { responsive:true, maintainAspectRatio:false,
          scales:{ y:{ beginAtZero:true } }
        }
      });
    }
  }
}

document.addEventListener('DOMContentLoaded', async ()=>{
  await initDates();
  await initYearMonth();
  document.getElementById('yearSelectMonth').addEventListener('change', fillMonths);
  document.getElementById('btnLoad').addEventListener('click', loadByDate);
  document.getElementById('btnLoadCharts').addEventListener('click', loadCharts);

  // auto load awal
  setTimeout(async ()=>{
    await loadByDate();
    await loadCharts();
  }, 200);
});
