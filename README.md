# rp_dummy
Empty Red Pitaya Oscilloscope application for test and development purposes

Based in [Scope App v0.95](https://github.com/RedPitaya/RedPitaya/tree/release-v0.95/apps-free/scope)
of community applications for Red Pitaya Project.


# Begin a new project

Describe the controls of the App in an `.ini` file (see `config.ini`: combo boxes, numbers, checkboxes,
buttons and read-only monitors) and run `new_project.py` (Python >= 3.8, standard library only;
ImageMagick is optional, for the icon labels):

```
./new_project.py -n -c my.ini my_app          # check my.ini and print the register map (writes nothing)
./new_project.py -c my.ini -o ~/rp my_app     # create the project ~/rp/rp_my_app/ with the App my_app/
./new_project.py -h                           # all the options
```

Every control becomes a register of the FPGA module (`fpga/rtl/dummy.v`), a parameter of the C controller
and an element of the web page, already connected. The `.ini` is validated before anything is written
(types, widths, names that clash with the template or with Verilog/C keywords...). The App is created as a
standalone project folder (root `Makefile`, `settings.sh`, `_settings.env`, `resources/`) and keeps a copy
of the `.ini` as `<App>/app.ini`: after editing it, `<App>/config_tool.py -a` regenerates the automatic
parts of the sources.

Register map of the dummy module (`0x40600000`), `[general] register_map`:
`fixed` (default) template registers at `0x000-0x0FC` and the controls from `0x100`; `legacy` the layout of
the old generator (controls right after the template registers).

## Make your circuit design

First, you need to load the Vivado (FPGA synthesys tool) and Linaro (cross
compiling C languge) envoroment variables, executing:

```
source settings.sh

```

If your Linaro version is not the same as in the settings.sh file, adit it and correct it.

Inside the created folder you will find severla files and folders:

css, js, index.html : files/folders related to Web GUI. You may need to edit index.html
                      to change controllers names or style.

fpga                : Inside this folder are all the FPGA Verilog modules
info                : Just version information and app icon
py                  : Python scripts for remote control
src                 : C source code

You may want to start editing the file:

fpga/rtl/dummy.v

You have there wires for all the inputs/outputs and the memory registers.

If you want to instantiate new modules, just paste them or create them in folder:

fpga/rtl/dummy/

And after that, run:

```
./config_tool.py -a
```

After that you can use the added module inside the dummy.v file for your project.

## Compile all

To compile the C components, run:

```
make app
```

To compile the FPGA circuit, run:

```
make fpga
```

If you have to re-compila one of this parts, first clean it:

```
make clean_fpga
make clean_app
```
or
```
make clean
```

## Example of compilation / synthesys:

```
./new_project.py -o ~/rp NAME
cd ~/rp/rp_NAME
source settings.sh
LANG=C make
```

## Ecosystem 2.0

The generated Apps run on Ecosystem 2.0 and on the older 0.9x/1.0. The FPGA is synthesized with Vivado 2015.2
(`red_pitaya.bit`, loaded by 0.9x/1.0 through `fpga.conf`); `bootgen` of Vivado 2020.1 converts it into
`fpga.bit.bin`, which Ecosystem 2.0 loads with `fpga.sh`. `nginx.conf` disables the cache of `index.html`.
The web page sends the parameters in chunks (Ecosystem 2.0 hangs with big POSTs), detects when another client
takes the board, and restores its state after a restart.

## Upload testing application to a Red Pitaya device

The file _settings.env of the project (written by new_project.py from [general] rp_host, ssh_opts, scp_opts;
`new_project.py -u` rewrites it) has the parameters for ssh testing upload

It looks like:

```
RPIP=rp-XXXXXX.local
RPOPTS=-l root -p 22
RPSCP=-P 22
```

You have to edit it and set RPIP to your RP address.

Then, you can run the upload command inside the project folder

```
make upload
```


# Other Resources:

  - [Write MicroSD card for Red Pitaya](http://redpitaya.readthedocs.io/en/latest/quickStart/SDcard/SDcard.html)
