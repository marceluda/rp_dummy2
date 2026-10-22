#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config_tool.py: regenerates the automatic parts ("docks") of the App sources from app.ini.

The registers of the dummy FPGA module are the fixed ones of the template (defined below) plus one per
control of app.ini. From them this script writes:

  -v  fpga/rtl/dummy.v         reg/wire declarations, bus write/read logic, list of the added registers
  -m  src/*.c, src/*.h         C controller: register struct, parameters table, FPGA <-> parameters copy
  -w  index.html               panels of the controls and monitors, JS lists of controls, LOADPARAMS
  -p  py/hugo.py               register list for remote access from Python
  -t  fpga/*.tcl               Verilog sources of fpga/rtl/dummy/ to synthesize
  -a  all of them

Run it again after editing app.ini (new controls, labels, widths...) or after adding .v files to
fpga/rtl/dummy/. The user logic in dummy.v (outside the docks) is not touched.

Register map (app.ini [general] register_map):
  fixed  (default) template registers at 0x000-0x0FC, controls of app.ini from 0x100 in order
  legacy           controls right after the template registers, read_ctrl last (old rp_dummy layout)
"""

import os
import sys
import argparse
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
                        help="configure verilog files (fpga/rtl/dummy.v)")
    parser.add_argument("-m", "--do-main"   , dest='do_main'   , action="store_true",
                        help="configure C files (src/)")
    parser.add_argument("-w", "--do-html"   , dest='do_html'   , action="store_true",
                        help="configure web HTML index file")
    parser.add_argument("-p", "--do-python" , dest='do_py'     , action="store_true",
                        help="configure python scripts (py/hugo.py)")
    parser.add_argument("-t", "--do-tcl"    , dest='do_tcl'    , action="store_true",
                        help="configure TCL files (Verilog sources of fpga/rtl/dummy/)")
    parser.add_argument("-a", "--all"       , dest='do_all'    , action="store_true",
                        help="configure all the files")

    args = parser.parse_args()

    if args.do_all:
        args.do_verilog = args.do_main = args.do_html = args.do_py = args.do_tcl = True

    if not ( args.do_verilog or args.do_main or args.do_html or args.do_py or args.do_tcl ):
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
print('\n')


#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# Process FPGA registers


f = fpga_registers()

# Oscilloscope
grp='scope'
f.add( name="oscA_sw"            , group=grp , val=    1, rw=True ,  nbits= 5, min_val=          0, max_val=         31, fpga_update=True , signed=False, desc="switch for muxer oscA" )
f.add( name="oscB_sw"            , group=grp , val=    2, rw=True ,  nbits= 5, min_val=          0, max_val=         31, fpga_update=True , signed=False, desc="switch for muxer oscB" )
f.add( name="osc_ctrl"           , group=grp , val=    3, rw=True ,  nbits= 2, min_val=          0, max_val= 4294967295, fpga_update=True , signed=False, desc="oscilloscope control\n[osc2_filt_off,osc1_filt_off]" )
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
f.add( name="slow_out1"          , group=grp , val=    0, rw=False,  nbits=12, min_val=      -2048, max_val=       2047, fpga_update=True , signed=False, desc="signal for RP slow DAC 1" )
f.add( name="slow_out2"          , group=grp , val=    0, rw=False,  nbits=12, min_val=      -2048, max_val=       2047, fpga_update=True , signed=False, desc="signal for RP slow DAC 2" )
f.add( name="slow_out3"          , group=grp , val=    0, rw=False,  nbits=12, min_val=      -2048, max_val=       2047, fpga_update=True , signed=False, desc="signal for RP slow DAC 3" )
f.add( name="slow_out4"          , group=grp , val=    0, rw=False,  nbits=12, min_val=      -2048, max_val=       2047, fpga_update=True , signed=False, desc="signal for RP slow DAC 4" )
f.add( name="oscA"               , group=grp , val=    0, rw=False,  nbits=14, min_val=      -8192, max_val=       8191, fpga_update=True , signed=True , desc="signal for Oscilloscope Channel A" )
f.add( name="oscB"               , group=grp , val=    0, rw=False,  nbits=14, min_val=      -8192, max_val=       8191, fpga_update=True , signed=True , desc="signal for Oscilloscope Channel B" )

def add_read_ctrl(index=None):
    f.add( name="read_ctrl"      , group='aux', val=    0, rw=True ,  nbits= 3, min_val=          0, max_val=          7, fpga_update=True , signed=False, desc="[unused,start_clk,Freeze]", index=index )

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

for i in ['osc_ctrl','in1','in2','out1','out2']:
    f[i].write_def=False



if __name__ == '__main__' and args.do_verilog:
    print('do_verilog')
    f.update_verilog_files(folder)
    update_verilog(os.path.join('fpga','rtl','dummy.v'), dock=['ADDED REGS'], txt=[added_regs_doc(f, cfg.controls)+'\n'])
    print('\n')



#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# Process C code for MAIN

m = main_registers(num_base=81)

for r in f:
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


h.auto_set_controls('fpga/rtl/dummy.v','dummy')


h['dummy_osc1_filt_off'   ].control.text='Ch1'
h['dummy_osc2_filt_off'   ].control.text='Ch2'
h['dummy_osc_raw_mode'    ].control.text = 'Raw&nbsp;Mode'
h['dummy_osc_lockin_mode' ].control.text = 'R|Phase&nbsp;Mode'

h['dummy_oscA_sw'].control.enable = [True]*30 + [False]*2
h['dummy_oscB_sw'].control.enable = [True]*30 + [False]*2

# Controls of app.ini
for c in cfg.controls:
    hr = h['dummy_'+c.name]
    if c.htype == 'select':
        items = list(c.options) if c.options else [ str(y) for y in range(2**c.nbits) ]
        hr.control = select(idd='dummy_'+c.name, items=items, vals=list(range(len(items))), default=c.default)
    elif c.htype in ('button', 'checkbox'):
        hr.control.text = c.label


h.set_global_configs()

# Monitors: names and widths for the refresh of their values and bars
mons = [ c for c in cfg.controls if c.type == 'monitor' ]
mon_txt   = ','.join([ 'dummy_'+c.name for c in mons ])
nbits_txt = ','.join([ ('-' if c.signed else '')+str(c.nbits) for c in mons ])
h.html_global_configs.append(
        html_global_config( regex_start = r' *let *mon *=',
                            regex_end   = r'.*;.*',
                            text        = f"let mon = '{mon_txt}'.split(','); // Monitor controls vector" ) )
h.html_global_configs.append(
        html_global_config( regex_start = r' *let *nbits *=',
                            regex_end   = r'.*;.*',
                            text        = f"let nbits = [{nbits_txt}] ; // Monitor controls bit numbers" ) )

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

    tag = ( '# Automatically added dummy modules', '# End of automatic part')
    txt1 = '\n'
    txt2 = '\n'
    for vfile in [ y.replace('fpga/rtl','$path_rtl') for y in sorted(glob('fpga/rtl/dummy/*.v')) ]:
        txt1 += 'read_verilog'.ljust(34) + vfile + '\n'
        txt2 += 'add_files'.ljust(34) + vfile + '\n'
    print('Writting file: fpga/red_pitaya_vivado.tcl')
    update_file_match(
        filename='fpga/red_pitaya_vivado.tcl',
        tag=tag,
        txt=txt1)
    print('Writting file: fpga/red_pitaya_vivado_project.tcl')
    update_file_match(
        filename='fpga/red_pitaya_vivado_project.tcl',
        tag=tag,
        txt=txt2)
    print('\n')


if __name__ == '__main__':
    # backups written by the update functions of config_lib (<name>_YYYYMMDD_HHMMSS[_p].<ext>.bak and
    # <file>_YYYYMMDD_HHMMSS.bak); other .bak files are not touched
    import re as _re
    for bak in glob('**/*.bak', recursive=True):
        if _re.search(r'_\d{8}_\d{6}(_p)?(\.[A-Za-z]+)?\.bak$', bak):
            os.remove(bak)
    print('end')
