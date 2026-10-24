# Remote: remote control of a generated App

> Documented version: rp_dummy2 **2.0.2** (branch `devel2.0`, tag `v2.0.2`). Back to the [README](../README.md).
> Related: [App.md](App.md) (register map), [Devel.md](Devel.md) (build, upload, safety notes).

Every App made by `new_project.py` can be controlled without its web page, the same way as the lock-in Apps
([Lock-in+PID](https://marceluda.github.io/rp_lock-in_pid/)):

- **On the board** (ssh): command line tools in `<App>/c/` that read and write registers **by name**: `c/dummy`
  (your module) and `c/osc` (oscilloscope).
- **Over HTTP** (Ecosystem 2.0): endpoints declared in the `nginx.conf` of the App that run those tools
  (`/<App>/dummy`, `/<App>/osc`, ...). Any language that can make a GET request works (`curl`, Python, a browser).
- **Streaming**: the two channels of the scope sent continuously over TCP to a PC (`c/streaming` +
  `c/stream_tcp_osc_cmd`), up to ~1 MS/s.
- **PC-side examples** in `resources/` of the project: `remote_control/http_regs.py` and `streaming/stream_receiver.py`
  (Python 3, standard library only).

Contents:

1. [Before you start](#1-before-you-start)
2. [Registers by name: `c/dummy` and `c/osc`](#2-registers-by-name-cdummy-and-cosc)
3. [HTTP endpoints](#3-http-endpoints)
4. [Streaming of the scope](#4-streaming-of-the-scope)
5. [Other ways](#5-other-ways)
6. [Ecosystem 0.9x/1.0](#6-ecosystem-09x10)
7. [Pending (CP7, optional)](#7-pending-cp7-optional)

---

## 1. Before you start

- **Open the App first** (its page, or `curl "http://rp-XXXXXX.local/bazaar?start=<App>"`): the tools read the FPGA
  of the App, which is loaded when the App starts. With another App loaded, the same addresses belong to another
  design (the values make no sense, and an address without a driver can hang the bus).
- **Restart nginx after the first upload** (or after a change of `nginx.conf`): nginx reads the `nginx.conf` of the
  Apps only when it starts. `./upload_app.sh -r rp-XXXXXX.local` does it ([Devel.md](Devel.md#upload_appsh)). Without
  it the endpoints answer 404.
- **Opening the App resets the registers.** Every start loads the bitstream again: every register returns to its
  reset value. The page writes its own parameters again when it connects. The streaming settings `stream_ip`,
  `stream_port` and `stream_rate` (not parameters of the page) are written back by the controller from
  `/tmp/<App>_stream.conf` (since 2.0.1, see [§4](#4-streaming-of-the-scope)); `stream_cmd` always starts at 0.
- Only single 32-bit accesses: the tools never burst-read the FPGA. Do the same in your own code
  ([Devel.md, safety notes](Devel.md#safety-notes)).

## 2. Registers by name: `c/dummy` and `c/osc`

On the board (`ssh root@rp-XXXXXX.local`, then `cd /opt/redpitaya/www/apps/<App>/c`):

```bash
./dummy                          # every register of the dummy module, one "name:value" per line
./dummy numberA                  # read one
./dummy numberA 1234             # write (decimal, negative, or 0x... hex) and print it again
./dummy numberA 1234 monitorA    # any mix of reads and writes, in order
./osc Dec TrgSrc DebLen          # registers of the oscilloscope
```

```
numberA:1234
monitorA:1234
```

- The register table of `c/dummy` is generated from `app.ini` by `config_tool.py -m` (`c/dummy.c`, plus
  `c/dummy.txt`: the same table as CSV with name, index, address, signed, read only, min, max and bits). After
  changing `app.ini`, run `config_tool.py -a` and rebuild (`make app`).
- **Everything is checked before writing**: names, read-only registers (monitors, `in1`, `oscA`...) and the range of
  each register (e.g. `oscA_sw` 0..31, a 14-bit signed number -8192..8191). If any argument is wrong, the tool
  prints one `ERROR: ...` line and writes nothing, not even the valid arguments before it.
- Exit status: 0 ok, 1 unknown register name, 2 read-only register, value out of range or not a number, 3 cannot map
  the FPGA (not root).
- Signed registers are printed sign-extended (`numberA:-100`).
- Monitors are read from a registered copy that is held during the read, so a fast-changing signal reads as one
  consistent value ([App.md, bus reads](App.md#1-overview-and-signal-flow)).

`c/osc` registers (2.0 scope, `c/osc.txt`): `conf` (0x00), `TrgSrc` (0x04), `ChAth`/`ChBth` (trigger levels,
0x08/0x0C), `TrgDelay` (0x10), `Dec` (0x14), `CurWpt`/`TrgWpt` (write pointers, read only), `ChAHys`/`ChBHys`, `AvgEn`,
`PreTrgCnt` (read only), the equalization filters `ChAEqFil1..4` / `ChBEqFil1..4`, `DebLen` (external trigger
debounce, 0x90) and `TrgUnlock` (0x94). The C controller also drives the scope (unless a streaming is running):
writing scope registers while the page is acquiring changes its next acquisition.

The texts of the values of the combo boxes are in `c/names_dic.txt` (`register offset value text`, e.g.
`oscA_sw 0x000 1 in1`), for scripts that want to show names instead of numbers
([Usage.md §5.4](Usage.md#54-cnames_dictxt)).

## 3. HTTP endpoints

Declared in `<App>/nginx.conf` (Ecosystem 2.0; exact-match locations, Lua). `<App>` is the name of the App.

| Endpoint | Answer |
|---|---|
| `/<App>/dummy` | `c/dummy` with the arguments of the query: `?numberA` reads, `?numberA=1234` writes, no query lists everything |
| `/<App>/osc` | `c/osc`, same rules: `?Dec&TrgSrc` |
| `/<App>/get_ip` | the address of the client as seen by the board (for `stream_ip`) |
| `/<App>/calib` | calibration of the board (`/opt/redpitaya/bin/calib -rv`) |
| `/<App>/streaming` | starts `c/streaming` (detached), answers `OK` ([§4](#4-streaming-of-the-scope)) |
| `/<App>/check_streaming` | `0` if `c/streaming` is running, `1` if not |

```bash
curl "http://rp-XXXXXX.local/my_app/dummy?numberA=1000&comboA"
# numberA:1000
# comboA:0
curl -i "http://rp-XXXXXX.local/my_app/dummy?numberA=99999"
# HTTP/1.1 400 Bad Request
# ERROR: numberA = 99999 out of range (-8192 .. 8191)
```

Security of the endpoints: only register names (`[A-Za-z0-9_]`, up to 64 characters) and decimal integers (up to 12
characters, optional `-`) are passed to the tools, never a raw string to the shell; anything else (`abc`, `1e3`,
`0x10`, `;`, a 13-digit value) answers **400** without running anything. An `ERROR` from the tool also gives 400.
Up to 40 arguments per request. Hex values are only accepted on the command line, not over HTTP.

The query order is not kept by nginx (Lua tables): do not rely on the order of writes within one request; send two
requests when the order matters (e.g. set `stream_ip` before `stream_cmd=1`).

From Python, `resources/remote_control/http_regs.py` of the project:

```bash
./http_regs.py rp-XXXXXX.local my_app                      # every register
./http_regs.py rp-XXXXXX.local my_app numberA=1234 comboA  # write numberA, read comboA
./http_regs.py --osc rp-XXXXXX.local my_app Dec TrgSrc     # scope registers
```

It prints the `name:value` lines and exits with 1 on an error answer. Inside your own script:

```python
import urllib.request
def regs(host, app, query):
    with urllib.request.urlopen(f'http://{host}/{app}/dummy?{query}', timeout=10) as r:
        return dict(line.split(':', 1) for line in r.read().decode().split())
print(regs('rp-XXXXXX.local', 'my_app', 'numberA=1234&monitorA'))   # {'numberA': '1234', 'monitorA': '1234'}
```

## 4. Streaming of the scope

`c/stream_tcp_osc_cmd` takes the scope (both channels, as selected by OscA / OscB) and sends every sample to a TCP
server on the PC. It needs the **2.0 scope** of the default bitstream (Vivado 2020.1).

**Registers** of the dummy module (0x054–0x060, [App.md](App.md#register-map-of-the-dummy-module)); they are not
parameters of the page, so the page never overwrites them:

| Register | Reset | Meaning |
|---|---|---|
| `stream_ip` | 0 | IP of the PC, a.b.c.d = `a + b*256 + c*65536 + d*16777216` (`stream_receiver.py --ip-int a.b.c.d` prints it) |
| `stream_port` | 6000 | TCP port of the receiver |
| `stream_rate` | 128 | decimation of the scope while streaming: 125 MS/s / `stream_rate` |
| `stream_cmd` | 0 | ≠ 0: streaming on |

**Kept when the App is opened again** (since 2.0.1): the bitstream load resets the four registers, so the controller
saves `stream_ip`, `stream_port` and `stream_rate` in `/tmp/<App>_stream.conf` whenever it sees them changed (on every
request of the page) and when the App exits, and writes them back to the FPGA when the App is opened. The nginx log
says `rp_app_init: streaming settings restored from /tmp/<App>_stream.conf: stream_ip=... stream_port=...
stream_rate=...`. `stream_cmd` is never saved: opening the App never starts a streaming. Notes:

- `/tmp` because the App folder (`/opt/redpitaya`) is mounted read-only on Ecosystem 2.0; the file is only written when
  the values change. It does not survive a reboot of the board (by design: the address of the PC may change).
- A file that is not valid (unknown or repeated key, value out of range, not a number) is ignored as a whole: the
  registers keep their reset values (and the nginx log says so). Delete the file to go back to the reset values.
- A change made while no page is open (only `/dummy` or `c/dummy`) is saved when the App exits (`bazaar?stop`,
  opening another App); if the controller dies without exiting (crash, power off) such a change is lost.

**Data:** a stream of little-endian 32-bit words, one per sample: CH1 in bits 13:0 and CH2 in bits 29:16, each a
14-bit two's complement number (8192 counts = 1 V with the LV jumpers). Rates tested on a STEMlab 125-14 with
OS 2.04-35: `stream_rate` 1024 → 122 kS/s and 128 → 976.6 kS/s (≈3.9 MB/s), without gaps; decimation 64 (1.95 MS/s)
is faster than the board can read the scope buffer (~1.6 MS/s): samples are skipped (the log counts them as
`overrun`/`lost`).

### The easy way: `stream_receiver.py --board`

With the App open, on the PC (`resources/streaming/` of the project):

```bash
./stream_receiver.py --board rp-XXXXXX.local --app my_app -r 128 -n 10 -o data.bin
```

```
rp-XXXXXX.local: this PC is 192.168.1.20; stream_ip=335653056 stream_port=6000 stream_rate=128
...
waiting for the Red Pitaya on port 6000 ...
connected from 192.168.1.30; writing data.bin
      976563 samples      976.4 kS/s
...
rp-XXXXXX.local: stream_cmd = 0, receiving the last samples ...
9765632 samples in 10.0 s (976.5 kS/s)
  CH1   -128   CH2    128
```

It listens on the port, asks the board for the address of the PC (`/get_ip`), writes `stream_ip`, `stream_port` and
`stream_rate`, starts `c/streaming` (`/streaming`), sets `stream_cmd=1` and receives for `-n` seconds (or until Ctrl-C).
Then it sets `stream_cmd=0` (from a second thread, while it keeps reading: if nobody reads the socket during the
HTTP request, the board waits in `send()` and its scope buffer is overwritten, `overrun`/`lost` in its log) and keeps
receiving until the board closes the connection, so the last samples are not lost and the board ends cleanly (before
2.0.1 it closed the socket first: "Broken pipe" in the log of the board). `--rcvbuf BYTES` sets the receive buffer of
the socket; by default Linux tunes it by itself (8 MiB only if `net.core.rmem_max` allows it). Ctrl-C does the same as
the time limit (a second Ctrl-C ends at once, after one more short `stream_cmd=0` if the first was not confirmed; Ctrl-C before
the data starts ends at once with exit status 130). If
the board ends first, it also sets `stream_cmd=0`. Since it writes the registers on every run, the reset of the
registers when the App is opened again does not matter (they are also restored by the controller, see above).

### By hand

```bash
# PC: start the receiver first (it only listens)
./stream_receiver.py -p 6000 -o data.bin
# board: registers (once: the controller restores them when the App is opened again), start c/streaming, then switch on
curl "http://rp-XXXXXX.local/my_app/dummy?stream_ip=$(./stream_receiver.py --ip-int 192.168.1.20)&stream_port=6000&stream_rate=1024"
curl "http://rp-XXXXXX.local/my_app/streaming"          # OK  (c/streaming waits for stream_cmd)
curl "http://rp-XXXXXX.local/my_app/check_streaming"    # 0   (running)
curl "http://rp-XXXXXX.local/my_app/dummy?stream_cmd=1" # the data starts
curl "http://rp-XXXXXX.local/my_app/dummy?stream_cmd=0" # stop: the receiver ends
```

The same works over ssh with `c/dummy stream_ip ...` and `c/stream_start.sh`.

**What happens on the board:**

- `c/stream_start.sh` (run by `/streaming`) starts `c/streaming` detached from nginx (one instance: a previous one is
  replaced; log in `/tmp/<App>_streaming.log`). `c/streaming` waits for `stream_cmd ≠ 0`, then runs
  `c/stream_tcp_osc_cmd <stream_ip> <stream_port> ...`, and stops it when `stream_cmd` goes back to 0.
- While `stream_cmd ≠ 0`, the scope belongs to `c/stream_tcp_osc_cmd`: the controller of the App does not reset, arm
  or configure it, so **the scope of the page stops refreshing**; the rest of the page (controls, monitors) keeps
  working, and a change in the page does not stop the streaming. The decimation of the scope is `stream_rate`
  (the FPGA replaces the decimation of the page while `stream_cmd[0] = 1`). When it goes back to 0, the controller
  waits for `c/stream_tcp_osc_cmd` to end and applies the settings of the page again.
- **The streaming stops by itself when the App stops** (closing the page, `bazaar?stop`, opening another App): the
  controller sets `stream_cmd = 0` and ends both processes (in ≤ 1 s), and `fpga.sh` kills them before another
  bitstream is loaded, so they never read a foreign FPGA.
- At the end, `/tmp/<App>_streaming.log` has a summary line of `c/stream_tcp_osc_cmd`:
  `samples=... wp_glitch=... wp_back=... resync=... overrun=... lost=...`. `lost=0` means no sample was skipped.
  `wp_glitch` counts write-pointer reads that did not agree and were repeated: a few at decimation 128 are normal and
  do not lose data (seen in the CP5 test: `wp_glitch=1`, no gap in 6 million samples).
- Only one streaming per board, to one receiver.

**Reading the file** (Python, standard library):

```python
import struct
def s14(v):
    v &= 0x3FFF
    return v - 0x4000 if v & 0x2000 else v
with open('data.bin', 'rb') as f:
    data = f.read()
words = struct.unpack(f'<{len(data) // 4}I', data)
ch1 = [s14(w) for w in words]          # counts; / 8192 -> V (LV jumpers)
ch2 = [s14(w >> 16) for w in words]
```

## 5. Other ways

- **`monitor`** (tool of Red Pitaya, on the board): one 32-bit access by address, `monitor 0x40600100` /
  `monitor 0x40600100 5`. Addresses in [App.md](App.md#register-map-of-the-dummy-module).
- **`py/`** of the App (runs on the board, Python with `/dev/mem`): `hugo.py` has the register list written by
  `config_tool.py -p`; `dummy.py`, `osc.py`, `osc_get_ch.py`, `osc_trig.py`, `data_dump.py` are the scripts of the first
  rp_dummy (not reviewed for this version: prefer `c/dummy` and `c/osc`).
- **`/data`** (the parameters of the controller, as the page uses them): the standard Red Pitaya endpoint of the App.
  It is what the page uses; driving it from a script has the problems documented for the lock-in Apps (only one
  client, the Ecosystem 2.0 handler that leaves one connection open per POST): see `doc/Remote.md` of
  [rp_lock-in_pid_h](https://github.com/marceluda/rp_lock-in_pid_h). Not tested with dummy Apps.
- `resources/remote_control/` also keeps the old SSH/paramiko scripts of the first rp_dummy (`control_hugo.py`,
  `read_dump.py`, ...), not updated.

## 6. Ecosystem 0.9x/1.0

The packages also carry the files of the older ecosystems (`fpga.conf` + `red_pitaya.bit`), and `nginx.conf` uses the
same Lua constructs as the lock-in Apps v0.3.x for those ecosystems, but the remote control **was only tested on
Ecosystem 2.0**. With the default bitstream (Vivado 2020.1, 2.0 scope) the tools should behave the same. With the
optional bitstream of `make eco1` (Vivado 2015.2, 0.9x scope): `c/dummy` works; `c/osc` lists 2.0 registers
(`TrgUnlock`, `DebLen`) that the 0.9x scope does not have; the streaming does not work (the 0.9x scope ignores the
decimation of `stream_rate`, bits 2–19 of `osc_ctrl_w`). See [Devel.md](Devel.md#ecosystem-09x10).

## 7. Pending (CP7, optional)

Not in rp_dummy2 2.0.x (plan of the Ecosystem 2.0 migration, `reportes/dummy2/plan_eco20.md` of the Apps folder):

- an acquisition tool with a trigger (`osc_dump` / `/run_dump` of the lock-in Apps): left out on purpose until it is
  versioned in `rp_lock-in_pid_h` (decision D6);
- the signal generator (ASG) in the Vivado 2020.1 design (decision D3);
- `new_project.py --update`: bring an existing App to a new version of the template.
