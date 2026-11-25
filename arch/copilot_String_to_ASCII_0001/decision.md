# decision.md — String_to_ASCII_Converter

## 1. Interface type

(e) one start signal, an end signal some edges later — here with a fixed latency of one cycle, a `valid` flag that marks the cycle in which the result is on `ascii_out`, and a `ready` flag that is low while the operation runs. `ready` is a busy/idle status of the module, not a back-pressure signal that holds data back, so it is not (d).

Sentences:
- "When `start` is asserted: All 8 characters from the input `char_in` should be processed simultaneously."
- "The `valid` signal should be asserted in the same cycle, and `ready` should deassert until processing is complete."
- "When processing completes: The `ready` signal should assert to indicate readiness for new inputs. The `valid` signal should deassert."

## 2. Timed specification: provided

The main schedule is fixed by the text:
- latency: "The ascii_out array should contain the ASCII values corresponding to all input characters within 1 clock cycle"
- result held for one cycle, then cleared: "it should be reset to all zeros after processing is completed"; Test Sequence, column "Expected ascii_out": cycle 1 = [65, 49, 98, 33, 67, 51, 100, 64], cycles 2..5 = [0, 0, 0, 0, 0, 0, 0, 0]
- `valid` rises with the result and falls at completion: "The `valid` signal should be asserted in the same cycle"; "The `valid` signal should deassert."
- `ready` falls with the start and rises at completion: "**ready**: Should deassert during processing and assert immediately after completion."

Not fixed, listed as open points and not invented: the reset, inputs given while busy, registered or combinational outputs (see schedule.md, "Open points").

Files written for this: top_interface.md, schedule.md, top_model.py.

## 3. Function

Computable from the text for codes 0..63: sections "Custom Encoding Scheme" (code -> character) together with the definition of ASCII in the first paragraph (standard: ASCII, character -> 7-bit code). It is a fixed table look-up, no named algorithm beyond ASCII itself.
- 0..9 -> 48..57, 10..35 -> 65..90, 36..61 -> 97..122, 62 -> 33, 63 -> 34.

Not computable for codes 64..95: the special-character line contradicts itself (below), so the missing piece is the code of each special character between `"` and `@` (and whether `@` is 93 or 95). Nothing is said for codes 96..255.

## 4. Open points (details and choices in schedule.md)

- T1 registered or combinational outputs relative to `start` (pure shift of the schedule) — unjudged as a shift
- R1 reset: name, polarity, kind, output values during / right after reset — unjudged
- B1 `start` = 1 while `ready` = 0, including `start` held high — unjudged
- B2 `char_in` changing with `start` = 0 — judged, no effect
- F2 ASCII value for codes 64..95 — unjudged
- F3 ASCII value for codes 96..255 — unjudged
- W1 width of an `ascii_out` element (7 or 8 bits) — unjudged
- W2 mapping of array index to port bits — unjudged; same order in and out is judged
- Clock and reset port names are not in the text.

## 5. Contradictory or unclear in task.md

1. "Special Characters (! to @): Mapped to values 62 to 95 (! = 62, \" = 63, ..., @ = 95)." — `!`..`@` is ASCII 33..64 = 32 characters, 62..95 is 34 codes; contiguous from `!` = 62 puts `@` at 93, not 95. The ASCII range `!`..`@` also contains the digits, which already have codes 0..9 ("Digits (0-9): Mapped to values 0 to 9."), so the count fits neither with nor without them (32 or 22, not 34).
2. "The `valid` signal should be asserted in the same cycle" against "**valid**: Should assert immediately after `start`." and "1 (asserted immediately after start)" — same cycle as `start`, or the cycle after it.
3. The two "Actual" tables of the same stimulus disagree by one cycle: Test Sequence cycle 1 = "[0, 0, 0, 0, 0, 0, 0, 0]", cycle 2 = "[65, 0, 0, 0, 0, 0, 0, 0]"; Example Test Case cycle 1 = "[65, 0, 0, 0, 0, 0, 0, 0]". So the meaning of "Clock Cycle 1" relative to the edge that samples `start` is not uniform in the text.
4. In the Test Sequence the columns "valid" and "ready" are not marked expected or actual. They read 1 / 0 in all five rows, which fits the actual (faulty) behaviour; taken as expected they would contradict "The `valid` signal should deassert." and "The `ready` signal should assert" for cycles 2..5. Row 1 (1 / 0) agrees with the expected behaviour.
5. "**ready**: 0 (deasserted during processing, asserted after completion)" listed under "Expected Output" gives one value for a signal that changes; read with "Expected Behavior" it is 0 in the result cycle and 1 after.
6. "ASCII ... typically in the range of 0 to 127" — width of an `ascii_out` element not stated.
7. "A "string" is a sequence of characters represented in various encodings, such as UTF-8 or custom formats." — no requirement.
8. No reset is mentioned anywhere; "reset to all zeros after processing is completed" is about clearing `ascii_out`, not about a reset port.

## 6. Told by the task about the faults

Not used as requirements:
- "During testing, it was observed that the buggy RTL failed to produce all outputs simultaneously in a single clock cycle. Instead, it generates sequential outputs across multiple clock cycles, indicating a timing or design issue that affects the expected parallel conversion of the input string to its ASCII values."
- "1. The `ascii_out` values appeared sequentially across multiple clock cycles."
- "2. The `valid` signal remained asserted during this time, indicating ongoing processing instead of immediate completion."
- Test Sequence, column "Actual ascii_out" (and the valid / ready columns, see 5.4).
- "**Actual Output (spread across cycles):**" with its table (cycles 1..8, `ready` = 1 only in cycle 8).

States required behaviour as well, used as a requirement (S1):
- "Identify and fix the RTL bug to ensure that all outputs (ascii_out) are generated in parallel within a single clock cycle when the start signal is asserted."

## 7. Self-check

top_model.py, `python3 top_model.py`: SELF-CHECK PASS.
- Example used: the only example with values in task.md, "A1b!C3d@" -> [65, 49, 98, 33, 67, 51, 100, 64] (Test Sequence expected column, "Expected Output", "Example Test Case Behavior"). Five edges as in the Test Sequence: start = 1 at cycle 1, start = 0 in cycles 2..5; model gives the values with valid 1 / ready 0 after cycle 1 and zeros with valid 0 / ready 1 after cycles 2..5.
- task.md gives the characters, not the codes on `char_in`; the codes were produced with the encoding scheme. Run for both readings of the special-character line: `@` = 93 (contiguous) and `@` = 95 (as written); both give 64. With the contiguous reading code 95 gives 66, not 64 — this is open point F2.
- Also checked the codes named one by one in the text: 0, 9, A = 10, B = 11, Z = 35, a = 36, b = 37, z = 61, ! = 62, " = 63.
