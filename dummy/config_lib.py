#!/usr/bin/env python3 -B
# -*- coding: utf-8 -*-

from math import ceil
import configparser
import keyword
import os
import enum
from datetime import datetime
import re
import fileinput
import shutil

# Version of the generator (rp_dummy2: new_project.py, config_tool.py, the template). Generated Apps keep their own
# version in info/info.json (0.1.0 when created); this one is recorded in their info.json, README and CHANGELOG.
RP_DUMMY_VERSION = '1.0.0'


# User RTL of the App: the dummy module and its own modules (shared by the Vivado 2020.1 design of fpga/
# and the optional Vivado 2015.2 design of fpga_eco1/)
DUMMY_RTL_DIR = os.path.join('fpga', 'prj', 'v0.94', 'rtl')
DUMMY_V       = os.path.join(DUMMY_RTL_DIR, 'dummy.v')


def unique(values):
    """Sorted list of the distinct values (replaces numpy.unique, so numpy is not needed)"""
    return sorted(set(values))

#%% auxiliar

def inline(txt):
    return txt.replace('\n',' // ')


#%% FPGA classes


class fpga_register():
    """Register for FPGA module"""
    def __init__(self, name, val=0, rw=True,  nbits=14, min_val=0, max_val=0, desc='todo', signed=False, fpga_update=True ,index=0, group='mix'):
        """Initialize attributes."""
        self.name        = name
        self.val         = val
        self.rw          = rw
        self.ro          = not rw
        self.nbits       = nbits
        self.index       = index
        self.i           = index
        self.pos         = index*4
        self.addr        = "20'h{:05X}".format(index*4)
        if min_val==0 and max_val==0:
            self.min     =   - 2**(nbits-1) if signed else  0
            self.max     =     2**(nbits-1)-1 if signed else  2**nbits -1
        else:
            self.min         = min_val
            self.max         = max_val
        self.desc        = desc
        self.fpga_update = fpga_update
        self.signed      = signed
        self.group       = group
        self.write_def   = True
        self.no_param    = False  # not a parameter of the C controller (e.g. stream_*: written by the c/ tools)
        self.rd_copy     = False  # read-only signal: the bus reads its registered copy <name>_rd
        self.c_update    = None
        self.main_reg    = None
        self.reg_read    = False

    def __repr__(self):
        txt  = self.name + ','
        txt += ( 'rw' if self.rw else 'ro' ) + ','
        txt += 'val='+str(self.val) + ','
        txt += 'min='+str(self.min) + ','
        txt += 'max='+str(self.max) + ','
        txt += 'nbits='+str(self.nbits) + ','
        txt += ( 'int' if self.signed else 'uint' ) + ','
        txt += 'group='+ self.group
        return 'fpga_register('+txt+')'

    def __getitem__(self, key):
        return getattr(self,key)




class fpga_registers():
    """Collection os fpga_register clasess"""
    def __init__(self):
        self.data  = []
        self.names = []
        self.len   = 0

    def __getitem__(self, key):
        if type(key)==int:
            return self.data[key]
        if type(key)==str:
            return self.data[self.names.index(key)]
        if type(key)==slice:
            return self.data[key]

    def __repr__(self):
        txt  = 'fpga_registers()\n'
        for r in self.data:
            txt += ' '*4 + r.name + '\n'
        txt += '\n'
        return txt

    def add(self, name, val=0, rw=True,  nbits=14, min_val=0, max_val=0, signed=False, desc='todo',fpga_update=True, group='mix', index=None):
        """Add a register. index (address/4) defaults to the one after the last register."""
        if index is None:
            index = self.next_index()
        if index in [ r.index for r in self.data ]:
            raise ValueError(f'fpga_registers.add({name}): address 0x{4*index:03X} already used')
        self.data.append(fpga_register(name=name, val=val, rw=rw, nbits=nbits, group=group,
                                       min_val=min_val, max_val=max_val, signed=signed,
                                       desc=desc, fpga_update=fpga_update , index=index ))
        self.names.append(name)
        self.len = len(self.names)

    def next_index(self):
        """Index (address/4) that follows the highest register"""
        return max([ r.index for r in self.data ], default=-1) + 1

    def end_addr(self):
        """First byte address after the last register"""
        return 4*self.next_index()

    def update_verilog_files(self,folder):
        fpga_mod_fn = DUMMY_V
        print('Updating verilog file: '+fpga_mod_fn)
        if not os.path.isdir(folder):
            raise ValueError('"folder" variable should be the source code folder path.')
        os.chdir(folder)
        update_verilog(fpga_mod_fn,dock=['WIREREG','BUS READ COPIES','FPGA MEMORY'],
                       txt=[fpga_defs(self),fpga_rd_copies(self),fpga_reg_write(self)+fpga_reg_read(self)])

    def set_py_global_config(self):
        print('set_py_global_config(): configuration of python scripts for remote comunication')
        self.py_global_config=[]
        self.py_global_config.append(
                html_global_config( regex_start = r' *# *\[REGSET DOCK\] *',
                                    regex_end   = r' *# *\[REGSET DOCK END\]',
                                    text        = '# [REGSET DOCK]\n'+self.print_hugo(ret=True)+'# [REGSET DOCK END]' )
                )

    def update_python_files(self,folder):
        print('update_python_files()')
        if not os.path.isdir(folder):
            raise ValueError('"folder" variable should be the source code folder path.')
        os.chdir(folder)
        update_py('py/hugo.py',self.py_global_config)

    def print_hugo(self,ret=False):
        txt=''
        txt+='dm = fpga_dummy(base_addr=0x40600000,dev_file="/dev/mem")\n'
        txt+='\n'
        for r in self:
            txt+="dm.add( fpga_reg(name={:21s}, index={:3d}, rw={:5s}, nbits={:2d},signed={:5s}) )\n".format(
                    "'"+r.name+"'" , r.index , str(r.rw) , r.nbits , str(r.signed) )
        if ret:
            return txt
        else:
            print(txt)


#%% MAIN classes


class main_register():
    """Register for C controller module"""
    def __init__(self, name, val=0, rw=True,  min_val=0, max_val=0, nbits=14, desc='todo',
                 signed=False, fpga_update=True ,index=0, c_update=None , group='mix'):
        """Initialize attributes."""
        self.name        = name
        self.val         = val
        self.rw          = rw
        self.ro          = not rw
        self.nbits       = nbits
        self.index       = index
        self.i           = index
        self.min         = min_val
        self.max         = max_val
        self.desc        = desc
        self.group       = group
        self.fpga_update = fpga_update
        self.signed      = signed
        self.c_update    = c_update
        self.fpga_reg    = ''
        self.cdef        = name.upper()

    def __repr__(self):
        txt  = self.name + ','
        txt += 'fpga_reg='+str(self.fpga_reg) + ','
        txt += ( 'rw' if self.rw else 'ro' ) + ','
        txt += 'val='+str(self.val) + ','
        txt += 'min='+str(self.min) + ','
        txt += 'max='+str(self.max) + ','
        txt += 'nbits='+str(self.nbits) + ','
        txt += ( 'int' if self.signed else 'uint' ) + ','
        txt += 'group='+ self.group
        return 'main_register('+txt+')'


class main_registers():
    """Collection of registers for C controller module"""
    def __init__(self,num_base=81):
        self.data  = []
        self.names = []
        self.len   = 0
        self.num_base=num_base
    def __getitem__(self, key):
        if type(key)==int:
            return self.data[key]
        if type(key)==str:
            return self.data[self.names.index(key)]
        if type(key)==slice:
            return self.data[key]

    def __repr__(self):
        txt  = 'main_registers()\n'
        for r in self.data:
            txt += ' '*4 + r.name + '\n'
        txt += '\n'
        return txt

    def renumber(self):
        i=0
        for r in self:
            r.i     = i
            r.index = r.i+self.num_base
            i+=1

    def fix_c_update(self,f):
        print('fix_c_update(): Completes C code for FPGA comunication')
        for r in [ y for y in filter(lambda x: ( x.c_update==None and x.fpga_reg!=None) , self) ]:
            r.c_update='(float)g_dummy_reg->{:20s}'.format(r.fpga_reg)
        for r in f:
            if r.no_param:
                continue
            if r.c_update==None:
                r.main_reg='dummy_'+r.name
                r.c_update='(int)params[{:30s}].value'.format( self[r.main_reg].cdef )
        return True

    def insert_reg(self,pos,reg,fpga_reg=None):
        if type(pos)==int:
            i=pos
        elif type(pos)==str and ( pos in self.names ):
            i=self[pos].i
        else:
            return 'Bad position'

        self.names.insert(i,reg.name)
        self.data.insert(i,reg)

        self.data[i].fpga_reg=fpga_reg
        self.len = len(self.names)
        self.renumber()
        return True

    def del_reg(self,pos):
        if type(pos)==int:
            i=pos
        elif type(pos)==str and ( pos in self.names ):
            i=self[pos].i
        else:
            return 'Bad position'
        self.names.pop(i)
        self.data.pop(i)
        self.renumber()
        return True

    def add(self, name, val=0, rw=True, nbits=14, min_val=0, max_val=0, signed=False, desc='todo',
            fpga_update=True, c_update=None, fpga_reg=None , group='mix'):
        if type(name)==str:
            self.data.append(main_register(name=name, val=val, rw=rw,  nbits=nbits, group=group,
                                           min_val=min_val, max_val=max_val, signed=signed,
                                           desc=desc, fpga_update=fpga_update , index=self.len,
                                           c_update=c_update))
            self.names.append(name)
            self.data[-1].fpga_reg=fpga_reg
            self.data[-1].c_update=None
            self.len = len(self.names)
        elif type(name)==fpga_register:
            self.data.append(main_register(name='dummy_'+name.name, val=name.val, rw=name.rw,
                                           min_val=name.min, max_val=name.max, signed=name.signed,
                                           desc=name.desc, fpga_update=name.fpga_update , index=self.len ))
            self.data[-1].fpga_reg=name.name
            self.data[-1].c_update='(float)g_dummy_reg->{:20s}'.format(name.name)
            self.names.append('dummy_'+name.name)
            self.len = len(self.names)
        self.data[-1].index=self.data[-1].i+self.num_base
        self.data[-1].cdef=self.data[-1].name.upper()

    def update_c_files(self,folder,f):
        if not os.path.isdir(folder):
            raise ValueError('"folder" variable should be the App folder path.')
        os.chdir(folder)
        #if not os.path.isdir(AppName):
        #    raise ValueError('"AppName" variable should be the source code folder path.')

        filename = os.path.join('src','dummy.c')
        update_main(filename , dock = ['PARAMSUPDATE'      , 'FPGAUPDATE'],
                               txt  = [main_update_params(self), main_update_fpga(f)])

        filename = os.path.join('src','fpga_dummy.c')
        update_main(filename , dock = ['FPGARESET'],
                               txt  = [main_fpga_regs_reset(f)])


        filename = os.path.join('src','fpga_dummy.h')

        update_main(filename , dock = ['FPGAREG'],
                               txt  = [main_fpga_regs_def(f)])

        filename = os.path.join('src','main.c')
        update_main(filename , dock = ['MAINDEF'],
                               txt  = [main_def(self)])

        filename = os.path.join('src','main.h')
        update_main(filename , dock = ['MAINDEFH'],
                               txt  = [main_defh(self)])

        replace_pattern(filename , pattern = ['^#define[ ]+PARAMS_NUM[ ]+[0-9]+'],
                                   txt     = [ '#define PARAMS_NUM        {:>3d}'.format(self[-1].index+1) ])



#%% HTML registers


class html_register():
    """Register for Web Frontend module"""
    def __init__(self, name, val=0, rw=True,  min_val=0, max_val=0,
                 desc='todo', signed=False, fpga_update=True ,index=0,
                 input_type='input'):
        """Initialize attributes."""
        self.name        = name
        self.val         = val
        self.rw          = rw
        self.ro          = not rw
        self.index       = index
        self.i           = index
        self.min         = min_val
        self.max         = max_val
        self.desc        = desc
        self.fpga_update = fpga_update
        self.signed      = signed
        self.type        = input_type
    def __repr__(self):
        txt  = self.name + ','
        txt += ( 'rw' if self.rw else 'ro' ) + ','
        txt += 'val='+str(self.val) + ','
        txt += 'min='+str(self.min) + ','
        txt += 'max='+str(self.max) + ','
        txt += ( 'int' if self.signed else 'uint' ) + ','
        txt += 'type='+ self.type
        return 'html_register('+txt+')'

class html_registers():
    """Collection of registers for Web Frontend module"""
    def __init__(self,num_base=81):
        self.data  = []
        self.names = []
        self.len   = 0
        self.num_base=num_base

    def __getitem__(self, key):
        if type(key)==int:
            return self.data[key]
        if type(key)==str:
            return self.data[self.names.index(key)]
        if type(key)==slice:
            return self.data[key]

    def __repr__(self):
        txt  = 'html_registers()\n'
        for r in self.data:
            txt += ' '*4 + r.name + '\n'
        txt += '\n'
        return txt

    def add(self, name, val=0, rw=True,  min_val=0, max_val=0, signed=False, desc='todo',
            fpga_update=True, c_update=None, fpga_reg=None):
        if type(name)==str:
            self.data.append(html_register(name=name, val=val, rw=rw,
                                           min_val=min_val, max_val=max_val, signed=signed,
                                           desc=desc, fpga_update=fpga_update ,
                                           input_type='input'))
            self.names.append(name)
            self.len = len(self.names)
        elif type(name)==main_register:
            self.data.append(html_register(name=name.name, val=name.val, rw=name.rw,
                                           min_val=name.min, max_val=name.max, signed=name.signed,
                                           desc=name.desc, fpga_update=name.fpga_update ,
                                           input_type='input'))
            self.names.append(name.name)
            self.len = len(self.names)
        self.data[-1].index=self.data[-1].i+self.num_base

    def guess_control_type(self):
        print('guess_control_type(): Automatic guessing of HTML control type from reg name')
        for r in self:
            if r.ro:
                r.type='none'
                # print('    '+ r.name + ' is monitor (read only)')
            else:
                if r.name[-3:]=='_sw' or r.max==15 or r.max==7:
                    r.type='select'
                    # print('    '+ r.name + ' is combo/select')
                elif r.max==1:
                    r.type='checkbox'
                    # print('    '+ r.name + ' is checkbox (can also be a button switch)')
                else:
                    r.type='number'
                    # print('    '+ r.name + ' is a raw number control')
            r.control=None

    def auto_set_controls(self,filename,AppName,names=None,quiet=()):
        """Controls of the HTML elements; a select whose register is the .sel of a muxer of dummy.v gets the
        names of the muxer inputs (names: {wire: text}, see get_muxer())"""
        print('auto_set_controls(): automatic configuration of HTML controllers')
        # load controls for number inputs
        for i in [ y.name for y in filter( lambda x: x.type=='number' , self) ]:
            self[i].control = input_number(idd=self[i])

        # load controls for checkbox inputs
        for i in [ y.name for y in filter( lambda x: x.type=='checkbox' , self) ]:
            self[i].control = input_checkbox(idd=self[i])

        # load controls for button inputs
        for i in [ y.name for y in filter( lambda x: x.type=='button' , self) ]:
            self[i].control = input_button(idd=self[i])

        if not os.path.isfile(filename):
            raise ValueError('filename('+filename+') does not existt')

        rip_len=(len(AppName)+1)
        # load controls for select
        for i in [ y.name for y in filter( lambda x: x.type=='select' , self) ]:
            items = get_muxer(filename, i[rip_len:], names)
            if len(items)>0:
                self[i].control = select(idd=i , items=items, default=self[i].val  );
            elif i not in quiet:
                print(i+': select controller should be set by hand. No muxer found.')

    def print_control_type(self):
        max_len=max([ len(y) for y in self.names ])+2
        txt="h[{:"+str(max_len)+"s}].type = '{:s}'"
        for r in self:
            print(txt.format("'"+r.name+"'",r.type))

    def update_html_files(self,folder):
        filename='index.html'
        if not os.path.isdir(folder):
            raise ValueError('"folder" variable should be the source code folder path.')
        if not os.path.isfile(filename):
            raise ValueError('"filename" should be an existing file.')
        os.chdir(folder)
        update_html(filename,self)

    def set_global_configs(self):
        print('set_global_configs(): Configuration of HTML+JS controls')
        self.html_global_configs=[]

        # config_params_txts  ***********************************************
        txt=[]
        txt.append("config_params_txts = 'xmin,xmax,trig_mode,trig_source,trig_edge,trig_delay,trig_level,time_range,time_units,en_avg_at_dec,min_y,'+")
        txt.append(' '*21+"'max_y,prb_att_ch1,gain_ch1,prb_att_ch2,gain_ch2,gui_xmin,gui_xmax,'+")
        tmp=' '*21+"'"
        for i in [ y.name for y in filter( lambda x: x.rw , self) ]:
            tmp += i+","
            if len(tmp)>130:
                tmp+="'+"
                txt.append(tmp)
                tmp=' '*21+"'"
        if len(tmp)>25:
            tmp=tmp[0:-1]
            tmp+="';"
            txt.append(tmp)
        else:
            txt[-1]=txt[-1][0:-3]+"';"
        txt=('\n'.join(txt))

        self.html_global_configs.append(
                html_global_config( regex_start = ' *config_params_txts *=',
                                    regex_end   = '.*;.*',
                                    text        = txt )
                )

        # input_checkboxes  *************************************************
        txt=[]
        tmp="var input_checkboxes = '"
        for i in [ '#'+y.name for y in filter( lambda x: x.type=='checkbox' , self) ]:
            tmp += i+","
            if len(tmp)>130:
                tmp+="'+"
                txt.append(tmp)
                tmp=' '*23+"'"
        if len(tmp)>25:
            tmp=tmp[0:-1]
            tmp+="';"
            txt.append(tmp)
        else:
            txt[-1]=txt[-1][0:-3]+"';"
        txt=('\n'.join(txt))

        self.html_global_configs.append(
                html_global_config( regex_start = ' *var *input_checkboxes *=',
                                    regex_end   = '.*;.*',
                                    text        =  txt)
                )

        # input_select  *************************************************
        txt=[]
        tmp="var switches=["
        for i in [ "'#"+y.name+"'" for y in filter( lambda x: x.type=='select' , self) ]:
            tmp += i+","
            if len(tmp)>130:
                txt.append(tmp)
                tmp=' '*14
        if len(tmp)>16:
            tmp=tmp[0:-1]
            tmp+="];"
            txt.append(tmp)
        else:
            txt[-1]=txt[-1][0:-1]+"];"
        txt=('\n'.join(txt))

        self.html_global_configs.append(
                html_global_config( regex_start = r' *var *switches *= *\[',
                                    regex_end   = r'.*\] *;.*',
                                    text        =  txt)
                )

        # input_buttons  *************************************************
        txt=[]
        tmp="var input_buttons = '"
        for i in [ '#'+y.name for y in filter( lambda x: x.type=='button' , self) ]:
            tmp += i+","
            if len(tmp)>130:
                tmp+="'+"
                txt.append(tmp)
                tmp=' '*20+"'"
        if len(tmp)>22:
            tmp=tmp[0:-1]
            tmp+="';"
            txt.append(tmp)
        else:
            txt[-1]=txt[-1][0:-3]+"';"
        txt=('\n'.join(txt))

        self.html_global_configs.append(
                html_global_config( regex_start = ' *var *input_buttons *=',
                                    regex_end   = '.*;.*',
                                    text        =  txt)
                )
        # input_number  *************************************************
        txt=[]
        tmp="var input_number=["
        for i in [ "'"+y.name+"'" for y in filter( lambda x: x.type=='number' , self) ]:
            tmp += i+","
            if len(tmp)>130:
                tmp+=" "
                txt.append(tmp)
                tmp=' '*18
        if len(tmp)>20:
            tmp=tmp[0:-1]
            tmp+="];"
            txt.append(tmp)
        elif len(txt)==0:
            txt.append("var input_number=[];")   # no number controls
        else:
            txt[-1]=txt[-1][0:-2]+"];"
        txt=('\n'.join(txt))

        self.html_global_configs.append(
                html_global_config( regex_start = r' *var *input_number *= *\[',
                                    regex_end   = r'.*\] *;.*',
                                    text        =  txt)
                )

        # LOADPARAMS  *************************************************
        txt=[]

        txt.append('// [LOLO DOCK LOADPARAMS]')

        txt.append('// Checkboxes')
        max_len=3+max([ len(y.name) for y in filter( lambda x: x.type=='checkbox' , self) ], default=0)
        for i in [ y.name for y in filter( lambda x: x.type=='checkbox' , self) ]:
            tmp="$({:<"+str(max_len)+"s}).prop('checked', (params.original.{:<"+str(max_len)+"s} ? true : false));"
            txt.append( tmp.format( "'#"+i+"'" , i ) )
        txt.append('')

        txt.append('// Numbers')
        max_len=3+max([ len(y.name) for y in filter( lambda x: x.type=='number' , self) ], default=0)
        for i in [ y.name for y in filter( lambda x: x.type=='number' , self) ]:
            tmp="$({:<"+str(max_len)+"s}).val(params.original.{:<"+str(max_len)+"s});"
            txt.append( tmp.format( "'#"+i+"'" , i ) )
        txt.append('')

        txt.append('// Switches')
        max_len=3+max([ len(y.name) for y in filter( lambda x: x.type=='select' , self) ], default=0)
        for i in [ y.name for y in filter( lambda x: x.type=='select' , self) ]:
            tmp="$({:<"+str(max_len)+"s}).val(params.original.{:<"+str(max_len)+"s});"
            txt.append( tmp.format( "'#"+i+"'" , i ) )
        txt.append('')

        txt.append('// Buttons')
        for i in [ y.name for y in filter( lambda x: x.type=='button' , self) ]:
            txt.append( ("if (params.original."+i+"){").ljust(55)+" // "+i )
            txt.append( "  $('#"+i+"').removeClass('btn-default').addClass('btn-primary').data('checked',true);" )
            txt.append( "}else{" )
            txt.append( "  $('#"+i+"').removeClass('btn-primary').addClass('btn-default').data('checked',false);" )
            txt.append( "}" )
        txt.append('')

        txt.append('// [LOLO DOCK LOADPARAMS END]')

        txt=('\n'.join(txt))

        self.html_global_configs.append(
                html_global_config( regex_start = r' *// *\[LOLO DOCK LOADPARAMS\].*',
                                    regex_end   = r'.*// *\[LOLO DOCK LOADPARAMS END\].*',
                                    text        =  txt)
                )



#%% more auxiliar

class txt_buff():
    """Buffer for text ot formating"""
    def __init__(self, tab=4,n=1,end='\n',comment='//'):
        self.indent=' '*tab
        self.end=end
        self.txt=''
        self.tab=tab
        self.n=n
        self.comment=comment
        self.ended=True
    def add(self,txt,end=True):
        if self.ended:
            self.txt+=self.indent*self.n+txt+(self.end if end else '')
        else:
            self.txt+=txt+(self.end if end else '')
        self.ended=end
    def add_comment(self,txt):
        self.txt+=(self.indent*self.n)[:-2]+self.comment+txt+self.end
    def out(self):
        return self.txt
    def indent_plus(self):
        self.n     += 1
    def indent_minus(self):
        self.n     -= 1
    def nl(self):
        self.txt+=self.end   # empty line, without trailing spaces


def fpga_reg_write(f,indent=1):
    """Print Processor-to-FPGA verliog design"""
    txt=txt_buff(n=indent)

    txt.add('//---------------------------------------------------------------------------------')
    txt.add('//')
    txt.add('//  System bus connection')
    txt.nl()
    txt.add('// SO --> MEMORIA --> FPGA')
    txt.nl()
    txt.add('always @(posedge clk)')
    txt.add('if (rst) begin')
    txt.indent_plus()

    for r in f:
        if r.rw:
            txt.add( "{:<20}   <= {:s}{:>2d}'d{:<5d} ; // {:s}".format(
                    r.name, '-' if r.val<0 else ' ' , r.nbits , abs(r.val) , inline(r.desc)
                    ))

    txt.indent_minus()
    txt.add('end else begin')
    txt.indent_plus()
    txt.add('if (sys_wen) begin')
    txt.indent_plus()

    for r in f:
        if r.rw:
            if r.nbits == 1:
                txt.add("if (sys_addr[19:0]=={:5s})  {:<20}  <= |sys_wdata[32-1: 0] ; // {:}".format(
                       r.addr, r.name , inline(r.desc)
                       ) )
            else:
                txt.add("if (sys_addr[19:0]=={:5s})  {:<20}  <=  sys_wdata[{:>2d}-1: 0] ; // {:}".format(
                       r.addr, r.name , r.nbits , inline(r.desc)
                       ))
        else:
            txt.add_comment("if (sys_addr[19:0]=={:5s})  {:<20}  <=  sys_wdata[{:>2d}-1: 0] ; // {:}".format(
                   r.addr, r.name , r.nbits , inline(r.desc)
                   ))
    txt.indent_minus()
    txt.add('end')
    txt.indent_minus()
    txt.add('end')

    return txt.out()


def rd_name(r):
    """Name of the signal read by the bus for register r"""
    if r.reg_read:
        return r.name+'_reg'
    if r.rd_copy:
        return r.name+'_rd'
    return r.name


def fpga_rd_copies(f,indent=1):
    """Registered copies of the read-only signals, read by the bus (from rp_lock-in_pid_h v2.3.17)"""
    txt=txt_buff(n=indent)
    regs=[ r for r in f if r.rd_copy ]
    txt.add('// Registered copies of the read-only signals (wires). The bus reads them instead of the wires, so every')
    txt.add('// input of the read mux of sys_rdata is a register of this clock domain (no long combinational path of')
    txt.add('// the design ends in sys_rdata). They are held while a read is requested (sys_ren: 2 clocks with the')
    txt.add('// address stable in the 2.0 bus; multicycle constraint in prj/v0.94/sdc/red_pitaya.xdc).')
    for r in regs:
        if r.nbits==1:
            txt.add('reg                  {:}_rd;'.format(r.name))
        else:
            txt.add('reg  {:6s} [{:>2d}-1:0] {:}_rd;'.format('signed' if r.signed else '', r.nbits, r.name))
    txt.add('always @(posedge clk) if (!sys_ren) begin')
    txt.indent_plus()
    for r in regs:
        txt.add('{:<20s} <= {:};'.format(r.name+'_rd', r.name))
    txt.indent_minus()
    txt.add('end')
    return txt.out()


def fpga_reg_read(f,indent=1):
    """Print FPGA-to-Processor verliog design (from rp_lock-in_pid_h v2.3.17)"""
    txt=txt_buff(n=indent)

    txt.add('//---------------------------------------------------------------------------------')
    txt.add('// FPGA --> MEMORIA --> SO')
    txt.add('// sys_rdata only changes while a read is requested (sys_ren) and then holds its value. The PS side')
    txt.add('// of the bus (sys_bus_cdc, clock fclk[0]) samples sys_rdata some cycles after sys_ack, asynchronously')
    txt.add('// to clk (adc_clk): a sys_rdata reloaded every cycle with a changing signal could give a mix of bits.')
    txt.add('wire sys_en;')
    txt.add('assign sys_en = sys_wen | sys_ren;')
    txt.nl()
    txt.add('always @(posedge clk, posedge rst)')
    txt.add("if (rst) begin")
    txt.indent_plus()
    txt.add("sys_err <= 1'b0  ;")
    txt.add("sys_ack <= 1'b0  ;")
    txt.indent_minus()
    txt.add("end else begin")
    txt.indent_plus()
    txt.add("sys_err <= 1'b0 ;")
    txt.add("sys_ack <= sys_en;")
    txt.nl()
    txt.add("if (sys_ren) begin")
    txt.indent_plus()
    txt.add("casez (sys_addr[19:0])")
    txt.indent_plus()
    for r in f:
        name = rd_name(r)
        if r.nbits==32:
            txt.add("{:5s} : sys_rdata <= {:>45}   ;".format(r.addr, name).ljust(73)+" // {:}".format(inline(r.desc)))
        elif r.nbits==1:
            txt.add("{:5s} : sys_rdata <=".format(r.addr)+" {  31'b0  ".ljust(28)+
                    ",  {:>15s}  }};".format(name)+" // {:}".format(inline(r.desc)))
        elif r.signed:
            txt.add("{:5s} : sys_rdata <=".format(r.addr)+
                    " {{  {{{:>2d}{{{:s}[{:d}]}}}} ".format(32-r.nbits, name, r.nbits-1).ljust(28)+
                    ",  {:>15s}  }};".format(name)+" // {:}".format(inline(r.desc)))
        else:
            txt.add("{:5s} : sys_rdata <=".format(r.addr)+" {{  {:>2d}'b0 ".format(32-r.nbits).ljust(28)+
                    ",  {:>15s}  }};".format(name)+" // {:}".format(inline(r.desc)))
    txt.add("default   : sys_rdata <=  32'h0        ;")
    txt.indent_minus()
    txt.add("endcase")
    txt.indent_minus()
    txt.add("end")
    txt.indent_minus()
    txt.add("end")

    return txt.out()


def fpga_defs(f,indent=1):
    """Print verliog reg and wire definitions"""
    txt=txt_buff(n=indent)

    for group in unique([ y.group for y in f ]):
        txt.add('// '+group+' --------------------------')
        # reg Unsigned
        for nbits in unique([ y.nbits for y in filter(lambda x: x.group==group and x.rw==True and x.signed==False and x.write_def==True, f) ]):
            if nbits==1:
                txt.add('reg                  '.format(nbits),end=False)
            else:
                txt.add('reg         [{:>2d}-1:0] '.format(nbits),end=False)
            txt.add(','.join( [ y.name for y in filter(lambda x: x.group==group and x.rw==True and x.nbits==nbits and x.signed==False and x.write_def==True, f) ] )
                   +';')
        # reg Signed
        for nbits in unique([ y.nbits for y in filter(lambda x: x.group==group and x.rw==True and x.signed==True and x.write_def==True, f) ]):
            txt.add('reg  signed [{:>2d}-1:0] '.format(nbits),end=False)
            txt.add(','.join( [ y.name for y in filter(lambda x: x.group==group and x.rw==True and x.nbits==nbits and x.signed==True and x.write_def==True, f) ] )
                   +';')
        # wire Unsigned
        for nbits in unique([ y.nbits for y in filter(lambda x: x.group==group and x.rw==False and x.signed==False and x.write_def==True, f) ]):
            if nbits==1:
                txt.add('wire                 '.format(nbits),end=False)
            else:
                txt.add('wire        [{:>2d}-1:0] '.format(nbits),end=False)
            txt.add(','.join( [ y.name for y in filter(lambda x: x.group==group and x.rw==False and x.nbits==nbits and x.signed==False and x.write_def==True, f) ] )
                   +';')
        # wire Signed
        for nbits in unique([ y.nbits for y in filter(lambda x: x.group==group and x.rw==False and x.signed==True and x.write_def==True, f) ]):
            txt.add('wire signed [{:>2d}-1:0] '.format(nbits),end=False)
            txt.add(','.join( [ y.name for y in filter(lambda x: x.group==group and x.rw==False and x.nbits==nbits and x.signed==True and x.write_def==True, f) ] )
                   +';')
        txt.nl()
    return txt.out()


def update_verilog(filename,dock,txt):
    """Update automatic parts in file DOCK place"""
    if type(dock)==str:
        dock=[dock]
    if type(txt)==str:
        txt=[txt]
    with open(filename, 'r') as input:
        with open(filename.replace('.v','_.v'), 'w') as output:
            out=''
            for line in input:
                for i,d in enumerate(dock):
                    if '// [{:s} DOCK]'.format(d) in line:
                        out=d
                        output.write(line)
                        output.write(txt[i])
                        if not txt[i][-1]=='\n':
                            output.write('\n')
                    if '// [{:s} DOCK END]'.format(d) in line and out==d:
                        out=''
                if out=='':
                    output.write(line)
    tnow=datetime.now().strftime("%Y%m%d_%H%M%S")
    os.rename(filename,filename.replace('.v','_'+tnow+'.v.bak'))
    os.rename(filename.replace('.v','_.v'),filename)
    shutil.copymode(filename.replace('.v','_'+tnow+'.v.bak'),filename)


def main_update_params(m,indent=1):
    """Print parameters update in C controller"""
    txt=txt_buff(n=indent)
    for r in [ y for y in filter(lambda x: ( x.fpga_reg!=None) , m) ]:
        #if r.name =='dummy_X':
        #    txt.add('dummy_freeze_regs();')
        txt.add('params[{:3d}].value = {:40s} ; // {:s}'.format(r.index, r.c_update , r.name ))
        #if r.name =='dummy_cnt_clk2':
        #    txt.add('dummy_restore_regs();')
    return txt.out()


def main_update_fpga(f,indent=1):
    """Print parameters FPGA update in C controller"""
    txt=txt_buff(n=indent)
    for r in f:
        if r.no_param:
            txt.add_comment('g_dummy_reg->{:25s}   (not a controller parameter: written by the c/ tools)'.format(r.name))
        elif r.rw:
            txt.add('g_dummy_reg->{:25s} = {:25s};'.format(r.name,r.c_update) )
        else:
            txt.add_comment('g_dummy_reg->{:25s} = {:25s};'.format(r.name,r.c_update) )
    return txt.out()


def main_fpga_regs_reset(f,indent=0):
    """Print parameters reset in C controller"""
    txt=txt_buff(n=indent)
    txt.add('/** Reset all DUMMY */')
    txt.add('void reset_locks(void)')
    txt.add('{')
    txt.indent_plus()
    txt.add('if (g_dummy_reg) {')
    txt.indent_plus()

    for r in f:
        txt.add('g_dummy_reg->{:20s} ={:>7d};'.format(r.name,r.val) )

    txt.indent_minus()
    txt.add('}')
    txt.indent_minus()
    txt.add('}')
    return txt.out()


def main_fpga_regs_def(f,indent=0):
    txt=txt_buff(n=indent)
    txt.add('typedef struct dummy_reg_t {')
    txt.nl()
    txt.indent_plus()

    expected = 0   # index of the next word of the struct
    for r in sorted(f, key=lambda x: x.index):
        if r.index > expected:
            # gap in the register map (reserved addresses): keep the struct aligned with the FPGA
            txt.add(f'/** @brief Offsets 0x{4*expected:03X} - 0x{4*r.index-4:03X}: reserved */')
            txt.add(f'uint32_t reserved_{4*expected:03X}[{r.index-expected}];')
            txt.nl()
        expected = r.index + 1
        txt.add('/** @brief Offset {:s} - {:}'.format(r.addr,r.name))
        for j in r.desc.split('\n'):
            txt.add('  *  '+j)
        txt.add('  *')
        if r.nbits<32:
            txt.add('  *  bits [{:>2d}:{:>2d}] - Reserved'.format(31,r.nbits))
        if r.nbits==1:
            txt.add('  *  bit  [0]     - Data')
        else:
            txt.add('  *  bits [{:>2d}:{:>2d}] - Data'.format(r.nbits-1,0) )
        txt.add('  */')
        if r.signed:
            txt.add('int32_t  {:};'.format(r.name))
        else:
            txt.add('uint32_t {:};'.format(r.name))
        txt.nl()
    txt.indent_minus()
    txt.nl()
    txt.add('} dummy_reg_t;')
    txt.nl()
    txt.add('/* The struct must match the addresses of the FPGA registers (fpga/prj/v0.94/rtl/dummy.v) */')
    for r in sorted(f, key=lambda x: x.index):
        txt.add(f'_Static_assert(offsetof(dummy_reg_t, {r.name}) == 0x{4*r.index:03X}, "dummy_reg_t.{r.name} must be at 0x{4*r.index:03X}");')
    return txt.out()


def main_def(m,indent=1):
    """Print parameters definitions in main.c controller"""
    txt=txt_buff(n=indent)
    txt.nl()
    for r in m:
        if r.signed:
            r_min='{:>12s}'.format(hex(r.min)) if abs(r.min)>2147483647-1 else '{:>12d}'.format(r.min)
            r_max='{:>12s}'.format(hex(r.max)) if abs(r.max)>2147483647-1 else '{:>12d}'.format(r.max)
        else:
            r_min='{:>12s}'.format(hex(r.min)) if r.min>2147483647 else '{:>12d}'.format(r.min)
            r_max='{:>12s}'.format(hex(r.max)) if r.max>2147483647 else '{:>12d}'.format(r.max)
        txt.add('{{ {:32s},  {:>5d}, {:d}, {:d}, {:12s}, {:12s} }},'.format(
                '"'+r.name+'"',r.val , int(r.fpga_update) , int(r.ro), r_min, r_max
                )+' /** '+inline(r.desc)+' **/'
                )
    txt.nl()
    return txt.out()


def main_defh(m,indent=0):
    """Print definition in main.h controller"""
    txt=txt_buff(n=indent)
    txt.nl()
    for r in m:
        txt.add('#define {:<30s}  {:>d}'.format(r.cdef,r.index)            )
    txt.nl()
    return txt.out()


def update_main(filename,dock,txt):
    """Update automatic parts in file DOCK place"""
    if type(dock)==str:
        dock=[dock]
    if type(txt)==str:
        txt=[txt]
    fn1=filename
    tmp=filename.split('.')
    tmp[-2]+='_'
    fn2='.'.join(tmp)
    print('Writing '+filename)
    with open(fn1, 'r') as input:
        with open(fn2, 'w') as output:
            out=''
            for line in input:
                for i,d in enumerate(dock):
                    if '// [{:s} DOCK]'.format(d) in line:
                        out=d
                        output.write(line)
                        output.write(txt[i])
                        if not txt[i][-1]=='\n':
                            output.write('\n')
                    if '// [{:s} DOCK END]'.format(d) in line and out==d:
                        out=''
                if out=='':
                    output.write(line)
    tnow=datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp=filename.split('.')
    tmp[-2]+='_'+tnow
    fn3='.'.join(tmp)+'.bak'

    os.rename(fn1,fn3)
    os.rename(fn2,fn1)
    shutil.copymode(fn3,fn1)   # keep the permissions (e.g. exec bit of py/*.py)


def replace_pattern(filename,pattern,txt):
    """Update automatic parts in file on pattern place"""
    if type(pattern)==str:
        pattern=[pattern]
    if type(txt)==str:
        txt=[txt]
    fn1=filename
    tmp=filename.split('.')
    tmp[-2]+='_'
    fn2='.'.join(tmp)
    print('Writing '+filename)
    with open(fn1, 'r') as input:
        with open(fn2, 'w') as output:
            for line in input:
                out=True
                for i,pat in enumerate(pattern):
                    if bool(re.match(pat,line)):
                        out=False
                        output.write(txt[i])
                        if not txt[i][-1]=='\n':
                            output.write('\n')
                        break
                if out:
                    output.write(line)
    tnow=datetime.now().strftime("%Y%m%d_%H%M%S_p")
    tmp=filename.split('.')
    tmp[-2]+='_'+tnow
    fn3='.'.join(tmp)+'.bak'

    os.rename(fn1,fn3)
    os.rename(fn2,fn1)
    shutil.copymode(fn3,fn1)   # keep the permissions (e.g. exec bit of py/*.py)


#%% HTML controls


class select():
    """Controller for HTML combo box"""
    def __init__(self,idd,items=[],vals=[],default=0):
        self.id      = idd
        self.items   = items
        if len(vals)==0:
            vals=list(range(len(items)))
        self.vals    = vals
        self.default = default
        self.enable  = [True]*len(vals)
        self.hide    = []
        self.hide_group = idd+'_hid'
        for i in range(len(vals)-len(items)):
            self.items.append('-')
            self.enable[-1-i]=False

    def __repr__(self):
        return 'select('+self.id+'): ' + '.'+join(items)

    def __getitem__(self, key):
        if type(key)==int:
            return self.items[key]
        if type(key)==str:
            return self.items.index(key)
        if type(key)==slice:
            return self.items[key]

    def out(self,indent=1):
        txt=txt_buff(n=indent,tab=2)
        txt.add('<select id="{:s}" class="form-control">'.format(self.id))
        txt.indent_plus()
        for i,v in enumerate(self.vals):
            sel=' selected="selected"' if v==self.default else ''
            dtag = ' data-tag="{:}"'.format(self.hide_group) if (v in self.hide) else ' '
            if self.enable[i]:
                txt.add('<option'+dtag+' value="{:d}"{:s}>{:s}</option>'.format(v,sel,self.items[i]))
            else:
                txt.add('<!--option value="{:d}{:s}">{:s}</option-->'.format(v,sel,self.items[i]))
        txt.indent_minus()
        txt.add('</select>')
        return txt.out()

    def regex(self):
        return '[ ]*<select.*id=[\'"]+'+self.id+'[\'"]+[^>]+>.*'

    def regexend(self):
        return '[ ]*</select[ ]*>'


class input_number():
    """Controller for HTML input number"""
    def __init__(self,idd,val=0,minv=0, maxv=8192,step=1):
        if type(idd)==str:
            self.id      = idd
            self.val     = val
            self.min     = minv
            self.max     = maxv
            self.step    = step
        elif type(idd)==html_register:
            self.id      = idd.name
            self.val     = idd.val
            self.min     = idd.min
            self.max     = idd.max
            self.step    = 1

    def __repr__(self):
        return 'input_number('+self.id+')'

    def out(self,indent=1):
        txt=txt_buff(n=indent,tab=2)
        txt.add('<input type="number" autocomplete="off" class="form-control" '+
                'value="{:d}" id="{:s}" step="{:d}" min="{:d}" max="{:d}">'.format(
                    self.val , self.id  , self.step , self.min , self.max
                ))
        return txt.out()
    def regex(self):
        return '[ ]*<input.*id=[\'"]+'+self.id+'[\'"]+[^>]*>.*'
    def regexend(self):
        return '.*'


class input_checkbox():
    """Controller for HTML checkbox"""
    def __init__(self,idd,val=0,text=''):
        if type(idd)==str:
            self.id      = idd
            self.val     = val
            if text=='':
                text=self.id
            self.text    = text
        elif type(idd)==html_register:
            self.id      = idd.name
            self.val     = idd.val
            self.text    = idd.name

    def __repr__(self):
        return 'input_checkbox('+self.id+'): '+self.text

    def out(self,indent=1):
        txt=txt_buff(n=indent,tab=2)
        checked='' if self.val==0 else ' checked'
        txt.add('<input type="checkbox" id="'+self.id+'"'+checked+'>',end=False)
        txt.add(self.text)
        return txt.out()
    def regex(self):
        return '[ ]*<input.*id=[\'"]+'+self.id+'[\'"]+[^>]*>.*'
    def regexend(self):
        return '.*'


class input_button():
    """Controller for HTML generic input"""
    def __init__(self,idd,val=0,text=''):
        if type(idd)==str:
            self.id      = idd
            self.val     = val
            if text=='':
                text=self.id
            self.text    = text
        elif type(idd)==html_register:
            self.id      = idd.name
            self.val     = idd.val
            self.text    = idd.name

    def __repr__(self):
        return 'input_button('+self.id+'): '+self.text

    def out(self,indent=1):
        txt=txt_buff(n=indent,tab=2)
        checked='' if self.val==0 else ''
        txt.add('<button id="'+self.id+'" class="btn btn-primary btn-lg" data-checked="true" disabled>',end=False)
        txt.add(self.text,end=False)
        txt.add('</button>')
        return txt.out()
    def regex(self):
        return '[ ]*<button.*id=[\'"]+'+self.id+'[\'"]+[^>]*>.*'
    def regexend(self):
        return '.*'


def parse_sw(val):
    values=[
             ['in1_m_in2.*','in1-in2'],
             [r'pid(\w)_out.*','PID \\1 out'],
             [r"14'b1?0+\s*",'0'],
             [".*sq_([a-z]*)_b.*",'square \\1 (bin)'],
             [r'ramp_(\w)','Ramp \\1'],
             [r'error_\w*', 'error']
         ]
    for i in values:
        if bool(re.match(i[0],val)):
            return re.sub(i[0],i[1],val)
    return val


def get_muxer_inputs(filename, name):
    """Inputs of the muxer of dummy.v whose select is the register name.

    Looks for an instance of a module whose name contains "muxer" with the port .sel(name). Returns the list of
    the expressions connected to .in0, .in1, ... (in order; '-' for a missing input), or None if there is none.
    """
    code = strip_verilog_comments(open(filename, encoding='utf-8').read())
    for m in re.finditer(r'\b(\w*muxer\w*)\s*(?:#\s*\((?:[^()]|\([^()]*\))*\))?\s*\w+\s*\(', code):
        # ports of the instance: up to the parenthesis that closes it
        depth, k = 1, m.end()
        while k < len(code) and depth:
            depth += {'(': 1, ')': -1}.get(code[k], 0)
            k += 1
        ports = code[m.end():k-1]
        sel = re.search(r'\.sel\s*\(\s*([^()]*?)\s*\)', ports)
        if not sel or sel.group(1) != name:
            continue
        ins = {}
        for pm in re.finditer(r'\.in(\d+)\s*\(((?:[^()]|\([^()]*\))*)\)', ports):
            ins[int(pm.group(1))] = ' '.join(pm.group(2).split())
        if not ins:
            continue
        return [ ins.get(i, '-') for i in range(max(ins) + 1) ]
    return None


def get_muxer(filename, name, names=None):
    """Names of the inputs of the muxer selected by the register name (texts of its combo box), [] if none.

    names: {expression: text} (app.ini [names], labels of the controls); otherwise parse_sw() makes the text.
    """
    ins = get_muxer_inputs(filename, name)
    if not ins:
        return []
    names = names or {}
    return [ names[y] if y in names else parse_sw(y) for y in ins ]


class html_global_config():
    """Collection for HTML configurations for replacement"""
    def __init__(self,regex_start,regex_end,text):
        self.regex_start   = regex_start
        self.regex_end     = regex_end
        if type(text)==str:
            self.text      = text.split('\n')
        elif type(text)==list:
            self.text      = text
        else:
            self.text      = 'ERROR'
            print('ERROR html_global_configs')
    def out(self,indent=1):
        txt=txt_buff(n=indent,tab=2)
        for i in self.text:
            txt.add(i)
        return txt.out()
    def regex(self):
        return self.regex_start
    def regexend(self):
        return self.regex_end


def update_html(filename,h):
    """Update automatic parts in file on pattern place"""
    fn1=filename
    tmp=filename.split('.')
    tmp[-2]+='_'
    fn2='.'.join(tmp)
    print('Writing '+filename)
    with open(fn1, 'r') as input:
        with open(fn2, 'w') as output:
            out=''
            for line in input:
                if out=='':
                    config_list=[ y.control for y in filter( lambda x: x.control!=None , h) ]
                    config_list.extend(h.html_global_configs)
                    for c in config_list:
                        if bool(re.match(c.regex(),line)):
                            out=c.regexend()
                            indent=int(ceil(len( re.search('^([ ]*)[^ ]+',line).group(1) )/2))
                            output.write( c.out(indent=indent) )
                            break
                if out=='':
                    output.write(line)
                elif bool(re.match(out,line)):
                    out=''

    tnow=datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp=filename.split('.')
    tmp[-2]+='_'+tnow
    fn3='.'.join(tmp)+'.bak'

    os.rename(fn1,fn3)
    os.rename(fn2,fn1)
    shutil.copymode(fn3,fn1)   # keep the permissions (e.g. exec bit of py/*.py)


def update_py(filename,h):
    """Update automatic parts in file on pattern place"""
    fn1=filename
    tmp=filename.split('.')
    tmp[-2]+='_'
    fn2='.'.join(tmp)

    with open(fn1, 'r') as input:
        with open(fn2, 'w') as output:
            out=''
            for line in input:
                if out=='':
                    config_list=h
                    for c in config_list:
                        if bool(re.match(c.regex(),line)):
                            out=c.regexend()
                            indent=int(ceil(len( re.search('^([ ]*)[^ ]+',line).group(1) )/2))
                            output.write( c.out(indent=indent) )
                            break
                if out=='':
                    output.write(line)
                elif bool(re.match(out,line)):
                    out=''

    tnow=datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp=filename.split('.')
    tmp[-2]+='_'+tnow
    fn3='.'.join(tmp)+'.bak'

    os.rename(fn1,fn3)
    os.rename(fn2,fn1)
    shutil.copymode(fn3,fn1)   # keep the permissions (e.g. exec bit of py/*.py)


def update_html_controls(filename,dock,txt):
    """Update automatic parts in file DOCK place"""
    if type(dock)==str:
        dock=[dock]
    if type(txt)==str:
        txt=[txt]
    with open(filename, 'r') as input:
        with open(filename.replace('.html','_.html'), 'w') as output:
            out=''
            for line in input:
                for i,d in enumerate(dock):
                    if '<!-- {:s} DOCK -->'.format(d) in line:
                        out=d
                        indent=line.find('<!--')
                        txt[i]= indent*' '+txt[i]
                        txt[i]= txt[i].replace('\n', '\n'+indent*' ')
                        output.write(line)
                        output.write(txt[i])
                        if not txt[i][-1]=='\n':
                            output.write('\n')
                    if '<!-- {:s} DOCK END -->'.format(d) in line and out==d:
                        out=''
                if out=='':
                    output.write(line)
    tnow=datetime.now().strftime("%Y%m%d_%H%M%S")
    os.rename(filename,filename.replace('.v','_'+tnow+'.bak'))
    os.rename(filename.replace('.html','_.html'),filename)



def print_html_combo(idd,label,nbits):
    txt='\n'.join([
        '<div class="panel-group col-xs-12 col-sm-12 col-md-12">',
        '  <form class="form-horizontal" role="form" onsubmit="return false;" novalidate>',
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
        '  <form class="form-horizontal" role="form" onsubmit="return false;" novalidate>',
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
        '  <form class="form-horizontal" role="form" onsubmit="return false;" novalidate>',
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
        '  <form class="form-horizontal" role="form" onsubmit="return false;" novalidate>',
        '    <div class="form-group text-center">\n'
    ])
    txt+='      <button id="dummy_'+idd+'" class="btn btn-primary btn-lg" data-checked="true" disabled>'+label+'</button>\n'
    txt+= '\n'.join([
        '    </div>',
        '  </form>',
        '</div>'
    ])
    return txt


def update_file_match(filename, tag=('start_tag','stop_tag'), txt='', blank=True):
    """Updates file replacing the lines between the tag lines (blank: an empty line after txt)"""
    write_file = True
    for line in fileinput.input( files=(filename) ,backup='_'+datetime.now().strftime("%Y%m%d_%H%M%S")+'.bak',inplace=True) :
        line = line.rstrip()
        if bool(re.match(tag[0],line)):
            if txt:
                line += '\n' + txt
            if blank:
                line += '\n'
            print(line)
            write_file = False
            continue
        if bool(re.match(tag[1],line)):
            write_file = True
        if write_file:
            print(line)


#%% App description file (app.ini): controls of the App
#
# The .ini given to new_project.py is copied into the App as app.ini, and config_tool.py reads it
# every time it regenerates the App. Format:
#
#   [general]
#   AppName        = my_app          # name of the App (folder, URL, info.json)
#   include_genfun = False           # original signal generator (ASG) of Red Pitaya
#   include_pids   = False           # original PID controllers of Red Pitaya
#   register_map   = fixed           # fixed: template registers at 0x000-0x0FC, controls from 0x100
#                                    # legacy: controls right after the template registers (old layout)
#   rp_host / ssh_opts / scp_opts    # for _settings.env (make upload)
#
#   [numberA]                        # one section per control = register name in dummy.v
#   type        = number             # combo | number | checkbox | button | monitor
#   label       = Number A           # text in the web page
#   bits_number = 14                 # combo, number, monitor (checkbox/button: always 1)
#   signed      = True               # number, monitor
#   default     = 0                  # optional: value after reset (not for monitor)
#   options     = off, slow, fast    # optional, combo only: text of the options (0, 1, 2...). Without it, a
#                                    # combo used as the select of a muxer of dummy.v (.sel(comboA)) shows the
#                                    # names of the muxer inputs; otherwise the numbers
#   display     = int                # optional, monitor only: int (default, the raw integer) or volts
#                                    # (raw / 8192 V: 14-bit ADC/DAC scale, 8192 counts = 1 V)
#   scale       = 0.001              # optional, monitor only: show raw * scale ...
#   unit        = s                  # ... with this unit (SI prefixes are added: ms, us...)
#
#   [names]                          # optional: texts of the muxer inputs in the combo boxes (oscA_sw, out1_sw,
#   test_saw    = Test sawtooth      # ... and the combos of the .ini used as muxer selects): wire = text.
#                                    # Default: the label of the control with that name, or the wire name

CONTROL_TYPES = {
    # type      : (html type, bits allowed, signed allowed, read only)
    'combo'     : ('select'  , (1, 8) , False, False),
    'number'    : ('number'  , (1, 32), True , False),
    'checkbox'  : ('checkbox', (1, 1) , False, False),
    'button'    : ('button'  , (1, 1) , False, False),
    'monitor'   : ('monitor' , (1, 32), True , True ),
}

# Address (index = address/4) where the controls of the .ini start with register_map = fixed.
# 0x000-0x0FC is reserved for the registers of the template (see config_tool.py).
USER_REGS_INDEX = 0x100 // 4

# Names already used in dummy.v / the C controller / the web page / the c/ tools by the template
# (stream_*), or reserved for registers of next versions (cnt_clk)
RESERVED_NAMES = {
    'oscA_sw', 'oscB_sw', 'osc_ctrl', 'trig_sw', 'out1_sw', 'out2_sw',
    'slow_out1_sw', 'slow_out2_sw', 'slow_out3_sw', 'slow_out4_sw',
    'in1', 'in2', 'out1', 'out2', 'slow_out1', 'slow_out2', 'slow_out3', 'slow_out4', 'oscA', 'oscB',
    'read_ctrl', 'osc1_filt_off', 'osc2_filt_off', 'osc_raw_mode', 'osc_lockin_mode',
    'cnt_clk', 'cnt_clk2', 'stream_ip', 'stream_port', 'stream_rate', 'stream_cmd',
    'clk', 'rst', 'external_trigger', 'osc1', 'osc2', 'trigger', 'digital_modulation',
    'pwm_cfg_a', 'pwm_cfg_b', 'pwm_cfg_c', 'pwm_cfg_d',
    'pwm_cfg_a_w', 'pwm_cfg_b_w', 'pwm_cfg_c_w', 'pwm_cfg_d_w', 'trigger_signals',
    'sys_addr', 'sys_wdata', 'sys_sel', 'sys_wen', 'sys_ren', 'sys_rdata', 'sys_err', 'sys_ack', 'sys_en',
    'slow_out1_14', 'slow_out2_14', 'slow_out3_14', 'slow_out4_14',
    'slow_out1_au', 'slow_out2_au', 'slow_out3_au', 'slow_out4_au',
    'slow_out1_aux', 'slow_out2_aux', 'slow_out3_aux', 'slow_out4_aux',
}

VERILOG_KEYWORDS = set('''always and assign automatic begin buf bufif0 bufif1 case casex casez cell cmos config
deassign default defparam design disable edge else end endcase endconfig endfunction endgenerate endmodule
endprimitive endspecify endtable endtask event for force forever fork function generate genvar highz0 highz1
if ifnone incdir include initial inout input instance integer join large liblist library localparam
macromodule medium module nand negedge nmos nor noshowcancelled not notif0 notif1 or output parameter
pmos posedge primitive pull0 pull1 pulldown pullup pulsestyle_onevent pulsestyle_ondetect rcmos real
realtime reg release repeat rnmos rpmos rtran rtranif0 rtranif1 scalared showcancelled signed small
specify specparam strong0 strong1 supply0 supply1 table task time tran tranif0 tranif1 tri tri0 tri1
triand trior trireg unsigned use uwire vectored wait wand weak0 weak1 while wire wor xnor xor
logic bit byte int shortint longint struct union enum typedef interface modport class'''.split())

C_KEYWORDS = set('''auto break case char const continue default do double else enum extern float for goto if
inline int long register restrict return short signed sizeof static struct switch typedef union unsigned
void volatile while _Bool _Complex _Imaginary'''.split())

JS_RESERVED = set('''arguments await break case catch class const continue debugger default delete do else
enum eval export extends false finally for function if implements import in instanceof interface let new
null package private protected public return static super switch this throw true try typeof var void
while with yield'''.split())

APP_NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_+-]*$')
REG_NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')


class control():
    """A control of the web page, defined by a section of the .ini, and its register in dummy.v"""
    def __init__(self, name, ctype, label, nbits=1, signed=False, default=0, options=None):
        self.name    = name
        self.type    = ctype
        self.label   = label
        self.nbits   = nbits
        self.signed  = signed
        self.default = default
        self.options = options
        self.scale   = 0       # monitors: 0 = show the integer; otherwise raw * scale [unit]
        self.unit    = ''
        self.htype   = CONTROL_TYPES[ctype][0]
        self.ro      = CONTROL_TYPES[ctype][3]
    @property
    def min(self):
        return -2**(self.nbits-1) if self.signed else 0
    @property
    def max(self):
        return 2**(self.nbits-1)-1 if self.signed else 2**self.nbits-1
    def __repr__(self):
        return f'control({self.name}, {self.type}, {self.nbits} bits, {"signed" if self.signed else "unsigned"})'


class app_config():
    """Contents of an App .ini file, validated"""
    def __init__(self):
        self.app_name       = None
        self.include_genfun = False
        self.include_pids   = False
        self.register_map   = 'fixed'
        self.rp_host        = 'rp-XXXXXX.local'
        self.ssh_opts       = '-l root -p 22'
        self.scp_opts       = '-P 22'
        self.controls       = []
        self.names          = {}      # [names]: wire/expression of a muxer input -> text of the combo box
        self.warnings       = []


def _to_bool(txt, what, errors):
    v = txt.strip().lower()
    if v in ('1', 'yes', 'true', 'on'):
        return True
    if v in ('0', 'no', 'false', 'off'):
        return False
    errors.append(f'{what}: "{txt}" is not a boolean (use True or False)')
    return False


def _to_int(txt, what, errors):
    try:
        return int(txt.strip(), 0)
    except ValueError:
        errors.append(f'{what}: "{txt}" is not an integer')
        return None


def load_app_ini(filename, app_name=None):
    """Read and validate an App .ini file.

    app_name: if given, it replaces [general] AppName.
    Returns an app_config. Raises ValueError with the list of every problem found.
    """
    if not os.path.isfile(filename):
        raise ValueError(f'configuration file not found: {filename}')
    ini = configparser.ConfigParser(inline_comment_prefixes=None)
    ini.optionxform = str   # keep the case of the keys
    try:
        with open(filename, encoding='utf-8') as fd:
            ini.read_file(fd)
    except configparser.Error as e:
        raise ValueError(f'{filename}: {e}'.replace('\n', ' '))

    errors = []
    cfg = app_config()

    gen = { k.lower(): v for k, v in ini['general'].items() } if ini.has_section('general') else None
    if gen is None:
        errors.append('missing section [general]')
        gen = {}
    for k in gen:
        if k not in ('appname', 'include_genfun', 'include_pids', 'register_map', 'rp_host', 'ssh_opts', 'scp_opts'):
            cfg.warnings.append(f'[general] {k}: unknown key, ignored')
    cfg.app_name = app_name if app_name else gen.get('appname', '').strip()
    if not cfg.app_name:
        errors.append('no App name: give it in the command line or as [general] AppName')
    elif not APP_NAME_RE.match(cfg.app_name):
        errors.append(f'App name "{cfg.app_name}": use letters, digits, "_", "+" or "-", starting with a letter')
    if 'include_genfun' in gen:
        cfg.include_genfun = _to_bool(gen['include_genfun'], '[general] include_genfun', errors)
        if cfg.include_genfun:
            # The Vivado 2020.1 FPGA of the App has no signal generator yet (its FIFO IP is not available for
            # 2020.1): the same controller runs with both bitstreams, so the ASG is off everywhere
            cfg.warnings.append('[general] include_genfun = True: the signal generator (ASG) is not available in the '
                                'Ecosystem 2.0 FPGA of this version, it is not included')
            cfg.include_genfun = False
    if 'include_pids' in gen:
        cfg.include_pids   = _to_bool(gen['include_pids']  , '[general] include_pids'  , errors)
    cfg.register_map = gen.get('register_map', 'fixed').strip().lower()
    if cfg.register_map not in ('fixed', 'legacy'):
        errors.append(f'[general] register_map = {cfg.register_map}: use fixed or legacy')
    for k in ('rp_host', 'ssh_opts', 'scp_opts'):
        if k in gen:
            setattr(cfg, k, gen[k].strip())

    seen = {}
    # [names]: texts of the values of the combo boxes made from muxers (wire or expression = text)
    if ini.has_section('names'):
        for k, v in ini['names'].items():
            v = v.strip()
            if not v or '<' in v or '>' in v or "'" in v:
                errors.append(f'[names] {k}: the text must not be empty nor contain <, > or \'')
            else:
                cfg.names[' '.join(k.split())] = v

    for sec in ini.sections():
        if sec in ('general', 'names'):
            continue
        what = f'[{sec}]'
        opts = { k.lower(): v for k, v in ini[sec].items() }
        if not REG_NAME_RE.match(sec):
            errors.append(f'{what}: the section name is the register name: use letters, digits and "_", starting with a letter')
        elif sec in RESERVED_NAMES or sec in VERILOG_KEYWORDS or sec in C_KEYWORDS or sec in JS_RESERVED \
                or keyword.iskeyword(sec):
            errors.append(f'{what}: "{sec}" is a reserved name (used by the template or a keyword)')
        elif sec.lower() in seen:
            # main.h uses DUMMY_<NAME> in upper case: names that differ only in case collide
            errors.append(f'{what}: same name as [{seen[sec.lower()]}] (names must differ in more than the case)')
        seen[sec.lower()] = sec

        ctype = opts.get('type', '').strip().lower()
        if ctype not in CONTROL_TYPES:
            errors.append(f'{what}: type = "{opts.get("type", "")}" unknown, use one of: {", ".join(CONTROL_TYPES)}')
            continue
        known = {'type', 'label', 'bits_number', 'signed', 'default', 'options', 'display', 'scale', 'unit'}
        for k in opts:
            if k not in known:
                cfg.warnings.append(f'{what} {k}: unknown key, ignored')
        label = opts.get('label', sec).strip()
        if '<' in label or '>' in label or "'" in label:
            errors.append(f'{what}: label must not contain <, > or \'')

        bmin, bmax = CONTROL_TYPES[ctype][1]
        if ctype in ('checkbox', 'button'):
            nbits = 1
            if 'bits_number' in opts and opts['bits_number'].strip() != '1':
                cfg.warnings.append(f'{what}: a {ctype} always has 1 bit, bits_number ignored')
        else:
            if 'bits_number' not in opts:
                errors.append(f'{what}: bits_number is required for type {ctype}')
                continue
            nbits = _to_int(opts['bits_number'], f'{what} bits_number', errors)
            if nbits is None:
                continue
            if not bmin <= nbits <= bmax:
                errors.append(f'{what}: bits_number = {nbits} out of range for {ctype} ({bmin}..{bmax})')
                continue

        signed = False
        if 'signed' in opts:
            signed = _to_bool(opts['signed'], f'{what} signed', errors)
            if signed and not CONTROL_TYPES[ctype][2]:
                cfg.warnings.append(f'{what}: a {ctype} is unsigned, signed ignored')
                signed = False

        c = control(sec, ctype, label, nbits, signed)

        if ctype == 'number' and nbits > 24:
            cfg.warnings.append(f'{what}: {nbits} bits: the controller keeps values as float (24 bits of '
                                f'mantissa), values beyond +-2^24 are not exact')

        if 'default' in opts:
            if c.ro:
                cfg.warnings.append(f'{what}: a monitor has no default, ignored')
            else:
                d = _to_int(opts['default'], f'{what} default', errors)
                if d is not None:
                    if not c.min <= d <= c.max:
                        errors.append(f'{what}: default = {d} out of range ({c.min}..{c.max})')
                    else:
                        c.default = d

        if 'options' in opts:
            if ctype != 'combo':
                cfg.warnings.append(f'{what}: options is only for combo, ignored')
            else:
                items = [ y.strip() for y in opts['options'].split(',') ]
                if len(items) > 2**nbits:
                    errors.append(f'{what}: {len(items)} options do not fit in {nbits} bits')
                elif any( (not y) or ('<' in y) or ('>' in y) for y in items ):
                    errors.append(f'{what}: empty option or option with < >')
                else:
                    c.options = items

        # How a monitor is shown in the web page (Raw Mode always shows the integer)
        if any(k in opts for k in ('display', 'scale', 'unit')):
            if ctype != 'monitor':
                cfg.warnings.append(f'{what}: display/scale/unit are only for monitors, ignored')
            else:
                disp = opts.get('display', 'scaled' if 'scale' in opts else 'int').strip().lower()
                unit = opts.get('unit', '').strip()
                if unit and not re.match(r'^[A-Za-z0-9%/._ -]{1,12}$', unit):
                    errors.append(f'{what}: unit = "{unit}": up to 12 letters, digits, %, /, ., _, - or spaces')
                if disp == 'int':
                    if 'scale' in opts or unit:
                        cfg.warnings.append(f'{what}: display = int: scale/unit ignored')
                elif disp == 'volts':
                    c.scale, c.unit = 1/8192, (unit if unit else 'V')
                    if 'scale' in opts:
                        cfg.warnings.append(f'{what}: display = volts: scale ignored (1/8192)')
                elif disp == 'scaled':
                    try:
                        c.scale = float(opts.get('scale', ''))
                    except ValueError:
                        errors.append(f'{what}: scale = "{opts.get("scale", "")}" is not a number')
                    else:
                        if c.scale == 0 or c.scale != c.scale or abs(c.scale) == float('inf'):
                            errors.append(f'{what}: scale must be a finite number other than 0')
                    c.unit = unit
                else:
                    errors.append(f'{what}: display = "{disp}": use int, volts or scaled (with scale = ...)')

        cfg.controls.append(c)

    if errors:
        raise ValueError('\n'.join(errors))
    return cfg


#%% HTML panels of the controls (docks of index.html)

def html_control_panel(c):
    """HTML of the web page element for control c (not monitors)"""
    idd = 'dummy_' + c.name
    if c.type == 'combo':
        items = c.options if c.options else [ f'opt{i}' for i in range(2**c.nbits) ]
        lines = [ '<div class="panel-group col-xs-12 col-sm-12 col-md-12">',
                  '  <form class="form-horizontal" role="form" onsubmit="return false;" novalidate>',
                  '    <div class="form-group">',
                  f'      <label for="{idd}" class="col-xs-4 control-label">{c.label}</label>',
                  '      <div class="col-xs-8">',
                  f'        <select id="{idd}" class="form-control">' ]
        for i, t in enumerate(items):
            sel = ' selected="selected"' if i == c.default else ' '
            lines.append(f'          <option  value="{i}"{sel}>{t}</option>')
        lines += [ '        </select>', '      </div>', '    </div>', '  </form>', '</div>' ]
    elif c.type == 'number':
        lines = [ '<div class="panel-group col-xs-12 col-sm-12 col-md-12">',
                  '  <form class="form-horizontal" role="form" onsubmit="return false;" novalidate>',
                  '    <div class="form-group">',
                  f'      <label for="{idd}" class="col-xs-4 control-label">{c.label}</label>',
                  '      <div class="col-xs-4 col-sm-8">',
                  f'        <input type="number" autocomplete="off" class="form-control" value="{c.default}" id="{idd}" step="1" min="{c.min}" max="{c.max}">',
                  f'        <span style="display: none;" class="input-group-btn" id="{idd}_apply">',
                  '          <button type="button" class="btn btn-primary btn-lg"><span class="glyphicon glyphicon-ok-circle"></span></button>',
                  '        </span>', '      </div>', '    </div>', '  </form>', '</div>' ]
    elif c.type == 'checkbox':
        lines = [ '<div class="panel-group col-xs-12 col-sm-12 col-md-12">',
                  '  <form class="form-horizontal" role="form" onsubmit="return false;" novalidate>',
                  '    <div class="checkbox" style="padding-bottom: 12px;">',
                  '      <label class="group-label">',
                  f'        <input type="checkbox" id="{idd}"{" checked" if c.default else ""}>{c.label}',
                  '      </label>', '    </div>', '  </form>', '</div>' ]
    elif c.type == 'button':
        lines = [ '<div class="panel-group col-xs-12 col-sm-12 col-md-12">',
                  '  <form class="form-horizontal" role="form" onsubmit="return false;" novalidate>',
                  '    <div class="form-group text-center">',
                  f'      <button id="{idd}" class="btn btn-primary btn-lg" data-checked="true" disabled>{c.label}</button>',
                  '    </div>', '  </form>', '</div>' ]
    else:
        raise ValueError(f'html_control_panel: {c.type}')
    return '\n'.join(lines)


def html_monitor_panel(c):
    """HTML of a monitor (read only value + bar)"""
    idd = 'dummy_' + c.name
    return '\n'.join([
        '<div class="panel-group col-xs-12 col-sm-6 col-md-6">',
        f'  <h2><label class="group-label" for="{idd}">{c.label}</label></h2>',
        f'  <h2><span class="label label-info" style="display:block;" id="{idd}">Value</span></h2>',
        '  <div class="progress" style="height: 5px;">',
        f'    <div id="{idd}_bar" class="progress-bar progress-bar-success" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" style="width:0%; height: 5px;" ></div>',
        '  </div>',
        '</div>' ])


def update_html_dock(filename, dock, txt):
    """Replace the lines between <!-- dock --> and <!-- dock END --> with txt, indented as the marker"""
    with open(filename, encoding='utf-8') as fd:
        lines = fd.read().split('\n')
    start = [ i for i, l in enumerate(lines) if l.strip() == f'<!-- {dock} -->' ]
    end   = [ i for i, l in enumerate(lines) if l.strip() == f'<!-- {dock} END -->' ]
    if len(start) != 1 or len(end) != 1 or end[0] < start[0]:
        raise ValueError(f'{filename}: markers <!-- {dock} --> / <!-- {dock} END --> not found once each')
    indent = lines[start[0]].find('<!--')
    new = [ (' '*indent + l) if l else '' for l in txt.split('\n') ] if txt else []
    lines = lines[:start[0]+1] + new + lines[end[0]:]
    with open(filename, 'w', encoding='utf-8') as fd:
        fd.write('\n'.join(lines))


def update_c_define(filename, name, value):
    """Set the value of '#define name value' in a C header"""
    with open(filename, encoding='utf-8') as fd:
        txt = fd.read()
    new, n = re.subn(rf'^(#define\s+{name}\s+)\S+', rf'\g<1>{value}', txt, flags=re.M)
    if n != 1:
        raise ValueError(f'{filename}: #define {name} not found')
    with open(filename, 'w', encoding='utf-8') as fd:
        fd.write(new)


def added_regs_doc(f, controls, indent=1, removed=()):
    """Comment block of dummy.v that lists the registers of the controls (ADDED REGS dock).

    removed: registers removed from app.ini that the user code still uses (config_tool.py keeps reporting them)
    """
    txt = txt_buff(n=indent)
    for c in controls:
        r = f[c.name]
        rng = f'({c.min:>11d} --> {c.max:<11d})'
        kind = 'read only (wire, drive it)' if c.ro else 'reg written by the web page'
        txt.add(f'//   {c.name:<15s} {r.addr} {c.nbits:2d} bits {"  " if c.signed else "un"}signed {rng} {kind}')
    if removed:
        txt.add('//   removed from app.ini but still used in the user code: ' + ', '.join(removed))
    return txt.out()



#%% Changes of app.ini in an existing App (config_tool.py)
#
# The ADDED REGS block of dummy.v lists the registers of the controls of the last generation (name, address, bits,
# signed, read only). config_tool.py compares it with app.ini before writing anything: controls added, removed,
# changed or moved to another address (with register_map = fixed the controls take consecutive addresses, so removing
# one moves the next ones), and likely renames (one removed and one added of the same kind). After writing, the
# names of the removed controls that are still used outside the generated parts (the logic of the user in dummy.v,
# own code in index.html, src/, py/) are reported: the FPGA or the C would not compile, or the page would use a
# control that does not exist any more.

_ADDED_REG_RE = re.compile(r"^\s*//\s+([A-Za-z]\w*)\s+20'h([0-9A-Fa-f]+)\s+(\d+)\s+bits\s+(un)?signed\s+\(.*?\)\s+(.*)$")


def read_added_regs(dummy_v):
    """{name: dict(addr, nbits, signed, ro)} of the ADDED REGS block of dummy.v (last generation); {} if none"""
    out = {}
    if not os.path.isfile(dummy_v):
        return out
    inside = False
    for line in open(dummy_v, encoding='utf-8'):
        if '[ADDED REGS DOCK]' in line:
            inside = True
            continue
        if '[ADDED REGS DOCK END]' in line:
            break
        if inside:
            mr = re.match(r'^\s*//\s+removed from app.ini but still used in the user code:\s*(.*)$', line)
            if mr:
                out.setdefault('__removed__', []).extend(y.strip() for y in mr.group(1).split(',') if y.strip())
                continue
            m = _ADDED_REG_RE.match(line)
            if m:
                out[m.group(1)] = { 'addr': int(m.group(2), 16), 'nbits': int(m.group(3)),
                                    'signed': m.group(4) is None, 'ro': m.group(5).startswith('read only') }
    return out


def ini_changes(prev, cfg, f):
    """Differences between the registers of the last generation (read_added_regs()) and app.ini.

    f: fpga_registers with the addresses of app.ini. Returns a dict with lists: added, removed, changed (texts),
    moved (name, old, new address) and renames (old, new) guessed: one removed and one added with the same width,
    sign and kind (read only or not), the only such pair.
    """
    pending = prev.get('__removed__', [])
    prev = { k: v for k, v in prev.items() if k != '__removed__' }
    new = { c.name: { 'addr': 4*f[c.name].index, 'nbits': c.nbits, 'signed': c.signed, 'ro': c.ro } for c in cfg.controls }
    added   = [ n for n in new if n not in prev ]
    removed = [ n for n in prev if n not in new ]
    changed, moved = [], []
    for n in new:
        if n not in prev:
            continue
        a, b = prev[n], new[n]
        what = []
        if a['nbits'] != b['nbits']:
            what.append(f'{a["nbits"]} -> {b["nbits"]} bits')
        if a['signed'] != b['signed']:
            what.append('signed' if b['signed'] else 'unsigned')
        if a['ro'] != b['ro']:
            what.append('now read only (monitor)' if b['ro'] else 'now written by the web page (not a monitor)')
        if what:
            changed.append(f'{n}: ' + ', '.join(what))
        if a['addr'] != b['addr']:
            moved.append((n, a['addr'], b['addr']))
    renames = []
    for r in removed:
        cand = [ a for a in added if (new[a]['nbits'], new[a]['signed'], new[a]['ro']) ==
                 (prev[r]['nbits'], prev[r]['signed'], prev[r]['ro']) ]
        back = [ y for y in removed if cand and (prev[y]['nbits'], prev[y]['signed'], prev[y]['ro']) ==
                 (new[cand[0]]['nbits'], new[cand[0]]['signed'], new[cand[0]]['ro']) ]
        if len(cand) == 1 and len(back) == 1:
            renames.append((r, cand[0]))
    # removed before and still used in the user code at the last run (reported until that code is fixed)
    pending = [ n for n in pending if n not in new and n not in removed ]
    return { 'added': added, 'removed': removed, 'changed': changed, 'moved': moved, 'renames': renames,
             'pending': pending }


def _strip_docks(lines):
    """Lines (number, text) outside the generated blocks ([... DOCK] .. [... DOCK END], automatic parts)"""
    out, inside = [], False
    for i, l in enumerate(lines, 1):
        if re.search(r'\[[\w ]+ DOCK\]', l) or re.search(r'<!-- [\w ]+ DOCK -->', l):
            inside = True
            continue
        if re.search(r'\[[\w ]+ DOCK END\]', l) or re.search(r'<!-- [\w ]+ DOCK END -->', l):
            inside = False
            continue
        if not inside:
            out.append((i, l))
    return out


def stale_references(names, dummy_v=None):
    """Uses of the registers names (removed from app.ini) outside the generated parts of the App sources.

    Verilog: the identifier in dummy.v and dummy/*.v (without comments); index.html: dummy_<name>;
    src/*.c|h: DUMMY_<NAME>, dummy_<name>, ->name; py/*.py: 'name' / "name". Returns [(file, line, text)].
    """
    dummy_v = dummy_v or DUMMY_V
    found = []
    if not names:
        return found
    vfiles = [dummy_v] + sorted(glob_files(os.path.join(os.path.dirname(dummy_v), 'dummy'), ('.v', '.sv')))
    for fn in vfiles:
        orig = open(fn, encoding='utf-8', errors='replace').read()
        code_lines = strip_verilog_comments(orig).split('\n')        # same line numbers, without comments
        for i, l in _strip_docks(orig.split('\n')):
            code = code_lines[i-1] if i-1 < len(code_lines) else ''
            for n in names:
                if re.search(rf'(?<![\w$.]){re.escape(n)}(?!\w)', code):
                    found.append((fn, i, l.strip()))
    pats = []
    for n in names:
        pats.append(('index.html', re.compile(rf'\bdummy_{re.escape(n)}\b')))
    for fn, pat in pats:
        if os.path.isfile(fn):
            for i, l in _strip_docks(open(fn, encoding='utf-8', errors='replace').read().split('\n')):
                if pat.search(l):
                    found.append((fn, i, l.strip()))
    for fn in sorted(glob_files('src', ('.c', '.h'))) + sorted(glob_files('py', ('.py',))):
        for i, l in _strip_docks(open(fn, encoding='utf-8', errors='replace').read().split('\n')):
            for n in names:
                if (re.search(rf'\b(DUMMY_{re.escape(n.upper())}|dummy_{re.escape(n)})\b|->\s*{re.escape(n)}\b', l) or
                        (fn.endswith('.py') and re.search(rf'[\'"]{re.escape(n)}[\'"]', l))):
                    found.append((fn, i, l.strip()))
    return found


def glob_files(folder, exts):
    if not os.path.isdir(folder):
        return []
    return [ os.path.join(folder, y) for y in os.listdir(folder) if y.endswith(exts) ]


def rename_in_sources(old, new, dummy_v=None):
    """Rename the register old to new in the user code of the App (outside the generated parts it is regenerated
    anyway): the identifier in dummy.v, dummy_<old> in index.html, DUMMY_<OLD> / dummy_<old> / ->old in src/.
    Returns the list of (file, number of replacements)."""
    dummy_v = dummy_v or DUMMY_V
    done = []
    edits = [ (dummy_v, [ (rf'(?<![\w$.]){re.escape(old)}(?!\w)', new) ]),
              ('index.html', [ (rf'\bdummy_{re.escape(old)}\b', f'dummy_{new}') ]) ]
    for fn in sorted(glob_files('src', ('.c', '.h'))):
        edits.append((fn, [ (rf'\bDUMMY_{re.escape(old.upper())}\b', f'DUMMY_{new.upper()}'),
                            (rf'\bdummy_{re.escape(old)}\b', f'dummy_{new}'),
                            (rf'->(\s*){re.escape(old)}\b', rf'->\g<1>{new}') ]))
    for fn, subs in edits:
        if not os.path.isfile(fn):
            continue
        txt = open(fn, encoding='utf-8').read()
        n = 0
        for pat, rep in subs:
            txt, k = re.subn(pat, rep, txt)
            n += k
        if n:
            with open(fn, 'w', encoding='utf-8') as fd:
                fd.write(txt)
            done.append((fn, n))
    return done


#%% Names of the values of the combo boxes (c/names_dic.txt)

def html_select_options(filename, idd):
    """[(value, text)] of the enabled options of <select id="idd"> in an HTML file ([] if not found)"""
    txt = open(filename, encoding='utf-8').read()
    m = re.search(r'<select[^>]*\bid=["\']' + re.escape(idd) + r'["\'][^>]*>(.*?)</select\s*>', txt, flags=re.S)
    if not m:
        return []
    body = re.sub(r'<!--.*?-->', '', m.group(1), flags=re.S)
    return [ (int(v), ' '.join(t.split())) for v, t in
             re.findall(r'<option[^>]*\bvalue=["\'](-?\d+)["\'][^>]*>(.*?)</option\s*>', body, flags=re.S) ]


def write_names_dic(filename, app_name, entries):
    """c/names_dic.txt: one line per value of each combo box: register, address, value, text.

    entries: [(register, address, source, [(value, text)])]
    """
    lines = [ f'# names_dic.txt: texts of the values of the combo boxes of the App {app_name}',
              '# Generated by config_tool.py (-n, also -a) from app.ini (options, [names], labels) and the muxers of',
              '# fpga/prj/v0.94/rtl/dummy.v (inputs of the muxer whose .sel is the register). Do not edit it: change',
              '# app.ini / dummy.v and run config_tool.py again. Selects without a muxer nor options (e.g. Ext Trig) keep',
              '# the options written in index.html. Registers without a <select> (e.g. read_ctrl) and output selects',
              '# without a muxer in dummy.v (e.g. slow_out1_sw/slow_out2_sw of the template: output fixed at 0) are not listed.',
              '# Format: <register> <address> <value> <text>   (the text is the rest of the line)',
              '' ]
    for reg, addr, src, items in entries:
        lines.append(f'# {reg}: {src}')
        for v, t in items:
            lines.append(f'{reg:<16s} 0x{addr:03X} {v:3d} {t}')
        lines.append('')
    os.makedirs(os.path.dirname(filename) or '.', exist_ok=True)
    with open(filename, 'w', encoding='utf-8') as fd:
        fd.write('\n'.join(lines))


#%% Verilog modules of dummy.v (config_tool.py -t)
#
# The Vivado projects (fpga/ 2020.1 and fpga_eco1/ 2015.2) read dummy.v and only the files of dummy/ that define a
# module instantiated in dummy.v, or in one of those modules (recursively). The list is written in the tcl scripts
# between "# Automatically added dummy modules" and "# End of automatic part". Modules that are not found in dummy/
# nor in the RedPitaya base design are reported (the synthesis would fail).

_INST_NOT_MODULE = VERILOG_KEYWORDS | {'else', 'begin', 'end', 'return'}
_INST_RE = re.compile(r'(?<![\w.$`\'])([A-Za-z_]\w*)(?:\s*(#\s*\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\))\s*|\s+)'
                      r'([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)?\(')


def strip_verilog_comments(txt):
    """Verilog text without comments (// ... and /* ... */) and strings"""
    txt = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', txt)
    txt = re.sub(r'/\*.*?\*/', lambda m: ' ' + '\n' * m.group(0).count('\n'), txt, flags=re.S)   # keeps the lines
    return re.sub(r'//[^\n]*', '', txt)


def verilog_modules_defined(txt):
    """Names of the modules defined in a Verilog text"""
    return re.findall(r'\b(?:module|macromodule)\s+([A-Za-z_]\w*)', strip_verilog_comments(txt))


def verilog_instances(txt):
    """Names of the modules instantiated in a Verilog text (instances "mod [#(...)] name (" outside comments)"""
    code = strip_verilog_comments(txt)
    found = []
    for m in _INST_RE.finditer(code):
        mod, inst = m.group(1), m.group(3)
        if mod in _INST_NOT_MODULE or inst in _INST_NOT_MODULE:
            continue
        if m.group(2) is None and mod in ('function', 'task'):
            continue
        if mod not in found:
            found.append(mod)
    return found


def _modules_of_dir(folder, recursive=False, exclude=()):
    """{module: path} of the .v/.sv files of folder"""
    mods = {}
    for root, dirs, files in os.walk(folder):
        for fn in sorted(files):
            path = os.path.join(root, fn)
            if not fn.endswith(('.v', '.sv')) or os.path.abspath(path) in exclude:
                continue
            try:
                txt = open(path, encoding='utf-8', errors='replace').read()
            except OSError:
                continue
            for m in verilog_modules_defined(txt):
                mods.setdefault(m, path)
        if not recursive:
            break
    return mods


def dummy_module_files(dummy_v=None):
    """Files of the folder dummy/ needed by dummy.v, and a report.

    Returns a dict:
      files     sorted file names (of dummy/) that define the modules instantiated by dummy.v, recursively
      modules   {module: file name} of those modules
      unused    files of dummy/ not needed
      base      modules instantiated that are not in dummy/ but in the RedPitaya base design
      missing   modules instantiated that are found nowhere (the synthesis would fail)
      warnings  list of texts (missing modules, modules defined twice or clashing with the base design)
    """
    dummy_v = dummy_v or DUMMY_V
    ddir = os.path.join(os.path.dirname(dummy_v), 'dummy')
    own = {}           # module -> file name in dummy/
    warnings = []
    for fn in sorted(os.listdir(ddir)) if os.path.isdir(ddir) else []:
        if not fn.endswith(('.v', '.sv')):
            continue
        txt = open(os.path.join(ddir, fn), encoding='utf-8', errors='replace').read()
        for m in verilog_modules_defined(txt):
            if m in own and own[m] != fn:
                warnings.append(f'module {m} is defined in dummy/{own[m]} and dummy/{fn} (the first one is used)')
                continue
            own[m] = fn
    # modules of the base designs (2020.1: fpga/rtl/ + fpga/prj/v0.94/rtl/; 2015.2: fpga_eco1/rtl/)
    exclude = { os.path.abspath(dummy_v) }
    base = {}
    base.update(_modules_of_dir(os.path.join('fpga', 'rtl'), recursive=True))
    base.update(_modules_of_dir(os.path.dirname(dummy_v), exclude=exclude))
    base.update(_modules_of_dir(os.path.join('fpga_eco1', 'rtl')))
    for m, fn in own.items():
        if m in base:
            warnings.append(f'module {m} of dummy/{fn} has the name of a module of the RedPitaya design '
                            f'({os.path.relpath(base[m])}): rename it')
    modules, todo, from_base, missing = {}, [], [], []
    todo = [ (m, 'dummy.v') for m in verilog_instances(open(dummy_v, encoding='utf-8').read()) ]
    seen = set()
    while todo:
        m, where = todo.pop(0)
        if m in seen:
            continue
        seen.add(m)
        if m in own:
            modules[m] = own[m]
            sub = verilog_instances(open(os.path.join(ddir, own[m]), encoding='utf-8', errors='replace').read())
            todo += [ (y, 'dummy/' + own[m]) for y in sub ]
        elif m in base:
            from_base.append(m)
        else:
            missing.append(m)
            warnings.append(f'module {m} (instantiated in {where}) not found in dummy/ nor in the RedPitaya design: '
                            f'put its file in {ddir}/')
    files = sorted(set(modules.values()), key=str.lower)
    allv = sorted([ y for y in os.listdir(ddir) if y.endswith(('.v', '.sv')) ], key=str.lower) if os.path.isdir(ddir) else []
    return { 'files': files, 'modules': modules, 'unused': [ y for y in allv if y not in files ],
             'base': from_base, 'missing': missing, 'warnings': warnings }


#%% Logo of the App (resources/logo.svg -> resources/logo.png and <App>/info/icon.png)
#
# The generic logo of rp_dummy2 (resources/logo.svg, 100 x 100) has an element with id="AppName" whose text
# ("APP NAME LONG") is replaced by the name of the App. The SVG is then rendered to a 100 x 100 PNG with the first
# tool available: the Python module cairosvg, rsvg-convert (librsvg) or inkscape. In the generic logo the name is
# an Inkscape "flowed text" (<flowRoot>/<flowPara>, SVG 1.2) that neither cairosvg nor librsvg draw: it is turned
# into a plain <text>, centred where the flowed text was and with a smaller font if the name is longer than the
# placeholder, so the three tools give the same picture.

LOGO_SIZE  = 100
LOGO_TOOLS = ('cairosvg', 'rsvg-convert', 'inkscape')
LOGO_INSTALL_HINT = ('to draw the App name on the logo install one of: the Python module cairosvg '
                     '(pip install cairosvg), rsvg-convert (sudo apt install librsvg2-bin) or Inkscape '
                     '(sudo apt install inkscape)')

# Advance widths of Liberation Sans / Arial (1/1000 em), to fit the name in the box of the logo
_ARIAL_W = dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ',
                    [667,667,722,722,667,611,778,722,278,500,667,556,833,722,778,667,778,722,667,611,722,667,944,667,667,611]))
_ARIAL_W.update(zip('abcdefghijklmnopqrstuvwxyz',
                    [556,556,500,556,556,278,556,556,222,222,500,222,833,556,556,556,556,333,500,278,556,500,722,500,500,500]))
_ARIAL_W.update({ c: 556 for c in '0123456789_' })
_ARIAL_W.update({ ' ': 278, '-': 333, '+': 584, '.': 278 })


def _text_em(txt):
    """Width of txt in em (Liberation Sans)"""
    return sum(_ARIAL_W.get(c, 667) for c in txt) / 1000.0


# Font size limits of the name, relative to the size of the placeholder: below LOGO_MIN_FONT (about 6 px in the
# 100 px icon) a long name is split in two lines (at most LOGO_TWO_LINES_FONT each, so both fit in the box) and,
# if a line still does not fit at the minimum size, it is cut with an ellipsis.
LOGO_MIN_FONT       = 0.55
LOGO_TWO_LINES_FONT = 0.72


def _logo_fit(txt, width, fs_min):
    """txt cut with an ellipsis so that it fits in width at the font size fs_min"""
    if _text_em(txt) * fs_min <= width:
        return txt
    while len(txt) > 1 and _text_em(txt + '\u2026') * fs_min > width:
        txt = txt[:-1]
    return txt + '\u2026'


def _logo_lines(name, fs0, width):
    """([lines], font size) of the name in a box of the given width: one line at the size of the placeholder (or
    smaller, down to LOGO_MIN_FONT x fs0); otherwise two lines split at a separator (_ - + space) near the middle
    (or at the middle), each one cut with an ellipsis if needed."""
    fs_min = LOGO_MIN_FONT * fs0
    em = _text_em(name)
    if em <= 0:
        return [name], fs0
    fs = min(fs0, width / em)
    if fs >= fs_min or len(name) < 2:
        return [name], max(fs, min(fs0, fs_min))
    total = em
    best = None
    for i in range(1, len(name)):
        if name[i-1] in '_-+ ' or name[i] in '_-+ ':
            d = abs(_text_em(name[:i]) - total / 2)
            if best is None or d < best[0]:
                best = (d, i)
    i = best[1] if best and best[0] < total / 4 else max(1, len(name) // 2)
    lines = [ name[:i].rstrip(' '), name[i:].lstrip(' ') ]
    fs2 = min(LOGO_TWO_LINES_FONT * fs0, min(width / max(_text_em(y), 1e-9) for y in lines))
    fs2 = max(fs2, fs_min)
    return [ _logo_fit(y, width, fs2) for y in lines ], fs2


def _xml_escape(txt):
    return txt.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _style_get(style, key):
    m = re.search(r'(?:^|;)\s*' + re.escape(key) + r'\s*:\s*([^;]*)', style)
    return m.group(1).strip() if m else None


def _style_set(style, key, value):
    parts = [ y for y in style.split(';') if y.strip() and y.split(':')[0].strip() != key ]
    return ';'.join(parts + [f'{key}:{value}'])


def _attr(tag_text, name):
    m = re.search(r'\s' + re.escape(name) + r'="([^"]*)"', tag_text)
    return m.group(1) if m else None


def logo_set_name(svg, name):
    """SVG text of the logo with the text of the element id="AppName" replaced by name.

    A flowed text (<flowPara id="AppName"> in a <flowRoot>) becomes a <text id="AppName">. Returns the new SVG text;
    raises ValueError if there is no element id="AppName".
    """
    m = re.search(r'<([A-Za-z][\w:.-]*)\b[^>]*\bid="AppName"[^>]*>', svg)
    if not m:
        raise ValueError('no element with id="AppName"')
    tag = m.group(1)
    ename = _xml_escape(name)
    if tag.endswith('flowPara'):
        # the <flowRoot> that holds it, with its <flowRegion><rect .../>
        fr_start = svg.rfind('<flowRoot', 0, m.start())
        fr_end = svg.find('</flowRoot>', m.end())
        if fr_start < 0 or fr_end < 0:
            raise ValueError('flowPara id="AppName" outside a flowRoot')
        fr_end += len('</flowRoot>')
        root = svg[fr_start:fr_end]
        root_tag = root[:root.index('>') + 1]
        rect = re.search(r'<rect\b[^>]*>', root)
        if not rect:
            raise ValueError('flowRoot of id="AppName" without a flowRegion rect')
        rx, ry, rw = (float(_attr(rect.group(0), k) or 0) for k in ('x', 'y', 'width'))
        para_style = _attr(m.group(0), 'style') or ''
        fs_txt = _style_get(para_style, 'font-size') or _style_get(_attr(root_tag, 'style') or '', 'font-size') or '10px'
        fs0 = float(re.match(r'[\d.]+', fs_txt).group(0))
        # vertical: the centre of the capitals stays where the first line of the flowed text was
        # (first baseline at the top of the region + ascent 0.905 em; capitals 0.716 em high)
        yc = ry + 0.905 * fs0 - 0.358 * fs0
        x = rx + rw / 2
        lines, fs = _logo_lines(name, fs0, 0.94 * rw)
        if len(lines) == 1:
            ys = [ yc + 0.358 * fs ]
        else:                                  # two lines around the same centre, 1.15 em apart
            ys = [ yc - 0.575 * fs + 0.358 * fs, yc + 0.575 * fs + 0.358 * fs ]
        style = para_style
        for k in ('line-height', 'text-align', 'text-anchor', 'font-size'):
            style = ';'.join(y_ for y_ in style.split(';') if y_.split(':')[0].strip() not in (k,))
        style = _style_set(style, 'font-size', f'{fs:.4f}px')
        style = _style_set(style, 'text-anchor', 'middle')
        style = _style_set(style, 'text-align', 'center')
        transform = _attr(root_tag, 'transform')
        head = ('<text xml:space="preserve" id="AppName"' + (f' transform="{transform}"' if transform else '') +
                f' x="{x:.4f}" y="{ys[0]:.4f}" style="{style}">')
        if len(lines) == 1:
            new = head + _xml_escape(lines[0]) + '</text>'
        else:
            new = head + ''.join(f'<tspan x="{x:.4f}" y="{yy:.4f}">{_xml_escape(t)}</tspan>'
                                 for t, yy in zip(lines, ys)) + '</text>'
        return svg[:fr_start] + new + svg[fr_end:]
    # <text>/<tspan>/other element: replace its text (the first non-blank text inside it; others removed)
    end = svg.find(f'</{tag}>', m.end())
    if end < 0:
        raise ValueError(f'element id="AppName" (<{tag}>) not closed')
    inner = svg[m.end():end]
    done = [False]
    def rep(mm):
        if not mm.group(1).strip():
            return mm.group(0)
        if done[0]:
            return '><'
        done[0] = True
        return '>' + ename + '<'
    if '<' not in inner:
        inner = ename
    else:
        inner = re.sub(r'>([^<]*)<', rep, '>' + inner + '<')[1:-1]
        if not done[0]:
            inner = ename + inner
    return svg[:m.end()] + inner + svg[end:]


def png_size(path):
    """(width, height) of a PNG file, or None"""
    try:
        with open(path, 'rb') as fd:
            head = fd.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return int.from_bytes(head[16:20], 'big'), int.from_bytes(head[20:24], 'big')


def _logo_tool_available(tool):
    if tool == 'cairosvg':
        try:
            import cairosvg  # noqa: F401
            return True
        except Exception:      # not installed, or its C library (cairo) missing
            return False
    return shutil.which(tool) is not None


def _logo_render_with(tool, svg_path, png_path, size):
    """Render svg_path to png_path (size x size) with tool. Returns None if OK, or the error text."""
    import subprocess
    try:
        if tool == 'cairosvg':
            import cairosvg
            cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_width=size, output_height=size)
        elif tool == 'rsvg-convert':
            r = subprocess.run(['rsvg-convert', '-w', str(size), '-h', str(size), '-a', str(svg_path),
                                '-o', str(png_path)], capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                return (r.stderr or r.stdout).strip()[:300] or f'exit {r.returncode}'
        elif tool == 'inkscape':
            v = subprocess.run(['inkscape', '--version'], capture_output=True, text=True, timeout=60)
            mv = re.search(r'Inkscape\s+(\d+)', v.stdout + v.stderr)
            if mv and int(mv.group(1)) >= 1:     # Inkscape 1.x
                cmd = ['inkscape', str(svg_path), f'--export-filename={png_path}', '-w', str(size), '-h', str(size)]
            else:                                 # Inkscape 0.92
                cmd = ['inkscape', '-z', str(svg_path), '-e', str(png_path), '-w', str(size), '-h', str(size)]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                return (r.stderr or r.stdout).strip()[:300] or f'exit {r.returncode}'
        else:
            return f'unknown tool {tool}'
    except Exception as e:      # noqa: BLE001  (any failure of a tool: try the next one)
        return f'{type(e).__name__}: {e}'
    sz = png_size(png_path)
    if sz != (size, size):
        return f'the PNG is {sz[0]}x{sz[1]}, not {size}x{size}' if sz else 'no PNG written'
    return None


def make_logo(svg_in, svg_out, png_out, name, icon_out=None, tool='auto', size=LOGO_SIZE):
    """Logo of the App: svg_in with the App name -> svg_out, rendered to png_out (size x size) and copied to icon_out.

    tool: 'auto' (cairosvg, rsvg-convert, inkscape: the first one that works), one of LOGO_TOOLS, or 'none'.
    If no tool works, png_out is left as it is (the generic logo) and copied to icon_out.
    Returns (tool used or None, list of warning texts).
    """
    import tempfile
    warnings = []
    with open(svg_in, encoding='utf-8') as fd:
        svg = fd.read()
    try:
        svg = logo_set_name(svg, name)
    except ValueError as e:
        warnings.append(f'{svg_in}: {e}: the logo keeps its text')
    with open(svg_out, 'w', encoding='utf-8') as fd:
        fd.write(svg)
    used = None
    if tool == 'none':
        warnings.append(f'logo not rendered (--no-icon): {os.path.basename(png_out)} is not changed and is used as icon')
    else:
        tools = LOGO_TOOLS if tool == 'auto' else (tool,)
        found = [ t for t in tools if _logo_tool_available(t) ]
        if not found:
            kept = (f'{os.path.basename(png_out)} is not changed and is used as icon (in a new project it is the '
                    f'generic logo, without the App name)')
            if tool == 'auto':
                warnings.append('no SVG renderer found (cairosvg, rsvg-convert, inkscape): ' + kept + '; ' + LOGO_INSTALL_HINT)
            else:
                warnings.append(f'{tool} not available: ' + kept + '; ' + LOGO_INSTALL_HINT)
        fd, tmp_png = tempfile.mkstemp(suffix='.png', dir=os.path.dirname(os.path.abspath(png_out)))
        os.close(fd)
        try:
            for t in found:
                err = _logo_render_with(t, svg_out, tmp_png, size)
                if err is None:
                    os.replace(tmp_png, png_out)
                    used = t
                    break
                warnings.append(f'{t} failed ({err})' + ('' if t == found[-1] else ', trying the next tool'))
            if found and used is None:
                warnings.append(f'the logo could not be rendered: {os.path.basename(png_out)} is not changed and is '
                                f'used as icon; ' + LOGO_INSTALL_HINT)
        finally:
            if os.path.exists(tmp_png):
                os.remove(tmp_png)
    if icon_out:
        shutil.copyfile(png_out, icon_out)
    return used, warnings


#%% Remote control tools of the App (c/)

def c_regs_table(f, indent=1):
    """Lines of the register table of c/dummy.c: { name, index (= address/4), signed, read_only, min, max }"""
    txt=txt_buff(n=indent)
    regs=sorted(f, key=lambda x: x.index)
    for k, r in enumerate(regs):
        txt.add('{{ {:25s}, {:4d}, {:d}, {:d}, {:>12d}LL, {:>12d}LL }}{:s}  // 0x{:03X}'.format(
                '"'+r.name+'"', r.index, int(r.signed), int(r.ro), int(r.min), int(r.max),
                ',' if k < len(regs)-1 else ' ', 4*r.index))
    return txt.out()


def c_regs_txt(f):
    """c/dummy.txt: the register table as CSV (for scripts)"""
    lines=['name,index,address,signed,read_only,min,max,nbits']
    for r in sorted(f, key=lambda x: x.index):
        lines.append('{},{:d},0x{:03X},{:d},{:d},{:d},{:d},{:d}'.format(r.name, r.index, 4*r.index, int(r.signed),
                     int(r.ro), int(r.min), int(r.max), r.nbits))
    return '\n'.join(lines)+'\n'


def c_app_regs_h(f, base_size):
    """c/app_regs.h: base, size and offsets of the dummy registers used by the c/ tools"""
    lines=['/* Generated by config_tool.py from app.ini: do not edit (it is rewritten by config_tool.py -m). */',
           '/* Registers of the dummy module (fpga/prj/v0.94/rtl/dummy.v) for the c/ tools of the App. */',
           '#ifndef APP_REGS_H', '#define APP_REGS_H', '',
           '#define DUMMY_FPGA_BASE_ADDR  0x40600000',
           '#define DUMMY_FPGA_BASE_SIZE  0x{:X}'.format(base_size), '',
           '/* byte offsets from DUMMY_FPGA_BASE_ADDR */']
    for r in sorted(f, key=lambda x: x.index):
        lines.append('#define DUMMY_{:<20s} 0x{:03X}'.format(r.name.upper()+'_OFF', 4*r.index))
    lines += ['', '#endif', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    print('This is a library file, only contains class and function definitios.\n')
