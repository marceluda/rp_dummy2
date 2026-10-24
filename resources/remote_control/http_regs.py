#!/usr/bin/env python3
"""
Read / write registers of a Red Pitaya App generated with rp_dummy2 through its HTTP endpoints
(nginx.conf of the App): /<App>/dummy (dummy module) and /<App>/osc (oscilloscope).

    ./http_regs.py rp-XXXXXX.local my_app                       every register of the dummy module
    ./http_regs.py rp-XXXXXX.local my_app numberA=1234 comboA    write numberA, read comboA
    ./http_regs.py --osc rp-XXXXXX.local my_app Dec TrgSrc       registers of the scope

Prints name:value lines; exits with 1 on an error answer (HTTP 400, "ERROR: ..."). Standard library only.
"""
import argparse
import sys
import urllib.error
import urllib.parse
import urllib.request


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('host')
    ap.add_argument('app')
    ap.add_argument('regs', nargs='*', help='name (read) or name=value (write)')
    ap.add_argument('--osc', action='store_true', help='oscilloscope registers instead of the dummy module')
    a = ap.parse_args()
    query = '&'.join(urllib.parse.quote(r, safe='=-') for r in a.regs)
    url = f'http://{a.host}/{urllib.parse.quote(a.app)}/{"osc" if a.osc else "dummy"}' + (f'?{query}' if query else '')
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            print(r.read().decode(), end='')
            return 0
    except urllib.error.HTTPError as e:
        print(e.read().decode(), end='', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
