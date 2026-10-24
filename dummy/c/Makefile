# Remote control tools of the App (run on the Red Pitaya, from ssh or from the nginx endpoints of
# ../nginx.conf). Cross compiled from the App Makefile (make c_tools, part of make all) with the Linaro
# toolchain of ../../settings.sh (CROSS_COMPILE=arm-linux-gnueabihf-). On the board itself
# (CROSS_COMPILE empty) the native gcc is used.
#
#   dummy               registers of the dummy module by name (table generated from app.ini)
#   osc                 registers of the oscilloscope by name
#   streaming           waits for stream_cmd != 0 and runs stream_tcp_osc_cmd (started by stream_start.sh)
#   stream_tcp_osc_cmd  scope data to a TCP client
#
# app_regs.h, dummy.txt and the table of dummy.c are written by ../config_tool.py -m.

CC = $(CROSS_COMPILE)gcc
RM = rm

# As rp_lock-in_pid_h: GNU C11, -g, no optimization, stack protector. Independent of the CFLAGS exported
# by the App Makefile.
TOOLS_CFLAGS = -g -std=gnu11 -fstack-protector-strong -Wall $(EXTRA_CFLAGS)

TOOLS = dummy osc streaming stream_tcp_osc_cmd

all: $(TOOLS)

dummy: dummy.c regtool.h app_regs.h
	$(CC) -o $@ dummy.c $(TOOLS_CFLAGS)

osc: osc.c regtool.h
	$(CC) -o $@ osc.c $(TOOLS_CFLAGS)

streaming: streaming.c app_regs.h
	$(CC) -o $@ streaming.c $(TOOLS_CFLAGS)

stream_tcp_osc_cmd: stream_tcp_osc_cmd.c app_regs.h
	$(CC) -o $@ stream_tcp_osc_cmd.c $(TOOLS_CFLAGS)

clean:
	-$(RM) -f $(TOOLS)

.PHONY: all clean
