# rp_dummy
Empty Red Pitaya Oscilloscope application for test and development purposes

Based in [Scope App v0.95](https://github.com/RedPitaya/RedPitaya/tree/release-v0.95/apps-free/scope)
of community applications for Red Pitaya Project.


# Begin a new project

Describe the controls of the App in an `.ini` file (see `config.ini`: combo boxes, numbers, checkboxes,
buttons and read-only monitors) and run `new_project.py` (Python >= 3.8, standard library only):

```
./new_project.py -n -c my.ini my_app          # check my.ini and print the register map (writes nothing)
./new_project.py -c my.ini -o ~/rp my_app     # create the project ~/rp/rp_my_app/ with the App my_app/
./new_project.py -h                           # all the options
```

Every control becomes a register of the FPGA module (`fpga/prj/v0.94/rtl/dummy.v`), a parameter of the C controller
and an element of the web page, already connected. The `.ini` is validated before anything is written
(types, widths, names that clash with the template or with Verilog/C keywords...). The App is created as a
standalone project folder (root `Makefile`, `settings.sh`, `_settings.env`, `resources/`) and keeps a copy
of the `.ini` as `<App>/app.ini`: after editing it, `<App>/config_tool.py -a` regenerates the automatic
parts of the sources.

**Logo / icon:** `resources/logo.svg` is a generic logo; `new_project.py` writes the App name in its element
`id="AppName"` (the text `APP NAME LONG`) and renders it as a 100x100 PNG into `resources/logo.png` and
`<App>/info/icon.png`, with the first tool found: the Python module `cairosvg`, `rsvg-convert` or `inkscape`
(`--icon-tool` chooses one). Without any of them it warns (install one with `pip install cairosvg`,
`sudo apt install librsvg2-bin` or `sudo apt install inkscape`) and the App uses the generic `resources/logo.png`;
`<App>/config_tool.py -l` renders it again later. `--no-icon` skips the rendering.

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

fpga                : FPGA design, Vivado 2020.1 (RedPitaya-FPGA structure, Ecosystem 2.0 scope)
fpga_eco1           : optional FPGA design, Vivado 2015.2 (0.9x scope), for Ecosystem 0.9x/1.0
info                : Just version information and app icon
py                  : Python scripts for remote control
src                 : C source code

You may want to start editing the file:

fpga/prj/v0.94/rtl/dummy.v

You have there wires for all the inputs/outputs and the memory registers.

If you want to instantiate new modules, just paste them or create them in folder:

fpga/prj/v0.94/rtl/dummy/

Instantiate them in dummy.v and run:

```
./config_tool.py -a
```

### What `config_tool.py` does (`-a` = all of it)

- **Registers** (`-v -m -w -p`): from `app.ini`, the registers in `dummy.v`, the C controller, the web page and
  `py/hugo.py` (the code written outside the `DOCK` markers is kept).
- **Modules in the tcl scripts** (`-t`): the files of `fpga/prj/v0.94/rtl/dummy/` that define the modules
  instantiated in `dummy.v` (and, recursively, in those modules) are listed in the Vivado scripts of `fpga/` (2020.1)
  and `fpga_eco1/` (2015.2); the other files are not read. It warns about modules found nowhere (the synthesis would
  fail) and about module names that clash with the RedPitaya design (e.g. `debounce`).
- **Combo boxes** (`-w`): the options of `app.ini` (`options = a, b, c`); otherwise, if the register is the `.sel` of a
  muxer of `dummy.v`, one option per muxer input, named by `[names]` of `app.ini` (`wire = text`), or the label of the
  control with that name, or the wire name; otherwise the numbers. The template selects (Osc A/B, Out1/2...) follow the
  same rule.
- **`c/names_dic.txt`** (`-n`): every value of every combo box with its text (`register address value text`), for
  scripts and the tools of the board.
- **Changes of `app.ini`**: before writing, the registers of the last generation (the `ADDED REGS` block of `dummy.v`)
  are compared with `app.ini`: controls added, removed, changed (width, sign, kind) and moved to another address
  (the controls take consecutive addresses from `0x100`: removing one moves the next ones, scripts that use fixed
  addresses must change). A removed register that the user code still uses (`dummy.v`, own code in `index.html`,
  `src/`, `py/`) is reported with its file and line until that code is fixed. For a control renamed in `app.ini`,
  `./config_tool.py -a --rename OLD:NEW` renames it also in that code (the tool suggests it when one control
  disappears and another one of the same width and kind appears).
- **Logo** (`-l`, not part of `-a`): App name on `../resources/logo.svg` -> `logo.png` and `info/icon.png`.

## Compile all

To compile the C components, run:

```
make app
```

To compile the FPGA circuit (Vivado 2020.1: `red_pitaya.bit` and `fpga.bit.bin`), run:

```
make fpga
```

Optional, for Ecosystem 0.9x/1.0: `make eco1` synthesizes the Vivado 2015.2 design of `fpga_eco1/` (same
`dummy.v`) into `red_pitaya_eco1.bit`; when it exists it goes in the packages as `red_pitaya.bit` (the file
those ecosystems load through `fpga.conf`). `make clean_eco1` removes it.

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

## Scope of the web page

Mouse wheel over the plot: no key = zoom of both axes centred on the mouse; SHIFT = time axis only (cursor ↔);
ALT = Y axis only (cursor ↕; some Linux window managers take ALT + wheel for themselves). Picking an Ext Trig other
than None sets the trigger to Source = External and Mode = Normal. **Reset zoom**: X = one whole memory of the scope at
the current decimation from t = 0, Y = -1..1 V (raw mode -8192..8192).

## Ecosystem 2.0

The generated Apps run on Ecosystem 2.0 and on the older 0.9x/1.0. The FPGA is synthesized with Vivado 2020.1
from the RedPitaya-FPGA structure (Release_2026.1, as in the lock-in Apps) with the 2.0 oscilloscope (trigger
lock, 20-bit decimation: windows up to ~68 s); `fpga/Makefile` loads Vivado 2020.1 by itself and converts the
bitstream with `bootgen` into `fpga.bit.bin`, which Ecosystem 2.0 loads with `fpga.sh`. The same `red_pitaya.bit`
(or the Vivado 2015.2 one of `make eco1`) goes in the packages for 0.9x/1.0 (`fpga.conf`). The controller works
with both scopes; with the 0.9x scope (`make eco1`) the longest window is 8.6 s (17-bit decimation).
`nginx.conf` disables the cache of `index.html`.
The web page sends the parameters in chunks (Ecosystem 2.0 hangs with big POSTs), detects when another client
takes the board, and restores its state after a restart.

## Upload testing application to a Red Pitaya device

**Ecosystem 2.0 and `nginx.conf`:** nginx reads the `nginx.conf` of the Apps only when it starts. After the
first upload of an App (or when its `nginx.conf` changes) restart it: `./upload_app.sh -r rp-XXXXXX.local`
does it (`systemctl restart redpitaya_nginx`, which stops the running App), otherwise the script reminds you.
Close or stop the App before uploading it. `upload_app.sh` uses your usual ssh keys/agent; if the board does
not accept them, ssh asks for the root password (`ssh-copy-id root@rp-XXXXXX.local` installs your key).

The log of nginx shows one `Application not loaded ... POST /data` line each time the page opens: it is the
check the page makes before starting the App, not an error.

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
