/*
 * Host test of the Raw Mode trigger level conversion of dummy/src/fpga.c (rp_dummy2 2.0.1), linked with the real
 * fpga.c: osc_fpga_cnv_cnt_to_trig_v() must give the voltage that osc_fpga_cnv_v_to_cnt() (the function that writes
 * the threshold of the scope) turns into exactly the same counts, for every 14-bit level, calibration offset,
 * full scale and user offset. Before, the worker passed the counts as volts: 100 counts -> threshold 8191.
 * 2.0.2: half counts rounded as the page (Math.round): -2.5 -> -2 (roundf() gave -3).
 *   make -C tests c
 */
#include <stdio.h>
#include <math.h>
#include "fpga.h"

int main(void)
{
    static const float adc_max[] = { 1.0f, 1.0835f, 20.5f };
    static const int   calib[]   = { 0, 37, -25 };
    static const float user[]    = { 0.0f, 0.1f };
    int a, b, u, c, fails = 0, n = 0, clamped = 0, old;
    for(a = 0; a < 3; a++)
        for(b = 0; b < 3; b++)
            for(u = 0; u < 2; u++)
                for(c = -8192; c <= 8191; c++) {
                    float v = osc_fpga_cnv_cnt_to_trig_v((float)c, adc_max[a], calib[b], user[u]);
                    int   r = osc_fpga_cnv_v_to_cnt(v, adc_max[a], calib[b], user[u]);
                    n++;
                    /* osc_fpga_cnv_v_to_cnt() clamps the voltage to +-adc_max_v before taking the user offset out:
                     * with a user offset the extreme levels saturate (as in volts mode) */
                    /* (and a level that, with the calibration offset, is beyond the 14-bit range saturates too) */
                    if(fabsf(v) > adc_max[a] || c + calib[b] > 8191 || c + calib[b] < -8192) { clamped++; continue; }
                    if((r & 0x3FFF) != (c & 0x3FFF)) {
                        if(fails++ < 10)
                            printf("  FAIL: %d counts (max %g V, calib %d, user %g V) -> %g V -> %d\n",
                                   c, adc_max[a], calib[b], user[u], v, r);
                    }
                }
    printf("  %s: %d levels x full scales x offsets -> the same counts in the threshold register (%d failures; "
           "%d beyond the full scale with the user/calibration offset, saturated as in volts mode)\n",
           fails ? "FAIL" : "PASS", n, fails, clamped);
    /* 2.0.2: half counts (the level of an AUTO in Raw Mode of 2.0.1, a config file, a remote client) are rounded as the
     * page shows them, Math.round (halves up): -2.5 -> -2, 2.5 -> 3. Before, roundf(): -2.5 -> -3 (page "-2") */
    {
        static const float half[] = { -2.5f, 2.5f, -0.5f, 0.5f, -2497.5f, 8190.5f, -8191.5f, -2.4f, -2.6f };
        int h, hf = 0;
        for(h = 0; h < (int)(sizeof(half) / sizeof(half[0])); h++)
            for(b = 0; b < 3; b++) {
                int want = (int)floorf(half[h] + 0.5f);              /* Math.round() of the page */
                float v  = osc_fpga_cnv_cnt_to_trig_v(half[h], 1.0f, calib[b], 0.0f);
                int   r  = osc_fpga_cnv_v_to_cnt(v, 1.0f, calib[b], 0.0f);
                if(want + calib[b] > 8191 || want + calib[b] < -8192)
                    continue;                                          /* saturated, as above */
                if((r & 0x3FFF) != (want & 0x3FFF)) {
                    hf++;
                    printf("  FAIL: %g counts (calib %d) -> threshold %d, the page shows %d\n", half[h], calib[b],
                           (r & 0x2000) ? (r & 0x3FFF) - 0x4000 : (r & 0x3FFF), want);
                }
            }
        printf("  %s: half counts -> the threshold is the count shown by the page (Math.round; %d failures)\n",
               hf ? "FAIL" : "PASS", hf);
        fails += hf;
    }
    old = osc_fpga_cnv_v_to_cnt(100.0f, 1.0f, 0, 0.0f);
    printf("  PASS: (reference) the old path, 100 counts taken as 100 V, gives %d\n", old);
    if(fails == 0 && old == 8191) { printf("ALL PASS (0 failures)\n"); return 0; }
    printf("FAILED\n");
    return 1;
}
