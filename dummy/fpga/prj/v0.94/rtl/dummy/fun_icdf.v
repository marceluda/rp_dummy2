`timescale 1ns / 1ps


//(* keep_hierarchy = "yes" *)
module fun_icdf
(
    input clk,rst,
    input signed    [11-1:0] in,   // input
    output signed   [14-1:0] out   // output
);
    // Addr for memory slots



    wire         [11-1:0]  pos ;
    reg  signed  [14-1:0]  out_reg ;
    reg                    neg_reg ;   // sign of in, delayed like out_reg
    wire signed  [14-1:0]  out_fun ;

    reg signed [14-1:0] icdf [1024-1:0]; // vector for amplitude value
    initial
    begin
        $readmemb("icdf_data.dat", icdf); // read memory binary code from data_sin.dat
    end

    // |in| (before rp_dummy2 1.0.0 the comparison 'in >= 11'b0' was unsigned, always true)
    assign pos = in[10] ? -in  : in ;

    assign out_fun = icdf[pos[10-1:0]];


    always @(posedge clk)
        if (rst)
        begin
            out_reg       <=   14'b0    ;
            neg_reg       <=   1'b0     ;
        end
        else
        begin
            out_reg       <=   out_fun   ;
            neg_reg       <=   in[10]    ;
        end

    // output sign = sign of in (taken in the same clock as the table value: latency 1 for both)
    assign out  = neg_reg ? - out_reg  : out_reg ;

endmodule

    //  fun_icdf i_fun_icdf  ( .clk(clk), .rst(rst), .in( IN11 ),  .out( OUT14 ) );
