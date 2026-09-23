const state = {
  map: null,
  tracksLayer: null,
  officialRehLayer: null,
  plannedLayer: null,
  heatLayer: null,
  atdHotspotLayer: null,
  complexityLayer: null,
  conflictLayer: null,
  resourceHighlightLayer: null,
  baseLayers: {},
  overlayLayers: {},
  lastTracks: null,
  lastConflicts: null,
  lastOfficialReh: null,
  lastCapacity: null,
  runs: [],
  comparison: null,
  activeRunIndex: 0,
  activeDayKey: null,
  trajectoryVolumeFilter: "all",
  conflictPairFilter: "all",
  activeKpa: "overview",
};

const viewer3d = {
  data: null,
  conflicts: [],
  macTimestampAvailable: false,
  currentTime: 0,
  playing: false,
  speed: 20,
  verticalScale: 5,
  yaw: -0.65,
  pitch: 0.58,
  zoom: 1,
  lastFrame: null,
  animationFrame: null,
  dragging: false,
  pointerX: 0,
  pointerY: 0,
};

document.addEventListener("DOMContentLoaded", () => {
  bindLayerControls();
  bindConflictPairControls();
  bindKpaTabs();
  bindCapacityResourceLinks();
  if (typeof window.L !== "undefined") {
    initMap();
  } else {
    showMapUnavailable();
  }
  loadStaticDashboard().catch((error) => {
    console.error(error);
    setText("comparison-summary", "Falha ao carregar o pacote de dados do dashboard.");
  });
});

function showMapUnavailable() {
  const map = document.getElementById("map");
  if (map) {
    map.innerHTML = `
      <div class="map-unavailable">
        <strong>Mapa indisponivel</strong>
        <span>O Leaflet externo nao foi carregado. Indicadores, tabelas e graficos continuam disponiveis.</span>
      </div>`;
  }
}

async function loadStaticDashboard() {
  if (window.__UAM_DASHBOARD_DATA__) {
    renderDashboard(window.__UAM_DASHBOARD_DATA__);
    return;
  }

  const [dashboard, tracks, plannedRoutes, officialReh, conflicts, heatmap, comparison] = await Promise.all([
    fetchJson("assets/data/dashboard.json"),
    fetchJson("assets/data/tracks.geojson"),
    fetchJson("assets/data/planned_routes.geojson"),
    fetchJson("assets/data/official_reh.geojson"),
    fetchJson("assets/data/conflicts.geojson"),
    fetchJson("assets/data/heatmap_points.json"),
    fetchJson("assets/data/comparison.json"),
  ]);

  renderDashboard({ dashboard, tracks, planned_routes: plannedRoutes, official_reh: officialReh, conflicts, heatmap, comparison });
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
  document.getElementById("layer-official-reh").addEventListener("change", (event) => toggleLayer("officialRehLayer", event));
  document.getElementById("layer-planned").addEventListener("change", (event) => toggleLayer("plannedLayer", event));
  document.getElementById("layer-heat").addEventListener("change", (event) => toggleLayer("heatLayer", event));
  document.getElementById("layer-atd-hotspots").addEventListener("change", (event) => toggleLayer("atdHotspotLayer", event));
  document.getElementById("layer-complexity").addEventListener("change", (event) => toggleLayer("complexityLayer", event));
  document.getElementById("layer-conflicts").addEventListener("change", (event) => toggleLayer("conflictLayer", event));
  document.getElementById("trajectory-volume-filter").addEventListener("change", (event) => {
    state.trajectoryVolumeFilter = event.target.value;
    const run = state.runs[state.activeRunIndex] || state.runs[0];
    if (run && state.map) renderMapLayers(run.tracks, run.planned_routes, run.official_reh, run.conflicts, run.heatmap, run.dashboard.capacity);
  });
  document.getElementById("fit-map").addEventListener("click", () => {
    if (state.map) fitMapToOperationalArea(state.lastTracks, state.lastConflicts);
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
  if (!layer || !state.map) return;
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
    official_reh: model.official_reh || emptyFeatureCollection(),
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
  if (state.map) {
    renderMapLayers(run.tracks, run.planned_routes, run.official_reh || emptyFeatureCollection(), run.conflicts, run.heatmap, run.dashboard.capacity);
  }
}

function bind3DControls() {
  const canvas = document.getElementById("viewer3d-canvas");
  const play = document.getElementById("viewer3d-play");
  const timeline = document.getElementById("viewer3d-time");
  play.addEventListener("click", () => {
    if (!viewer3d.data) return;
    if (viewer3d.currentTime >= viewer3d.data.sim_end_s) viewer3d.currentTime = viewer3d.data.sim_start_s;
    viewer3d.playing = !viewer3d.playing;
    viewer3d.lastFrame = null;
    update3DControls();
    if (viewer3d.playing) viewer3d.animationFrame = requestAnimationFrame(animate3D);
  });
  timeline.addEventListener("input", (event) => {
    viewer3d.playing = false;
    viewer3d.currentTime = Number(event.target.value);
    update3DControls();
    draw3D();
  });
  document.getElementById("viewer3d-speed").addEventListener("change", (event) => {
    viewer3d.speed = Number(event.target.value);
  });
  document.getElementById("viewer3d-vertical-scale").addEventListener("change", (event) => {
    viewer3d.verticalScale = Number(event.target.value);
    draw3D();
  });
  document.getElementById("viewer3d-reset").addEventListener("click", () => {
    viewer3d.yaw = -0.65;
    viewer3d.pitch = 0.58;
    viewer3d.zoom = 1;
    draw3D();
  });
  canvas.addEventListener("pointerdown", (event) => {
    viewer3d.dragging = true;
    viewer3d.pointerX = event.clientX;
    viewer3d.pointerY = event.clientY;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!viewer3d.dragging) return;
    viewer3d.yaw += (event.clientX - viewer3d.pointerX) * 0.008;
    viewer3d.pitch = Math.max(0.08, Math.min(1.35, viewer3d.pitch + (event.clientY - viewer3d.pointerY) * 0.006));
    viewer3d.pointerX = event.clientX;
    viewer3d.pointerY = event.clientY;
    draw3D();
  });
  canvas.addEventListener("pointerup", () => { viewer3d.dragging = false; });
  canvas.addEventListener("pointercancel", () => { viewer3d.dragging = false; });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    viewer3d.zoom = Math.max(0.55, Math.min(3, viewer3d.zoom * (event.deltaY > 0 ? 0.9 : 1.1)));
    draw3D();
  }, { passive: false });
  if (window.ResizeObserver) new ResizeObserver(() => draw3D()).observe(canvas);
}

function render3DVisualization(data, conflicts) {
  viewer3d.playing = false;
  viewer3d.lastFrame = null;
  viewer3d.data = data || null;
  viewer3d.conflicts = conflicts?.features || [];
  viewer3d.macTimestampAvailable = Boolean(conflicts?.properties?.mac_timestamp_available);
  renderConflictTimeline(filteredConflictFeatures(viewer3d.conflicts), viewer3d.macTimestampAvailable);
  if (!data?.tracks?.length) {
    setText("viewer3d-status", "Sem trajetórias 3D para este cenário.");
    update3DControls();
    draw3D();
    return;
  }
  viewer3d.currentTime = data.sim_start_s;
  setText(
    "viewer3d-note",
    `Plano-base a ${formatNumber(data.ground_plane_msl_ft, 0)} pés (${formatNumber(data.ground_plane_msl_m, 1)} m) MSL · janelas de ${data.sample_seconds} s.`
  );
  const timeline = document.getElementById("viewer3d-time");
  timeline.min = data.sim_start_s;
  timeline.max = data.sim_end_s;
  timeline.step = data.sample_seconds;
  timeline.value = viewer3d.currentTime;
  update3DControls();
  draw3D();
}

function animate3D(timestamp) {
  if (!viewer3d.playing || !viewer3d.data) return;
  if (viewer3d.lastFrame === null) viewer3d.lastFrame = timestamp;
  const elapsed = (timestamp - viewer3d.lastFrame) / 1000;
  const interval = viewer3d.data.sample_seconds;
  const next = viewer3d.currentTime + elapsed * viewer3d.speed;
  const aligned = viewer3d.data.sim_start_s + Math.floor((next - viewer3d.data.sim_start_s) / interval) * interval;
  if (aligned !== viewer3d.currentTime) {
    viewer3d.currentTime = Math.min(aligned, viewer3d.data.sim_end_s);
    viewer3d.lastFrame = timestamp;
    update3DControls();
    draw3D();
  }
  if (viewer3d.currentTime >= viewer3d.data.sim_end_s) {
    viewer3d.playing = false;
    update3DControls();
    return;
  }
  viewer3d.animationFrame = requestAnimationFrame(animate3D);
}

function update3DControls() {
  const play = document.getElementById("viewer3d-play");
  const timeline = document.getElementById("viewer3d-time");
  play.textContent = viewer3d.playing ? "Pausar" : "Reproduzir";
  play.setAttribute("aria-pressed", String(viewer3d.playing));
  play.disabled = !viewer3d.data;
  timeline.disabled = !viewer3d.data;
  if (viewer3d.data) timeline.value = viewer3d.currentTime;
  setText("viewer3d-time-label", formatSimulationTime(viewer3d.currentTime));
}

function formatSimulationTime(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = String(Math.floor(value / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((value % 3600) / 60)).padStart(2, "0");
  const secs = String(value % 60).padStart(2, "0");
  return `${hours}:${minutes}:${secs}`;
}

function conflictEventClass(feature) {
  const properties = feature?.properties || feature || {};
  if (properties.event_class === "mac" || properties.is_mac) return "mac";
  if (properties.event_class === "nmac" || properties.is_nmac) return "nmac";
  return "lowc";
}

function conflictEventLabel(feature) {
  const eventClass = conflictEventClass(feature);
  return eventClass === "mac" ? "MAC" : eventClass === "nmac" ? "NMAC" : "LoWC";
}

function conflictEventColor(feature) {
  const eventClass = conflictEventClass(feature);
  return eventClass === "mac" ? "#dc2626" : eventClass === "nmac" ? "#f97316" : "#facc15";
}

function conflictPairKey(feature) {
  const pair = String(feature?.properties?.vehicle_pair || "").toLowerCase();
  const hasEvtol = pair.includes("evtol");
  const helicopterCount = (pair.match(/helicoptero/g) || []).length;
  if (hasEvtol && helicopterCount) return "evtol-helicoptero";
  if (hasEvtol) return "evtol-evtol";
  if (helicopterCount >= 2) return "helicoptero-helicoptero";
  return "desconhecido";
}

function filteredConflictFeatures(features) {
  if (state.conflictPairFilter === "all") return features || [];
  return (features || []).filter((feature) => conflictPairKey(feature) === state.conflictPairFilter);
}

function filteredConflictCollection(conflicts) {
  return {
    ...(conflicts || emptyFeatureCollection()),
    features: filteredConflictFeatures(conflicts?.features || []),
  };
}

function bindConflictPairControls() {
  document.querySelectorAll("[data-conflict-pair]").forEach((button) => {
    button.addEventListener("click", () => {
      state.conflictPairFilter = button.dataset.conflictPair;
      document.querySelectorAll("[data-conflict-pair]").forEach((item) => {
        const active = item.dataset.conflictPair === state.conflictPairFilter;
        item.classList.toggle("active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      renderConflictTimeline(filteredConflictFeatures(viewer3d.conflicts), viewer3d.macTimestampAvailable);
      draw3D();
      const run = state.runs[state.activeRunIndex] || state.runs[0];
      if (run && state.map) {
        renderMapLayers(run.tracks, run.planned_routes, run.official_reh, run.conflicts, run.heatmap, run.dashboard.capacity);
      }
    });
  });
}

function bindKpaTabs() {
  document.querySelectorAll("[data-kpa-tab]").forEach((button) => {
    button.addEventListener("click", () => activateKpa(button.dataset.kpaTab));
  });
  activateKpa(state.activeKpa);
}

function activateKpa(kpa) {
  state.activeKpa = kpa || "overview";
  document.querySelectorAll("[data-kpa-tab]").forEach((button) => {
    const active = button.dataset.kpaTab === state.activeKpa;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  document.querySelectorAll("[data-kpa-panel]").forEach((panel) => {
    panel.hidden = !String(panel.dataset.kpaPanel).split(/\s+/).includes(state.activeKpa);
  });
  document.querySelectorAll("[data-kpa-child]").forEach((child) => {
    child.hidden = child.dataset.kpaChild !== state.activeKpa;
  });
  if (state.activeKpa === "overview" && state.map) {
    window.setTimeout(() => state.map.invalidateSize(true), 0);
  }
}

function bindCapacityResourceLinks() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-map-target]");
    if (!button) return;
    try {
      highlightMapResource(JSON.parse(button.dataset.mapTarget));
    } catch (error) {
      console.error("Invalid map target", error);
    }
  });
}

function renderConflictTimeline(features, macTimestampAvailable) {
  const body = document.getElementById("conflict-timeline-body");
  if (!body) return;
  const ordered = [...features].sort((left, right) => left.properties.start_simt - right.properties.start_simt);
  const counts = { lowc: 0, nmac: 0, mac: 0 };
  for (const feature of ordered) counts[conflictEventClass(feature)] += 1;
  setText(
    "conflict-timeline-summary",
    `${counts.lowc} LoWC fora de NMAC · ${counts.nmac} NMAC · ${counts.mac} MAC observados`
  );
  body.innerHTML = ordered.length
    ? ordered.map((feature) => {
        const p = feature.properties;
        const eventClass = conflictEventClass(feature);
        const timeButton = (value) => `<button class="conflict-time-button" type="button" data-simt="${Number(value)}">${formatSimulationTime(value)}</button>`;
        return `<tr>
          <td><span class="event-label ${eventClass}">${conflictEventLabel(feature)}</span></td>
          <td>${timeButton(p.start_simt)}</td>
          <td>${timeButton(p.simt)}</td>
          <td>${timeButton(p.end_simt)}</td>
          <td>${escapeHtml(p.id_a)} / ${escapeHtml(p.id_b)}</td>
          <td>${escapeHtml(p.vehicle_pair || "tipos desconhecidos")}</td>
          <td>${formatNumber(p.dist_h_m, 1)} m / ${formatNumber(p.dist_v_m, 1)} m</td>
        </tr>`;
      }).join("")
    : `<tr><td colspan="7">Nenhum evento LoWC/NMAC observado para esta combinação.</td></tr>`;
  body.querySelectorAll("[data-simt]").forEach((button) => {
    button.addEventListener("click", () => {
      viewer3d.playing = false;
      viewer3d.currentTime = Number(button.dataset.simt);
      update3DControls();
      draw3D();
      document.getElementById("viewer3d-canvas").scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });
  setText(
    "mac-availability",
    macTimestampAvailable
      ? "O log contém eventos MAC observáveis e seus timestamps estão listados em vermelho."
      : "MAC não possui timestamp neste conjunto: o indicador atual é uma expectativa probabilística derivada de NMAC, não uma colisão observada."
  );
}

function pointAtOrBefore(points, time) {
  let low = 0;
  let high = points.length - 1;
  let result = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (points[middle][0] <= time) { result = middle; low = middle + 1; }
    else high = middle - 1;
  }
  return result;
}

function draw3D() {
  const canvas = document.getElementById("viewer3d-canvas");
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.round(rect.width * dpr);
  const height = Math.round(rect.height * dpr);
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  const data = viewer3d.data;
  if (!data?.tracks?.length) return;

  const bounds = data.bounds;
  const centerLat = (bounds.min_lat + bounds.max_lat) / 2;
  const centerLon = (bounds.min_lon + bounds.max_lon) / 2;
  const metersLon = 111320 * Math.cos(centerLat * Math.PI / 180);
  const rangeX = Math.max(1000, (bounds.max_lon - bounds.min_lon) * metersLon);
  const rangeZ = Math.max(1000, (bounds.max_lat - bounds.min_lat) * 111320);
  const minAlt = data.altitude_bounds_m[0];
  const maxAlt = data.altitude_bounds_m[1];
  const groundAlt = Number.isFinite(data.ground_plane_msl_m) ? data.ground_plane_msl_m : minAlt;
  const cosY = Math.cos(viewer3d.yaw), sinY = Math.sin(viewer3d.yaw);
  const cosP = Math.cos(viewer3d.pitch), sinP = Math.sin(viewer3d.pitch);
  const verticalRange = Math.max(maxAlt, groundAlt) - Math.min(minAlt, groundAlt);
  const scale = Math.min(rect.width / (rangeX * 1.35), rect.height / (rangeZ * 1.05 + Math.max(100, verticalRange) * viewer3d.verticalScale)) * viewer3d.zoom;
  const originX = rect.width / 2;
  const originY = rect.height * 0.61;
  const project = (lon, lat, alt = groundAlt) => {
    const x = (lon - centerLon) * metersLon;
    const z = (lat - centerLat) * 111320;
    const y = (alt - groundAlt) * viewer3d.verticalScale;
    const xr = x * cosY - z * sinY;
    const zr = x * sinY + z * cosY;
    return { x: originX + xr * scale, y: originY - (y * cosP - zr * sinP) * scale, depth: y * sinP + zr * cosP };
  };

  draw3DGround(ctx, project, bounds, groundAlt, rect.width, data.ground_plane_msl_ft);
  const markers = [];
  let activeCount = 0;
  for (const track of data.tracks) {
    const color = track.vehicle_type === "evtol" ? "#22d3ee" : track.vehicle_type === "helicoptero" ? "#a3e635" : "#a78bfa";
    draw3DLine(ctx, track.points, project, color, 0.11, 0, track.points.length - 1);
    const index = pointAtOrBefore(track.points, viewer3d.currentTime);
    if (index < 0 || viewer3d.currentTime - track.points[index][0] > data.sample_seconds) continue;
    activeCount += 1;
    draw3DLine(ctx, track.points, project, color, 0.82, Math.max(0, index - Math.ceil(120 / data.sample_seconds)), index);
    const point = track.points[index];
    const position = project(point[1], point[2], point[3]);
    const previous = track.points[Math.max(0, index - 1)];
    const previousPosition = project(previous[1], previous[2], previous[3]);
    markers.push({
      ...position,
      color,
      label: track.id,
      vehicleType: track.vehicle_type,
      angle: Math.atan2(position.y - previousPosition.y, position.x - previousPosition.x),
    });
  }
  const activeConflicts = filteredConflictFeatures(viewer3d.conflicts).filter((feature) => {
    const p = feature.properties;
    return p.start_simt <= viewer3d.currentTime && p.end_simt >= viewer3d.currentTime;
  });
  for (const feature of activeConflicts) {
    const coordinates = feature.geometry.coordinates;
    markers.push({
      ...project(coordinates[0], coordinates[1], coordinates[2] ?? groundAlt),
      color: conflictEventColor(feature),
      conflict: true,
      eventClass: conflictEventClass(feature),
    });
  }
  markers.sort((a, b) => a.depth - b.depth);
  for (const marker of markers) {
    if (marker.conflict) drawConflictSymbol(ctx, marker);
    else drawAircraftSymbol(ctx, marker);
  }
  const activeCounts = { lowc: 0, nmac: 0, mac: 0 };
  for (const feature of activeConflicts) activeCounts[conflictEventClass(feature)] += 1;
  setText(
    "viewer3d-status",
    `${activeCount} aeronaves · ${activeCounts.lowc} LoWC fora de NMAC · ${activeCounts.nmac} NMAC · ${activeCounts.mac} MAC ativos · amostra de ${data.sample_seconds} s`
  );
}

function drawConflictSymbol(ctx, marker) {
  ctx.save();
  ctx.translate(marker.x, marker.y);
  ctx.strokeStyle = marker.color;
  ctx.fillStyle = marker.color;
  ctx.shadowBlur = 16;
  ctx.shadowColor = marker.color;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.arc(0, 0, marker.eventClass === "mac" ? 7 : 6, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(0, 0, 2.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawAircraftSymbol(ctx, marker) {
  ctx.save();
  ctx.translate(marker.x, marker.y);
  ctx.rotate(marker.angle || 0);
  ctx.strokeStyle = marker.color;
  ctx.fillStyle = marker.color;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowBlur = 5;
  ctx.shadowColor = marker.color;
  if (marker.vehicleType === "helicoptero") {
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.ellipse(0, 0, 5, 3, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(-4, 0); ctx.lineTo(-10, 0); ctx.lineTo(-12, -2);
    ctx.moveTo(0, -7); ctx.lineTo(0, 7);
    ctx.moveTo(-7, 0); ctx.lineTo(7, 0);
    ctx.stroke();
  } else {
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(7, 0); ctx.lineTo(-4, -3); ctx.lineTo(-7, 0); ctx.lineTo(-4, 3); ctx.closePath();
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(-2, -6); ctx.lineTo(-2, 6);
    ctx.moveTo(2, -6); ctx.lineTo(2, 6);
    ctx.stroke();
    for (const x of [-2, 2]) for (const y of [-6, 6]) {
      ctx.beginPath(); ctx.arc(x, y, 1.8, 0, Math.PI * 2); ctx.stroke();
    }
  }
  ctx.restore();
}

function draw3DLine(ctx, points, project, color, alpha, start, end) {
  if (end <= start) return;
  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.globalAlpha = alpha;
  ctx.lineWidth = alpha > 0.5 ? 1.8 : 0.7;
  for (let index = start; index <= end; index += 1) {
    const point = points[index];
    const projected = project(point[1], point[2], point[3]);
    if (index === start) ctx.moveTo(projected.x, projected.y); else ctx.lineTo(projected.x, projected.y);
  }
  ctx.stroke();
  ctx.globalAlpha = 1;
}

function draw3DGround(ctx, project, bounds, altitude, width, altitudeFt) {
  ctx.strokeStyle = "rgba(107, 145, 180, 0.22)";
  ctx.lineWidth = 1;
  const divisions = width < 700 ? 5 : 8;
  for (let index = 0; index <= divisions; index += 1) {
    const ratio = index / divisions;
    const lon = bounds.min_lon + (bounds.max_lon - bounds.min_lon) * ratio;
    const lat = bounds.min_lat + (bounds.max_lat - bounds.min_lat) * ratio;
    const a = project(lon, bounds.min_lat, altitude), b = project(lon, bounds.max_lat, altitude);
    const c = project(bounds.min_lon, lat, altitude), d = project(bounds.max_lon, lat, altitude);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(c.x, c.y); ctx.lineTo(d.x, d.y); ctx.stroke();
  }
  const label = project(bounds.min_lon, bounds.max_lat, altitude);
  ctx.fillStyle = "rgba(199, 215, 231, 0.82)";
  ctx.font = "12px Inter, sans-serif";
  ctx.fillText(`Plano-base ${Math.round(altitudeFt)} pés MSL`, label.x + 8, label.y - 8);
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
    days[0]?.rows?.[0]?.experiment_family === "produto2"
      ? `${formatNumber(model.runs.length)} simulacoes C1/C2 comparaveis. C1 e a referencia; cards, mapa e graficos mostram o cenario escolhido.`
      : `${formatNumber(model.runs.length)} simulacoes organizadas em ${formatNumber(days.length)} grupos; cards, mapa e graficos mostram a variante escolhida.`
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
        <tr class="${row.variant_key === "c1" ? "reference-row" : row.mvp_enabled ? "mvp-row" : ""}">
          <td title="${escapeHtml(row.name)}">${escapeHtml(row.variant_label)}</td>
          <td>${formatOptionalDuration(row.ground_delay_s)}</td>
          <td>${formatOptionalDuration(row.airborne_delay_s)}</td>
          <td>${formatOptionalDuration(row.total_delay_s)}</td>
          <td>${formatNumber(row.flight_time_min, 1)} min</td>
          <td>${formatSigned(row.flight_time_delta_vs_reference_min, 1, " min")}</td>
          <td>${formatNumber(row.distance_nm, 1)} NM</td>
          <td>${formatSigned(row.distance_delta_vs_reference_nm, 2, " NM")}</td>
          <td>${formatOptionalPercent(row.trajectory_conformity_pct)}</td>
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

  setText("metric-aircraft", formatNumber(summary.aircraft_count));
  setText("metric-records", `${formatNumber(summary.records)} registros`);
  setText("metric-peak", formatNumber(summary.peak_simultaneous_aircraft));
  setText("metric-duration", `${formatNumber(summary.duration_min, 1)} min`);
  setText("metric-flight-time", formatNumber(efficiency.mean_flight_time_min, 1));
  setText("metric-distance", formatNumber(efficiency.mean_distance_nm, 1));
  setText("metric-lowc", formatNumber(safety.lowc_events));
  setText("metric-lowc-threshold", `${formatNumber(safety.lowc_horizontal_m, 0)} m H / ${formatNumber(safety.lowc_vertical_m, 2)} m V`);
  setText("metric-nmac", formatNumber(safety.nmac_events));
  setText("metric-nmac-threshold", `${formatNumber(safety.nmac_horizontal_m, 0)} m H / ${formatNumber(safety.nmac_vertical_m, 2)} m V`);
  setText("metric-lowc-rate", formatNumber(safety.lowc_per_flight_hour, 2));
  setText("metric-mac-rate", formatNumber(safety.expected_mac_per_100k_flight_hours, 3));
  setText("kpa-route-efficiency", `${formatNumber(efficiency.mean_horizontal_inefficiency_pct, 1)}%`);
  setText(
    "kpa-conformity",
    efficiency.trajectory_conformity?.available
      ? `${formatNumber(efficiency.trajectory_conformity.mean_trajectory_conformity_ratio * 100, 1)}%`
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
      ? `${formatNumber(complexity.uam_corridor_count, 0)} corredores UAM planejados × ` +
          `${formatNumber(complexity.reh_segment_count, 0)} trechos REH formais, ` +
          `${formatNumber(complexity.planned_route_crossings, 0)} waypoints de cruzamento 2D, ` +
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
    ["planned_reh", "Trecho REH formal"],
    ["crossing_waypoints", "Waypoint UAM × REH"],
  ]) {
    const group = throughput[type];
    if (!group?.available) continue;
    for (const resource of group.top_resources || []) {
      rows.push({
        type: label,
        capacity: resource.capacity_declared_per_hour ?? group.capacity_declared_per_hour,
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
          <td title="${escapeHtml(row.resource_id)}">${row.map_target
            ? `<button class="resource-map-link" type="button" data-map-target="${escapeHtml(JSON.stringify(row.map_target))}">${escapeHtml(row.label)}</button>`
            : escapeHtml(row.label)}</td>
          <td>${formatNumber(row.operations, 0)}</td>
          <td>${formatNumber(row.peak_throughput_per_hour, 1)} ops/h</td>
          <td>${row.capacity == null ? "Não informada" : `${formatNumber(row.capacity, 1)} ops/h`}</td>
          <td>${row.utilization_peak == null ? "Indisponível" : formatPercentRatio(row.utilization_peak)}</td>
        </tr>`
        )
        .join("")
    : `<tr><td colspan="6">Sem recursos de capacidade calculados.</td></tr>`;
}

function showImageChart(imageId, src) {
  const image = document.getElementById(imageId);
  image.src = src;
}

function renderMapLayers(tracks, plannedRoutes, officialReh, conflicts, heatmap, capacity) {
  if (!state.map || typeof window.L === "undefined") return;
  state.lastTracks = tracks;
  state.lastConflicts = conflicts;
  state.lastOfficialReh = officialReh;
  state.lastCapacity = capacity;
  const visibleConflicts = filteredConflictCollection(conflicts);
  const visibleTracks = filterTracksByVolume(tracks, state.trajectoryVolumeFilter);
  clearLayer("tracksLayer");
  clearLayer("officialRehLayer");
  clearLayer("plannedLayer");
  clearLayer("heatLayer");
  clearLayer("atdHotspotLayer");
  clearLayer("complexityLayer");
  clearLayer("conflictLayer");
  clearLayer("resourceHighlightLayer");

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
              `Desvio medio do planejamento ${formatNumber(p.mean_deviation_m, 1)} m`
            : "")
      );
    },
  });

  state.tracksLayer = L.layerGroup([routeHalo, routeLines]);

  state.officialRehLayer = L.geoJSON(officialReh || emptyFeatureCollection(), {
    pane: "routePane",
    style: (feature) => ({
      className: "official-reh-feature",
      color: feature.properties.route_type === "Obrig" ? "#075985" : "#0f766e",
      fillColor: feature.properties.route_type === "Obrig" ? "#38bdf8" : "#5eead4",
      opacity: 0.82,
      fillOpacity: 0.12,
      weight: 1.5,
    }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties || {};
      layer.bindTooltip(`${escapeHtml(p.label)} - ${escapeHtml(p.route_type || "REH")}`, { sticky: true });
      layer.bindPopup(
        `<strong>${escapeHtml(p.label)}</strong><br>` +
          `Tipo ${escapeHtml(p.route_type || "nao informado")} / classe ${escapeHtml(p.airspace_class || "nao informada")}<br>` +
          `Semilargura ${formatNumber(p.semi_width_m, 0)} m` +
          (p.fix_a_name || p.fix_b_name
            ? `<br>${escapeHtml(p.fix_a_name || "-")} -> ${escapeHtml(p.fix_b_name || "-")}`
            : "") +
          (p.altitude_min_ft != null || p.altitude_max_ft != null
            ? `<br>Altitude ${formatNumber(p.altitude_min_ft, 0)}-${formatNumber(p.altitude_max_ft, 0)} ft`
            : p.altitude_compulsory_ft != null
              ? `<br>Altitude compulsoria ${formatNumber(p.altitude_compulsory_ft, 0)} ft`
              : "") +
          (p.source_identifier ? `<br>Fonte ${escapeHtml(p.source_identifier)}` : "")
      );
    },
  });

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
      const conformity = Number.isFinite(Number(p.planned_line_adherence_pct))
        ? `${formatNumber(p.planned_line_adherence_pct, 1)}% das amostras dentro de ${formatNumber(plannedRoutes.properties.conformity_tolerance_m, 0)} m da linha planejada`
        : "Sem trajetoria executada associada";
      layer.bindTooltip(`Planejamento ${escapeHtml(p.flight_instance)}`, { sticky: true });
      layer.bindPopup(
        `<strong>Planejamento do cenario</strong><br>` +
          `${escapeHtml(p.flight_instance)} / ${formatNumber(p.waypoint_count)} waypoints<br>` +
          `${conformity}<br>` +
          (Number.isFinite(Number(p.mean_deviation_m))
            ? `Desvio medio ${formatNumber(p.mean_deviation_m, 1)} m<br>P95 ${formatNumber(p.p95_deviation_m, 1)} m`
            : "")
      );
    },
  });

  const conflictMarkers = L.geoJSON(visibleConflicts, {
    pane: "conflictPane",
    pointToLayer: (feature, latlng) =>
      L.circleMarker(latlng, {
        radius: 11,
        color: conflictEventColor(feature),
        weight: 3,
        fillColor: conflictEventColor(feature),
        fillOpacity: 0.94,
      }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindTooltip(`${conflictEventLabel(feature)} ${escapeHtml(p.id_a)} / ${escapeHtml(p.id_b)}`, {
        sticky: true,
      });
      layer.bindPopup(
        `<strong>Evento ${conflictEventLabel(feature)}</strong><br>` +
          `${escapeHtml(p.id_a)} / ${escapeHtml(p.id_b)}<br>` +
          `${formatNumber(p.dist_h_m, 1)} m horizontal / ${formatNumber(p.dist_v_m, 1)} m vertical<br>` +
          `${escapeHtml(p.vehicle_pair || "tipos desconhecidos")}<br>` +
          `Severidade ${formatNumber(p.severity_ratio, 2)}<br>` +
          `Razao H ${formatNumber(p.horizontal_ratio, 3)} / V ${formatNumber(p.vertical_ratio, 3)}<br>` +
          `Duracao ${formatNumber(p.duration_s, 0)} s<br>` +
          `t = ${formatNumber(p.simt, 0)} s`
      );
    },
  });

  const conflictPulse = L.geoJSON(visibleConflicts, {
    interactive: false,
    pane: "conflictPane",
    pointToLayer: (feature, latlng) =>
      L.circleMarker(latlng, {
        radius: 22,
        color: conflictEventColor(feature),
        weight: 2,
        fillColor: conflictEventColor(feature),
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

  state.atdHotspotLayer = L.geoJSON(capacity?.density?.hotspots || emptyFeatureCollection(), {
    pane: "heatPane",
    style: (feature) => {
      const ratio = Math.max(0, Math.min(1, Number(feature.properties.density_ratio) || 0));
      return {
        color: "#b91c1c",
        fillColor: colorForHotspot(ratio),
        fillOpacity: 0.12 + ratio * 0.28,
        opacity: 0.45 + ratio * 0.35,
        weight: 1.2 + ratio * 1.5,
      };
    },
    onEachFeature: (feature, layer) => {
      const p = feature.properties || {};
      layer.bindTooltip(`Hotspot ATD ${escapeHtml(p.label)} - ${formatNumber(p.air_traffic_density_per_km2, 3)} aeronaves/km2`, {
        sticky: true,
      });
      layer.bindPopup(
        `<strong>Hotspot ATD ${escapeHtml(p.label)}</strong><br>` +
          `${formatNumber(p.air_traffic_density_per_km2, 3)} aeronaves/km2<br>` +
          `Media simultanea ${formatNumber(p.mean_simultaneous_aircraft, 2)}<br>` +
          `Pico simultaneo ${formatNumber(p.peak_simultaneous_aircraft, 0)}<br>` +
          `Area ${formatNumber(p.corridor_area_km2, 2)} km2`
      );
    },
  });

  state.complexityLayer = L.geoJSON(capacity?.complexity?.crossings || emptyFeatureCollection(), {
    pane: "conflictPane",
    pointToLayer: (_feature, latlng) =>
      L.circleMarker(latlng, {
        radius: 7,
        color: "#581c87",
        weight: 2,
        fillColor: "#a855f7",
        fillOpacity: 0.88,
      }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties || {};
      layer.bindTooltip(`${escapeHtml(p.label || "Cruzamento UAM × REH")} · capacidade não informada`, {
        sticky: true,
      });
      layer.bindPopup(
        `<strong>${escapeHtml(p.label || "Cruzamento UAM × REH")}</strong><br>` +
          `Corredor UAM: ${escapeHtml((p.uam_route_labels || []).join(", "))}<br>` +
          `REH: ${escapeHtml((p.reh_labels || []).join(", "))}<br>` +
          `${formatNumber(p.operations, 0)} passagens dentro de ${formatNumber(p.capture_radius_m, 0)} m<br>` +
          `Capacidade declarada não informada · pico ${formatNumber(p.peak_throughput_per_hour, 1)} ops/h<br>` +
          `Utilizacao de pico ${formatPercentRatio(p.utilization_peak)}<br>` +
          `Intersecao horizontal 2D; envelope vertical nao disponivel.`
      );
    },
  });

  applyCheckedLayer("layer-heat", state.heatLayer);
  applyCheckedLayer("layer-official-reh", state.officialRehLayer);
  applyCheckedLayer("layer-atd-hotspots", state.atdHotspotLayer);
  applyCheckedLayer("layer-complexity", state.complexityLayer);
  applyCheckedLayer("layer-tracks", state.tracksLayer);
  applyCheckedLayer("layer-planned", state.plannedLayer);
  applyCheckedLayer("layer-conflicts", state.conflictLayer);

  fitMapToOperationalArea(visibleTracks, visibleConflicts);
  updateMapInfo(tracks, visibleTracks, plannedRoutes, officialReh, visibleConflicts, heatmap, capacity);
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
  if (!state.map || typeof window.L === "undefined") return;
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

function updateMapInfo(tracks, visibleTracks, plannedRoutes, officialReh, conflicts, heatmap, capacity) {
  const trajectories = tracks.features?.length || 0;
  const visible = visibleTracks.features?.length || 0;
  const groups = tracks.properties?.trajectory_group_count || new Set(
    (tracks.features || []).map((feature) => feature.properties.trajectory_group)
  ).size;
  const conflictFeatures = conflicts.features || [];
  const lowc = conflictFeatures.filter((feature) => conflictEventClass(feature) === "lowc").length;
  const nmac = conflictFeatures.filter((feature) => conflictEventClass(feature) === "nmac").length;
  const mac = conflictFeatures.filter((feature) => conflictEventClass(feature) === "mac").length;
  const planned = plannedRoutes?.features?.length || 0;
  const officialSegments = officialReh?.features?.length || 0;
  const density = heatmap.length || 0;
  const atdHotspots = capacity?.density?.hotspots?.features?.length || 0;
  const crossings = capacity?.complexity?.crossings?.features?.length || 0;
  setText("map-info-title", "Mapa operacional");
  setText(
    "map-info-text",
    `${formatNumber(visible)} de ${formatNumber(trajectories)} trajetorias executadas visiveis, ${formatNumber(officialSegments)} trechos REH oficiais e ${formatNumber(planned)} planejamentos de voo; ${formatNumber(density)} pontos de densidade, ${formatNumber(atdHotspots)} corredores ATD, ${formatNumber(crossings)} waypoints UAM × REH, ${formatNumber(lowc)} LoWC fora de NMAC, ${formatNumber(nmac)} NMAC e ${formatNumber(mac)} MAC observados.`
  );
}

function highlightMapResource(target) {
  if (!state.map || typeof window.L === "undefined" || !target) return;
  activateKpa("overview");
  clearLayer("resourceHighlightLayer");
  let geojson = emptyFeatureCollection();
  if (target.type === "od_pair" && target.coordinates?.length === 2) {
    geojson = {
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: target.coordinates } }],
    };
  } else if (target.type === "trajectory_group") {
    geojson = {
      ...(state.lastTracks || emptyFeatureCollection()),
      features: (state.lastTracks?.features || []).filter(
        (feature) => feature.properties?.trajectory_group === target.resource_id
      ),
    };
  } else if (target.type === "reh_segment") {
    geojson = {
      ...(state.lastOfficialReh || emptyFeatureCollection()),
      features: (state.lastOfficialReh?.features || []).filter(
        (feature) => feature.properties?.resource_id === target.resource_id
      ),
    };
  } else if (target.type === "crossing_waypoint") {
    const matchingFeatures = (state.lastCapacity?.complexity?.crossings?.features || []).filter(
      (feature) => feature.properties?.resource_id === target.resource_id
    );
    geojson = {
      type: "FeatureCollection",
      features: matchingFeatures.length
        ? matchingFeatures
        : target.coordinates?.length === 2
          ? [{ type: "Feature", properties: { resource_id: target.resource_id }, geometry: { type: "Point", coordinates: target.coordinates } }]
          : [],
    };
  }
  state.resourceHighlightLayer = L.geoJSON(geojson, {
    pane: "conflictPane",
    style: { color: "#db2777", fillColor: "#f472b6", fillOpacity: 0.34, weight: 7, opacity: 1 },
    pointToLayer: (_feature, latlng) => L.circleMarker(latlng, {
      pane: "conflictPane", radius: 13, color: "#831843", fillColor: "#f472b6", weight: 4, fillOpacity: 0.92,
    }),
  }).addTo(state.map);
  const bounds = state.resourceHighlightLayer.getBounds();
  if (bounds.isValid()) state.map.fitBounds(bounds.pad(0.35), { maxZoom: 15 });
  document.querySelector(".workspace")?.scrollIntoView({ behavior: "smooth", block: "center" });
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
  if (layer && state.map && state.map.hasLayer(layer)) {
    state.map.removeLayer(layer);
  }
  state[layerName] = null;
}

function applyCheckedLayer(controlId, layer) {
  if (state.map && document.getElementById(controlId).checked && layer) {
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
          <td colspan="8">${escapeHtml(group.label)}</td>
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
          <td>${escapeHtml(metric.data_required)}</td>
          <td>${escapeHtml(metric.implemented)}</td>
          <td>${escapeHtml(metric.improvements_needed)}</td>
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
  if (metric.availability === "indisponivel") return "Indisponiveis";
  if (id.includes("lowc") || id.includes("nmac") || id.includes("severity") || id.includes("mac") || id.includes("risk") || id.includes("tls") || id.includes("conflict")) {
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

function colorForHotspot(densityRatio) {
  const ratio = Math.max(0, Math.min(1, Number(densityRatio) || 0));
  if (ratio >= 0.75) return "#dc2626";
  if (ratio >= 0.45) return "#f97316";
  if (ratio >= 0.2) return "#facc15";
  return "#14b8a6";
}

function emptyFeatureCollection() {
  return { type: "FeatureCollection", features: [] };
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
