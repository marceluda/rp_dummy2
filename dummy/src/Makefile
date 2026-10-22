CC=$(CROSS_COMPILE)gcc
RM=rm

OBJECTS=main.o fpga.o worker.o calib.o fpga_awg.o generate.o fpga_pid.o pid.o fpga_dummy.o dummy.o

CFLAGS+= -Wall -Werror -g -fPIC $(INCLUDE)
# -lm: round/ceil/sqrt...; -lpthread: worker thread and mutexes (explicit, so that controllerhf.so
# does not depend on the libraries the server happens to have loaded)
LDFLAGS=-shared -lm -lpthread

CONTROLLER     = ../controllerhf.so
CONTROLLER_DBG = ../controllerhf_dbg.so
CONTROLLER_RLD = ../controllerhf_rld.so

# Each controller is compiled into its own object folder, with its own defines:
#   controllerhf.so      normal
#   controllerhf_dbg.so  -DDEBUG=1  (TRACE() messages on stderr, see main.h)
#   controllerhf_rld.so  -DRELOAD   (does not write the dummy registers on start, see main.c)
# (Before, the sources were edited with sed after the objects were compiled: the three .so were identical.)
OBJ_N = $(addprefix obj/,$(OBJECTS))
OBJ_D = $(addprefix obj_dbg/,$(OBJECTS))
OBJ_R = $(addprefix obj_rld/,$(OBJECTS))
HEADERS = $(wildcard *.h)

all: $(CONTROLLER)

obj/%.o: %.c $(HEADERS)
	@mkdir -p obj
	$(CC) $(CFLAGS) -c -o $@ $<

obj_dbg/%.o: %.c $(HEADERS)
	@mkdir -p obj_dbg
	$(CC) $(CFLAGS) -DDEBUG=1 -c -o $@ $<

obj_rld/%.o: %.c $(HEADERS)
	@mkdir -p obj_rld
	$(CC) $(CFLAGS) -DRELOAD -c -o $@ $<

$(CONTROLLER): $(OBJ_N)
	$(CC) -o $@ $^ $(CFLAGS) $(LDFLAGS)

$(CONTROLLER_DBG): $(OBJ_D)
	$(CC) -o $@ $^ $(CFLAGS) -DDEBUG=1 $(LDFLAGS)

$(CONTROLLER_RLD): $(OBJ_R)
	$(CC) -o $@ $^ $(CFLAGS) -DRELOAD $(LDFLAGS)

clean:
	-$(RM) -rf obj obj_dbg obj_rld *.o

.PHONY: all clean
