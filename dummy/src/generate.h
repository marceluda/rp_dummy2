/**
 * $Id: generate.h 882 2013-12-16 12:46:01Z crt.valentincic $
 *
 * @brief Red Pitaya simple signal/function generator with pre-defined
 *        signal types.
 *
 * @Author Jure Menart <juremenart@gmail.com>
 *         
 * (c) Red Pitaya  http://www.redpitaya.com
 *
 * This part of code is written in C programming language.
 * Please visit http://en.wikipedia.org/wiki/C_(programming_language)
 * for more details on the language used herein.
 */

#ifndef __GENERATE_H
#define __GENERATE_H

#include "main.h"
#include "calib.h"

/** @defgroup generate_h Arbitrary Signal Generator
 * @{
 */

/** Signal types */
typedef enum awg_signal_e {
    eSignalSine = 0,     /* Sinusoidal waveform. */
    eSignalSquare,       /* Square waveform. */
    eSignalTriangle,     /* Triangular waveform. */
    eSignalFile          /* Waveform read from file */
} awg_signal_t;

/** AWG FPGA parameters */
typedef struct awg_param_s {
    int32_t  offsgain;   /* AWG offset & gain. */
    uint32_t wrap;       /* AWG buffer wrap value. */
    uint32_t step;       /* AWG step interval. */
} awg_param_t;

/** @} */

/* 1 if the FPGA has the signal generator (ASG, bus slot 2 = 0x402xxxxx). new_project.py sets it to 0 when
 * [general] include_genfun = False: then red_pitaya_top.v answers that slot with a stub (ack=1, rdata=0)
 * and generate_* never touch that address range (no mmap, no writes). */
#define GEN_FPGA_HAS_ASG 1

int generate_init(rp_calib_params_t *calib_params);
int generate_exit(void);

int generate_update(rp_app_params_t *params);

#endif // __GENERATE_H
