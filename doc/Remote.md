# Remote: remote control of a generated App

> Documented version: branch `devel2.0`, checkpoint CP4_bis (`8b80464`). Back to the [README](../README.md).

**To be completed after CP6/CP7.** The remote control tools of the generated Apps are in development: command line
tools in `c/` (register access by name, oscilloscope capture, streaming), HTTP endpoints declared in the `nginx.conf` of
the App, and a Python client for the PC, following the lock-in Apps
([Lock-in+PID](https://marceluda.github.io/rp_lock-in_pid/)). They are not part of this checkpoint.

What exists today in a generated App:

- `py/` (runs **on the board**, through `/dev/mem`): `hugo.py` with the register list written by `config_tool.py -p`,
  and the older scripts `dummy.py`, `osc.py`, `osc_get_ch.py`, `osc_trig.py`, `data_dump.py` (not reviewed for this
  version).
- `c/names_dic.txt`: the text of every value of every combo box, for scripts
  ([Usage.md §5.4](Usage.md#54-cnames_dictxt)).
- `resources/remote_control/` of the project: old SSH-based scripts (paramiko) from the first rp_dummy, not updated.
- The register map of the App ([App.md](App.md#register-map-of-the-dummy-module)): from a shell on the board, a
  register can be read or written with the `monitor` tool of Red Pitaya, one 32-bit access at a time
  (`monitor 0x40600100`, `monitor 0x40600100 5`). See the safety notes in [Devel.md](Devel.md#safety-notes).
