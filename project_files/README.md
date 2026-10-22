# @APP@

Red Pitaya App generated on @DATE@ with [rp_dummy2](https://github.com/marceluda/rp_dummy) (`new_project.py`)
from the controls of `@APP@/app.ini`.

## Build

```bash
source settings.sh      # Vivado 2015.2 + Linaro toolchain (edit the paths if yours differ)
LANG=C make             # controllerhf.so + FPGA + packages in archive/
```

## Where to write your design

- `@APP@/fpga/rtl/dummy.v`: your logic. The registers of the controls are already declared and connected to
  the web page (see the `ADDED REGS` list near the top). Monitors are `wire`s: assign them a value.
- `@APP@/fpga/rtl/dummy/`: put new Verilog modules here and run `@APP@/config_tool.py -t`.
- `@APP@/app.ini`: the controls. After editing it, run `@APP@/config_tool.py -a` to regenerate the
  automatic parts of the sources (the code you wrote outside the `DOCK` markers is kept).

## Upload

`_settings.env` has the address of the board (`RPIP=...`); `make upload`, or `./upload_app.sh rp-XXXXXX.local`
from a package of `archive/`.
