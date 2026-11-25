# schedule.md — cycle schedule of `pipelined_adder_32bit`, from task.md only

Counting. Edge 1 = the rising clock edge that samples `start` = 1 together with `A` and `B` (the edge at which
the operation is accepted). Edge 2, 3, 4 = the next rising edges. "After edge n" = the output values from just
after edge n until just before edge n+1; this is what `Top.step` returns for the call of edge n.

## Statements (each with its sentence in task.md)

S1. Acceptance. An edge with `start` = 1 (and `reset` = 0) accepts one operation with the `A`, `B` values of
    that edge. There is no busy state: an operation can be accepted at every edge, also at edges 2, 3, 4 of an
    earlier operation, and each one is computed independently.
    - "The `start` signal initiates the addition process"
    - Stage 1: "Captures the `start` signal to initiate the pipeline."
    - "For a continuous stream of inputs (with new inputs provided every clock cycle), the pipeline will
      produce new outputs every clock cycle after the initial 4-cycle delay."

S2. Latency 4. For an operation accepted at edge 1: after edges 1, 2, 3 this operation does not raise `done`;
    after edge 4, `done` = 1 and `S`, `Co` carry the result of this operation.
    (One edge per pipeline stage: stage 1 at edge 1, stage 2 at edge 2, stage 3 at edge 3, stage 4 at edge 4.)
    - "The pipelined adder uses **4 pipeline stages** ... store intermediate results in registers (D flip-flops)"
    - "the `done` signal is asserted after the final stage is completed"
    - Stage 4: "Generates the `done` signal, indicating the computation is complete after the final stage."
    - "The design requires **4 clock cycles** after the `start` signal is asserted to produce the first result.
      The `done` signal goes high after this delay, indicating the computation is complete."
    - "It is expected to be asserted after 4 cycles."
    - "The following table shows the output values, 4 clock cycles after each input"
    See open point O2 for the wording "4 clock cycles after".

S3. `done` follows `start` with that delay, one cycle per accepted operation.
    After edge n (n >= 4 edges after the last reset edge, see O3), `done` = 1 exactly when `start` was 1 at
    edge n-3, else 0. So a single `start` pulse of one cycle gives `done` = 1 for exactly one cycle (after
    edge 4) and 0 after edge 5; `start` = 1 on k successive edges gives `done` = 1 for k successive cycles.
    - "(For non-continuous inputs, `done` is high for only one clock cycle. ..."
    - "For a continuous stream of inputs ... the pipeline will produce new outputs every clock cycle after the
      initial 4-cycle delay."
    - `done` is never 1 for an edge at which no operation was accepted: "the `done` signal is asserted after the
      final stage is completed"

S4. Result value. In every cycle with `done` = 1: {`Co`, `S`} = `A` + `B` as a 33-bit unsigned sum of the
    operands sampled at edge 1 of that operation; `S` = bits 31..0, `Co` = bit 32. Carry-in is 0.
    - "designed to perform the addition of two 32-bit operands"
    - Stage 1: "assuming an initial carry-in of 0"; stages 2..4: "using the carry-out from Stage 1/2/3"
    - Stage 4: "Assembles the complete 32-bit sum and final carry-out from all stages."
    - table columns "Expected S", "Expected Co"

S5. Retention. After a `done` cycle, `S` and `Co` keep the result as long as no new calculation changes them.
    Judged case: if from edge 1 of the operation on `A` and `B` stay at the accepted values and no reset
    occurs, `S` and `Co` stay at the result in all later cycles (with `done` = 0 unless `start` is given again).
    - "Output sum and carry will be retained until it changes from the calculation of a new set of inputs)"
    For the other cases (A or B changed while `start` = 0) see open point O1.

S6. Reset. `reset` is active high and acts only at a rising clock edge.
    - "It is triggered by the positive edge of the clock (`clk`) and an active-high synchronous reset
      (`reset`) signal"
    What the outputs are after a reset edge is not stated in the text (O3, O4). What follows from S3 without any
    statement about reset: after a reset edge, `done` is 0 in every cycle whose edge n-3 had `start` = 0.

S7. Inputs while operations are in flight. They are not ignored and not held back; see S1. `A` and `B` at an
    edge with `start` = 0 never produce a `done`.

## Example timeline (single operation, A and B held, start = 1 for edge 1 only)

| after edge | reset edge | 1 | 2 | 3 | 4 | 5 | 6 |
|------------|-----------|---|---|---|---|---|---|
| `done`     | not judged if a start was pending, else 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| `S`, `Co`  | not judged | not judged | not judged | not judged | A+B | A+B | A+B |

(After edges 1..3 the outputs are "not judged" only for the first operation after reset; later they follow
S5/O1.)

## Open points

O1. `S`, `Co` in cycles with `done` = 0 when `A` or `B` changed at edges with `start` = 0.
    Text: "Output sum and carry will be retained until it changes from the calculation of a new set of inputs".
    It does not say whether values of `A`, `B` given without `start` are "a new set of inputs".
    Choices that satisfy the text:
    (a) the data registers load only for accepted operations: `S`, `Co` keep the last result until the next
        `done`;
    (b) the data registers load at every edge: `S`, `Co` are the sum of the `A`, `B` sampled 3 edges earlier,
        with or without `start`.
    Checker: MUST LEAVE UNJUDGED (judge `S`, `Co` only in `done` = 1 cycles and in the case of S5).
    The model returns `None` there.

O2. How "4 clock cycles after the `start` signal is asserted" is counted.
    Choices: (a) `done` after edge 4 counting the accepting edge as edge 1 (four registers, S2);
    (b) `done` after edge 5 (four full cycles after the accepting edge, five registers).
    The schedule uses (a), because the text gives four stages, each stored in registers, with `start` captured
    in stage 1 and `done` generated in stage 4, and a testbench that sets `start` between two edges sees `done`
    4 edges later under (a). Checker: JUDGED with (a). If the RTL has `done` and the data both exactly one
    cycle later than (a), report this as "reading (b)" to the orchestrator, do not repair it on this ground alone.

O3. Effect of a reset edge on operations in flight and on a `start` given at the reset edge.
    Text: only the DFF sentence (S6) and "details are explained in the given code ... Retain the clock, reset
    functionalities"; no sentence says which registers are reset or to what value.
    Choices: (a) reset clears every stage, operations accepted at the 3 edges before the reset edge and a
    `start` at the reset edge give no `done`; (b) only some registers are reset, such operations still complete.
    Checker: MUST LEAVE UNJUDGED `done` (and `S`, `Co`) in the cycles after edges r .. r+3 (r = a reset edge)
    whose edge n-3 had `start` = 1; if that `start` was 0, `done` must be 0 (S3). The model returns `None`.
    A testbench avoids the point by keeping `start` = 0 from 3 edges before reset until reset is released.

O4. `S`, `Co` after reset, until the first `done` = 1 cycle.
    Text: nothing. Choices: 0, any other constant, or (O1 b) the sum of whatever `A`, `B` were sampled.
    Checker: MUST LEAVE UNJUDGED.

O5. Port names of the sum and carry outputs (table headings "S", "Co" only), and all outputs before the first
    reset edge. Checker: map the names from the RTL port list; MUST LEAVE UNJUDGED before the first reset.

O6. Length of reset needed. Text: nothing. A checker should apply reset for at least 4 edges with `start` = 0
    before the first operation, then nothing depends on this point. UNJUDGED.

O7. Internal structure (which byte is computed at which edge, whether the CLA has its own output register in
    addition to the D flip-flops, the internal G/P/C signals). Not visible at the ports once S2..S4 hold.
    Checker: not a port requirement; UNJUDGED at the ports.
