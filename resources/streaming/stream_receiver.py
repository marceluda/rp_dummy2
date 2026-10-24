#!/usr/bin/env python3
"""
PC side of the streaming of a Red Pitaya App generated with rp_dummy2 (c/stream_tcp_osc_cmd connects to it).

    ./stream_receiver.py [-p PORT] [-o FILE] [-n SECONDS]

Listens on PORT (default 6000), accepts one connection, writes the raw data to FILE (default
stream_YYYYmmdd_HHMMSS.bin) and prints the rate every second. Each sample is a little-endian uint32:
CH1 in bits 13:0 and CH2 in bits 29:16, 14-bit two's complement (8192 counts = 1 V with the default gains).
At the end it prints the first samples decoded. Standard library only.

Board side (see the README of the App):
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


def s14(v):
    """14-bit two's complement -> int"""
    v &= 0x3FFF
    return v - 0x4000 if v & 0x2000 else v


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-p', '--port', type=int, default=6000)
    ap.add_argument('-o', '--output', default=time.strftime('stream_%Y%m%d_%H%M%S.bin'))
    ap.add_argument('-n', '--seconds', type=float, default=0, help='stop after this time (0: until the board closes)')
    ap.add_argument('--ip-int', metavar='A.B.C.D', help='print the value of stream_ip for this address and exit')
    a = ap.parse_args()

    if a.ip_int:
        p = [int(x) for x in a.ip_int.split('.')]
        print(p[0] + (p[1] << 8) + (p[2] << 16) + (p[3] << 24))
        return 0

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('', a.port))
    srv.listen(1)
    print(f'waiting for the Red Pitaya on port {a.port} ...', flush=True)
    conn, addr = srv.accept()
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
    dt = time.time() - t0
    print(f'{total / 4:.0f} samples in {dt:.1f} s ({total / 4 / max(dt, 1e-9) / 1e3:.1f} kS/s)')
    for i in range(0, len(first) - 3, 4):
        (w,) = struct.unpack('<I', first[i:i+4])
        print(f'  CH1 {s14(w):6d}   CH2 {s14(w >> 16):6d}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
