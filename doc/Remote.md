# Remote: remote control of a generated App

> Documented version: branch `devel2.0`, checkpoint CP5 (on top of CP4_bis `8b80464`). Back to the [README](../README.md).

**To be completed after CP6/CP7.** Since CP5 the generated Apps carry the remote control tools of the lock-in Apps
([Lock-in+PID](https://marceluda.github.io/rp_lock-in_pid/)): command line tools in `c/` (`dummy`: registers of the
App by name, `osc`: registers of the scope, `streaming` + `stream_tcp_osc_cmd`: scope → TCP), HTTP endpoints for them in
the `nginx.conf` of the App, and PC-side examples (`resources/remote_control/http_regs.py`,
`resources/streaming/stream_receiver.py`). Until this page is written, see the "Remote control" section of the README
of a generated project, the streaming registers in [App.md](App.md#register-map-of-the-dummy-module) and the contents
of `c/` in [Devel.md](Devel.md#layout-of-a-generated-project).

What exists today in a generated App:

- `py/` (runs **on the board**, through `/dev/mem`): `hugo.py` with the register list written by `config_tool.py -p`,
  and the older scripts `dummy.py`, `osc.py`, `osc_get_ch.py`, `osc_trig.py`, `data_dump.py` (not reviewed for this
  version).
- `c/names_dic.txt`: the text of every value of every combo box, for scripts
  ([Usage.md §5.4](Usage.md#54-cnames_dictxt)).
- `resources/remote_control/` of the project: `http_regs.py` (CP5) and old SSH-based scripts (paramiko) from the first
  rp_dummy, not updated.
- The register map of the App ([App.md](App.md#register-map-of-the-dummy-module)): from a shell on the board, a
  register can be read or written with the `monitor` tool of Red Pitaya, one 32-bit access at a time
  (`monitor 0x40600100`, `monitor 0x40600100 5`). See the safety notes in [Devel.md](Devel.md#safety-notes).
