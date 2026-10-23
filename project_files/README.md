# @APP@

Red Pitaya App generated on @DATE@ with [rp_dummy2](https://github.com/marceluda/rp_dummy) (`new_project.py`)
from the controls of `@APP@/app.ini`.

## Build

```bash
source settings.sh      # Linaro toolchain (+ Vivado 2015.2 for make eco1); edit the paths if yours differ
LANG=C make             # controllerhf.so + FPGA (Vivado 2020.1) + packages in archive/
```

The FPGA is synthesized with Vivado 2020.1 (`@APP@/fpga/`, RedPitaya-FPGA structure; its Makefile loads
`/tools/Xilinx/Vivado/2020.1/settings64.sh` by itself, or `VIVADO_SETTINGS=...`): `red_pitaya.bit` and, with
bootgen, `fpga.bit.bin` (Ecosystem 2.0, loaded by `fpga.sh`). For Ecosystem 0.9x/1.0 the packages carry
`red_pitaya.bit` (`fpga.conf`); optional: `make -C @APP@ eco1` synthesizes the Vivado 2015.2 design of
`@APP@/fpga_eco1/` (0.9x scope, same `dummy.v`), which then goes in the packages instead.

## Where to write your design

- `@APP@/fpga/prj/v0.94/rtl/dummy.v`: your logic. The registers of the controls are already declared and connected to
  the web page (see the `ADDED REGS` list near the top). Monitors are `wire`s: assign them a value.
- `@APP@/fpga/prj/v0.94/rtl/dummy/`: put new Verilog modules here. After instantiating one in `dummy.v`, run
  `@APP@/config_tool.py -a` (or `-t`): the files of the modules used by `dummy.v` are listed in the tcl scripts of
  `fpga/` and `fpga_eco1/` (missing modules and names that clash with the RedPitaya design, e.g. `debounce`, are
  reported).
- `@APP@/app.ini`: the controls. After editing it, run `@APP@/config_tool.py -a` to regenerate the
  automatic parts of the sources (the code you wrote outside the `DOCK` markers is kept). It lists what changed
  (controls added / removed / moved to another address) and the lines of your code that still use a removed
  register; for a renamed control use `@APP@/config_tool.py -a --rename OLD:NEW`.
- Combo boxes: `options = a, b` in `app.ini`, or the inputs of the muxer that the combo selects in `dummy.v` (texts in
  `[names]` of `app.ini`). `@APP@/c/names_dic.txt` lists the text of every combo value.
- Logo: `resources/logo.svg` with the App name, rendered to `resources/logo.png` and `@APP@/info/icon.png`
  (`@APP@/config_tool.py -l` renders it again; needs `cairosvg`, `rsvg-convert` or `inkscape`).

## Upload

**Ecosystem 2.0 and `nginx.conf`:** nginx reads the `nginx.conf` of the Apps only when it starts. After the
first upload of an App (or when its `nginx.conf` changes) restart it: `./upload_app.sh -r rp-XXXXXX.local`
does it (`systemctl restart redpitaya_nginx`, which stops the running App), otherwise the script reminds you.
Close or stop the App before uploading it. `upload_app.sh` uses your usual ssh keys/agent; if the board does
not accept them, ssh asks for the root password (`ssh-copy-id root@rp-XXXXXX.local` installs your key).

The log of nginx shows one `Application not loaded ... POST /data` line each time the page opens: it is the
check the page makes before starting the App, not an error.

`_settings.env` has the address of the board (`RPIP=...`); `make upload`, or `./upload_app.sh rp-XXXXXX.local`
from a package of `archive/`.
