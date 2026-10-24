#!/usr/bin/env node
// rp_dummy2 2.0.1 (CP6.1): units of the trigger level in the web page, Raw Mode in ADC counts.
// Before, the page converted the level with the volts scale also in Raw Mode and limited it to +-gui_reset_y_range/2
// (+-1): a level of 100 counts was sent as 100 (then taken as 100 V by the controller: threshold 8191) and shown as 1.
// Real functions of index.html: the [RAW TRIGGER] block (trigRaw, trigLevelScale, pageToTrigLevel, trigLevelToPage,
// trigLevelLimits, trigLevelForRaw) and roundLevel(); the [CONFIG KEYS] block (configKnownKeys(): a config of an
// older version, e.g. with dummy_osc_lockin_mode, no longer makes the controller log "not found"); plus static checks that every place of the page that converts
// the level uses them, and of the Y limits of src/main.c for the auto-set in Raw Mode.
//
// Usage:  node tests/raw_trigger_sim.js [index.html]   (default ../dummy/index.html; exit code 1 on failure)
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path');

const args = process.argv.slice(2);
const file = args.find(a => !a.startsWith('--')) || path.join(__dirname, '..', 'dummy', 'index.html');
const html = fs.readFileSync(file, 'utf8');
const js = [...html.matchAll(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');
const mainc = fs.readFileSync(path.join(path.dirname(file), 'src', 'main.c'), 'utf8');

function braceFrom(i) {
  let d = 0;
  for(let k = js.indexOf('{', i); k < js.length; k++) {
    if(js[k] == '{') d++;
    else if(js[k] == '}' && --d == 0) return js.slice(i, k + 1);
  }
  return '';
}
function fnSrc(name) { const i = js.indexOf('function ' + name + '('); return i < 0 ? '' : braceFrom(i); }
function blockSrc(tag) {
  const a = js.indexOf('// [' + tag + ' BEGIN]'), b = js.indexOf('// [' + tag + ' END]');
  return (a < 0 || b < 0) ? '' : js.slice(a, b);
}

const ctx = {};
vm.createContext(ctx);
const debug = [];
ctx.console = { debug: m => debug.push(m), log: () => {} };
vm.runInContext(blockSrc('RAW TRIGGER') + '\n' + fnSrc('roundLevel') + '\n' + blockSrc('CONFIG KEYS') +
                '\nthis.__get = function(e){return eval(e)};', ctx);
// (a missing function, e.g. in the index.html of 2.0.0, gives NaN: its checks fail instead of stopping the test)
const F = n => { try { return ctx.__get(n); } catch(e) { return () => NaN; } };

let fails = 0, n = 0;
function check(name, ok, info) {
  n++;
  if(!ok) fails++;
  console.log((ok ? 'ok   ' : 'FAIL ') + name + (info !== undefined ? '  [' + info + ']' : ''));
}
const near = (a, b, e) => Math.abs(a - b) <= (e || 1e-9);

// typical server values (LV jumpers, probe x1: scale 1, full scale ~1.08 V)
const V = { trig_source: 0, scale_ch1: 1, scale_ch2: 1, gui_reset_y_range: 2.167, dummy_osc_raw_mode: 0 };
const R = Object.assign({}, V, { dummy_osc_raw_mode: 1 });
const V10 = Object.assign({}, V, { scale_ch1: 10, scale_ch2: 1, gui_reset_y_range: 21.67 });   // probe x10 on CH1

// 1. volts mode: unchanged (level shown = trig_level * scale of the trigger channel)
check('1.1 volts: page 0.25 V -> trig_level 0.25 -> page 0.25', near(F('pageToTrigLevel')(0.25, V), 0.25) && near(F('trigLevelToPage')(0.25, V), 0.25));
check('1.2 volts, probe x10 on CH1: page 2.5 V -> trig_level 0.25', near(F('pageToTrigLevel')(2.5, V10), 0.25), F('pageToTrigLevel')(2.5, V10));
check('1.3 volts, probe x10 on CH1, source CH2: scale of CH2 (1)', near(F('pageToTrigLevel')(2.5, Object.assign({}, V10, { trig_source: 1 })), 2.5));
check('1.4 volts: limits +-gui_reset_y_range/2', JSON.stringify(F('trigLevelLimits')(V)) == JSON.stringify([-1.0835, 1.0835]), F('trigLevelLimits')(V));
check('1.5 volts: the limits of the server values (2nd argument) win', F('trigLevelLimits')(V, V10)[1] == 10.835);

// 2. Raw Mode: counts as they are (whatever the probe), integer, limits of 14 bits
check('2.1 raw: page 100 counts -> trig_level 100 -> page 100 (before: 100 / scale, limited to +-1)',
      F('pageToTrigLevel')(100, R) === 100 && F('trigLevelToPage')(100, R) === 100);
check('2.2 raw: no probe scale (probe x10 on CH1)', F('pageToTrigLevel')(100, Object.assign({}, V10, { dummy_osc_raw_mode: 1 })) === 100);
check('2.3 raw: rounded to whole counts', F('pageToTrigLevel')(100.4, R) === 100 && F('pageToTrigLevel')(-3.6, R) === -4);
check('2.4 raw: limits -8192..8191 (before: +-1)', JSON.stringify(F('trigLevelLimits')(R, V)) == JSON.stringify([-8192, 8191]));
check('2.5 raw: the level box shows the counts', F('roundLevel')(F('trigLevelToPage')(-3, R)) === -3);

// 3. switching Raw Mode converts the level (same trigger point): counts = V_norm * 8192 / full scale
const fs1 = V.gui_reset_y_range / 2;
const c = F('trigLevelForRaw')(0.1, V, true);
check('3.1 volts -> raw: 0.1 V -> ' + c + ' counts', c === Math.round(0.1 * 8192 / fs1), c);
check('3.2 raw -> volts: back to ~0.1 V', near(F('trigLevelForRaw')(c, R, false), 0.1, 1e-4), F('trigLevelForRaw')(c, R, false));
check('3.3 probe x10: the same counts for the same normalized level (full scale at gain 1 = 21.67/2/10)',
      F('trigLevelForRaw')(0.1, V10, true) === c, F('trigLevelForRaw')(0.1, V10, true));
check('3.4 volts -> raw beyond the full scale: 8191 / -8192', F('trigLevelForRaw')(5, V, true) === 8191 && F('trigLevelForRaw')(-5, V, true) === -8192);
check('3.5 bad values: 0', F('trigLevelForRaw')(NaN, V, true) === 0 && F('trigLevelForRaw')(0.1, {}, true) === 819);

// 4. static: every conversion of the page uses the block; the Raw button converts; limits of the controller
check('4.1 no "trig_level * scale" / "/ scale" left in the page', !/trig_level\s*\*\s*scale|\)\s*\/\s*scale;|tlev\s*\/\s*scale/.test(js));
check('4.2 updateTriggerSlider() takes the limits from trigLevelLimits()', /trigLevelLimits\(/.test(fnSrc('updateTriggerSlider')));
check('4.3 the Raw Mode button converts trig_level', /dummy_osc_raw_mode[\s\S]{0,200}trigLevelForRaw\(/.test(js));
const lim = name => (mainc.match(new RegExp('"' + name + '",\\s*\\d+,\\s*\\d+,\\s*\\d+,\\s*(-?\\d+),\\s*\\+?(-?\\d+)')) || []).slice(1).map(Number);
check('4.4 src/main.c: min_y/max_y(_norm) limits +-20000 (auto-set in Raw: +-8192 * 1.2 was clipped to +-1000)',
      ['min_y', 'max_y', 'min_y_norm', 'max_y_norm'].every(k => lim(k)[0] <= -9831 && lim(k)[1] >= 9831), ['min_y', 'max_y_norm'].map(lim));
check('4.5 src/main.c: Y range of the auto-set not scaled in Raw Mode', /DUMMY_OSC_RAW_MODE\][\s\S]{0,40}scale = 1/.test(mainc));

// 6. CP6.1 retest O1-O3: units label, levels limited in the page, Y range when Raw Mode is switched
check('6.1 raw: a level beyond the range is limited before sending (9000 -> 8191, -9000 -> -8192)',
      F('pageToTrigLevel')(9000, R) === 8191 && F('pageToTrigLevel')(-9000, R) === -8192);
check('6.2 volts: limited to +-full scale of the server values (5 V -> 1.0835)', near(F('pageToTrigLevel')(5, V, V), 1.0835));
check('6.3 volts, probe x10: 50 V -> limit 10.835 V -> trig_level 1.0835', near(F('pageToTrigLevel')(50, V10, V10), 1.0835));
{
  const y = F('yRangeForRaw')(-9830, 9830, V, false);
  check('6.4 raw -> volts: Y +-9830 counts -> +-' + (y && y[1].toFixed(3)) + ' V (before: stayed +-9000 "V")',
        y && near(y[1], 9830 * fs1 / 8192, 1e-9) && near(y[0], -y[1]), JSON.stringify(y));
  const y2 = F('yRangeForRaw')(y[0], y[1], V, true);
  check('6.5 volts -> raw: back to +-9830', y2 && near(y2[1], 9830, 1e-6), JSON.stringify(y2));
  const y3 = F('yRangeForRaw')(-5, 5, V10, true);
  check('6.6 probe x10: +-5 V shown -> +-' + (y3 && y3[1].toFixed(1)) + ' counts (full scale 10.835 V = 8192)',
        y3 && near(y3[1], 5 * 8192 / 10.835, 1e-6), JSON.stringify(y3));
  check('6.7 bad axis: default range', JSON.stringify(F('yRangeForRaw')(NaN, 1, V, false)) == '[-1,1]');
}
check('6.8 the Level units label follows Raw Mode (counts / V)', /trig_lev_units'\)\.text\(set_raw \? 'counts' : 'V'\)/.test(fnSrc('display_update')));
check('6.9 switching Raw Mode converts the Y axis (yRangeForRaw), no delayed autoscale with the old trace',
      /yRangeForRaw\(/.test(fnSrc('display_update')) && !/setTimeout\(autoscaleY/.test(js));
check('6.10 the level box and the slider drag pass the server limits', (js.match(/pageToTrigLevel\([^;]*params\.original\)/g) || []).length >= 2);

// 5. config load (CP6.1 O2): keys unknown to this App are not sent (the controller logged "not found")
{
  const keys = ['trig_level', 'dummy_osc_raw_mode', 'dummy_oscA_sw'], keep = ['meas_min_ch1'];
  const data = { trig_level: 3, dummy_osc_raw_mode: 1, dummy_oscA_sw: 5, meas_min_ch1: 0, numberA: 7,
                 dummy_osc_lockin_mode: 0, lock_ctrl_aux_pidA_enable_ctrl: 0 };
  const out = F('configKnownKeys')(data, keys, keep, { numberA: 0 });
  check('5.1 known keys kept (saved params, display keys, params of the controller such as an app.ini control)',
        out && out.trig_level === 3 && out.dummy_osc_raw_mode === 1 && out.dummy_oscA_sw === 5 && out.meas_min_ch1 === 0 &&
        out.numberA === 7, JSON.stringify(out));
  check('5.2 dummy_osc_lockin_mode (removed in 2.0.0) and lock-in keys dropped',
        out && !('dummy_osc_lockin_mode' in out) && !('lock_ctrl_aux_pidA_enable_ctrl' in out));
  check('5.3 debug note with the dropped keys', debug.some(m => /dummy_osc_lockin_mode, lock_ctrl_aux_pidA_enable_ctrl/.test(m)), debug[0]);
  check('5.4 config_load_storage() uses it', /configKnownKeys\(/.test(fnSrc('config_load_storage')) && /loadParams\(cfg\)/.test(fnSrc('config_load_storage')));
}

console.log(fails ? 'FAILED ' + fails + ' (' + (n - fails) + '/' + n + ')' : 'ALL OK (' + n + '/' + n + ')');
process.exit(fails ? 1 : 0);
