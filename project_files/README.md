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

**Ecosystem 2.0 and `nginx.conf`:** nginx reads the `nginx.conf` of the Apps only when it starts. After the
first upload of an App (or when its `nginx.conf` changes) restart it: `./upload_app.sh -r rp-XXXXXX.local`
does it (`systemctl restart redpitaya_nginx`, which stops the running App), otherwise the script reminds you.
Close or stop the App before uploading it. `upload_app.sh` uses your usual ssh keys/agent; if the board does
not accept them, ssh asks for the root password (`ssh-copy-id root@rp-XXXXXX.local` installs your key).

The log of nginx shows one `Application not loaded ... POST /data` line each time the page opens: it is the
check the page makes before starting the App, not an error.

`_settings.env` has the address of the board (`RPIP=...`); `make upload`, or `./upload_app.sh rp-XXXXXX.local`
from a package of `archive/`.
