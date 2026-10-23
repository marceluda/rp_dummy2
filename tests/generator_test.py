#!/usr/bin/env python3
"""
Host tests of the generator (CP4_bis): new_project.py and the App config_tool.py, without board nor Vivado.

  python3 tests/generator_test.py [-v]      (also run by make -C tests)

  Logo        logo_set_name() (flowed text -> <text>, escaping, plain <text>, missing id), make_logo() with each tool
              found on this PC (cairosvg, rsvg-convert, inkscape: 100x100 PNG, icon = logo), a fake cairosvg module
              (the call of the cairosvg path), the fallback without tools (warning with what to install, generic logo),
              new_project.py with --icon-tool and without any tool (PATH without renderers).
  No DEBUG    a generated App has no icon_DEBUG/RELOAD, no _dbg/_rld controllers or targets.
  config_tool modules of dummy.v -> tcl (2020.1 and 2015.2), unknown module warning; combo box texts from a muxer
              (+ [names], labels); c/names_dic.txt; app.ini changes (added, removed with the user code that still uses
              it, address moves, rename guess, --rename).
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # rp_dummy2/
TEMPLATE = os.path.join(ROOT, 'dummy')
sys.path.insert(0, TEMPLATE)
sys.dont_write_bytecode = True
import config_lib as cl     # noqa: E402

GENERIC_SVG = os.path.join(ROOT, 'resources', 'logo.svg')
GENERIC_PNG = os.path.join(ROOT, 'resources', 'logo.png')
TOOLS = [ t for t in cl.LOGO_TOOLS if cl._logo_tool_available(t) ]


def run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def read(path):
    with open(path, encoding='utf-8', errors='replace') as fd:
        return fd.read()


def same_file(a, b):
    with open(a, 'rb') as fa, open(b, 'rb') as fb:
        return fa.read() == fb.read()


class Logo(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='logo_')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_set_name_flowed_text(self):
        svg = read(GENERIC_SVG)
        self.assertIn('APP NAME LONG', svg)
        out = cl.logo_set_name(svg, 'my_app')
        self.assertNotIn('APP NAME LONG', out)
        self.assertNotIn('<flowRoot', out)                         # converted: cairosvg / librsvg do not draw it
        m = re.search(r'<text[^>]*id="AppName"[^>]*>([^<]*)</text>', out)
        self.assertTrue(m and m.group(1) == 'my_app')
        self.assertIn('text-anchor:middle', m.group(0))
        # a long name gets a smaller font, the placeholder keeps its size
        fs = lambda t: float(re.search(r'id="AppName"[^>]*font-size:([\d.]+)px', cl.logo_set_name(svg, t)).group(1))
        self.assertAlmostEqual(fs('APP NAME LONG'), 6.81902, places=3)
        self.assertLess(fs('a_very_long_application_name_2026'), fs('my_app'))
        # escaping and idempotence (a second call replaces the name again)
        out2 = cl.logo_set_name(out, 'a+b<c')
        self.assertIn('>a+b&lt;c</text>', out2)

    def test_long_names(self):
        """O1: a minimum font size; longer names in two lines; what still does not fit is cut with an ellipsis"""
        svg = read(GENERIC_SVG)
        fs0 = 6.81902
        out = cl.logo_set_name(svg, 'a_very_long_application_name_2026')
        el = re.search(r'<text[^>]*id="AppName".*?</text>', out, flags=re.S).group(0)
        spans = re.findall(r'<tspan[^>]*>([^<]*)</tspan>', el)
        self.assertEqual(len(spans), 2)
        self.assertEqual(''.join(spans), 'a_very_long_application_name_2026')      # split, nothing lost
        fs = float(re.search(r'font-size:([\d.]+)px', el).group(1))
        self.assertGreaterEqual(fs, cl.LOGO_MIN_FONT * fs0 - 1e-6)
        huge = 'W' * 60
        el = re.search(r'<text[^>]*id="AppName".*?</text>', cl.logo_set_name(svg, huge), flags=re.S).group(0)
        spans = re.findall(r'<tspan[^>]*>([^<]*)</tspan>', el)
        self.assertEqual(len(spans), 2)
        self.assertTrue(all(y.endswith('\u2026') for y in spans))
        self.assertGreaterEqual(float(re.search(r'font-size:([\d.]+)px', el).group(1)), cl.LOGO_MIN_FONT * fs0 - 1e-6)
        # a name that fits stays in one line at the placeholder size
        self.assertNotIn('<tspan', re.search(r'<text[^>]*id="AppName".*?</text>', cl.logo_set_name(svg, 'my_app'),
                                             flags=re.S).group(0))

    def test_set_name_text_element(self):
        svg = '<svg><text id="AppName" x="1"><tspan id="t1">OLD NAME</tspan></text></svg>'
        self.assertEqual(cl.logo_set_name(svg, 'new'), '<svg><text id="AppName" x="1"><tspan id="t1">new</tspan></text></svg>')
        self.assertEqual(cl.logo_set_name('<svg><text id="AppName">x</text></svg>', 'y'), '<svg><text id="AppName">y</text></svg>')
        with self.assertRaises(ValueError):
            cl.logo_set_name('<svg><text id="Other">x</text></svg>', 'y')

    def _make(self, tool, name='test_app'):
        svg, png, icon = (os.path.join(self.tmp, y) for y in ('logo.svg', 'logo.png', 'icon.png'))
        shutil.copy(GENERIC_SVG, svg)
        shutil.copy(GENERIC_PNG, png)
        used, warns = cl.make_logo(svg, svg, png, name, icon_out=icon, tool=tool)
        return used, warns, svg, png, icon

    def test_each_available_tool(self):
        if not TOOLS:
            self.skipTest('no SVG renderer on this PC')
        for tool in TOOLS:
            with self.subTest(tool=tool):
                used, warns, svg, png, icon = self._make(tool)
                self.assertEqual(used, tool, warns)
                self.assertEqual(warns, [])
                self.assertEqual(cl.png_size(png), (100, 100))
                self.assertTrue(same_file(png, icon))
                self.assertFalse(same_file(png, GENERIC_PNG))
                self.assertIn('>test_app</text>', read(svg))

    def test_auto_takes_the_first_available(self):
        if not TOOLS:
            self.skipTest('no SVG renderer on this PC')
        used, warns, *_ = self._make('auto')
        self.assertEqual(used, TOOLS[0], warns)

    def test_fake_cairosvg_module(self):
        """The cairosvg path (module not installed here): a stand-in module that renders with rsvg-convert"""
        if not shutil.which('rsvg-convert'):
            self.skipTest('rsvg-convert not available for the stand-in cairosvg')
        calls = []

        def svg2png(url=None, write_to=None, output_width=None, output_height=None, **kw):
            calls.append((url, write_to, output_width, output_height))
            subprocess.run(['rsvg-convert', '-w', str(output_width), '-h', str(output_height), '-a', url, '-o', write_to],
                           check=True)
        fake = types.ModuleType('cairosvg')
        fake.svg2png = svg2png
        saved = sys.modules.get('cairosvg')
        sys.modules['cairosvg'] = fake
        try:
            used, warns, svg, png, icon = self._make('auto')
        finally:
            if saved is None:
                del sys.modules['cairosvg']
            else:
                sys.modules['cairosvg'] = saved
        self.assertEqual(used, 'cairosvg', warns)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2:], (100, 100))
        self.assertEqual(cl.png_size(png), (100, 100))

    def test_fallback_without_tools(self):
        saved = cl._logo_tool_available
        cl._logo_tool_available = lambda t: False
        try:
            used, warns, svg, png, icon = self._make('auto')
        finally:
            cl._logo_tool_available = saved
        self.assertIsNone(used)
        txt = ' '.join(warns)
        for hint in ('pip install cairosvg', 'librsvg2-bin', 'inkscape'):
            self.assertIn(hint, txt)
        self.assertTrue(same_file(png, GENERIC_PNG))                # the generic logo is kept ...
        self.assertTrue(same_file(icon, GENERIC_PNG))               # ... and used as icon
        self.assertIn('>test_app</text>', read(svg))                # the SVG still gets the name

    def test_failing_tool_falls_back_to_next(self):
        if len(TOOLS) < 1:
            self.skipTest('no SVG renderer on this PC')
        saved_av, saved_r = cl._logo_tool_available, cl._logo_render_with
        cl._logo_tool_available = lambda t: True
        cl._logo_render_with = lambda t, a, b, s: ('boom' if t != TOOLS[-1] else saved_r(t, a, b, s))
        try:
            used, warns, *_ = self._make('auto')
        finally:
            cl._logo_tool_available, cl._logo_render_with = saved_av, saved_r
        self.assertEqual(used, TOOLS[-1])
        self.assertTrue(any('failed (boom)' in w for w in warns))


class Generated(unittest.TestCase):
    """Apps made by new_project.py in a temporary folder"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='gen_')
        cls.ini = os.path.join(ROOT, 'config.ini')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def gen(self, name, *opts, env=None):
        r = run([sys.executable, '-B', os.path.join(ROOT, 'new_project.py'), '-c', self.ini, '-o', self.tmp, '-f', *opts, name],
                env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return os.path.join(self.tmp, 'rp_' + name), r.stdout + r.stderr

    def tool(self, app, *args):
        return run([sys.executable, '-B', os.path.join(app, 'config_tool.py'), *args])

    # -- logo through new_project.py
    def test_new_project_logo_each_tool(self):
        for tool in TOOLS:
            with self.subTest(tool=tool):
                prj, out = self.gen('logo_' + tool.replace('-', '_'), '--icon-tool', tool)
                app = os.path.join(prj, 'logo_' + tool.replace('-', '_'))
                self.assertIn(f'rendered with {tool}', out)
                self.assertEqual(cl.png_size(os.path.join(prj, 'resources', 'logo.png')), (100, 100))
                self.assertTrue(same_file(os.path.join(prj, 'resources', 'logo.png'), os.path.join(app, 'info', 'icon.png')))
                self.assertIn('>logo_' + tool.replace('-', '_') + '</text>', read(os.path.join(prj, 'resources', 'logo.svg')))

    def test_new_project_without_renderers(self):
        empty = os.path.join(self.tmp, 'empty_path')
        os.makedirs(empty, exist_ok=True)
        env = dict(os.environ, PATH=empty)        # no rsvg-convert / inkscape (and cairosvg is not installed)
        if TOOLS and TOOLS[0] == 'cairosvg':
            self.skipTest('cairosvg installed: PATH does not hide it')
        prj, out = self.gen('nologo', env=env)
        self.assertIn('WARNING: no SVG renderer found', out)
        self.assertIn('pip install cairosvg', out)
        self.assertTrue(same_file(os.path.join(prj, 'resources', 'logo.png'), GENERIC_PNG))
        self.assertTrue(same_file(os.path.join(prj, 'nologo', 'info', 'icon.png'), GENERIC_PNG))

    def test_no_icon_option(self):
        prj, out = self.gen('noicon', '--no-icon')
        self.assertTrue(same_file(os.path.join(prj, 'noicon', 'info', 'icon.png'), GENERIC_PNG))

    # -- no DEBUG / RELOAD
    def test_no_debug_reload(self):
        prj, out = self.gen('nodbg', '--no-icon')
        app = os.path.join(prj, 'nodbg')
        self.assertEqual(sorted(os.listdir(os.path.join(app, 'info'))), ['icon.png', 'info.json'])
        for fn in ('Makefile', os.path.join('src', 'Makefile'), 'upload_app.sh', 'fpga.sh', 'nginx.conf'):
            txt = read(os.path.join(app, fn))
            self.assertIsNone(re.search(r'_DEBUG|_RELOAD|_dbg|_rld|obj_dbg|obj_rld|target_dbg|target_rld|RELOAD', txt), fn)
        self.assertNotIn('RELOAD', read(os.path.join(app, 'src', 'main.c')))
        self.assertIsNone(re.search(r'_dbg|_rld', read(os.path.join(prj, '.gitignore'))))
        r = run(['make', '-n', '-C', app, 'zip', 'tar', 'BUILD_NUMBER=7'])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('DEBUG', r.stdout)
        self.assertNotIn('RELOAD', r.stdout)

    # -- config_tool.py tasks
    def test_config_tool_tasks(self):
        prj, out = self.gen('cfgt', '--no-icon')
        app = os.path.join(prj, 'cfgt')
        dv = os.path.join(app, 'fpga', 'prj', 'v0.94', 'rtl', 'dummy.v')
        tcl20 = os.path.join(app, 'fpga', 'red_pitaya_vivado_Z10.tcl')
        tcl15 = os.path.join(app, 'fpga_eco1', 'red_pitaya_vivado.tcl')
        names = os.path.join(app, 'c', 'names_dic.txt')

        # generated App: the modules of the template dummy.v in the tcl, names_dic with every combo
        auto = lambda f: re.findall(r'dummy/(\w+\.s?v)\s*$', read(f).split('# Automatically added dummy modules')[1]
                                    .split('# End of automatic part')[0], flags=re.M)
        self.assertEqual(auto(tcl20), ['aDACdecoder.v', 'muxer4.v', 'muxer_reg4.v', 'muxer_reg5.v', 'pipe_mult.v'])
        self.assertEqual(auto(tcl15), auto(tcl20))
        nd = read(names)
        self.assertRegex(nd, r'(?m)^oscA_sw\s+0x000\s+1 in1$')
        self.assertRegex(nd, r'(?m)^trig_sw\s+0x00C\s+1 Pin$')
        self.assertRegex(nd, r'(?m)^comboB\s+0x104\s+3 fast$')          # options of the .ini
        self.assertRegex(nd, r'(?m)^comboA\s+0x100\s+15 15$')           # numbers
        self.assertNotIn('# read_ctrl', nd)                              # O3: no <select> -> not listed
        self.assertIsNone(re.search(r'(?m)^slow_out[12]_sw ', nd))       # O5: muxers disabled in dummy.v
        self.assertEqual(len(re.findall(r'(?m)^oscA_sw ', nd)), 32)      # O4: the 32 inputs of the scope muxer
        self.assertIn('0 (no muxer in dummy.v)', read(os.path.join(app, 'index.html')))
        r = self.tool(app, '-a')
        self.assertNotIn('dummy_comboB: select controller should be set by hand', r.stdout)   # O6 (options)
        self.assertNotIn('dummy_comboA: select controller should be set by hand', r.stdout)   # O6 (numbers)
        # O2: -l alone does only the logo; without renderer it says that logo.png is kept
        r = self.tool(app, '-l')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('guess_control_type', r.stdout)
        self.assertIn('do_logo', r.stdout)
        empty = os.path.join(self.tmp, 'empty_path_l')
        os.makedirs(empty, exist_ok=True)
        if not (TOOLS and TOOLS[0] == 'cairosvg'):
            r = run([sys.executable, '-B', os.path.join(app, 'config_tool.py'), '-l'], env=dict(os.environ, PATH=empty))
            self.assertIn('logo.png is not changed and is used as icon', r.stdout)
            self.assertTrue(same_file(os.path.join(prj, 'resources', 'logo.png'), os.path.join(app, 'info', 'icon.png')))

        # user logic: a counter and a muxer selected by comboA; [names] for a wire
        s = read(dv)
        anchor = '    // NOW CONNECT CABLES AND MODULES\n    // ' + '-' * 89 + '\n'
        self.assertIn(anchor, s)
        s = s.replace(anchor, anchor + """
    wire [14-1:0] cnt14, mux_out;
    UniversalCounter #(.N(14)) i_cnt ( .clk(clk), .reset(rst), .en(checkboxA), .up(1'b1), .syn_clr(1'b0),
                                       .load(1'b0), .d(14'd0), .max_tick(), .min_tick(), .q(cnt14) );
    muxer3 #(.RES(14)) i_user_mux ( .sel(comboA[2:0]), .in0(14'b0), .in1(numberA), .in2(numberB), .in3(cnt14),
                                    .in4(in1), .in5(14'b0), .in6(14'b0), .in7(14'b0), .out(mux_out) );
    muxer3 #(.RES(14)) i_user_mux2 ( .sel(comboA), .in0(14'b0), .in1(numberA), .in2(numberB), .in3(cnt14),
                                     .in4(in1), .in5(14'b0), .in6(14'b0), .in7(14'b0), .out() );
    /* my_unknown_module i_never ( .a(b) );  (a comment: not an instance) */
    assign monitorA = mux_out;
    assign monitorB = numberB;
    assign monitorC = 27'd0;
    assign monitorD = 27'd0;
""")
        with open(dv, 'w') as fd:
            fd.write(s)
        with open(os.path.join(app, 'app.ini'), 'a') as fd:
            fd.write('\n[names]\ncnt14 = Counter\n')
        r = self.tool(app, '-a')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('UniversalCounter.v', auto(tcl20))
        self.assertIn('muxer3.v', auto(tcl15))
        self.assertNotIn('WARNING: module', r.stdout)
        sel = re.search(r'<select id="dummy_comboA"[^>]*>(.*?)</select>', read(os.path.join(app, 'index.html')), flags=re.S).group(1)
        opts = re.findall(r'<option[^>]*value="(\d+)"[^>]*>([^<]*)</option>', sel)
        self.assertEqual(opts[:5], [('0', '0'), ('1', 'Number A'), ('2', 'Number B'), ('3', 'Counter'), ('4', 'in1')])
        self.assertEqual(len(opts), 8)                                   # muxer3: 8 inputs (comboA has 4 bits)
        self.assertRegex(read(names), r'(?m)^comboA\s+0x100\s+3 Counter$')

        # unknown module and a module that clashes with the RedPitaya design
        s = read(dv).replace('    assign monitorA = mux_out;', '    my_missing_mod #(.W(2)) i_x ( .a(clk) );\n    assign monitorA = mux_out;')
        with open(dv, 'w') as fd:
            fd.write(s)
        with open(os.path.join(app, 'fpga', 'prj', 'v0.94', 'rtl', 'dummy', 'my_debounce.v'), 'w') as fd:
            fd.write('module debounce (input clk); endmodule\n')
        r = self.tool(app, '-t')
        self.assertIn('WARNING: module my_missing_mod (instantiated in dummy.v) not found', r.stdout)
        self.assertIn('WARNING: module debounce of dummy/my_debounce.v has the name of a module of the RedPitaya design', r.stdout)
        self.assertNotIn('my_unknown_module', r.stdout)
        self.assertNotIn('my_debounce.v', auto(tcl20))                    # not instantiated: not read
        os.remove(os.path.join(app, 'fpga', 'prj', 'v0.94', 'rtl', 'dummy', 'my_debounce.v'))
        with open(dv, 'w') as fd:
            fd.write(s.replace('    my_missing_mod #(.W(2)) i_x ( .a(clk) );\n', ''))

        # app.ini: numberB removed, monitorD renamed to monitorE, numberC added
        ini = read(os.path.join(app, 'app.ini'))
        ini = re.sub(r'(?ms)^\[numberB\]\n.*?(?=^\[)', '', ini, count=1)
        ini = re.sub(r'(?m)^\[monitorD\]', '[monitorE]', ini)
        ini = re.sub(r'(?m)^\[names\]', '[numberC]\ntype = number\nlabel = Number C\nbits_number = 10\n\n[names]', ini)
        with open(os.path.join(app, 'app.ini'), 'w') as fd:
            fd.write(ini)
        r = self.tool(app, '-a')
        o = r.stdout
        self.assertEqual(r.returncode, 0, o + r.stderr)
        self.assertRegex(o, r'added\s+: numberC')
        self.assertRegex(o, r'removed\s+: numberB\s+WARNING')
        self.assertRegex(o, r'address\s+: checkboxA 0x110 -> 0x10C')
        self.assertIn('renamed? : monitorD -> monitorE', o)
        self.assertRegex(o, r'WARNING: fpga/prj/v0.94/rtl/dummy.v:\d+: uses a register removed from app.ini: .*numberB')
        self.assertRegex(o, r'WARNING: fpga/prj/v0.94/rtl/dummy.v:\d+: uses a register removed from app.ini: assign monitorD')
        self.assertNotRegex(read(names), r'(?m)^numberB')
        # --rename: the user code follows; only numberB is still reported
        r = self.tool(app, '-a', '--rename', 'monitorD:monitorE')
        o = r.stdout
        self.assertEqual(r.returncode, 0, o + r.stderr)
        self.assertIn('assign monitorE = 27\'d0;', read(dv))
        self.assertNotIn('monitorD', read(dv))
        self.assertNotRegex(o, r'uses a register removed from app.ini: .*monitorD')
        self.assertRegex(o, r'uses a register removed from app.ini: .*numberB')
        r = self.tool(app, '-a', '--rename', 'x:numberZ')
        self.assertEqual(r.returncode, 2)
        # after fixing the user code: no warnings, and a second run changes nothing
        with open(dv, 'w') as fd:
            fd.write(read(dv).replace('.in2(numberB)', '.in2({4\'d0, numberC})').replace('monitorB = numberB', 'monitorB = numberA'))
        r = self.tool(app, '-a')
        self.assertNotIn('WARNING: fpga', r.stdout)
        snap = { os.path.join(dp, f): read(os.path.join(dp, f)) for dp, _, fs in os.walk(app) for f in fs
                 if f.endswith(('.v', '.html', '.c', '.h', '.tcl', '.txt', '.py')) }
        r = self.tool(app, '-a')
        again = { os.path.join(dp, f): read(os.path.join(dp, f)) for dp, _, fs in os.walk(app) for f in fs
                  if f.endswith(('.v', '.html', '.c', '.h', '.tcl', '.txt', '.py')) }
        self.assertEqual(snap, again)
        self.assertNotIn('Changes of app.ini', r.stdout)


if __name__ == '__main__':
    print('SVG renderers on this PC: ' + (', '.join(TOOLS) or 'none'))
    unittest.main(verbosity=2 if '-v' in sys.argv else 1)
