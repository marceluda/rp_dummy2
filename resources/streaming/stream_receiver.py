#!/usr/bin/env python3
"""
PC side of the streaming of a Red Pitaya App generated with rp_dummy2 (c/stream_tcp_osc_cmd connects to it).

    ./stream_receiver.py [-p PORT] [-o FILE] [-n SECONDS] [--board HOST --app APP [-r RATE]]

Listens on PORT (default 6000), accepts one connection, writes the raw data to FILE (default
stream_YYYYmmdd_HHMMSS.bin) and prints the rate every second. Each sample is a little-endian uint32:
CH1 in bits 13:0 and CH2 in bits 29:16, 14-bit two's complement (8192 counts = 1 V with the default gains).
At the end it prints the first samples decoded. Standard library only.

With --board HOST --app APP (the App must be open in the board) it also does the board side through the
HTTP endpoints of the App: it asks the board for the address of this PC (/<App>/get_ip), writes stream_ip,
stream_port and stream_rate (/<App>/dummy), starts c/streaming (/<App>/streaming), sets stream_cmd = 1 and,
at the end (time limit or Ctrl-C) stream_cmd = 0, and it keeps receiving until the board closes the connection
(no sample is lost; also stream_cmd = 0 if the board ends first). --board writes the registers on every run.
Without it, write them once: loading the FPGA when the App is opened resets them (0 / 6000 / 128 / 0), but
since rp_dummy2 2.0.1 the controller of the App writes stream_ip, stream_port and stream_rate back (from
/tmp/<App>_stream.conf on the board); stream_cmd always starts at 0.

Board side by hand (see the README of the App):
    curl "http://rp-XXXXXX.local/<App>/dummy?stream_ip=<IP as integer>&stream_port=6000&stream_rate=128"
    curl "http://rp-XXXXXX.local/<App>/streaming"
    curl "http://rp-XXXXXX.local/<App>/dummy?stream_cmd=1"      ...      stream_cmd=0 to stop
<IP as integer> = a + b*256 + c*65536 + d*16777216 for a.b.c.d (--ip-int prints it).
"""
import argparse
import os
import signal
import socket
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


def s14(v):
    """14-bit two's complement -> int"""
    v &= 0x3FFF
    return v - 0x4000 if v & 0x2000 else v


def ip_int(addr):
    """a.b.c.d -> value of stream_ip"""
    p = [int(x) for x in addr.strip().split('.')]
    if len(p) != 4 or any(not 0 <= x <= 255 for x in p):
        raise ValueError(f'not an IPv4 address: {addr!r}')
    return p[0] + (p[1] << 8) + (p[2] << 16) + (p[3] << 24)


def board_get(host, app, path, query=None):
    """GET http://host/app/path?query from the endpoints of the App; returns the text (error on HTTP 4xx/5xx)"""
    url = f'http://{host}/{urllib.parse.quote(app)}/{path}'
    if query:
        url += '?' + urllib.parse.urlencode(query)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read().decode()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'{url}: HTTP {e.code} {e.read().decode().strip()}')


def in_thread(fn, limit=None):
    """Run fn() in a daemon thread and wait for it in short steps, so that a Ctrl-C (KeyboardInterrupt in this, the
    main thread) is not delayed by a blocking call (name resolution, connect: up to the 10 s timeout). Returns
    ('ok', value), ('error', exception) or ('timeout', None) after limit seconds; KeyboardInterrupt goes up."""
    res = {}
    def run():
        try:
            res['ok'] = fn()
        except Exception as e:                               # noqa: BLE001 (reported to the caller)
            res['error'] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t_end = None if limit is None else time.time() + limit
    while t.is_alive() and (t_end is None or time.time() < t_end):
        t.join(0.05)
    if 'ok' in res:
        return 'ok', res['ok']
    if 'error' in res:
        return 'error', res['error']
    return 'timeout', None


def stop_short(a, limit=1.0):
    """stream_cmd = 0 with at most `limit` seconds of waiting (at the end after a Ctrl-C); True if it was done"""
    try:
        st, v = in_thread(lambda: board_get(a.board, a.app, 'dummy', {'stream_cmd': 0}), limit)
    except KeyboardInterrupt:
        return False
    return st == 'ok'


def hard_exit(code):
    """Exit at once after a Ctrl-C: a daemon thread blocked in getaddrinfo() (urlopen of a name that does not
    resolve, e.g. a wrong .local) made the shutdown of Python wait ~5 s for it. Output is flushed first; the data
    file and the sockets are already closed by the caller."""
    for f in (sys.stdout, sys.stderr):
        try:
            f.flush()
        except Exception:                                    # noqa: BLE001
            pass
    os._exit(code)


def stop_quietly(a, srv, reached=True):
    """After a Ctrl-C before the data starts: stream_cmd = 0 (best effort, at most 1 s), close. Not sent if no
    request ever reached the board (reached False: e.g. its name was still being resolved): it would only wait"""
    if a.board and not reached:
        print(f'{a.board}: never reached, nothing to stop', file=sys.stderr)
    elif a.board:
        if stop_short(a):
            print(f'{a.board}: stream_cmd = 0', file=sys.stderr)
        else:
            print(f'{a.board}: stream_cmd = 0 not confirmed', file=sys.stderr)
    srv.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-p', '--port', type=int, default=6000)
    ap.add_argument('-o', '--output', default=time.strftime('stream_%Y%m%d_%H%M%S.bin'))
    ap.add_argument('-n', '--seconds', type=float, default=0, help='stop after this time (0: until the board closes)')
    ap.add_argument('--ip-int', metavar='A.B.C.D', help='print the value of stream_ip for this address and exit')
    ap.add_argument('--board', metavar='HOST', help='also configure and start the streaming in this board (HTTP)')
    ap.add_argument('--app', metavar='APP', help='name of the App in the board (with --board)')
    ap.add_argument('-r', '--rate', type=int, default=128,
                    help='with --board: stream_rate, decimation of the scope (default 128: 976.6 kS/s)')
    ap.add_argument('--rcvbuf', type=int, default=None, metavar='BYTES',
                    help='receive buffer of the socket (default: 8 MiB, about 2 s of data at 976 kS/s, if the system '
                         'allows it (net.core.rmem_max), otherwise the automatic tuning of Linux, up to tcp_rmem)')
    a = ap.parse_args()

    if a.ip_int:
        print(ip_int(a.ip_int))
        return 0
    if a.board and not a.app:
        ap.error('--board needs --app')

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # A large receive buffer (set before listen(), so the accepted socket and its TCP window get it): a short pause
    # of this program does not make the board wait in send() (its scope buffer, 16384 samples, is ~17 ms at
    # decimation 128; the board counts the overwritten samples as overrun / lost). Setting SO_RCVBUF turns off the
    # automatic tuning of Linux and is capped at net.core.rmem_max (often 208 KiB, less than the automatic tuning
    # reaches): by default it is only set when the system allows the whole 8 MiB.
    rcvbuf = a.rcvbuf
    if rcvbuf is None:
        try:
            with open('/proc/sys/net/core/rmem_max') as fd:
                rcvbuf = (8 << 20) if int(fd.read()) >= (8 << 20) else None
        except (OSError, ValueError):
            rcvbuf = None
    if rcvbuf:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, rcvbuf)
    srv.bind(('', a.port))
    srv.listen(1)
    if a.board:
        reached = {'any': False}                             # some request got an answer from the board
        def configure():
            pc = board_get(a.board, a.app, 'get_ip').strip()
            reached['any'] = True
            print(f'{a.board}: this PC is {pc}; stream_ip={ip_int(pc)} stream_port={a.port} stream_rate={a.rate}',
                  flush=True)
            print(board_get(a.board, a.app, 'dummy', {'stream_cmd': 0, 'stream_ip': ip_int(pc),
                                                      'stream_port': a.port, 'stream_rate': a.rate}), end='', flush=True)
            board_get(a.board, a.app, 'streaming')
            time.sleep(0.3)                                  # c/streaming starts and waits for stream_cmd
            board_get(a.board, a.app, 'dummy', {'stream_cmd': 1})
        try:
            # (in a thread: a Ctrl-C is not delayed by a slow name resolution or connect of the board)
            st, err = in_thread(configure)
            if st == 'error':
                if not isinstance(err, (OSError, RuntimeError, ValueError)):
                    raise err
                print(f'ERROR configuring the board: {err}', file=sys.stderr)
                srv.close()
                return 1
        except KeyboardInterrupt:                            # e.g. during a slow name resolution of the board
            print('interrupted while configuring the board', file=sys.stderr)
            stop_quietly(a, srv, reached['any'])
            hard_exit(130)
    print(f'waiting for the Red Pitaya on port {a.port} ...', flush=True)
    try:
        conn, addr = srv.accept()
    except KeyboardInterrupt:
        print('interrupted while waiting for the board', file=sys.stderr)
        stop_quietly(a, srv)
        hard_exit(130)
    print(f'connected from {addr[0]}; writing {a.output}', flush=True)
    total, t0, last, first = 0, time.time(), time.time(), b''

    stop_result = {}

    def stop_board():
        """stream_cmd = 0 (in a thread: the HTTP request takes 10-50 ms and the socket must be read meanwhile,
        or the board waits in send() and its scope buffer is overwritten): the board sends what it has and closes
        the connection, which ends the loop"""
        try:
            board_get(a.board, a.app, 'dummy', {'stream_cmd': 0})
            print(f'{a.board}: stream_cmd = 0, receiving the last samples ...', flush=True)
            stop_result['ok'] = True
        except (OSError, RuntimeError) as e:
            print(f'ERROR stopping the streaming: {e}', file=sys.stderr)
            stop_result['ok'] = False

    stop_thread = threading.Thread(target=stop_board, daemon=True)

    # With --board the end is clean: stream_cmd = 0 first (from stop_thread, while this loop keeps reading), then
    # everything the board still sends is received until it closes the connection (up to DRAIN_S); closing the
    # socket first gave "Broken pipe" on the board and lost the last samples. Without --board (the board is
    # stopped by hand) the time limit closes the connection.
    DRAIN_S = 5.0
    stopping, drain_end = False, None
    # Ctrl-C only sets a flag, checked once per pass of the loop (a KeyboardInterrupt between recv() and write()
    # lost the segment just received): the first one stops the streaming (with --board) or ends the reception,
    # a second one ends it at once
    sigint = {'n': 0}
    def on_sigint(signum, frame):
        sigint['n'] += 1
    signal.signal(signal.SIGINT, on_sigint)
    conn.settimeout(0.2)
    with open(a.output, 'wb') as f:
        while True:
            if sigint['n'] >= 2 or (sigint['n'] == 1 and not a.board):
                break
            if sigint['n'] == 1 and not stopping:
                stopping, drain_end = True, time.time() + DRAIN_S
                stop_thread.start()
            try:
                data = conn.recv(1 << 16)
            except socket.timeout:
                data = None
            if data == b'':
                break                                    # the board closed the connection
            if data:
                f.write(data)
                if len(first) < 64:
                    first += data[:64 - len(first)]
                total += len(data)
            now = time.time()
            if now - last >= 1:
                print(f'{total / 4:12.0f} samples  {total / 4 / (now - t0) / 1e3:9.1f} kS/s', flush=True)
                last = now
            if stop_result.get('ok') is False:
                break                                    # stream_cmd = 0 failed: nothing else will close it
            if drain_end is not None and now > drain_end:
                print(f'WARNING: the board did not close the connection {DRAIN_S:g} s after stream_cmd = 0',
                      file=sys.stderr)
                break
            if a.seconds and now - t0 >= a.seconds and not stopping:
                if not a.board:
                    break
                stopping, drain_end = True, now + DRAIN_S
                stop_thread.start()
    # (the flag handler stays until the end: a Ctrl-C while waiting here gave a traceback)
    if stopping and stop_thread.is_alive():
        t_end = time.time() + 10
        while stop_thread.is_alive() and sigint['n'] < 2 and time.time() < t_end:
            stop_thread.join(0.1)                            # a second Ctrl-C does not wait for it
    conn.close()
    srv.close()
    if a.board and not stopping:
        # the board ended by itself (or the App stopped, or a quick double Ctrl-C came before the stop): leave
        # stream_cmd = 0 anyway (at most 2 s of waiting)
        if stop_short(a, 2.0):
            print(f'{a.board}: stream_cmd = 0')
            stop_result['ok'] = True
        else:
            print('ERROR stopping the streaming: stream_cmd = 0 not confirmed', file=sys.stderr)
    # the flag handler is kept until the program ends (a Ctrl-C after restoring the default one, during the last
    # prints, ended the program with a traceback)
    if sigint['n'] >= 2:
        msg = 'interrupted (second Ctrl-C)'
        if a.board and not stop_result.get('ok') and stopping:
            # the stop request of stop_thread did not finish: one more, short (1 s), so the board is not left
            # streaming (stream_cmd = 1)
            msg += ': stream_cmd = 0 ' + ('sent' if stop_short(a) else 'NOT confirmed (set it by hand)')
        print(msg, file=sys.stderr)
    dt = time.time() - t0
    print(f'{total / 4:.0f} samples in {dt:.1f} s ({total / 4 / max(dt, 1e-9) / 1e3:.1f} kS/s)')
    for i in range(0, len(first) - 3, 4):
        (w,) = struct.unpack('<I', first[i:i+4])
        print(f'  CH1 {s14(w):6d}   CH2 {s14(w >> 16):6d}')
    # a late Ctrl-C (e.g. the second of a quick double Ctrl-C, after the board already closed) is ignored: during
    # the shutdown of Python it would kill the process with SIGINT (exit status 130 / -2)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if sigint['n'] >= 2 or (stopping and stop_thread.is_alive()):
        hard_exit(0)                                         # do not wait for a stop request still blocked
    return 0


if __name__ == '__main__':
    sys.exit(main())
