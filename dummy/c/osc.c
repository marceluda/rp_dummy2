/*
 * c/osc: read / write the registers of the oscilloscope (0x40100000) by name. See regtool.h for the usage.
 * Ported from c/osc.c of rp_lock-in_pid_h (v2.3.28). index = address offset / 4.
 *  - 2.0 scope (Vivado 2020.1 FPGA of the App): every trigger locks the trigger logic (TrgSrc bit 5 reads 1)
 *    until 1 is written to TrgUnlock (0x94); write it before TrgSrc. conf bit 2 = trigger received, bit 4 =
 *    acquisition done. Dec has 20 bits (up to 524288).
 *  - 0.9x scope (fpga_eco1): TrgUnlock is unmapped (ignored), Dec has 17 bits.
 *  - DebLen (0x90): external trigger debounce in clocks of 8 ns (the controller writes 12500 = 100 us).
 * The controller re-arms the scope continuously: writes here last until its next acquisition, except while
 * streaming (stream_cmd != 0 in c/dummy), when the scope belongs to c/stream_tcp_osc_cmd.
 *
 * HTTP (nginx.conf of the App):  http://rp-XXXXXX.local/<App>/osc?Dec&TrgSrc
 */
#include "regtool.h"

#define OSC_FPGA_BASE_ADDR 0x40100000
#define OSC_FPGA_BASE_SIZE 0x1000          /* registers only (the buffers are at 0x10000 / 0x20000) */

static const regtool_reg_t registers[] = {
    { "conf"      ,   0, 0, 0,      0,          31LL },
    { "TrgSrc"    ,   1, 0, 0,      0,          31LL },
    { "ChAth"     ,   2, 1, 0,  -8192,        8191LL },
    { "ChBth"     ,   3, 1, 0,  -8192,        8191LL },
    { "TrgDelay"  ,   4, 0, 0,      0,  4294967295LL },
    { "Dec"       ,   5, 0, 0,      0,     1048575LL },
    { "CurWpt"    ,   6, 0, 1,      0,       16383LL },
    { "TrgWpt"    ,   7, 0, 1,      0,       16383LL },
    { "ChAHys"    ,   8, 0, 0,      0,       16383LL },
    { "ChBHys"    ,   9, 0, 0,      0,       16383LL },
    { "AvgEn"     ,  10, 0, 0,      0,           1LL },
    { "PreTrgCnt" ,  11, 0, 1,      0,  4294967295LL },
    { "ChAEqFil1" ,  12, 0, 0,      0,      262143LL },
    { "ChAEqFil2" ,  13, 0, 0,      0,    33554431LL },
    { "ChAEqFil3" ,  14, 0, 0,      0,    33554431LL },
    { "ChAEqFil4" ,  15, 0, 0,      0,    33554431LL },
    { "ChBEqFil1" ,  16, 0, 0,      0,      262143LL },
    { "ChBEqFil2" ,  17, 0, 0,      0,    33554431LL },
    { "ChBEqFil3" ,  18, 0, 0,      0,    33554431LL },
    { "ChBEqFil4" ,  19, 0, 0,      0,    33554431LL },
    { "DebLen"    ,  36, 0, 0,      0,     1048575LL },
    { "TrgUnlock" ,  37, 0, 0,      0,           1LL }
};

int main(int argc, char *argv[])
{
    return regtool_main(argc, argv, OSC_FPGA_BASE_ADDR, OSC_FPGA_BASE_SIZE,
                        registers, (int)(sizeof(registers) / sizeof(registers[0])));
}
