const state = {
  map: null,
  tracksLayer: null,
  heatLayer: null,
  conflictLayer: null,
  baseLayers: {},
  overlayLayers: {},
  lastTracks: null,
  lastConflicts: null,
};

const colors = ["#1d4ed8", "#047857", "#be123c", "#6d28d9", "#b45309", "#0e7490", "#c2410c"];

const metersPerNm = 1852;
const feetToMeters = 0.3048;

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

  const osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap",
    maxZoom: 19,
    updateWhenIdle: true,
    keepBuffer: 4,
  }).addTo(state.map);

  const positron = L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    maxZoom: 20,
    updateWhenIdle: true,
    keepBuffer: 4,
  });

  state.baseLayers = {
    OpenStreetMap: osm,
    "Base clara": positron,
  };
}

function bindLayerControls() {
  document.getElementById("layer-tracks").addEventListener("change", (event) => toggleLayer("tracksLayer", event));
  document.getElementById("layer-heat").addEventListener("change", (event) => toggleLayer("heatLayer", event));
  document.getElementById("layer-conflicts").addEventListener("change", (event) => toggleLayer("conflictLayer", event));
  document.getElementById("fit-map").addEventListener("click", () => {
    fitMapToOperationalArea(state.lastTracks, state.lastConflicts);
  });
}

function bindUpload() {
  document.getElementById("log-upload").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const text = await file.text();
    const parsed = parseStateLog(text);
    const model = buildClientModel(parsed, file.name);
    renderDashboard({ ...model, uploaded: true });
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
  renderMetrics(model.dashboard);
  renderCharts(model.dashboard, model.timeline, model.uploaded);
  renderMapLayers(model.tracks, model.conflicts, model.heatmap);
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
  setText("metric-low-altitude-threshold", `< ${formatNumber(environment.low_altitude_threshold_ft, 0)} ft`);
  setText("metric-lowc", formatNumber(safety.lowc_events));
  setText("metric-lowc-threshold", `${formatNumber(safety.lowc_horizontal_m, 0)} m x ${formatNumber(safety.lowc_vertical_m, 0)} m`);
  setText("kpa-route-efficiency", `${formatNumber(efficiency.mean_route_efficiency_pct, 1)}%`);
  setText("kpa-altitude", `${formatNumber(environment.median_altitude_m, 0)} m`);
  setText("kpa-safety-sample", `${formatNumber(safety.sample_seconds, 0)} s`);
}

function renderCharts(dashboard, timeline, uploaded) {
  if (!uploaded) {
    showImageChart("chart-active", "canvas-active", dashboard.charts.active_aircraft);
    showImageChart("chart-separation", "canvas-separation", dashboard.charts.separation_histogram);
    showImageChart("chart-altitude", "canvas-altitude", dashboard.charts.altitude_histogram);
    showImageChart("chart-distance", "canvas-distance", dashboard.charts.distance_histogram);
    return;
  }

  showCanvasChart("chart-active", "canvas-active", timeline.map((item) => item.aircraft), "#2563eb");
  showCanvasChart("chart-separation", "canvas-separation", dashboard._client.separationSamples, "#dc2626");
  showCanvasChart("chart-altitude", "canvas-altitude", dashboard._client.altitudes, "#0f766e");
  showCanvasChart("chart-distance", "canvas-distance", dashboard._client.distancesNm, "#7c3aed");
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
  clearLayer("tracksLayer");
  clearLayer("heatLayer");
  clearLayer("conflictLayer");

  const routeHalo = L.geoJSON(tracks, {
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

  const routeLines = L.geoJSON(tracks, {
    pane: "routePane",
    style: (feature) => ({
      color: colorForId(feature.properties.id),
      opacity: 1,
      weight: 4,
      lineCap: "round",
      lineJoin: "round",
    }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindTooltip(`${escapeHtml(p.id)} - ${formatNumber(p.distance_nm, 1)} NM`, {
        sticky: true,
      });
      layer.bindPopup(
        `<strong>Aeronave ${escapeHtml(p.id)}</strong><br>` +
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
        `<strong>Evento LoWC</strong><br>` +
          `${escapeHtml(p.id_a)} / ${escapeHtml(p.id_b)}<br>` +
          `${formatNumber(p.dist_h_m, 1)} m horizontal<br>` +
          `${formatNumber(p.dist_v_m, 1)} m vertical<br>` +
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

  const airportMarkers = buildEndpointLayer(tracks);
  state.tracksLayer.addLayer(airportMarkers);

  if (L.heatLayer) {
    state.heatLayer = L.heatLayer(heatmap, {
      pane: "heatPane",
      radius: 18,
      blur: 22,
      minOpacity: 0.28,
      maxZoom: 12,
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
          fillOpacity: 0.32,
          fillColor: "#2563eb",
        })
      )
    );
  }

  applyCheckedLayer("layer-heat", state.heatLayer);
  applyCheckedLayer("layer-tracks", state.tracksLayer);
  applyCheckedLayer("layer-conflicts", state.conflictLayer);

  fitMapToOperationalArea(tracks, conflicts);
  updateMapInfo(tracks, conflicts, heatmap);
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

function updateMapInfo(tracks, conflicts, heatmap) {
  const aircraft = tracks.features?.length || 0;
  const lowc = conflicts.features?.length || 0;
  const density = heatmap.length || 0;
  setText("map-info-title", "Mapa operacional");
  setText(
    "map-info-text",
    `${formatNumber(aircraft)} rotas amostradas, ${formatNumber(density)} pontos de densidade e ${formatNumber(lowc)} eventos LoWC. Clique nas linhas ou pontos para detalhes.`
  );
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
  const routeEfficiencies = [];
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
    durations.push((last.simt - first.simt) / 60);
    if (distanceM > 0) {
      routeEfficiencies.push((haversineM(first.lat, first.lon, last.lat, last.lon) / distanceM) * 100);
    }

    const sampled = sampleRows(group, 20);
    features.push({
      type: "Feature",
      properties: {
        id,
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

  const lowAltitudeFt = 1500;
  const lowAltitudeM = lowAltitudeFt * feetToMeters;
  const lowc = detectClientLowc(byTime, 500, 30, 10);

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
      mean_distance_nm: average(distancesNm),
      median_distance_nm: median(distancesNm),
      mean_route_efficiency_pct: average(routeEfficiencies),
    },
    environment: {
      low_altitude_threshold_ft: lowAltitudeFt,
      low_altitude_threshold_m: lowAltitudeM,
      low_altitude_share_pct: (rows.filter((row) => row.alt < lowAltitudeM).length / rows.length) * 100,
      mean_altitude_m: average(rows.map((row) => row.alt)),
      median_altitude_m: median(rows.map((row) => row.alt)),
    },
    safety: {
      lowc_events: lowc.events.length,
      lowc_horizontal_m: 500,
      lowc_vertical_m: 30,
      sample_seconds: 10,
      separation_samples: lowc.separationSamples.length,
    },
    _client: {
      altitudes: rows.map((row) => row.alt),
      distancesNm,
      separationSamples: lowc.separationSamples,
    },
  };

  return {
    dashboard,
    timeline: activeCounts.sort((a, b) => a.simt - b.simt),
    tracks: { type: "FeatureCollection", features },
    conflicts: {
      type: "FeatureCollection",
      features: lowc.events.map((event) => ({
        type: "Feature",
        properties: event,
        geometry: { type: "Point", coordinates: [event.lon, event.lat] },
      })),
    },
    heatmap: sampleRows(rows, 10).map((row) => [row.lat, row.lon, 0.65]),
  };
}

function detectClientLowc(byTime, horizontalM, verticalM, sampleSeconds) {
  const events = [];
  const separationSamples = [];
  for (const [simtText, group] of byTime.entries()) {
    const simt = Number(simtText);
    if (simt % sampleSeconds !== 0 || group.length < 2) continue;

    for (let i = 0; i < group.length; i += 1) {
      for (let j = i + 1; j < group.length; j += 1) {
        const a = group[i];
        const b = group[j];
        const distV = Math.abs(a.alt - b.alt);
        if (distV >= 150) continue;
        const distH = haversineM(a.lat, a.lon, b.lat, b.lon);
        separationSamples.push(distH);
        if (distH < horizontalM && distV < verticalM) {
          events.push({
            simt,
            id_a: a.id,
            id_b: b.id,
            lat: (a.lat + b.lat) / 2,
            lon: (a.lon + b.lon) / 2,
            dist_h_m: distH,
            dist_v_m: distV,
          });
        }
      }
    }
  }
  return { events, separationSamples };
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

function colorForId(id) {
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) {
    hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  }
  return colors[hash % colors.length];
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
