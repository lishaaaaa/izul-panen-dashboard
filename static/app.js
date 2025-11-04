(() => {
  const $ = (q, el=document) => el.querySelector(q);
  const $$ = (q, el=document) => Array.from(el.querySelectorAll(q));

  const bulanSel = $("#bulanSel");
  const tahunBulananSel = $("#tahunBulananSel");
  const tahunTahunanSel = $("#tahunTahunanSel");
  const btn = $("#btnRender");

  let charts = []; // simpan instances Chart.js supaya bisa destroy saat re-render

  function fmtTicksLinear(value){
    try { return new Intl.NumberFormat('id-ID').format(value); }
    catch(e) { return value; }
  }

  function makeLineChart(ctx, labels, values, title){
    if (ctx._chart){ ctx._chart.destroy(); }
    const data = {
      labels,
      datasets: [{
        label: 'Janjang',
        data: values,
        tension: 0.25,
        fill: true
      }]
    };
    const chart = new Chart(ctx, {
      type: 'line',
      data,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, title: { display: false, text: title } },
        scales: {
          y: { ticks: { callback: fmtTicksLinear }, beginAtZero: true }
        }
      }
    });
    ctx._chart = chart;
    charts.push(chart);
  }

  async function fetchSeries({seksi, month, year}){
    const q = new URLSearchParams({ seksi, month, year });
    const r = await fetch(`/api/series?${q.toString()}`, { credentials:'same-origin' });
    if (!r.ok) return { daily: [], monthly: [] };
    return await r.json();
  }

  async function renderAll(){
    const month = parseInt(bulanSel.value, 10);
    const yBulanan = parseInt(tahunBulananSel.value, 10);
    const yTahunan = parseInt(tahunTahunanSel.value, 10);

    const canvases = $$("#chartGrid canvas");
    charts.forEach(c => c.destroy());
    charts = [];

    for (const cv of canvases){
      const seksi = cv.dataset.seksi;
      const kind  = cv.dataset.kind; // "bulan" atau "tahun"
      cv.height = 320;

      const series = await fetchSeries({ seksi, month, year: (kind==="bulan" ? yBulanan : yTahunan) });
      if (kind === "bulan"){
        const labels = series.daily.map(d => d.x);
        const values = series.daily.map(d => d.y);
        makeLineChart(cv.getContext("2d"), labels, values, `${seksi} — Bulanan`);
      } else {
        const labels = series.monthly.map(d => d.x);
        const values = series.monthly.map(d => d.y);
        makeLineChart(cv.getContext("2d"), labels, values, `${seksi} — Tahunan`);
      }
    }
  }

  // set nilai awal dari server
  if (window._chartOptions){
    bulanSel.value = window._chartOptions.month;
    tahunBulananSel.value = window._chartOptions.yearBulanan;
    tahunTahunanSel.value = window._chartOptions.yearTahunan;
  }

  $("#btnRender").addEventListener("click", renderAll);
  renderAll();
})();
