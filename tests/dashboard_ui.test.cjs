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
  const elements = new Map();
  const drawn=[];
  const canvasContext=new Proxy({}, {get(target,key){return target[key] || ((...args)=>drawn.push([key,...args]));}});
  function element(id) {
    return {id,innerHTML:'',textContent:'',hidden:false,value:'',dataset:{}, listeners:{},
      checked:html.includes(`id="${id}" checked`),
      setAttribute(name,value){this[name]=value;}, removeAttribute(name){delete this[name];},
      addEventListener(name,fn){this.listeners[name]=fn;},
      after(node){elements.set(node.id,node);}, scrollIntoView(){}, setPointerCapture(){},
      getBoundingClientRect(){return {width:800,height:500};}, getContext(){return canvasContext;},
      querySelectorAll(selector){
        if(selector!=='[data-simt]')return [];
        this.buttons=[...this.innerHTML.matchAll(/data-simt="([^"]+)"/g)].map(m=>{
          const node=element('time-button');node.dataset.simt=m[1];return node;
        });return this.buttons;
      },
      classList:{toggle(){},add(){},remove(){}},closest(){return {hidden:false};}
    };
  }
  for(const id of ids) elements.set(id,element(id));
  const seen = [];
  const layer = () => ({addTo() {return this;}, addLayer() {}, bindTooltip() {}, bindPopup() {}});
  const document = {
    createElement(){return element("");}, addEventListener() {}, getElementById(id) {return elements.get(id) || null;},
    querySelectorAll() {return [];}, querySelector() {return {hidden:false};},
  };
  const L = {geoJSON(data) {seen.push(data);return layer();}, layerGroup: layer, heatLayer: layer,
    circleMarker:layer, latLngBounds() {return {extend(){return this;},isValid(){return true;},pad(){return this;}};}};
  const window = {__UAM_DASHBOARD_DATA__: model, L, setTimeout(fn){fn();}};
  vm.runInNewContext(fs.readFileSync(path.join(root, 'docs/assets/scenario_catalog.js'), 'utf8'), {window});
  const frames=new Map();let frame=0;
  const c = vm.createContext({document,window,L,console,requestAnimationFrame(fn){if(fn.name!=="animate3D"){fn();return 0;}frames.set(++frame,fn);return frame;},cancelAnimationFrame(id){frames.delete(id);}});
  vm.runInContext(script,c);
  return {c,elements,seen,drawn,frames};
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
// Explicit legacy fixture even after the published bundle has been reprocessed.
template.analysis_schema_version=0;
template.dashboard.chart_aggregation_version=0;
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
assert.equal(current.elements.has('viewer3d-canvas'),true);
assert.equal(current.elements.has('kpa-time-to-conflict'),false);
assert.equal(current.elements.get('chart-active').hidden,true);
assert.match(current.elements.get('chart-active-aggregation').textContent,/indisponível/);
assert.match(current.elements.get('stability-safety').innerHTML,/valores individuais/);
assert(current.drawn.some(call=>call[0]==='lineTo'));
vm.runInContext('bind3DControls()',current.c);
const timeButton=current.elements.get('conflict-timeline-body').buttons[0];
assert(timeButton);timeButton.listeners.click();
assert.equal(vm.runInContext('viewer3d.currentTime',current.c),Number(timeButton.dataset.simt));
assert.equal(vm.runInContext('state.activeKpa',current.c),'safety');
current.elements.get('viewer3d-play').listeners.click();
assert.equal(current.frames.size,1);
assert(!current.seen.some(collection=>collection===model.runs[0].tracks || collection===model.runs[0].planned_routes));
vm.runInContext('state.activeRunIndex=3;renderSelectedRun()',current.c);
assert.equal(current.elements.get('layer-complexity').disabled,false);
assert.equal(current.frames.size,0);
assert.equal(vm.runInContext('viewer3d.playing',current.c),false);
assert.equal(vm.runInContext('viewer3d.currentTime',current.c),model.runs[3].trajectory_3d.sim_start_s);
assert.equal(vm.runInContext('viewer3d.data',current.c),model.runs[3].trajectory_3d);
assert.match(current.elements.get('map-info-text').textContent,/50 réplicas/);
console.log('Dashboard DOM/Leaflet contracts: OK (pending legacy, four scenarios, hidden paths, density, scenario change)');

// Aggregated-format fixture: valid count, images, stability and missing next run.
model.runs[3].analysis_schema_version=1;
model.runs[3].dashboard.chart_aggregation_version=1;
model.runs[3].aggregate_analysis={schema_version:1,coverage:[],charts:{}};
model.runs[3].stability={schema_version:1,panels:{overview:{},safety:{},efficiency:{},capacity:{}}};
vm.runInContext('renderSelectedRun()',current.c);
assert.equal(current.elements.get('chart-active').hidden,false);
model.runs[0].trajectory_3d=null;
vm.runInContext('state.activeRunIndex=0;renderSelectedRun()',current.c);
assert.equal(vm.runInContext('viewer3d.data',current.c),null);
assert.equal(current.elements.get('viewer3d-play').disabled,true);
assert.equal(current.elements.get('chart-active').hidden,true);
assert.match(current.elements.get('viewer3d-status').textContent,/Sem trajetórias/);
console.log('3D seek/play/reset-on-scenario and aggregate-version guards: OK');

model.runs[3].stability.panels.safety={example:{status:'confirmed',valid_count:50,total_count:50,stable_from_n:30,confirmed_at_n:44,trace:Array.from({length:50},(_,i)=>({replicas:i+1,mean:10+i*.01,ci95:i>1?[9,11]:null,criterion_met:i>=29}))}};
vm.runInContext('state.activeRunIndex=3;renderSelectedRun()',current.c);
const stabilityHtml=current.elements.get('stability-safety').innerHTML;
assert.match(stabilityHtml,/Confirmação em 44 réplicas/);
assert.match(stabilityHtml,/a partir de 30 réplicas/);
assert.match(stabilityHtml,/<svg/);
assert(!/NaN|Infinity/.test(stabilityHtml));
console.log('Stability SVG and distinct start/confirmation labels: OK');

// Every canonical combination must remain reachable through the five controls.
const catalog=current.c.window.__UAM_SCENARIO_CATALOG__.scenarios.filter(row=>row.condition==='nominal');
const allModel={};
allModel.runs=catalog.map(row=>({replica_count:50,metadata:{scenario_key:row.scenario,day_key:'produto2_p100',variant_label:row.scenario,scenario_dimensions:row}}));
allModel.comparison={days:[{day_key:'produto2_p100',day_label:'P100',rows:allModel.runs.map((run,run_index)=>({run_index,...run.metadata}))}]};
const all=context(allModel);
vm.runInContext('state.runs=window.__UAM_DASHBOARD_DATA__.runs;state.comparison=window.__UAM_DASHBOARD_DATA__.comparison;state.activeDayKey="produto2_p100";populateScenarioFilters()',all.c);
const fields=[['corridor-select','airspace'],['management-select','management'],['condition-select','condition'],['vertiports-select','vertiports'],['separation-select','separation_seconds']];
for(const row of catalog){
  for(const [index,[id,key]] of fields.entries()){
    const select=all.elements.get(id);select.value=String(row[key]??'');vm.runInContext(`populateScenarioFilters(${index})`,all.c);
  }
  assert.equal(vm.runInContext('state.runs[state.activeRunIndex].metadata.scenario_key',all.c),row.scenario);
  assert.match(all.elements.get('scenario-selection').textContent,new RegExp(row.scenario.replaceAll('.','\\.')));
}
assert.equal(all.elements.get('legacy-run-filter').hidden,true);
assert.equal(all.elements.get('condition-select').disabled,true);
assert.match(all.elements.get('condition-select').innerHTML,/value="disturbed" disabled/);
// Leaving micro clears the headway; no fabricated baseline with 38 seconds.
all.elements.get('management-select').value='none';
vm.runInContext('populateScenarioFilters(1)',all.c);
assert.equal(all.elements.get('separation-select').value,'');
assert.equal(all.elements.get('separation-select').disabled,true);
console.log('All 36 canonical combinations reachable; unavailable conditions and non-micro headways guarded: OK');
