/*
 * regtool.h: read / write FPGA registers by name, from the command line (Red Pitaya, /dev/mem).
 * Shared by c/dummy (registers of the dummy module) and c/osc (registers of the oscilloscope).
 * Based on c/lock.c and c/osc.c of rp_lock-in_pid_h (v2.3.28).
 *
 *   tool                       print every register:  name:value  (one per line)
 *   tool name                  print one register
 *   tool name value [...]      write value (decimal, or 0x... hex) and print the register again
 *   tool name1 name2 v2 ...    any mix of reads and writes, in order
 *
 * Exit status: 0 ok, 1 unknown register name, 2 read-only register, value out of range or not a number,
 *              3 cannot map the FPGA (not root, no /dev/mem).
 * On error a line "ERROR: ..." is printed on stdout (the nginx endpoints return it) and nothing else is done.
 *
 * Only single 32-bit accesses (volatile): never burst reads of the FPGA memory (they can hang the board).
 * Values are checked against the range of the register (min..max of its table entry) before writing.
 */
#ifndef REGTOOL_H
#define REGTOOL_H

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

/* Memory device (a test on a PC maps a sparse file instead, see ../../tests) */
#ifndef REGTOOL_DEV
#define REGTOOL_DEV "/dev/mem"
#endif

typedef struct regtool_reg_s {
    const char *name;
    int         index;      /* address offset / 4 (not the position in the table) */
    int         is_signed;  /* the register holds a signed value (two's complement, sign-extended on read) */
    int         read_only;
    long long   min_val;
    long long   max_val;
} regtool_reg_t;

/* Parse a decimal or 0x... hexadecimal integer; the whole string must be the number */
static int regtool_parse(const char *s, long long *out)
{
    char *end;
    if(s == NULL || s[0] == '\0' || isspace((unsigned char)s[0]))
        return -1;
    errno = 0;
    long long v = strtoll(s, &end, 0);
    if(errno == ERANGE || *end != '\0')
        return -1;
    *out = v;
    return 0;
}

static int regtool_find(const regtool_reg_t *regs, int n, const char *name)
{
    int i;
    for(i = 0; i < n; i++)
        if(strcmp(name, regs[i].name) == 0)
            return i;
    return -1;
}

static void regtool_print(const regtool_reg_t *r, volatile uint32_t *mem)
{
    uint32_t v = mem[r->index];
    if(r->is_signed)
        printf("%s:%d\n", r->name, (int32_t)v);
    else
        printf("%s:%u\n", r->name, v);
}

/* base: physical address of the block; size: bytes to map; regs/n: register table */
static int regtool_main(int argc, char *argv[], unsigned long base, size_t size, const regtool_reg_t *regs, int n)
{
    int fd, jj;
    long page = sysconf(_SC_PAGESIZE);
    void *ptr;
    volatile uint32_t *mem;

    /* Check every argument before touching the FPGA: a bad request does nothing */
    for(jj = 1; jj < argc; jj++) {
        int pos = regtool_find(regs, n, argv[jj]);
        long long v;
        if(pos < 0) {
            printf("ERROR: register '%s' not found\n", argv[jj]);
            return 1;
        }
        if(jj + 1 < argc && regtool_parse(argv[jj+1], &v) == 0) {
            if(regs[pos].read_only) {
                printf("ERROR: %s is read-only\n", regs[pos].name);
                return 2;
            }
            if(v < regs[pos].min_val || v > regs[pos].max_val) {
                printf("ERROR: %s = %lld out of range (%lld .. %lld)\n", regs[pos].name, v,
                       regs[pos].min_val, regs[pos].max_val);
                return 2;
            }
            jj++;
        }
    }

    if((fd = open(REGTOOL_DEV, O_RDWR | O_SYNC)) < 0) {
        printf("ERROR: cannot open %s: %s\n", REGTOOL_DEV, strerror(errno));
        return 3;
    }
    ptr = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off_t)(base & ~(unsigned long)(page - 1)));
    close(fd);
    if(ptr == MAP_FAILED) {
        printf("ERROR: mmap failed: %s\n", strerror(errno));
        return 3;
    }
    mem = (volatile uint32_t *)((char *)ptr + (base & (unsigned long)(page - 1)));

    if(argc < 2) {
        for(jj = 0; jj < n; jj++)
            regtool_print(&regs[jj], mem);
    } else {
        for(jj = 1; jj < argc; jj++) {
            int pos = regtool_find(regs, n, argv[jj]);
            long long v;
            if(jj + 1 < argc && regtool_parse(argv[jj+1], &v) == 0) {
                mem[regs[pos].index] = (uint32_t)v;     /* two's complement for negative values */
                jj++;
            }
            regtool_print(&regs[pos], mem);
        }
    }
    munmap(ptr, size);
    return 0;
}

#endif
