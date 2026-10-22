# @APP@

Red Pitaya App generated on @DATE@ with [rp_dummy2](https://github.com/marceluda/rp_dummy) (`new_project.py`)
from the controls of `@APP@/app.ini`.

## Build

```bash
source settings.sh      # Vivado 2015.2 + Linaro toolchain (edit the paths if yours differ)
LANG=C make             # controllerhf.so + FPGA + packages in archive/
```

The FPGA is synthesized with Vivado 2015.2 (`red_pitaya.bit`, loaded by Ecosystem 0.9x/1.0 through
`fpga.conf`). For Ecosystem 2.0 the Makefile converts it with `bootgen` of Vivado 2020.1 into
`fpga.bit.bin`, loaded by `fpga.sh` (set `BOOTGEN_SETTINGS=.../settings64.sh` if Vivado 2020.1 is not in
`/tools/Xilinx/Vivado/2020.1`). Both go in the packages, with `nginx.conf` (no cache for `index.html`).

## Where to write your design

- `@APP@/fpga/rtl/dummy.v`: your logic. The registers of the controls are already declared and connected to
  the web page (see the `ADDED REGS` list near the top). Monitors are `wire`s: assign them a value.
- `@APP@/fpga/rtl/dummy/`: put new Verilog modules here and run `@APP@/config_tool.py -t`.
- `@APP@/app.ini`: the controls. After editing it, run `@APP@/config_tool.py -a` to regenerate the
  automatic parts of the sources (the code you wrote outside the `DOCK` markers is kept).

## Upload

`_settings.env` has the address of the board (`RPIP=...`); `make upload`, or `./upload_app.sh rp-XXXXXX.local`
from a package of `archive/`.
