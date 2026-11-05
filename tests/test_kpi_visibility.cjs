const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({window: {}, document: {addEventListener() {}}, console});
vm.runInContext(fs.readFileSync('web/assets/metric_catalog.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('web/assets/dashboard.js', 'utf8'), context);
vm.runInContext(`
  const sample = {values: [1, null, 3], trace: [], valid_count: 2, total_count: 3};
  const run = {stability: {panels: {
    overview: {'safety.lowc_events': sample, 'safety.nmac_events': sample, 'summary.records': sample},
    safety: {'safety.min_severity_ratio': sample, 'safety.tls_margin': sample, 'safety.total_time_below_threshold_s': sample},
    capacity: {'planned_reh · R1 · Pico (ops/h)': sample, 'planned_reh · R1 · Operações': sample,
      'planned_reh · R1 · Referência P95 (ops/h)': sample, 'planned_reh · R1 · Utilização (razão)': sample}
  }}};
`, context);
const evaluate = source => vm.runInContext(source, context);
assert.equal(evaluate('publicCatalog("safety").length'), 6);
assert.equal(evaluate('publicCatalog("efficiency").length'), 7);
assert.equal(evaluate('publicCatalog("predictability").length'), 3);
assert.equal(evaluate('publicCatalog("equity").length'), 3);
assert.equal(evaluate('publicStabilityEntries(run, {id:"loss_of_separation",name:"LoWC"}).length'), 1);
for (const id of ['tls', 'severity_exposure', 'spatial_diagnostics']) {
  assert.equal(evaluate(`publicStabilityEntries(run, {id:"${id}"}).length`), 0);
}
for (const id of ['throughput', 'practical_capacity', 'utilization']) {
  assert.equal(evaluate(`publicStabilityEntries(run, {id:"${id}", name:"KPI"}).length`), 1);
  assert.ok(!evaluate(`publicStabilityEntries(run, {id:"${id}", name:"KPI"})[0][0]`).includes('Operações'));
}
assert.equal(evaluate('numericValue({efficiency:{total_flight_hours:0}, safety:{expected_mac_per_100k_flight_hours:0}}, "safety.expected_mac_per_100k_flight_hours")'), null);
assert.equal(evaluate('valueAt({available:false, mean:0}, "mean")'), null);
assert.equal(evaluate('valueAt({mean:0}, "mean")'), 0);
assert.equal((evaluate('replicaSvg([1,null,3], "KPI")').match(/<circle /g) || []).length, 2);
assert.ok(!evaluate('replicaSvg([1,null,3], "KPI")').includes('polyline'));
assert.equal(evaluate('normalizeModel({runs:[]}).runs.length'), 0);
console.log('KPI visibility checks passed: formal catalog, legacy series routing, diagnostic exclusion and missing values.');

assert.ok(evaluate('scenarioFilters.find(filter => filter.key === "vertiports").options.some(([value]) => value === "0")'));
// C0 must never display UAM geometry or UAM nodes, including global fallbacks.
vm.runInContext(fs.readFileSync('web/assets/maps.js', 'utf8'), context);
vm.runInContext(`
  const controls = {};
  document.getElementById = id => controls[id] ||= {};
  document.querySelectorAll = () => [];
  render3DVisualization = () => {};
  updateMapsVisibility = () => {};
  setText = () => {};
  const feature = network => ({properties: {network}});
  renderMaps({metadata: {scenario_key: "C0"}, dashboard: {},
    uam_projection: {features: [feature("UAM")]},
    uam_junctions: {features: [feature("UAM")]},
    candidate_nodes: {features: [feature("UAM"), feature("REH")]}});
`, context);
assert.equal(evaluate('state.candidateNodes.features.length'), 1);
assert.equal(evaluate('state.candidateNodes.features[0].properties.network'), 'REH');
assert.equal(evaluate('state.uamProjection.features.length'), 0);
assert.equal(evaluate('controls["layer-uam-corridors"].disabled'), true);
