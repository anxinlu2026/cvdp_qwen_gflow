# schedule.md — cycle schedule of `String_to_ASCII_Converter`

Source: task.md only. Edges are rising clock edges. "After edge n" = the values of the output ports right after that edge, held until the next edge.
Edge 0 = the edge at which an operation is accepted: `start` = 1 is sampled while the module is idle (`ready` = 1).

## Schedule of one operation

| Edge | Inputs sampled | `ascii_out` after the edge | `valid` | `ready` |
|---|---|---|---|---|
| before edge 0 (idle) | — | all 0 (S5) | 0 (S5) | 1 (S4) |
| 0 | `start` = 1, `char_in` = 8 codes | ASCII value of all 8 codes, `ascii_out[i]` from `char_in[i]` | 1 | 0 |
| 1 | `start` = 0 | all 0 | 0 | 1 |
| 2, 3, ... (`start` = 0) | — | all 0 | 0 | 1 |

Statements and their sentences:

- S1. All 8 values appear together after edge 0, none earlier or later. — "All 8 characters from the input `char_in` should be processed simultaneously." / "The ascii_out array should contain the ASCII values corresponding to all input characters within 1 clock cycle" / Test Sequence row "1 | 1 | "A1b!C3d@" | [65, 49, 98, 33, 67, 51, 100, 64]".
- S2. `valid` = 1 after edge 0, together with the values. — "The `valid` signal should be asserted in the same cycle" / "**valid**: Should assert immediately after `start`."
- S3. `ready` = 0 after edge 0. — "`ready` should deassert until processing is complete." / "**ready**: Should deassert during processing and assert immediately after completion."
- S4. After edge 1: `ready` = 1, `valid` = 0. — "When processing completes: The `ready` signal should assert to indicate readiness for new inputs. The `valid` signal should deassert." With S1 the processing takes one cycle, so completion is edge 1. "deassert" in S3 also means `ready` was 1 while idle before edge 0.
- S5. After edge 1 and on later edges without a new start: `ascii_out` = all 0. — "it should be reset to all zeros after processing is completed to ensure proper initialization for subsequent operations" / Test Sequence rows 2..5, column "Expected ascii_out": "[0, 0, 0, 0, 0, 0, 0, 0]" with `start` = 0 and `char_in` unchanged.
- S6. `char_in` is used only at edge 0; with `start` = 0 it has no effect (rows 2..5 of the Test Sequence keep `char_in` = "A1b!C3d@" and expect zeros).
- S7. A new operation may be accepted from edge 2 on (the first edge that samples `ready` = 1). — "The `ready` signal should assert to indicate readiness for new inputs."

## Function (values of `ascii_out` at edge 0)

From "Custom Encoding Scheme" (code = 8-bit value of one `char_in` element):

| Code | ASCII value | Sentence |
|---|---|---|
| 0..9 | code + 48 | "Digits (0-9): Mapped to values 0 to 9." |
| 10..35 | code + 55 | "Uppercase Letters (A-Z): Mapped to values 10 to 35 (A = 10, B = 11, ..., Z = 35)." |
| 36..61 | code + 61 | "Lowercase Letters (a-z): Mapped to values 36 to 61 (a = 36, b = 37, ..., z = 61)." |
| 62, 63 | 33, 34 | "(! = 62, \" = 63, ..." |
| 64..95 | open point F2 | "Special Characters (! to @): Mapped to values 62 to 95 (! = 62, \" = 63, ..., @ = 95)." |
| 96..255 | open point F3 | not mentioned |

## Open points

"Unjudged: yes" = a checker must not count a difference here as a fault.

| Id | What task.md leaves open | Choices that all satisfy the text | Unjudged |
|---|---|---|---|
| T1 | Whether the outputs are registered (appear right after the edge that samples `start` = 1, as in the table above) or follow `start` combinationally in the same cycle. The text says both "in the same cycle" and "immediately after `start`", and the two "Actual" tables number their cycles differently (see decision.md). | (a) registered, table above; (b) combinational: outputs present while `start` = 1, before any edge. | yes for a pure shift of the whole schedule by this choice. Still judged under both: all 8 values together, for one cycle only, `valid` = 1 exactly with them, `ready` = 0 exactly then, zeros / `valid` 0 / `ready` 1 afterwards. |
| R1 | Reset: name, polarity, synchronous or asynchronous, and the output values during and right after reset. No sentence mentions a reset. | `ascii_out` = 0, `valid` = 0, `ready` = 1 (model's choice); or `ready` = 0 until some edge after reset; other values. | yes: all outputs while reset is active. After reset and before the first operation: `ready` = 1 is implied by "should deassert" (S3/S4) and may be judged from the edge at which the stimulus first gives `start` = 1; `valid` and `ascii_out` before the first operation are not stated — unjudged. |
| B1 | `start` = 1 at edge 1 (while `ready` = 0), which includes `start` held high for several cycles. | ignored (model's choice; a held start is then accepted again at edge 2); accepted at edge 1 back to back; anything else. | yes: all outputs from edge 1 until the next operation accepted from idle. Stimuli should give `start` for one cycle and wait for `ready` = 1. |
| B2 | `char_in` changing while `start` = 0 | no effect is the only reading consistent with S5/S6 | no (judged: outputs stay 0) |
| F2 | ASCII value for codes 64..95. The line is contradictory: `!`..`@` are 32 characters (ASCII 33..64) but 62..95 are 34 codes; contiguous from `!` = 62 gives `@` = 93, the text says `@` = 95; the range also contains the digits `0`..`9`, which already have codes 0..9. | (a) contiguous: ASCII = code - 29 for 62..95 (then 93 -> `@`, 95 -> 66); (b) `@` = 95 -> 64 with some other assignment of 64..94; (c) digits left out of the special range (22 characters). | yes for codes 64..95. Codes 62 and 63 are judged (33, 34). The example `@` -> 64 can be reproduced only if the stimulus encodes `@` according to the same reading as the RTL. |
| F3 | ASCII value for codes 96..255 | any | yes |
| W1 | Width of one `ascii_out` element | 7 bits ("typically in the range of 0 to 127") or 8 bits | yes for the width; values are compared as integers |
| W2 | How array index maps to the port bits (packed / unpacked, where index 0 sits) | any, as long as `ascii_out[i]` comes from `char_in[i]` | yes for the mapping; the same order on input and output is judged |
