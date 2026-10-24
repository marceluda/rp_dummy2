# Host-side regression tests of the template (no Red Pitaya, no cross compiler, no Vivado).
#
#   make          build and run every test
#   make c        auto_set_harness, trig_level_test and test_tools.sh only
#   make js       web page simulations (node)
#   make py       generator and remote control script tests (python3)
#   make hdl      optional, not in "make": library modules in the Vivado 2020.1 simulator (xsim)
#   make clean
#
# auto_set_harness: AUTO (auto-set) of dummy/src/worker.c with a mock scope: 2.0 sample decoding,
# trigger level of a sawtooth/square/DC, time limits (no hang without trigger), quit during AUTO.
# plot_wheel_sim.js: mouse wheel over the scope (no key both axes, SHIFT time only, ALT Y only, cursors, limits).
# ext_trig_reset_zoom_sim.js: Ext Trig sets Source External + Mode Normal; Reset zoom (one memory at the current Dec).
# raw_trigger_sim.js: units of the trigger level in the page (volts, counts in Raw Mode, switching Raw converts).
# generator_test.py: logo (cairosvg / rsvg-convert / inkscape / fallback), no DEBUG/RELOAD, config_tool.py
# (modules -> tcl, combo texts from muxers and [names], c/names_dic.txt, app.ini changes, --rename),
# App name in the paths of fpga.sh / nginx.conf / src/main.c, c/ without binaries.
# trig_level_test: Raw Mode trigger level (counts -> threshold register) with the real dummy/src/fpga.c.
# test_tools.sh: c/dummy and c/osc built for the PC on a sparse file instead of /dev/mem (reads, writes,
# errors, ranges), and the offsets of app_regs.h against the register struct of the controller.
# remote_test.py: resources/streaming/stream_receiver.py (--board) and resources/remote_control/http_regs.py
# against a mock board (HTTP endpoints + streaming socket) on localhost.
# lib_modules_tb.v (make hdl): fun_icdf, fun_pico, gen_ramp of the library (dummy/fpga/prj/v0.94/rtl/dummy/).

SRC     = ../dummy/src
CC      = gcc
CFLAGS  = -std=gnu89 -O0 -g -Wall -I$(SRC)
TIMEOUT = timeout 60
NODE   ?= node
PYTHON ?= python3

.PHONY: all run c js py hdl clean

all: run

auto_set_harness: auto_set_harness.c $(SRC)/worker.c $(wildcard $(SRC)/*.h)
	$(CC) $(CFLAGS) -o $@ auto_set_harness.c $(SRC)/worker.c -lm -lpthread

run: c js py

trig_level_test: trig_level_test.c $(SRC)/fpga.c $(SRC)/fpga.h
	$(CC) $(CFLAGS) -o $@ trig_level_test.c $(SRC)/fpga.c -lm

c: auto_set_harness trig_level_test
	$(TIMEOUT) ./auto_set_harness
	$(TIMEOUT) ./trig_level_test
	$(TIMEOUT) ./test_tools.sh

JS_SIMS = plot_wheel_sim.js ext_trig_reset_zoom_sim.js raw_trigger_sim.js

js:
	@command -v $(NODE) > /dev/null || { echo "node not found: web page simulations skipped"; exit 0; } ; \
	for t in $(JS_SIMS) ; do \
	  out=$$($(NODE) $$t) ; r=$$? ; echo "$$t: $$(echo "$$out" | tail -1)" ; \
	  if [ $$r -ne 0 ] ; then echo "$$out" | grep FAIL ; exit 1 ; fi ; \
	done

py:
	$(TIMEOUT) $(PYTHON) -B generator_test.py
	$(TIMEOUT) $(PYTHON) -B remote_test.py

LIB = ../dummy/fpga/prj/v0.94/rtl/dummy
VIVADO_SETTINGS ?= /tools/Xilinx/Vivado/2020.1/settings64.sh

hdl:
	@[ -f "$(VIVADO_SETTINGS)" ] || { echo "Vivado not found ($(VIVADO_SETTINGS)): hdl test skipped"; exit 0; } ; \
	rm -rf hdl_sim ; mkdir hdl_sim ; cp $(LIB)/*.dat hdl_sim/ ; \
	env -i HOME="$$HOME" PATH=/usr/bin:/bin bash -c '. "$(VIVADO_SETTINGS)" > /dev/null && cd hdl_sim && \
	  xvlog ../lib_modules_tb.v ../$(LIB)/fun_icdf.v ../$(LIB)/fun_pico.v ../$(LIB)/gen_ramp.v > xvlog.log && \
	  xelab lib_modules_tb -s tb > xelab.log && xsim tb -R > xsim.log' || { echo "hdl: build failed (tests/hdl_sim/*.log)"; exit 1; } ; \
	grep "LIB ERRORS" hdl_sim/xsim.log ; grep -q "LIB ERRORS=0" hdl_sim/xsim.log

clean:
	rm -rf auto_set_harness trig_level_test hdl_sim
