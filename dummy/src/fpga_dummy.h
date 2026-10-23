/**
 * @brief Red Pitaya LOCK FPGA controller.
 *
 * @Author Marcelo Luda <marceluda@gmail.com>
 *
 *
 *
 * This part of code is written in C programming language.
 * Please visit http://en.wikipedia.org/wiki/C_(programming_language)
 * for more details on the language used herein.
 */

#ifndef _FPGA_DUMMY_H_
#define _FPGA_DUMMY_H_

#include <stdint.h>
#include <stddef.h>   /* offsetof() of the register checks */

/** @defgroup fpga_dummy_h LOCK Controller
 * @{
 */

/** Base LOCK FPGA address */
#define DUMMY_BASE_ADDR 0x40600000
/** Base LOCK FPGA core size */
#define DUMMY_BASE_SIZE 0x1000

/** @brief LOCK FPGA registry structure.
 *
 * This structure is direct image of physical FPGA memory. When accessing it all
 * reads/writes are performed directly from/to FPGA LOCK registers.
 */
// [FPGAREG DOCK]
typedef struct dummy_reg_t {

    /** @brief Offset 20'h00000 - oscA_sw
      *  switch for muxer oscA
      *
      *  bits [31: 5] - Reserved
      *  bits [ 4: 0] - Data
      */
    uint32_t oscA_sw;

    /** @brief Offset 20'h00004 - oscB_sw
      *  switch for muxer oscB
      *
      *  bits [31: 5] - Reserved
      *  bits [ 4: 0] - Data
      */
    uint32_t oscB_sw;

    /** @brief Offset 20'h00008 - osc_ctrl
      *  oscilloscope control
      *  [osc2_filt_off,osc1_filt_off]
      *
      *  bits [31: 2] - Reserved
      *  bits [ 1: 0] - Data
      */
    uint32_t osc_ctrl;

    /** @brief Offset 20'h0000C - trig_sw
      *  Select the external trigger signal
      *
      *  bits [31: 8] - Reserved
      *  bits [ 7: 0] - Data
      */
    uint32_t trig_sw;

    /** @brief Offset 20'h00010 - out1_sw
      *  switch for muxer out1
      *
      *  bits [31: 4] - Reserved
      *  bits [ 3: 0] - Data
      */
    uint32_t out1_sw;

    /** @brief Offset 20'h00014 - out2_sw
      *  switch for muxer out2
      *
      *  bits [31: 4] - Reserved
      *  bits [ 3: 0] - Data
      */
    uint32_t out2_sw;

    /** @brief Offset 20'h00018 - slow_out1_sw
      *  switch for muxer slow_out1
      *
      *  bits [31: 4] - Reserved
      *  bits [ 3: 0] - Data
      */
    uint32_t slow_out1_sw;

    /** @brief Offset 20'h0001C - slow_out2_sw
      *  switch for muxer slow_out2
      *
      *  bits [31: 4] - Reserved
      *  bits [ 3: 0] - Data
      */
    uint32_t slow_out2_sw;

    /** @brief Offset 20'h00020 - slow_out3_sw
      *  switch for muxer slow_out3
      *
      *  bits [31: 4] - Reserved
      *  bits [ 3: 0] - Data
      */
    uint32_t slow_out3_sw;

    /** @brief Offset 20'h00024 - slow_out4_sw
      *  switch for muxer slow_out4
      *
      *  bits [31: 4] - Reserved
      *  bits [ 3: 0] - Data
      */
    uint32_t slow_out4_sw;

    /** @brief Offset 20'h00028 - in1
      *  Input signal IN1
      *
      *  bits [31:14] - Reserved
      *  bits [13: 0] - Data
      */
    int32_t  in1;

    /** @brief Offset 20'h0002C - in2
      *  Input signal IN2
      *
      *  bits [31:14] - Reserved
      *  bits [13: 0] - Data
      */
    int32_t  in2;

    /** @brief Offset 20'h00030 - out1
      *  signal for RP RF DAC Out1
      *
      *  bits [31:14] - Reserved
      *  bits [13: 0] - Data
      */
    int32_t  out1;

    /** @brief Offset 20'h00034 - out2
      *  signal for RP RF DAC Out2
      *
      *  bits [31:14] - Reserved
      *  bits [13: 0] - Data
      */
    int32_t  out2;

    /** @brief Offset 20'h00038 - slow_out1
      *  signal for RP slow DAC 1
      *
      *  bits [31:12] - Reserved
      *  bits [11: 0] - Data
      */
    uint32_t slow_out1;

    /** @brief Offset 20'h0003C - slow_out2
      *  signal for RP slow DAC 2
      *
      *  bits [31:12] - Reserved
      *  bits [11: 0] - Data
      */
    uint32_t slow_out2;

    /** @brief Offset 20'h00040 - slow_out3
      *  signal for RP slow DAC 3
      *
      *  bits [31:12] - Reserved
      *  bits [11: 0] - Data
      */
    uint32_t slow_out3;

    /** @brief Offset 20'h00044 - slow_out4
      *  signal for RP slow DAC 4
      *
      *  bits [31:12] - Reserved
      *  bits [11: 0] - Data
      */
    uint32_t slow_out4;

    /** @brief Offset 20'h00048 - oscA
      *  signal for Oscilloscope Channel A
      *
      *  bits [31:14] - Reserved
      *  bits [13: 0] - Data
      */
    int32_t  oscA;

    /** @brief Offset 20'h0004C - oscB
      *  signal for Oscilloscope Channel B
      *
      *  bits [31:14] - Reserved
      *  bits [13: 0] - Data
      */
    int32_t  oscB;

    /** @brief Offset 20'h00050 - read_ctrl
      *  [unused,start_clk,Freeze]
      *
      *  bits [31: 3] - Reserved
      *  bits [ 2: 0] - Data
      */
    uint32_t read_ctrl;


} dummy_reg_t;

/* The struct must match the addresses of the FPGA registers (fpga/prj/v0.94/rtl/dummy.v) */
_Static_assert(offsetof(dummy_reg_t, oscA_sw) == 0x000, "dummy_reg_t.oscA_sw must be at 0x000");
_Static_assert(offsetof(dummy_reg_t, oscB_sw) == 0x004, "dummy_reg_t.oscB_sw must be at 0x004");
_Static_assert(offsetof(dummy_reg_t, osc_ctrl) == 0x008, "dummy_reg_t.osc_ctrl must be at 0x008");
_Static_assert(offsetof(dummy_reg_t, trig_sw) == 0x00C, "dummy_reg_t.trig_sw must be at 0x00C");
_Static_assert(offsetof(dummy_reg_t, out1_sw) == 0x010, "dummy_reg_t.out1_sw must be at 0x010");
_Static_assert(offsetof(dummy_reg_t, out2_sw) == 0x014, "dummy_reg_t.out2_sw must be at 0x014");
_Static_assert(offsetof(dummy_reg_t, slow_out1_sw) == 0x018, "dummy_reg_t.slow_out1_sw must be at 0x018");
_Static_assert(offsetof(dummy_reg_t, slow_out2_sw) == 0x01C, "dummy_reg_t.slow_out2_sw must be at 0x01C");
_Static_assert(offsetof(dummy_reg_t, slow_out3_sw) == 0x020, "dummy_reg_t.slow_out3_sw must be at 0x020");
_Static_assert(offsetof(dummy_reg_t, slow_out4_sw) == 0x024, "dummy_reg_t.slow_out4_sw must be at 0x024");
_Static_assert(offsetof(dummy_reg_t, in1) == 0x028, "dummy_reg_t.in1 must be at 0x028");
_Static_assert(offsetof(dummy_reg_t, in2) == 0x02C, "dummy_reg_t.in2 must be at 0x02C");
_Static_assert(offsetof(dummy_reg_t, out1) == 0x030, "dummy_reg_t.out1 must be at 0x030");
_Static_assert(offsetof(dummy_reg_t, out2) == 0x034, "dummy_reg_t.out2 must be at 0x034");
_Static_assert(offsetof(dummy_reg_t, slow_out1) == 0x038, "dummy_reg_t.slow_out1 must be at 0x038");
_Static_assert(offsetof(dummy_reg_t, slow_out2) == 0x03C, "dummy_reg_t.slow_out2 must be at 0x03C");
_Static_assert(offsetof(dummy_reg_t, slow_out3) == 0x040, "dummy_reg_t.slow_out3 must be at 0x040");
_Static_assert(offsetof(dummy_reg_t, slow_out4) == 0x044, "dummy_reg_t.slow_out4 must be at 0x044");
_Static_assert(offsetof(dummy_reg_t, oscA) == 0x048, "dummy_reg_t.oscA must be at 0x048");
_Static_assert(offsetof(dummy_reg_t, oscB) == 0x04C, "dummy_reg_t.oscB must be at 0x04C");
_Static_assert(offsetof(dummy_reg_t, read_ctrl) == 0x050, "dummy_reg_t.read_ctrl must be at 0x050");
// [FPGAREG DOCK END]


/** @} */

/* Description of the following variables or function declarations is in
 * fpga_lock.c
 */
  extern dummy_reg_t    *g_dummy_reg;

int fpga_dummy_init(void);
int fpga_dummy_exit(void);

#endif // _FPGA_DUMMY_H_
