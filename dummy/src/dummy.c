/**
 * @brief Red Pitaya LOCK Controller
 *
 * @Author Marcelo Luda <marceluda@gmail.com>
 *
 *
 *
 * This part of code is written in C programming language.
 * Please visit http://en.wikipedia.org/wiki/C_(programming_language)
 * for more details on the language used herein.
 */

#include <stdio.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

#include "dummy.h"
#include "fpga_dummy.h"


#ifndef min
    #define min(a,b) ((a) < (b) ? (a) : (b))
#endif

#ifndef max
    #define max(a,b) ((a) > (b) ? (a) : (b))
#endif


int   save_read_ctrl = -1 ;
float dummy_error_var = 0 ;

/**
 * GENERAL DESCRIPTION:
 *
 *
 * PENDIENTE  PENDIENTE  PENDIENTE  PENDIENTE  PENDIENTE  PENDIENTE
 *
 *
 */


/*----------------------------------------------------------------------------------*/
/** @brief Initialize LOCK Controller module
 *
 * A function is intended to be called within application initialization. It's purpose
 * is to initialize LOCK Controller module.
 *
 * @retval     -1 failure, error message is reported on standard error
 * @retval      0 successful initialization
 */

int dummy_init(void)
{
    if(fpga_dummy_init() < 0) {
        return -1;
    }

    return 0;
}


/*----------------------------------------------------------------------------------*/
/** @brief Cleanup LOCK Controller module
 *
 * A function is intended to be called on application's termination. The main purpose
 * of this function is to release allocated resources...
 *
 * @retval      0 success, never fails.
 */
int dummy_exit(void)
{
    fpga_dummy_exit();

    return 0;
}


/*----------------------------------------------------------------------------------*/
/**
 * @brief Update LOCK Controller module towards actual settings.
 *
 * A function is intended to be called whenever one of the settings is modified
 *
 * @param[in] params  Pointer to overall configuration parameters
 * @retval -1 failure, error message is repoted on standard error device
 * @retval  0 succesful update
 */
int dummy_update(rp_app_params_t *params)
{

  // [FPGAUPDATE DOCK]
    g_dummy_reg->oscA_sw                   = (int)params[DUMMY_OSCA_SW                 ].value;
    g_dummy_reg->oscB_sw                   = (int)params[DUMMY_OSCB_SW                 ].value;
    g_dummy_reg->osc_ctrl                  = (((int)params[DUMMY_OSC2_FILT_OFF].value)<<1) + ((int)params[DUMMY_OSC1_FILT_OFF].value);
    g_dummy_reg->trig_sw                   = (int)params[DUMMY_TRIG_SW                 ].value;
    g_dummy_reg->out1_sw                   = (int)params[DUMMY_OUT1_SW                 ].value;
    g_dummy_reg->out2_sw                   = (int)params[DUMMY_OUT2_SW                 ].value;
    g_dummy_reg->slow_out1_sw              = (int)params[DUMMY_SLOW_OUT1_SW            ].value;
    g_dummy_reg->slow_out2_sw              = (int)params[DUMMY_SLOW_OUT2_SW            ].value;
    g_dummy_reg->slow_out3_sw              = (int)params[DUMMY_SLOW_OUT3_SW            ].value;
    g_dummy_reg->slow_out4_sw              = (int)params[DUMMY_SLOW_OUT4_SW            ].value;
  //g_dummy_reg->in1                       = (int)params[DUMMY_IN1                     ].value;
  //g_dummy_reg->in2                       = (int)params[DUMMY_IN2                     ].value;
  //g_dummy_reg->out1                      = (int)params[DUMMY_OUT1                    ].value;
  //g_dummy_reg->out2                      = (int)params[DUMMY_OUT2                    ].value;
  //g_dummy_reg->slow_out1                 = (int)params[DUMMY_SLOW_OUT1               ].value;
  //g_dummy_reg->slow_out2                 = (int)params[DUMMY_SLOW_OUT2               ].value;
  //g_dummy_reg->slow_out3                 = (int)params[DUMMY_SLOW_OUT3               ].value;
  //g_dummy_reg->slow_out4                 = (int)params[DUMMY_SLOW_OUT4               ].value;
  //g_dummy_reg->oscA                      = (int)params[DUMMY_OSCA                    ].value;
  //g_dummy_reg->oscB                      = (int)params[DUMMY_OSCB                    ].value;
    g_dummy_reg->read_ctrl                 = (int)params[DUMMY_READ_CTRL               ].value;
  //g_dummy_reg->stream_ip                   (not a controller parameter: written by the c/ tools)
  //g_dummy_reg->stream_port                 (not a controller parameter: written by the c/ tools)
  //g_dummy_reg->stream_rate                 (not a controller parameter: written by the c/ tools)
  //g_dummy_reg->stream_cmd                  (not a controller parameter: written by the c/ tools)
  // [FPGAUPDATE DOCK END]

    return 0;
}


int dummy_freeze_regs(){
  //TRACE("LOLO: prev save_read_ctrl = %d \n",  save_read_ctrl );
  save_read_ctrl          = (uint)g_dummy_reg->read_ctrl ;
  g_dummy_reg->read_ctrl   =  g_dummy_reg->read_ctrl | 0b00000000000000000000000000000001 ;
  //TRACE("LOLO: g_dummy_reg->read_ctrl = %d \n",  g_dummy_reg->read_ctrl );
  return 0;
}

int dummy_restore_regs(){
  //TRACE("LOLO: prev save_read_ctrl = %d \n",  save_read_ctrl );
  g_dummy_reg->read_ctrl   =  save_read_ctrl ;
  //TRACE("LOLO: g_dummy_reg->read_ctrl = %d \n",  g_dummy_reg->read_ctrl );
  return 0;
}


/*----------------------------------------------------------------------------------*/
/**
 * @brief Update DUMMY Controller module towards actual settings FROM THE FPGA REGs
 *
 * A function is intended to be called whenever one of the settings is modified BY FPGA
 *
 * @param[in] params  Pointer to overall configuration parameters
 * @retval -1 failure, error message is repoted on standard error device
 * @retval  0 succesful update
 */
int dummy_update_main(rp_app_params_t *params)
{
    if(g_dummy_reg == NULL)
        return -1;

    //uint32_t  mask16 =   0b00000000000000000000000000001111 ;

    // [PARAMSUPDATE DOCK]
    params[ 81].value = (float)g_dummy_reg->oscA_sw              ; // dummy_oscA_sw
    params[ 82].value = (float)g_dummy_reg->oscB_sw              ; // dummy_oscB_sw
    params[ 83].value = (float) ((g_dummy_reg->osc_ctrl      )& 0x01) ; // dummy_osc1_filt_off
    params[ 84].value = (float) ((g_dummy_reg->osc_ctrl >> 1 )& 0x01) ; // dummy_osc2_filt_off
    params[ 86].value = (float)g_dummy_reg->trig_sw              ; // dummy_trig_sw
    params[ 87].value = (float)g_dummy_reg->out1_sw              ; // dummy_out1_sw
    params[ 88].value = (float)g_dummy_reg->out2_sw              ; // dummy_out2_sw
    params[ 89].value = (float)g_dummy_reg->slow_out1_sw         ; // dummy_slow_out1_sw
    params[ 90].value = (float)g_dummy_reg->slow_out2_sw         ; // dummy_slow_out2_sw
    params[ 91].value = (float)g_dummy_reg->slow_out3_sw         ; // dummy_slow_out3_sw
    params[ 92].value = (float)g_dummy_reg->slow_out4_sw         ; // dummy_slow_out4_sw
    params[ 93].value = (float)g_dummy_reg->in1                  ; // dummy_in1
    params[ 94].value = (float)g_dummy_reg->in2                  ; // dummy_in2
    params[ 95].value = (float)g_dummy_reg->out1                 ; // dummy_out1
    params[ 96].value = (float)g_dummy_reg->out2                 ; // dummy_out2
    params[ 97].value = (float)g_dummy_reg->slow_out1            ; // dummy_slow_out1
    params[ 98].value = (float)g_dummy_reg->slow_out2            ; // dummy_slow_out2
    params[ 99].value = (float)g_dummy_reg->slow_out3            ; // dummy_slow_out3
    params[100].value = (float)g_dummy_reg->slow_out4            ; // dummy_slow_out4
    params[101].value = (float)g_dummy_reg->oscA                 ; // dummy_oscA
    params[102].value = (float)g_dummy_reg->oscB                 ; // dummy_oscB
    params[103].value = (float)g_dummy_reg->read_ctrl            ; // dummy_read_ctrl
    // [PARAMSUPDATE DOCK END]

    return 0;
}
