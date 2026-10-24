/**
 * $Id: main.c 881 2013-12-16 05:37:34Z rp_jmenart $
 *
 * @brief Red Pitaya Oscilloscope main module.
 *
 * @Author Jure Menart <juremenart@gmail.com>
 *
 * (c) Red Pitaya  http://www.redpitaya.com
 *
 * This part of code is written in C programming language.
 * Please visit http://en.wikipedia.org/wiki/C_(programming_language)
 * for more details on the language used herein.
 */

#include <stdio.h>
#include <unistd.h>
#include <sys/types.h>
#include <signal.h>
#include <dirent.h>
#include <pthread.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <errno.h>
#include <sys/time.h>

#include "main.h"
#include "version.h"
#include "worker.h"
#include "fpga.h"
#include "calib.h"
#include "generate.h"
#include "pid.h"
#include "dummy.h"
#include "fpga_dummy.h"


/* Describe app. parameters with some info/limitations */
pthread_mutex_t rp_main_params_mutex = PTHREAD_MUTEX_INITIALIZER;
static rp_app_params_t rp_main_params[PARAMS_NUM+1] = {
    { /* min_gui_time   */
        //"xmin", -1000000, 1, 0, -10000000, +10000000 },
        "xmin", 0, 1, 0, -60000000, +60000000 },
    { /* max_gui_time   */
        //"xmax", +1000000, 1, 0, -10000000, +10000000 },
        "xmax", 131, 1, 0, -60000000, +60000000 },
    { /* trig_mode:
       *    0 - auto
       *    1 - normal
       *    2 - single  */
        "trig_mode", 0, 1, 0,         0,         2 },
    { /* trig_source:
       *    0 - ChA
       *    1 - ChB
       *    2 - ext.    */
        "trig_source", 0, 1, 0,         0,         2 },
    { /* trig_edge:
       *    0 - rising
       *    1 - falling */
        "trig_edge", 0, 1, 0,         0,         1 },
    { /* trig_delay     */
        "trig_delay", 0, 1, 1, -10000000, +10000000 },
    { /* trig_level : Trigger level, expressed in normalized 1V  */
        "trig_level", 0, 1, 0,     -8192,     +8191 }, // LOLO
    { /* single_button:
       *    0 - ignore
       *    1 - trigger */
        "single_btn", 0, 1, 0,         0,         1 },
    { /* time_range:
       *  decimation:
       *    0 - 1x
       *    1 - 8x
       *    2 - 64x
       *    3 - 128x
       *    4 - 256x
       *    5 - 512x
       *    6 - 1kx
       *    7 - 8kx
       *    8 - 65kx
       *    9 - 524k (20-bit decimation of the 2.0 scope; the 0.9x scope of fpga_eco1 has 17 bits: 64k) */
        "time_range", 0, 1, 1,         0,         9 },
    { /* time_unit_used:
       *    0 - [us]
       *    1 - [ms]
       *    2 - [s]     */
        "time_units", 0, 0, 1,         0,         2 },
    { /* en_avg_at_dec:
           *    0 - disable
           *    1 - enable */
        "en_avg_at_dec", 0, 1, 0,      0,         1 },
    { /* auto_flag:
       * Puts the controller to auto mode - the algorithm which detects input
       * signal and changes the parameters to most fit the input:
       *    0 - normal operation
       *    1 - auto button pressed */
        "auto_flag", 0, 1, 0, 0, 1 },
    { /* min_y, max_y - Controller defined Y range when using auto-set or after
       * gain change y range */
        "min_y", 0, 0, 0, -1000, +1000 },
    { /* min_y, max_y - Controller defined Y range when using auto-set or after
       * gain change y range */
        "max_y", 0, 0, 0, -1000, +1000 },
    { /* forcex_flag:
       * Server sets this flag when X axis time units change
       * Client checks this flag, when set the server's xmin:xmax define the visualization range
       *    0 - normal operation
       *    1 - Server forces xmin, xmax  */
        "forcex_flag", 0, 0, 0, 0, 1 },
      /* Measurement parameters for both channels. All are read-only and they
       * are calculated on FPGA buffer (non decimated in SW):
       * min, max [V] - minimum and maximum value in the buffer (non-decimated)
       * amp [Vpp] - amplitude = maximum - minum
       * avg [V] - average value
       * freq [MHz] - frequency of the signal (if any, otherwise NaN)
       * period [s] - period of the signal (if any, otherwise NaN)
       **/
    {  "meas_min_ch1", 0, 0, 1, -1000, +1000 },
    {  "meas_max_ch1", 0, 0, 1, +1000, -1000 },
    {  "meas_amp_ch1", 0, 0, 1, +1000, -1000 },
    {  "meas_avg_ch1", 0, 0, 1, +1000, -1000 },
    {  "meas_freq_ch1", 0, 0, 1, 0, 1e9 },
    {  "meas_per_ch1", 0, 0, 1, 0, 1e9 },
    {  "meas_min_ch2", 0, 0, 1, -1000, +1000 },
    {  "meas_max_ch2", 0, 0, 1, +1000, -1000 },
    {  "meas_amp_ch2", 0, 0, 1, +1000, -1000 },
    {  "meas_avg_ch2", 0, 0, 1, +1000, -1000 },
    {  "meas_freq_ch2", 0, 0, 1, 0, 1e9 },
    {  "meas_per_ch2", 0, 0, 1, 0, 1e9 },
    { /* prb_att_ch1 - User probe attenuation setting for channel 1:
       *    0 - 1x
       *    1 - 10x */
        "prb_att_ch1", 0, 1, 0, 0, 1 },
    { /* gain_ch1 - User jumper gain setting for channel 1:
       *    0 - high gain (0.6 [V] Full-scale)
       *    1 - low gain (15 [V] Full-scale) */
        "gain_ch1", 0, 1, 0, 0, 1 },
    { /* prb_att_ch2 - User probe attenuation setting for channel 2:
       *    0 - 1x
       *    1 - 10x */
        "prb_att_ch2", 0, 1, 0, 0, 1 },
    { /* gain_ch2 - User jumper gain setting for channel 2:
       *    0 - high gain (0.6 [V] Full-scale)
       *    1 - low gain (15 [V] Full-scale) */
        "gain_ch2", 0, 1, 0, 0, 1 },
    { /* gui_reset_y_range - Maximum voltage range [Vpp] with current settings
       * This parameter is calculated by application and is read-only for
       * client.
       */
        "gui_reset_y_range", 28, 0, 1, 0, 2000 },
    { /* gen_DC_offs_1 - DC offset for channel 1 expressed in [V] requested by
       * GUI */
        "gen_DC_offs_1", 0, 1, 0, -100, 100 },
    { /* gen_DC_offs_2 - DC offset for channel 2 expressed in [V] requested by
       * GUI */
        "gen_DC_offs_2", 0, 1, 0, -100, 100 },
    { /* gui_xmin - Xmin as specified by GUI - not rounded to sampling engine quanta. */
        "gui_xmin",      0, 0, 1, -60000000, +60000000 },
    { /* gui_xmax - Xmax as specified by GUI - not rounded to sampling engine quanta. */
        "gui_xmax",    131, 0, 1, -60000000, +60000000 },
    { /* min_y_norm, max_y_norm - Normalized controller defined Y range when using auto-set */
        "min_y_norm", 0, 0, 0, -1000, +1000 },
    { /* min_y_norm, max_y_norm - Normalized controller defined Y range when using auto-set */
        "max_y_norm", 0, 0, 0, -1000, +1000 },
    { /* gen_DC_norm_1 - DC offset for channel 1 expressed in normalized 1V */
        "gen_DC_norm_1", 0, 1, 0, -100, 100 },
    { /* gen_DC_norm_2 - DC offset for channel 2 expressed in normalized 1V */
        "gen_DC_norm_2", 0, 1, 0, -100, 100 },
    { /* scale_ch1 - Jumper & probe attenuation dependent Y scaling factor for Channel 1 */
        "scale_ch1", 0, 0, 1, -1000, 1000 },
    { /* scale_ch2 - Jumper & probe attenuation dependent Y scaling factor for Channel 2 */
        "scale_ch2", 0, 0, 1, -1000, 1000 },

    /********************************************************/
    /* Arbitrary Waveform Generator parameters from here on */
    /********************************************************/

    { /* gen_trig_mod_ch1 - Selects the trigger mode for channel 1:
       *    0 - continuous
       *    1 - single
       *    2 - external */
        "gen_trig_mod_ch1", 0, 1, 0, 0, 2 },
    { /* gen_sig_type_ch1 - Selects the type of signal for channel 1:
       *    0 - sine
       *    1 - square
       *    2 - triangle
       *    3 - from file */
        "gen_sig_type_ch1", 0, 1, 0, 0, 3 },
    { /* gen_enable_ch1 - Enables/disable signal generation on channel 1:
       *    0 - Channel 1 disabled
       *    1 - Channel 1 enabled */
        "gen_enable_ch1", 0, 1, 0, 0, 1 },
    { /* gen_single_ch1 - Fire single trigger on generator channel 1:
       *    0 - Do not fire single trigger
       *    1 - Fire single trigger */
        "gen_single_ch1", 0, 1, 0, 0, 1 },
    { /* gen_sig_amp_ch1 - Amplitude for Channel 1 in [Vpp] */
        "gen_sig_amp_ch1", 0, 1, 0, 0, 2.0 },
    { /* gen_sig_freq_ch1 - Frequency for Channel 1 in [Hz] */
        "gen_sig_freq_ch1", 1000, 1, 0, 0, 50e6 },
    { /* gen_sig_dcoff_ch1 - DC offset applied to the signal in [V] */
        "gen_sig_dcoff_ch1", 0, 1, 0, -1, 1 },
    { /* gen_trig_mod_ch2 - Selects the trigger mode for channel 2:
       *    0 - continuous
       *    1 - single
       *    2 - external */
        "gen_trig_mod_ch2", 0, 1, 0, 0, 2 },
    { /* gen_sig_type_ch2 - Selects the type of signal for channel 2:
       *    0 - sine
       *    1 - square
       *    2 - triangle
       *    3 - from file */
        "gen_sig_type_ch2", 0, 1, 0, 0, 3 },
    { /* gen_enable_ch2 - Enables/disable signal generation on channel 2:
       *    0 - channel 2 disabled
       *    1 - channel 2 enabled */
        "gen_enable_ch2", 0, 1, 0, 0, 1 },
    { /* gen_single_ch2 - Fire single trigger on generator channel 2:
       *    0 - Do not fire single trigger
       *    1 - Fire single trigger */
        "gen_single_ch2", 0, 1, 0, 0, 1 },
    { /* gen_sig_amp_ch2 - Amplitude for channel 2 in [Vpp] */
        "gen_sig_amp_ch2", 0, 1, 0, 0, 2.0 },
    { /* gen_sig_freq_ch2 - Frequency for channel 2 in [Hz] */
        "gen_sig_freq_ch2", 1000, 1, 0, 0.2, 50e6 },
    { /* gen_sig_dcoff_ch2 - DC offset applied to the signal in [V] */
        "gen_sig_dcoff_ch2", 0, 1, 0, -1, 1 },
    { /* gen_awg_refresh - Refresh AWG data from (uploaded) file.
       *     0 - Do not refresh
       *     1 - Refresh Channel 1
       *     2 - Refresh Channel 2
       */
        "gen_awg_refresh",   0, 0, 0, 0, 2 },

    /******************************************/
    /* PID Controller parameters from here on */
    /******************************************/

    { /* pid_NN_enable - Enables/closes or disables/open PID NN loop:
       *    0 - PID disabled (open loop)
       *    1 - PID enabled (closed loop)    */
        "pid_11_enable", 0, 1, 0, 0, 1 },
    { /* pid_NN_rst - Reset PID NN integrator:
        *    0 - Do not reset integrator
        *    1 - Reset integrator            */
        "pid_11_rst", 0, 1, 0, 0, 1 },
    { /* pid_NN_sp - PID NN set-point in [ADC] counts. */
        "pid_11_sp",  0, 1, 0, -8192, 8191 },
    { /* pid_NN_kp - PID NN proportional gain Kp in [ADC] counts. */
        "pid_11_kp",  0, 1, 0, -8192, 8191 },
    { /* pid_NN_ki - PID NN integral gain     Ki in [ADC] counts. */
        "pid_11_ki",  0, 1, 0, -8192, 8191 },
    { /* pid_NN_kd - PID NN derivative gain   Kd in [ADC] counts. */
        "pid_11_kd",  0, 1, 0, -8192, 8191 },

    { /* pid_NN_enable - Enables/closes or disables/open PID NN loop:
       *    0 - PID disabled (open loop)
       *    1 - PID enabled (closed loop)    */
        "pid_12_enable", 0, 1, 0, 0, 1 },
    { /* pid_NN_rst - Reset PID NN integrator:
        *    0 - Do not reset integrator
        *    1 - Reset integrator            */
        "pid_12_rst", 0, 1, 0, 0, 1 },
    { /* pid_NN_sp - PID NN set-point in [ADC] counts. */
        "pid_12_sp",  0, 1, 0, -8192, 8191 },
    { /* pid_NN_kp - PID NN proportional gain Kp in [ADC] counts. */
        "pid_12_kp",  0, 1, 0, -8192, 8191 },
    { /* pid_NN_ki - PID NN integral gain     Ki in [ADC] counts. */
        "pid_12_ki",  0, 1, 0, -8192, 8191 },
    { /* pid_NN_kd - PID NN derivative gain   Kd in [ADC] counts. */
        "pid_12_kd",  0, 1, 0, -8192, 8191 },

    { /* pid_NN_enable - Enables/closes or disables/open PID NN loop:
       *    0 - PID disabled (open loop)
       *    1 - PID enabled (closed loop)    */
        "pid_21_enable", 0, 1, 0, 0, 1 },
    { /* pid_NN_rst - Reset PID NN integrator:
        *    0 - Do not reset integrator
        *    1 - Reset integrator            */
        "pid_21_rst", 0, 1, 0, 0, 1 },
    { /* pid_NN_sp - PID NN set-point in [ADC] counts. */
        "pid_21_sp",  0, 1, 0, -8192, 8191 },
    { /* pid_NN_kp - PID NN proportional gain Kp in [ADC] counts. */
        "pid_21_kp",  0, 1, 0, -8192, 8191 },
    { /* pid_NN_ki - PID NN integral gain     Ki in [ADC] counts. */
        "pid_21_ki",  0, 1, 0, -8192, 8191 },
    { /* pid_NN_kd - PID NN derivative gain   Kd in [ADC] counts. */
        "pid_21_kd",  0, 1, 0, -8192, 8191 },

    { /* pid_NN_enable - Enables/closes or disables/open PID NN loop:
       *    0 - PID disabled (open loop)
       *    1 - PID enabled (closed loop)    */
        "pid_22_enable", 0, 1, 0, 0, 1 },
    { /* pid_NN_rst - Reset PID NN integrator:
        *    0 - Do not reset integrator
        *    1 - Reset integrator            */
        "pid_22_rst", 0, 1, 0, 0, 1 },
    { /* pid_NN_sp - PID NN set-point in [ADC] counts. */
        "pid_22_sp",  0, 1, 0, -8192, 8191 },
    { /* pid_NN_kp - PID NN proportional gain Kp in [ADC] counts. */
        "pid_22_kp",  0, 1, 0, -8192, 8191 },
    { /* pid_NN_ki - PID NN integral gain     Ki in [ADC] counts. */
        "pid_22_ki",  0, 1, 0, -8192, 8191 },
    { /* pid_NN_kd - PID NN derivative gain   Kd in [ADC] counts. */
        "pid_22_kd",  0, 1, 0, -8192, 8191 },

    /*********************************************/
    /** DUMMY Controller parameters from here on **/
    /*********************************************/

    // [MAINDEF DOCK]

    { "dummy_oscA_sw"                 ,      1, 1, 0,            0,           31 }, /** switch for muxer oscA **/
    { "dummy_oscB_sw"                 ,      2, 1, 0,            0,           31 }, /** switch for muxer oscB **/
    { "dummy_osc1_filt_off"           ,      1, 1, 0,            0,            1 }, /** oscilloscope control osc1_filt_off **/
    { "dummy_osc2_filt_off"           ,      1, 1, 0,            0,            1 }, /** oscilloscope control osc2_filt_off **/
    { "dummy_osc_raw_mode"            ,      0, 0, 0,            0,            1 }, /** Set oscilloscope mode in Raw (int unit instead of Volts) **/
    { "dummy_osc_lockin_mode"         ,      0, 0, 0,            0,            1 }, /** Set oscilloscope mode in lock-in (ch1 as R [V|int], ch2 as Phase [rad]) **/
    { "dummy_trig_sw"                 ,      0, 1, 0,            0,          255 }, /** Select the external trigger signal **/
    { "dummy_out1_sw"                 ,      0, 1, 0,            0,           15 }, /** switch for muxer out1 **/
    { "dummy_out2_sw"                 ,      0, 1, 0,            0,           15 }, /** switch for muxer out2 **/
    { "dummy_slow_out1_sw"            ,      0, 1, 0,            0,           15 }, /** switch for muxer slow_out1 **/
    { "dummy_slow_out2_sw"            ,      0, 1, 0,            0,           15 }, /** switch for muxer slow_out2 **/
    { "dummy_slow_out3_sw"            ,      0, 1, 0,            0,           15 }, /** switch for muxer slow_out3 **/
    { "dummy_slow_out4_sw"            ,      0, 1, 0,            0,           15 }, /** switch for muxer slow_out4 **/
    { "dummy_in1"                     ,      0, 0, 1,        -8192,         8191 }, /** Input signal IN1 **/
    { "dummy_in2"                     ,      0, 0, 1,        -8192,         8191 }, /** Input signal IN2 **/
    { "dummy_out1"                    ,      0, 0, 1,        -8192,         8191 }, /** signal for RP RF DAC Out1 **/
    { "dummy_out2"                    ,      0, 0, 1,        -8192,         8191 }, /** signal for RP RF DAC Out2 **/
    { "dummy_slow_out1"               ,      0, 0, 1,            0,         4095 }, /** signal for RP slow DAC 1 **/
    { "dummy_slow_out2"               ,      0, 0, 1,            0,         4095 }, /** signal for RP slow DAC 2 **/
    { "dummy_slow_out3"               ,      0, 0, 1,            0,         4095 }, /** signal for RP slow DAC 3 **/
    { "dummy_slow_out4"               ,      0, 0, 1,            0,         4095 }, /** signal for RP slow DAC 4 **/
    { "dummy_oscA"                    ,      0, 0, 1,        -8192,         8191 }, /** signal for Oscilloscope Channel A **/
    { "dummy_oscB"                    ,      0, 0, 1,        -8192,         8191 }, /** signal for Oscilloscope Channel B **/
    { "dummy_read_ctrl"               ,      0, 1, 0,            0,            7 }, /** [unused,start_clk,Freeze] **/

    // [MAINDEF DOCK END]

    { /* Must be last! */
        NULL, 0.0, -1, -1, 0.0, 0.0 }
};
/* params initialized */
static int params_init = 0;

/* AUTO set algorithm in progress flag */
int auto_in_progress = 0;

rp_calib_params_t rp_main_calib_params;

int forcex_state = 0;
float forced_xmin = 0;
float forced_xmax = 0;
float forced_units = 0;
float forced_delay = 0;

/* When the last forceX was issued (from rp_lock-in_pid_h v2.3.14). A GUI range more than 33x away from the
 * forced one is taken as a POST still in the old time units and ignored, so a real zoom-out of more than 33x
 * right after a change of units was lost. POSTs built before the GUI got the forced range arrive within ~1.1 s;
 * after FORCEX_STALE_MS the GUI range is always taken. */
#define FORCEX_STALE_MS 1500
static struct timeval forcex_tv;

static void forcex_mark(void)
{
    gettimeofday(&forcex_tv, NULL);
}

static long forcex_age_ms(void)
{
    struct timeval now;
    gettimeofday(&now, NULL);
    return (now.tv_sec - forcex_tv.tv_sec) * 1000L + (now.tv_usec - forcex_tv.tv_usec) / 1000L;
}


const char *rp_app_desc(void)
{
    return (const char *)"Osciloscope+Dummy application.\n";
}

int rp_app_init(void)
{
    fprintf(stderr, "Loading scope (with dummy extensions) version %s-%s.\n", VERSION_STR, REVISION_STR);

    rp_default_calib_params(&rp_main_calib_params);
    if(rp_read_calib_params(&rp_main_calib_params) < 0) {
        fprintf(stderr, "rp_read_calib_params() failed, using default"
                " parameters\n");
    }

    TRACE("LOLO(rp_app_init): Now: rp_osc_worker_init\n");

    if(rp_osc_worker_init(&rp_main_params[0], PARAMS_NUM,
                          &rp_main_calib_params) < 0) {
        return -1;
    }

    TRACE("LOLO(rp_app_init): Now: generate_init\n");
    if(generate_init(&rp_main_calib_params) < 0) {
        return -1;
    }

    TRACE("LOLO(rp_app_init): Now: pid_init\n");
    if(pid_init() < 0) {
        return -1;
    }

    TRACE("LOLO(rp_app_init): Now: dummy_init\n");
    if(dummy_init() < 0) {
        return -1;
    }

    TRACE("LOLO(rp_app_init): PARAMS_NUM: %d \n", PARAMS_NUM);

    rp_set_params(&rp_main_params[0], PARAMS_NUM );

    TRACE("LOLO(rp_app_init): END\n");

    return 0;
}

/*----------------------------------------------------------------------------------*/
/* Streaming processes of this App (c/streaming, c/stream_tcp_osc_cmd), from rp_lock-in_pid_h v2.3.10. They read
 * the PL through /dev/mem: they must not run when Ecosystem 2.0 loads the FPGA of another App.
 * new_project.py writes the App name in APP_DIR. */
#define APP_DIR "/opt/redpitaya/www/apps/dummy"

/* Send sig to every c/streaming (from first = 0) and c/stream_tcp_osc_cmd of this App.
 * Returns how many were found alive (zombies are not counted). */
static int stream_procs_scan(int sig, unsigned first)
{
    static const char *tools[] = { "streaming", "stream_tcp_osc_cmd" };
    char names[2][128], path[64], exe[512];
    int  found = 0;
    unsigned i;
    DIR *d;
    struct dirent *e;
    for(i = 0; i < 2; i++)
        snprintf(names[i], sizeof(names[i]), "%s/c/%s", APP_DIR, tools[i]);
    d = opendir("/proc");
    if(!d)
        return 0;
    while((e = readdir(d)) != NULL) {
        char *end;
        long pid = strtol(e->d_name, &end, 10);
        ssize_t n;
        if(*end != '\0' || pid <= 1 || pid == (long)getpid())
            continue;
        snprintf(path, sizeof(path), "/proc/%ld/exe", pid);
        n = readlink(path, exe, sizeof(exe) - 1);   /* fails for zombies */
        if(n <= 0)
            continue;
        exe[n] = '\0';
        for(i = first; i < 2; i++) {
            size_t ln = strlen(names[i]);
            /* exact path (optionally followed by " (deleted)") */
            if(strncmp(exe, names[i], ln) == 0 && (exe[ln] == '\0' || exe[ln] == ' ')) {
                kill((pid_t)pid, sig);
                found++;
                break;
            }
        }
    }
    closedir(d);
    return found;
}

/* Used by the worker: after stream_cmd goes to 0 it waits for c/stream_tcp_osc_cmd to end before touching
 * the scope again */
int stream_tcp_alive(void)
{
    return stream_procs_scan(0, 1);
}

/* Stop the streaming before leaving the App */
static void stream_stop_all(void)
{
    int i, n;
    if(g_dummy_reg)
        *(volatile uint32_t *)&g_dummy_reg->stream_cmd = 0;   /* c/streaming stops its child too */

    n = stream_procs_scan(SIGTERM, 0);
    if(n == 0)
        return;
    fprintf(stderr, "rp_app_exit: stopping %d streaming process(es)\n", n);
    /* up to 0.5 s for a clean exit, then SIGKILL and up to 0.5 s more */
    for(i = 0; i < 50 && stream_procs_scan(0, 0) > 0; i++)
        usleep(10000);
    if(stream_procs_scan(SIGKILL, 0) > 0) {
        for(i = 0; i < 50 && stream_procs_scan(0, 0) > 0; i++)
            usleep(10000);
        n = stream_procs_scan(0, 0);
        if(n > 0)
            fprintf(stderr, "rp_app_exit: %d streaming process(es) still alive\n", n);
    }
}

int rp_app_exit(void)
{
    fprintf(stderr, "Unloading scope (with dummy extensions) version %s-%s.\n", VERSION_STR, REVISION_STR);

    TRACE("LOLO(rp_app_exit): Now: stream_stop_all\n");
    stream_stop_all();

    TRACE("LOLO(rp_app_exit): Now: rp_osc_worker_exit\n");
    rp_osc_worker_exit();

    TRACE("LOLO(rp_app_exit): Now: generate_exit\n");
    generate_exit();

    TRACE("LOLO(rp_app_exit): Now: pid_exit\n");
    pid_exit();

    TRACE("LOLO(rp_app_exit): Now: dummy_exit\n");
    dummy_exit();

    TRACE("LOLO(rp_app_exit): END\n");

    return 0;
}

int time_range_to_time_unit(int range)
{
    int unit = 2;

    switch (range) {
    case 0:
    case 1:
        unit = 0;
        break;
    case 2:
    case 3:
    case 4:
    case 5:
    case 6:
        /* 10 time ranges since the 2.0 scope (decimation 128/256/512/1k: ms) */
        unit = 1;
        break;
    default:
        unit = 2;
    }

    return unit;
}

/* Find a suitable FPGA decimation factor and trigger delay,
 * based on xmin & xmax zoom conntrols
 */
int transform_acq_params(rp_app_params_t *p)
{
    TRACE("%s()\n", __FUNCTION__);

    int ret = 0;
    int i;

    /* Skip the transform in case auto-set is in progress */
    if ( (p[AUTO_FLAG_PARAM].value == 1) || (auto_in_progress == 1)) {
        return ret;
    }

    double xmin = p[MIN_GUI_PARAM].value;
    double xmax = p[MAX_GUI_PARAM].value;

    float ratio;

    int reset_zoom = 0;

    int time_unit = p[TIME_UNIT_PARAM].value;
    float t_unit_factor = pow(10, 3*(2 - time_unit));

    /* When exactly this pair is provided by client, Reset Zoom is requested. */
    if ((xmax == 1.0e6) && (xmin == -1.0e6)) {
        reset_zoom = 1;
    }

    /* Server ForceX state */
    p[FORCEX_FLAG_PARAM].value = (float) forcex_state;

    /* Difference (expressed as ratio) between forced values and GUI state */
    if ((xmax - xmin) != 0) {
        ratio = fabs(forced_xmax - forced_xmin) / fabs(xmax - xmin);
    } else {
        ratio = 0.0;
    }

    /* Make it always between 0 and 1   (0: very different, 1 equal) */
    if (ratio > 1) {
        ratio = 1.0 / ratio;
    }

    /* Stop forcing if factor 33 of difference or less, or if the forceX is not recent: the GUI already has
     * the new units, the range is a real zoom */
    if ((ratio > 0.03) || (forcex_state && (forcex_age_ms() > FORCEX_STALE_MS))) {
        p[FORCEX_FLAG_PARAM].value  = 0;
        forcex_state = 0;
    }

    /* Contver GUI values to seconds */
    xmin /= t_unit_factor;
    xmax /= t_unit_factor;

    TRACE("TR: Xmin, Xmax: %10.8f, %10.8f\n", xmin, xmax);

    int time_unit_gui = time_unit;

    int dec;
    double rdec;

    /* Calculate the suitable FPGA decimation setting that optimally covers the GUI time frame */
    if (p[TRIG_MODE_PARAM].value == 0) {
        /* Autotriggering mode => acquisition starts at time t = 0 */
        rdec = (xmax - 0) * c_osc_fpga_smpl_freq / OSC_FPGA_SIG_LEN;
    } else {
        double rxmax = (xmax < 0) ? 0 : xmax;
        rdec = (rxmax - xmin) * c_osc_fpga_smpl_freq / OSC_FPGA_SIG_LEN;
    }

    /* Find optimal decimation setting */
    for (i = 0; i <= 9; i++) {
        dec = osc_fpga_cnv_time_range_to_dec(i);
        if (dec >= rdec) {
            break;
        }
    }
    if (i > 9)
        i = 9;

    /* Apply decimation parameter (time range), but not when forcing GUI client
     * or during reset zoom.
     */
    if ((forcex_state == 0) && (reset_zoom == 0)) {
        p[TIME_RANGE_PARAM].value = i;
    }

    TRACE("TR: Dcimation: %6.2f -> %dx\n", rdec, dec);

    /* New time_unit & factor */
    time_unit = time_range_to_time_unit(p[TIME_RANGE_PARAM].value);
    t_unit_factor = pow(10, 3*(2 - time_unit));

    /* Update time unit Min and Max, but not if GUI hasn't responded to "forceX" command. */
    if (forcex_state == 0) {
        p[MIN_GUI_PARAM].value = xmin * t_unit_factor;
        p[MAX_GUI_PARAM].value = xmax * t_unit_factor;
        p[GUI_XMIN].value = p[MIN_GUI_PARAM].value;
        p[GUI_XMAX].value = p[MAX_GUI_PARAM].value;
        p[TIME_UNIT_PARAM].value = time_unit;
    } else {
        p[MIN_GUI_PARAM].value = forced_xmin;
        p[MAX_GUI_PARAM].value = forced_xmax;
        p[GUI_XMIN].value = p[MIN_GUI_PARAM].value;
        p[GUI_XMAX].value = p[MAX_GUI_PARAM].value;
        p[TIME_UNIT_PARAM].value = forced_units;
    }

    /* If time units have changed by server: client MUST configure x axis
     * (ForceX is set for this purpose by server) to p[MIN_GUI_PARAM].value,
     * expressed in new units.
     */

    TRACE("TR: New xmin, xmax [unit]: %6.2f  %6.2f [%d]\n",
            p[MIN_GUI_PARAM].value,
            p[MAX_GUI_PARAM].value,
            (int)p[TIME_UNIT_PARAM].value);

    int64_t t_delay;

    /* Calculate necessary trigger delay expressed in FPGA decimated cycles */
    if (p[TRIG_MODE_PARAM].value == 0) {
        /* Autotriggering mode => acquisition starts at time t = 0 */
        t_delay= OSC_FPGA_SIG_LEN ;
    } else {
        t_delay= OSC_FPGA_SIG_LEN + (xmin * c_osc_fpga_smpl_freq / dec);
    }

    /* Trigger delay limitations/saturation */
    const int64_t c_max_t_delay = ((int64_t)1 << 32) - 1;
    if (t_delay < 0)
        t_delay = 0;
    if (t_delay > c_max_t_delay)
        t_delay = c_max_t_delay;

    /* Trigger delay (reconverted in seconds) updated ONLY if client has responded to
     * last forceX command.
     */
    if (forcex_state == 0) {
        p[TRIG_DLY_PARAM].value = ((t_delay - OSC_FPGA_SIG_LEN) * dec / c_osc_fpga_smpl_freq);
    } else {
        p[TRIG_DLY_PARAM].value = forced_delay;
    }

    /* Server issues a forceX command when time units change wrt. GUI (client) units */
    if ((time_unit != time_unit_gui)) {
        p[FORCEX_FLAG_PARAM].value = 1.0;
        forcex_state = 1;
        forcex_mark();

        /* Other settings frozen until GUI recovers */
        forced_xmin = p[MIN_GUI_PARAM].value;
        forced_xmax = p[MAX_GUI_PARAM].value;
        forced_units = p[TIME_UNIT_PARAM].value;
        forced_delay = p[TRIG_DLY_PARAM].value;
    }

    /* When client issues a zoom reset, a particular ForceX command with
     * the initial 0 - 130 us time range.
     */
    if (reset_zoom == 1) {
        p[FORCEX_FLAG_PARAM].value  = 1.0;
        forcex_state = 1;
        forcex_mark();

        forced_xmin = 0.0;
        forced_xmax = 130.0;
        forced_units = 0.0;
        forced_delay = 0;

        p[MIN_GUI_PARAM].value = forced_xmin;
        p[MAX_GUI_PARAM].value = forced_xmax;
        p[GUI_XMIN].value = p[MIN_GUI_PARAM].value;
        p[GUI_XMAX].value = p[MAX_GUI_PARAM].value;
        p[TIME_UNIT_PARAM].value = forced_units;
        p[TRIG_DLY_PARAM].value = forced_delay;
        p[TIME_RANGE_PARAM].value = 0;
    }

    TRACE("TR: Trigger delay: %.6f\n", p[TRIG_DLY_PARAM].value);

    return ret;
}

void get_scales(rp_app_params_t *p, float *scale1, float *scale2, float *maxv) {

    /* Max ADC for Ch1, Ch2, both combined, normalized & selected */
    uint32_t fe_fsg1 = (p[GAIN_CH1].value == 0) ?
            rp_main_calib_params.fe_ch1_fs_g_hi :
            rp_main_calib_params.fe_ch1_fs_g_lo;
    float ch1_max_adc_v =
            osc_fpga_calc_adc_max_v(fe_fsg1, p[PRB_ATT_CH1].value);

    uint32_t fe_fsg2 = (p[GAIN_CH2].value == 0) ?
            rp_main_calib_params.fe_ch2_fs_g_hi :
            rp_main_calib_params.fe_ch2_fs_g_lo;
    float ch2_max_adc_v =
            osc_fpga_calc_adc_max_v(fe_fsg2, p[PRB_ATT_CH2].value);

    float max_adc_norm = osc_fpga_calc_adc_max_v(rp_main_calib_params.fe_ch1_fs_g_hi, 0);

    *scale1 = ch1_max_adc_v / max_adc_norm;
    *scale2 = ch2_max_adc_v / max_adc_norm;
    *maxv = (ch1_max_adc_v > ch2_max_adc_v) ?
             ch1_max_adc_v : ch2_max_adc_v;
}

void transform_to_iface_units(rp_app_params_t *p)
{
    float scale, scale1, scale2, maxv;
    get_scales(p, &scale1, &scale2, &maxv);
    scale = (scale1 > scale2) ? scale1 : scale2;

    /* Re-calculate output parameters */
    p[GUI_RST_Y_RANGE].value = 2.0 * maxv;

    p[MIN_Y_PARAM].value = p[MIN_Y_NORM].value * scale;
    p[MAX_Y_PARAM].value = p[MAX_Y_NORM].value * scale;

    p[GEN_DC_OFFS_1].value = p[GEN_DC_NORM_1].value * scale1;
    p[GEN_DC_OFFS_2].value = p[GEN_DC_NORM_2].value * scale2;

    p[SCALE_CH1].value = scale1;
    p[SCALE_CH2].value = scale2;
}

void transform_from_iface_units(rp_app_params_t *p)
{
    float scale1, scale2, maxv;
    get_scales(p, &scale1, &scale2, &maxv);

    /* Re-calculate input parameters */
    p[GEN_DC_NORM_1].value = p[GEN_DC_OFFS_1].value / scale1;
    p[GEN_DC_NORM_2].value = p[GEN_DC_OFFS_2].value / scale2;
}

int rp_set_params(rp_app_params_t *p, int len)
{
    int i;
    int fpga_update = 1;
    int params_change = 0;
    int awg_params_change = 0;
    int pid_params_change = 0;
    int dummy_params_change = 0;
    int got_xmin = 0, got_xmax = 0;


    TRACE("%s()\n", __FUNCTION__);

    TRACE("LOLO(rp_set_params): START\n");

    if(len > PARAMS_NUM) {
        fprintf(stderr, "Too many parameters, max=%d\n", PARAMS_NUM);
        return -1;
    }

    pthread_mutex_lock(&rp_main_params_mutex);
    for(i = 0; i < len || p[i].name != NULL; i++) {
        int p_idx = -1;
        int j = 0;
        /* Search for correct parameter name in defined parameters */
        while(rp_main_params[j].name != NULL) {
            int p_strlen = strlen(p[i].name);

            if(p_strlen != strlen(rp_main_params[j].name)) {
                j++;
                continue;
            }
            if(!strncmp(p[i].name, rp_main_params[j].name, p_strlen)) {
                p_idx = j;
                break;
            }
            j++;
        }

        if(p_idx == -1) {
            fprintf(stderr, "Parameter %s not found, ignoring it\n", p[i].name);
            continue;
        }

        if(rp_main_params[p_idx].read_only)
            continue;

        if(p_idx == MIN_GUI_PARAM) got_xmin = 1;
        if(p_idx == MAX_GUI_PARAM) got_xmax = 1;

        /* xmin/xmax are compared with the last GUI values (GUI_XMIN/GUI_XMAX, GUI units): after a change
         * MIN/MAX_GUI_PARAM hold the worker window in seconds, so the xmin/xmax that the page sends in every
         * POST always looked changed, and every POST (any parameter, e.g. a dummy control) re-armed the scope:
         * a Normal/Single acquisition waiting for its trigger was disarmed (from rp_lock-in_pid_h v2.3.14) */
        float cmp_val = rp_main_params[p_idx].value;
        if(params_init && (p_idx == MIN_GUI_PARAM))
            cmp_val = rp_main_params[GUI_XMIN].value;
        if(params_init && (p_idx == MAX_GUI_PARAM))
            cmp_val = rp_main_params[GUI_XMAX].value;

        if(cmp_val != p[i].value) {
            if(p_idx < PARAMS_AWG_PARAMS)
                params_change = 1;
            /* dummy params that the scope worker uses (inputs of the channels, raw / R-phase display) */
            if((p_idx == DUMMY_OSCA_SW) || (p_idx == DUMMY_OSCB_SW) ||
               (p_idx == DUMMY_OSC_RAW_MODE) || (p_idx == DUMMY_OSC_LOCKIN_MODE))
                params_change = 1;
            if ( (p_idx >= PARAMS_AWG_PARAMS) && (p_idx < PARAMS_PID_PARAMS) )
                awg_params_change = 1;
            if ( (p_idx >= PARAMS_PID_PARAMS) && (p_idx < PARAMS_DUMMY_PARAMS ) )
                pid_params_change = 1;
            if(p_idx >= PARAMS_DUMMY_PARAMS)
                dummy_params_change = 1;
            if(rp_main_params[p_idx].fpga_update)
                fpga_update = 1;
        }
        if(rp_main_params[p_idx].min_val > p[i].value) {
            fprintf(stderr, "Incorrect parameters value: %f (min:%f), "
                    " correcting it\n", p[i].value, rp_main_params[p_idx].min_val);
            p[i].value = rp_main_params[p_idx].min_val;
        } else if(rp_main_params[p_idx].max_val < p[i].value) {
            fprintf(stderr, "Incorrect parameters value: %f (max:%f), "
                    " correcting it\n", p[i].value, rp_main_params[p_idx].max_val);
            p[i].value = rp_main_params[p_idx].max_val;
        }
        rp_main_params[p_idx].value = p[i].value;
    }
    transform_from_iface_units(&rp_main_params[0]);
    pthread_mutex_unlock(&rp_main_params_mutex);


    /* Set parameters in HW/FPGA only if they have changed */
    if(params_change || (params_init == 0)) {

        pthread_mutex_lock(&rp_main_params_mutex);
        /* Xmin & Xmax public copy to be served to clients */
        /* p may be a partial list (split POSTs): use the values already copied by name in the loop above.
         * xmin/xmax not in this POST: the MIN/MAX_GUI_PARAM slots hold the worker window in seconds (see
         * "write back" below), not GUI units: use the last GUI values (GUI_XMIN/GUI_XMAX) instead */
        if(!got_xmin)
            rp_main_params[MIN_GUI_PARAM].value = rp_main_params[GUI_XMIN].value;
        if(!got_xmax)
            rp_main_params[MAX_GUI_PARAM].value = rp_main_params[GUI_XMAX].value;
        rp_main_params[GUI_XMIN].value = rp_main_params[MIN_GUI_PARAM].value;
        rp_main_params[GUI_XMAX].value = rp_main_params[MAX_GUI_PARAM].value;
        transform_acq_params(rp_main_params);
        pthread_mutex_unlock(&rp_main_params_mutex);

        /* First do health check and then send it to the worker! */
        int mode = rp_main_params[TRIG_MODE_PARAM].value;
        int time_range = rp_main_params[TIME_RANGE_PARAM].value;
        int time_unit = 2;
        /* Get info from FPGA module about clocks/decimation, ...*/
        int dec_factor = osc_fpga_cnv_time_range_to_dec(time_range);
        float smpl_period = c_osc_fpga_smpl_period * dec_factor;
        /* t_delay - trigger delay in seconds */
        float t_delay = rp_main_params[TRIG_DLY_PARAM].value;
        float t_unit_factor = 1; /* to convert to seconds */

        /* Our time window with current settings:
         *   - time_delay is added later, when we check if it is correct
         *     setting
         */
        float t_min = 0;
        float t_max = ((OSC_FPGA_SIG_LEN-1) * smpl_period);
        float t_max_minus = ((OSC_FPGA_SIG_LEN-6) * smpl_period);

        params_init = 1;
        /* in time units time_unit, needs to be converted */
        float t_start = rp_main_params[MIN_GUI_PARAM].value;
        float t_stop  = rp_main_params[MAX_GUI_PARAM].value;
        int t_start_idx;
        int t_stop_idx;
        int t_step_idx = 0;

        /* If auto-set algorithm was requested do not set other parameters */
        if(rp_main_params[AUTO_FLAG_PARAM].value == 1) {
            auto_in_progress = 1;
            forcex_state = 0;

            rp_osc_clean_signals();
            rp_osc_worker_change_state(rp_osc_auto_set_state);
            /* AUTO_FLAG_PARAM is cleared when Auto-set algorithm finishes */

            /* Wait for auto-set algorithm to finish or timeout (the auto-set itself gives up after its own
             * time limits, ~10 s in the worst case: decimation 8k, forced acquisitions) */
            int timeout = 15000000; // [us]
            const int step = 50000; // [us]
            rp_osc_worker_state_t state;
            while (timeout > 0) {

                rp_osc_worker_get_state(&state);
                if (state != rp_osc_auto_set_state) {
                    break;
                }

                usleep(step);
                timeout -= step;
            }

            if (timeout <= 0) {
                fprintf(stderr, "AUTO: Timeout waiting for AUTO-set algorithm to finish.\n");
                /* do not leave auto_flag = 1: every later POST would start the auto-set again */
                rp_auto_set_aborted();
            }

            auto_in_progress = 0;

            return 0;
        }

        /* If AUTO trigger mode, reset trigger delay */
        if(mode == 0)
            t_delay = 0;

        if(dec_factor < 0) {
            fprintf(stderr, "Incorrect time range: %d\n", time_range);
            return -1;
        }

        /* Pick time unit and unit factor corresponding to current time range. */
        if((time_range == 0) || (time_range == 1)) {
            time_unit     = 0;
            t_unit_factor = 1e6;
        } else if((time_range == 2) || (time_range == 3) || (time_range == 4) || (time_range == 5) || (time_range == 6)) {
            time_unit     = 1;
            t_unit_factor = 1e3;
        }

        rp_main_params[TIME_UNIT_PARAM].value = time_unit;
        TRACE("PC: time_(R,U) = (%d, %d)\n", time_range, time_unit);

        /* Check if trigger delay in correct range, otherwise correct it
         * Correct trigger delay is:
         *  t_delay >= -t_max_minus
         *  t_delay <= OSC_FPGA_MAX_TRIG_DELAY
         */
        if(t_delay < -t_max_minus) {
            t_delay = -t_max_minus;
        } else if(t_delay > (OSC_FPGA_TRIG_DLY_MASK * smpl_period)) {
            t_delay = OSC_FPGA_TRIG_DLY_MASK * smpl_period;
        } else {
            t_delay = round(t_delay / smpl_period) * smpl_period;
        }
        t_min = t_min + t_delay;
        t_max = t_max + t_delay;
        rp_main_params[TRIG_DLY_PARAM].value = t_delay;

        /* Convert to seconds */
        t_start = t_start / t_unit_factor;
        t_stop  = t_stop  / t_unit_factor;
        TRACE("PC: t_stop = %.9f\n", t_stop);

        /* Select correct time window with this settings:
         * time window is defined from:
         *  ([ 0 - 16k ] * smpl_period) + trig_delay */
        /* round to correct/possible values - convert to nearest index
         * and back
         */
        t_start_idx = round(t_start / smpl_period);
        t_stop_idx  = round(t_stop / smpl_period);

        t_start = (t_start_idx * smpl_period);
        t_stop  = (t_stop_idx * smpl_period);

        if(t_start < t_min)
            t_start = t_min;
        if(t_stop > t_max)
            t_stop = t_max;
        if(t_stop <= t_start )
            t_stop = t_max;

        /* Correct the window according to possible decimations - always
         * provide at least the data demanded by the user (ceil() instead
         * of round())
         */
        t_start_idx = round(t_start / smpl_period);
        t_stop_idx  = round(t_stop / smpl_period);

        if((((t_stop_idx-t_start_idx)/(float)(SIGNAL_LENGTH-1))) >= 1) {
            t_step_idx = ceil((t_stop_idx-t_start_idx)/(float)(SIGNAL_LENGTH-1));
            int max_step = OSC_FPGA_SIG_LEN/SIGNAL_LENGTH;
            if(t_step_idx > max_step)
                t_step_idx = max_step;

            t_stop = t_start + SIGNAL_LENGTH * t_step_idx * smpl_period;
        }


        /* write back and convert to set units */
        rp_main_params[MIN_GUI_PARAM].value = t_start;
        rp_main_params[MAX_GUI_PARAM].value = t_stop;


        rp_osc_worker_update_params((rp_app_params_t *)&rp_main_params[0],
                                    fpga_update);

        /* check if we need to change state */
        switch(mode) {
        case 0:
            /* auto */
            rp_osc_worker_change_state(rp_osc_auto_state);
            break;
        case 1:
            /* normal */
            rp_osc_worker_change_state(rp_osc_normal_state);
            break;
        case 2:
            /* single - clear last ok buffer */
            rp_osc_worker_change_state(rp_osc_idle_state);
            rp_osc_clean_signals();
            break;
        default:
            return -1;
        }


        if(rp_main_params[SINGLE_BUT_PARAM].value == 1) {
            rp_main_params[SINGLE_BUT_PARAM].value = 0;
            rp_osc_clean_signals();
            rp_osc_worker_change_state(rp_osc_single_state);
        }
    }

    if(awg_params_change) {

        /* Correct frequencies if needed */
        rp_main_params[GEN_SIG_FREQ_CH1].value =
            rp_gen_limit_freq(rp_main_params[GEN_SIG_FREQ_CH1].value,
                              rp_main_params[GEN_SIG_TYPE_CH1].value);
        rp_main_params[GEN_SIG_FREQ_CH2].value =
            rp_gen_limit_freq(rp_main_params[GEN_SIG_FREQ_CH2].value,
                              rp_main_params[GEN_SIG_TYPE_CH2].value);
        if(generate_update(&rp_main_params[0]) < 0) {
            return -1;
        }
    }

    if (pid_params_change) {
        if(pid_update(&rp_main_params[0]) < 0) {
            return -1;
        }
    }

    if (dummy_params_change) {
        if(dummy_update(&rp_main_params[0]) < 0) {
            return -1;
        }
    }

    return 0;
}

/* Returned vector must be free'd externally! */
int rp_get_params(rp_app_params_t **p)
{
    rp_app_params_t *p_copy = NULL;
    int i;

    TRACE("LOLO(rp_get_params): START\n");

    p_copy = (rp_app_params_t *)malloc((PARAMS_NUM+1) * sizeof(rp_app_params_t));
    if(p_copy == NULL)
        return -1;

    pthread_mutex_lock(&rp_main_params_mutex);
    /* Registers of the dummy module (monitors, and values written from outside, e.g. by ssh) read on every
     * request, not only when a complete capture arrives: with Normal waiting for its trigger or a long
     * window the page kept showing old values */
    dummy_update_main(&rp_main_params[0]);
    for(i = 0; i < PARAMS_NUM; i++) {
        int p_strlen = strlen(rp_main_params[i].name);
        p_copy[i].name = (char *)malloc(p_strlen+1);
        strncpy((char *)&p_copy[i].name[0], &rp_main_params[i].name[0],
                p_strlen);
        p_copy[i].name[p_strlen]='\0';

        p_copy[i].value       = rp_main_params[i].value;
        p_copy[i].fpga_update = rp_main_params[i].fpga_update;
        p_copy[i].read_only   = rp_main_params[i].read_only;
        p_copy[i].min_val     = rp_main_params[i].min_val;
        p_copy[i].max_val     = rp_main_params[i].max_val;
    }
    pthread_mutex_unlock(&rp_main_params_mutex);
    p_copy[PARAMS_NUM].name = NULL;

    /* Return the original public Xmin & Xmax to client (not the internally modified ones). */
    p_copy[MIN_GUI_PARAM].value = p_copy[GUI_XMIN].value;
    p_copy[MAX_GUI_PARAM].value = p_copy[GUI_XMAX].value;

    transform_to_iface_units(p_copy);

    *p = p_copy;
    return PARAMS_NUM;
}

int rp_get_signals(float ***s, int *sig_num, int *sig_len)
{

    TRACE("LOLO(rp_get_signals): START\n");

    int ret_val;
    int sig_idx;

    if(*s == NULL)
        return -1;

    *sig_num = SIGNALS_NUM;
    *sig_len = SIGNAL_LENGTH;

    ret_val = rp_osc_get_signals(s, &sig_idx);

    TRACE("LOLO(rp_get_signals): ret_val: %d \n", ret_val);

    /* Not finished signal */
    if((ret_val != -1) && sig_idx != SIGNAL_LENGTH-1) {
        return -2;
    }
    /* Old signal */
    if(ret_val < 0) {
        return -1;
    }


    //TRACE("LOLO(rp_get_signals): g_dummy_reg->read_ctrl: %d \n", (int)g_dummy_reg->read_ctrl ) ;
    //dummy_freeze_regs();

    /* The registers of the dummy module are read in rp_get_params() (every request, under the mutex) */

    //dummy_restore_regs();

    return 0;
}

int rp_create_signals(float ***a_signals)
{
    int i;
    float **s;

    TRACE("LOLO(rp_create_signals): START\n");

    s = (float **)malloc(SIGNALS_NUM * sizeof(float *));
    if(s == NULL) {
        return -1;
    }
    for(i = 0; i < SIGNALS_NUM; i++)
        s[i] = NULL;

    for(i = 0; i < SIGNALS_NUM; i++) {
        s[i] = (float *)malloc(SIGNAL_LENGTH * sizeof(float));
        if(s[i] == NULL) {
            rp_cleanup_signals(a_signals);
            return -1;
        }
        memset(&s[i][0], 0, SIGNAL_LENGTH * sizeof(float));
    }
    *a_signals = s;

    return 0;
}

void rp_cleanup_signals(float ***a_signals)
{
    int i;
    float **s = *a_signals;

    if(s) {
        for(i = 0; i < SIGNALS_NUM; i++) {
            if(s[i]) {
                free(s[i]);
                s[i] = NULL;
            }
        }
        free(s);
        *a_signals = NULL;
    }
}

/*----------------------------------------------------------------------------------*/
/**
 * @brief Make a copy of Application parameters
 *
 * Function copies actual Application parameters to the specified destination
 * buffer. This action was intended to prepare two parameter instances, where the first
 * one can be further modified from the user side, while the second one is processed by
 * the worker thread.
 * In case the destination buffer is not allocated yet, it is allocated internally and must
 * be freed outside of the function scope by calling rp_clean_params() function. Note that
 * if function returns failure, the destination buffer could be partially allocated and must
 * be freed in the same way.
 * If the specified destination buffer is already allocated, it is assumed the number of table
 * entries is the same as in the source table. No special check is made internally if this is really
 * the case.
 *
 * @param[in]   src  Source application parameters
 * @param[out]  dst  Destination application parameters
 * @retval      -1   Failure, error message is output on standard error
 * @retval      0    Successful operation
 */
int rp_copy_params(rp_app_params_t *src, rp_app_params_t **dst)
{
    rp_app_params_t *p_new = *dst;
    int i, num_params;

    TRACE("LOLO(rp_copy_params): START\n");

    /* check arguments */
    if (src == NULL) {
        fprintf(stderr, "Internal error, the source Application parameters are not specified.\n");
        return -1;
    }

    /* check if destination buffer is allocated or not */
    if(p_new == NULL) {
        i = 0;

        /* retrieve the number of source parameters */
        num_params=0;
        while(src[i++].name != NULL)
            num_params++;

        /* allocate array of parameter entries, parameter names must be allocated separately */
        p_new = (rp_app_params_t *)malloc(sizeof(rp_app_params_t) * (num_params+1));
        if(p_new == NULL) {
            fprintf(stderr, "Memory problem, the destination buffer could not be allocated.\n");
            return -1;
        }

        /* scan source parameters, allocate memory space for parameter names and copy values */
        i = 0;
        while(src[i].name != NULL) {
            p_new[i].name = (char *)malloc(strlen(src[i].name)+1);
            if(p_new[i].name == NULL)
                return -1;

            strncpy(p_new[i].name, src[i].name, strlen(src[i].name));
            p_new[i].name[strlen(src[i].name)]='\0';
            p_new[i].value = src[i].value;
            i++;
        }

        /* mark last one */
        p_new[num_params].name = NULL;
        p_new[num_params].value = -1;

    } else {
        /* destination buffer is already allocated, just copy values */
        i = 0;
        while(src[i].name != NULL) {
            p_new[i].value = src[i].value;
            i++;
        }

    }

    *dst = p_new;
    return 0;
}


/*----------------------------------------------------------------------------------*/
/**
 * @brief Deallocate the specified buffer of Application parameters
 *
 * Function is used to deallocate the specified buffers, which were previously
 * allocated by calling rp_copy_params() function.
 *
 * @param[in]   params  Application parameters to be deallocated
 * @retval      0       Success, never fails
 */
int rp_clean_params(rp_app_params_t *params)
{
    int i = 0;
    TRACE("LOLO(rp_clean_params): START\n");

    /* cleanup params structure */
    if(params) {
        while(params[i].name != NULL) {
            if(params[i].name)
                free(params[i].name);
            params[i].name = NULL;
            i++;
        }
        free(params);
        params = NULL;
    }
    return 0;
}

/* Scope parameters computed by the auto-set (from rp_lock-in_pid_h v2.3.14) */
static const int auto_set_params[] = {
    MIN_GUI_PARAM, MAX_GUI_PARAM, TRIG_MODE_PARAM, TRIG_SRC_PARAM, TRIG_DLY_PARAM, TRIG_LEVEL_PARAM,
    TIME_RANGE_PARAM, TIME_UNIT_PARAM, AUTO_FLAG_PARAM, MIN_Y_PARAM, MAX_Y_PARAM, GUI_RST_Y_RANGE,
    MIN_Y_NORM, MAX_Y_NORM
};

/* Called by the worker when the auto-set has finished: only the scope parameters it found go to the main
 * parameters (before, the whole worker copy, which could be stale), which are then applied */
int rp_update_main_params(rp_app_params_t *params)
{
    TRACE("LOLO(rp_update_main_params): START\n");
    unsigned i;
    if(params == NULL)
        return -1;

    pthread_mutex_lock(&rp_main_params_mutex);
    for(i = 0; i < sizeof(auto_set_params) / sizeof(auto_set_params[0]); i++)
        rp_main_params[auto_set_params[i]].value = params[auto_set_params[i]].value;
    rp_main_params[AUTO_FLAG_PARAM].value = 0;   /* never start another auto-set from the worker thread */
    pthread_mutex_unlock(&rp_main_params_mutex);
    params_init = 0;
    rp_set_params(&rp_main_params[0], PARAMS_NUM);

    return 0;
}

/* The auto-set was aborted by a change of the worker state (another POST, quit): nothing is copied back,
 * only auto_flag is cleared, so that the next POST does not start an AUTO the user did not ask for */
void rp_auto_set_aborted(void)
{
    pthread_mutex_lock(&rp_main_params_mutex);
    rp_main_params[AUTO_FLAG_PARAM].value = 0;
    pthread_mutex_unlock(&rp_main_params_mutex);
}

/* The auto-set failed (no acquisition / trigger in time): auto_flag cleared and the current parameters
 * applied again (the worker goes back to the trigger mode of the page). Called from the worker thread:
 * auto_flag is 0, so rp_set_params() does not wait for the worker. */
void rp_auto_set_failed(void)
{
    rp_auto_set_aborted();
    params_init = 0;
    rp_set_params(&rp_main_params[0], PARAMS_NUM);
}

int rp_update_meas_data(rp_osc_meas_res_t ch1_meas, rp_osc_meas_res_t ch2_meas)
{
    pthread_mutex_lock(&rp_main_params_mutex);
    rp_main_params[MEAS_MIN_CH1].value = ch1_meas.min;
    rp_main_params[MEAS_MAX_CH1].value = ch1_meas.max;
    rp_main_params[MEAS_AMP_CH1].value = ch1_meas.amp;
    rp_main_params[MEAS_AVG_CH1].value = ch1_meas.avg;
    rp_main_params[MEAS_FREQ_CH1].value = ch1_meas.freq;
    rp_main_params[MEAS_PER_CH1].value = ch1_meas.period;

    rp_main_params[MEAS_MIN_CH2].value = ch2_meas.min;
    rp_main_params[MEAS_MAX_CH2].value = ch2_meas.max;
    rp_main_params[MEAS_AMP_CH2].value = ch2_meas.amp;
    rp_main_params[MEAS_AVG_CH2].value = ch2_meas.avg;
    rp_main_params[MEAS_FREQ_CH2].value = ch2_meas.freq;
    rp_main_params[MEAS_PER_CH2].value = ch2_meas.period;

    pthread_mutex_unlock(&rp_main_params_mutex);
    return 0;
}

float rp_gen_limit_freq(float freq, float gen_type)
{
    int type = (int)gen_type;

    if(freq < 0) {
        freq = 0;
    } else {
        switch(type) {
        case 0:
            /* Sine */
            if(freq > 50e6)
                freq = 50e6;
            break;
        case 1:
            /* Square */
            if(freq > 20e6)
                freq = 20e6;
            break;
        case 2:
            /* Triangle */
            if(freq > 25e6)
                freq = 25e6;
            break;
        }
    }

    return freq;
}
