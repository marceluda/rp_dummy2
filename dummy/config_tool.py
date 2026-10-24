#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config_tool.py: regenerates the automatic parts ("docks") of the App sources from app.ini.

The registers of the dummy FPGA module are the fixed ones of the template (defined below) plus one per
control of app.ini. From them this script writes:

  -v  fpga/prj/v0.94/rtl/dummy.v   reg/wire declarations, bus write/read logic, list of the added registers
  -m  src/*.c, src/*.h         C controller: register struct, parameters table, FPGA <-> parameters copy
      c/dummy.c, c/app_regs.h  remote control tools: register table, offsets (and c/dummy.txt)
  -w  index.html               panels of the controls and monitors, JS lists of controls, LOADPARAMS
  -p  py/hugo.py               register list for remote access from Python
  -t  fpga/*.tcl, fpga_eco1/*.tcl   files of fpga/prj/v0.94/rtl/dummy/ with the modules instantiated in dummy.v
                               (recursively) for the Vivado 2020.1 and 2015.2 designs; reports unused files and
                               modules that are found nowhere
  -n  c/names_dic.txt            texts of the values of every combo box (register, address, value, text)
  -a  all of them (-v -m -w -p -t -n)
  -l  ../resources/logo.svg, logo.png and info/icon.png: App name on the logo, rendered to 100x100 PNG
      (cairosvg, rsvg-convert or inkscape; not part of -a)

Run it again after editing app.ini (new controls, labels, widths...) or after instantiating in dummy.v a module of
fpga/prj/v0.94/rtl/dummy/. The user logic in dummy.v (outside the docks) is not touched.

Changes of app.ini: before writing, the registers of the last generation (ADDED REGS block of dummy.v) are compared
with app.ini and the controls added, removed, changed or moved to another address are listed. After writing, the
removed registers still used in the user code (dummy.v, index.html, src/, py/) are reported with their line: fix
them, or rename them with --rename OLD:NEW (when a control was renamed in app.ini).

Combo boxes: the options of app.ini; otherwise, if the register is the .sel of a muxer of dummy.v, the names of the
muxer inputs (text from app.ini [names], or the label of the control with that name, or the wire name); otherwise
the numbers. The template selects (oscA_sw, out1_sw...) take the names of their muxer inputs the same way.

Register map (app.ini [general] register_map):
  fixed  (default) template registers at 0x000-0x0FC, controls of app.ini from 0x100 in order
  legacy           controls right after the template registers, read_ctrl last (old rp_dummy layout)
"""

import os
import sys
import argparse
import re
from glob import glob

from config_lib import *


#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# App folder and app.ini

if '__file__' in globals():
    folder = os.path.dirname(os.path.realpath(__file__))
else:
    folder = 'rp_dummy2/dummy'

os.chdir(folder)
AppName = os.path.basename(folder)

if __name__ == '__main__':

    parser = argparse.ArgumentParser(
                description='Regenerate the automatic parts of the App files (web page <--> C controller <--> '
                            'FPGA registers) from app.ini.')
    parser.add_argument("-v", "--do-verilog", dest='do_verilog', action="store_true",
                        help="configure verilog files (fpga/prj/v0.94/rtl/dummy.v)")
    parser.add_argument("-m", "--do-main"   , dest='do_main'   , action="store_true",
                        help="configure C files (src/)")
    parser.add_argument("-w", "--do-html"   , dest='do_html'   , action="store_true",
                        help="configure web HTML index file")
    parser.add_argument("-p", "--do-python" , dest='do_py'     , action="store_true",
                        help="configure python scripts (py/hugo.py)")
    parser.add_argument("-t", "--do-tcl"    , dest='do_tcl'    , action="store_true",
                        help="configure TCL files of fpga/ and fpga_eco1/ (the files of fpga/prj/v0.94/rtl/dummy/ "
                             "with the modules instantiated in dummy.v)")
    parser.add_argument("-n", "--names"     , dest='do_names'  , action="store_true",
                        help="write c/names_dic.txt (texts of the values of the combo boxes)")
    parser.add_argument("-a", "--all"       , dest='do_all'    , action="store_true",
                        help="configure all the files (-v -m -w -p -t -n)")
    parser.add_argument("--rename"          , dest='rename'    , action="append", default=[], metavar='OLD:NEW',
                        help="a control was renamed in app.ini from OLD to NEW: rename it also in the user code "
                             "(dummy.v, index.html, src/) before regenerating (repeatable)")
    parser.add_argument("-l", "--logo"      , dest='do_logo'   , action="store_true",
                        help="write the App name on ../resources/logo.svg and render logo.png and info/icon.png "
                             "(not part of -a)")

    args = parser.parse_args()

    if args.do_all:
        args.do_verilog = args.do_main = args.do_html = args.do_py = args.do_tcl = args.do_names = True

    if not ( args.do_verilog or args.do_main or args.do_html or args.do_py or args.do_tcl or args.do_logo or
             args.do_names or args.rename ):
        print('nothing to do')
        parser.print_help()
        sys.exit(0)

print('Working folder: '+folder)
print('App folder    : '+AppName)

try:
    cfg = load_app_ini(os.path.join(folder, 'app.ini'))
except ValueError as e:
    print('ERROR in app.ini:\n  ' + str(e).replace('\n', '\n  '), file=sys.stderr)
    sys.exit(1)
for w in cfg.warnings:
    print('WARNING app.ini: ' + w)
print('Register map  : '+cfg.register_map)


def do_logo():
    """-l: App name on ../resources/logo.svg, rendered to ../resources/logo.png and info/icon.png"""
    print('do_logo')
    res = os.path.join('..', 'resources')
    if not os.path.isfile(os.path.join(res, 'logo.svg')):
        print(f'WARNING: {res}/logo.svg not found: logo not made')
    else:
        used, warns = make_logo(os.path.join(res, 'logo.svg'), os.path.join(res, 'logo.svg'),
                                os.path.join(res, 'logo.png'), cfg.app_name or AppName,
                                icon_out=os.path.join('info', 'icon.png'))
        for w in warns:
            print('WARNING: ' + w)
        if used:
            print(f'{res}/logo.svg, logo.png and info/icon.png written (rendered with {used})')
        else:
            print(f'{res}/logo.svg written; info/icon.png = {res}/logo.png (not rendered)')
    print('\n')


# -l alone: only the logo (no analysis of the registers and controls)
if __name__ == '__main__' and args.do_logo and not ( args.do_verilog or args.do_main or args.do_html or args.do_py or
                                                     args.do_tcl or args.do_names or args.rename ):
    do_logo()
    sys.exit(0)
print('\n')


#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# Process FPGA registers


f = fpga_registers()

# Oscilloscope
grp='scope'
f.add( name="oscA_sw"            , group=grp , val=    1, rw=True ,  nbits= 5, min_val=          0, max_val=         31, fpga_update=True , signed=False, desc="switch for muxer oscA" )
f.add( name="oscB_sw"            , group=grp , val=    2, rw=True ,  nbits= 5, min_val=          0, max_val=         31, fpga_update=True , signed=False, desc="switch for muxer oscB" )
f.add( name="osc_ctrl"           , group=grp , val=    3, rw=True ,  nbits= 2, min_val=          0, max_val=          3, fpga_update=True , signed=False, desc="oscilloscope control\n[osc2_filt_off,osc1_filt_off]" )
f.add( name="trig_sw"            , group=grp , val=    0, rw=True ,  nbits= 8, min_val=          0, max_val=        255, fpga_update=True , signed=False, desc="Select the external trigger signal" )

# Outputs
grp='outputs'
f.add( name="out1_sw"            , group=grp , val=    0, rw=True ,  nbits= 4, min_val=          0, max_val=         15, fpga_update=True , signed=False, desc="switch for muxer out1" )
f.add( name="out2_sw"            , group=grp , val=    0, rw=True ,  nbits= 4, min_val=          0, max_val=         15, fpga_update=True , signed=False, desc="switch for muxer out2" )
f.add( name="slow_out1_sw"       , group=grp , val=    0, rw=True ,  nbits= 4, min_val=          0, max_val=         15, fpga_update=True , signed=False, desc="switch for muxer slow_out1" )
f.add( name="slow_out2_sw"       , group=grp , val=    0, rw=True ,  nbits= 4, min_val=          0, max_val=         15, fpga_update=True , signed=False, desc="switch for muxer slow_out2" )
f.add( name="slow_out3_sw"       , group=grp , val=    0, rw=True ,  nbits= 4, min_val=          0, max_val=         15, fpga_update=True , signed=False, desc="switch for muxer slow_out3" )
f.add( name="slow_out4_sw"       , group=grp , val=    0, rw=True ,  nbits= 4, min_val=          0, max_val=         15, fpga_update=True , signed=False, desc="switch for muxer slow_out4" )

# Other signals
grp='inout'
f.add( name="in1"                , group=grp , val=    0, rw=False,  nbits=14, min_val=      -8192, max_val=       8191, fpga_update=True , signed=True , desc="Input signal IN1" )
f.add( name="in2"                , group=grp , val=    0, rw=False,  nbits=14, min_val=      -8192, max_val=       8191, fpga_update=True , signed=True , desc="Input signal IN2" )
f.add( name="out1"               , group=grp , val=    0, rw=False,  nbits=14, min_val=      -8192, max_val=       8191, fpga_update=True , signed=True , desc="signal for RP RF DAC Out1" )
f.add( name="out2"               , group=grp , val=    0, rw=False,  nbits=14, min_val=      -8192, max_val=       8191, fpga_update=True , signed=True , desc="signal for RP RF DAC Out2" )
f.add( name="slow_out1"          , group=grp , val=    0, rw=False,  nbits=12, min_val=          0, max_val=       4095, fpga_update=True , signed=False, desc="signal for RP slow DAC 1" )
f.add( name="slow_out2"          , group=grp , val=    0, rw=False,  nbits=12, min_val=          0, max_val=       4095, fpga_update=True , signed=False, desc="signal for RP slow DAC 2" )
f.add( name="slow_out3"          , group=grp , val=    0, rw=False,  nbits=12, min_val=          0, max_val=       4095, fpga_update=True , signed=False, desc="signal for RP slow DAC 3" )
f.add( name="slow_out4"          , group=grp , val=    0, rw=False,  nbits=12, min_val=          0, max_val=       4095, fpga_update=True , signed=False, desc="signal for RP slow DAC 4" )
f.add( name="oscA"               , group=grp , val=    0, rw=False,  nbits=14, min_val=      -8192, max_val=       8191, fpga_update=True , signed=True , desc="signal for Oscilloscope Channel A" )
f.add( name="oscB"               , group=grp , val=    0, rw=False,  nbits=14, min_val=      -8192, max_val=       8191, fpga_update=True , signed=True , desc="signal for Oscilloscope Channel B" )

def add_read_ctrl(index=None):
    f.add( name="read_ctrl"      , group='aux', val=    0, rw=True ,  nbits= 3, min_val=          0, max_val=          7, fpga_update=True , signed=False, desc="[unused,start_clk,Freeze]", index=index )
    # Streaming of the scope (c/streaming + c/stream_tcp_osc_cmd): written by the c/ tools / HTTP /dummy, not
    # parameters of the controller (a POST of the page must not stop a streaming)
    grp='streaming'
    f.add( name="stream_ip"      , group=grp  , val=    0, rw=True ,  nbits=32, min_val=          0, max_val= 4294967295, fpga_update=True , signed=False, desc="Client IP for streaming (a.b.c.d = a + b<<8 + c<<16 + d<<24)" )
    f.add( name="stream_port"    , group=grp  , val= 6000, rw=True ,  nbits=32, min_val=          0, max_val=      65535, fpga_update=True , signed=False, desc="Client TCP port for streaming" )
    f.add( name="stream_rate"    , group=grp  , val=  128, rw=True ,  nbits=17, min_val=          0, max_val=     131071, fpga_update=True , signed=False, desc="Decimation of the scope while streaming" )
    f.add( name="stream_cmd"     , group=grp  , val=    0, rw=True ,  nbits=32, min_val=          0, max_val= 4294967295, fpga_update=True , signed=False, desc="Streaming command (!= 0: streaming on)" )
    for n in ('stream_ip', 'stream_port', 'stream_rate', 'stream_cmd'):
        f[n].no_param = True

# fixed map: the template registers end at 0x0FC, so the addresses above do not depend on app.ini
if cfg.register_map == 'fixed':
    add_read_ctrl()                            # 0x050
    if f.next_index() > USER_REGS_INDEX:
        raise RuntimeError('template registers beyond 0x0FC')

# Registers of the controls of app.ini
for i, c in enumerate(cfg.controls):
    index = USER_REGS_INDEX + i if cfg.register_map == 'fixed' else None
    f.add( name=c.name, group='dummy', val=c.default, rw=not c.ro, nbits=c.nbits, min_val=c.min, max_val=c.max,
           fpga_update=not c.ro, signed=c.signed, desc=c.label, index=index )

if cfg.register_map == 'legacy':
    add_read_ctrl()


for r in f:
    if r.ro:
        r.fpga_update=False
        r.rd_copy=True    # the bus reads a registered copy (see BUS READ COPIES dock of dummy.v)

# ports of the dummy module (declared in its port list)
for i in ['in1','in2','out1','out2']:
    f[i].write_def=False


#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# Changes of app.ini since the last generation (ADDED REGS block of dummy.v)

prev_regs = read_added_regs(DUMMY_V)
changes = ini_changes(prev_regs, cfg, f)
renames = []
if __name__ == '__main__':
    for rn in args.rename:
        old, sep, new = rn.partition(':')
        if not sep or not REG_NAME_RE.match(old) or not REG_NAME_RE.match(new):
            print(f'ERROR: --rename {rn}: use --rename OLD:NEW', file=sys.stderr)
            sys.exit(2)
        if new not in [ c.name for c in cfg.controls ]:
            print(f'ERROR: --rename {rn}: app.ini has no control [{new}] (rename the section in app.ini first)', file=sys.stderr)
            sys.exit(2)
        if old in [ c.name for c in cfg.controls ]:
            print(f'ERROR: --rename {rn}: app.ini still has a control [{old}]', file=sys.stderr)
            sys.exit(2)
        renames.append((old, new))
    if prev_regs:
        if any(changes[k] for k in changes if k != 'pending'):
            print('Changes of app.ini since the last generation (ADDED REGS of dummy.v):')
        for n in changes['added']:
            print(f'    added    : {n}')
        for n in changes['removed']:
            print(f'    removed  : {n}' + ('' if n in [ o for o, _ in renames ] else
                  '   WARNING: its register and wire disappear from dummy.v, the C controller and the web page'))
        for t in changes['changed']:
            print(f'    changed  : {t}')
        for n, a, b in changes['moved']:
            print(f'    address  : {n} 0x{a:03X} -> 0x{b:03X}   WARNING: scripts that use the old address must change')
        for o, n in changes['renames']:
            if (o, n) not in renames:
                print(f'    renamed? : {o} -> {n} (same width and kind): if so, run again with --rename {o}:{n} so that '
                      f'the user code is renamed too')
        print('\n')
    for old, new in renames:
        for fn, k in rename_in_sources(old, new):
            print(f'--rename {old}:{new}: {k} replacement(s) in {fn}')



if __name__ == '__main__' and args.do_verilog:
    print('do_verilog')
    f.update_verilog_files(folder)
    update_verilog(DUMMY_V, dock=['ADDED REGS'], txt=[added_regs_doc(f, cfg.controls)+'\n'])
    print('\n')



#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# Process C code for MAIN

m = main_registers(num_base=81)

for r in f:
    if not r.no_param:
        m.add(r)

m.insert_reg("dummy_osc_ctrl",
             main_register(name="dummy_osc1_filt_off", val=1, rw=True,
                           nbits=1, group="scope",
                           min_val=0, max_val=1, signed=False,
                           desc="oscilloscope control osc1_filt_off",
                           fpga_update=True,
                           c_update='(float) ((g_dummy_reg->osc_ctrl      )& 0x01)'
                           )
             )
m.insert_reg("dummy_osc_ctrl",
             main_register(name="dummy_osc2_filt_off", val=1, rw=True,
                           nbits=1, group="scope",
                           min_val=0, max_val=1, signed=False,
                           desc="oscilloscope control osc2_filt_off",
                           fpga_update=True,
                           c_update='(float) ((g_dummy_reg->osc_ctrl >> 1 )& 0x01)'
                           )
             )

m.insert_reg("dummy_osc_ctrl",
             main_register(name="dummy_osc_raw_mode", val=0, rw=True,
                           nbits=1, group="scope",
                           min_val=0, max_val=1, signed=False,
                           desc="Set oscilloscope mode in Raw (int unit instead of Volts)",
                           fpga_update=False
                           )
             )

m.insert_reg("dummy_osc_ctrl",
             main_register(name="dummy_osc_lockin_mode", val=0, rw=True,
                           nbits=1, group="scope",
                           min_val=0, max_val=1, signed=False,
                           desc="Set oscilloscope mode in lock-in (ch1 as R [V|int], ch2 as Phase [rad])",
                           fpga_update=False
                           )
             )

m.del_reg("dummy_osc_ctrl")

m["dummy_osc1_filt_off"].fpga_reg="osc_ctrl"
m["dummy_osc2_filt_off"].fpga_reg="osc_ctrl"

r=f["osc_ctrl"]; r.c_update='(((int)params[{:s}].value)<<1) + ((int)params[{:s}].value)'.format( m["dummy_osc2_filt_off"].cdef , m["dummy_osc1_filt_off"].cdef )

m.fix_c_update(f)


if __name__ == '__main__' and args.do_main:
    print('do_main')
    m.update_c_files(folder,f)
    # Size of the mapped register area: whole 4 kB pages covering every register
    size = max(0x1000, (f.end_addr() + 0xFFF) & ~0xFFF)
    update_c_define(os.path.join('src','fpga_dummy.h'), 'DUMMY_BASE_SIZE', f'0x{size:X}')
    # remote control tools of the App (c/): register table of c/dummy, offsets for the streaming tools
    update_main(os.path.join('c','dummy.c'), dock=['DUMMYREGS'], txt=[c_regs_table(f)])
    with open(os.path.join('c','app_regs.h'), 'w') as fd:
        fd.write(c_app_regs_h(f, size))
    with open(os.path.join('c','dummy.txt'), 'w') as fd:
        fd.write(c_regs_txt(f))
    print('Writing c/dummy.c, c/app_regs.h, c/dummy.txt')
    print('\n')


#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# Process HTML controls


h = html_registers(num_base=81)

for i in m:
    h.add(i)

h.guess_control_type()

h['dummy_osc_raw_mode'   ].type   = 'button'
h['dummy_osc_lockin_mode'].type   = 'button'

h['dummy_oscA_sw'        ].type    = 'select'
h['dummy_oscB_sw'        ].type    = 'select'
h['dummy_trig_sw'        ].type    = 'select'
h['dummy_out1_sw'        ].type    = 'select'
h['dummy_out2_sw'        ].type    = 'select'
h['dummy_slow_out3_sw'   ].type    = 'select'
h['dummy_slow_out4_sw'   ].type    = 'select'

# Controls of app.ini
for c in cfg.controls:
    h['dummy_'+c.name].type = c.htype


for r in h:
    print('    '+r.name.ljust(25)+' is of type '+r.type)


# texts of the muxer inputs in the combo boxes: app.ini [names], else the label of the control with that name
mux_names = { c.name: c.label for c in cfg.controls }
mux_names.update(cfg.names)
# the combos of app.ini are configured below (options / muxer / numbers): no "set by hand" message for them
OUT_SW_RE = r'^dummy_(out\d|slow_out\d)_sw$'
h.auto_set_controls(DUMMY_V, 'dummy', mux_names, quiet=[ 'dummy_'+c.name for c in cfg.controls ] +
                                                       [ r.name for r in h if re.match(OUT_SW_RE, r.name) ])

# Output selects of the template whose muxer is not in dummy.v (e.g. slow_out1/2, disabled in the template: those
# outputs are fixed at 0): one option that says so, instead of the texts of another App. When the muxer is written
# in dummy.v, config_tool.py takes its inputs.
no_mux_outputs = []
for r in h:
    if r.type == 'select' and r.control is None and re.match(OUT_SW_RE, r.name):
        r.control = select(idd=r.name, items=['0 (no muxer in dummy.v)'], vals=[0], default=0)
        no_mux_outputs.append(r.name[len('dummy_'):])
        print(r.name + ': no muxer in dummy.v (output fixed): one option "0 (no muxer in dummy.v)"')


h['dummy_osc1_filt_off'   ].control.text='Ch1'
h['dummy_osc2_filt_off'   ].control.text='Ch2'
h['dummy_osc_raw_mode'    ].control.text = 'Raw&nbsp;Mode'
h['dummy_osc_lockin_mode' ].control.text = 'R|Phase&nbsp;Mode'

# the 32 inputs of the scope muxers (in0..in31) are all usable: none is reserved

# Controls of app.ini
for c in cfg.controls:
    hr = h['dummy_'+c.name]
    if c.htype == 'select':
        # options of app.ini; else the inputs of a muxer selected by this combo in dummy.v; else the numbers
        mux = get_muxer(DUMMY_V, c.name, mux_names)[:2**c.nbits]
        items = list(c.options) if c.options else (mux if mux else [ str(y) for y in range(2**c.nbits) ])
        hr.control = select(idd='dummy_'+c.name, items=items, vals=list(range(len(items))), default=c.default)
        c.combo_source = 'options of app.ini' if c.options else ('inputs of its muxer in dummy.v' if mux else 'numbers')
    elif c.htype in ('button', 'checkbox'):
        hr.control.text = c.label


h.set_global_configs()

# Monitors: names and widths for the refresh of their values and bars
mons = [ c for c in cfg.controls if c.type == 'monitor' ]
mon_txt   = ','.join([ 'dummy_'+c.name for c in mons ])
nbits_txt = ','.join([ ('-' if c.signed else '')+str(c.nbits) for c in mons ])
scale_txt = ','.join([ repr(float(c.scale)) if c.scale else '0' for c in mons ])
unit_txt  = ','.join([ "'"+c.unit+"'" for c in mons ])
h.html_global_configs.append(
        html_global_config( regex_start = r' *let *mon *=',
                            regex_end   = r'.*;.*',
                            text        = f"let mon = '{mon_txt}'.split(','); // Monitor controls vector" ) )
h.html_global_configs.append(
        html_global_config( regex_start = r' *let *nbits *=',
                            regex_end   = r'.*;.*',
                            text        = f"let nbits = [{nbits_txt}] ; // Monitor controls bit numbers" ) )
h.html_global_configs.append(
        html_global_config( regex_start = r' *let *mon_scale *=',
                            regex_end   = r'.*;.*',
                            text        = f"let mon_scale = [{scale_txt}] ; // Monitor display scale (0 = integer)" ) )
h.html_global_configs.append(
        html_global_config( regex_start = r' *let *mon_unit *=',
                            regex_end   = r'.*;.*',
                            text        = f"let mon_unit = [{unit_txt}] ; // Monitor display units" ) )

if __name__ == '__main__' and args.do_html:
    print('do_html')
    # panels of the controls and monitors (between the DOCK / DOCK END markers)
    update_html_dock('index.html', 'Dummy panel controls DOCK',
                     '\n'.join([ html_control_panel(c) for c in cfg.controls if c.type != 'monitor' ]))
    update_html_dock('index.html', 'Monitor PANEL DOCK',
                     '\n'.join([ html_monitor_panel(c) for c in mons ]))
    h.update_html_files(folder)
    print('\n')

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# Process Python scripts


f.set_py_global_config()


if __name__ == '__main__' and args.do_py:
    print('do_py')
    f.update_python_files(folder)
    print('\n')

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# Re-write TCL scripts

if __name__ == '__main__' and args.do_tcl:
    print('do_tcl')
    # Files of fpga/prj/v0.94/rtl/dummy/ with the modules instantiated in dummy.v (recursively)
    mods = dummy_module_files(DUMMY_V)
    print('Modules instantiated in dummy.v (and in them): ' +
          (', '.join(f'{m} ({fn})' for m, fn in mods['modules'].items()) or 'none'))
    if mods['base']:
        print('Modules of the RedPitaya design used by dummy.v: ' + ', '.join(mods['base']))
    print('Files of dummy/ not used (not added): ' + (', '.join(mods['unused']) or 'none'))
    for w in mods['warnings']:
        print('WARNING: ' + w)

    tag = ( '# Automatically added dummy modules', '# End of automatic part')
    # fpga/ (Vivado 2020.1): path relative to fpga/prj/v0.94/ ($path_rtl_prj)
    txt0 = ''.join('add_files  -fileset sources_1 $path_rtl_prj/dummy/' + y + '\n' for y in mods['files'])
    print('Writting file: fpga/red_pitaya_vivado_Z10.tcl')
    update_file_match(filename='fpga/red_pitaya_vivado_Z10.tcl', tag=tag, txt=txt0.rstrip('\n'), blank=False)
    # fpga_eco1/ (Vivado 2015.2, non-project and project scripts): path relative to fpga_eco1/ ($path_dummy)
    txt1 = '\n'
    txt2 = '\n'
    for vfile in [ '$path_dummy/dummy/'+y for y in mods['files'] ]:
        txt1 += 'read_verilog'.ljust(34) + vfile + '\n'
        txt2 += 'add_files'.ljust(34) + vfile + '\n'
    for fn, txt in (('fpga_eco1/red_pitaya_vivado.tcl', txt1), ('fpga_eco1/red_pitaya_vivado_project.tcl', txt2)):
        if os.path.isfile(fn):
            print('Writting file: ' + fn)
            update_file_match(filename=fn, tag=tag, txt=txt)
    print('\n')


if __name__ == '__main__' and args.do_names:
    print('do_names')
    entries = []
    ini_combos = { c.name: c for c in cfg.controls if c.htype == 'select' }
    for r in h:
        if r.type != 'select' or not r.name.startswith('dummy_'):
            continue
        reg = r.name[len('dummy_'):]
        if reg not in f.names:
            continue
        ctl = r.control
        if reg in no_mux_outputs:
            continue                  # no muxer in dummy.v: the output is fixed, its select has no meaning
        if isinstance(ctl, select):
            items = [ (v, t) for v, t, e in zip(ctl.vals, ctl.items, ctl.enable) if e ]
            src = getattr(ini_combos.get(reg), 'combo_source', None) or 'inputs of its muxer in dummy.v'
        else:
            items = html_select_options('index.html', r.name)
            src = 'options written in index.html'
        if not items:
            continue                  # no <select> in the page (e.g. read_ctrl, a bit mask)
        entries.append((reg, 4*f[reg].index, src, items))
    print('Writting file: c/names_dic.txt (' + ', '.join(e[0] for e in entries) + ')')
    write_names_dic(os.path.join('c', 'names_dic.txt'), cfg.app_name or AppName, entries)
    print('\n')


if __name__ == '__main__' and args.do_logo:
    do_logo()


if __name__ == '__main__' and (args.do_verilog or args.do_main or args.do_html or args.do_py) and prev_regs:
    # removed registers still used outside the generated parts (also those of earlier runs not fixed yet)
    gone = [ n for n in changes['removed'] + changes['pending'] if n not in [ o for o, _ in renames ] ]
    refs = stale_references(gone, DUMMY_V)
    for fn, i, l in refs:
        print(f'WARNING: {fn}:{i}: uses a register removed from app.ini: {l}')
    if refs:
        print('         (remove or change that code; if the control was renamed, use --rename OLD:NEW)\n')
    # remembered in the ADDED REGS block of dummy.v, so the next runs keep reporting them until they are fixed
    still = [ n for n in gone if any(re.search(rf'\b(dummy_|DUMMY_|->\s*)?{re.escape(n)}\b', l, flags=re.I) for _, _, l in refs) ]
    if args.do_verilog and (still or changes['pending']):
        update_verilog(DUMMY_V, dock=['ADDED REGS'], txt=[added_regs_doc(f, cfg.controls, removed=still)+'\n'])


if __name__ == '__main__':
    # backups written by the update functions of config_lib (<name>_YYYYMMDD_HHMMSS[_p].<ext>.bak and
    # <file>_YYYYMMDD_HHMMSS.bak); other .bak files are not touched
    import re as _re
    for bak in glob('**/*.bak', recursive=True):
        if _re.search(r'_\d{8}_\d{6}(_p)?(\.[A-Za-z]+)?\.bak$', bak):
            os.remove(bak)
    print('end')
