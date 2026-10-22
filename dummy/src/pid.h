/**
 * @brief Red Pitaya PID Controller
 *
 * @Author Ales Bardorfer <ales.bardorfer@redpitaya.com>
 *         
 * (c) Red Pitaya  http://www.redpitaya.com
 *
 * This part of code is written in C programming language.
 * Please visit http://en.wikipedia.org/wiki/C_(programming_language)
 * for more details on the language used herein.
 */

#ifndef __PID_H
#define __PID_H

#include "main.h"

/* 1 if the FPGA has the PID block (bus slot 3 = 0x403xxxxx). new_project.py sets it to 0 when
 * [general] include_pids = False: then red_pitaya_top.v answers that slot with a stub (ack=1, rdata=0)
 * and pid_* never touch that address range. */
#define PID_FPGA_HAS_PID 1

int pid_init(void);
int pid_exit(void);

int pid_update(rp_app_params_t *params);

#endif // __PID_H
