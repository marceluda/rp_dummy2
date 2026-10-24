# @APP@

Red Pitaya App generated on @DATE@ with [rp_dummy2](https://github.com/marceluda/rp_dummy) @GEN_VERSION@ (`new_project.py`)
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

## Remote control (ssh and HTTP)

The App carries command line tools in `<App>/c/` (cross compiled with the App) and HTTP endpoints for them in its
`nginx.conf` (Ecosystem 2.0; restart nginx after the first upload: `upload_app.sh -r`):

| On the board (ssh) | HTTP | What |
|---|---|---|
| `c/dummy` | `/<App>/dummy` | every register of the dummy module (`name:value` lines) |
| `c/dummy numberA 1234 comboA` | `/<App>/dummy?numberA=1234&comboA` | write `numberA`, read `comboA` |
| `c/osc Dec TrgSrc` | `/<App>/osc?Dec&TrgSrc` | registers of the oscilloscope (2.0: `TrgUnlock` at 0x94, `DebLen` at 0x90) |
| `c/stream_start.sh` | `/<App>/streaming` | start `c/streaming`, which waits for `stream_cmd` != 0 |
| | `/<App>/check_streaming` | 0: `c/streaming` running, 1: not running |
| | `/<App>/get_ip`, `/<App>/calib` | address of the client, calibration of the board |

The register table of `c/dummy` (and `c/dummy.txt`, CSV) is generated from `app.ini` by `config_tool.py -m`. Values
are decimal or `0x...`; names, read-only registers and ranges are checked and nothing is written if any argument is
wrong (`ERROR: ...`, HTTP 400). The HTTP endpoints pass only register names and decimal integers to the tools.

**Streaming of the scope** (2.0 FPGA): `stream_ip` (a.b.c.d as `a + b*256 + c*65536 + d*16777216`), `stream_port`,
`stream_rate` (decimation) and `stream_cmd` are registers of the dummy module at 0x054–0x060, not parameters of the
web page. With the App open, the simplest way is
`resources/streaming/stream_receiver.py --board rp-XXXXXX.local --app @APP@ -r 128 -n 10` (it writes the registers,
starts the streaming, receives 10 s and stops it). By hand: start a receiver on the PC
(`resources/streaming/stream_receiver.py -p 6000`), then `/<App>/dummy?stream_ip=...&stream_port=6000&stream_rate=128`,
`/<App>/streaming`, `/<App>/dummy?stream_cmd=1`; stop with `stream_cmd=0` (also done when the App stops). Each time
the App is opened its FPGA is loaded again, but the controller writes `stream_ip`, `stream_port` and `stream_rate`
back from `/tmp/@APP@_stream.conf` on the board (saved when they change and when the App exits; not after a reboot);
`stream_cmd` always starts at 0. While streaming, the web page scope does not refresh (the
scope belongs to `c/stream_tcp_osc_cmd`). `resources/remote_control/http_regs.py` is an HTTP client example. More in
`doc/Remote.md` of rp_dummy2 (the generator).

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
