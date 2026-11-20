module t;
  localparam N = 128;
  logic [N-1:0] d;
  logic [7:0] a, b8, c8;
  logic [3:0] x;
  logic r1, r2, clk;
  logic [7:0] s [4][4];
  integer k;
  initial begin
    d = 128'h00112233445566778899aabbccddeeff;
    k = 0; $display("R1 k=0 d[N-8*k-1 -: 8] = %h (expect 00 = d[127:120])", d[N-8*k-1 -: 8]);
    k = 15; $display("R1 k=15 = %h (expect ff = d[7:0])", d[N-8*k-1 -: 8]);
    $display("R1 d[16 +: 8] = %h (expect dd = d[23:16])", d[16 +: 8]);
    $display("R1 d[N-1-:8] = %h (expect 00, base N-1)", d[N-1-:8]);
    a = 8'b0000_0110; b8 = 8'd3; c8 = 8'd3;
    $display("R5 a & b8 == c8 = %0d (expect a & 1 = 0)", a & b8 == c8);
    $display("R5 8'd1 << 1 + 2 = %0d (expect 8)", 8'd1 << 1 + 2);
    x = 4'hA; $display("R3 {4'h1, x} = %h (expect 1a)", {4'h1, x});
    $display("R4 narrow to wide: %h (expect 000a)", 16'(x));
    s[1][2] = 8'h5c; $display("R6 s[1][2] = %h", s[1][2]);
  end
  // R8/R9: non-blocking: r2 takes r1's old value
  initial begin clk=0; r1=0; r2=0; #5 r1=1; repeat(3) #5 clk=~clk; end
  always_ff @(posedge clk) r2 <= r1;
  always_ff @(posedge clk) $display("R8 at edge t=%0t: r1=%0d r2(before update)=%0d", $time, r1, r2);
  initial #40 $display("R8 after edges r2=%0d", r2);
endmodule
