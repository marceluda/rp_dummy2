# Host-side regression tests of the template (no Red Pitaya, no cross compiler).
#
#   make          build and run every test
#   make clean
#
# auto_set_harness: AUTO (auto-set) of dummy/src/worker.c with a mock scope: 2.0 sample decoding,
# trigger level of a sawtooth/square/DC, time limits (no hang without trigger), quit during AUTO.

SRC     = ../dummy/src
CC      = gcc
CFLAGS  = -std=gnu89 -O0 -g -Wall -I$(SRC)
TIMEOUT = timeout 60

.PHONY: all run clean

all: run

auto_set_harness: auto_set_harness.c $(SRC)/worker.c $(wildcard $(SRC)/*.h)
	$(CC) $(CFLAGS) -o $@ auto_set_harness.c $(SRC)/worker.c -lm -lpthread

run: auto_set_harness
	$(TIMEOUT) ./auto_set_harness

clean:
	rm -f auto_set_harness
