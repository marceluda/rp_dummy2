# Devel: compiling, testing and uploading

> Documented version: rp_dummy2 **2.0.2** (branch `devel2.0`, tag `v2.0.2`). Back to the [README](../README.md).
> Related: [Usage.md](Usage.md) (generate an App, `config_tool.py`), [App.md](App.md) (registers, scope, modules).

Contents:

1. [Software and environment](#1-software-and-environment)
2. [Layout of a generated project](#layout-of-a-generated-project)
3. [Compiling](#compiling)
4. [Host tests](#4-host-tests)
5. [Upload to the Red Pitaya](#upload-to-the-red-pitaya)
6. [Ecosystem 0.9x/1.0](#ecosystem-09x10)
7. [Working on the generator itself](#7-working-on-the-generator-itself)

---

## 1. Software and environment

| Software | Used for | Default path (where it is set) |
|---|---|---|
| Xilinx **Vivado 2020.1** | FPGA of the App (`fpga/`) and `bootgen` (`.bit` → `fpga.bit.bin`) | `/tools/Xilinx/Vivado/2020.1/settings64.sh` (`VIVADO_SETTINGS`, `dummy/fpga/Makefile:33`) |
| Xilinx Vivado 2015.2 | only the optional `make eco1` (`fpga_eco1/`) | `/opt/Xilinx/Vivado/2015.2/settings64.sh` (`settings.sh:5`) |
| Linaro toolchain `arm-linux-gnueabihf` 4.9 | C controller `controllerhf.so` and the tools of `c/` (cross-compiled) | `/opt/linaro/gcc-linaro-4.9-2014.11-x86_64_arm-linux-gnueabihf/` or `...-2015.02-3-...` (`settings.sh:11-19`) |
| Python >= 3.8 | `new_project.py`, `config_tool.py` (standard library only) | |
| `rsvg-convert` (`librsvg2-bin`), `inkscape` or the Python module `cairosvg` | optional: logo with the App name | |
| `gcc`, `node`, `python3` | optional: host tests (`tests/`) | |
| `zip`, `tar`, `ssh`, `scp` | packages, upload | |

`settings.sh` (copied into every generated project) loads Vivado 2015.2, adds the Linaro `bin/` to `PATH` and exports
`CROSS_COMPILE=arm-linux-gnueabihf-`. Edit it if your paths differ (if Vivado 2015.2 is not installed, its line only
prints an error; it is needed only for `make eco1`). **Vivado 2020.1 is not loaded by `settings.sh`**:
`fpga/Makefile` loads it by itself in a clean environment (`env -i`), so the 2015.2 environment of the shell does not mix
with it (`dummy/fpga/Makefile:16-20, 43-47`). Use another installation with `VIVADO_SETTINGS=/path/settings64.sh`.

Always build with `LANG=C` (Vivado and the scripts expect it; see `CLAUDE.md` of the Apps folder).

---

## Layout of a generated project

`./new_project.py -c my.ini -o ~/rp my_app` creates:

```
~/rp/rp_my_app/
├── Makefile              all = make -C my_app all zip tar; clean; upload  (from project_files/Makefile)
├── settings.sh           environment: Linaro (+ Vivado 2015.2 for eco1)
├── _settings.env         RPIP / RPOPTS / RPSCP for make upload (from [general] rp_host, ssh_opts, scp_opts)
├── _build_number         BUILD_NUMBER, incremented by make clean_app / clean_fpga (created by them)
├── README.md, CHANGELOG.md, LICENSE, .gitignore
├── resources/            logo.svg / logo.png (App icon), code_helpers/, remote_control/ (http_regs.py: HTTP client),
│                         streaming/ (stream_receiver.py: receiver on the PC), rp_cmds/
├── archive/              packages made by make (zip, tar.gz)
└── my_app/               the App
    ├── app.ini           the controls (copy of my.ini): edit it, then ./config_tool.py -a
    ├── config_tool.py, config_lib.py
    ├── index.html, css/, js/          web interface
    ├── info/             info.json (name, version), icon.png
    ├── src/              C controller (main.c, worker.c, fpga*.c, dummy.c, ...) and its Makefile
    ├── c/                remote control tools (cross compiled by make app / c_tools): dummy.c (registers of the
    │                     dummy module by name), osc.c (scope), streaming.c + stream_tcp_osc_cmd.c + stream_start.sh
    │                     (scope → TCP), regtool.h, app_regs.h, dummy.txt / osc.txt (CSV), names_dic.txt (texts of
    │                     the combo values), Makefile
    ├── py/               Python scripts for the board (hugo.py: register list, dummy.py, osc*.py, data_dump.py)
    ├── fpga/             FPGA, Vivado 2020.1 (RedPitaya-FPGA structure)
    │   ├── Makefile, red_pitaya_vivado_Z10.tcl, synCheck.sh
    │   ├── rtl/, ip/, sdc/, brd/                      base design of Red Pitaya
    │   └── prj/v0.94/rtl/
    │       ├── red_pitaya_top.sv                      top (dummy module in bus slot 6, optional PIDs)
    │       ├── dummy.v                                YOUR MODULE
    │       └── dummy/                                 library of modules + your modules (+ .dat tables)
    ├── fpga_eco1/        optional FPGA, Vivado 2015.2 (0.9x scope), same dummy.v
    ├── fpga.conf         0.9x/1.0: path of red_pitaya.bit
    ├── fpga.sh           2.0: stops the streaming tools of the App, loads fpga.bit.bin with fpgautil when the App starts
    ├── nginx.conf        2.0: no cache for index.html; HTTP endpoints of the c/ tools (/<App>/dummy, osc, streaming, ...)
    ├── upload_app.sh     upload script (copied to target/)
    ├── Makefile          build of the App (below)
    └── doc/              Doxygen configuration of the C sources
```

Files written by `config_tool.py` (only between their `DOCK` markers): `dummy.v`, `src/main.c`, `src/main.h`,
`src/dummy.c`, `src/fpga_dummy.c`, `src/fpga_dummy.h`, `c/dummy.c` (register table of the tool), `index.html`,
`py/hugo.py`, the tcl scripts of `fpga/` and `fpga_eco1/`, and as whole files `c/app_regs.h`, `c/dummy.txt` (`-m`) and
`c/names_dic.txt` (`-n`). See [Usage.md §5](Usage.md#5-config_toolpy).

---

## Compiling

From the project folder:

```bash
cd ~/rp/rp_my_app
source settings.sh
LANG=C make                  # = make -C my_app all zip tar
```

### Targets of the App Makefile (`my_app/Makefile`, from `dummy/Makefile`)

Run them as `make -C my_app <target>` from the project folder, or `make <target>` inside `my_app/`.

| Target | Does | Output |
|---|---|---|
| `all` | `controllerhf.so` + `c_tools` + `fpga` | |
| `app` | C controller (`make -C src`, `-Wall -Werror`) + `c_tools` | `my_app/controllerhf.so` |
| `c_tools` | tools of `c/` (`make -C c all`, Linaro) | `my_app/c/dummy`, `osc`, `streaming`, `stream_tcp_osc_cmd` |
| `fpga` | FPGA with Vivado 2020.1 + `bootgen` (`make -C fpga all`) | `my_app/red_pitaya.bit`, `fpga.bit`, `fpga.bit.bin` (copied from `fpga/prj/v0.94/out/`) |
| `eco1` | optional: Vivado 2015.2 design of `fpga_eco1/` (needs `settings.sh`) | `my_app/red_pitaya_eco1.bit` |
| `zip` / `tar` | builds `target/` and packs it (builds what is missing, FPGA included) | `archive/my_app-<ver>-<build>-<rev>.zip` / `.tar.gz` |
| `clean_app` | C objects, `controllerhf.so`, binaries of `c/`, `target/`; BUILD_NUMBER + 1 | |
| `clean_fpga` | `make -C fpga clean`, bitstreams, `target/`; BUILD_NUMBER + 1 | |
| `clean_eco1` | `fpga_eco1/` products, `red_pitaya_eco1.bit` and `target/` (the next package takes the 2020.1 bitstream again) | |
| `clean_target` | `target/` | |
| `clean` | `clean_app` + `clean_fpga` + `clean_target` (not `clean_eco1`) | |
| `upload`, `upload_bit`, `upload_html` | copy to the board (see [Upload](#upload-to-the-red-pitaya)) | |

The project `Makefile` has `all`, `clean`, `upload`, `eco1` and `clean_eco1`, which call the App Makefile.

Version string: `<ver>-<build>-<rev>` with `ver` from `info/info.json` (`0.1.0` for a new App), `build` = `BUILD_NUMBER`
(`_build_number`, 0 by default) and `rev` = `REVISION` (`devbuild` by default; `make REVISION=$(git rev-parse --short
HEAD)`). It is written into `target/my_app/info/info.json` and into the `app_version` of `target/my_app/index.html`
(`dummy/Makefile:99-101`).

### Contents of the package (`target/`)

```
target/
├── upload_app.sh, README.md, CHANGELOG.md, resources/
└── my_app/
    ├── controllerhf.so, index.html, css/, js/, info/, py/
    ├── c/                                  dummy, osc, streaming, stream_tcp_osc_cmd (binaries), stream_start.sh,
    │                                       sources, dummy.txt, osc.txt, names_dic.txt
    ├── fpga.sh (755), fpga.bit.bin          Ecosystem 2.0
    ├── fpga.conf, red_pitaya.bit           Ecosystem 0.9x/1.0 (red_pitaya_eco1.bit if make eco1 was run)
    └── nginx.conf                          Ecosystem 2.0 (HTTP endpoints: restart nginx after the first upload)
```

(`APP_FILES`, `dummy/Makefile:86-101`.) The 0.9x/1.0 bitstream of the packages is `red_pitaya_eco1.bit` when it exists,
otherwise the 2020.1 `red_pitaya.bit` (`PKG_BIT`, `dummy/Makefile:34`); the build prints which one
(`Package: red_pitaya.bit for Ecosystem 0.9x/1.0 = ...`), and the package is rebuilt when `red_pitaya_eco1.bit` appears
or changes. See [Ecosystem 0.9x/1.0](#ecosystem-09x10).

### FPGA (`my_app/fpga/Makefile`)

| Target | |
|---|---|
| `make -C my_app/fpga` (`all`) | bitstream `prj/v0.94/out/red_pitaya.bit` + `fpga.bit.bin` |
| `bit` / `bin` | only the bitstream / only `fpga.bit.bin` from an existing bitstream |
| `project` | creates the Vivado project `prj/v0.94/build/redpitaya.xpr` and opens the GUI (no synthesis) |
| `clean` | every product of the project |
| `help` | prints the header of the Makefile |

Variables: `VIVADO_SETTINGS`, `PRJ` (`v0.94`), `MODEL` (`Z10`, STEMlab 125-14), `DEFINES` (extra Verilog defines).
The bitstream is rebuilt when any source changes (`rtl/`, `prj/v0.94/rtl/`, `ip/`, `sdc/`, `brd/`, the tcl). After a
build, `synCheck.sh` writes a synthesis report into `prj/v0.94/out/` and `vivado.log` is copied there. The tcl writes
the git hash of the sources into the housekeeping ID registers, or zeros if the project is not a git repository
(`red_pitaya_vivado_Z10.tcl:161-165`).

`fpga_eco1/Makefile` (Vivado 2015.2): `make out/red_pitaya.bit` (used by `make eco1`); `all` also builds FSBL, memtest
and device tree; `project` opens the 2015.2 GUI.

### Durations and timing (measured)

| Build | Time | Result | Source |
|---|---|---|---|
| FPGA Vivado 2020.1 (`make`, test App `dummy2_test`) | 21 min 25 s (CP4), 22 min 45 s (CP4_bis), 22 min 28 s (CP5, C + FPGA + packages) | CP5: 0 errors, 54 CRITICAL WARNING of the base design; WNS −0.379 ns (`pll_pwm_clk`, 8 endpoints) and −0.195 ns (`pll_adc_clk`, 12 endpoints: scope configuration `i_scope/i_cfg` and `i_dummy/stream_cmd` → scope decimator, quasi-static registers), hold OK (WHS +0.031 ns); 5600 LUT, 18 BRAM | `reportes/dummy2/2026-10-23_cp5_rebase.md` |
| FPGA Vivado 2015.2 (`make eco1`) | 5 min 26 s (CP4), 5 min 54 s (CP6, eco1 + C + packages) | 0 errors, no width/undriven warnings of `dummy`; WNS −0.263 ns (CP4) / −0.607 ns (CP6), WHS −2.163 ns (base 2015.2 design: AXI of the PS and ADC input, not the user logic) | `reportes/dummy2/2026-10-22_cp3_1_cp4.md`, `reportes/dummy2/2026-10-23_cp6.md` |
| C controller + web package | seconds | 0 gcc warnings (`-Werror`) | idem |

The small negative slacks are in the base Red Pitaya design (PWM clock and scope configuration), not in the user logic,
and the bitstreams with them were tested on the board. Your own logic in `dummy.v` adds its own paths at 125 MHz: check
the timing summary of the build log (`vivado.log`, "Design Timing Summary") after adding wide arithmetic; pipeline it
(e.g. `pipe_mult`, registered muxers) if WNS gets worse.

### Debug messages of the controller

Uncomment `#define DEBUG 1` in `my_app/src/main.h` and rebuild (`make -C my_app clean_app app`): the `TRACE()` messages
go to the log of nginx on the board.

### Changing the web page

`index.html` is edited by hand except between its `DOCK` markers (panels of the controls and monitors, JS lists),
which `config_tool.py -w` rewrites. To try a change, rebuild the package and upload only the web part:
`./upload_app.sh -w rp-XXXXXX.local` (from `target/`) or `make -C my_app upload_html`, then reload the page. `nginx.conf`
disables the browser cache of `index.html` (Ecosystem 2.0), so a reload gets the new page.

---

## 4. Host tests

`tests/` of this repository: regression tests of the template that run on the PC, without board, cross compiler or
Vivado (`tests/Makefile`).

```bash
make -C tests            # everything (about 40 s)
make -C tests c          # auto_set_harness, trig_level_test, stream_conf_test and test_tools.sh only
make -C tests js         # web page simulations (skipped if node is not installed)
make -C tests py         # generator and remote control script tests
make -C tests hdl        # optional (Vivado 2020.1 xsim, ~30 s, not part of "make"): library modules
```

| Test | Covers |
|---|---|
| `auto_set_harness.c` (gcc) | AUTO of `dummy/src/worker.c` with a mock scope: 2.0 sample decoding, trigger level of sawtooth / square / DC, time limits (no hang without trigger), quit during AUTO; Raw Mode: level and Y range in counts, `rp_osc_trig_level_v()`; with calibration offsets (2.0.2): threshold of the search and of the resulting level at the middle of the raw signal in volts mode (CH1 and CH2), Raw level on a half count rounded as the page; level and Y range with a calibrated full scale of 1.07 V (`max_adc_norm`) |
| `trig_level_test.c` (gcc, real `dummy/src/fpga.c`) | Raw Mode trigger level: every 14-bit level, full scale and offset gives the same counts in the threshold register; half counts give the count shown by the page (`Math.round`, 2.0.2) |
| `stream_conf_test.c` (gcc, real `dummy/src/stream_conf.c`) | File of the streaming settings kept between runs of the App (`/tmp/<App>_stream.conf`): path from `APP_DIR`, save/load round trip and limits, accepted variations (order, comments, CRLF), every kind of bad file ignored as a whole (missing, empty, unknown / repeated key, `stream_cmd`, out of range, hex, negative, too long, NUL), temporary file replaced and never followed through a link (36 checks) |
| `test_tools.sh` (gcc) | `c/dummy` and `c/osc` built for the PC over a sparse file instead of `/dev/mem`: reads, writes, hex, sign, errors (name, read only, range, negative in unsigned), a request with one error writes nothing, `TrgUnlock` 0x094 / `DebLen` 0x090; offsets of `c/app_regs.h` against `dummy_reg_t` (`_Static_assert`) |
| `plot_wheel_sim.js` (node) | Mouse wheel over the scope: both axes, SHIFT, ALT, cursors, limits (57 checks) |
| `ext_trig_reset_zoom_sim.js` (node) | Ext Trig → External + Normal; Reset zoom over the 10 time ranges; config load sets the X axis, also across time units; a reply that changes the time units converts the X axis once, also with repeated / out-of-order replies and split POSTs (every POST in the units of the server); config load resets the Y axis, also when it changes Raw Mode (V ↔ Raw, no double conversion); a Raw toggle of the user still converts Y (45 checks) |
| `raw_trigger_sim.js` (node) | Units of the trigger level (volts, counts in Raw Mode, limits, switching Raw Mode), Y limits of the controller, config load without unknown keys, levels limited before sending, Y axis converted when Raw Mode is switched, units label, half counts shown as the whole count of the controller (38 checks) |
| `generator_test.py` (python3) | Logo with each renderer and fallback, no DEBUG/RELOAD packages, `config_tool.py` (modules → tcl, combo texts from muxers and `[names]`, `names_dic.txt`, `app.ini` changes, `--rename`), App name in the paths of `fpga.sh` / `nginx.conf` / `src/main.c` and `c/` without binaries, version / `-h` keys / no lock-in leftovers / 0.9x bitstream of the packages, commented drivers of the monitors in `dummy.v`, `-DVERSION` once per gcc line (16 tests) |
| `remote_test.py` (python3) | `resources/streaming/stream_receiver.py --board` (get_ip, `stream_*` writes, `/streaming`, `stream_cmd` 0/1/0, received and decoded data, clean stop: `stream_cmd=0` first and every sample until the board closes, the socket is read while the stop request is answered: the mock board measures how long it waits in `send()`; Ctrl-C (SIGINT) ×3 without losing data, double Ctrl-C (also with a slow stop request: one more short stop) and Ctrl-C during the setup, also during a slow name resolution, without traceback and without waiting) and `resources/remote_control/http_regs.py` against a mock board on localhost (10 tests) |
| `lib_modules_tb.v` (`make hdl`, xsim) | `fun_icdf` (negative inputs and output sign), `fun_pico`, `gen_ramp` (limits, triggers, `outB`) of the library |

Last run (2026-10-24, 2.0.2): auto-set ALL PASS (39 checks), `trig_level_test` and `test_tools.sh` ALL PASS, `stream_conf_test`
36/36, 57/57, 45/45, 38/38, 16 + 10 tests OK; `make hdl` LIB ERRORS=0 (2026-10-23, library unchanged since).

Other checks used during development (see the reports): `config_tool.py -a` twice on the template must leave it
unchanged (idempotent); `make app` of a generated App with Linaro; `xvlog` + `xelab` (Vivado 2020.1 simulator) on
`dummy.v` and the module files listed in the tcl, a quick syntax/elaboration check before a 20-minute synthesis:

```bash
cd my_app/fpga/prj/v0.94/rtl
FILES=$(grep -o 'dummy/[A-Za-z0-9_]*\.v' ../../../red_pitaya_vivado_Z10.tcl | tr '\n' ' ')
env -i HOME=$HOME PATH=/usr/bin:/bin FILES="$FILES" bash -c \
  '. /tools/Xilinx/Vivado/2020.1/settings64.sh > /dev/null; cd $(mktemp -d) && xvlog '"$PWD"'/dummy.v $(for f in $FILES; do echo '"$PWD"'/$f; done) && xelab dummy'
```

(The two `VRFC 10-2292` warnings of `muxer_reg4.v` / `muxer_reg5.v`, an extra `;` after `endcase`, are harmless.)

---

## Upload to the Red Pitaya

The App goes to `/opt/redpitaya/www/apps/<App>/` on the board (both ecosystems). How the ecosystem starts it:

- **Ecosystem 2.0**: the menu (bazaar) runs `fpga.sh` (because `fpga.conf` is not empty), which removes the previous
  device-tree overlay and loads `fpga.bit.bin` with `/opt/redpitaya/bin/fpgautil`; then nginx loads
  `controllerhf.so`. nginx reads the `nginx.conf` of the Apps **only when it starts**.
- **Ecosystem 0.9x/1.0**: the file named in `fpga.conf` (`red_pitaya.bit`) is loaded.

### `upload_app.sh`

Run it from the package folder (`my_app/target/`, or an unpacked `archive/*.zip`) or from inside the App folder; it needs
`index.html` and `controllerhf.so` there (`dummy/upload_app.sh:69-76`).

```
./upload_app.sh [-w] [-r] [-p port] rp-XXXXXX.local
```

| Option | Meaning |
|---|---|
| `-w` | Upload only the web interface (`index.html`, `css/`, `js/`) |
| `-r` | Ecosystem 2.0: if the `nginx.conf` of the App is new or changed (md5 compared with the one on the board), run `systemctl restart redpitaya_nginx` after the upload. **The restart stops the running App.** Without `-r` it prints a note |
| `-p port` | ssh port (default 22) |
| `-h` | help |

What it does (`dummy/upload_app.sh:95-130`): checks whether your ssh key is accepted (otherwise ssh asks for the root
password, several times; `ssh-copy-id root@rp-XXXXXX.local` installs your key), makes the file system writable
(`/opt/redpitaya/sbin/rw` in 2.0, `/boot/sbin/rw` in 0.9x), **replaces** the App folder, copies `controllerhf.so css js
nginx.conf fpga.conf index.html info py` plus `fpga.sh fpga.bit.bin red_pitaya.bit c` if present, sets `fpga.sh` to 755
(2.0 runs it with `system()`), and prints the URL. Messages in Spanish when `LANG` is `es_*`.

```bash
cd ~/rp/rp_my_app/my_app/target
./upload_app.sh -r rp-XXXXXX.local        # first upload, or nginx.conf changed
./upload_app.sh rp-XXXXXX.local           # next uploads
./upload_app.sh -w rp-XXXXXX.local        # only the web page
```

### `make upload`

With `RPIP` in `_settings.env` (`./new_project.py -u` rewrites it from the `.ini`) or on the command line:

```bash
make upload                                   # from the project folder: make -C my_app upload
make -C my_app upload RPIP=rp-XXXXXX.local
make -C my_app upload_bit                     # only red_pitaya.bit + fpga.bit.bin
make -C my_app upload_html                    # only index.html, css, js
```

`upload` rebuilds `target/` if needed, replaces the App folder and sets `fpga.sh` to 755 (`dummy/Makefile:134-161`). It
does **not** restart nginx: after the first upload of an App (or a change of its `nginx.conf`) restart it yourself (below)
or use `upload_app.sh -r`.

### Manual procedure (Ecosystem 2.0)

```bash
APP=my_app; RP=rp-XXXXXX.local
curl "http://$RP/bazaar?stop=$APP"                         # or close the App in the browser
ssh root@$RP '/opt/redpitaya/sbin/rw ; rm -rf /opt/redpitaya/www/apps/'$APP
scp -r target/$APP root@$RP:/opt/redpitaya/www/apps/
ssh root@$RP "chmod 755 /opt/redpitaya/www/apps/$APP/fpga.sh"
ssh root@$RP 'systemctl restart redpitaya_nginx'           # only if nginx.conf is new or changed
```

Then open `http://rp-XXXXXX.local/my_app/` or the icon in the menu.

### Safety notes

- **Close or stop the App before uploading it**: its folder is replaced while the controller may be loaded.
- **Never load a bitstream with `fpgautil` while an App is running** (it can hang the board until the watchdog
  reboots it): stop the App (`bazaar?stop`), load, then start it (`bazaar?start=<App>`). Normally you never need to:
  the App loads its bitstream when it starts.
- When reading FPGA registers from a shell or script on the board, use **single 32-bit accesses** (e.g. the `monitor`
  tool of Red Pitaya: `monitor 0x40600100`); never burst-read the mapped FPGA area (`memcpy`, NEON, `ldm` on
  `0x4xxxxxxx`): it has hung the board.
- `systemctl restart redpitaya_nginx` stops the running App (any App open in a browser loses its server).
- The log of nginx shows one `Application not loaded ... POST /data` line each time the page opens: it is the check the
  page makes before starting the App, not an error.
- Only one browser should control the App: when another one takes it, the page says so (it can take control back).

---

## Ecosystem 0.9x/1.0

The generated packages carry the files of both ecosystems: `fpga.sh` + `fpga.bit.bin` + `nginx.conf` for 2.0, and
`fpga.conf` + `red_pitaya.bit` for 0.9x/1.0 (which load the file named in `fpga.conf` when the App starts). The C
controller works with both oscilloscopes (2.0 and 0.9x) and the web page and `upload_app.sh` with both ecosystems.

Two bitstreams can go in `red_pitaya.bit`:

| | Vivado 2020.1 (default) | `make eco1` (Vivado 2015.2, optional) |
|---|---|---|
| Design | RedPitaya-FPGA Release_2026.1 structure, 2.0 scope | the original template design (`fpga_eco1/`), 0.9x scope, same `dummy.v` |
| Longest time range | 68.7 s (decimation 524288) | 8.6 s (decimation 65536) |
| Streaming (`c/streaming`), `TrgUnlock`/`DebLen` of `c/osc` | yes | no (0.9x scope) |
| Tested on a 0.9x/1.0 board | no | no |

```bash
cd ~/rp/rp_my_app
source settings.sh          # also loads Vivado 2015.2
LANG=C make eco1            # my_app/red_pitaya_eco1.bit (about 5-6 min)
LANG=C make                 # the packages now carry it as red_pitaya.bit (fpga.bit.bin for 2.0 does not change)
LANG=C make clean_eco1      # back to the 2020.1 bitstream in the packages
```

Status: **built, not tested on a board with Ecosystem 0.9x/1.0** (no SD card with those versions was available). The
known differences of the older ecosystems: `nginx.conf` uses the same Lua constructs as the lock-in Apps v0.3.x (which
ran on 0.9x); `upload_app.sh` uses `/boot/sbin/rw` there; nginx must also be restarted for a new `nginx.conf`.

---

## 7. Working on the generator itself

Layout of this repository:

| Path | |
|---|---|
| `new_project.py` | the generator ([Usage.md](Usage.md)) |
| `config.ini` | example `.ini` with every key (also the default of `-c`) |
| `dummy/` | the App template. It is itself a complete App (`dummy/app.ini`: no controls, `AppName = dummy`) |
| `dummy/config_lib.py` | `.ini` parser/validator (shared with `new_project.py`), generators of the docks, logo, tcl, `names_dic.txt`, register tables of `c/` |
| `dummy/config_tool.py` | regenerates the docks of an App |
| `project_files/` | templates of the project `Makefile`, `README.md`, `CHANGELOG.md`, `.gitignore` (`@APP@`, `@DATE@`) |
| `resources/` | copied to every project: `logo.svg`/`logo.png`, helpers (`code_helpers/muxer_generator.py`, `gen_sin_cos.py`), `remote_control/` (`http_regs.py`, HTTP client of `/<App>/dummy` and `/osc`; plus the old SSH/paramiko scripts), `streaming/stream_receiver.py`, `rp_cmds/nginx.sh` |
| `settings.sh` | environment, copied to every project |
| `tests/` | host tests |
| `CHANGELOG.md` | changes by version of the generator (`RP_DUMMY_VERSION` in `dummy/config_lib.py`, `new_project.py --version`) |
| `doc/` | this documentation |

After changing `config_lib.py`, `config_tool.py` or the docks of the template, run `dummy/config_tool.py -a` twice: the
second run must not change anything (`git status` clean), then `make -C tests`. Do not commit build products of the
template (`.gitignore` covers `dummy/target/`, `dummy/src/obj/`, the binaries of `dummy/c/`, bitstreams, Vivado folders).

Development history and test reports of the Ecosystem 2.0 version: `reportes/dummy2.md` and `reportes/dummy2/` in the
parent Apps folder (not part of this repository).
