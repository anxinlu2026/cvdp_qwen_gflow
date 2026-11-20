module latch(input logic en, input logic [3:0] d, input logic [1:0] s, output logic [3:0] q, output logic [3:0] y);
  always_comb begin if (en) q = d; end            // no assignment when en = 0, no default
  always_comb begin case (s) 2'd0: y = d; 2'd1: y = ~d; endcase end   // case without default
endmodule
