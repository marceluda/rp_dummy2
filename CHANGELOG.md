# Changelog of rp_dummy (rp_dummy2)

Versions of the generator (`new_project.py`, `config_tool.py` and the `dummy/` template). `./new_project.py --version`
prints it; it is `RP_DUMMY_VERSION` in `dummy/config_lib.py`. Each generated App keeps its own version (`0.1.0` when it
is created, in `<App>/info/info.json`) and records the version of the generator that made it.

## 1.0.0 (2026-10-23, branch `devel2.0`)

First version for Red Pitaya **Ecosystem 2.0**, made in checkpoints CP1–CP6 (tested on a STEMlab 125-14 with
RedPitaya_OS 2.04-35). Generated Apps still carry the files of Ecosystem 0.9x/1.0 (built, not tested on such a board).

### CP6: version, Ecosystem 0.9x/1.0, documentation, library fixes
- Version of the generator: `RP_DUMMY_VERSION = 1.0.0`, `new_project.py --version`; written in the `info.json`,
  `README.md` and `CHANGELOG.md` of the generated Apps.
- `new_project.py -h` lists every key of the `.ini` (`[general]`: `AppName`, `include_genfun`, `include_pids`,
  `register_map`, `rp_host`, `ssh_opts`, `scp_opts`; controls: `type`, `label`, `bits_number`, `signed`, `default`,
  `options`, `display`, `scale`, `unit`; `[names]`).
- Ecosystem 0.9x/1.0: `make eco1` / `make clean_eco1` also in the project Makefile; the package says which
  `red_pitaya.bit` it carries and is rebuilt when `red_pitaya_eco1.bit` appears or changes; `clean_eco1` removes
  `target/`. Documented in `doc/Devel.md` (what works with each bitstream).
- Library of Verilog modules: `fun_icdf` (unsigned comparison: negative inputs gave wrong values; output sign one tick
  early), `fun_pico` (undeclared net), `gen_ramp` (could not be synthesized: relock system removed, registered `*`
  instead of `mult_dsp_14`; example with the real ports); instantiation examples of the filters (4-bit `tau`) and of
  `dummy_debounce`; comments of `filtro_pasaaltos` (`TAU_OFFSET` default 0) and `sum_2N` (2^N samples). Simulation
  test `make -C tests hdl` (Vivado 2020.1 xsim).
- Web page and controller: lock-in leftovers removed (the *R|Phase Mode* button and its parameter
  `dummy_osc_lockin_mode`, the handlers of PID / filters / ramp / modulation of the lock-in Apps, about 640 lines).
- `resources/streaming/stream_receiver.py --board HOST --app APP [-r RATE]`: writes `stream_ip/port/rate` through the
  endpoints of the App, starts the streaming and stops it at the end (the `stream_*` registers return to their reset
  values each time the App is opened). Host test `tests/remote_test.py` (mock board).
- Documentation: `doc/Remote.md` (registers by name, HTTP endpoints, streaming), `doc/App.md` (library), `doc/Devel.md`
  (Ecosystem 0.9x/1.0, tests), `doc/Usage.md`, README.

### CP5: remote control tools and streaming (from rp_lock-in_pid_h v2.3.28)
- `c/` tools cross compiled with the App: `dummy` (registers of the dummy module by name; table generated from `app.ini`
  into `c/dummy.c`, `c/dummy.txt`, `c/app_regs.h`; everything checked before writing), `osc` (scope registers),
  `streaming` + `stream_tcp_osc_cmd` + `stream_start.sh` (scope → TCP).
- `nginx.conf` endpoints: `/<App>/dummy`, `/osc` (only names and decimal integers reach the tools, 400 otherwise),
  `/streaming`, `/check_streaming`, `/get_ip`, `/calib`.
- Streaming registers `stream_ip/port/rate/cmd` at 0x054–0x060 (not parameters of the page); the controller leaves
  the scope to the streaming and stops it when the App exits; `fpga.sh` stops it before loading a bitstream.
- Bus reads of rp_lock-in_pid_h v2.3.17 (`sys_rdata` held, registered copies of read-only registers, multicycle).
- Trigger level with 4 decimals; PC examples `resources/streaming/stream_receiver.py`,
  `resources/remote_control/http_regs.py`; host test `tests/test_tools.sh`.

### CP4_bis: one package, logo, scope UI of the lock-in Apps, config_tool.py tasks
- DEBUG/RELOAD packages removed (one controller, one package).
- App logo from `resources/logo.svg` with the App name (cairosvg / rsvg-convert / inkscape, fallback), `config_tool.py -l`.
- Scope: mouse wheel zoom (no key both axes, SHIFT time, ALT Y), Ext Trig ≠ None sets External/Normal, Reset zoom =
  one memory at the current decimation.
- `config_tool.py`: modules instantiated in `dummy.v` listed in the Vivado scripts; combo texts from muxer inputs,
  `options` and `[names]`; `c/names_dic.txt`; report of `app.ini` changes with warnings for stale user code, `--rename`.
- Documentation `doc/` (Usage, App, Devel) and new README.

### CP4: FPGA with Vivado 2020.1 and the 2.0 scope
- RedPitaya-FPGA Release_2026.1 structure (as the lock-in Apps): `dummy` in bus slot 6, optional PIDs, no ASG;
  `fpga.bit.bin` with bootgen. The previous Vivado 2015.2 design kept in `fpga_eco1/` (`make eco1`).
- 2.0 scope in the controller: trigger unlock, decimation up to 524288 (windows up to 68.7 s), auto-set on the 10
  ranges with time limits (the App and nginx can no longer hang), external trigger debounce, dummy registers read on
  every GET. Host test of the auto-set.

### CP3 / CP3.1: Ecosystem 2.0 web page and controller
- Web page ported from dummy_simulator: POSTs in chunks of ≤ 600 B, cautious polling, client id, state save/restore,
  per-field editing; `fpga.sh`, `nginx.conf` without cache for `index.html`; `upload_app.sh` for 2.0 (`-r` restarts
  nginx when `nginx.conf` changes).
- Per-monitor display from the `.ini` (`display = int|volts`, or `scale`/`unit`); Raw Mode in counts.

### CP2: new generator
- `new_project.py` rewritten (Python 3 standard library, argparse, validation of the `.ini`, `--dry-run` register map,
  standalone project in `-o DIR`, atomic generation, exit codes); `app.ini` as the single source for `config_tool.py`;
  fixed register map (template 0x000–0x0FC, controls from 0x100).

### CP1: fixes of the template (Vivado 2015.2)
- Bus slots of the disabled ASG/PID answered by a stub (fixed a SIGBUS), implicit nets declared in `dummy.v`
  (`default_nettype none`), separate DEBUG/RELOAD builds, `make zip/tar` create `../archive`, consistent template.

## 0.1.0.0-devbuild (2020)
- First rp_dummy: empty oscilloscope App based on the Scope App v0.95 of Red Pitaya, for Ecosystem 0.9x, with
  `new_project.py` (numpy) and `config_tool.py` (GitHub `marceluda/rp_dummy`, `master` `3298c1c`, 2020-08-18).
