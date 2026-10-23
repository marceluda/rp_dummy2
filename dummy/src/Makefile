CC=$(CROSS_COMPILE)gcc
RM=rm

OBJECTS=main.o fpga.o worker.o calib.o fpga_awg.o generate.o fpga_pid.o pid.o fpga_dummy.o dummy.o

CFLAGS+= -Wall -Werror -g -fPIC $(INCLUDE)
# -lm: round/ceil/sqrt...; -lpthread: worker thread and mutexes (explicit, so that controllerhf.so
# does not depend on the libraries the server happens to have loaded)
LDFLAGS=-shared -lm -lpthread

CONTROLLER = ../controllerhf.so

# Objects in obj/. For the TRACE() messages (stderr, nginx log) uncomment "#define DEBUG 1" in main.h.
OBJ_N   = $(addprefix obj/,$(OBJECTS))
HEADERS = $(wildcard *.h)

all: $(CONTROLLER)

obj/%.o: %.c $(HEADERS)
	@mkdir -p obj
	$(CC) $(CFLAGS) -c -o $@ $<

$(CONTROLLER): $(OBJ_N)
	$(CC) -o $@ $^ $(CFLAGS) $(LDFLAGS)

clean:
	-$(RM) -rf obj *.o

.PHONY: all clean
