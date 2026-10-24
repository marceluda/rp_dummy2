// Testbench of library modules of dummy/fpga/prj/v0.94/rtl/dummy/ fixed in rp_dummy2 1.0.0 (make -C tests hdl,
// Vivado 2020.1 xsim): fun_icdf (|in| and output sign: before, negative inputs gave wrong values), fun_pico
// (table lookup), gen_ramp (triangle between the limits, triggers, outB = outA * B / 4096 one tick later).
// Prints "LIB ERRORS=<n>" and checks the ramp sequence.
`timescale 1ns/1ps
module lib_modules_tb;
  reg clk=0, rst=1; always #4 clk=~clk;
  reg  signed [10:0] ia; wire signed [13:0] oa;
  reg  signed [13:0] pa; wire signed [13:0] po;
  wire signed [13:0] rA, rB; wire tl, th;
  fun_icdf ui(.clk(clk),.rst(rst),.in(ia),.out(oa));
  fun_pico up(.clk(clk),.rst(rst),.in(pa),.out(po));
  gen_ramp #(.R(14)) ur(.clk(clk),.rst(rst),.ramp_step(32'd0),.ramp_low_lim(-14'sd3),.ramp_hig_lim(14'sd4),
     .ramp_reset(1'b0),.ramp_enable(1'b1),.ramp_direction(1'b1),.ramp_B_factor(14'sd2048),
     .trigger_low(tl),.trigger_hig(th),.outA(rA),.outB(rB));
  reg signed [13:0] icdf [0:1023]; reg signed [13:0] pico[0:2047];
  integer i, a, err=0;
  initial begin
    $readmemb("icdf_data.dat", icdf); $readmemb("pico_data.dat", pico);
    ia=0; pa=0; repeat(3) @(posedge clk); rst=0;
    for (i=-1023;i<=1023;i=i+97) begin
      @(negedge clk) ia=i; pa=i*7;
      @(posedge clk); #1;
      if (oa !== (i<0 ? -icdf[-i] : icdf[i])) begin err=err+1; $display("ICDF in=%0d out=%0d", i, oa); end
      a = i*7; if (a<0) a=-a; if (a>2047) a=2047;
      if (po !== pico[a]) begin err=err+1; $display("PICO in=%0d out=%0d", i*7, po); end
    end
    // ramp -3..4, one step per tick (ramp_step 0); outB = outA / 2 (B = 2048) of the previous tick
    a = 99;
    for (i=0;i<24;i=i+1) begin
      @(posedge clk); #1;
      if (a != 99 && rB !== (a >>> 1)) begin err=err+1; $display("RAMP B=%0d expected %0d", rB, a >>> 1); end
      if (rA < -3 || rA > 4) begin err=err+1; $display("RAMP A=%0d out of the limits", rA); end
      if (tl !== (rA == -3) || th !== (rA == 4)) begin err=err+1; $display("RAMP A=%0d tl=%b th=%b", rA, tl, th); end
      a = rA;
    end
    $display("LIB ERRORS=%0d", err); $finish;
  end
endmodule
