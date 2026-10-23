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
        update_verilog(fpga_mod_fn,dock=['WIREREG','FPGA MEMORY'],
                       txt=[fpga_defs(self),fpga_reg_write(self)+fpga_reg_read(self)])

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

    def auto_set_controls(self,filename,AppName):
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
            if len(get_muxer(filename,i[rip_len:] ))>0:
                self[i].control = select(idd=i , items=get_muxer(filename,i[rip_len:] ), default=self[i].val  );
            else:
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


def fpga_reg_read(f,indent=1):
    """Print FPGA-to-Processor verliog design"""
    txt=txt_buff(n=indent)

    txt.add('//---------------------------------------------------------------------------------')
    txt.add('// FPGA --> MEMORIA --> SO')
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
    txt.nl()
    txt.add("casez (sys_addr[19:0])")

    txt.indent_plus()

    for r in f:
        if r.nbits==32:
            txt.add("{:3s} : begin sys_ack <= sys_en;  sys_rdata <= {:>45}   ;".format(
                    r.addr , (r.name+'_reg' if r.reg_read else r.name )
                    ).ljust(95)
                    +" end // {:}".format(inline(r.desc))
              )
        elif r.nbits==1:
            txt.add(
                    "{:5s} : begin sys_ack <= sys_en;  sys_rdata <=".format(r.addr)+
                    " {  31'b0  ".ljust(28)+
                    ",  {:>15s}  }};".format( (r.name+'_reg' if r.reg_read else r.name ) ) +
                    " end // {:}".format(inline(r.desc))
                    )
        else:
            if r.signed:
                txt.add(
                        "{:5s} : begin sys_ack <= sys_en;  sys_rdata <=".format(r.addr)+
                        " {{  {{{:>2d}{{{:s}[{:d}]}}}} ".format(32-r.nbits, (r.name+'_reg' if r.reg_read else r.name ), r.nbits-1).ljust(28)+
                        ",  {:>15s}  }};".format( (r.name+'_reg' if r.reg_read else r.name ) ) +
                        " end // {:}".format(inline(r.desc))
                        )
            else:
                txt.add(
                        "{:5s} : begin sys_ack <= sys_en;  sys_rdata <=".format(r.addr)+
                        " {{  {:>2d}'b0 ".format(32-r.nbits).ljust(28)+
                        ",  {:>15s}  }};".format(  (r.name+'_reg' if r.reg_read else r.name )  ) +
                        " end // {:}".format(inline(r.desc))
                        )
    txt.add("default   : begin sys_ack <= sys_en;  sys_rdata <=  32'h0        ; end")
    txt.indent_minus()
    txt.add("endcase")
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
        if r.rw:
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


def get_muxer(filename,name):
    with open(filename, 'r') as input:
        out=False
        deep=0
        txt=[]
        sel=''
        for line in input:
            lin=line.strip(' \n\t')
            if '//' in lin:
                lin=lin[0:lin.find('//')]
            if bool(re.match(r'.*muxer.*\(',lin)):
                out=True
            if out:
                #print(lin)
                txt.append(lin)
                deep+=lin.count('(')-line.count(')')
            if out and deep==0:
                out=False
                tmp=''.join(txt)
                txt=[]
                if bool(re.match(r'.*sel *\( *'+name+r' *\).*',tmp)):
                    sel=tmp
                #txt=[]
        txt=sel.split(')')
        ret=[]
        for i in txt:
            i=i.strip(' \n\t')
            if '.in' in i:
                ii=re.search(r'.*\((.*)',i)
                ret.append( parse_sw( ii.group(1).strip(' \n\t')  ))
        #print( '["' + '","'.join(ret) + '"]')
        return ret


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


def update_file_match(filename, tag=('start_tag','stop_tag'), txt=''):
    """Updates file replacing matched tag"""
    write_file = True
    for line in fileinput.input( files=(filename) ,backup='_'+datetime.now().strftime("%Y%m%d_%H%M%S")+'.bak',inplace=True) :
        line = line.rstrip()
        if bool(re.match(tag[0],line)):
            line += '\n'
            line += txt+'\n'
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
#   options     = off, slow, fast    # optional, combo only: text of the options (0, 1, 2...)
#   display     = int                # optional, monitor only: int (default, the raw integer) or volts
#                                    # (raw / 8192 V: 14-bit ADC/DAC scale, 8192 counts = 1 V)
#   scale       = 0.001              # optional, monitor only: show raw * scale ...
#   unit        = s                  # ... with this unit (SI prefixes are added: ms, us...)

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

# Names already used in dummy.v / the C controller / the web page by the template, or reserved
# for registers of next versions (cnt_clk, stream_*)
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
    for sec in ini.sections():
        if sec == 'general':
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


def added_regs_doc(f, controls, indent=1):
    """Comment block of dummy.v that lists the registers of the controls (ADDED REGS dock)"""
    txt = txt_buff(n=indent)
    for c in controls:
        r = f[c.name]
        rng = f'({c.min:>11d} --> {c.max:<11d})'
        kind = 'read only (wire, drive it)' if c.ro else 'reg written by the web page'
        txt.add(f'//   {c.name:<15s} {r.addr} {c.nbits:2d} bits {"  " if c.signed else "un"}signed {rng} {kind}')
    return txt.out()


if __name__ == '__main__':
    print('This is a library file, only contains class and function definitios.\n')
