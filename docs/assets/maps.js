// Spatial views restored from the previous dashboard; KPIs remain in their own tabs.
Object.assign(state, {
  map: null,
  tracksLayer: null,
  officialRehLayer: null,
  uamProjectionLayer: null,
  uamJunctionLayer: null,
  uamCenterlines: {type: "FeatureCollection", features: []},
  uamJunctions: window.__UAM_GEOMETRIC_JUNCTIONS__ || { type: "FeatureCollection", features: [] },
  plannedLayer: null,
  heatLayer: null,
  atdHotspotLayer: null,
  complexityLayer: null,
  candidateNodeLayer: null,
  conflictLayer: null,
  resourceHighlightLayer: null,
  baseLayers: {},
  overlayLayers: {},
  lastTracks: null,
  lastConflicts: null,
  lastOfficialReh: null,
  lastCapacity: null,
  candidateNodes: window.__UAM_CANDIDATE_NODES__ || { type: "FeatureCollection", features: [] },
  waypointRankings: window.__UAM_WAYPOINT_RANKINGS__ || [],
  uamProjection: window.__UAM_CORRIDOR_PROJECTION__ || { type: "FeatureCollection", features: [] },
  crossingCandidates: window.__UAM_CROSSINGS_3D__ || { type: "FeatureCollection", features: [] },
  conflictPairFilter: "all"
});
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

  const openStreetMap = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxNativeZoom: 19,
    maxZoom: 20,
    updateWhenIdle: true,
    keepBuffer: 4,
  }).addTo(state.map);

  state.baseLayers = {
    "OpenStreetMap": openStreetMap,
  };
}


function toggleLayer(layerName, event) {
  const layer = state[layerName];
  if (!layer || !state.map) {
    updateMapLegend();
    return;
  }
  if (event.target.checked) {
    layer.addTo(state.map);
  } else {
    state.map.removeLayer(layer);
  }
  updateMapLegend();
}


function bind3DControls() {
  const canvas = document.getElementById("viewer3d-canvas");
  if (!canvas) return;
  const play = document.getElementById("viewer3d-play");
  const timeline = document.getElementById("viewer3d-time");
  play.addEventListener("click", () => {
    if (!viewer3d.data) return;
    if (viewer3d.currentTime >= viewer3d.data.sim_end_s) viewer3d.currentTime = viewer3d.data.sim_start_s;
    if (viewer3d.animationFrame !== null) cancelAnimationFrame(viewer3d.animationFrame);
    viewer3d.animationFrame = null;
    viewer3d.playing = !viewer3d.playing;
    viewer3d.lastFrame = null;
    update3DControls();
    if (viewer3d.playing) viewer3d.animationFrame = requestAnimationFrame(animate3D);
  });
  timeline.addEventListener("input", (event) => {
    if (viewer3d.animationFrame !== null) cancelAnimationFrame(viewer3d.animationFrame);
    viewer3d.animationFrame = null;
    viewer3d.lastFrame = null;
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
  if (viewer3d.animationFrame !== null) cancelAnimationFrame(viewer3d.animationFrame);
  viewer3d.animationFrame = null;
  viewer3d.currentTime = 0;
  viewer3d.dragging = false;
  viewer3d.playing = false;
  viewer3d.lastFrame = null;
  viewer3d.data = data?.tracks?.length ? data : null;
  viewer3d.conflicts = conflicts?.features || [];
  viewer3d.macTimestampAvailable = Boolean(conflicts?.properties?.mac_timestamp_available);
  if (!data?.tracks?.length) {
    setText("viewer3d-status", "Sem trajetórias 3D para este cenário.");
    setText("viewer3d-note", "Dados 3D indisponíveis para esta réplica.");
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
  if (aligned > viewer3d.currentTime) {
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
      draw3D();
      const run = state.runs[state.activeRunIndex] || state.runs[0];
      if (run && state.map) {
        renderMapLayers(run.tracks, run.planned_routes, run.official_reh, run.conflicts, run.heatmap, run.dashboard.capacity);
      }
    });
  });
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


function waypointMetric(feature) {
  const scenario = (state.runs[state.activeRunIndex] || state.runs[0])?.metadata?.scenario_key;
  return state.waypointRankings.find(row => row.scenario === scenario && row.waypoint_id === feature.properties.resource_id && row.source_sha256 === feature.properties.source?.sha256 && row.analysis_method_version === feature.properties.analysis_method_version);
}


function waypointAltitude(p) {
  return p.vertical_intervals_m?.length
    ? p.vertical_intervals_m.map(([lo, hi]) => `${formatNumber(lo, 1)}–${formatNumber(hi, 1)} m MSL`).join("; ")
    : "Altitude desconhecida/inválida: sem contagem 3D";
}


function waypointTooltip(feature) {
  const p = feature.properties, [lon, lat] = feature.geometry.coordinates, metric = waypointMetric(feature);
  return `${escapeHtml(p.label)} · ${p.network} · ${formatNumber(lat, 6)}, ${formatNumber(lon, 6)}<br>` +
    `${waypointAltitude(p)}<br>P95: ${metric?.p95_throughput_per_hour == null ? "indisponível" : `${formatNumber(metric.p95_throughput_per_hour, 2)} ops/h`} · ${p.name_position_count} posições deste nome`;
}


function waypointSelectionDetails(p) {
  if (p.network === "REH") return `Junção REH: ${p.network_degree} arestas distintas, conforme o critério original.<br>`;
  const ref = p.reh_reference;
  if (!ref) return "Referência REH indisponível.<br>";
  const target = { type: "candidate_node", resource_id: ref.resource_id };
  const referenceLabel = (state.candidateNodes.features || []).some(f => f.properties.resource_id === ref.resource_id)
    ? `<button class="resource-map-link" data-map-target="${escapeHtml(JSON.stringify(target))}">${escapeHtml(ref.label)}</button>`
    : `${escapeHtml(ref.label)} (fixo de referência fora da seleção de junções REH)`;
  return `Junção UAM: ${p.network_degree} arestas físicas distintas; ${p.interior_route_ids.length} rotas com uso não terminal.<br>` +
    `Referência REH: ${referenceLabel}` +
    ` · ${formatNumber(ref.horizontal_distance_m, 1)} m · ${ref.match_method === "documented_alias" ? "alias documentado" : "nome normalizado equivalente"}. Vínculo de referência, sem fusão de recursos.<br>`;
}


function waypointDetails(feature) {
  const p = feature.properties, metric = waypointMetric(feature);
  const positions = (state.candidateNodes.features || []).filter(f => f.properties.name_group_id === p.name_group_id ||
    JSON.stringify(f.geometry.coordinates) === JSON.stringify(feature.geometry.coordinates));
  const links = positions.map(f => {
    const q = f.properties, [lon, lat] = f.geometry.coordinates;
    const target = { type: "candidate_node", resource_id: q.resource_id };
    return `<li><button class="resource-map-link" data-map-target="${escapeHtml(JSON.stringify(target))}">${escapeHtml(q.label)} · ${formatNumber(lat, 6)}, ${formatNumber(lon, 6)} · ${waypointAltitude(q)}</button><br><small>${escapeHtml(q.resource_id)}</small></li>`;
  }).join("");
  return `<strong>${waypointTooltip(feature)}</strong><br>ID: ${escapeHtml(p.resource_id)}<br>` +
    `Nomes originais: ${escapeHtml(p.original_names.join(", "))} · normalizado: ${escapeHtml(p.normalized_name)}<br>` +
    waypointSelectionDetails(p) +
    `THR médio: ${metric?.mean_throughput_per_hour == null ? "indisponível" : formatNumber(metric.mean_throughput_per_hour, 2) + " ops/h"}<br>` +
    `Fonte: ${escapeHtml(p.source?.file || "indisponível")}<br><small>SHA256: ${escapeHtml(p.source?.sha256 || "—")}</small><br>` +
    `Rotas/trechos: ${escapeHtml([...p.uam_route_labels, ...p.reh_labels].join(", "))}<br>` +
    `${p.name_position_count} posições elegíveis de ${p.name_all_position_count || p.name_position_count} posições nomeadas indexadas por rede. Coordenadas, níveis e dimensões permanecem separados; nenhuma soma de P95. Marcadores não são deslocados. Posições no mesmo local 2D também estão abaixo.<ul>${links}</ul>`;
}


function renderMapLayers(tracks, plannedRoutes, officialReh, conflicts, heatmap, capacity) {
  if (!state.map || typeof window.L === "undefined") return;
  state.lastTracks = tracks;
  state.lastConflicts = conflicts;
  state.lastOfficialReh = officialReh;
  state.lastCapacity = capacity;
  const visibleConflicts = filteredConflictCollection(conflicts);
  const visibleTracks = emptyFeatureCollection();
  clearLayer("tracksLayer");
  clearLayer("officialRehLayer");
  clearLayer("uamProjectionLayer");
  clearLayer("uamJunctionLayer");
  clearLayer("plannedLayer");
  clearLayer("heatLayer");
  clearLayer("atdHotspotLayer");
  clearLayer("complexityLayer");
  clearLayer("candidateNodeLayer");
  clearLayer("conflictLayer");
  clearLayer("resourceHighlightLayer");

  // Executed and planned paths are intentionally excluded from map rendering.
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

  const uamArea = L.geoJSON(state.uamProjection, {
    pane: "routePane",
    style: () => ({
      color: "#be185d",
      fillColor: "#f472b6",
      opacity: 0.9,
      fillOpacity: 0.13,
      weight: 1.7,
      // Dissolved area: no repeated OD boundaries.
    }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties || {};
      layer.bindTooltip(`${escapeHtml(p.label || "Corredor UAM")} · projeção 2D`, { sticky: true });
      layer.bindPopup(
        `<strong>${escapeHtml(p.label || "Corredor UAM")}</strong><br>` +
        `Projeção horizontal do corredor 3D<br>` +
        `Área consolidada de ${formatNumber(p.source_route_count || 0)} rotas; a projeção não implica conexão entre altitudes.<br>` +
        `Altitude do eixo ${formatNumber(p.altitude_min_m, 0)}–${formatNumber(p.altitude_max_m, 0)} m MSL`
      );
    },
  });

  const uamAxes = L.geoJSON(state.uamCenterlines, {
    pane: "routePane", interactive: false,
    style: {color: "#9d174d", weight: 1, opacity: .45},
  });
  state.uamProjectionLayer = L.layerGroup([uamArea, uamAxes]);

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
          fillOpacity: Math.max(0.08, point[2]),
          fillColor: "#2563eb",
        })
      )
    );
  }

  state.complexityLayer = L.geoJSON(crossingCollection(capacity), {
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
      layer.bindTooltip(`${escapeHtml(p.label || "Cruzamento UAM × REH")} · ${formatNumber(p.altitude_m, 0)} m MSL`, {
        sticky: true,
      });
      layer.bindPopup(
        `<strong>${escapeHtml(p.label || "Cruzamento UAM × REH")}</strong><br>` +
          `Corredor UAM: ${escapeHtml((p.uam_route_labels || []).join(", "))}<br>` +
          `REH: ${escapeHtml((p.reh_labels || []).join(", "))}<br>` +
          `Altitude de interseção: ${formatNumber(p.altitude_m, 1)} m MSL<br>` +
          `Diagnóstico geométrico separado; não é recurso de capacidade neste modo.`
      );
    },
  });

  state.candidateNodeLayer = L.geoJSON(state.candidateNodes, {
    pane: "conflictPane",
    pointToLayer: (feature, latlng) => {
      const reh = feature.properties?.criterion === "reh_named_waypoint";
      return L.circleMarker(latlng, {
        radius: 6, color: reh ? "#92400e" : "#0e7490", weight: 2,
        fillColor: reh ? "#f59e0b" : "#22d3ee", fillOpacity: 0.9,
      });
    },
    onEachFeature: (feature, layer) => {
      layer.bindTooltip(waypointTooltip(feature), { sticky: true });
      layer.bindPopup(waypointDetails(feature), { maxWidth: 520, maxHeight: 360 });
    }
  });

  state.uamJunctionLayer = L.geoJSON(state.uamJunctions, {
    pane: "conflictPane",
    pointToLayer: (_feature, latlng) => L.circleMarker(latlng, {
      radius: 4, color: "#075985", fillColor: "#67e8f9", fillOpacity: .9, weight: 1.5,
    }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindTooltip(`${escapeHtml(p.label)} · grau ${p.network_degree} · ${formatNumber(p.altitude_m, 1)} m MSL`, {sticky: true});
      layer.bindPopup(`<strong>${escapeHtml(p.label)}</strong><br>Grau ${p.network_degree} · ${formatNumber(p.altitude_m, 1)} m MSL<br>Junção dos eixos 3D. Diagnóstico geométrico; não define capacidade.<br>${(p.route_labels || []).map(escapeHtml).join("<br>")}`, {maxHeight: 240});
    },
  });
  applyCheckedLayer("layer-uam-junctions", state.uamJunctionLayer);
  applyCheckedLayer("layer-heat", state.heatLayer);
  applyCheckedLayer("layer-official-reh", state.officialRehLayer);
  applyCheckedLayer("layer-uam-corridors", state.uamProjectionLayer);
  applyCheckedLayer("layer-complexity", state.complexityLayer);
  applyCheckedLayer("layer-candidate-nodes", state.candidateNodeLayer);
  applyCheckedLayer("layer-conflicts", state.conflictLayer);

  fitMapToOperationalArea(visibleTracks, visibleConflicts);
  updateMapInfo(tracks, visibleTracks, plannedRoutes, officialReh, visibleConflicts, heatmap, capacity);
}


function fitMapToOperationalArea(tracks, conflicts) {
  if (!state.map || typeof window.L === "undefined") return;
  if (!tracks || !conflicts) {
    state.map.invalidateSize(true);
    state.map.setView([-23.5505, -46.6333], 10);
    return;
  }

  const bounds = L.latLngBounds([]);
  const run = state.runs[state.activeRunIndex];
  for (const [lat, lon] of run?.heatmap || []) bounds.extend([lat, lon]);
  const operationalBounds = run?.dashboard?.summary?.bounds;
  if (operationalBounds) {
    bounds.extend([operationalBounds.min_lat, operationalBounds.min_lon]);
    bounds.extend([operationalBounds.max_lat, operationalBounds.max_lon]);
  }
  for (const feature of conflicts.features || []) {
    const coordinate = feature.geometry?.coordinates;
    if (coordinate) bounds.extend([coordinate[1], coordinate[0]]);
  }
  if (document.getElementById("layer-uam-corridors")?.checked) {
    for (const feature of state.uamProjection.features || []) {
      for (const ring of feature.geometry?.coordinates || []) {
        for (const [lon, lat] of ring) bounds.extend([lat, lon]);
      }
    }
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


function updateMapLegend() {
  const volume = document.getElementById("trajectory-volume-filter")?.value || "all";
  const classes = new Set((state.lastConflicts?.features || []).map(conflictEventClass));
  let visible = 0;
  document.querySelectorAll(".map-legend [data-legend-layer]").forEach((item) => {
    const layer = item.dataset.legendLayer;
    const control = document.getElementById(`layer-${layer}`);
    const checked = Boolean(control?.checked && !control.disabled);
    const showVolume = !item.dataset.volume || volume === "all" || item.dataset.volume === volume;
    const showConflict = !item.dataset.conflict || classes.has(item.dataset.conflict);
    item.hidden = !(checked && showVolume && showConflict);
    if (!item.hidden) visible += 1;
  });
  const panel = document.querySelector(".map-info");
  if (panel) panel.hidden = visible === 0;
}


function crossingCollection(capacity) {
  return capacity?.complexity?.geometry_dimension === "3D"
    ? capacity.complexity.crossings || emptyFeatureCollection()
    : emptyFeatureCollection();
}


function highlightMapResource(target) {
  if (!state.map || typeof window.L === "undefined" || !target) return;
  if (["trajectory_group", "od_pair"].includes(target.type)) return;
  activateKpa("maps");
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
    const matchingFeatures = (crossingCollection(state.lastCapacity).features || []).filter(
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
  } else if (target.type === "candidate_node") {
    geojson = {
      type: "FeatureCollection",
      features: (state.candidateNodes.features || []).filter(
        (feature) => feature.properties?.resource_id === target.resource_id
      ),
    };
  }
  state.resourceHighlightLayer = L.geoJSON(geojson, {
    pane: "conflictPane",
    style: { color: "#db2777", fillColor: "#f472b6", fillOpacity: 0.34, weight: 7, opacity: 1 },
    pointToLayer: (_feature, latlng) => L.circleMarker(latlng, {
      pane: "conflictPane", radius: 13, color: "#831843", fillColor: "#f472b6", weight: 4, fillOpacity: 0.92,
    }),
    onEachFeature: (feature, layer) => {
      if (feature.properties?.name_group_id) layer.bindPopup(waypointDetails(feature), { maxWidth: 520, maxHeight: 360 });
    },
  }).addTo(state.map);
  const bounds = state.resourceHighlightLayer.getBounds();
  if (bounds.isValid()) state.map.fitBounds(bounds.pad(0.35), { maxZoom: 15, animate: false });
  state.resourceHighlightLayer.eachLayer(layer => { if (layer.getPopup()) layer.openPopup(); });
  document.querySelector("#map")?.scrollIntoView({ behavior: "smooth", block: "center" });
}


function clearLayer(layerName) {
  const layer = state[layerName];
  if (layer && state.map && state.map.hasLayer(layer)) {
    state.map.removeLayer(layer);
  }
  state[layerName] = null;
}


function applyCheckedLayer(controlId, layer) {
  if (state.map && document.getElementById(controlId)?.checked && !document.getElementById(controlId)?.disabled && layer) {
    layer.addTo(state.map);
  }
}


function emptyFeatureCollection() {
  return { type: "FeatureCollection", features: [] };
}


function updateMapInfo() {
  setText("map-info-title", "Mapa operacional");
  setText("map-info-text", "Ative as camadas e clique nos eventos ou nós para inspecionar sua localização.");
  updateMapLegend();
}

function initMaps() {
  bind3DControls();
  bindConflictPairControls();
  for (const [id, layer] of [
    ["official-reh", "officialRehLayer"], ["uam-corridors", "uamProjectionLayer"],
    ["uam-junctions", "uamJunctionLayer"], ["heat", "heatLayer"],
    ["complexity", "complexityLayer"], ["candidate-nodes", "candidateNodeLayer"],
    ["conflicts", "conflictLayer"]
  ]) document.getElementById(`layer-${id}`).addEventListener("change", event => toggleLayer(layer, event));
  document.getElementById("fit-map").addEventListener("click", () => fitMapToOperationalArea(state.lastTracks, state.lastConflicts));
  document.addEventListener("click", event => {
    const button = event.target.closest("[data-map-target]");
    if (button) highlightMapResource(JSON.parse(button.dataset.mapTarget));
  });
  if (typeof window.L !== "undefined") initMap();
  else showMapUnavailable();
}

function updateMapsVisibility() {
  if (state.activeKpa === "maps") {
    requestAnimationFrame(() => {
      if (state.activeKpa !== "maps") return;
      state.map?.invalidateSize(true);
      const run = state.mapRun;
      if (state.mapNeedsRender && run) {
        renderMapLayers(run.tracks || emptyFeatureCollection(), run.planned_routes || emptyFeatureCollection(), run.official_reh || emptyFeatureCollection(), run.conflicts || emptyFeatureCollection(), run.heatmap || [], run.dashboard.capacity);
        state.mapNeedsRender = false;
      }
      draw3D();
    });
  } else {
    if (viewer3d.animationFrame !== null) cancelAnimationFrame(viewer3d.animationFrame);
    viewer3d.animationFrame = null;
    viewer3d.playing = false;
    viewer3d.lastFrame = null;
    update3DControls();
  }
}

function renderMaps(run) {
  const dedicated = (runDimensions(run)?.airspace || run.metadata?.airspace) === "dedicated_uam" || /^C2(?:\.|$)/.test(run.metadata?.scenario_key || "");
  for (const id of ["layer-uam-corridors", "layer-uam-junctions", "layer-complexity"]) {
    const control = document.getElementById(id);
    control.disabled = !dedicated;
    control.title = dedicated ? "" : "Este cenário utiliza a rede REH compartilhada.";
  }
  state.uamProjection = run.uam_projection || emptyFeatureCollection();
  state.uamJunctions = run.uam_junctions || emptyFeatureCollection();
  state.uamCenterlines = run.uam_centerlines || emptyFeatureCollection();
  state.candidateNodes = run.candidate_nodes || window.__UAM_CANDIDATE_NODES__ || emptyFeatureCollection();
  if (run.metadata?.scenario_key === "C0") {
    state.uamProjection = emptyFeatureCollection();
    state.uamJunctions = emptyFeatureCollection();
    state.uamCenterlines = emptyFeatureCollection();
    state.candidateNodes = {...state.candidateNodes, features: state.candidateNodes.features.filter(feature => feature.properties?.network === "REH")};
    state.conflictPairFilter = "all";
  }
  document.querySelectorAll("[data-conflict-pair]").forEach(button => {
    button.disabled = run.metadata?.scenario_key === "C0" && button.dataset.conflictPair.includes("evtol");
    const active = button.dataset.conflictPair === state.conflictPairFilter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  const replica = run.metadata?.replica;
  setText("map-replica-note", `A camada de densidade reúne as ${run.replica_count || 1} réplicas do cenário. Os eventos e a reprodução 3D usam uma réplica ilustrativa${replica == null ? "" : ` (r${String(replica).padStart(3, "0")})`}.`);
  state.mapRun = run;
  state.mapNeedsRender = true;
  render3DVisualization(run.trajectory_3d, run.conflicts);
  updateMapsVisibility();
}
