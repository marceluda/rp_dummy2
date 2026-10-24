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
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
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
        self.until_stop = False        # True: stream until stream_cmd = 0 (as the real tool), False: N_SAMPLES
        self.sent = 0                  # bytes sent by the mock streaming tool
        self.stream_error = None       # e.g. BrokenPipeError: the receiver closed before the end
        self.stream_done = threading.Event()
        self.get_ip_delay = 0.0       # /get_ip answers this late (e.g. slow name resolution of the board)
        self.stop_delay = 0.0          # the answer to stream_cmd=0 takes this long (a slow board / network)
        self.stop_delay_once = False   # only for the first stream_cmd=0 after the streaming started
        self.max_send_block = 0.0      # longest sendall() of the mock tool: the receiver did not read meanwhile
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
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass                       # the client went away (Ctrl-C during the setup test)

            def do_GET(self):
                u = urllib.parse.urlsplit(self.path)
                q = urllib.parse.parse_qsl(u.query, keep_blank_values=True)
                board.log.append((u.path, q))
                if u.path == f'/{APP}/get_ip':
                    time.sleep(board.get_ip_delay)
                    return self.answer(200, self.client_address[0] + '\n')
                if u.path == f'/{APP}/streaming':
                    board.streaming_started = True
                    return self.answer(200, 'OK\n')
                if u.path == f'/{APP}/dummy':
                    out = []
                    if board.stop_delay and any(k == 'stream_cmd' and v == '0' for k, v in q) and board.sent:
                        d = board.stop_delay
                        if board.stop_delay_once:
                            board.stop_delay = 0.0
                        time.sleep(d)                  # the board keeps streaming while this request is answered
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

    @staticmethod
    def samples(i0, n):
        """CH1 = sawtooth of 256 samples (-128..127), CH2 = -CH1"""
        return b''.join(struct.pack('<I', ((i % 256 - 128) & 0x3FFF) | ((-(i % 256 - 128) & 0x3FFF) << 16))
                        for i in range(i0, i0 + n))

    def stream(self):
        """c/stream_tcp_osc_cmd: connect to stream_ip:stream_port and send the samples; with until_stop, chunks
        until stream_cmd = 0, then one more chunk (the read in progress) and close, as the real tool"""
        ip = self.regs['stream_ip']
        addr = '.'.join(str((ip >> s) & 255) for s in (0, 8, 16, 24))
        try:
            with socket.create_connection((addr, self.regs['stream_port']), timeout=5) as c:
                c.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)   # small: a reader stall blocks send
                if not self.until_stop:
                    data = self.samples(0, N_SAMPLES)
                    c.sendall(data)
                    self.sent += len(data)
                else:
                    i = 0
                    while True:
                        stop = self.regs['stream_cmd'] == 0
                        data = self.samples(i, 1000)
                        t0 = time.time()
                        c.sendall(data)
                        self.max_send_block = max(self.max_send_block, time.time() - t0)
                        self.sent += len(data)
                        i += 1000
                        if stop:
                            break
                        time.sleep(0.002)
        except OSError as e:
            self.stream_error = e
        self.stream_done.set()

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

    def test_receiver_clean_stop(self):
        """time limit: stream_cmd = 0 first, then everything the board sends until it closes (no Broken pipe)"""
        self.board.until_stop = True
        port = free_port()
        out = os.path.join(self.tmp.name, 'c.bin')
        r = subprocess.run([sys.executable, '-I', RECEIVER, '-p', str(port), '-o', out, '--board', self.board.host,
                            '--app', APP, '-n', '0.5'], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.board.stream_done.wait(5))
        self.assertIsNone(self.board.stream_error, 'the board side saw an error (receiver closed first)')
        with open(out, 'rb') as f:
            data = f.read()
        self.assertGreater(self.board.sent, 4 * 1000 * 5)
        self.assertEqual(len(data), self.board.sent, 'samples lost at the end')
        self.assertEqual(data[-4000:], Board.samples(len(data) // 4 - 1000, 1000))   # the last chunk, in order
        cmds = [dict(q).get('stream_cmd') for p, q in self.board.log if 'stream_cmd' in dict(q)]
        self.assertEqual(cmds, ['0', '1', '0'])
        self.assertIn('receiving the last samples', r.stdout)

    def test_receiver_reads_during_stop(self):
        """F2 (CP6.1 retest): the stream_cmd=0 request must not stop the reading. The mock board answers it after
        0.3 s while it keeps streaming; with small socket buffers a receiver that does not read meanwhile makes the
        board wait in send() (on the real board: scope buffer overwritten, overrun / lost samples)"""
        self.board.until_stop = True
        self.board.stop_delay = 0.3
        out = os.path.join(self.tmp.name, 'd.bin')
        r = subprocess.run([sys.executable, '-I', RECEIVER, '-p', str(free_port()), '-o', out, '--board', self.board.host,
                            '--app', APP, '-n', '0.5', '--rcvbuf', '16384'], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.board.stream_done.wait(5))
        self.assertIsNone(self.board.stream_error)
        with open(out, 'rb') as f:
            self.assertEqual(len(f.read()), self.board.sent, 'samples lost at the end')
        self.assertLess(self.board.max_send_block, 0.03,
                        f'the board waited {self.board.max_send_block:.3f} s in send(): the receiver stopped reading')

    def test_receiver_ctrl_c(self):
        """F3 (CP6.1 retest): Ctrl-C (SIGINT) stops the streaming like the time limit, without losing the segment in
        flight (a KeyboardInterrupt between recv() and write() dropped it); three runs"""
        for run in range(3):
            board = self.board if run == 0 else Board()
            board.until_stop = True
            out = os.path.join(self.tmp.name, f'i{run}.bin')
            p = subprocess.Popen([sys.executable, '-I', RECEIVER, '-p', str(free_port()), '-o', out, '--board', board.host,
                                  '--app', APP], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            t0 = time.time()
            while board.sent < 200000 + 37000 * run and time.time() - t0 < 10:
                time.sleep(0.01)
            p.send_signal(signal.SIGINT)
            o, e = p.communicate(timeout=30)
            if run:
                board.close()
            with self.subTest(run=run):
                self.assertEqual(p.returncode, 0, o + e)
                self.assertTrue(board.stream_done.wait(5))
                self.assertIsNone(board.stream_error)
                with open(out, 'rb') as f:
                    data = f.read()
                self.assertEqual(len(data), board.sent, 'samples lost')
                self.assertEqual(data, Board.samples(0, len(data) // 4), 'samples out of order / missing')
                cmds = [dict(q).get('stream_cmd') for pth, q in board.log if 'stream_cmd' in dict(q)]
                self.assertEqual(cmds, ['0', '1', '0'])
                self.assertNotIn('Traceback', e)

    def test_receiver_double_ctrl_c_and_setup(self):
        """CP6.1 retest 2 O1: a quick double Ctrl-C ends without a traceback (exit 0, data kept); Ctrl-C while the
        board is being configured: clean message, exit 130, no traceback"""
        self.board.until_stop = True
        out = os.path.join(self.tmp.name, 'dd.bin')
        p = subprocess.Popen([sys.executable, '-I', RECEIVER, '-p', str(free_port()), '-o', out, '--board', self.board.host,
                              '--app', APP], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        t0 = time.time()
        while self.board.sent < 200000 and time.time() - t0 < 10:
            time.sleep(0.01)
        p.send_signal(signal.SIGINT); time.sleep(0.02); p.send_signal(signal.SIGINT)
        o, e = p.communicate(timeout=30)
        self.assertEqual(p.returncode, 0, o + e)
        self.assertNotIn('Traceback', e)
        with open(out, 'rb') as f:
            data = f.read()
        self.assertGreater(len(data), 0)
        self.assertEqual(data, Board.samples(0, len(data) // 4))
        b2 = Board()
        try:
            b2.get_ip_delay = 8.0
            p = subprocess.Popen([sys.executable, '-I', RECEIVER, '-p', str(free_port()), '-o',
                                  os.path.join(self.tmp.name, 'ds.bin'), '--board', b2.host, '--app', APP],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            time.sleep(1.0)
            t_int = time.time()
            p.send_signal(signal.SIGINT)
            o, e = p.communicate(timeout=30)
            dt_int = time.time() - t_int
            self.assertLess(dt_int, 0.8, f'Ctrl-C during the setup took {dt_int:.2f} s')
            self.assertEqual(p.returncode, 130, o + e)
            self.assertNotIn('Traceback', e)
            self.assertIn('interrupted while configuring the board', e)
            # /get_ip never answered: no stream_cmd=0 is sent to a board that was never reached (retest 4 O2)
            self.assertIn('never reached', e)
            self.assertFalse(any('stream_cmd' in dict(q) for pth, q in b2.log), b2.log)
        finally:
            b2.close()

    def test_receiver_double_ctrl_c_slow_stop(self):
        """CP6.1 retest 3 O1: double Ctrl-C while the first stop request is still unanswered (slow board): one more
        short stream_cmd=0 at the end, the board is not left streaming; exits in ~1 s"""
        self.board.until_stop = True
        self.board.stop_delay, self.board.stop_delay_once = 3.0, True
        out = os.path.join(self.tmp.name, 'ds2.bin')
        p = subprocess.Popen([sys.executable, '-I', RECEIVER, '-p', str(free_port()), '-o', out, '--board', self.board.host,
                              '--app', APP], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        t0 = time.time()
        while self.board.sent < 200000 and time.time() - t0 < 10:
            time.sleep(0.01)
        p.send_signal(signal.SIGINT); time.sleep(0.3)
        t_int = time.time()
        p.send_signal(signal.SIGINT)
        o, e = p.communicate(timeout=30)
        self.assertLess(time.time() - t_int, 2.0)
        self.assertEqual(p.returncode, 0, o + e)
        self.assertNotIn('Traceback', e)
        self.assertIn('stream_cmd = 0 sent', e)
        self.assertEqual(self.board.regs['stream_cmd'], 0)

    def test_receiver_ctrl_c_slow_name_resolution(self):
        """CP6.1 retest 5: Ctrl-C while the name of the board is being resolved (getaddrinfo of a .local name that does
        not exist: ~5 s with mDNS): exit at once (os._exit; the shutdown of Python waited for the blocked thread).
        Skipped where such a name fails quickly (no mDNS resolver)."""
        name = 'rp-noexiste-xyz-%d.local' % os.getpid()
        t0 = time.time()
        try:
            socket.getaddrinfo(name, 80)
        except OSError:
            pass
        if time.time() - t0 < 1.5:
            self.skipTest('the resolution of a missing .local name is fast here')
        p = subprocess.Popen([sys.executable, '-I', RECEIVER, '-p', str(free_port()), '-o',
                              os.path.join(self.tmp.name, 'nx.bin'), '--board', name, '--app', APP],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.5)
        t_int = time.time()
        p.send_signal(signal.SIGINT)
        o, e = p.communicate(timeout=30)
        dt = time.time() - t_int
        self.assertLess(dt, 1.0, f'exit {dt:.2f} s after the Ctrl-C')
        self.assertEqual(p.returncode, 130, o + e)
        self.assertNotIn('Traceback', e)
        self.assertIn('interrupted while configuring the board', e)
        self.assertIn('never reached', e)

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
