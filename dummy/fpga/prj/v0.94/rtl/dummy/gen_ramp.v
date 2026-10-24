`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// 
// 
// Scanning module with ramp shape. Outputs triangular ramp. Each  value last for ramp_step clock ticks 
// before changing to the next value.
// Outputs two signals, with a amplitud relation set by ramp_B_factor
// 
// outB = outA * ramp_B_factor / 4096 (registered: one clock after outA).
//
// rp_dummy2 1.0.0: the relock system of the lock-in Apps was removed (its module gen_ramp_relock is not in
// this library) and the multiplier is a registered '*' (Vivado infers a DSP) instead of mult_dsp_14 (a Xilinx
// core that is not in the project). Before, the module could not be synthesized.
// 
//////////////////////////////////////////////////////////////////////////////////


module gen_ramp #(parameter R=14)
    (
    input clk,rst,
    // inputs
    input         [32-1:0] ramp_step,
    input  signed [ R-1:0] ramp_low_lim,ramp_hig_lim,ramp_B_factor,
    input                  ramp_reset,ramp_enable,ramp_direction,
    // outputs
    output                 trigger_low,
    output                 trigger_hig,
    output signed [ R-1:0] outA, outB
    );
    
    // R resolution of input and output signals
    reg  signed [ R-1:0] ramp_signal;
    wire signed [ R-1:0] ramp_signal_next;
    // Second output
    reg  signed [2*R-1:0] outB_28;
    
    // Counter
    reg         [32-1:0] cnt;
    wire        [32-1:0] cnt_next;
    
    // Auxiliary signals
    reg  slope;
    wire slope_next;
    reg  trig_low_last,trig_low_now;
    reg  trig_hig_last,trig_hig_now;
    
    reg  [32-1:0] ramp_step_last, ramp_step_now;
    wire          ramp_step_changed ;
    wire          go ;
    
    reg  [32-1:0] ramp_direction_last, ramp_direction_now;
    wire          floor,ceil,slope_changed;
    
    // Wires for ramp control
    wire signed [ R-1:0] low_lim,hig_lim;
    wire                 enable,direction;
    
    assign  low_lim   = ramp_low_lim   ;
    assign  hig_lim   = ramp_hig_lim   ;
    assign  direction = ramp_direction ;
    assign  enable    = ramp_enable    ;
    
    

        
    
    // Counter evolution    
    always @(posedge clk) 
        if (rst) begin
            cnt            <=    32'b0        ;
            ramp_step_last <=    32'b0        ;
            ramp_step_now  <=    32'b0        ;
        end
        else begin
            cnt            <=    cnt_next        ;
            ramp_step_last <=    ramp_step_now   ;
            ramp_step_now  <=    ramp_step       ;
        end
    

    
    assign ramp_step_changed = ~ ( ramp_step_now == ramp_step_last)  ;
    assign cnt_next          =  |{ramp_reset,ramp_step_changed,ramp_step_now==cnt} ? 32'b0 :  cnt + enable ;
    assign go                =  &{ cnt==ramp_step_now | (~(|ramp_step_now)) , enable , ~ramp_reset } ;
    
    
    
    // ramp_signal evolution
    always @(posedge clk) 
    if (rst) begin
        ramp_signal          <=    {R{1'b0}}    ;
        slope                <=         1'b1    ;
        ramp_direction_last  <=         1'b0    ;
        ramp_direction_now   <=         1'b0    ;
    end
    else if(ramp_reset) begin
        ramp_signal          <=    {R{1'b0}}      ;
        slope                <=   ~direction ;
        ramp_direction_last  <=    direction ;
        ramp_direction_now   <=    direction ;
        trig_low_last        <=    1'b0           ;
        trig_low_now         <=    1'b0           ;
        trig_hig_last        <=    1'b0           ;
        trig_hig_now         <=    1'b0           ;
    end
    else begin
        if(go) begin
            ramp_signal          <= ramp_signal_next   ;
            slope                <= slope_next         ;
            ramp_direction_last  <= ramp_direction_now ;
            ramp_direction_now   <= direction     ;
        end
        else begin
            ramp_signal          <= ramp_signal      ;
            slope                <= slope            ;
            ramp_direction_last  <= ramp_direction_last ;
            ramp_direction_now   <= ramp_direction_now  ;
        end
        trig_low_last        <=    trig_low_now        ;
        trig_low_now         <=    trigger_low         ;
        trig_hig_last        <=    trig_hig_now        ;
        trig_hig_now         <=    trigger_hig         ;
    end
    
    
    assign floor         = ( ramp_signal<=low_lim  )  ;
    assign ceil          = ( ramp_signal>=hig_lim  )  ;
    assign slope_changed =  ramp_direction_now ^ ramp_direction_last ;
    
    assign ramp_signal_next = floor ? ramp_signal + 1'b1  :
                              ceil  ? ramp_signal - 1'b1  :
                              slope ? ramp_signal + 1'b1  :
                                      ramp_signal - 1'b1  ;
    
    assign slope_next       = floor         ? 1'b1   :
                              ceil          ? 1'b0   :
                              slope_changed ? ~slope : 
                                               slope ;
    
    assign trigger_low = &{ ramp_signal==low_lim , go, ~trig_low_last } ;
    assign trigger_hig = &{ ramp_signal==hig_lim , go, ~trig_hig_last } ;
    
    
    // outputs
    assign outA    = ramp_signal ;
    
    always @(posedge clk)
        if (rst) outB_28 <= {2*R{1'b0}} ;
        else     outB_28 <= $signed(ramp_signal) * $signed(ramp_B_factor) ;
    
    assign outB     = $signed(outB_28[2*R-2:0]) >>> 12 ;
    
endmodule

/*
gen_ramp #(.R(14)) NAME (
    .clk(clk),  .rst(rst),
    // inputs
    .ramp_step (   32'd1000 ),
    .ramp_low_lim(  14'd0     ),
    .ramp_hig_lim(  14'd1000  ),
    .ramp_reset  (    1'b0    ),
    .ramp_enable (   1'b1     ),
    .ramp_direction(1'b1      ),
    .ramp_B_factor (14'sd4096 ),   // outB = outA * ramp_B_factor / 4096
    // outputs
    .trigger_low ( TRIG_LOW   ),   // one tick when the ramp reaches ramp_low_lim
    .trigger_hig ( TRIG_HIG   ),   // one tick when the ramp reaches ramp_hig_lim
    .outA        (  OUT_A     ),
    .outB        (  OUT_B     )
);
*/
