# decision.md — `pipelined_adder_32bit`

## 1. Interface type: (c) inputs marked valid, outputs marked valid

`start` marks `A`, `B` as valid at an edge; `done` marks `S`, `Co` as valid a fixed number of edges later. There
is no ready signal and no busy state, a new operation can enter at every edge.
- "The `start` signal initiates the addition process, and the `done` signal is asserted after the final stage is
  completed."
- "For a continuous stream of inputs (with new inputs provided every clock cycle), the pipeline will produce new
  outputs every clock cycle after the initial 4-cycle delay."
- "(For non-continuous inputs, `done` is high for only one clock cycle. ..."
Not (e): with (e) a second `start` before the end signal would be undefined or ignored; here the text requires
one result per cycle for one input per cycle. For a single isolated operation the behaviour looks like (e).

## 2. Timed specification: provided

The main schedule is fixed by the text:
- latency: "The design requires **4 clock cycles** after the `start` signal is asserted to produce the first
  result. The `done` signal goes high after this delay"; "It is expected to be asserted after 4 cycles."; "The
  following table shows the output values, 4 clock cycles after each input"; "4 pipeline stages ... store
  intermediate results in registers"
- rise and fall of `done`: "For non-continuous inputs, `done` is high for only one clock cycle."
- outputs between operations: "Output sum and carry will be retained until it changes from the calculation of a
  new set of inputs"
- inputs while busy: "with new inputs provided every clock cycle ... new outputs every clock cycle"
- reset: "active-high synchronous reset (`reset`)", positive clock edge.
Not fixed: output values after reset and the reach of reset (open points O3, O4).

Files written: top_interface.md, schedule.md, top_model.py.

## 3. Function: computable from the text

{`Co`, `S`} = `A` + `B`, 33-bit unsigned result of two 32-bit unsigned operands, carry-in 0.
- "designed to perform the addition of two 32-bit operands"
- Pipeline Behavior table: least significant byte first "assuming an initial carry-in of 0", each next byte
  "using the carry-out from Stage" before it, "Assembles the complete 32-bit sum and final carry-out".
- CLA formulas: G[i] = A[i] & B[i], C[i+1] = G[i] | (P[i] & C[i]), S[i] = P[i] ^ C[i], carry = MSB of C.
Standard algorithm named by the text: carry-lookahead adder (CLA), four 8-bit CLA blocks with the carry chained
between them. The function at the ports is plain binary addition.

## 4. Self-check (python3 top_model.py): ALL PASS

Examples with values in task.md: the four rows of the table "Simulation Results" (columns A, B, Expected S,
Expected Co). All four used.
- bit-level four-stage CLA with P = A ^ B gives Expected S and Expected Co for all 4 rows: pass
- the same with P = A | B gives the expected values for none of the 4 rows (see 6, C1): confirmed
- function equals A + B on 20000 random pairs: pass
- four rows as a continuous stream (start = 1 on 4 successive edges after reset): `done` = 0,0,0,1,1,1,1,0,0 and
  the values of the 4 rows in the `done` cycles in order: pass (for all three settings of open point O1)
- each row as a single operation with A, B held: `done` only after edge 4, S/Co retained afterwards: pass
- the model with open points left open returns a value only where the choices of O1 agree (5000 random edges
  with random resets): pass
The task gives no waveform and no example for reset, for `done` = 0 cycles or for changing inputs without `start`.

## 5. Open points (details and choices in schedule.md)

- O1 `S`, `Co` in `done` = 0 cycles when A or B changed without `start` (hold last result, or follow the
  inputs) — unjudged
- O2 counting of "4 clock cycles after start": schedule uses `done` after the 4th edge counting the accepting
  edge as the 1st — judged with this reading; a uniform one-cycle-later RTL is to be reported, not repaired on
  that ground alone
- O3 effect of reset on operations in flight and on `start` at a reset edge — unjudged
- O4 `S`, `Co` after reset until the first `done` — unjudged
- O5 real port names of sum and carry outputs; outputs before the first reset — names from the RTL, unjudged
- O6 required length of reset — unjudged
- O7 internal structure / internal signals — not a port requirement

## 6. Contradictory or unclear in task.md

C1 (contradiction). "The propagate signal (`P`) for each bit is 1 if either `A[i]` or `B[i]` is 1 (**i.e.,
   A[i] ^ B[i]**)." The words describe OR, the formula is XOR. With "S[i] = P[i] ^ C[i]" only XOR gives a sum;
   with OR none of the four expected rows comes out (self-check). The carry is the same for both. Used: XOR.
   Not visible at the ports; a worker must not take an OR-propagate in the carry path alone as a fault, but an
   OR-propagate in the sum bit is one.
C2 (unclear). "Input operands are divided into 8-bit segments for processing in parallel." against "These stages
   progressively process the data from lower to higher bits" and the table, where each stage uses the carry-out
   of the stage before. Used: the progressive description (it has the detail). Not visible at the ports.
C3 (unclear). "Note: **Interface:** details are explained in the given code for all modules." The task text
   gives no port list; the result ports are named only by the table headings "Expected S", "Expected Co".
C4 (unclear). "Retain the clock, reset functionalities, and control signal behavior while correcting the bugs"
   against "Done is asserted for the first input 2 cycles after the start. It is expected to be asserted after
   4 cycles." The control signal `done` has to change, so "retain ... control signal behavior" cannot mean the
   present timing of `done`. Used: the 4-cycle requirement. The same sentence means the reset behaviour is
   defined by the given code, which this specification does not have (O3, O4).
C5 (unclear). "requires 4 clock cycles after the `start` signal is asserted" — counting, see O2.
C6 (unclear). "Output sum and carry will be retained until it changes from the calculation of a new set of
   inputs" — whether inputs without `start` count, see O1.
C7 (unclear). "The CLA calculates the sum and carry_out combinationally and latches it to the output of that
   module at the positive edge of the clock." together with D flip-flops "between pipeline stages": the text
   does not say whether these are the same registers. The total of 4 is fixed, the split is not (O7).
C8 (unclear). Title "Simulation Results for Carry Lookahead Adder Testing", but the rows are 32-bit values with
   `Done`, so they are results of the top module, not of the 8-bit CLA.

## 7. Told by the task about the faults

- "During testing, it was found that the behavior was not as expected. Identify and correct the bugs to match
  the behavior described below." (says only that there are several faults)
- "Done is asserted for the first input 2 cycles after the start." (fault description: `done` too early by 2)
  The next sentence, "It is expected to be asserted after 4 cycles.", states required behaviour and is used.
- Table columns "Got S", "Got Co", "Result = Fail" for the four rows: 0x9CD2A56B / 0, 0x76356AA8 / 0,
  0x6640824E / 0, 0xC7366DA4 / 0. Fault descriptions, not used as requirements. The columns "Expected S",
  "Expected Co" and "Done = 1" of the same table state required behaviour and are used.
- "Retain the clock, reset functionalities, and control signal behavior while correcting the bugs" (limits the
  fix; states no behaviour by value)
No sentence of the task says where in the RTL the faults are or what the fix is.
