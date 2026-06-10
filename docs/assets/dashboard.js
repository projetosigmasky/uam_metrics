const state = {
  map: null,
  tracksLayer: null,
  heatLayer: null,
  conflictLayer: null,
  baseLayers: {},
  overlayLayers: {},
  lastTracks: null,
  lastConflicts: null,
  runs: [],
  comparison: null,
  currentModel: null,
  activeRunIndex: 0,
  trajectoryVolumeFilter: "all",
};

const metersPerNm = 1852;
const feetToMeters = 0.3048;
const lowAltitudeFt = 1500;
const lowAltitudeReferenceMode = "origin_agl_proxy";
const lowAltitudeReferenceSamples = 5;
const flightInstanceGapSeconds = 300;
const flightInstanceResetDistanceM = 250;
const flightInstanceJumpM = 5000;
const lowcHorizontalM = 500;
const lowcVerticalM = 30;
const nmacHorizontalM = 150;
const nmacVerticalM = 30;
const conflictSampleSeconds = 10;
const sameAltitudeBandM = 150;
const macProbabilityBands = [0.001, 0.01, 0.05];

document.addEventListener("DOMContentLoaded", () => {
  initMap();
  bindLayerControls();
  bindUpload();
  loadStaticDashboard();
});

async function loadStaticDashboard() {
  if (window.__UAM_DASHBOARD_DATA__) {
    renderDashboard({
      ...window.__UAM_DASHBOARD_DATA__,
      uploaded: false,
    });
    return;
  }

  const [dashboard, tracks, conflicts, heatmap, timeline] = await Promise.all([
    fetchJson("assets/data/dashboard.json"),
    fetchJson("assets/data/tracks.geojson"),
    fetchJson("assets/data/conflicts.geojson"),
    fetchJson("assets/data/heatmap_points.json"),
    fetchJson("assets/data/timeline.json"),
  ]);

  renderDashboard({
    dashboard,
    tracks,
    conflicts,
    heatmap,
    timeline,
    uploaded: false,
  });
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
  document.getElementById("layer-heat").addEventListener("change", (event) => toggleLayer("heatLayer", event));
  document.getElementById("layer-conflicts").addEventListener("change", (event) => toggleLayer("conflictLayer", event));
  document.getElementById("trajectory-volume-filter").addEventListener("change", (event) => {
    state.trajectoryVolumeFilter = event.target.value;
    const run = state.runs[state.activeRunIndex] || state.runs[0];
    if (run) renderMapLayers(run.tracks, run.conflicts, run.heatmap);
  });
  document.getElementById("fit-map").addEventListener("click", () => {
    fitMapToOperationalArea(state.lastTracks, state.lastConflicts);
  });
  document.getElementById("run-select").addEventListener("change", (event) => {
    state.activeRunIndex = Number(event.target.value);
    renderSelectedRun(false);
  });
}

function bindUpload() {
  document.getElementById("log-upload").addEventListener("change", async (event) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;

    const runs = [];
    for (const [index, file] of files.entries()) {
      const text = await file.text();
      const parsed = parseStateLog(text);
      const model = buildClientModel(parsed, file.name);
      runs.push({ id: `upload_${index + 1}`, name: file.name, ...model });
    }
    renderDashboard(buildMultiRunModel(runs, true));
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
  state.currentModel = normalized;
  state.runs = normalized.runs;
  state.comparison = normalized.comparison;
  state.activeRunIndex = Math.min(state.activeRunIndex, state.runs.length - 1);

  renderMetrics(normalized.dashboard);
  renderComparison(normalized);
  renderTraceability(normalized.metric_catalog || normalized.dashboard.metric_catalog || []);
  renderSelectedRun(normalized.uploaded);
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
    conflicts: model.conflicts,
    heatmap: model.heatmap,
    timeline: model.timeline,
  };
  return buildMultiRunModel([singleRun], model.uploaded);
}

function renderSelectedRun(uploaded) {
  const run = state.runs[state.activeRunIndex] || state.runs[0];
  if (!run) return;
  renderCharts(run.dashboard, run.timeline, uploaded ?? state.currentModel?.uploaded);
  renderMapLayers(run.tracks, run.conflicts, run.heatmap);
}

function renderComparison(model) {
  const select = document.getElementById("run-select");
  select.innerHTML = model.runs
    .map((run, index) => `<option value="${index}">${escapeHtml(run.name)}</option>`)
    .join("");
  select.value = String(state.activeRunIndex);

  const runCount = model.runs.length;
  setText(
    "comparison-summary",
    runCount > 1
      ? `${formatNumber(runCount)} logs processados. Os cards superiores mostram a media das metricas; o mapa e os graficos mostram o cenario selecionado.`
      : "Um log processado. Adicione mais STATELOGs para comparar cenarios e calcular medias."
  );

  const rows = model.comparison?.rows || [];
  document.getElementById("comparison-table-body").innerHTML = rows
    .map(
      (row) => `
        <tr class="${row.is_average ? "average-row" : ""}">
          <td title="${escapeHtml(row.name)}">${escapeHtml(row.name)}</td>
          <td>${formatNumber(row.aircraft, 1)}</td>
          <td>${formatNumber(row.peak, 1)}</td>
          <td>${formatNumber(row.duration_min, 1)} min</td>
          <td>${formatNumber(row.flight_time_min, 1)} min</td>
          <td>${formatNumber(row.distance_nm, 1)} NM</td>
          <td>${formatNumber(row.route_efficiency_pct, 1)}%</td>
          <td>${formatNumber(row.low_altitude_pct, 1)}%</td>
          <td>${formatNumber(row.lowc_events, 1)}</td>
          <td>${formatNumber(row.nmac_events, 1)}</td>
          <td>${formatNumber(row.lowc_per_flight_hour, 2)}</td>
          <td>${formatNumber(row.min_severity_ratio, 2)}</td>
        </tr>`
    )
    .join("");
}

function renderMetrics(dashboard) {
  const summary = dashboard.summary;
  const efficiency = dashboard.efficiency;
  const environment = dashboard.environment;
  const safety = dashboard.safety;

  setText("source-log", dashboard.source_log);
  setText("metric-aircraft", formatNumber(summary.aircraft_count));
  setText("metric-records", `${formatNumber(summary.records)} registros`);
  setText("metric-peak", formatNumber(summary.peak_simultaneous_aircraft));
  setText("metric-duration", `${formatNumber(summary.duration_min, 1)} min`);
  setText("metric-flight-time", formatNumber(efficiency.mean_flight_time_min, 1));
  setText("metric-distance", formatNumber(efficiency.mean_distance_nm, 1));
  setText("metric-low-altitude", `${formatNumber(environment.low_altitude_share_pct, 1)}%`);
  setText(
    "metric-low-altitude-threshold",
    `< ${formatNumber(environment.low_altitude_threshold_ft, 0)} ft acima da origem`
  );
  setText("metric-lowc", formatNumber(safety.lowc_events));
  setText("metric-lowc-threshold", `${formatNumber(safety.lowc_horizontal_m, 0)} m x ${formatNumber(safety.lowc_vertical_m, 0)} m`);
  setText("metric-nmac", formatNumber(safety.nmac_events));
  setText("metric-nmac-threshold", `${formatNumber(safety.nmac_horizontal_m, 0)} m x ${formatNumber(safety.nmac_vertical_m, 0)} m`);
  setText("metric-lowc-rate", formatNumber(safety.lowc_per_flight_hour, 2));
  setText("kpa-route-efficiency", `${formatNumber(efficiency.mean_route_efficiency_pct, 1)}%`);
  setText("kpa-altitude", `${formatNumber(environment.median_altitude_agl_proxy_m, 0)} m`);
  setText("kpa-origin-altitude", `${formatNumber(environment.median_origin_altitude_m, 0)} m`);
  setText("kpa-severity", formatNumber(safety.min_severity_ratio, 2));
  setText("kpa-time-below", `${formatNumber(safety.total_time_below_threshold_s, 0)} s`);
  setText("kpa-safety-sample", `${formatNumber(safety.sample_seconds, 0)} s`);
}

function renderCharts(dashboard, timeline, uploaded) {
  if (!uploaded) {
    showImageChart("chart-active", "canvas-active", dashboard.charts.active_aircraft);
    showImageChart("chart-separation", "canvas-separation", dashboard.charts.separation_histogram);
    showImageChart("chart-altitude", "canvas-altitude", dashboard.charts.altitude_histogram);
    showImageChart("chart-distance", "canvas-distance", dashboard.charts.distance_histogram);
    showImageChart("chart-severity", "canvas-severity", dashboard.charts.severity_histogram);
    return;
  }

  showCanvasChart("chart-active", "canvas-active", timeline.map((item) => item.aircraft), "#2563eb");
  showCanvasChart("chart-separation", "canvas-separation", dashboard._client.separationSamples, "#dc2626");
  showCanvasChart("chart-altitude", "canvas-altitude", dashboard._client.altitudes, "#0f766e");
  showCanvasChart("chart-distance", "canvas-distance", dashboard._client.distancesNm, "#7c3aed");
  showCanvasChart("chart-severity", "canvas-severity", dashboard._client.severities, "#be123c");
}

function showImageChart(imageId, canvasId, src) {
  const image = document.getElementById(imageId);
  const canvas = document.getElementById(canvasId);
  image.hidden = false;
  canvas.hidden = true;
  image.src = src;
}

function showCanvasChart(imageId, canvasId, values, color) {
  const image = document.getElementById(imageId);
  const canvas = document.getElementById(canvasId);
  image.hidden = true;
  canvas.hidden = false;
  drawHistogram(canvas, values, color);
}

function renderMapLayers(tracks, conflicts, heatmap) {
  state.lastTracks = tracks;
  state.lastConflicts = conflicts;
  const visibleTracks = filterTracksByVolume(tracks, state.trajectoryVolumeFilter);
  clearLayer("tracksLayer");
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
          `Altitude ${formatNumber(p.min_alt_m, 0)}-${formatNumber(p.max_alt_m, 0)} m`
      );
    },
  });

  state.tracksLayer = L.layerGroup([routeHalo, routeLines]);

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
          `${formatNumber(p.dist_v_m, 1)} m vertical<br>` +
          `Severidade ${formatNumber(p.severity_ratio, 2)}<br>` +
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
  applyCheckedLayer("layer-conflicts", state.conflictLayer);

  fitMapToOperationalArea(visibleTracks, conflicts);
  updateMapInfo(tracks, visibleTracks, conflicts, heatmap);
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

function updateMapInfo(tracks, visibleTracks, conflicts, heatmap) {
  const trajectories = tracks.features?.length || 0;
  const visible = visibleTracks.features?.length || 0;
  const groups = tracks.properties?.trajectory_group_count || new Set(
    (tracks.features || []).map((feature) => feature.properties.trajectory_group)
  ).size;
  const lowc = conflicts.features?.length || 0;
  const density = heatmap.length || 0;
  setText("map-info-title", "Mapa operacional");
  setText(
    "map-info-text",
    `${formatNumber(visible)} de ${formatNumber(trajectories)} trajetorias visiveis, agrupadas em ${formatNumber(groups)} padroes; ${formatNumber(density)} pontos de densidade e ${formatNumber(lowc)} eventos LoWC.`
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

function parseStateLog(text) {
  return text
    .split(/\r?\n/)
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => line.split(",").map((value) => value.trim()))
    .filter((parts) => parts.length >= 9)
    .map((parts) => ({
      simt: Number(parts[0]),
      id: parts[1],
      lat: Number(parts[2]),
      lon: Number(parts[3]),
      distflown: Number(parts[4]),
      alt: Number(parts[5]),
      cas: Number(parts[6]),
      tas: Number(parts[7]),
      gs: Number(parts[8]),
    }))
    .filter((row) => Number.isFinite(row.simt) && row.id && Number.isFinite(row.lat) && Number.isFinite(row.lon));
}

function buildClientModel(rows, fileName) {
  rows.sort((a, b) => a.simt - b.simt || a.id.localeCompare(b.id));
  const byId = groupBy(rows, (row) => row.id);
  const byTime = groupBy(rows, (row) => String(row.simt));
  const activeCounts = [...byTime.entries()].map(([simt, group]) => ({
    simt: Number(simt),
    hour: Number(simt) / 3600,
    aircraft: new Set(group.map((row) => row.id)).size,
  }));

  const durations = [];
  const distancesNm = [];
  const distancesKm = [];
  const routeEfficiencies = [];
  const greatCircleDistancesNm = [];
  const features = [];
  let minLat = Infinity;
  let maxLat = -Infinity;
  let minLon = Infinity;
  let maxLon = -Infinity;

  for (const [id, group] of byId.entries()) {
    group.sort((a, b) => a.simt - b.simt);
    const first = group[0];
    const last = group[group.length - 1];
    const distanceM = Math.max(...group.map((row) => row.distflown));
    const distanceNm = distanceM / metersPerNm;
    distancesNm.push(distanceNm);
    distancesKm.push(distanceM / 1000);
    durations.push((last.simt - first.simt) / 60);
    const straightM = haversineM(first.lat, first.lon, last.lat, last.lon);
    greatCircleDistancesNm.push(straightM / metersPerNm);
    if (distanceM > 0) {
      routeEfficiencies.push((straightM / distanceM) * 100);
    }

    const sampled = sampleRows(group, 20);
    features.push({
      type: "Feature",
      properties: {
        id,
        flight_instance: `${id}#0`,
        samples: group.length,
        distance_nm: distanceNm,
        duration_min: (last.simt - first.simt) / 60,
        min_alt_m: Math.min(...group.map((row) => row.alt)),
        max_alt_m: Math.max(...group.map((row) => row.alt)),
      },
      geometry: {
        type: "LineString",
        coordinates: sampled.map((row) => [row.lon, row.lat, row.alt]),
      },
    });
  }

  for (const row of rows) {
    minLat = Math.min(minLat, row.lat);
    maxLat = Math.max(maxLat, row.lat);
    minLon = Math.min(minLon, row.lon);
    maxLon = Math.max(maxLon, row.lon);
  }

  const lowAltitudeM = lowAltitudeFt * feetToMeters;
  annotateTrajectoryFrequencies(features);
  const annotatedAltitudeRows = annotateFlightInstances(rows, byId);
  const originAltitudes = [...groupBy(annotatedAltitudeRows, (row) => row.flight_instance).values()].map(
    (group) => group[0].origin_alt_m
  );
  const totalFlightHours = durations.reduce((sum, value) => sum + value, 0) / 60;
  const totalDistanceKm = distancesKm.reduce((sum, value) => sum + value, 0);
  const lowc = detectClientLowc(byTime, byId.size, totalFlightHours, totalDistanceKm);

  const dashboard = {
    source_log: `${fileName} (preview local)`,
    summary: {
      records: rows.length,
      aircraft_count: byId.size,
      sim_start_s: Math.min(...rows.map((row) => row.simt)),
      sim_end_s: Math.max(...rows.map((row) => row.simt)),
      duration_min: (Math.max(...rows.map((row) => row.simt)) - Math.min(...rows.map((row) => row.simt))) / 60,
      mean_simultaneous_aircraft: average(activeCounts.map((row) => row.aircraft)),
      peak_simultaneous_aircraft: Math.max(...activeCounts.map((row) => row.aircraft)),
      bounds: { min_lat: minLat, max_lat: maxLat, min_lon: minLon, max_lon: maxLon },
    },
    efficiency: {
      mean_flight_time_min: average(durations),
      median_flight_time_min: median(durations),
      p95_flight_time_min: percentile(durations, 0.95),
      mean_distance_nm: average(distancesNm),
      median_distance_nm: median(distancesNm),
      p95_distance_nm: percentile(distancesNm, 0.95),
      total_distance_km: totalDistanceKm,
      total_flight_hours: totalFlightHours,
      mean_great_circle_distance_nm: average(greatCircleDistancesNm),
      mean_route_efficiency_pct: average(routeEfficiencies),
    },
    environment: {
      low_altitude_threshold_ft: lowAltitudeFt,
      low_altitude_threshold_m: lowAltitudeM,
      low_altitude_reference_mode: lowAltitudeReferenceMode,
      low_altitude_reference_samples: lowAltitudeReferenceSamples,
      flight_instance_gap_seconds: flightInstanceGapSeconds,
      flight_instance_reset_distance_m: flightInstanceResetDistanceM,
      flight_instance_jump_m: flightInstanceJumpM,
      low_altitude_share_pct:
        (annotatedAltitudeRows.filter((row) => row.alt_agl_proxy_m < lowAltitudeM).length /
          annotatedAltitudeRows.length) *
        100,
      mean_altitude_m: average(rows.map((row) => row.alt)),
      median_altitude_m: median(rows.map((row) => row.alt)),
      mean_altitude_agl_proxy_m: average(annotatedAltitudeRows.map((row) => row.alt_agl_proxy_m)),
      median_altitude_agl_proxy_m: median(annotatedAltitudeRows.map((row) => row.alt_agl_proxy_m)),
      mean_origin_altitude_m: average(originAltitudes),
      median_origin_altitude_m: median(originAltitudes),
      flight_instance_count: originAltitudes.length,
    },
    safety: {
      ...lowc.safety,
    },
    _client: {
      altitudes: rows.map((row) => row.alt),
      distancesNm,
      separationSamples: lowc.separationSamples,
      severities: lowc.events.map((event) => event.severity_ratio),
    },
  };

  return {
    dashboard,
    timeline: activeCounts.sort((a, b) => a.simt - b.simt),
    tracks: trajectoryFeatureCollection(features),
    conflicts: {
      type: "FeatureCollection",
      features: lowc.events.map((event) => ({
        type: "Feature",
        properties: event,
        geometry: { type: "Point", coordinates: [event.lon, event.lat] },
      })),
    },
    heatmap: sampleRows(rows, 10).map((row) => [row.lat, row.lon, 0.28]),
  };
}

function buildMultiRunModel(runs, uploaded) {
  const dashboards = runs.map((run) => run.dashboard);
  const dashboard = dashboards.length > 1 ? averageDashboard(dashboards) : dashboards[0];
  const comparison = buildComparison(runs, dashboard);
  return {
    dashboard,
    tracks: runs[0].tracks,
    conflicts: runs[0].conflicts,
    heatmap: runs[0].heatmap,
    timeline: runs[0].timeline,
    runs,
    comparison,
    metric_catalog: dashboard.metric_catalog || runs[0].dashboard.metric_catalog || [],
    uploaded,
  };
}

function averageDashboard(dashboards) {
  if (dashboards.length === 1) return dashboards[0];

  return {
    source_log: `Media de ${dashboards.length} STATELOGs`,
    summary: {
      records: dashboards.reduce((sum, item) => sum + item.summary.records, 0),
      aircraft_count: average(dashboards.map((item) => item.summary.aircraft_count)),
      sim_start_s: average(dashboards.map((item) => item.summary.sim_start_s)),
      sim_end_s: average(dashboards.map((item) => item.summary.sim_end_s)),
      duration_min: average(dashboards.map((item) => item.summary.duration_min)),
      mean_simultaneous_aircraft: average(dashboards.map((item) => item.summary.mean_simultaneous_aircraft)),
      peak_simultaneous_aircraft: average(dashboards.map((item) => item.summary.peak_simultaneous_aircraft)),
      bounds: {
        min_lat: Math.min(...dashboards.map((item) => item.summary.bounds.min_lat)),
        max_lat: Math.max(...dashboards.map((item) => item.summary.bounds.max_lat)),
        min_lon: Math.min(...dashboards.map((item) => item.summary.bounds.min_lon)),
        max_lon: Math.max(...dashboards.map((item) => item.summary.bounds.max_lon)),
      },
    },
    efficiency: {
      mean_flight_time_min: average(dashboards.map((item) => item.efficiency.mean_flight_time_min)),
      median_flight_time_min: average(dashboards.map((item) => item.efficiency.median_flight_time_min)),
      p95_flight_time_min: average(dashboards.map((item) => item.efficiency.p95_flight_time_min)),
      mean_distance_nm: average(dashboards.map((item) => item.efficiency.mean_distance_nm)),
      median_distance_nm: average(dashboards.map((item) => item.efficiency.median_distance_nm)),
      p95_distance_nm: average(dashboards.map((item) => item.efficiency.p95_distance_nm)),
      total_distance_km: dashboards.reduce((sum, item) => sum + item.efficiency.total_distance_km, 0),
      total_flight_hours: dashboards.reduce((sum, item) => sum + item.efficiency.total_flight_hours, 0),
      mean_great_circle_distance_nm: average(dashboards.map((item) => item.efficiency.mean_great_circle_distance_nm)),
      mean_route_efficiency_pct: average(dashboards.map((item) => item.efficiency.mean_route_efficiency_pct)),
    },
    environment: {
      low_altitude_threshold_ft: dashboards[0].environment.low_altitude_threshold_ft,
      low_altitude_threshold_m: dashboards[0].environment.low_altitude_threshold_m,
      low_altitude_reference_mode: dashboards[0].environment.low_altitude_reference_mode,
      low_altitude_reference_samples: dashboards[0].environment.low_altitude_reference_samples,
      flight_instance_gap_seconds: dashboards[0].environment.flight_instance_gap_seconds,
      flight_instance_reset_distance_m: dashboards[0].environment.flight_instance_reset_distance_m,
      flight_instance_jump_m: dashboards[0].environment.flight_instance_jump_m,
      low_altitude_share_pct: average(dashboards.map((item) => item.environment.low_altitude_share_pct)),
      mean_altitude_m: average(dashboards.map((item) => item.environment.mean_altitude_m)),
      median_altitude_m: average(dashboards.map((item) => item.environment.median_altitude_m)),
      mean_altitude_agl_proxy_m: average(dashboards.map((item) => item.environment.mean_altitude_agl_proxy_m)),
      median_altitude_agl_proxy_m: average(dashboards.map((item) => item.environment.median_altitude_agl_proxy_m)),
      mean_origin_altitude_m: average(dashboards.map((item) => item.environment.mean_origin_altitude_m)),
      median_origin_altitude_m: average(dashboards.map((item) => item.environment.median_origin_altitude_m)),
      flight_instance_count: average(dashboards.map((item) => item.environment.flight_instance_count)),
    },
    safety: {
      lowc_events: average(dashboards.map((item) => item.safety.lowc_events)),
      nmac_events: average(dashboards.map((item) => item.safety.nmac_events)),
      lowc_horizontal_m: dashboards[0].safety.lowc_horizontal_m,
      lowc_vertical_m: dashboards[0].safety.lowc_vertical_m,
      nmac_horizontal_m: dashboards[0].safety.nmac_horizontal_m,
      nmac_vertical_m: dashboards[0].safety.nmac_vertical_m,
      sample_seconds: dashboards[0].safety.sample_seconds,
      same_altitude_band_m: dashboards[0].safety.same_altitude_band_m,
      separation_samples: dashboards.reduce((sum, item) => sum + item.safety.separation_samples, 0),
      lowc_per_100_operations: average(dashboards.map((item) => item.safety.lowc_per_100_operations)),
      lowc_per_flight_hour: average(dashboards.map((item) => item.safety.lowc_per_flight_hour)),
      lowc_per_1000_km: average(dashboards.map((item) => item.safety.lowc_per_1000_km)),
      nmac_per_100_operations: average(dashboards.map((item) => item.safety.nmac_per_100_operations)),
      nmac_per_flight_hour: average(dashboards.map((item) => item.safety.nmac_per_flight_hour)),
      nmac_per_1000_km: average(dashboards.map((item) => item.safety.nmac_per_1000_km)),
      monitored_pair_samples: dashboards.reduce((sum, item) => sum + item.safety.monitored_pair_samples, 0),
      min_severity_ratio: Math.min(...dashboards.map((item) => item.safety.min_severity_ratio)),
      p05_severity_ratio: average(dashboards.map((item) => item.safety.p05_severity_ratio)),
      median_severity_ratio: average(dashboards.map((item) => item.safety.median_severity_ratio)),
      p95_severity_ratio: average(dashboards.map((item) => item.safety.p95_severity_ratio)),
      total_time_below_threshold_s: dashboards.reduce(
        (sum, item) => sum + item.safety.total_time_below_threshold_s,
        0
      ),
      mean_time_below_threshold_s: average(dashboards.map((item) => item.safety.mean_time_below_threshold_s)),
      max_time_below_threshold_s: Math.max(...dashboards.map((item) => item.safety.max_time_below_threshold_s)),
      mac_probability_low: dashboards[0].safety.mac_probability_low,
      mac_probability_nominal: dashboards[0].safety.mac_probability_nominal,
      mac_probability_high: dashboards[0].safety.mac_probability_high,
      expected_mac_low: average(dashboards.map((item) => item.safety.expected_mac_low)),
      expected_mac_nominal: average(dashboards.map((item) => item.safety.expected_mac_nominal)),
      expected_mac_high: average(dashboards.map((item) => item.safety.expected_mac_high)),
    },
    charts: dashboards[0].charts || {},
  };
}

function buildComparison(runs, dashboard) {
  const rows = runs.map((run) => comparisonRow(run.name, run.dashboard, false));
  rows.push(comparisonRow("Media", dashboard, true));
  return { run_count: runs.length, rows };
}

function comparisonRow(name, dashboard, isAverage) {
  return {
    name,
    records: dashboard.summary.records,
    aircraft: dashboard.summary.aircraft_count,
    peak: dashboard.summary.peak_simultaneous_aircraft,
    duration_min: dashboard.summary.duration_min,
    flight_time_min: dashboard.efficiency.mean_flight_time_min,
    distance_nm: dashboard.efficiency.mean_distance_nm,
    route_efficiency_pct: dashboard.efficiency.mean_route_efficiency_pct,
    low_altitude_pct: dashboard.environment.low_altitude_share_pct,
    lowc_events: dashboard.safety.lowc_events,
    nmac_events: dashboard.safety.nmac_events,
    lowc_per_flight_hour: dashboard.safety.lowc_per_flight_hour,
    min_severity_ratio: dashboard.safety.min_severity_ratio,
    is_average: isAverage,
  };
}

function annotateTrajectoryFrequencies(features) {
  const clusters = [];
  for (const feature of features) {
    const signature = trajectorySignature(feature.geometry.coordinates, 12);
    let cluster = clusters.find((candidate) => {
      const representative = candidate.signature;
      const startDistance = haversineM(signature[0][1], signature[0][0], representative[0][1], representative[0][0]);
      const endDistance = haversineM(
        signature[signature.length - 1][1],
        signature[signature.length - 1][0],
        representative[representative.length - 1][1],
        representative[representative.length - 1][0]
      );
      return startDistance <= 2500 && endDistance <= 2500 && meanTrajectoryDistance(signature, representative) <= 1200;
    });

    if (!cluster) {
      cluster = { signature, features: [] };
      clusters.push(cluster);
    }
    cluster.features.push(feature);
  }

  const maxFrequency = Math.max(1, ...clusters.map((cluster) => cluster.features.length));
  clusters.forEach((cluster, index) => {
    const frequency = cluster.features.length;
    const volumeRatio = frequency / maxFrequency;
    const volumeClass = volumeRatio >= 0.67 ? "high" : volumeRatio >= 0.34 ? "medium" : "low";
    cluster.features.forEach((feature) => {
      Object.assign(feature.properties, {
        trajectory_group: `T${String(index + 1).padStart(3, "0")}`,
        frequency,
        volume_ratio: volumeRatio,
        volume_class: volumeClass,
      });
    });
  });
  features.sort((left, right) => left.properties.frequency - right.properties.frequency);
}

function trajectoryFeatureCollection(features) {
  const groups = new Set(features.map((feature) => feature.properties.trajectory_group));
  return {
    type: "FeatureCollection",
    properties: {
      trajectory_count: features.length,
      trajectory_group_count: groups.size,
      max_frequency: Math.max(1, ...features.map((feature) => feature.properties.frequency)),
      cluster_distance_m: 1200,
      endpoint_tolerance_m: 2500,
      shape_points: 12,
    },
    features,
  };
}

function trajectorySignature(coordinates, pointCount) {
  if (coordinates.length <= 1) return new Array(pointCount).fill(coordinates[0]);
  const cumulative = [0];
  for (let index = 1; index < coordinates.length; index += 1) {
    const previous = coordinates[index - 1];
    const current = coordinates[index];
    cumulative.push(
      cumulative[index - 1] + haversineM(previous[1], previous[0], current[1], current[0])
    );
  }
  const totalDistance = cumulative[cumulative.length - 1];
  if (totalDistance <= 0) return new Array(pointCount).fill(coordinates[0]);

  return Array.from({ length: pointCount }, (_item, index) => {
    const targetDistance = (index / (pointCount - 1)) * totalDistance;
    let upper = cumulative.findIndex((distance) => distance >= targetDistance);
    if (upper < 0) upper = cumulative.length - 1;
    const lower = Math.max(0, upper - 1);
    const span = cumulative[upper] - cumulative[lower] || 1;
    const ratio = (targetDistance - cumulative[lower]) / span;
    const left = coordinates[lower];
    const right = coordinates[upper];
    return [
      left[0] + (right[0] - left[0]) * ratio,
      left[1] + (right[1] - left[1]) * ratio,
    ];
  });
}

function meanTrajectoryDistance(left, right) {
  return average(
    left.map((coordinate, index) =>
      haversineM(coordinate[1], coordinate[0], right[index][1], right[index][0])
    )
  );
}

function annotateFlightInstances(rows, byId) {
  const annotated = [];
  for (const [id, group] of byId.entries()) {
    group.sort((a, b) => a.simt - b.simt);
    let instanceNumber = 0;
    let previous = null;
    const localRows = [];

    for (const row of group) {
      if (previous) {
        const timeGap = row.simt - previous.simt;
        const distanceReset = row.distflown + flightInstanceResetDistanceM < previous.distflown;
        const jumpM = haversineM(previous.lat, previous.lon, row.lat, row.lon);
        if (timeGap > flightInstanceGapSeconds || distanceReset || jumpM > flightInstanceJumpM) {
          instanceNumber += 1;
        }
      }

      const annotatedRow = { ...row, flight_instance: `${id}#${instanceNumber}` };
      localRows.push(annotatedRow);
      previous = row;
    }

    for (const groupRows of groupBy(localRows, (row) => row.flight_instance).values()) {
      const originAltitude = median(groupRows.slice(0, lowAltitudeReferenceSamples).map((row) => row.alt));
      for (const row of groupRows) {
        row.origin_alt_m = originAltitude;
        row.alt_agl_proxy_m = row.alt - originAltitude;
        annotated.push(row);
      }
    }
  }

  return annotated.sort((a, b) => a.simt - b.simt || a.id.localeCompare(b.id));
}

function detectClientLowc(byTime, aircraftCount, totalFlightHours, totalDistanceKm) {
  const samples = [];
  const separationSamples = [];
  for (const [simtText, group] of byTime.entries()) {
    const simt = Number(simtText);
    if (simt % conflictSampleSeconds !== 0 || group.length < 2) continue;

    for (let i = 0; i < group.length; i += 1) {
      for (let j = i + 1; j < group.length; j += 1) {
        const a = group[i];
        const b = group[j];
        const distV = Math.abs(a.alt - b.alt);
        if (distV >= sameAltitudeBandM) continue;
        const distH = haversineM(a.lat, a.lon, b.lat, b.lon);
        separationSamples.push(distH);
        if (distH < lowcHorizontalM && distV < lowcVerticalM) {
          samples.push({
            simt,
            id_a: a.id,
            id_b: b.id,
            lat: (a.lat + b.lat) / 2,
            lon: (a.lon + b.lon) / 2,
            dist_h_m: distH,
            dist_v_m: distV,
            severity_ratio: Math.min(distH / lowcHorizontalM, distV / lowcVerticalM),
            is_nmac: distH < nmacHorizontalM && distV < nmacVerticalM,
          });
        }
      }
    }
  }
  const events = collapseClientLowcSamples(samples);
  return {
    events,
    separationSamples,
    safety: clientSafetySummary(events, separationSamples.length, aircraftCount, totalFlightHours, totalDistanceKm),
  };
}

function collapseClientLowcSamples(samples) {
  const grouped = groupBy(samples, (sample) => [sample.id_a, sample.id_b].sort().join("::"));
  const events = [];
  for (const group of grouped.values()) {
    group.sort((a, b) => a.simt - b.simt);
    let current = [];
    for (const sample of group) {
      if (current.length && sample.simt - current[current.length - 1].simt > conflictSampleSeconds * 1.5) {
        events.push(summarizeClientLowcEvent(current));
        current = [];
      }
      current.push(sample);
    }
    if (current.length) events.push(summarizeClientLowcEvent(current));
  }
  return events.sort((a, b) => a.simt - b.simt);
}

function summarizeClientLowcEvent(samples) {
  const mostSevere = samples.reduce((best, item) => (item.severity_ratio < best.severity_ratio ? item : best));
  return {
    ...mostSevere,
    start_simt: samples[0].simt,
    end_simt: samples[samples.length - 1].simt,
    duration_s: samples.length * conflictSampleSeconds,
    sample_count: samples.length,
    is_nmac: samples.some((sample) => sample.is_nmac),
  };
}

function clientSafetySummary(events, pairSampleCount, aircraftCount, totalFlightHours, totalDistanceKm) {
  const lowcCount = events.length;
  const nmacCount = events.filter((event) => event.is_nmac).length;
  const severities = events.map((event) => event.severity_ratio);
  const durations = events.map((event) => event.duration_s);
  return {
    lowc_events: lowcCount,
    nmac_events: nmacCount,
    lowc_horizontal_m: lowcHorizontalM,
    lowc_vertical_m: lowcVerticalM,
    nmac_horizontal_m: nmacHorizontalM,
    nmac_vertical_m: nmacVerticalM,
    sample_seconds: conflictSampleSeconds,
    same_altitude_band_m: sameAltitudeBandM,
    separation_samples: pairSampleCount,
    lowc_per_100_operations: safeRate(lowcCount, aircraftCount, 100),
    lowc_per_flight_hour: safeRate(lowcCount, totalFlightHours),
    lowc_per_1000_km: safeRate(lowcCount, totalDistanceKm, 1000),
    nmac_per_100_operations: safeRate(nmacCount, aircraftCount, 100),
    nmac_per_flight_hour: safeRate(nmacCount, totalFlightHours),
    nmac_per_1000_km: safeRate(nmacCount, totalDistanceKm, 1000),
    monitored_pair_samples: pairSampleCount,
    min_severity_ratio: severities.length ? Math.min(...severities) : 0,
    p05_severity_ratio: percentile(severities, 0.05),
    median_severity_ratio: median(severities),
    p95_severity_ratio: percentile(severities, 0.95),
    total_time_below_threshold_s: durations.reduce((sum, value) => sum + value, 0),
    mean_time_below_threshold_s: average(durations),
    max_time_below_threshold_s: durations.length ? Math.max(...durations) : 0,
    mac_probability_low: macProbabilityBands[0],
    mac_probability_nominal: macProbabilityBands[1],
    mac_probability_high: macProbabilityBands[2],
    expected_mac_low: nmacCount * macProbabilityBands[0],
    expected_mac_nominal: nmacCount * macProbabilityBands[1],
    expected_mac_high: nmacCount * macProbabilityBands[2],
  };
}

function renderTraceability(catalog) {
  const body = document.getElementById("traceability-table-body");
  if (!body) return;
  body.innerHTML = (catalog || [])
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
    .join("");
}

function drawHistogram(canvas, values, color) {
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = Math.max(220, Math.round(width / 2.5));
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);

  const clean = values.filter(Number.isFinite);
  if (!clean.length) {
    ctx.fillStyle = "#667085";
    ctx.font = "14px system-ui";
    ctx.fillText("Sem dados", 18, 34);
    return;
  }

  const bins = Math.min(48, Math.max(12, Math.round(Math.sqrt(clean.length))));
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const span = max - min || 1;
  const counts = new Array(bins).fill(0);
  for (const value of clean) {
    const index = Math.min(bins - 1, Math.floor(((value - min) / span) * bins));
    counts[index] += 1;
  }

  const pad = { left: 42, right: 14, top: 18, bottom: 34 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const maxCount = Math.max(...counts);

  ctx.strokeStyle = "#d8e0ea";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, pad.top + plotHeight);
  ctx.lineTo(pad.left + plotWidth, pad.top + plotHeight);
  ctx.stroke();

  ctx.fillStyle = color;
  counts.forEach((count, index) => {
    const barWidth = plotWidth / bins - 2;
    const barHeight = (count / maxCount) * plotHeight;
    const x = pad.left + index * (plotWidth / bins) + 1;
    const y = pad.top + plotHeight - barHeight;
    ctx.fillRect(x, y, Math.max(1, barWidth), barHeight);
  });

  ctx.fillStyle = "#667085";
  ctx.font = "12px system-ui";
  ctx.fillText(formatNumber(min, 1), pad.left, height - 10);
  ctx.fillText(formatNumber(max, 1), width - pad.right - 52, height - 10);
}

function sampleRows(rows, stride) {
  const sampled = rows.filter((_row, index) => index % stride === 0);
  if (sampled.length < 2 && rows.length) return rows;
  return sampled;
}

function groupBy(rows, getKey) {
  const map = new Map();
  for (const row of rows) {
    const key = getKey(row);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(row);
  }
  return map;
}

function colorForVolume(volumeRatio) {
  const ratio = Math.max(0, Math.min(1, Number(volumeRatio) || 0));
  if (ratio >= 0.67) return "#dc2626";
  if (ratio >= 0.34) return "#f59e0b";
  return "#0ea5e9";
}

function haversineM(lat1, lon1, lat2, lon2) {
  const r = 6371000;
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dp = ((lat2 - lat1) * Math.PI) / 180;
  const dl = ((lon2 - lon1) * Math.PI) / 180;
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function average(values) {
  const clean = values.filter(Number.isFinite);
  return clean.length ? clean.reduce((sum, value) => sum + value, 0) / clean.length : 0;
}

function median(values) {
  const clean = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!clean.length) return 0;
  const middle = Math.floor(clean.length / 2);
  return clean.length % 2 ? clean[middle] : (clean[middle - 1] + clean[middle]) / 2;
}

function percentile(values, q) {
  const clean = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!clean.length) return 0;
  const position = (clean.length - 1) * q;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return clean[lower];
  return clean[lower] + (clean[upper] - clean[lower]) * (position - lower);
}

function safeRate(numerator, denominator, scale = 1) {
  return denominator > 0 ? (numerator / denominator) * scale : 0;
}

function formatNumber(value, digits = 0) {
  if (!Number.isFinite(Number(value))) return "-";
  return Number(value).toLocaleString("pt-BR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
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
