module t2;
  integer n, i, acc;
  logic signed [3:0] sa; logic [3:0] ua; logic [7:0] w, w2; logic signed [7:0] sw;
  logic clk = 0; logic [3:0] r;
  initial begin
    // R12: procedural for loop with a bound known only at run time -> executed at run time, not unrolled at elaboration
    n = 3; acc = 0; for (i = 0; i < n; i++) acc = acc + 1; $display("R12 runtime bound n=3 -> acc=%0d", acc);
    n = 5; acc = 0; for (i = 0; i < n; i++) acc = acc + 1; $display("R12 runtime bound n=5 -> acc=%0d", acc);
    // signed widening = sign extension
    sa = -4'sd3; sw = sa; $display("signed widen 4'sb%b -> 8'b%b (expect 11111101)", sa, sw);
    // mixed signed/unsigned -> unsigned
    ua = 4'd1; $display("mixed: (sa < ua) = %0d (signed -3 < 1 would be 1; as unsigned 13 < 1 is 0)", sa < ua);
    // >>> arithmetic vs >> logical on signed
    sw = -8'sd16; $display(">>>: %b  >>: %b (expect 11111100 and 00111100)", sw >>> 2, sw >> 2);
    // unsized decimal is 32 bits
    $display("width of 1 = %0d", $bits(1));
  end
  // multiple non-blocking assignments to one register in one edge: last wins
  always_ff @(posedge clk) begin r <= 4'd1; r <= 4'd2; end
  initial begin #5 clk = 1; #1 $display("last NBA wins: r=%0d (expect 2)", r); end
  // generate-if evaluated at elaboration
  localparam P = 1;
  generate if (P == 1) begin : g1 initial $display("generate-if P==1 branch elaborated"); end
           else begin : g0 initial $display("generate-if else branch"); end endgenerate
endmodule
