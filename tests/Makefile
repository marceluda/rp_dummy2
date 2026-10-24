# Host-side regression tests of the template (no Red Pitaya, no cross compiler, no Vivado).
#
#   make          build and run every test
#   make c        auto_set_harness and test_tools.sh only
#   make js       web page simulations (node)
#   make py       generator tests (python3)
#   make clean
#
# auto_set_harness: AUTO (auto-set) of dummy/src/worker.c with a mock scope: 2.0 sample decoding,
# trigger level of a sawtooth/square/DC, time limits (no hang without trigger), quit during AUTO.
# plot_wheel_sim.js: mouse wheel over the scope (no key both axes, SHIFT time only, ALT Y only, cursors, limits).
# ext_trig_reset_zoom_sim.js: Ext Trig sets Source External + Mode Normal; Reset zoom (one memory at the current Dec).
# generator_test.py: logo (cairosvg / rsvg-convert / inkscape / fallback), no DEBUG/RELOAD, config_tool.py
# (modules -> tcl, combo texts from muxers and [names], c/names_dic.txt, app.ini changes, --rename),
# App name in the paths of fpga.sh / nginx.conf / src/main.c, c/ without binaries.
# test_tools.sh: c/dummy and c/osc built for the PC on a sparse file instead of /dev/mem (reads, writes,
# errors, ranges), and the offsets of app_regs.h against the register struct of the controller.

SRC     = ../dummy/src
CC      = gcc
CFLAGS  = -std=gnu89 -O0 -g -Wall -I$(SRC)
TIMEOUT = timeout 60
NODE   ?= node
PYTHON ?= python3

.PHONY: all run c js py clean

all: run

auto_set_harness: auto_set_harness.c $(SRC)/worker.c $(wildcard $(SRC)/*.h)
	$(CC) $(CFLAGS) -o $@ auto_set_harness.c $(SRC)/worker.c -lm -lpthread

run: c js py

c: auto_set_harness
	$(TIMEOUT) ./auto_set_harness
	$(TIMEOUT) ./test_tools.sh

JS_SIMS = plot_wheel_sim.js ext_trig_reset_zoom_sim.js

js:
	@command -v $(NODE) > /dev/null || { echo "node not found: web page simulations skipped"; exit 0; } ; \
	for t in $(JS_SIMS) ; do \
	  out=$$($(NODE) $$t) ; r=$$? ; echo "$$t: $$(echo "$$out" | tail -1)" ; \
	  if [ $$r -ne 0 ] ; then echo "$$out" | grep FAIL ; exit 1 ; fi ; \
	done

py:
	$(TIMEOUT) $(PYTHON) -B generator_test.py

clean:
	rm -f auto_set_harness
