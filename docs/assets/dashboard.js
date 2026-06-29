const state = {
  map: null,
  tracksLayer: null,
  plannedLayer: null,
  heatLayer: null,
  conflictLayer: null,
  baseLayers: {},
  overlayLayers: {},
  lastTracks: null,
  lastConflicts: null,
  runs: [],
  comparison: null,
  activeRunIndex: 0,
  activeDayKey: null,
  trajectoryVolumeFilter: "all",
};

document.addEventListener("DOMContentLoaded", () => {
  initMap();
  bindLayerControls();
  loadStaticDashboard();
});

async function loadStaticDashboard() {
  if (window.__UAM_DASHBOARD_DATA__) {
    renderDashboard(window.__UAM_DASHBOARD_DATA__);
    return;
  }

  const [dashboard, tracks, plannedRoutes, conflicts, heatmap, comparison] = await Promise.all([
    fetchJson("assets/data/dashboard.json"),
    fetchJson("assets/data/tracks.geojson"),
    fetchJson("assets/data/planned_routes.geojson"),
    fetchJson("assets/data/conflicts.geojson"),
    fetchJson("assets/data/heatmap_points.json"),
    fetchJson("assets/data/comparison.json"),
  ]);

  renderDashboard({ dashboard, tracks, planned_routes: plannedRoutes, conflicts, heatmap, comparison });
}

async function fetchJson(path) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("GET", path, true);
    request.overrideMimeType("application/json");
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        resolve(JSON.parse(request.responseText));
      } else {
        reject(new Error(`Falha ao carregar ${path}`));
      }
    };
    request.onerror = () => reject(new Error(`Falha ao carregar ${path}`));
    request.send();
  });
}

function initMap() {
  state.map = L.map("map", {
    preferCanvas: false,
    zoomControl: true,
    zoomSnap: 0.25,
    wheelPxPerZoomLevel: 90,
  }).setView([-23.5505, -46.6333], 10);

  const heatPane = state.map.createPane("heatPane");
  heatPane.style.zIndex = 360;
  const routePane = state.map.createPane("routePane");
  routePane.style.zIndex = 460;
  const conflictPane = state.map.createPane("conflictPane");
  conflictPane.style.zIndex = 560;

  const positron = L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    maxZoom: 20,
    updateWhenIdle: true,
    keepBuffer: 4,
  }).addTo(state.map);

  const voyager = L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    maxZoom: 20,
    updateWhenIdle: true,
    keepBuffer: 4,
  });

  state.baseLayers = {
    "Base clara": positron,
    "Base detalhada": voyager,
  };
}

function bindLayerControls() {
  document.getElementById("layer-tracks").addEventListener("change", (event) => toggleLayer("tracksLayer", event));
  document.getElementById("layer-planned").addEventListener("change", (event) => toggleLayer("plannedLayer", event));
  document.getElementById("layer-heat").addEventListener("change", (event) => toggleLayer("heatLayer", event));
  document.getElementById("layer-conflicts").addEventListener("change", (event) => toggleLayer("conflictLayer", event));
  document.getElementById("trajectory-volume-filter").addEventListener("change", (event) => {
    state.trajectoryVolumeFilter = event.target.value;
    const run = state.runs[state.activeRunIndex] || state.runs[0];
    if (run) renderMapLayers(run.tracks, run.planned_routes, run.conflicts, run.heatmap);
  });
  document.getElementById("fit-map").addEventListener("click", () => {
    fitMapToOperationalArea(state.lastTracks, state.lastConflicts);
  });
  document.getElementById("run-select").addEventListener("change", (event) => {
    state.activeRunIndex = Number(event.target.value);
    renderSelectedRun();
  });
  document.getElementById("day-select").addEventListener("change", (event) => {
    state.activeDayKey = event.target.value;
    renderDayComparison();
    populateRunSelect();
  });
}

function toggleLayer(layerName, event) {
  const layer = state[layerName];
  if (!layer) return;
  if (event.target.checked) {
    layer.addTo(state.map);
  } else {
    state.map.removeLayer(layer);
  }
}

function renderDashboard(model) {
  const normalized = normalizeModel(model);
  state.runs = normalized.runs;
  state.comparison = normalized.comparison;
  state.activeRunIndex = Math.min(state.activeRunIndex, state.runs.length - 1);

  renderComparison(normalized);
  renderTraceability(normalized.metric_catalog || normalized.dashboard.metric_catalog || []);
  renderSelectedRun();
}

function normalizeModel(model) {
  if (model.runs?.length) {
    return model;
  }

  const singleRun = {
    id: "run_1",
    name: model.dashboard.source_log,
    dashboard: model.dashboard,
    tracks: model.tracks,
    planned_routes: model.planned_routes,
    conflicts: model.conflicts,
    heatmap: model.heatmap,
  };
  return {
    ...model,
    runs: [singleRun],
    comparison: model.comparison || { run_count: 1, rows: [] },
  };
}

function renderSelectedRun() {
  const run = state.runs[state.activeRunIndex] || state.runs[0];
  if (!run) return;
  renderMetrics(run.dashboard);
  renderCharts(run.dashboard);
  renderCapacity(run.dashboard);
  renderMapLayers(run.tracks, run.planned_routes, run.conflicts, run.heatmap);
}

function renderComparison(model) {
  const days = model.comparison?.days || [];
  state.activeDayKey = state.activeDayKey || days[0]?.day_key || null;
  const daySelect = document.getElementById("day-select");
  daySelect.innerHTML = days
    .map((day) => `<option value="${escapeHtml(day.day_key)}">${escapeHtml(day.day_label)}</option>`)
    .join("");
  daySelect.value = state.activeDayKey || "";
  populateRunSelect();
  setText(
    "comparison-summary",
    `${formatNumber(model.runs.length)} simulacoes organizadas em ${formatNumber(days.length)} dias. A tabela compara as quatro variantes do dia selecionado; cards, mapa e graficos mostram a variante escolhida.`
  );
  renderDayComparison();
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
  renderSelectedRun();
}

function renderDayComparison() {
  const day = state.comparison?.days?.find((item) => item.day_key === state.activeDayKey);
  const rows = day?.rows || [];
  document.getElementById("comparison-table-body").innerHTML = rows
    .map(
      (row) => `
        <tr class="${row.mvp_enabled ? "mvp-row" : ""}">
          <td title="${escapeHtml(row.name)}">${escapeHtml(row.variant_label)}</td>
          <td>${formatOptionalDuration(row.ground_delay_s)}</td>
          <td>${formatOptionalDuration(row.airborne_delay_s)}</td>
          <td>${formatOptionalDuration(row.total_delay_s)}</td>
          <td>${formatNumber(row.flight_time_min, 1)} min</td>
          <td>${formatSigned(row.flight_time_delta_vs_off_min, 1, " min")}</td>
          <td>${formatNumber(row.distance_nm, 1)} NM</td>
          <td>${formatSigned(row.distance_delta_vs_off_nm, 2, " NM")}</td>
          <td>${formatOptionalPercent(row.trajectory_conformity_pct)}</td>
          <td>${formatOptionalPercent(row.spatial_adherence_pct)}</td>
          <td>${formatNumber(row.lowc_events, 1)}</td>
          <td>${formatNumber(row.lowc_per_flight_hour, 2)}</td>
          <td>${formatNumber(row.expected_mac_per_100k_flight_hours, 3)}</td>
          <td>${formatTLSMargin(row.tls_margin, row.tls_compliant)}</td>
          <td>${formatOptionalRatio(row.risk_ratio_vs_reference)}</td>
          <td>${formatNumber(row.nmac_events, 1)}</td>
          <td>${formatNumber(row.min_severity_ratio, 2)}</td>
        </tr>`
    )
    .join("");
}

function renderMetrics(dashboard) {
  const summary = dashboard.summary;
  const efficiency = dashboard.efficiency;
  const safety = dashboard.safety;

  setText("source-log", dashboard.source_log);
  setText("metric-aircraft", formatNumber(summary.aircraft_count));
  setText("metric-records", `${formatNumber(summary.records)} registros`);
  setText("metric-peak", formatNumber(summary.peak_simultaneous_aircraft));
  setText("metric-duration", `${formatNumber(summary.duration_min, 1)} min`);
  setText("metric-flight-time", formatNumber(efficiency.mean_flight_time_min, 1));
  setText("metric-distance", formatNumber(efficiency.mean_distance_nm, 1));
  setText("metric-lowc", formatNumber(safety.lowc_events));
  setText("metric-lowc-threshold", `${formatNumber(safety.lowc_horizontal_m, 0)} m horizontal`);
  setText("metric-nmac", formatNumber(safety.nmac_events));
  setText("metric-nmac-threshold", `${formatNumber(safety.nmac_horizontal_m, 0)} m horizontal`);
  setText("metric-lowc-rate", formatNumber(safety.lowc_per_flight_hour, 2));
  setText("metric-mac-rate", formatNumber(safety.expected_mac_per_100k_flight_hours, 3));
  setText("metric-tls-margin", formatTLSMargin(safety.tls_margin, safety.tls_compliant));
  setText("metric-tls-status", safety.tls_compliant ? "atende ao TLS" : "viola o TLS");
  setText("kpa-route-efficiency", `${formatNumber(efficiency.mean_horizontal_inefficiency_pct, 1)}%`);
  setText(
    "kpa-conformity",
    efficiency.trajectory_conformity?.available
      ? `${formatNumber(efficiency.trajectory_conformity.mean_trajectory_conformity_ratio * 100, 1)}%`
      : "Sem SCN"
  );
  setText(
    "kpa-spatial-adherence",
    efficiency.trajectory_conformity?.available
      ? `${formatNumber(efficiency.trajectory_conformity.spatial_adherence_pct, 1)}%`
      : "Sem SCN"
  );
  setText(
    "kpa-ground-delay",
    efficiency.ground_delay?.available
      ? `${formatNumber(efficiency.ground_delay.mean_ground_delay_s, 0)} s`
      : "Sem pareamento"
  );
  setText(
    "kpa-airborne-delay",
    efficiency.airborne_delay?.available
      ? `${formatNumber(efficiency.airborne_delay.mean_airborne_delay_s, 0)} s`
      : "Sem referencia"
  );
  setText(
    "kpa-total-delay",
    efficiency.total_delay?.available
      ? `${formatNumber(efficiency.total_delay.mean_total_delay_s, 0)} s`
      : "Sem pareamento"
  );
  setText("kpa-severity", formatNumber(safety.min_severity_ratio, 2));
  setText("kpa-mac-rate", formatNumber(safety.expected_mac_per_100k_flight_hours, 3));
  setText("kpa-tls-margin", formatTLSMargin(safety.tls_margin, safety.tls_compliant));
  setText("kpa-time-below", `${formatNumber(safety.total_time_below_threshold_s, 0)} s`);
  setText("kpa-safety-sample", `${formatNumber(safety.sample_seconds, 0)} s`);
}

function renderCharts(dashboard) {
  showImageChart("chart-active", dashboard.charts.active_aircraft);
  showImageChart("chart-separation", dashboard.charts.separation_histogram);
  showImageChart("chart-altitude", dashboard.charts.altitude_histogram);
  showImageChart("chart-distance", dashboard.charts.distance_histogram);
  showImageChart("chart-severity", dashboard.charts.severity_histogram);
  showImageChart("chart-conformity", dashboard.charts.trajectory_conformity);
}

function renderCapacity(dashboard) {
  const capacity = dashboard.capacity || {};
  const density = capacity.density || {};
  const complexity = capacity.complexity || {};
  setText(
    "capacity-atd",
    density.available ? formatNumber(density.air_traffic_density_per_km2, 3) : "-"
  );
  setText(
    "capacity-hotspot",
    density.available ? formatNumber(density.hotspot_density_per_km2, 3) : "-"
  );
  setText("capacity-area", density.available ? formatNumber(density.corridor_area_km2, 2) : "-");
  setText(
    "capacity-crossings",
    complexity.available ? formatNumber(complexity.planned_route_crossings, 0) : "-"
  );
  setText(
    "capacity-complexity",
    complexity.available
      ? `${formatNumber(complexity.planned_route_count, 0)} REHs planejadas, ` +
          `${formatNumber(complexity.planned_waypoint_count, 0)} waypoints, ` +
          `${formatNumber(complexity.trajectory_group_count, 0)} grupos de trajetoria, ` +
          `${formatNumber(complexity.repeated_trajectory_group_count, 0)} grupos recorrentes e ` +
          `${formatNumber(complexity.lowc_event_count, 0)} eventos LoWC.`
      : "Sem dados de capacidade."
  );
  renderCapacityTable(capacity.throughput || {});
}

function renderCapacityTable(throughput) {
  const rows = [];
  for (const [type, label] of [
    ["od_pairs", "Par OD"],
    ["trajectory_groups", "Grupo trajetoria"],
    ["planned_reh", "REH planejada"],
  ]) {
    const group = throughput[type];
    if (!group?.available) continue;
    for (const resource of group.top_resources || []) {
      rows.push({
        type: label,
        capacity: group.capacity_reference_per_hour,
        ...resource,
      });
    }
  }
  document.getElementById("capacity-table-body").innerHTML = rows.length
    ? rows
        .map(
          (row) => `
        <tr>
          <td>${escapeHtml(row.type)}</td>
          <td title="${escapeHtml(row.resource_id)}">${escapeHtml(row.label)}</td>
          <td>${formatNumber(row.operations, 0)}</td>
          <td>${formatNumber(row.peak_throughput_per_hour, 1)} ops/h</td>
          <td>${formatNumber(row.capacity, 1)} ops/h</td>
          <td>${formatPercentRatio(row.utilization_peak)}</td>
        </tr>`
        )
        .join("")
    : `<tr><td colspan="6">Sem recursos de capacidade calculados.</td></tr>`;
}

function showImageChart(imageId, src) {
  const image = document.getElementById(imageId);
  image.src = src;
}

function renderMapLayers(tracks, plannedRoutes, conflicts, heatmap) {
  state.lastTracks = tracks;
  state.lastConflicts = conflicts;
  const visibleTracks = filterTracksByVolume(tracks, state.trajectoryVolumeFilter);
  clearLayer("tracksLayer");
  clearLayer("plannedLayer");
  clearLayer("heatLayer");
  clearLayer("conflictLayer");

  const routeHalo = L.geoJSON(visibleTracks, {
    interactive: false,
    pane: "routePane",
    style: () => ({
      color: "#f8fafc",
      opacity: 0.96,
      weight: 8,
      lineCap: "round",
      lineJoin: "round",
    }),
  });

  const routeLines = L.geoJSON(visibleTracks, {
    pane: "routePane",
    style: (feature) => ({
      color: colorForVolume(feature.properties.volume_ratio),
      opacity: 1,
      weight: 3 + feature.properties.volume_ratio * 3,
      lineCap: "round",
      lineJoin: "round",
    }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindTooltip(`${escapeHtml(p.trajectory_group)} - ${formatNumber(p.frequency)} ocorrencias`, {
        sticky: true,
      });
      layer.bindPopup(
        `<strong>Trajetoria ${escapeHtml(p.trajectory_group)}</strong><br>` +
          `Aeronave ${escapeHtml(p.id)} / ${escapeHtml(p.flight_instance)}<br>` +
          `${formatNumber(p.frequency)} instancias semelhantes<br>` +
          `${formatNumber(p.distance_nm, 1)} NM voadas<br>` +
          `${formatNumber(p.duration_min, 1)} min de voo<br>` +
          `Altitude ${formatNumber(p.min_alt_m, 0)}-${formatNumber(p.max_alt_m, 0)} m` +
          (Number.isFinite(Number(p.trajectory_conformity_ratio))
            ? `<br>Conformidade por distancia ${formatNumber(p.trajectory_conformity_ratio * 100, 1)}%<br>` +
              `Aderencia espacial ${formatNumber(p.spatial_adherence_pct, 1)}%<br>` +
              `Desvio medio da REH ${formatNumber(p.mean_deviation_m, 1)} m`
            : "")
      );
    },
  });

  state.tracksLayer = L.layerGroup([routeHalo, routeLines]);

  state.plannedLayer = L.geoJSON(plannedRoutes, {
    pane: "routePane",
    style: {
      color: "#111827",
      opacity: 0.82,
      weight: 2.5,
      dashArray: "8 7",
      lineCap: "round",
    },
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      const conformity = Number.isFinite(Number(p.spatial_adherence_pct))
        ? `${formatNumber(p.spatial_adherence_pct, 1)}% das amostras dentro de ${formatNumber(plannedRoutes.properties.conformity_tolerance_m, 0)} m`
        : "Sem trajetoria executada associada";
      layer.bindTooltip(`REH planejada ${escapeHtml(p.flight_instance)}`, { sticky: true });
      layer.bindPopup(
        `<strong>REH planejada</strong><br>` +
          `${escapeHtml(p.flight_instance)} / ${formatNumber(p.waypoint_count)} waypoints<br>` +
          `${conformity}<br>` +
          (Number.isFinite(Number(p.mean_deviation_m))
            ? `Desvio medio ${formatNumber(p.mean_deviation_m, 1)} m<br>P95 ${formatNumber(p.p95_deviation_m, 1)} m`
            : "")
      );
    },
  });

  const conflictMarkers = L.geoJSON(conflicts, {
    pane: "conflictPane",
    pointToLayer: (_feature, latlng) =>
      L.circleMarker(latlng, {
        radius: 11,
        color: "#7f1d1d",
        weight: 3,
        fillColor: "#ef4444",
        fillOpacity: 0.94,
      }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindTooltip(`LoWC ${escapeHtml(p.id_a)} / ${escapeHtml(p.id_b)}`, {
        sticky: true,
      });
      layer.bindPopup(
        `<strong>${p.is_nmac ? "Evento NMAC" : "Evento LoWC"}</strong><br>` +
          `${escapeHtml(p.id_a)} / ${escapeHtml(p.id_b)}<br>` +
          `${formatNumber(p.dist_h_m, 1)} m horizontal<br>` +
          `Severidade ${formatNumber(p.severity_ratio, 2)}<br>` +
          `Razao horizontal ${formatNumber(p.horizontal_ratio, 3)}<br>` +
          `Duracao ${formatNumber(p.duration_s, 0)} s<br>` +
          `t = ${formatNumber(p.simt, 0)} s`
      );
    },
  });

  const conflictPulse = L.geoJSON(conflicts, {
    interactive: false,
    pane: "conflictPane",
    pointToLayer: (_feature, latlng) =>
      L.circleMarker(latlng, {
        radius: 22,
        color: "#ef4444",
        weight: 2,
        fillColor: "#ef4444",
        fillOpacity: 0.12,
        opacity: 0.45,
      }),
  });
  state.conflictLayer = L.layerGroup([conflictPulse, conflictMarkers]);

  const airportMarkers = buildEndpointLayer(visibleTracks);
  state.tracksLayer.addLayer(airportMarkers);

  if (L.heatLayer) {
    state.heatLayer = L.heatLayer(heatmap, {
      pane: "heatPane",
      radius: 9,
      blur: 10,
      minOpacity: 0.08,
      maxZoom: 14,
      gradient: {
        0.15: "#2dd4bf",
        0.45: "#2563eb",
        0.7: "#f59e0b",
        1.0: "#dc2626",
      },
    });
  } else {
    state.heatLayer = L.layerGroup(
      heatmap.map((point) =>
        L.circleMarker([point[0], point[1]], {
          radius: 3,
          stroke: false,
          fillOpacity: 0.16,
          fillColor: "#2563eb",
        })
      )
    );
  }

  applyCheckedLayer("layer-heat", state.heatLayer);
  applyCheckedLayer("layer-tracks", state.tracksLayer);
  applyCheckedLayer("layer-planned", state.plannedLayer);
  applyCheckedLayer("layer-conflicts", state.conflictLayer);

  fitMapToOperationalArea(visibleTracks, conflicts);
  updateMapInfo(tracks, visibleTracks, plannedRoutes, conflicts, heatmap);
}

function buildEndpointLayer(tracks) {
  const points = [];
  for (const feature of tracks.features || []) {
    const coordinates = feature.geometry?.coordinates || [];
    if (!coordinates.length) continue;
    const first = coordinates[0];
    const last = coordinates[coordinates.length - 1];
    points.push({ type: "inicio", id: feature.properties.id, coordinate: first });
    points.push({ type: "fim", id: feature.properties.id, coordinate: last });
  }

  return L.layerGroup(
    points.map((point) =>
      L.circleMarker([point.coordinate[1], point.coordinate[0]], {
        pane: "routePane",
        radius: point.type === "inicio" ? 4 : 5,
        color: point.type === "inicio" ? "#0f766e" : "#7c3aed",
        weight: 1.5,
        fillColor: "#ffffff",
        fillOpacity: 0.95,
      }).bindTooltip(`${point.type === "inicio" ? "Inicio" : "Fim"} ${escapeHtml(point.id)}`, {
        sticky: true,
      })
    )
  );
}

function fitMapToOperationalArea(tracks, conflicts) {
  if (!tracks || !conflicts) {
    state.map.invalidateSize(true);
    state.map.setView([-23.5505, -46.6333], 10);
    return;
  }

  const bounds = L.latLngBounds([]);
  for (const feature of tracks.features || []) {
    for (const coordinate of feature.geometry?.coordinates || []) {
      bounds.extend([coordinate[1], coordinate[0]]);
    }
  }
  for (const feature of conflicts.features || []) {
    const coordinate = feature.geometry?.coordinates;
    if (coordinate) bounds.extend([coordinate[1], coordinate[0]]);
  }

  state.map.invalidateSize(true);
  if (bounds.isValid()) {
    state.map.fitBounds(bounds.pad(0.18), {
      animate: false,
      maxZoom: 11,
      paddingTopLeft: [16, 16],
      paddingBottomRight: [16, 16],
    });
  } else {
    state.map.setView([-23.5505, -46.6333], 10);
  }

  requestAnimationFrame(() => {
    state.map.invalidateSize(true);
    if (bounds.isValid()) {
      state.map.fitBounds(bounds.pad(0.18), {
        animate: false,
        maxZoom: 11,
        paddingTopLeft: [16, 16],
        paddingBottomRight: [16, 16],
      });
    }
  });
}

function updateMapInfo(tracks, visibleTracks, plannedRoutes, conflicts, heatmap) {
  const trajectories = tracks.features?.length || 0;
  const visible = visibleTracks.features?.length || 0;
  const groups = tracks.properties?.trajectory_group_count || new Set(
    (tracks.features || []).map((feature) => feature.properties.trajectory_group)
  ).size;
  const lowc = conflicts.features?.length || 0;
  const planned = plannedRoutes?.features?.length || 0;
  const density = heatmap.length || 0;
  setText("map-info-title", "Mapa operacional");
  setText(
    "map-info-text",
    `${formatNumber(visible)} de ${formatNumber(trajectories)} trajetorias executadas visiveis, ${formatNumber(planned)} trajetorias REH planejadas; ${formatNumber(density)} pontos de densidade e ${formatNumber(lowc)} eventos LoWC.`
  );
}

function filterTracksByVolume(tracks, filter) {
  if (!tracks || filter === "all") return tracks;
  return {
    ...tracks,
    features: (tracks.features || []).filter((feature) => feature.properties.volume_class === filter),
  };
}

function clearLayer(layerName) {
  const layer = state[layerName];
  if (layer && state.map.hasLayer(layer)) {
    state.map.removeLayer(layer);
  }
  state[layerName] = null;
}

function applyCheckedLayer(controlId, layer) {
  if (document.getElementById(controlId).checked && layer) {
    layer.addTo(state.map);
  }
}

function renderTraceability(catalog) {
  const body = document.getElementById("traceability-table-body");
  if (!body) return;
  const groups = groupTraceability(catalog || []);
  body.innerHTML = groups
    .map(
      (group) => `
        <tr class="traceability-group-row">
          <td colspan="5">${escapeHtml(group.label)}</td>
        </tr>
        ${group.items
          .map(
            (metric) => `
        <tr>
          <td>${escapeHtml(metric.name)}</td>
          <td>${escapeHtml(metric.formula)}</td>
          <td>${escapeHtml(metric.pdf_reference)}</td>
          <td>${escapeHtml(metric.code_reference)}</td>
          <td>${escapeHtml(metric.status)}</td>
        </tr>`
          )
          .join("")}`
    )
    .join("");
}

function groupTraceability(catalog) {
  const order = ["Seguranca", "Eficiencia", "Capacidade", "Trajetorias e mapa", "Indisponiveis"];
  const labels = {
    Seguranca: "Metricas de seguranca",
    Eficiencia: "Metricas de eficiencia",
    Capacidade: "Metricas de capacidade",
    "Trajetorias e mapa": "Trajetorias, mapa e diagnosticos espaciais",
    Indisponiveis: "Metricas ainda indisponiveis",
  };
  const groups = Object.fromEntries(order.map((key) => [key, []]));
  for (const metric of catalog) {
    groups[inferMetricCategory(metric)].push(metric);
  }
  return order
    .filter((key) => groups[key].length)
    .map((key) => ({ label: labels[key], items: groups[key] }));
}

function inferMetricCategory(metric) {
  const id = metric.id || "";
  if (metric.status?.startsWith("unavailable")) return "Indisponiveis";
  if (id.includes("lowc") || id.includes("nmac") || id.includes("severity") || id.includes("mac") || id.includes("risk") || id.includes("tls")) {
    return "Seguranca";
  }
  if (id.includes("density") || id.includes("complexity") || id.includes("throughput") || id.includes("utilization")) {
    return "Capacidade";
  }
  if (id.includes("time") || id.includes("distance") || id.includes("efficiency") || id.includes("delay") || id.includes("conformity")) {
    return "Eficiencia";
  }
  return "Trajetorias e mapa";
}

function colorForVolume(volumeRatio) {
  const ratio = Math.max(0, Math.min(1, Number(volumeRatio) || 0));
  if (ratio >= 0.67) return "#dc2626";
  if (ratio >= 0.34) return "#f59e0b";
  return "#0ea5e9";
}

function formatNumber(value, digits = 0) {
  if (!Number.isFinite(Number(value))) return "-";
  return Number(value).toLocaleString("pt-BR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatOptionalPercent(value) {
  return value !== null && value !== undefined && Number.isFinite(Number(value))
    ? `${formatNumber(value, 1)}%`
    : "-";
}

function formatOptionalDuration(value) {
  return value !== null && value !== undefined && Number.isFinite(Number(value))
    ? `${formatNumber(value, 0)} s`
    : "-";
}

function formatOptionalRatio(value) {
  return value !== null && value !== undefined && Number.isFinite(Number(value))
    ? formatNumber(value, 2)
    : "-";
}

function formatPercentRatio(value) {
  return value !== null && value !== undefined && Number.isFinite(Number(value))
    ? `${formatNumber(Number(value) * 100, 1)}%`
    : "-";
}

function formatTLSMargin(value, compliant) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "-";
  const number = Number(value);
  if (number > 999999) return compliant ? ">999999" : formatNumber(number, 1);
  if (number >= 1000) return formatNumber(number, 0);
  if (number >= 10) return formatNumber(number, 1);
  return formatNumber(number, 2);
}

function formatSigned(value, digits, suffix = "") {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "-";
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${formatNumber(number, digits)}${suffix}`;
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
