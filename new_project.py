#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from datetime import datetime
import re
import argparse
import configparser
import fileinput

from glob import glob

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# Useful functions

def print_html_monitor(idd,label):
    txt='\n'.join([
        '<div class="panel-group col-xs-12 col-sm-6 col-md-6">',
        '  <h2><label class="group-label" for="dummy_'+idd+'">'+label+'</label></h2>',
        '  <h2><span class="label label-info" style="display:block;" id="dummy_'+idd+'">Value</span></h2>',
        '  <div class="progress" style="height: 5px;">',
        '    <div id="dummy_'+idd+'_bar" class="progress-bar progress-bar-success" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" style="width:0%; height: 5px;" ></div>',
        '  </div>',
        '</div>'])
    return txt


def print_html_combo(idd,label,nbits):
    txt='\n'.join([
        '<div class="panel-group col-xs-12 col-sm-12 col-md-12">',
        '  <form class="form-horizontal" role="form" onsubmit="return false;">',
        '    <div class="form-group">\n'
    ])
    txt+='      <label for="dummy_'+idd+'" class="col-xs-4 control-label">'+label+'</label>\n'
    txt+='      <div class="col-xs-8">\n'
    txt+='        <select id="dummy_'+idd+'" class="form-control">\n'
    txt+='          <option  value="0" selected="selected">opt0</option>\n'
    for i in range(1,2**nbits):
        txt+='          <option  value="{:d}" >opt{:d}</option>\n'.format(i,i)
    txt+='\n'.join([
            '        </select>',
            '      </div>',
            '    </div>',
            '  </form>',
            '</div>'
            ])
    return txt


def print_html_number(idd,label,nbits,signed=True):

    txt = '\n'.join([
        '<div class="panel-group col-xs-12 col-sm-12 col-md-12">',
        '  <form class="form-horizontal" role="form" onsubmit="return false;">',
        '    <div class="form-group">\n'
    ])
    txt+='      <label for="dummy_'+idd+'" class="col-xs-4 control-label">'+label+'</label>\n'
    txt+='      <div class="col-xs-4 col-sm-8">\n'
    txt+='        <input type="number" autocomplete="off" class="form-control" value="0" id="dummy_'+idd
    txt+='" step="1" min="'+ ( str(-2**(nbits-1)) if signed else '0' )+'" max="'+ ( str(2**(nbits-1)-1) if signed else str(2**nbits-1)) +'">\n'
    txt+='        <span style="display: none;" class="input-group-btn" id="dummy_'+idd+'_apply">\n'
    txt+= '\n'.join([
        '          <button type="button" class="btn btn-primary btn-lg"><span class="glyphicon glyphicon-ok-circle"></span></button>',
        '        </span>',
        '      </div>',
        '    </div>',
        '  </form>',
        '</div>\n'
    ])
    return txt



def print_html_checkbox(idd,label):
    txt = '\n'.join([
        '<div class="panel-group col-xs-12 col-sm-12 col-md-12">',
        '  <form class="form-horizontal" role="form" onsubmit="return false;">',
        '    <div class="checkbox" style="padding-bottom: 12px;">',
        '      <label class="group-label">\n'
    ])
    txt+='        <input type="checkbox" id="dummy_'+idd+'" checked>'+label+'\n'
    txt+= '\n'.join([
        '      </label>',
        '    </div>',
        '  </form>',
        '</div>'
    ])
    return txt

def print_html_button(idd,label):
    txt = '\n'.join([
        '<div class="panel-group col-xs-12 col-sm-12 col-md-12">',
        '  <form class="form-horizontal" role="form" onsubmit="return false;">',
        '    <div class="form-group text-center">\n'
    ])
    txt+='      <button id="dummy_'+idd+'" class="btn btn-primary btn-lg" data-checked="true" disabled>'+label+'</button>\n'
    txt+= '\n'.join([
        '    </div>',
        '  </form>',
        '</div>'
    ])
    return txt




#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# Parse arguments


if '__file__' in globals():
    scriptFolder = os.path.dirname(os.path.realpath(__file__))
else:
    scriptFolder = 'rp_dummy/resources'


#folder = os.path.sep.join(scriptFolder.split(os.path.sep)[:-1]) # + os.path.sep + AppName
folder = scriptFolder # + os.path.sep + AppName

# Save original working directory for later
cwd = os.getcwd()

# Change to configuration folder
os.chdir(folder)
print('Working folder: '+folder)


#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# Parse arguments

AppName = 'dummy'

if __name__ == '__main__':

    # Parse arguments
    parser = argparse.ArgumentParser(
                description='Configure the Dummy app files to ease the Web Browser <--> C controller <--> FPGA registers comunication'
            )

    parser.add_argument("AppName", type=str,
                        help="Name of the application folder")

    parser.add_argument("-c", "--config-file" ,  dest='config', default=os.path.join(folder,'config.ini') ,type=str,
                        help="Read configuration from this file")

    parser.add_argument("-u", "--update-rp-settings"   , dest='update_rp'   , action="store_true",
                        help="Create _settings.env file from config file info")

    args = parser.parse_args()

    AppName = args.AppName
    if not ( 'dummy_' in AppName ) :
        AppName = 'dummy_' + AppName

    print('AppName: '+AppName)

    if not os.path.isdir(  os.path.join(folder,AppName) ):
        print('Creating folder: '+ AppName)
        os.system('cp -a dummy ' + AppName)
    else:
        print('Destiny folder already exist.')
        exit(1)

    #print(args.config.read())
    config = configparser.ConfigParser()
    if folder in args.config:
        config_file = args.config
    else:
        config_file = os.path.join(cwd,args.config)
    print('Reading configuration from: '+ config_file )
    config.read(config_file)

    #print(config.sections())

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Reading config file

    txt_control=[]
    txt_monitor=[]

    print('Processing config file:\n')
    py_txt=['grp="dummy"']

    ctrls=[]


    include_genfun = config.getboolean('general','include_genfun')
    include_pids   = config.getboolean('general','include_pids')

    for section in config.sections():
        if section == 'general':
            continue
        c_type  = config.get(section,'type')
        c_label = config.get(section,'label')
        if c_type=='combo' or c_type=='number' or c_type=='monitor':
            c_nbits = config.getint(section,'bits_number')
        else:
            c_nbits = 1

        if c_type=='number' or c_type=='monitor':
            c_signed = config.getboolean(section,'signed')
        else:
            c_signed = False

        print('Creating control type:'+c_type.ljust(10)+' reg: '+section.ljust(15)+' label: '+c_label.ljust(15))



        if c_type=='combo':
            txt_control.append( print_html_combo(    section,c_label,c_nbits) )
            ctrls.append( {'name': section, 'htype': 'select', 'label': c_label, 'nbits': c_nbits, 'signed': c_signed} )
        elif c_type=='number':
            txt_control.append( print_html_number(   section,c_label,c_nbits,c_signed) )
            ctrls.append( {'name': section, 'htype': 'number', 'label': c_label, 'nbits': c_nbits , 'signed': c_signed} )
        elif c_type=='checkbox':
            txt_control.append( print_html_checkbox( section,c_label) )
            ctrls.append( {'name': section, 'htype': 'checkbox', 'label': c_label, 'nbits': 1 , 'signed': False } )
        elif c_type=='button':
            txt_control.append( print_html_button( section,c_label) )
            ctrls.append( {'name': section, 'htype': 'button', 'label': c_label, 'nbits': 1 , 'signed': False  } )
        elif c_type=='monitor':
            txt_monitor.append( print_html_monitor(section, c_label) )
            ctrls.append( {'name': section, 'htype': 'monitor', 'label': c_label, 'nbits': c_nbits , 'signed': c_signed} )

        py_txt.append('f.add( name='+('"'+section+'"').ljust(20)+', group=grp , val=    0, rw='+ ('False' if c_type=='monitor' else 'True').rjust(6)+
                     ', nbits='+str(c_nbits).ljust(4)+
                     ', min_val= '+( str(-2**(c_nbits-1)) if c_signed else '0' ).rjust(10)+
                     ', max_val= '+( str(2**(c_nbits-1)-1) if c_signed else str(2**c_nbits-1)).rjust(10)+
                     ', fpga_update='+('False' if c_type=='monitor' else 'True').rjust(6)+
                     ', signed='+str(c_signed).rjust(6)+
                     ', desc="Added automatically by script" )')

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Update HTML5

    html_file = os.path.join(folder,AppName,'index.html')

    print('Updating htmlfile: '+html_file)

    for line in fileinput.input( files=(html_file),backup='_'+datetime.now().strftime("%Y%m%d_%H%M%S")+'.bak',inplace=True) :
        line = line.rstrip()
        if '<!-- Dummy panel controls DOCK -->' in line:
            indent=line.find('<!--')
            line +=  '\n'+' '*indent
            line += '\n'.join(txt_control).replace('\n','\n'+' '*indent)
        if '<!-- Monitor PANEL -->' in line:
            indent=line.find('<!--')
            line +=  '\n'+' '*indent
            line += '\n'.join(txt_monitor).replace('\n','\n'+' '*indent)
        print(line)

    # Raplacement vector
    rep = [
        ["var app_id = 'dummy';","var app_id = '"+AppName+"';"],
        ["localStorage\\.lockConfig","localStorage."+AppName+"config"],
        [r'<h2 class="page-title">Oscilloscope\+Dummy</h2>','<h2 class="page-title">'+AppName.replace('_',' ')+'</h2>']
    ]

    tmp_mon_txt = ','.join([ 'dummy_'+y['name'] for y in filter( lambda x: x['htype']=='monitor', ctrls ) ])
    rep.append( [r"let mon = ''.split\(','\); // Monitor controls vector" ,"let mon = '"+tmp_mon_txt+"'.split(','); // Monitor controls vector" ] )

    tmp_mon_nbits = ','.join([ ('-' if y['signed'] else '' )+str(y['nbits']) for y in filter( lambda x: x['htype']=='monitor', ctrls ) ])
    rep.append( [r"let nbits = \[\] ; // Monitor controls bit numbers" , "let nbits = ["+tmp_mon_nbits+"] ; // Monitor controls bit numbers" ])

    print('Include Signal Generator? : ' + str(include_genfun) )
    if not include_genfun :
        rep.append( ["<!-- DISABLE SignalGenerator -->","<!-- DISABLE SignalGenerator "] )
        rep.append( ["// Events binding for signal generator","/* DISABLE Events binding for signal generator" ] )

    print('Include PID Controllers?  : ' + str(include_pids) )
    if not include_pids :
        rep.append( ["<!-- DISABLE PIDController -->","<!-- DISABLE PIDController "] )
        rep.append( ["// Events binding for PID Controller","/* DISABLE Events binding for PID Controller" ] )

    for line in fileinput.input( files=(html_file),backup='_'+datetime.now().strftime("%Y%m%d_%H%M%S")+'.bak',inplace=True) :
        for i in rep:
            line = re.sub(i[0], i[1], line.rstrip())
        print(line)

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Update FPGA fpga.conf

    with open( os.path.join(AppName,'fpga.conf'), 'w') as fpga_file:
        fpga_file.write('/opt/redpitaya/www/apps/'+AppName+'/red_pitaya.bit\n')

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Update INFO

    with open( os.path.join(AppName,'info','info.json'), 'w') as info_file:
        info_file.write('{\n')
        info_file.write('    "name": "'+AppName+'",\n')
        info_file.write('    "version": "0.1.0-BUILD_NUMBER",\n')
        info_file.write('    "revision": "REVISION",\n')
        info_file.write('    "description": "A toolkit application testing and learnning FPGA Verilog programming for RedPitaya. Includes several already-made modules."\n')
        info_file.write('}')

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Create SETTINGS

    if args.update_rp or ( not os.path.isfile('_settings.env') ):
        with open( '_settings.env', 'w') as sett_file:
            sett_file.write('#\n')
            sett_file.write('# Settings for Makefile\n')
            sett_file.write('#\n')
            sett_file.write('\n')
            sett_file.write('RPIP='  +config.get('general','rp_host' )+'\n')
            sett_file.write('RPOPTS='+config.get('general','ssh_opts')+'\n')
            sett_file.write('RPSCP=' +config.get('general','scp_opts')+'\n')
            sett_file.write('\n')

    print('After updating config_tool.py, run it with -a option for '+ AppName)

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Update CONFIG config_tool.py

    configtool_file = os.path.join(folder,AppName,'config_tool.py')
    for line in fileinput.input( files=(configtool_file),backup='_'+datetime.now().strftime("%Y%m%d_%H%M%S")+'.bak',inplace=True) :
        line = line.rstrip()
        if bool(re.match(r'\s*# Automated added registers',line)):
            line += '\n'
            line += '\n'.join(py_txt)
            line += '\n'
        if bool(re.match(r'\s*# Automated added HTML controllers',line)):
            line += '\n'
            for y in ctrls:
                line += "h["+ ("'dummy_"+y['name']+"'").ljust(25)+"].type    = '"+y['htype']+"'\n"
            line += '\n'
        if bool(re.match(r'\s*# Automatic configuration of HTML controllers',line)):
            line += '\n'
            for y in ctrls:
                if y['htype']=='select':
                    line += "h["+ ("'dummy_"+y['name']+"'").ljust(25)+"].control      = select(idd="+ ("'dummy_"+y['name']+"'").ljust(25)+", items=[ str(y) for y in range("+str(2**y['nbits'])+") ] ) \n"
                elif y['htype']=='button' or y['htype']=='checkbox':
                    line += "h["+ ("'dummy_"+y['name']+"'").ljust(25)+"].control.text = '"+y['label']+"'\n"
            line += '\n'

        print(line)

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Update TCL config

    tcl_files = ( os.path.join(folder,AppName,'fpga','red_pitaya_vivado.tcl') , os.path.join(folder,AppName,'fpga','red_pitaya_vivado_project.tcl') )
    for line in fileinput.input( files=tcl_files ,backup='_'+datetime.now().strftime("%Y%m%d_%H%M%S")+'.bak',inplace=True) :
        line = line.rstrip()
        if 'project' in fileinput.filename():
            add_cmd = 'add_files'
        else:
            add_cmd = 'read_verilog'
        if bool(re.match(r'\s*# Automatically added dummy modules',line)):
            line += '\n'
            line += add_cmd.ljust(34)+'$path_rtl/dummy.v\n'
            for vfile in [ y.replace(AppName+'/fpga/rtl','$path_rtl') for y in glob(AppName+'/fpga/rtl/dummy/*.v') ]:
                line += add_cmd.ljust(34) + vfile + '\n'
            line += '\n'
        print(line)


    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Update dummy.v help comments

    dummyv_file = os.path.join(folder,AppName,'fpga','rtl','dummy.v')
    for line in fileinput.input( files=(dummyv_file),backup='_'+datetime.now().strftime("%Y%m%d_%H%M%S")+'.bak',inplace=True) :
        line = line.rstrip()
        if bool(re.match(r'\s*// \[DOCK_FOR_ADDED_REGS\]',line)):
            line = '\n'
            for y in ctrls:
                line += '    //   '+y['name'].ljust(10)+'--> {:2d} bits {:s}signed bus ({:>10d} --> {:<10d}) \n'.format(
                        y['nbits'],
                        '  ' if y['signed'] else 'un'  ,
                        - 2**(y['nbits']-1) if y['signed'] else 0 ,
                        2**(y['nbits']-1)-1 if y['signed'] else 2**y['nbits']-1
                        )
            line += '\n'
        print(line)

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Update red_pitaya_top.v
    topv_file = os.path.join(folder,AppName,'fpga','rtl','red_pitaya_top.v')
    for line in fileinput.input( files=(topv_file),backup='_'+datetime.now().strftime("%Y%m%d_%H%M%S")+'.bak',inplace=True) :
        line = line.rstrip()
        # `define INCLUDE_GENFUN / INCLUDE_PIDS: commented out when the block is disabled (the top
        # then answers its bus slot with a stub)
        if not include_genfun and re.match(r'\s*`define\s+INCLUDE_GENFUN\b',line):
            line = '// ' + line + ' (disabled: include_genfun = False)'
        if not include_pids and re.match(r'\s*`define\s+INCLUDE_PIDS\b',line):
            line = '// ' + line + ' (disabled: include_pids = False)'
        print(line)

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Update ICONS


    #os.system('rm ./'+AppName+'/info/icon.png')
    os.system("""mogrify  -font FreeSans-Negrita -pointsize 20 -draw "gravity south ; fill black  text 0,12 '"""+AppName[6:]+"""' ; fill white  text 1,11 '"""+AppName[6:]+"""' "  ./"""+AppName+"""/info/icon.png""")
    os.system("""mogrify  -font FreeSans-Negrita -pointsize 20 -draw "gravity south ; fill black  text 0,12 '"""+AppName[6:]+"""' ; fill white  text 1,11 '"""+AppName[6:]+"""' "  ./"""+AppName+"""/info/icon_DEBUG.png""")
    os.system("""mogrify  -font FreeSans-Negrita -pointsize 20 -draw "gravity south ; fill black  text 0,12 '"""+AppName[6:]+"""' ; fill white  text 1,11 '"""+AppName[6:]+"""' "  ./"""+AppName+"""/info/icon_RELOAD.png""")

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Run  config_tool.py -a

    print('\n\nRunning first configuration: ./'+AppName+'/config_tool.py -a \n')
    os.system('./'+AppName+'/config_tool.py -a ')

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Update upload script

    upload_file = os.path.join(folder,AppName,'upload_app.sh')
    for line in fileinput.input( files=(upload_file),backup='_'+datetime.now().strftime("%Y%m%d_%H%M%S")+'.bak',inplace=True) :
        for i in rep:
            line = re.sub('APP="dummy"', 'APP="'+AppName+'"', line.rstrip())
        print(line)

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Clean bak files and bkp ini file
    print('\n\nCleanning temp files .bak')
    os.system("find "+AppName+" -type f  | grep '\\.bak$'  | xargs rm ")
    os.system('cp ' + config_file +' ./'+ AppName+'/info/')
    exit(0)



if __name__ == '__main__':
    print('end')
