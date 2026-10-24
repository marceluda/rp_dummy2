/*
 * Host-side regression harness for the AUTO (auto-set) of the dummy template (dummy/src/worker.c).
 * worker.c is compiled for the host and linked with a mock of the scope (osc_fpga_*) and stubs of main.c.
 *   make -C tests        (host gcc; builds and runs it against ../dummy/src/worker.c)
 * The mock scope returns 16-bit sign-extended samples (2.0 FPGA). The level trigger fires only if the
 * level is strictly inside the signal range (or never, in the "no level trigger" tests).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <pthread.h>
#include <unistd.h>
#include <sys/time.h>
#include "main.h"
#include "worker.h"
#include "fpga.h"
#include "calib.h"

/* ---- mock scope ---- */
const int   c_osc_fpga_adc_bits   = 14;
const float c_osc_fpga_smpl_freq  = 125e6;
const float c_osc_fpga_smpl_period = 8e-12;   /* 1000x shorter than real: short time limits in the test */
static int  m_cha[OSC_FPGA_SIG_LEN], m_chb[OSC_FPGA_SIG_LEN];
static int  m_src = 0, m_trig_imm = 0, m_trig_ch = 0;
static float m_level_v = 0;
static int  m_level_never = 0;               /* 1: the level trigger never fires */
static int  m_dead = 0;                      /* 1: no trigger at all (not even immediate) */
static int  m_min[2], m_max[2];

int osc_fpga_init(void) { return 0; }
int osc_fpga_exit(void) { return 0; }
int osc_fpga_reset(void) { m_src = 0; return 0; }
int osc_fpga_arm_trigger(void) { return 0; }
int osc_fpga_set_trigger(uint32_t trig_source) { m_src = trig_source; return 0; }
int osc_fpga_get_wr_ptr(int *wr_ptr_curr, int *wr_ptr_trig) { if(wr_ptr_curr) *wr_ptr_curr = 0; if(wr_ptr_trig) *wr_ptr_trig = 0; return 0; }
int osc_fpga_get_sig_ptr(int **cha_signal, int **chb_signal) { *cha_signal = m_cha; *chb_signal = m_chb; return 0; }
float osc_fpga_calc_adc_max_v(uint32_t fe_gain_fs, int probe_att) { return 1.0; }
int osc_fpga_cnv_trig_source(int trig_imm, int trig_source, int trig_edge)
{
    if(trig_imm) return 1;
    if(trig_source == 0) return trig_edge ? 3 : 2;
    if(trig_source == 1) return trig_edge ? 5 : 4;
    return trig_edge ? 7 : 6;
}
int osc_fpga_cnv_time_range_to_dec(int time_range)
{
    static const int d[10] = { 1, 8, 64, 128, 256, 512, 1024, 8192, 65536, 524288 };
    return (time_range >= 0 && time_range < 10) ? d[time_range] : -1;
}
float osc_fpga_cnv_cnt_to_v(int cnts, float adc_max_v, int calib_dc_off, float user_dc_off)
{
    int m = cnts & 0x3FFF;
    if(m & 0x2000) m = -((m ^ 0x3FFF) + 1);
    return m * adc_max_v / 8192.0;
}
int osc_fpga_update_params(int trig_imm, int trig_source, int trig_edge, float trig_delay, float trig_level,
                           int time_range, float ch1_adc_max_v, float ch2_adc_max_v, int ch1_calib_dc_off,
                           float ch1_user_dc_off, int ch2_calib_dc_off, float ch2_user_dc_off, int ch1_probe_att,
                           int ch2_probe_att, int ch1_gain, int ch2_gain, int enable_avg_at_dec)
{
    m_trig_imm = trig_imm; m_trig_ch = trig_source; m_level_v = trig_level;
    return 0;
}
int osc_fpga_triggered(void)
{
    int lvl, ch;
    if(m_src == 0 || m_dead) return 0;
    if(m_src == 1) return 1;                       /* immediate */
    if(m_level_never) return 0;
    ch  = (m_src <= 3) ? 0 : 1;
    lvl = (int)lround(m_level_v * 8192.0);
    return (lvl > m_min[ch]) && (lvl < m_max[ch]);  /* the signal crosses the level */
}

/* ---- dummy module (no streaming in these tests) ---- */
#include "fpga_dummy.h"
dummy_reg_t *g_dummy_reg = NULL;
int stream_tcp_alive(void) { return 0; }

/* ---- stubs of main.c ---- */
static int n_update = 0, n_aborted = 0, n_failed = 0;
static rp_app_params_t last_params[PARAMS_NUM+1];
int rp_update_main_params(rp_app_params_t *params) { n_update++; memcpy(last_params, params, sizeof(last_params)); return 0; }
void rp_auto_set_aborted(void) { n_aborted++; }
void rp_auto_set_failed(void) { n_failed++; }
int rp_update_meas_data(rp_osc_meas_res_t a, rp_osc_meas_res_t b) { return 0; }
void transform_to_iface_units(rp_app_params_t *p) { }
int rp_copy_params(rp_app_params_t *src, rp_app_params_t **dst) { return 0; }
int rp_clean_params(rp_app_params_t *params) { return 0; }
int rp_create_signals(float ***a_signals) { return 0; }
void rp_cleanup_signals(float ***a_signals) { }

extern rp_calib_params_t *rp_calib_params;
extern rp_app_params_t   *rp_osc_params;
extern int *rp_fpga_cha_signal, *rp_fpga_chb_signal;
int rp_osc_adc_sign(int in_data);

static double now_s(void) { struct timeval t; gettimeofday(&t, NULL); return t.tv_sec + t.tv_usec * 1e-6; }

static void set_signal(int ch, int kind, int amp, int period)
{
    int i, v, *b = ch ? m_chb : m_cha;
    m_min[ch] = 100000; m_max[ch] = -100000;
    for(i = 0; i < OSC_FPGA_SIG_LEN; i++) {
        if(kind == 0)      v = amp;                                                    /* DC */
        else if(kind == 1) v = -amp + (int)((2.0 * amp) * (i % period) / period);      /* sawtooth */
        else               v = ((i % period) < period / 2) ? -amp : amp;              /* square */
        if(v < m_min[ch]) m_min[ch] = v;
        if(v > m_max[ch]) m_max[ch] = v;
        b[i] = v & 0xFFFF;                     /* 2.0 FPGA: 16-bit sign-extended sample */
    }
}

static rp_app_params_t P[PARAMS_NUM+1];
static int fails = 0;
#define CHECK(c, ...) do { if(c) printf("  PASS: "); else { printf("  FAIL: "); fails++; } printf(__VA_ARGS__); printf("\n"); } while(0)

static int run_auto(double *dt)
{
    int r; double t0;
    memset(P, 0, sizeof(P));
    rp_osc_worker_change_state(rp_osc_auto_set_state);
    t0 = now_s();
    r = rp_osc_auto_set(P, 1.0, 1.0, 0, 0, 0, 0, 0, 0, 0);
    *dt = now_s() - t0;
    return r;
}

static void *quit_later(void *arg) { usleep(50000); rp_osc_worker_change_state(rp_osc_quit_state); return NULL; }

int main(void)
{
    static rp_calib_params_t calib;
    static rp_app_params_t osc_params[PARAMS_NUM+1];
    double dt; int r;
    setvbuf(stdout, NULL, _IONBF, 0);
    memset(&calib, 0, sizeof(calib));
    rp_calib_params   = &calib;
    rp_osc_params     = osc_params;
    rp_fpga_cha_signal = m_cha; rp_fpga_chb_signal = m_chb;

    printf("T1 sample decoding (rp_osc_adc_sign)\n");
    CHECK(rp_osc_adc_sign(0xFF9C) == -100,  "0xFF9C (2.0, -100) -> %d", rp_osc_adc_sign(0xFF9C));
    CHECK(rp_osc_adc_sign(0x3F9C) == -100,  "0x3F9C (0.9x, -100) -> %d", rp_osc_adc_sign(0x3F9C));
    CHECK(rp_osc_adc_sign(0xE000) == -8192, "0xE000 (2.0, -8192) -> %d", rp_osc_adc_sign(0xE000));
    CHECK(rp_osc_adc_sign(0x1FFF) == 8191,  "0x1FFF (8191) -> %d", rp_osc_adc_sign(0x1FFF));

    printf("T2 AUTO on a sawtooth +-8000 (CH1), CH2 at 0\n");
    m_level_never = 0; set_signal(0, 1, 8000, 1000); set_signal(1, 0, 0, 1);
    r = run_auto(&dt);
    CHECK(r == 0, "returns 0 (%d) in %.2f s", r, dt);
    CHECK(P[TRIG_SRC_PARAM].value == 0, "trigger source CH1 (%g)", P[TRIG_SRC_PARAM].value);
    CHECK(fabs(P[TRIG_LEVEL_PARAM].value) < 0.1, "level inside the signal, near 0 V (%g V; before: -1 V)", P[TRIG_LEVEL_PARAM].value);
    CHECK(P[AUTO_FLAG_PARAM].value == 0, "auto_flag cleared");

    printf("T6 AUTO on a DC level (no signal)\n");
    set_signal(0, 0, 1000, 1); set_signal(1, 0, 0, 1);
    r = run_auto(&dt);
    CHECK(r == 0 && P[TRIG_MODE_PARAM].value == 0, "returns 0 with trigger mode Auto (%d, mode %g) in %.2f s", r, P[TRIG_MODE_PARAM].value, dt);

    printf("T7 AUTO on a square +-4096 (CH2), CH1 at 0\n");
    set_signal(0, 0, 0, 1); set_signal(1, 2, 4096, 2000);
    r = run_auto(&dt);
    CHECK(r == 0 && P[TRIG_SRC_PARAM].value == 1, "returns 0, source CH2 (%d, src %g) in %.2f s", r, P[TRIG_SRC_PARAM].value, dt);
    CHECK(fabs(P[TRIG_LEVEL_PARAM].value) < 0.1, "level near 0 V (%g V)", P[TRIG_LEVEL_PARAM].value);

    printf("T3 AUTO when the level trigger never fires\n");
    m_level_never = 1; set_signal(0, 1, 8000, 1000); set_signal(1, 0, 0, 1);
    r = run_auto(&dt);
    CHECK(r == 0 || r == RP_OSC_AUTO_FAILED, "ends (%d: forced acquisitions, no period -> slow range) in %.2f s, does not hang", r, dt);
    CHECK(dt < 12.0, "bounded time (%.2f s)", dt);

    printf("T8 AUTO with a scope that never triggers (dead)\n");
    m_dead = 1;
    r = run_auto(&dt);
    CHECK(r == RP_OSC_AUTO_FAILED && dt < 1.0, "fails (%d) in %.2f s instead of waiting forever", r, dt);

    printf("T4 quit during AUTO (dead scope)\n");
    {
        pthread_t th; double t0;
        rp_osc_worker_change_state(rp_osc_idle_state);
        memset(P, 0, sizeof(P));
        rp_osc_worker_change_state(rp_osc_auto_set_state);
        pthread_create(&th, NULL, quit_later, NULL);
        t0 = now_s();
        r = rp_osc_auto_set(P, 1.0, 1.0, 0, 0, 0, 0, 0, 0, 0);
        dt = now_s() - t0;
        pthread_join(th, NULL);
        CHECK(r == RP_OSC_AUTO_ABORTED && dt < 0.1, "aborted (%d) %.3f s after the start (quit at 0.05 s)", r, dt);
    }

    printf("T5 the quit state cannot be replaced\n");
    {
        rp_osc_worker_state_t st;
        r = rp_osc_worker_change_state(rp_osc_normal_state);
        rp_osc_worker_get_state(&st);
        CHECK(r == -1 && st == rp_osc_quit_state, "change to normal after quit refused (ret %d, state %d)", r, (int)st);
    }

    printf("%s (%d failures)\n", fails ? "FAILED" : "ALL PASS", fails);
    return fails ? 1 : 0;
}
