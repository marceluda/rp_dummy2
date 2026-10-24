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
at the end (time limit, Ctrl-C or the board closing), stream_cmd = 0. The stream_* registers return to their
reset values (0 / 6000 / 128 / 0) every time the App is opened (the FPGA is loaded again), so they must be
written again after that: --board does it on every run.

Board side by hand (see the README of the App):
    curl "http://rp-XXXXXX.local/<App>/dummy?stream_ip=<IP as integer>&stream_port=6000&stream_rate=128"
    curl "http://rp-XXXXXX.local/<App>/streaming"
    curl "http://rp-XXXXXX.local/<App>/dummy?stream_cmd=1"      ...      stream_cmd=0 to stop
<IP as integer> = a + b*256 + c*65536 + d*16777216 for a.b.c.d (--ip-int prints it).
"""
import argparse
import socket
import struct
import sys
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
    a = ap.parse_args()

    if a.ip_int:
        print(ip_int(a.ip_int))
        return 0
    if a.board and not a.app:
        ap.error('--board needs --app')

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('', a.port))
    srv.listen(1)
    if a.board:
        try:
            pc = board_get(a.board, a.app, 'get_ip').strip()
            print(f'{a.board}: this PC is {pc}; stream_ip={ip_int(pc)} stream_port={a.port} stream_rate={a.rate}')
            print(board_get(a.board, a.app, 'dummy', {'stream_cmd': 0, 'stream_ip': ip_int(pc),
                                                      'stream_port': a.port, 'stream_rate': a.rate}), end='')
            board_get(a.board, a.app, 'streaming')
            time.sleep(0.3)                                  # c/streaming starts and waits for stream_cmd
            board_get(a.board, a.app, 'dummy', {'stream_cmd': 1})
        except (OSError, RuntimeError, ValueError) as e:
            print(f'ERROR configuring the board: {e}', file=sys.stderr)
            srv.close()
            return 1
    print(f'waiting for the Red Pitaya on port {a.port} ...', flush=True)
    try:
        conn, addr = srv.accept()
    except KeyboardInterrupt:
        if a.board:
            board_get(a.board, a.app, 'dummy', {'stream_cmd': 0})
        srv.close()
        return 1
    print(f'connected from {addr[0]}; writing {a.output}', flush=True)
    total, t0, last, first = 0, time.time(), time.time(), b''
    with open(a.output, 'wb') as f:
        try:
            while True:
                data = conn.recv(1 << 16)
                if not data:
                    break
                f.write(data)
                if len(first) < 64:
                    first += data[:64 - len(first)]
                total += len(data)
                now = time.time()
                if now - last >= 1:
                    print(f'{total / 4:12.0f} samples  {total / 4 / (now - t0) / 1e3:9.1f} kS/s', flush=True)
                    last = now
                if a.seconds and now - t0 >= a.seconds:
                    break
        except KeyboardInterrupt:
            pass
    conn.close()
    srv.close()
    if a.board:
        try:
            board_get(a.board, a.app, 'dummy', {'stream_cmd': 0})
            print(f'{a.board}: stream_cmd = 0')
        except (OSError, RuntimeError) as e:
            print(f'ERROR stopping the streaming: {e}', file=sys.stderr)
    dt = time.time() - t0
    print(f'{total / 4:.0f} samples in {dt:.1f} s ({total / 4 / max(dt, 1e-9) / 1e3:.1f} kS/s)')
    for i in range(0, len(first) - 3, 4):
        (w,) = struct.unpack('<I', first[i:i+4])
        print(f'  CH1 {s14(w):6d}   CH2 {s14(w >> 16):6d}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
