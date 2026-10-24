#!/usr/bin/env node
// rp_dummy2 (CP4_bis): simulation of two scope features of the web page ported from lock_in+pid_harmonic:
//   1. Ext Trig sets the Trigger panel (v2.3.24): when the user picks in Ext Trig (dummy_trig_sw) a value that is not
//      None and differs from the current one, Trigger Source = External (2) and Mode = Normal (1) go in the SAME POST
//      (from Single the page polls again); None changes nothing else; already Normal/External: only the Ext Trig;
//      other selects do not apply it; Config load keeps the values of the config (the rule is only in the handler of
//      the select).
//   2. Reset zoom (v2.3.21, without ramp / modulation periods: no preset sweeps in the dummy): X = one whole memory of
//      the scope at the current Dec (16384 x 8 ns x Dec) from t = 0, in the current time units, a bit under one
//      memory so that the server keeps the same Dec (model of src/main.c: float32 xmin/xmax, smallest Dec whose memory
//      covers the window); Y = -1..1 V, raw mode -8192..8192 (before: X 0..130 us at Dec 1, Y +-1 count in raw mode).
// Real functions of index.html: onDropdownChange(), sendParams() -> splitParams() -> postParamsChunks(), loadParams(),
// unsentChanges(), updateTimeUnits(), doGetData(), runStop(), config_load_storage(), the [RESET ZOOM] block,
// resetZoom(), resetZoomY(), scopeSetXWindow(), timeUnitFactor(). Mocked: jQuery/DOM, $.ajax (a server that keeps
// what it gets and answers all the params), localStorage, the plot (only its axes and options).
//
// Usage:  node tests/ext_trig_reset_zoom_sim.js [index.html]   (default ../dummy/index.html; exit code 1 on failure)
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path');

const args = process.argv.slice(2);
const file = args.find(a => !a.startsWith('--')) || path.join(__dirname, '..', 'dummy', 'index.html');
const html = fs.readFileSync(file, 'utf8');
const js = [...html.matchAll(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');

function braceFrom(i) {
  let d = 0;
  for(let k = js.indexOf('{', i); k < js.length; k++) {
    if(js[k] == '{') d++;
    else if(js[k] == '}' && --d == 0) return js.slice(i, k + 1);
  }
  return '';
}
function fnSrc(name) { const i = js.indexOf('function ' + name + '('); return i < 0 ? '' : braceFrom(i); }
function varSrc(name) { const m = js.match(new RegExp('\\n\\s*var ' + name + ' = [\\s\\S]*?;\\s*(//.*)?\\n')); return m ? m[0] : ''; }
function blockSrc(tag) {
  const a = js.indexOf('// [' + tag + ' BEGIN]'), b = js.indexOf('// [' + tag + ' END]');
  return (a < 0 || b < 0) ? '' : js.slice(a, b);
}

// ---- clock ----------------------------------------------------------------------------------------------------------
class Clock {
  constructor() { this.t = 1000; this.q = []; this.n = 0; }
  at(t, fn) { const id = ++this.n; this.q.push({ t: Math.max(t, this.t), fn, id }); return id; }
  after(d, fn) { return this.at(this.t + (d || 0), fn); }
  cancel(id) { this.q = this.q.filter(e => e.id !== id); }
  run(until) {
    for(let g = 0; g < 1000000; g++) {
      let bi = -1;
      for(let i = 0; i < this.q.length; i++)
        if(this.q[i].t <= until && (bi < 0 || this.q[i].t < this.q[bi].t || (this.q[i].t == this.q[bi].t && this.q[i].id < this.q[bi].id))) bi = i;
      if(bi < 0) break;
      const e = this.q.splice(bi, 1)[0];
      this.t = e.t; e.fn();
    }
    this.t = Math.max(this.t, until);
  }
}

// ---- model of the server (src/main.c transform_acq_params(), src/fpga.c) -------------------------------------------
const DEC = [1, 8, 64, 128, 256, 512, 1024, 8192, 65536, 524288];
const MEM = 16384 * 8e-9;
function rangeToUnit(r) { return r <= 1 ? 0 : (r <= 6 ? 1 : 2); }
function unitF(tu) { return Math.pow(10, 3 * (2 - tu)); }
// new time_range / units for a POST with xmin/xmax in the current units (the server keeps them as float).
// ForceX as src/main.c transform_acq_params(): after a change of units the server keeps the forced window (and
// forcex_flag 1) while the window of the client differs by more than x33 from it and for at most 1.5 s, so the
// next POSTs of a split send (which still carry the window in the old units) do not move it (CP6.1 retest 3).
const FX = new WeakMap();
function srvWindow(srv, q, now) {
  if(!('xmin' in q) && !('xmax' in q)) return;
  const xmin_g = Math.fround(Number('xmin' in q ? q.xmin : srv.xmin)), xmax_g = Math.fround(Number('xmax' in q ? q.xmax : srv.xmax));
  const fx = FX.get(srv);
  if(fx) {
    let ratio = (xmax_g - xmin_g) != 0 ? Math.abs(fx.xmax - fx.xmin) / Math.abs(xmax_g - xmin_g) : 0;
    if(ratio > 1) ratio = 1 / ratio;
    if(ratio > 0.03 || (now !== undefined && now - fx.t > 1500)) FX.delete(srv);
    else { Object.assign(srv, { xmin: fx.xmin, xmax: fx.xmax, time_units: fx.tu, time_range: fx.tr, forcex_flag: 1 }); return; }
  }
  if(xmin_g == -1e6 && xmax_g == 1e6) {           // old Reset Zoom request: forced 0..130 us, Dec 1
    Object.assign(srv, { xmin: 0, xmax: 130, time_units: 0, time_range: 0, forcex_flag: 1 });
    return;
  }
  const f = unitF(srv.time_units);
  const xmin = xmin_g / f, xmax = xmax_g / f;
  const rdec = (srv.trig_mode == 0 ? xmax : (Math.max(xmax, 0) - xmin)) * 125e6 / 16384;
  let i = 0; while(i <= 9 && DEC[i] < rdec) i++;
  if(i > 9) i = 9;
  const tu = rangeToUnit(i), nf = unitF(tu);
  const changed = (tu != srv.time_units);
  Object.assign(srv, { time_range: i, forcex_flag: changed ? 1 : 0, time_units: tu, xmin: xmin * nf, xmax: xmax * nf });
  if(changed) FX.set(srv, { xmin: srv.xmin, xmax: srv.xmax, tu, tr: i, t: now === undefined ? 0 : now });
}

// ---- environment ----------------------------------------------------------------------------------------------------
const BASE = { xmin: 0, xmax: 20, single_btn: 0, auto_flag: 0, forcex_flag: 0, time_units: 1, time_range: 3, trig_mode: 0,
  trig_source: 0, trig_edge: 0, trig_delay: 0, trig_level: 0, dummy_trig_sw: 0, dummy_oscA_sw: 1, dummy_oscB_sw: 2,
  dummy_osc_raw_mode: 0, gui_xmin: 0, gui_xmax: 20, gui_reset_y_range: 2, scale_ch1: 1, scale_ch2: 1 };

function makeEnv(init, ls) {
  const clock = new Clock(), dom = {}, log = [];
  const D = id => (dom[id] = dom[id] || { cls: new Set(), val: undefined, text: '', html: '', prop: {}, attr: {}, data: {} });
  const el = sel => {
    sel = String(sel);
    const ids = sel.split(',').map(s => s.trim().replace(/^#/, '')).filter(s => s);
    const o = {
      val(v) { if(v === undefined) return D(ids[0]).val; ids.forEach(i => D(i).val = String(v)); return o; },
      prop(k, v) { if(v === undefined) return D(ids[0]).prop[k]; ids.forEach(i => D(i).prop[k] = v); return o; },
      attr(k, v) { if(v === undefined) return D(ids[0]).attr[k]; ids.forEach(i => D(i).attr[k] = v); return o; },
      html(v) { if(v === undefined) return D(ids[0]).html; ids.forEach(i => D(i).html = String(v)); return o; },
      text(v) { if(v === undefined) return D(ids[0]).text; ids.forEach(i => D(i).text = String(v)); return o; },
      data(k, v) { if(v === undefined && typeof k === 'string') return D(ids[0]).data[k]; if(typeof k === 'string') ids.forEach(i => D(i).data[k] = v); return o; },
      show() { return o; }, hide() { return o; }, focus() { return o; }, blur() { return o; },
      trigger() { return o; }, parent() { return o; }, closest() { return { length: 1 }; }, on() { return o; },
      find() { return o; }, not() { return o; }, tooltip() { return o; }, modal() { return o; },
      addClass(c) { ids.forEach(i => c.split(' ').forEach(x => D(i).cls.add(x))); return o; },
      removeClass(c) { ids.forEach(i => c.split(' ').forEach(x => D(i).cls.delete(x))); return o; },
      toggleClass() { return o; }, hasClass(c) { return D(ids[0]).cls.has(c); }, is() { return false; },
      length: 1, 0: (D(ids[0]).node = D(ids[0]).node || { download: '', href: '' }),
    };
    return o;
  };
  const $ = sel => (sel && typeof sel == 'object') ? el('#' + (sel.id || 'doc')) : el(sel);
  $.inArray = (v, a) => a.indexOf(v);
  $.trim = s => String(s).trim();
  $.extend = function () { let a = Array.from(arguments); const deep = (a[0] === true); if(deep) a = a.slice(1);
    const t = a[0];
    const merge = (x, y) => { for(const k in y) { if(deep && y[k] && typeof y[k] === 'object' && !Array.isArray(y[k])) { x[k] = x[k] || {}; merge(x[k], y[k]); } else x[k] = y[k]; } };
    for(let i = 1; i < a.length; i++) merge(t, a[i] || {});
    return t; };
  $.isPlainObject = o => o !== null && typeof o == 'object' && !Array.isArray(o);
  $.isEmptyObject = o => Object.keys(o).length == 0;
  $.isNumeric = v => !isNaN(parseFloat(v)) && isFinite(v);
  $.Deferred = function () {
    let st = null, a, dn = [], fl = [], al = [];
    const run = () => { (st == 'r' ? dn : fl).forEach(f => f.apply(null, a)); al.forEach(f => f.apply(null, a)); dn = []; fl = []; al = []; };
    const p = { done(f) { dn.push(f); if(st) run(); return p; }, fail(f) { fl.push(f); if(st) run(); return p; },
                always(f) { al.push(f); if(st) run(); return p; }, promise() { return p; },
                then(f) { const d2 = $.Deferred(); p.done((...x) => { const r = f(...x); if(r && r.done) r.done((...y) => d2.resolve(...y)); else d2.resolve(r); }); return d2.promise(); } };
    p.resolve = (...x) => { if(!st) { st = 'r'; a = x; run(); } return p; };
    p.reject = (...x) => { if(!st) { st = 'j'; a = x; run(); } return p; };
    return p;
  };
  const srv = Object.assign({}, BASE, init || {});
  let gets = 0;
  $.ajax = o => {
    const d = $.Deferred();
    if(o.type == 'POST') {
      const q = JSON.parse(o.data).datasets.params;
      log.push({ t: clock.t, kind: 'POST', q });
      clock.after(5, () => {
        srv.forcex_flag = 0;
        for(const k in q) if(!['single_btn', 'time_units', 'time_range', 'forcex_flag', 'gui_xmin', 'gui_xmax', 'xmin', 'xmax'].includes(k)) srv[k] = q[k];
        srvWindow(srv, q, clock.t);
        const r = Object.assign({}, srv, { single_btn: 0 });
        d.resolve({ app: { id: 'dummy' }, status: 'OK', datasets: { params: r, g1: [] } });
      });
    }
    else {
      gets++;
      log.push({ t: clock.t, kind: 'GET' });
      clock.after(20, () => d.resolve({ app: { id: 'dummy' }, status: 'OK',
        datasets: { params: Object.assign({}, srv), g1: [{ data: [[0, 0]] }, { data: [[0, 0]] }] } }));
    }
    return d.promise();
  };
  const axes = { min: srv.xmin + 1, max: srv.xmax / 2 }, yax = [{ min: -0.3, max: 0.2 }];
  const plot = { getOptions() { return { xaxes: [axes], yaxes: yax }; }, setupGrid() {}, draw() {}, width() { return 500; },
                 setData() {}, getAxes() { return { xaxis: axes, yaxis: yax[0] }; } };
  const store = ls || {};
  if(!store.getItem) Object.defineProperties(store, {
    getItem:    { value(k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; } },
    setItem:    { value(k, v) { store[k] = String(v); } },
    removeItem: { value(k) { delete store[k]; } } });
  const ctx = { $, console: { log(m) { log.push({ t: clock.t, kind: 'LOG', m: String(m) }); }, info() {}, warn() {} },
    Object, JSON, Math, Number, isFinite, isNaN, parseInt, parseFloat, String, Array, Date: Object.assign(function() { return new Date(); },
    { now: () => clock.t }), encodeURIComponent, alert() {}, Storage: function() {}, localStorage: store,
    setTimeout: (f, d) => clock.after(d, f), clearTimeout: id => clock.cancel(id),
    document: { activeElement: null }, plot, autorun: 1, refresh_counter: 0, trigger_just_set: false,
    downloading: false, user_editing: false, control_lost: false, trig_dragging: false, last_get_failed: false,
    floatToLocalString: x => String(x), shortenFloat: x => x, parseLocalFloat: parseFloat, format_oom: (n, u) => String(n) + u,
    display_update() {}, updateTriggerSlider() {}, saveState() {}, redrawPlot() {}, updateRanges() {}, initPlot() {},
    filterData: d => d, showModalError: m => log.push({ t: clock.t, kind: 'MODAL', m }), app_id: 'dummy',
    post_url: '/data', get_url: '/data', request_timeout: 10000, update_interval: 50, isEscapeKey: e => e.key == 'Escape',
    plot_options: { xaxis: { min: -1000000, max: 1000000 }, yaxis: {} }, xmin: -1000000, xmax: 1000000,
    meas_panel_dec: 5, last_unit_mode: 0, convertSec() { return 0; }, convertHz() { return 0; } };
  vm.createContext(ctx);
  let code = ['sending', 'send_que', 'send_que_all', 'single_que', 'use_long_timeout', 'readonly_keys', 'display_keep_keys', 'unsent_base',
    'unsent_skip_keys', 'always_send_params', 'last_send_params', 'post_chunk_timeout', 'post_chunk_retries', 'long_timeout',
    'post_min_gap_ms', 'post_max_per_s', 'post_starts', 'post_rate_timer', 'post_rate_args', 'server_ro_keys',
    'config_storage_key', 'config_storage_old_key'].map(varSrc).join('\n');
  code += 'var x_axis_tu = ' + Number(srv.time_units) + ';   // as initPlot() sets it\n';
  code += 'var last_raw_mode = ' + (Number(srv.dummy_osc_raw_mode) ? 'true' : 'false') + ', raw_y_keep = false;\n';
  code += 'var monitor_bar_tsp = 0; function set_bar() {}\n';   // used by display_update() (monitors: none here)
  code += 'var params = {original:null, local:null, storage: []};\nvar post_max_bytes = 600;\nvar post_inflight = 0, last_post_end = 0;\n' +
          'var set_trigger_val = false, plot_time_units = null, update_timer = null, datasets = [];\n';
  const ct = (js.match(/config_params_txts = [\s\S]*?;\n/) || [''])[0];
  code += 'var ' + ct + 'var config_params_keys = config_params_txts.split(",");\n';
  code += ['unsentChanges', 'loadParams', 'updateTimeUnits', 'isParamChanged', 'splitParams', 'postParamsChunks',
           'sendParams', 'postEnd', 'sendableValue', 'isSendable', 'hasRealChange', 'doGetData', 'runStop', 'singleUpdate',
           'onDropdownChange', 'config_storage_read', 'config_load_storage', 'resetZoom', 'resetZoomY', 'scopeSetXWindow',
           'timeUnitFactor', 'roundLevel', 'xAxisToUnits', 'display_update'].map(fnSrc).join('\n');
  code += '\n' + blockSrc('RESET ZOOM') + '\n';
  code += '\n' + blockSrc('RAW TRIGGER') + '\n' + blockSrc('CONFIG KEYS') + '\n';   // units of the level, config keys (2.0.1)
  code += '\nvar scope_stop = false;\nfunction updateGraphData() { if(downloading || scope_stop) return; if(update_timer) { clearTimeout(update_timer); update_timer = null; }' +
          ' downloading = true; doGetData(); }\n';
  code += '\nthis.__get = function(e){return eval(e)};';
  vm.runInContext(code, ctx);
  const get = e => ctx.__get(e);
  const E = {
    log, dom, D, get, clock, srv, axes, yax, ls: store, gets: () => gets,
    posts(from) { return log.filter(l => l.kind == 'POST' && (from === undefined || l.t >= from)).map(l => l.q); },
    run(ms) { clock.run(clock.t + ms); },
    select(id, v) { D(id).val = String(v); get('onDropdownChange')($('#' + id), id); },
  };
  get('loadParams')(Object.assign({}, srv));
  get('autorun = ' + (srv.trig_mode == 2 ? 0 : 1));
  get('updateGraphData')();
  E.run(300);
  return E;
}

let fails = 0, n = 0;
function check(name, fn, extra) {
  n++;
  let ok = false, x = '';
  try { ok = !!fn(); } catch(e) { x = 'exception: ' + e.message; }
  let ex = '';
  try { ex = extra ? extra() : ''; } catch(e) { ex = ''; }
  console.log((ok ? 'ok   ' : 'FAIL ') + name + ((x || ex) ? '  [' + (x || ex) + ']' : ''));
  if(!ok) fails++;
}
const J = o => JSON.stringify(o);
const near = (a, b, r) => Math.abs(a - b) <= (r || 1e-9) * Math.max(1, Math.abs(a), Math.abs(b));

console.log('=== Ext Trig rule / Reset zoom (' + file + ') ===');

// ---- 1. Ext Trig rule ---------------------------------------------------------------------------------------------
{
  let extra = '';
  check('1.1 Auto/Channel 1/None -> Ext Trig Pin (1): ONE POST with dummy_trig_sw 1 + trig_source 2 + trig_mode 1; selects updated', () => {
    const E = makeEnv({ trig_mode: 0, trig_source: 0, dummy_trig_sw: 0 });
    const t0 = E.clock.t;
    E.select('dummy_trig_sw', 1); E.run(400);
    const ps = E.posts(t0), q = ps[0] || {};
    extra = J(ps);
    return ps.length == 1 && q.dummy_trig_sw == 1 && q.trig_source == 2 && q.trig_mode == 1 &&
           E.srv.trig_mode == 1 && E.srv.trig_source == 2 && E.D('trig_source').val == '2' && E.D('trig_mode').val == '1' &&
           E.get('autorun') == 1;
  }, () => extra);
  check('1.2 Single -> Ext Trig 2 (an option added by the user): Normal + External in one POST, polling again (GET /data)', () => {
    const E = makeEnv({ trig_mode: 2, trig_source: 1, dummy_trig_sw: 1 });
    E.get('autorun = 0');
    const t0 = E.clock.t, g0 = E.gets();
    E.select('dummy_trig_sw', 2); E.run(1000);
    const ps = E.posts(t0), q = ps[0] || {};
    extra = J(ps) + ' GETs ' + (E.gets() - g0);
    return ps.length == 1 && q.dummy_trig_sw == 2 && q.trig_source == 2 && q.trig_mode == 1 && E.get('autorun') == 1 &&
           E.gets() - g0 >= 5 && E.D('btn_single').prop.disabled === true;
  }, () => extra);
  check('1.3 Ext Trig -> None: only dummy_trig_sw (Source/Mode unchanged)', () => {
    const E = makeEnv({ trig_mode: 0, trig_source: 0, dummy_trig_sw: 1 });
    const t0 = E.clock.t;
    E.select('dummy_trig_sw', 0); E.run(400);
    const ps = E.posts(t0), q = ps[0] || {};
    extra = J(ps);
    return ps.length == 1 && q.dummy_trig_sw == 0 && !('trig_source' in q) && !('trig_mode' in q) && E.srv.trig_mode == 0 && E.srv.trig_source == 0;
  }, () => extra);
  check('1.4 already Normal + External: only dummy_trig_sw', () => {
    const E = makeEnv({ trig_mode: 1, trig_source: 2, dummy_trig_sw: 1 });
    const t0 = E.clock.t;
    E.select('dummy_trig_sw', 2); E.run(400);
    const ps = E.posts(t0), q = ps[0] || {};
    extra = J(ps);
    return ps.length == 1 && q.dummy_trig_sw == 2 && !('trig_source' in q) && !('trig_mode' in q);
  }, () => extra);
  check('1.5 the same Ext Trig picked again (no change): nothing else is changed', () => {
    const E = makeEnv({ trig_mode: 0, trig_source: 0, dummy_trig_sw: 1 });
    const t0 = E.clock.t;
    E.select('dummy_trig_sw', 1); E.run(400);
    const ps = E.posts(t0);
    extra = J(ps);
    return E.srv.trig_mode == 0 && E.srv.trig_source == 0 && ps.every(q => !('trig_mode' in q) && !('trig_source' in q));
  }, () => extra);
  check('1.6 other selects (OscA, Source) do not apply the rule', () => {
    const E = makeEnv({ trig_mode: 0, trig_source: 0, dummy_trig_sw: 1 });
    const t0 = E.clock.t;
    E.select('dummy_oscA_sw', 3); E.run(400); E.select('trig_source', 1); E.run(400);
    const ps = E.posts(t0);
    extra = J(ps);
    return ps.length == 2 && E.srv.trig_mode == 0 && E.srv.trig_source == 1;
  }, () => extra);
  check('1.7 Config load (Ext Trig Pin, Channel 1, Auto): the config values stay (rule not applied)', () => {
    const E = makeEnv({ trig_mode: 1, trig_source: 2, dummy_trig_sw: 0 });
    const data = Object.assign({}, BASE, { trig_mode: 0, trig_source: 0, dummy_trig_sw: 1 });
    E.ls[E.get('config_storage_key')] = JSON.stringify([{ name: 'k', datetime: '', data }]);
    E.get('config_load_storage')('k'); E.run(1500);
    extra = 'server ' + J({ trig_mode: E.srv.trig_mode, trig_source: E.srv.trig_source, dummy_trig_sw: E.srv.dummy_trig_sw });
    return E.srv.dummy_trig_sw == 1 && E.srv.trig_mode == 0 && E.srv.trig_source == 0;
  }, () => extra);
  check('1.9 Config load sets the X axis of the plot to the window of the config (CP6.1 retest O4; same units: ms)', () => {
    const E = makeEnv({ trig_mode: 0, trig_source: 0, dummy_trig_sw: 0 });
    const data = Object.assign({}, BASE, { xmin: 0, xmax: 130, time_units: 1 });
    E.ls[E.get('config_storage_key')] = JSON.stringify([{ name: 'k', datetime: '', data }]);
    E.get('config_load_storage')('k'); E.run(1500);
    const o = E.get('plot').getOptions().xaxes[0];
    extra = 'axis ' + o.min + '..' + o.max + ', server xmax ' + E.srv.xmax;
    return o.min == 0 && o.max == 130 && E.srv.xmax == 130;
  }, () => extra);
  // CP6.1 retest F4: the window of the config is converted to the time units of the plot
  const xcase = (name, plot_tu, plot_xmax, cfg, want_axis, want_s) => check(name, () => {
    const E = makeEnv({ trig_mode: 0, trig_source: 0, dummy_trig_sw: 0, time_units: plot_tu, xmin: 0, xmax: plot_xmax,
                        gui_xmax: plot_xmax, time_range: plot_tu == 0 ? 1 : 3 });
    const data = Object.assign({}, BASE, cfg);
    E.ls[E.get('config_storage_key')] = JSON.stringify([{ name: 'k', datetime: '', data }]);
    const t0 = E.clock.t;
    E.get('config_load_storage')('k');
    const o = E.get('plot').getOptions().xaxes[0];
    const ax = [o.min, o.max];
    E.run(1500);
    const sent = E.posts(t0).filter(q => q.xmax !== undefined).pop() || {};
    const srv_s = E.srv.xmax / unitF(E.srv.time_units);
    // after the reply (CP6.1 retest 2): the axis shows the window in the units of the server, the page has its units
    const fin = [o.min, o.max], pu = E.get('params.original.time_units');
    const fin_s = fin[1] / unitF(pu);
    extra = 'axis after load ' + J(ax) + ', sent ' + J({ xmin: sent.xmin, xmax: sent.xmax, time_units: sent.time_units }) +
            ', server ' + E.srv.xmax + ' (units ' + E.srv.time_units + ') = ' + srv_s + ' s; axis after the reply ' + J(fin) +
            ' (page units ' + pu + ') = ' + fin_s + ' s';
    return Math.abs(ax[0] - want_axis[0]) < 1e-9 && Math.abs(ax[1] - want_axis[1]) < 1e-9 * Math.max(1, want_axis[1]) &&
           sent.time_units == plot_tu && Math.abs(srv_s - want_s) < 1e-6 * want_s &&
           pu == E.srv.time_units && Math.abs(fin_s - want_s) < 1e-6 * want_s;
  }, () => extra);
  xcase('1.10 config 0..130 us loaded with the plot in ms -> axis 0..0.13 ms, server 130 us, after the reply in us: 0..130 (before: 0..130 ms / 0..0.13 us)',
        1, 20, { xmin: 0, xmax: 130, time_units: 0 }, [0, 0.13], 130e-6);
  xcase('1.11 config 0..1.57 ms loaded with the plot in us -> axis 0..1570 us, server 1.57 ms (before: 0..1.57 us)',
        0, 130, { xmin: 0, xmax: 1.57, time_units: 1 }, [0, 1570], 1.57e-3);
  xcase('1.12 config 0..2 s loaded with the plot in us -> axis 0..2e6 us, server 2 s',
        0, 130, { xmin: 0, xmax: 2, time_units: 2 }, [0, 2e6], 2);
  check('1.13 configXWindow(): no window -> null; config without units -> unchanged numbers', () => {
    const cw = makeEnv({}).get('configXWindow');
    return cw({ xmin: 5, xmax: 1 }, 1) === null && J(cw({ xmin: 0, xmax: 3 }, 1)) == J({ xmin: 0, xmax: 3, time_units: 1 });
  });

  // CP6.1 retest 2 (F4): a reply of the server with other time_units and forcex_flag 0 (split POSTs: only the last
  // reply is read) must convert the numbers of the X axis, not only the label; with forcex_flag 1 the axis takes the
  // window of the server once (no double conversion)
  const ucase = (name, forcex) => check(name, () => {
    const E = makeEnv({ trig_mode: 0, time_units: 1, xmin: 0, xmax: 2, gui_xmax: 2, time_range: 3 });
    const o = E.get('plot').getOptions().xaxes[0];
    o.min = 0; o.max = 0.13;                                 // the page shows 0..0.13 ms
    Object.assign(E.srv, { time_units: 0, time_range: 1, xmin: 0, xmax: 130, gui_xmin: 0, gui_xmax: 130, forcex_flag: forcex });
    E.get('doGetData')(); E.run(200);
    extra = 'axis ' + o.min + '..' + o.max + ', page units ' + E.get('params.original.time_units');
    return E.get('params.original.time_units') == 0 && Math.abs(o.min) < 1e-9 && Math.abs(o.max - 130) < 1e-6;
  }, () => extra);
  ucase('1.14 GET reply in us (forcex_flag 0) while the page is in ms: axis 0..0.13 ms -> 0..130 us (before: 0..0.13 "us")', 0);
  ucase('1.15 GET reply in us with forcex_flag 1: axis = window of the server, 0..130 us (not converted twice)', 1);
  // CP6.1 retest 3 (F4 intermittent): replies with the new units repeated and in any order (split POST of a config
  // load + GET polling) must convert the axis once; no POST may carry the window in the old units
  check('1.17 config load 0..130 us with the plot in ms, GET replies in between the POST chunks: axis 0..130 us at the end, every POST in the units of the server', () => {
    const E = makeEnv({ trig_mode: 0, time_units: 1, xmin: 0, xmax: 2, gui_xmax: 2, time_range: 3 });
    const o = E.get('plot').getOptions().xaxes[0];
    o.min = 0; o.max = 2;
    const keys = E.get('config_params_keys');
    const data = {}; keys.forEach(k => { data[k] = (k in BASE) ? BASE[k] : 0; });
    Object.assign(data, { xmin: 0, xmax: 130, time_units: 0, trig_mode: 0 });
    E.ls[E.get('config_storage_key')] = JSON.stringify([{ name: 'k', datetime: '', data }]);
    E.get('post_max_bytes = 160');                       // several POST chunks, as a config load on the board
    const t0 = E.clock.t;
    E.get('config_load_storage')('k');
    for(let i = 0; i < 12; i++) { E.run(4); E.get('doGetData')(); }
    E.run(3000);
    E.select('dummy_oscA_sw', 3); E.run(400);          // a later POST (any control) carries the window too
    const ps = E.posts(t0).filter(q => q.xmax !== undefined);
    const nchunks = E.posts(t0).length;
    const bad = ps.filter(q => Math.abs(q.xmax - 130000) < 1 || Math.abs(q.xmax - 0.00013) < 1e-9);
    extra = nchunks + ' POSTs, ' + ps.length + ' with xmax ' + J(ps.map(q => q.xmax)) + '; axis ' + o.min + '..' + o.max +
            ', page units ' + E.get('params.original.time_units') + ', server ' + E.srv.xmax + ' (units ' + E.srv.time_units + ')';
    return nchunks >= 3 && ps.length >= 2 && Math.abs(ps[ps.length - 1].xmax - 130) < 1e-3 && bad.length == 0 &&
           E.get('params.original.time_units') == 0 && E.srv.time_units == 0 &&
           Math.abs(o.max - 130) < 1e-3 && Math.abs(E.srv.xmax - 130) < 1e-3;
  }, () => extra);
  check('1.18 the same unit change applied twice / out of order (updateTimeUnits, loadParams, stale reply, the POST copy-back of time_units): converted once, the next POST sends 0..130 us', () => {
    const E = makeEnv({ trig_mode: 0, time_units: 1, xmin: 0, xmax: 0.13, gui_xmax: 0.13, time_range: 3 });
    const o = E.get('plot').getOptions().xaxes[0];
    o.min = 0; o.max = 0.13;
    E.get('params.local.xmin = 0; params.local.xmax = 0.13; params.original.xmin = 0; params.original.xmax = 0.13');
    const r0 = Object.assign({}, E.srv, { time_units: 0, time_range: 1, xmin: 0, xmax: 130, forcex_flag: 0 });
    const r1 = Object.assign({}, E.srv, { time_units: 1, time_range: 3, xmin: 0, xmax: 0.13, forcex_flag: 0 });
    E.get('updateTimeUnits')(r0);
    E.get('loadParams')(Object.assign({}, r0), true);
    E.get('params.original.time_units = 1');            // what the copy-back of a POST used to do
    E.get('loadParams')(Object.assign({}, r0), true);
    E.get('updateTimeUnits')(r0);
    const once = [o.min, o.max];
    E.get('loadParams')(Object.assign({}, r1), true);   // a stale reply in ms: back to ms ...
    E.get('loadParams')(Object.assign({}, r0), true);   // ... and the newer one in us
    Object.assign(E.srv, { time_units: 0, time_range: 1, xmin: 0, xmax: 130 });
    const t0 = E.clock.t;
    E.select('dummy_oscA_sw', 3); E.run(400);
    const q = E.posts(t0).pop() || {};
    extra = 'axis after the repeated change ' + J(once) + ', final ' + J([o.min, o.max]) + ', POST xmax ' + q.xmax;
    return Math.abs(once[1] - 130) < 1e-6 && Math.abs(o.max - 130) < 1e-6 && Math.abs(q.xmax - 130) < 1e-6;
  }, () => extra);
  check('1.19 config load resets the Y axis (Reset zoom: +-1 V) after a wheel zoom (retest 3 O3)', () => {
    const E = makeEnv({ trig_mode: 0 });
    const y = E.get('plot').getOptions().yaxes[0];
    y.min = -0.01; y.max = 0.02;
    E.ls[E.get('config_storage_key')] = JSON.stringify([{ name: 'k', datetime: '', data: Object.assign({}, BASE) }]);
    E.get('config_load_storage')('k'); E.run(1500);
    extra = 'y ' + y.min + '..' + y.max;
    return y.min == -1 && y.max == 1;
  }, () => extra);
  // CP6.1 retest 4 (F5): a config load that changes Raw Mode sets Y once (as Reset zoom for the mode of the config);
  // the Raw Mode change of display_update() must not convert it again. A Raw toggle of the user still converts.
  check('1.20 config loads alternating V <-> Raw (x3 each): Y -1..1 V / -8192..8192 counts every time (before: +-0.000122 V / +-67108864)', () => {
    const E = makeEnv({ trig_mode: 0, dummy_osc_raw_mode: 1 });
    const y = E.get('plot').getOptions().yaxes[0];
    y.min = -8192; y.max = 8192;
    E.get("$('#dummy_osc_raw_mode').data('checked', true)");
    const cfgV = Object.assign({}, BASE, { dummy_osc_raw_mode: 0 }), cfgR = Object.assign({}, BASE, { dummy_osc_raw_mode: 1 });
    E.ls[E.get('config_storage_key')] = JSON.stringify([{ name: 'v', datetime: '', data: cfgV }, { name: 'r', datetime: '', data: cfgR }]);
    const seen = [];
    for(let i = 0; i < 3; i++) {
      E.get('config_load_storage')('v'); E.run(1500); seen.push([y.min, y.max, E.get("$('#trig_lev_units').text()")]);
      E.get('config_load_storage')('r'); E.run(1500); seen.push([y.min, y.max, E.get("$('#trig_lev_units').text()")]);
    }
    extra = J(seen);
    return seen.every((v, i) => (i % 2 == 0) ? (v[0] == -1 && v[1] == 1 && v[2] == 'V') : (v[0] == -8192 && v[1] == 8192 && v[2] == 'counts'));
  }, () => extra);
  check('1.21 a Raw Mode change that does not come from a config load still converts Y (same part of the signal)', () => {
    const E = makeEnv({ trig_mode: 0, dummy_osc_raw_mode: 0, gui_reset_y_range: 2 });
    const y = E.get('plot').getOptions().yaxes[0];
    y.min = -0.5; y.max = 0.5;
    E.get("$('#dummy_osc_raw_mode').data('checked', true)");
    E.get('display_update')();
    extra = 'y ' + y.min + '..' + y.max;
    return Math.abs(y.max - 4096) < 1e-6 && Math.abs(y.min + 4096) < 1e-6;
  }, () => extra);
  check('1.16 xAxisToUnits() is used where the units change (updateTimeUnits, loadParams) and the forceX / AUTO blocks of the POST update the units first', () =>
    /xAxisToUnits\(/.test(fnSrc('updateTimeUnits')) && /xAxisToUnits\(/.test(fnSrc('loadParams')) &&
    (fnSrc('sendParams').match(/updateTimeUnits\(dresult\.datasets\.params\)/g) || []).length == 2);

  check('1.8 the rule is only in onDropdownChange (code check: not in config_load_storage, loadParams, resetZoom)', () =>
    /dummy_trig_sw/.test(fnSrc('onDropdownChange')) && /dv != 0/.test(fnSrc('onDropdownChange')) &&
    !/trig_source\s*=\s*2/.test(fnSrc('config_load_storage')) && !/trig_source\s*=\s*2/.test(fnSrc('loadParams')) &&
    !/trig_source/.test(fnSrc('resetZoom')));
}

// ---- 2. Reset zoom ------------------------------------------------------------------------------------------------
{
  let extra = '';
  check('2.0 [RESET ZOOM] block, resetZoom() without the old server request xmin/xmax = -1e6/1e6', () =>
    blockSrc('RESET ZOOM') !== '' && !/params\.local\.xmin\s*=\s*xmin\s*;/.test(fnSrc('resetZoom')));
  // every time range: window = one memory at that Dec (units of the range), Y +-1 V; the server keeps the Dec
  for(let tr = 0; tr <= 9; tr++) {
    for(const mode of [0, 1]) {
      const tu = rangeToUnit(tr), f = unitF(tu), mem = DEC[tr] * MEM;
      check('2.' + (tr + 1) + (mode ? 'n' : 'a') + ' time_range ' + tr + ' (Dec ' + DEC[tr] + ', ' + ['us', 'ms', 's'][tu] + ', ' +
            (mode ? 'Normal' : 'Auto') + '): X 0 .. one memory (' + (mem * f).toPrecision(6) + '), Y -1..1, same Dec after the POST', () => {
        const E = makeEnv({ trig_mode: mode, time_range: tr, time_units: tu, xmin: 0, xmax: mem * f / 3, gui_xmin: 0, gui_xmax: mem * f / 3 });
        const t0 = E.clock.t;
        E.get('resetZoom')(); E.run(400);
        const ps = E.posts(t0), q = ps[0] || {};
        const o = E.get('plot').getOptions();
        extra = J(q) + ' -> srv range ' + E.srv.time_range + ', y ' + J(o.yaxes[0]);
        return ps.length >= 1 && near(q.xmin, 0) && near(q.xmax, mem * f, 2e-6) && q.xmax < mem * f &&
               o.yaxes.length == 1 && o.yaxes[0].min == -1 && o.yaxes[0].max == 1 &&
               near(o.xaxes[0].min, 0) && near(o.xaxes[0].max, q.xmax) && E.srv.time_range == tr && E.srv.forcex_flag == 0;
      }, () => extra);
    }
  }
  check('2.20 raw mode: Y -8192 .. 8192 (counts; before: +-1 count)', () => {
    const E = makeEnv({ dummy_osc_raw_mode: 1, time_range: 1, time_units: 0, xmax: 500 });
    E.get('resetZoom')(); E.run(400);
    const y = E.get('plot').getOptions().yaxes[0];
    extra = J(y);
    return y.min == -8192 && y.max == 8192;
  }, () => extra);
  check('2.21 zoomed into a part of the window at Dec 64 (units ms): window 0 .. 8.389 ms, units unchanged', () => {
    const E = makeEnv({ time_range: 2, time_units: 1, trig_mode: 1, xmin: 2, xmax: 3, gui_xmin: 2, gui_xmax: 3 });
    E.get('resetZoom')(); E.run(400);
    extra = 'srv ' + J({ xmin: E.srv.xmin, xmax: E.srv.xmax, tr: E.srv.time_range, tu: E.srv.time_units });
    return near(E.srv.xmax, 64 * MEM * 1e3, 2e-6) && E.srv.time_range == 2 && E.srv.time_units == 1;
  }, () => extra);
  check('2.22 resetZoomWindow() pure: invalid time_range -> Dec 1 (0 .. 131.07 us)', () => {
    const E = makeEnv({});
    const w = E.get('resetZoomWindow')({ dummy_osc_raw_mode: 0 }, 'x');
    extra = J(w);
    return w.dec == 1 && near(w.xmax_s, MEM, 2e-6) && w.xmin_s == 0;
  }, () => extra);
}

console.log((fails ? 'FAILED ' + fails : 'ALL OK') + ' (' + (n - fails) + '/' + n + ')');
process.exit(fails ? 1 : 0);
