#!/bin/bash
# Host-side test of the c/ register tools of the template (c/dummy, c/osc) without a Red Pitaya:
# they are compiled with REGTOOL_DEV = a sparse file that stands for /dev/mem, and run with valid and invalid
# arguments. Also checks that c/app_regs.h (offsets of the streaming tools) matches the register struct of
# the controller (src/fpga_dummy.h). Run from the repo:  make -C tests
set -u
SRC=../dummy
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
FAIL=0
ok()   { echo "  PASS: $*"; }
bad()  { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }
expect() {   # expect <description> <expected exit> <expected output regex> -- command...
    local d="$1" ex="$2" re="$3"; shift 4
    local out; out=$("$@" 2>&1); local rc=$?
    if [ "$rc" = "$ex" ] && echo "$out" | grep -Eq -- "$re"; then ok "$d"; else bad "$d (exit $rc, output: $(echo $out | head -c 200))"; fi
}
# 32-bit little-endian word of the fake memory at byte address A
word() { od -An -t d4 -j $(( $1 )) -N 4 "$2" | tr -d ' '; }

truncate -s $(( 0x40601000 )) "$T/mem_dummy"
truncate -s $(( 0x40101000 )) "$T/mem_osc"
gcc -std=gnu11 -Wall -Werror -DREGTOOL_DEV="\"$T/mem_dummy\"" -I$SRC/c -o "$T/dummy" $SRC/c/dummy.c || { echo "build of c/dummy failed"; exit 1; }
gcc -std=gnu11 -Wall -Werror -DREGTOOL_DEV="\"$T/mem_osc\""   -I$SRC/c -o "$T/osc"   $SRC/c/osc.c   || { echo "build of c/osc failed"; exit 1; }
gcc -std=gnu11 -Wall -Werror -fsyntax-only $SRC/c/streaming.c $SRC/c/stream_tcp_osc_cmd.c -I$SRC/c || bad "streaming tools do not compile"

echo "c/dummy (template registers)"
B=$(( 0x40600000 ))
expect "list every register"            0 "^oscA_sw:0"                 -- "$T/dummy"
expect "write stream_port 6001"         0 "^stream_port:6001$"         -- "$T/dummy" stream_port 6001
[ "$(word $((B+0x58)) "$T/mem_dummy")" = "6001" ] && ok "stream_port at 0x058" || bad "stream_port not at 0x058"
expect "write stream_ip 4294967295"     0 "^stream_ip:4294967295$"     -- "$T/dummy" stream_ip 4294967295
expect "hex value 0x10"                 0 "^stream_rate:16$"           -- "$T/dummy" stream_rate 0x10
expect "write + read in one call"       0 "stream_cmd:1"               -- "$T/dummy" stream_cmd 1 stream_rate
expect "unknown register -> exit 1"     1 "^ERROR: register 'nope' not found" -- "$T/dummy" nope
expect "read-only register -> exit 2"   2 "^ERROR: in1 is read-only"   -- "$T/dummy" in1 5
expect "out of range -> exit 2"         2 "^ERROR: oscA_sw = 32 out of range" -- "$T/dummy" oscA_sw 32
expect "negative unsigned -> exit 2"    2 "out of range"               -- "$T/dummy" stream_port -1
expect "not a number = read"            1 "^ERROR: register 'abc' not found" -- "$T/dummy" trig_sw abc
expect "bad request writes nothing"     2 "out of range"               -- "$T/dummy" oscB_sw 7 oscA_sw 99
[ "$(word $((B+0x04)) "$T/mem_dummy")" = "0" ] && ok "oscB_sw untouched after the rejected request" || bad "oscB_sw written by a rejected request"
printf '\xff\xff\xff\xff' | dd of="$T/mem_dummy" bs=1 seek=$((B+0x28)) conv=notrunc status=none   # in1 = -1
expect "signed read (in1 = -1)"         0 "^in1:-1$"                   -- "$T/dummy" in1

echo "c/osc"
expect "write TrgUnlock 1"              0 "^TrgUnlock:1$"              -- "$T/osc" TrgUnlock 1
[ "$(word $((0x40100000+0x94)) "$T/mem_osc")" = "1" ] && ok "TrgUnlock at 0x094" || bad "TrgUnlock not at 0x094"
expect "DebLen 12500 at 0x090"          0 "^DebLen:12500$"             -- "$T/osc" DebLen 12500
expect "ChAth -100 (signed)"            0 "^ChAth:-100$"               -- "$T/osc" ChAth -100
expect "Dec 524288"                     0 "^Dec:524288$"               -- "$T/osc" Dec 524288
expect "CurWpt read-only"               2 "read-only"                  -- "$T/osc" CurWpt 1

echo "app_regs.h vs src/fpga_dummy.h"
cat > "$T/regs_check.c" <<'C'
#include <stddef.h>
#include "fpga_dummy.h"
#include "app_regs.h"
_Static_assert(offsetof(dummy_reg_t, stream_ip)   == DUMMY_STREAM_IP_OFF,   "stream_ip");
_Static_assert(offsetof(dummy_reg_t, stream_port) == DUMMY_STREAM_PORT_OFF, "stream_port");
_Static_assert(offsetof(dummy_reg_t, stream_rate) == DUMMY_STREAM_RATE_OFF, "stream_rate");
_Static_assert(offsetof(dummy_reg_t, stream_cmd)  == DUMMY_STREAM_CMD_OFF,  "stream_cmd");
int main(void) { return 0; }
C
gcc -std=gnu11 -Wall -I$SRC/src -I$SRC/c -o "$T/regs_check" "$T/regs_check.c" 2>"$T/err" && ok "offsets of the streaming registers agree" || { bad "offsets differ"; cat "$T/err"; }

echo "$([ $FAIL = 0 ] && echo ALL PASS || echo FAILED) ($FAIL failures)"
exit $FAIL
