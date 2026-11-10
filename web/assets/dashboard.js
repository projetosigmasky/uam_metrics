const state = {runs: [], runSummaries: [], comparison: null, activeRunIndex: 0, activeDayKey: null, activeKpa: "maps"};
const pendingRunLoads = new Map();
const runPartReceivers = new Map();
const cachedRunIndices = new Map();

window.__UAM_RUN_PART__ = (token, index, count, text) => {
  const receiver = runPartReceivers.get(token);
  if (!receiver || count !== receiver.length || !Number.isInteger(index) || index < 0 || index >= count || typeof text !== "string") {
    throw new Error("Fragmento de cenário inválido");
  }
  receiver[index] = text;
};

function loadRunPart(path) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = path;
    script.onload = () => { script.remove(); resolve(); };
    script.onerror = () => { script.remove(); reject(new Error(`Falha ao carregar ${path}`)); };
    document.head.appendChild(script);
  });
}

function loadRunDetails(index) {
  if (pendingRunLoads.has(index)) return pendingRunLoads.get(index);
  const summary = state.runs[index];
  const fragments = new Array(summary.data_parts.length).fill(null);
  runPartReceivers.set(summary.data_token, fragments);
  const promise = Promise.allSettled(summary.data_parts.map(loadRunPart)).then(results => {
    const failed = results.find(result => result.status === "rejected");
    if (failed) throw failed.reason;
    if (fragments.some(part => part === null)) throw new Error("Pacote de cenário incompleto");
    const run = JSON.parse(fragments.join(""));
    if (run.id !== summary.id || run.metadata?.scenario_key !== summary.metadata?.scenario_key) throw new Error("Identidade do cenário divergente");
    if (state.runs[index] !== summary || state.activeRunIndex !== index) return;
    state.runs[index] = {...run, data_token: summary.data_token};
    cachedRunIndices.set(index, true);
    // Keep at most two complete scenarios; summaries stay available for filters
    // and cross-scenario stability comparisons.
    for (const cached of cachedRunIndices.keys()) {
      if (cachedRunIndices.size <= 2) break;
      if (cached === state.activeRunIndex || cached === index) continue;
      state.runs[cached] = state.runSummaries[cached];
      cachedRunIndices.delete(cached);
    }
  }).finally(() => {
    runPartReceivers.delete(summary.data_token);
    pendingRunLoads.delete(index);
  });
  pendingRunLoads.set(index, promise);
  return promise;
}

const scenarioFilters = [
  {id: "corridor-select", key: "airspace", options: [["shared_reh", "Compartilhamento de REH"], ["dedicated_uam", "Corredores UAM dedicados"]]},
  {id: "management-select", key: "management", options: [["none", "Sem gestão estratégica"], ["dcb_milp_waypoint", "DCB por waypoint", "Balanceamento demanda-capacidade (DCB)"], ["dcb_milp_grid", "DCB por quadrícula", "Balanceamento demanda-capacidade (DCB)"], ["micro_milp", "Desconflito (Chen)", "Desconflito de trajetórias"], ["micro_moolchandani", "Desconflito (Moolchandani)", "Desconflito de trajetórias"]]},
  {id: "condition-select", key: "condition", options: [["nominal", "Nominal"], ["disturbed", "Fora da condição nominal"]]},
  {id: "vertiports-select", key: "vertiports", options: [["0", "C0 · somente helicópteros"], ["6", "Estágio inicial (6 vertiportos)"], ["12", "Estágio intermediário (12 vertiportos)"], ["", "Não informado"]]},
  {id: "separation-select", key: "separation_seconds", options: [["", "Não se aplica"], ["11", "11 s · LoWC 0,3 NM"], ["23", "23 s · LoWC 0,6 NM"], ["38", "38 s · LoWC 1,0 NM"]]},
];

function runDimensions(run) {
  return run.metadata?.scenario_dimensions || window.__UAM_SCENARIO_CATALOG__?.scenarios?.find(row => row.scenario === run.metadata?.scenario_key) || null;
}

function filterValue(dimensions, key) {
  return String(dimensions?.[key] ?? "");
}

function normalizeModel(model) {
  if (model.runs) return model;
  if (!model.dashboard) return {...model, runs: []};
  return {...model, runs: [{id: "run_1", name: model.dashboard.source_log,
    dashboard: model.dashboard, metadata: model.dashboard.metadata}],
    comparison: model.comparison || {days: []}};
}

function renderComparison(model) {
  const days = model.comparison?.days || [];
  state.activeDayKey = state.activeDayKey || days[0]?.day_key || null;
  const daySelect = document.getElementById("day-select");
  daySelect.innerHTML = days
    .map((day) => `<option value="${escapeHtml(day.day_key)}">${escapeHtml(day.day_label)}</option>`)
    .join("");
  daySelect.value = state.activeDayKey || "";
  daySelect.disabled = days.length <= 1;
  document.getElementById("day-filter").hidden = days.length <= 1;
  populateRunSelect();

}

function populateRunSelect() {
  const select = document.getElementById("run-select");
  const day = state.comparison?.days?.find((item) => item.day_key === state.activeDayKey);
  const rows = day?.rows || state.runs.map((run, index) => ({ run_index: index, variant_label: run.name }));
  if (!rows.some((row) => row.run_index === state.activeRunIndex)) {
    state.activeRunIndex = rows[0]?.run_index ?? 0;
  }
  select.innerHTML = rows
    .map((row) => `<option value="${row.run_index}">${escapeHtml(row.variant_label)}</option>`)
    .join("");
  select.value = String(state.activeRunIndex);
  select.disabled = rows.length <= 1;
  populateScenarioFilters();
  renderSelectedRun();
}

function populateScenarioFilters(changedIndex = -1) {
  const day = state.comparison?.days?.find(item => item.day_key === state.activeDayKey);
  const indices = day?.rows?.map(row => row.run_index) || state.runs.map((_, index) => index);
  let candidates = indices.filter(index => runDimensions(state.runs[index]));
  const fallback = !candidates.length;
  document.getElementById("legacy-run-filter").hidden = !fallback;
  const previous = runDimensions(state.runs[state.activeRunIndex]);
  scenarioFilters.forEach((filter, index) => {
    const select = document.getElementById(filter.id);
    const available = new Set(candidates.map(i => filterValue(runDimensions(state.runs[i]), filter.key)));
    const desired = changedIndex >= 0 && index <= changedIndex ? select.value : filterValue(previous, filter.key);
    const value = available.has(desired) ? desired : filter.options.find(([value]) => available.has(value))?.[0] ?? "";
    const groups = new Map();
    for (const [option, name, group] of filter.options) {
      const label = option === "" && filter.key === "separation_seconds" && candidates.some(i => runDimensions(state.runs[i]).management?.startsWith("micro_"))
        ? "Não informado" : name;
      const enabled = available.has(option);
      const suffix = enabled ? "" : filter.key === "vertiports" && option === "0" ? " · aguardando dados" : " · indisponível";
      const item = `<option value="${option}"${enabled ? "" : " disabled"}>${label}${suffix}</option>`;
      groups.set(group, (groups.get(group) || "") + item);
    }
    select.innerHTML = [...groups].map(([group, items]) => group ? `<optgroup label="${group}">${items}</optgroup>` : items).join("");
    select.value = value;
    select.disabled = available.size <= 1;
    select.title = "Combinações disponíveis nos resultados processados";
    candidates = candidates.filter(i => filterValue(runDimensions(state.runs[i]), filter.key) === value);
  });
  if (candidates.length) {
    if (!candidates.includes(state.activeRunIndex)) state.activeRunIndex = candidates[0];
    document.getElementById("run-select").value = String(state.activeRunIndex);
  }
  const run = state.runs[state.activeRunIndex];
  setText("scenario-selection", run ? `Cenário ${run.metadata?.scenario_key || run.name} · ${run.replica_count || run.density?.replica_count || 1} réplicas disponíveis` : "Nenhum resultado disponível");
}

function stabilitySvg(metric) {
  const rows = metric.trace.filter(p => p.mean != null);
  if (!rows.length) return "";
  const ys = rows.flatMap(p => p.ci95 ? [...p.ci95, p.mean] : [p.mean]);
  const min = Math.min(...ys), max = Math.max(...ys), span = max-min || Math.abs(max)*.1 || 1;
  const x = p => 70 + (p.replicas-1) / Math.max(1,metric.total_count-1)*610;
  const y = v => 160-(v-min)/span*125;
  const axis = v => Math.abs(v)>1e5 || (v!==0 && Math.abs(v)<.001) ? Number(v).toExponential(2) : formatNumber(v,3);
  const line = rows.map(p => `${x(p)},${y(p.mean)}`).join(" ");
  const bands = rows.filter(p=>p.ci95);
  const polygon = [...bands.map(p=>`${x(p)},${y(p.ci95[0])}`),...bands.slice().reverse().map(p=>`${x(p)},${y(p.ci95[1])}`)].join(" ");
  const confirmation = metric.confirmed_at_n == null ? "" : `<line x1="${x({replicas:metric.confirmed_at_n})}" x2="${x({replicas:metric.confirmed_at_n})}" y1="25" y2="160" stroke="#15803d" stroke-dasharray="5 3"/><text x="80" y="18">Confirmação em ${metric.confirmed_at_n} réplicas</text>`;
  return `<svg class="stability-plot" viewBox="0 0 720 210" role="img" aria-label="Média acumulada, intervalo bootstrap de 95% e critério por prefixo"><text x="5" y="35">${axis(min+span)}</text><text x="5" y="165">${axis(min)}</text><line x1="70" y1="160" x2="680" y2="160" stroke="#64748b"/><polygon points="${polygon}" fill="#93c5fd" opacity=".5"/><polyline points="${line}" fill="none" stroke="#2563eb" stroke-width="2"/>${rows.filter(p=>p.criterion_met).map(p=>`<circle cx="${x(p)}" cy="${y(p.mean)}" r="3" fill="#15803d"/>`).join("")}${confirmation}<text x="70" y="180">1</text><text x="665" y="180">${metric.total_count}</text><text x="210" y="202">Réplicas incorporadas (ordem do índice)</text></svg>`;
}

function stabilityMetricHtml([key, m]) {
  const status = m.status==="confirmed" ? `Estabilidade confirmada: trecho a partir de ${m.stable_from_n} réplicas; confirmação obtida em ${m.confirmed_at_n}.` : m.status==="unavailable" ? "Indisponível; sem zeros imputados." : m.status==="configuration_or_geometry_no_inference" ? "Configuração/geometria: inferência estatística não se aplica." : m.status==="constant_observed_no_inference" ? `Valores constantes observados; estabilidade inferencial não confirmada com ${m.total_count} réplicas.` : `Estabilidade não confirmada com ${m.total_count} réplicas.`;
  return `<details class="stability-metric"><summary>${escapeHtml(stabilityLabels[key] || key)} · ${m.valid_count}/${m.total_count} válidas</summary><p>${status}${m.first_confirmed_at_n != null && m.status!=="confirmed" ? ` Houve confirmação anterior em ${m.first_confirmed_at_n}, sem manutenção no final.` : ""}</p>${stabilitySvg(m)}</details>`;
}

function formatNumber(value, digits = 0) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return Number(value).toLocaleString("pt-BR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

const kpaNames = {safety: "Segurança", efficiency: "Eficiência", capacity: "Capacidade", predictability: "Previsibilidade", equity: "Equidade"};
// Only explicitly listed Product III KPIs may cross the presentation boundary.
// The raw publication and internal audit fields remain unchanged.
const kpiSeries = {
  loss_of_separation: [["safety.lowc_events", "eventos"], ["safety.lowc_per_flight_hour", "eventos/h de voo"]],
  nmac: [["safety.nmac_events", "eventos"]],
  estimated_mac: [["safety.expected_mac", "eventos estimados"]],
  safety_level: [["safety.expected_mac_per_100k_flight_hours", "MAC/100.000 h de voo"]],
  tls: [], risk_ratio: [],
  ground_delay: [["efficiency.ground_delay.mean_ground_delay_s", "s"]],
  airborne_delay: [["efficiency.airborne_delay.mean_airborne_delay_s", "s"]],
  total_delay: [["efficiency.total_delay.mean_total_delay_s", "s"]],
  flight_time: [["efficiency.mean_flight_time_min", "min"]],
  distance: [["efficiency.mean_distance_nm", "NM"]],
  horizontal_efficiency: [
    ["efficiency.trajectory_conformity.mean_planned_horizontal_inefficiency_ratio", "razão planejada"],
    ["efficiency.trajectory_conformity.mean_executed_horizontal_inefficiency_ratio", "razão executada"]],
  trajectory_conformity: [["efficiency.trajectory_conformity.mean_trajectory_conformity_ratio", "TC (razão)"],
    ["efficiency.trajectory_conformity.mean_additional_distance_m", "ED (m)"]],
  throughput: [], practical_capacity: [], utilization: [],
  flight_time_variability: [], punctuality: [], relative_degradation: [],
  group_mean_delay: [], delay_dispersion: [], delay_cv: []
};
const resourceSeries = {
  throughput: "Pico (ops/h)", practical_capacity: "Referência P95 (ops/h)", utilization: "Utilização (razão)"
};
const stabilityLabels = {};
function publicCatalog(panel) {
  return (window.__UAM_METRIC_CATALOG__?.metrics || []).filter(m => m.kpa === kpaNames[panel] && Object.hasOwn(kpiSeries, m.id));
}
function valueAt(object, path) {
  let value = object;
  for (const part of path.split(".")) {
    if (value?.available === false) return null;
    value = value?.[part];
  }
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function numericValue(dashboard, path) {
  // A zero-exposure rate is undefined, even if a legacy payload stores zero.
  if (path.includes("flight_hour") && path !== "safety.tls_target_per_flight_hour" && !(dashboard.efficiency?.total_flight_hours > 0)) return null;
  return valueAt(dashboard, path);
}
function displayValue(value, unit) {
  if (value == null) return "Indisponível";
  const count = unit === "eventos";
  // Preserve the scale of very small nonzero estimates and rates.
  const number = !count && value !== 0 && Math.abs(value) < .01
    ? value.toExponential(2).replace(".", ",") : formatNumber(value, count ? 0 : 2);
  return `${number} ${unit}`.trim();
}
function comparisonRow() {
  return state.comparison?.days?.flatMap(day => day.rows || []).find(row => row.run_index === state.activeRunIndex);
}
function renderMetrics(dashboard) {
  const run = state.runs[state.activeRunIndex];
  for (const panel of Object.keys(kpaNames)) {
    document.getElementById(`kpis-${panel}`).innerHTML = publicCatalog(panel).map(metric => {
      let values = (kpiSeries[metric.id] || []).map(([path, unit]) => {
        const value = numericValue(dashboard, path);
        return `<p>${escapeHtml(displayValue(value, unit))}</p>`;
      }).join("");
      if (metric.id === "tls") {
        const target = numericValue(dashboard, "safety.tls_target_per_flight_hour");
        const rate = numericValue(dashboard, "safety.expected_mac_per_100k_flight_hours");
        values = `<p>${escapeHtml(displayValue(target == null ? null : target * 100000, "MAC/100.000 h de voo"))}</p><p>${rate == null || target == null ? "Comparação indisponível" : rate <= target * 100000 ? "Nível de Segurança ≤ TLS" : "Nível de Segurança > TLS"}</p>`;
      }
      if (metric.id === "risk_ratio") values = `<p>${escapeHtml(displayValue(valueAt(comparisonRow(), "risk_ratio_vs_reference"), ""))}</p>`;
      if (resourceSeries[metric.id]) values = "<p>Resultados por recurso na tabela abaixo.</p>";
      if (!values) values = "<p>Indisponível</p><small>Sem cálculo ou dados disponíveis para este indicador.</small>";
      const estimate = metric.id === "estimated_mac" ? "<small>Estimativa probabilística pela Eq. 3.2.</small>" : "";
      return `<article class="metric" data-kpi="${metric.id}"><h3>${escapeHtml(metric.name)}</h3><div class="kpi-value">${values}</div>${estimate}<small>${escapeHtml(metric.pdf_reference)}</small></article>`;
    }).join("");
  }
}
function replicaSvg(values, label) {
  const rows = values.map((value, index) => ({value, index})).filter(row => typeof row.value === "number" && Number.isFinite(row.value));
  if (!rows.length) return "<p>Gráfico indisponível: sem valores individuais deste KPI.</p>";
  const min = Math.min(...rows.map(row => row.value)), max = Math.max(...rows.map(row => row.value));
  const span = max - min || Math.abs(max) * .1 || 1;
  const x = index => 75 + index / Math.max(1, values.length - 1) * 595;
  const y = value => 160 - (value - min) / span * 125;
  // Show observations individually; missing replicas never become zero or interpolated lines.
  return `<svg class="stability-plot" viewBox="0 0 720 210" role="img" aria-label="${escapeHtml(label)} por réplica"><text x="5" y="35">${escapeHtml(displayValue(min + span, ""))}</text><text x="5" y="165">${escapeHtml(displayValue(min, ""))}</text><line x1="75" y1="160" x2="670" y2="160" stroke="#64748b"/>${rows.map(row => `<circle cx="${x(row.index)}" cy="${y(row.value)}" r="3" fill="#2563eb"/>`).join("")}<text x="75" y="180">1</text><text x="650" y="180">${values.length}</text><text x="290" y="202">Réplica</text></svg>`;
}
function renderCharts(dashboard) {
  const run = state.runs[state.activeRunIndex];
  for (const panel of Object.keys(kpaNames)) {
    document.getElementById(`charts-${panel}`).innerHTML = publicCatalog(panel).flatMap(metric =>
      publicStabilityEntries(run, metric).filter(([key, data]) => (kpiSeries[metric.id] || []).some(([path]) => path === key) && Array.isArray(data.values))
        .map(([key, data]) => `<article class="chart-card"><h3>${escapeHtml(stabilityLabels[key])}</h3>${replicaSvg(data.values, stabilityLabels[key])}</article>`)
    ).join("");
  }
  const target = document.getElementById("charts-efficiency");
  const available = run.analysis_schema_version === 1 && run.aggregate_analysis?.schema_version === 1 && dashboard.chart_aggregation_version === 1;
  const charts = [["distance_histogram", "Distância de Voo"], ["trajectory_conformity", "Conformidade da Trajetória"]];
  target.innerHTML += charts.map(([key, title]) => {
    const src = available ? dashboard.charts?.[key] : null;
    // Source paths are generated by the pipeline and must remain local assets.
    const safe = typeof src === "string" && /^assets\/[\w./-]+\.png$/.test(src) && !src.includes("..");
    return `<article class="chart-card"><h3>${title}</h3>${safe ? `<img src="${escapeHtml(src)}" alt="${title}: distribuição média por réplica" /><p>Média por réplica válida; faixa mínimo–máximo entre réplicas.</p>` : "<p>Gráfico indisponível neste cenário.</p>"}</article>`;
  }).join("");
}
function renderCapacity(dashboard) {
  const rows = [];
  for (const [key, label] of [["od_pairs", "Par OD"], ["trajectory_groups", "Grupo de trajetória"], ["planned_reh", "Trecho REH"]]) {
    const group = dashboard.capacity?.throughput?.[key];
    if (!group?.available) continue;
    for (const resource of group.top_resources || []) {
      rows.push(`<tr><td>${escapeHtml(label)}</td><td>${escapeHtml(resource.label || resource.resource_id)}</td><td>${displayValue(valueAt(resource, "peak_throughput_per_hour"), "ops/h")}</td><td>${displayValue(valueAt(resource, "capacity_reference_per_hour") ?? valueAt(group, "capacity_reference_per_hour"), "ops/h")}</td><td>${displayValue(valueAt(resource, "utilization_peak"), "")}</td></tr>`);
    }
  }
  document.getElementById("charts-capacity").innerHTML = `<div class="table-wrap"><table class="comparison-table"><thead><tr><th>Tipo de recurso</th><th>Recurso</th><th>Throughput por Recurso (pico)</th><th>Capacidade Prática de Recurso (P95)</th><th>Utilização de Recurso (pico)</th></tr></thead><tbody>${rows.join("") || '<tr><td colspan="5">Indicadores indisponíveis neste cenário.</td></tr>'}</tbody></table><p>P95 calculado por réplica e agregado por média. Throughput baseado em inícios de voo e atribuição à rota planejada.</p></div>`;
}
function publicStabilityEntries(run, metric) {
  const panels = run.stability?.panels || {};
  const entries = Object.entries(Object.assign({}, ...Object.values(panels)));
  const paths = new Map(kpiSeries[metric.id] || []);
  // Legacy packages preserve executed HFE in percent, not as a ratio.
  if (metric.id === "horizontal_efficiency" && !entries.some(([key]) => key === "efficiency.trajectory_conformity.mean_executed_horizontal_inefficiency_ratio")) {
    paths.set("efficiency.mean_horizontal_inefficiency_pct", "% executada");
  }
  return entries.filter(([key]) => paths.has(key) || (resourceSeries[metric.id] && /^(od_pairs|trajectory_groups|planned_reh) · /.test(key) && key.endsWith(` · ${resourceSeries[metric.id]}`)))
    .map(([key, data]) => {
      const label = paths.has(key) ? `${metric.name} (${paths.get(key)})` : `${metric.name} · ${key.split(" · ").slice(0, -1).join(" · ")}`;
      stabilityLabels[key] = label;
      return [key, data];
    });
}
function renderStability() {
  const run = state.runs[state.activeRunIndex];
  const valid = run.analysis_schema_version === 1 && run.stability?.schema_version === 1;
  const method = "<p>Média acumulada por réplica; IC bootstrap de 95%, 1.000 reamostragens. Mínimo de 30 réplicas válidas, tolerância relativa de 5% e confirmação por 15 prefixos consecutivos. Pontos verdes: critério atendido. Constantes e zeros observados não confirmam estabilidade inferencial.</p>";
  for (const panel of Object.keys(kpaNames)) {
    const content = publicCatalog(panel).map(metric => {
      const entries = valid ? publicStabilityEntries(run, metric) : [];
      // TLS is a target, not a stochastic outcome. Do not substitute TLS margin.
      if (metric.id === "tls") return `<h3>TLS</h3><p>Nível-alvo de referência; a estabilização é avaliada no Nível de Segurança.</p>`;
      return entries.length ? entries.map(stabilityMetricHtml).join("") : `<h3>${escapeHtml(metric.name)}</h3><p>Estabilidade indisponível: sem série individual deste KPI neste cenário.</p>`;
    }).join("");
    document.getElementById(`stability-${panel}`).innerHTML = method + content;
  }
}
function activateKpa(kpa) {
  state.activeKpa = kpa === "maps" || Object.hasOwn(kpaNames, kpa) ? kpa : "maps";
  document.querySelectorAll("[data-kpa-tab]").forEach(button => {
    const active = button.dataset.kpaTab === state.activeKpa;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  document.querySelectorAll("[data-kpa-panel]").forEach(panel => { panel.hidden = panel.dataset.kpaPanel !== state.activeKpa; });
  document.querySelectorAll("[data-kpi-context]").forEach(node => { node.hidden = state.activeKpa === "maps"; });
  updateMapsVisibility();
}
function renderDashboard(model) {
  const normalized = normalizeModel(model);
  // Preserve the existing exclusion of retired scenario definitions.
  const retained = normalized.runs.filter(run => (run.metadata?.scenario_key && !/^C[12]$/.test(run.metadata.scenario_key)) || run.metadata?.experiment_family === "bimtra");
  const remap = new Map(retained.map((run, index) => [normalized.runs.indexOf(run), index]));
  state.runs = retained;
  state.runSummaries = [...retained];
  cachedRunIndices.clear();
  state.comparison = {...normalized.comparison, days: (normalized.comparison?.days || []).map(day => ({...day,
    rows: day.rows.filter(row => remap.has(row.run_index)).map(row => ({...row, run_index: remap.get(row.run_index)}))
  })).filter(day => day.rows.length)};
  if (!retained.length) {
    setText("scenario-load-status", "Nenhum cenário processado disponível.");
    document.getElementById("scenario-load-status").hidden = false;
    document.getElementById("dashboard-content").hidden = true;
    return;
  }
  renderComparison({...normalized, runs: retained, comparison: state.comparison});
}
function renderOverview(run) {
  const dashboard = run.dashboard;
  const replicas = run.replica_count || run.density?.replica_count || 1;
  // The aggregate stores the mean number of flight instances over all replicas.
  const flights = valueAt(dashboard, "summary.operation_count") ?? valueAt(dashboard, "efficiency.flight_instances");
  const total = flights == null ? null : Math.round(flights * replicas);
  setText("overview-flight-total", total == null ? "Indisponível" : formatNumber(total));
  setText("overview-flight-detail", replicas > 1
    ? `${formatNumber(replicas)} réplicas${flights == null ? "" : ` · média de ${formatNumber(flights, 2)} voos por réplica`}`
    : "1 réplica");
  setText("overview-scenario", `Cenário ${run.metadata?.scenario_key || run.name}`);

  const dimensions = runDimensions(run);
  const labels = ["Gestão do espaço aéreo", "Gestão do tráfego", "Condição operacional", "Demanda", "Critérios de separação"];
  const filters = scenarioFilters.map(({key, options}, index) => {
    const value = filterValue(dimensions, key);
    let label = options.find(([option]) => option === value)?.[1] || "Não informado";
    if (!value && key === "separation_seconds" && dimensions?.management?.startsWith("micro_")) label = "Não informado";
    return [labels[index], label];
  });
  const days = state.comparison?.days || [];
  const group = days.find(day => day.day_key === state.activeDayKey);
  if (days.length > 1 && group) filters.unshift(["Grupo de cenários", group.day_label]);
  document.getElementById("overview-filters").innerHTML = dimensions
    ? filters.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")
    : "<div><dt>Configuração</dt><dd>Detalhes dos filtros indisponíveis para este cenário.</dd></div>";
}

function renderSelectedRun() {
  const run = state.runs[state.activeRunIndex];
  if (!run) return;
  const content = document.getElementById("dashboard-content");
  const status = document.getElementById("scenario-load-status");
  const retry = document.getElementById("scenario-load-retry");
  if (run.data_parts) {
    const index = state.activeRunIndex;
    content.hidden = true;
    render3DVisualization(null, null);
    status.hidden = false;
    retry.hidden = true;
    status.textContent = `Carregando cenário ${run.metadata?.scenario_key || run.name}…`;
    loadRunDetails(index).then(() => { if (state.activeRunIndex === index) renderSelectedRun(); }).catch(error => {
      console.error(error);
      if (state.activeRunIndex !== index) return;
      status.textContent = "Não foi possível carregar este cenário.";
      retry.hidden = false;
    });
    return;
  }
  content.hidden = false;
  status.hidden = true;
  retry.hidden = true;
  renderOverview(run);
  renderMaps(run);
  renderMetrics(run.dashboard);
  renderCharts(run.dashboard);
  renderCapacity(run.dashboard);
  renderStability();
  setText("replica-universe", `Cenário ${run.metadata?.scenario_key || run.name} · Média de ${run.replica_count || 1} réplicas. Indicadores sem cálculo ou dados disponíveis são identificados como indisponíveis.`);
}
document.addEventListener("DOMContentLoaded", () => {
  initMaps();
  document.getElementById("scenario-load-retry").addEventListener("click", renderSelectedRun);
  document.getElementById("run-select").addEventListener("change", event => {
    state.activeRunIndex = Number(event.target.value); populateScenarioFilters(); renderSelectedRun();
  });
  document.getElementById("day-select").addEventListener("change", event => {
    state.activeDayKey = event.target.value; populateRunSelect();
  });
  scenarioFilters.forEach((filter, index) => document.getElementById(filter.id).addEventListener("change", () => {
    populateScenarioFilters(index); renderSelectedRun();
  }));
  const tabs = [...document.querySelectorAll("[data-kpa-tab]")];
  tabs.forEach((button, index) => {
    button.addEventListener("click", () => activateKpa(button.dataset.kpaTab));
    button.addEventListener("keydown", event => {
      const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null;
      if (next == null) return;
      event.preventDefault(); tabs[next].focus(); activateKpa(tabs[next].dataset.kpaTab);
    });
  });
  activateKpa("maps");
  renderDashboard(window.__UAM_DASHBOARD_DATA__ || {runs: []});
});
