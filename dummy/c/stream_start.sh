#!/bin/sh
# Starts c/streaming detached from nginx (from rp_lock-in_pid_h v2.3.28, any App folder).
# Called by the /<App>/streaming location of nginx.conf. nginx must not wait for it (an io.popen() pipe
# kept the nginx worker blocked until the streaming ended): the process gets its own session, no pipe to
# nginx, and this script returns at once. c/streaming then waits for stream_cmd != 0 (c/dummy).
D=$(cd "$(dirname "$0")" && pwd)
APP=$(basename "$(dirname "$D")")
LOG=/tmp/${APP}_streaming.log

# Only one instance: a previous one (maybe with another IP/port) is replaced.
# stream_tcp_osc_cmd runs in its own process group, so it is stopped explicitly too.
PIDS=$(pidof $D/streaming $D/stream_tcp_osc_cmd)
if [ -n "$PIDS" ]; then
    kill $PIDS 2>/dev/null
    i=0
    while [ $i -lt 10 ] && [ -n "$(pidof $D/streaming $D/stream_tcp_osc_cmd)" ]; do
        sleep 0.1; i=$((i+1))
    done
    PIDS=$(pidof $D/streaming $D/stream_tcp_osc_cmd)
    [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null
fi

if command -v setsid >/dev/null 2>&1; then
    setsid $D/streaming > $LOG 2>&1 < /dev/null &
else
    nohup  $D/streaming > $LOG 2>&1 < /dev/null &
fi
exit 0
