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
// new time_range / units for a POST with xmin/xmax in the current units (the server keeps them as float)
function srvWindow(srv, q) {
  if(!('xmin' in q) && !('xmax' in q)) return;
  const xmin_g = Math.fround(Number('xmin' in q ? q.xmin : srv.xmin)), xmax_g = Math.fround(Number('xmax' in q ? q.xmax : srv.xmax));
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
  Object.assign(srv, { time_range: i, forcex_flag: (tu != srv.time_units) ? 1 : 0, time_units: tu, xmin: xmin * nf, xmax: xmax * nf });
}

// ---- environment ----------------------------------------------------------------------------------------------------
const BASE = { xmin: 0, xmax: 20, single_btn: 0, auto_flag: 0, forcex_flag: 0, time_units: 1, time_range: 3, trig_mode: 0,
  trig_source: 0, trig_edge: 0, trig_delay: 0, trig_level: 0, dummy_trig_sw: 0, dummy_oscA_sw: 1, dummy_oscB_sw: 2,
  dummy_osc_raw_mode: 0, gui_xmin: 0, gui_xmax: 20, gui_reset_y_range: 2 };

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
        srvWindow(srv, q);
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
  code += 'var params = {original:null, local:null, storage: []};\nvar post_max_bytes = 600;\nvar post_inflight = 0, last_post_end = 0;\n' +
          'var set_trigger_val = false, plot_time_units = null, update_timer = null, datasets = [];\n';
  const ct = (js.match(/config_params_txts = [\s\S]*?;\n/) || [''])[0];
  code += 'var ' + ct + 'var config_params_keys = config_params_txts.split(",");\n';
  code += ['unsentChanges', 'loadParams', 'updateTimeUnits', 'isParamChanged', 'splitParams', 'postParamsChunks',
           'sendParams', 'postEnd', 'sendableValue', 'isSendable', 'hasRealChange', 'doGetData', 'runStop', 'singleUpdate',
           'onDropdownChange', 'config_storage_read', 'config_load_storage', 'resetZoom', 'resetZoomY', 'scopeSetXWindow',
           'timeUnitFactor'].map(fnSrc).join('\n');
  code += '\n' + blockSrc('RESET ZOOM') + '\n';
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
