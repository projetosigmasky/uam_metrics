// DOM/Leaflet contract checks without external services or browser packages.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'web/index.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'web/assets/dashboard.js'), 'utf8');
const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
const actual = {};
vm.runInNewContext(fs.readFileSync(path.join(root, 'docs/assets/data_bundle.js'), 'utf8'), {window: actual});

function context(model) {
  const elements = new Map([...ids].map(id => [id, {
    innerHTML: '', textContent: '', hidden: false, value: '', checked: html.includes(`id="${id}" checked`),
    setAttribute() {}, addEventListener() {}, querySelectorAll() {return [];}, scrollIntoView() {},
    classList: {toggle() {}, add() {}, remove() {}}, closest() {return {hidden:false};},
  }]));
  const seen = [];
  const layer = () => ({addTo() {return this;}, addLayer() {}, bindTooltip() {}, bindPopup() {}});
  const document = {
    addEventListener() {}, getElementById(id) {return elements.get(id) || null;},
    querySelectorAll() {return [];}, querySelector() {return {hidden:false};},
  };
  const L = {geoJSON(data) {seen.push(data);return layer();}, layerGroup: layer, heatLayer: layer,
    circleMarker:layer, latLngBounds() {return {extend(){return this;},isValid(){return true;},pad(){return this;}};}};
  const window = {__UAM_DASHBOARD_DATA__: model, L};
  const c = vm.createContext({document,window,L,console,requestAnimationFrame(fn){fn();}});
  vm.runInContext(script,c);
  return {c,elements,seen};
}

const pendingModel=structuredClone(actual.__UAM_DASHBOARD_DATA__);
pendingModel.runs=['C1','C2'].map(code=>({...structuredClone(pendingModel.runs[0]),metadata:{scenario_key:code}}));
const pending=context(pendingModel);
vm.runInContext('renderDashboard(window.__UAM_DASHBOARD_DATA__)',pending.c);
assert.match(pending.elements.get('protocol-data-note').textContent,/aguardando/);
assert.equal(pending.elements.get('run-select').disabled,true);
assert.equal(pending.elements.get('metric-aircraft').textContent,'');

// Synthetic UI fixture only: no relabeling or rewriting of published results.
const model=structuredClone(actual.__UAM_DASHBOARD_DATA__);
const template=model.runs[0];
model.runs=['C1.1','C1.2','C2.1','C2.2'].map(code => ({...structuredClone(template),
  metadata:{scenario_key:code,day_key:'produto2_p100',variant_label:code},
  density:{replica_count:50,position_sample_count:150},
  uam_projection:{type:'FeatureCollection',features:[]},
  uam_junctions:{type:'FeatureCollection',features:[]},
  uam_centerlines:{type:'FeatureCollection',features:[]},
  candidate_nodes:{type:'FeatureCollection',features:[]},
}));
model.comparison={days:[{day_key:'produto2_p100',day_label:'P100',rows:model.runs.map((run,index)=>({run_index:index,...run.metadata}))}]};
const current=context(model);
vm.runInContext('state.map={hasLayer(){return false;},invalidateSize(){},fitBounds(){},setView(){}};renderDashboard(window.__UAM_DASHBOARD_DATA__)',current.c);
assert.match(current.elements.get('run-select').innerHTML,/C2\.2/);
assert.match(current.elements.get('map-info-text').textContent,/50 réplicas/);
assert.equal(current.elements.get('layer-complexity').disabled,true);
assert.equal(current.elements.has('layer-tracks'),false);
assert.equal(current.elements.has('layer-planned'),false);
assert.equal(current.elements.has('viewer3d-canvas'),false);
assert(!current.seen.some(collection=>collection===model.runs[0].tracks || collection===model.runs[0].planned_routes));
vm.runInContext('state.activeRunIndex=3;renderSelectedRun()',current.c);
assert.equal(current.elements.get('layer-complexity').disabled,false);
assert.match(current.elements.get('map-info-text').textContent,/50 réplicas/);
console.log('Dashboard DOM/Leaflet contracts: OK (pending legacy, four scenarios, hidden paths, density, scenario change)');
