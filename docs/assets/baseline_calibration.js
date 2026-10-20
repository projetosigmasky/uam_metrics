/* Independent baseline-calibration view; no external chart or map dependency. */
(() => {
  const data = window.__BASELINE_CALIBRATION__;
  const escape = (value) => String(value).replace(/[&<>"']/g, (c) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
  const number = (value) => value === null || value === undefined ? "—" : Number(value).toLocaleString("pt-BR", {maximumFractionDigits: 2});
  const status = (estimate) => estimate.status === "no_observed_use" ? "Sem uso observado" : estimate.status === "insufficient_full_windows" ? "Cobertura insuficiente" : estimate.stable_at_final ? "Estável no critério" : "Estabilidade não confirmada";
  function chart(points, {xLabel, yLabel, color = "#2563eb"}) {
    const valid = points.filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
    if (!valid.length) return '<p class="cal-note">Dados insuficientes para esta curva.</p>';
    const width = 840, height = 280, left = 80, top = 20, bottom = 55, right = 25;
    const xmin = Math.min(...valid.map(p => p.x)), xmax = Math.max(...valid.map(p => p.x));
    const ymax = Math.max(1, ...valid.flatMap(p => [p.y, ...(p.ci || [])])) * 1.1;
    const x = value => left + (value - xmin) / Math.max(1, xmax - xmin) * (width - left - right);
    const y = value => height - bottom - value / ymax * (height - top - bottom);
    const ticks = Array.from({length: 5}, (_, i) => ymax * i / 4).map(value => `<line x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}" stroke="#e2e8f0"/><text x="${left-8}" y="${y(value)+5}" text-anchor="end">${number(value)}</text>`).join("");
    const intervals = valid.filter(p => p.ci).map(p => `<line x1="${x(p.x)}" x2="${x(p.x)}" y1="${y(p.ci[0])}" y2="${y(p.ci[1])}" stroke="${color}" stroke-width="3" opacity=".25"/>`).join("");
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(yLabel)} por ${escape(xLabel)}">${ticks}${intervals}<polyline points="${valid.map(p => `${x(p.x)},${y(p.y)}`).join(" ")}" fill="none" stroke="${color}" stroke-width="2"/>${valid.map(p => `<circle cx="${x(p.x)}" cy="${y(p.y)}" r="3" fill="${color}"/><text x="${x(p.x)}" y="${height-bottom+20}" text-anchor="middle">${p.label ? escape(p.label) : p.x % 5 === 0 || p.x === xmin || p.x === xmax ? p.x : ""}</text>`).join("")}<text x="${width/2}" y="${height-8}" text-anchor="middle">${escape(xLabel)}</text><text x="18" y="${height/2}" transform="rotate(-90 18 ${height/2})" text-anchor="middle">${escape(yLabel)}</text></svg>`;
  }
  function initialize(root) {
    if (!data?.scenarios) {
      root.innerHTML = '<div class="cal-empty"><h3>Calibração dos quatro cenários-base</h3><p>Os resultados de C1.1, C1.2, C2.1 e C2.2 estarão disponíveis após o processamento dos logs concluídos.</p><p>Comparação de janelas de 5, 15 e 60 minutos, histogramas e estabilidade entre réplicas.</p></div>';
      return;
    }
    let scenarioKey = "C1.1", policy = "positive", windowSeconds = "300", waypoint = null;
    root.innerHTML = `<h2>Fluxo observado nos cenários-base</h2><div class="cal-controls"><label>Cenário da calibração<select data-cal="scenario">${Object.keys(data.scenarios).map(k => `<option>${escape(k)}</option>`).join("")}</select></label><label>Janelas consideradas<select data-cal="policy"><option value="positive">Somente positivas</option><option value="all">Todas as completas, incluindo zeros</option></select></label><label>Janela da análise detalhada<select data-cal="window"><option value="300">5 minutos</option><option value="900">15 minutos</option><option value="3600">60 minutos</option></select></label><label>Waypoint físico<select data-cal="waypoint"></select></label></div><div data-cal="output"></div>`;
    const waypointSelect = root.querySelector('[data-cal="waypoint"]');
    function render(updateWaypoints = false) {
      const scenario = data.scenarios[scenarioKey];
      if (updateWaypoints) {
        waypointSelect.innerHTML = scenario.resources.map(r => `<option value="${escape(r.waypoint_id)}">${escape(r.label)} · ${escape(r.network)} · ${escape(r.waypoint_id)}</option>`).join("");
        waypoint = (scenario.resources.find(r => r.estimates[`${windowSeconds}:${policy}`].status === "observed") || scenario.resources[0])?.waypoint_id;
        waypointSelect.value = waypoint || "";
      }
      const key = `${windowSeconds}:${policy}`;
      const estimates = scenario.resources.map(r => r.estimates[key]);
      const selected = scenario.resources.find(r => r.waypoint_id === waypoint);
      const estimate = selected?.estimates[key];
      const trace = estimate?.convergence.map(point => Array.isArray(point) ? Object.fromEntries(data.trace_columns.map((column, i) => [column, point[i]])) : point) || [];
      const ciLevel = number(data.criteria.confidence_level * 100);
      const cards = [["Réplicas", scenario.replica_count], ["Waypoints com estimativa", estimates.filter(e => e.status === "observed").length], ["Sem uso observado", estimates.filter(e => e.status === "no_observed_use").length], ["Estáveis no critério", estimates.filter(e => e.stable_at_final).length]];
      root.querySelector('[data-cal="output"]').innerHTML = `<div class="cal-cards">${cards.map(([label, value]) => `<div class="cal-card">${label}<strong>${number(value)}</strong></div>`).join("")}</div>
        <p class="cal-note">${scenario.passage_source === "native" ? "Passagens nativas validadas" : "Estimativa geométrica de passagens"}. Referência empírica P95, em operações/h. Não demonstra capacidade operacional máxima da rede.</p>
        <figure class="cal-figure"><h3>Distribuição do P95 entre waypoints físicos</h3><img src="${escape(scenario.charts[`${policy}:histogram`])}" alt="Histogramas da quantidade de waypoints por referência P95 para 5, 15 e 60 minutos" /></figure>
        <figure class="cal-figure"><h3>Distribuição acumulada dos waypoints</h3><img src="${escape(scenario.charts[`${policy}:cdf`])}" alt="Percentual acumulado dos waypoints por referência P95 nas três janelas" /></figure>
        ${selected ? `<figure class="cal-figure"><h3>${escape(selected.label)}: efeito da janela</h3>${chart(data.windows_seconds.map(w => ({x: w/60, y: selected.estimates[`${w}:${policy}`].p95_per_hour, label: `${w/60} min`, ci: selected.estimates[`${w}:${policy}`].ci95})), {xLabel: "Tamanho da janela (min)", yLabel: "P95 (operações/h)"})}</figure>
        <figure class="cal-figure"><h3>P95 acumulado · ${escape(selected.label)} · ${Number(windowSeconds)/60} min</h3>${chart(trace.map(p => ({x: p.replicas, y: p.p95_per_hour, ci: p.ci95})), {xLabel: "Réplicas acumuladas", yLabel: "P95 (operações/h)"})}<figcaption>Intervalos de confiança de ${ciLevel}% por bootstrap de réplicas. ${status(estimate)}.</figcaption></figure>
        <figure class="cal-figure"><h3>Média acumulada do throughput · ${escape(selected.label)}</h3>${chart(trace.map(p => ({x: p.replicas, y: p.mean_per_hour, ci: p.mean_ci95})), {xLabel: "Réplicas acumuladas", yLabel: "Média (operações/h)", color: "#0f766e"})}<figcaption>Média das janelas reunidas. ${estimate.mean_stable_at_final ? "Estável no critério de precisão." : "Estabilidade da média não confirmada."}</figcaption></figure>` : ""}
        <details class="cal-details"><summary>Ver detalhes e tabela comparativa</summary><p class="cal-note">Cada ponto físico/pista/altitude permanece independente. P95 com método higher, calculado sobre as janelas reunidas das réplicas. Janelas fixas alinhadas em zero e intervalos semiabertos. Períodos incompletos são excluídos. Recursos sem uso não são classificados como capacidade zero.</p><p class="cal-note">Estabilidade do P95: mínimo de ${data.criteria.minimum_replications} réplicas, IC de ${ciLevel}%, tolerância relativa de ${number(data.criteria.relative_tolerance*100)}% ou absoluta de ${number(data.criteria.absolute_tolerance_per_hour)} operações/h, e ${data.criteria.confirmation_window} avaliações consecutivas. Não equivale a comprovação de segurança ou suficiência para outros KPIs.</p><div class="cal-table-wrap"><table class="cal-table"><thead><tr><th>Waypoint / rede / recurso físico</th><th>P95 · 5 min (op/h)</th><th>P95 · 15 min (op/h)</th><th>P95 · 60 min (op/h)</th><th>Média · janela selecionada (op/h)</th><th>P95 (op/janela)</th><th>Réplicas com janela completa</th><th>Situação · janela selecionada</th></tr></thead><tbody>${scenario.resources.map(r => `<tr><td>${escape(r.label)} · ${escape(r.network)}<br><small>${escape(r.waypoint_id)}</small></td>${data.windows_seconds.map(w => `<td>${number(r.estimates[`${w}:${policy}`].p95_per_hour)}</td>`).join("")}<td>${number(r.estimates[key].mean_per_hour)}</td><td>${number(r.estimates[key].p95_operations_per_window)}</td><td>${number(r.estimates[key].replicas_with_full_windows)}</td><td>${status(r.estimates[key])}</td></tr>`).join("")}</tbody></table></div><div class="cal-downloads"><a href="assets/data/baseline_calibration/comparison.csv" download>Baixar comparação CSV</a><a href="assets/data/baseline_calibration/replica_metrics.csv" download>Baixar métricas por réplica CSV</a><a href="assets/data/baseline_calibration/convergence.csv" download>Baixar convergência CSV</a><a href="assets/data/baseline_calibration/calibration.json" download>Baixar resultados e cobertura JSON</a></div></details>`;
    }
    root.addEventListener("change", event => {
      const control = event.target.dataset.cal;
      if (control === "scenario") scenarioKey = event.target.value;
      if (control === "policy") policy = event.target.value;
      if (control === "window") windowSeconds = event.target.value;
      if (control === "waypoint") waypoint = event.target.value;
      render(control === "scenario");
    });
    render(true);
  }
  document.addEventListener("DOMContentLoaded", () => document.querySelectorAll("[data-baseline-calibration]").forEach(initialize));
})();
