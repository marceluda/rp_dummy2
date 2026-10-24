#!/usr/bin/env python3
"""
Host tests of the PC-side remote control scripts (resources/), against a mock board on localhost:

- resources/streaming/stream_receiver.py --board: asks /<App>/get_ip, writes stream_ip/port/rate, calls
  /<App>/streaming, sets stream_cmd = 1, receives the data that the mock "c/stream_tcp_osc_cmd" sends, and sets
  stream_cmd = 0 at the end; decoded samples.
- resources/remote_control/http_regs.py: reads, writes, error answer (HTTP 400) -> exit 1.

Standard library only:  python3 -B remote_test.py
"""
import http.server
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RECEIVER = os.path.join(ROOT, 'resources', 'streaming', 'stream_receiver.py')
HTTP_REGS = os.path.join(ROOT, 'resources', 'remote_control', 'http_regs.py')
APP = 'my_app'
N_SAMPLES = 5000


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Board:
    """Mock of the endpoints of a generated App (nginx.conf) and of the streaming tool"""

    def __init__(self):
        self.regs = {'numberA': 0, 'stream_ip': 0, 'stream_port': 6000, 'stream_rate': 128, 'stream_cmd': 0}
        self.log = []
        self.streaming_started = False
        board = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def answer(self, code, text):
                body = text.encode()
                self.send_response(code)
                self.send_header('Content-Type', 'text/plain')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                u = urllib.parse.urlsplit(self.path)
                q = urllib.parse.parse_qsl(u.query, keep_blank_values=True)
                board.log.append((u.path, q))
                if u.path == f'/{APP}/get_ip':
                    return self.answer(200, self.client_address[0] + '\n')
                if u.path == f'/{APP}/streaming':
                    board.streaming_started = True
                    return self.answer(200, 'OK\n')
                if u.path == f'/{APP}/dummy':
                    out = []
                    for k, v in q:
                        if k not in board.regs:
                            return self.answer(400, f'ERROR: unknown register {k}\n')
                        if v != '':
                            board.regs[k] = int(v)
                    for k, v in q:
                        out.append(f'{k}:{board.regs[k]}')
                    if not q:
                        out = [f'{k}:{v}' for k, v in board.regs.items()]
                    if any(k == 'stream_cmd' and v == '1' for k, v in q) and board.streaming_started:
                        threading.Thread(target=board.stream, daemon=True).start()
                    return self.answer(200, '\n'.join(out) + '\n')
                return self.answer(404, 'not found\n')

        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.host = f'127.0.0.1:{self.httpd.server_address[1]}'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stream(self):
        """c/stream_tcp_osc_cmd: connect to stream_ip:stream_port and send CH1 = sawtooth, CH2 = -CH1"""
        ip = self.regs['stream_ip']
        addr = '.'.join(str((ip >> s) & 255) for s in (0, 8, 16, 24))
        with socket.create_connection((addr, self.regs['stream_port']), timeout=5) as c:
            data = b''.join(struct.pack('<I', ((i % 256 - 128) & 0x3FFF) | ((-(i % 256 - 128) & 0x3FFF) << 16))
                            for i in range(N_SAMPLES))
            c.sendall(data)

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Remote(unittest.TestCase):
    def setUp(self):
        self.board = Board()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.board.close()
        self.tmp.cleanup()

    def test_receiver_with_board(self):
        port = free_port()
        out = os.path.join(self.tmp.name, 's.bin')
        r = subprocess.run([sys.executable, '-I', RECEIVER, '-p', str(port), '-o', out, '--board', self.board.host,
                            '--app', APP, '-r', '1024'], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        regs = self.board.regs
        self.assertEqual(regs['stream_ip'], 127 + (1 << 24))          # 127.0.0.1 as seen by the board
        self.assertEqual(regs['stream_port'], port)
        self.assertEqual(regs['stream_rate'], 1024)
        self.assertEqual(regs['stream_cmd'], 0)                       # stopped at the end
        paths = [p for p, q in self.board.log]
        self.assertEqual(paths[:2], [f'/{APP}/get_ip', f'/{APP}/dummy'])
        self.assertIn(f'/{APP}/streaming', paths)
        cmds = [dict(q).get('stream_cmd') for p, q in self.board.log if 'stream_cmd' in dict(q)]
        self.assertEqual(cmds, ['0', '1', '0'])                       # off while configuring, on, off at the end
        with open(out, 'rb') as f:
            data = f.read()
        self.assertEqual(len(data), 4 * N_SAMPLES)
        w = struct.unpack('<I', data[4 * 300:4 * 301])[0]
        ch1 = (w & 0x3FFF) - (0x4000 if w & 0x2000 else 0)
        ch2 = ((w >> 16) & 0x3FFF) - (0x4000 if (w >> 16) & 0x2000 else 0)
        self.assertEqual((ch1, ch2), (300 % 256 - 128, -(300 % 256 - 128)))
        self.assertIn('CH1   -128   CH2    128', r.stdout)

    def test_receiver_board_error(self):
        r = subprocess.run([sys.executable, '-I', RECEIVER, '-p', str(free_port()), '-o',
                            os.path.join(self.tmp.name, 'x.bin'), '--board', self.board.host, '--app', 'other_app'],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 1)
        self.assertIn('ERROR configuring the board', r.stderr)

    def test_ip_int(self):
        r = subprocess.run([sys.executable, '-I', RECEIVER, '--ip-int', '192.168.1.123'], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), str(192 + 168 * 256 + 1 * 65536 + 123 * 16777216))

    def test_http_regs(self):
        r = subprocess.run([sys.executable, '-I', HTTP_REGS, self.board.host, APP, 'numberA=1234', 'stream_port'],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ['numberA:1234', 'stream_port:6000'])
        r = subprocess.run([sys.executable, '-I', HTTP_REGS, self.board.host, APP, 'nope=1'],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 1)
        self.assertIn('ERROR', r.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=1)
