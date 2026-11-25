# order_reading.md — reading of the key-expansion check order

This file is a *reading* of the order given in the cell (the text between the two
lines of dashes). It does not carry the order out. It has three parts:
(1) the order in my own words, (2) how I would carry it out, (3) what is not clear.

The order's scope is the module `aes128_key_expansion` (rtl/aes128_key_expansion.sv)
plus the `sbox` module it instantiates (rtl/sbox.sv), which itself instantiates nothing.
`inv_sbox` is **not** in this scope (it is instantiated by the top `aes128_decrypt`, not by
the key-expansion module).

---

## 1. The order in my own words

The RTL is unverified and may contain faults. Check the pieces of `aes128_key_expansion`
(and its `sbox` instances) one by one against the specification, and locate and prove any
fault inside each piece. Each piece is judged **alone**: the same inputs go into the design's
piece and into the reference-model function for it, and the outputs are compared. Also judge
the pieces of the **same `step()`** together, and the key expansion **as a unit** if it needs
several cycles to finish. What is *not* judged here: which cycle a piece is used in, and how the
steps of the whole operation follow one another over several `step()` calls — that is a later order.

The golden reference is the reference model in `/code/work/model/` (`ref_model.py`), whose
functions were checked against the spec's examples (per `ref_model_notes.md` and the host's run
of `ref_check.py`). The "Data at the ports" section of `top_interface.md` defines the byte
arrangement on the ports.

Required steps, in order:

1. **Write `notes.md` first** with the data arrangement inside the design: for each data array
   of the scope, which index is which spec index (row / column / word / byte), and the pieces
   and lines that decide it. If `/code/work/arrangement.json` exists, keep what it gives and add
   only the arrays this scope does not give; if it does not exist, write it. Then list the pieces
   of the scope and the reference-model function each one matches.
2. **Compare** each piece, and each spec step the scope computes run as one, with the matching
   reference-model function, using `piececheck.against`. If the scope has pieces that bring data
   in and take it out, also check the port-to-port data path.
3. **For each piece that differs:** locate the first wrong part and prove it with a switch in
   `RtlModel` (one operand / index / condition / constant / statement-position change). With no
   switch on, `RtlModel` must still do what the RTL as written does. Keep a class attribute
   `SWITCHES` (a dict from every switch name to its RTL file, line and change);
   `RtlModel(fix="all")` turns all switches on.
4. **Keep `notes.md` live:** after each run that settles something, append one line (what was
   run, what it showed, what follows from it). If the order is cut off, work continues from it.
5. **Write `/code/work/block_check_1.md`:** the table of pieces (lines, matching ref function,
   agree/differ); the table of spec steps run as one; for a multi-cycle unit, the table of its
   parts per cycle; for each differing piece, the first wrong part and the operand table; and
   each switch with its RTL line, the change, and the values without and with it.
6. **When `block_check_1.md` is written and `rtl_model.py` has the switches, create the empty
   file `/code/work/DONE`.** The order ends after 45 minutes.

---

## 2. How I would carry it out (steps in sequence)

### Step A — Read (done for this reading task; re-read as needed in the real order)
- `/code/lib/usage.md` — how to use `svvec`, `sigdump`, `piececheck`, `basecheck`.
- skills `check-pieces-against-spec` and `sv-semantics` — the method (read first).
- `/code/task.md` — the spec text.
- `/code/work/spec/top_interface.md` — port byte arrangement ("Data at the ports").
- `/code/work/model/ref_model.py` + `ref_model_notes.md` — the golden functions and which checks passed.
- `/code/rtl/aes128_key_expansion.sv` and `/code/rtl/sbox.sv` — the RTL of the scope.
- `/code/work/rtl_model.py` — current `RtlModel` / `KeyExpansion`.
- `/code/work/interface.json` — top ports.

### Step B — Write `/code/work/arrangement.json` (it does **not** exist yet, so write it)
Map each data array of the scope to spec indices, with the deciding pieces/lines as the basis:
- `expanded_key_ff[1408]` → words `w[0..43]`, word k = bits `[k*32 .. (k+1)*32-1]`.
  Basis: lines 111–113 (`expanded_key_nx = {valid_key, step_key[0..9]}`) and the select bases in
  lines 100, 101, 103–106.
- `valid_key[128]` → `w[0..3]` (the key) when `i_start`; else the top 128 bits of
  `expanded_key_ff` (feedback). Basis: lines 115–121.
- `step_key[i][128]` → four words `w[4i+1 .. 4i+4]`. Basis: lines 103–106.
- `RotWord[i][32]`, `SubWord[i][32]`, `RconXor[i][32]` → intermediate words of the schedule.
  Basis: lines 100, 101, 79–97.
- `sbox` `i_data[8]` / `o_data[8]` → one byte. Basis: `sbox.sv` lines 3–262.
Record the basis in the file's `"basis"` field. (Note: key-expansion data is *words/bytes*, not a
4×4 state, so "row/column" do not apply here — see Part 3.)

### Step C — List the pieces and match each to a reference-model function (skill points 2, 3)
From `rtl_model.py` `KeyExpansion` + `aes128_key_expansion.sv`:
- `Rcon[0..9]` (lines 62–71) — constants; task says "previously tested, no errors" → likely excluded (flag it).
- `RotWord[i]` (line 100), i=0..9 → `ref.RotWord`.
- `SubWord[i]` via the 4 `sbox` instances (lines 79–97), i=0..9 → `ref.SubWord`; each `sbox` byte → `ref.SBOX_byte`.
- `RconXor[i]` (line 101), i=0..9 → part of `ref.KeyExpansion` (XOR with Rcon); no single ref function, so build it from `ref.RotWord`/`ref.SubWord`/`RCON` and say so.
- `step_key[i]` (lines 103–106), i=0..9 → the words `w[4i+1..4i+4]` of `ref.KeyExpansion`.
- `expanded_key_nx` (lines 111–113) → full `ref.KeyExpansion` output (44 words).
- `valid_key` / `input_data` (lines 115–121) → key loading (`w[0..3]`).
- `reset_regs` / `always_ff` (lines 39–56) → register update + counter; control only, no spec function.
- `o_expanded_key`, `o_done` (lines 33–34) → outputs.
- `sbox.sv` case (lines 3–262) → `ref.SBOX_byte`.

### Step D — Compare each piece with `piececheck.against` (skill points 4, 5)
- Inputs: `piececheck.befores(record, "KeyExpansion...")` from the ref model's step record
  (`aes128_decrypt_with_steps`) **plus ≥20 random inputs** in the ref model's form.
- Per piece, hold the signal(s) that carry the input, read the output signal, give the matching
  `ref` function, and set `place` from `arrangement.json`:
  - `sbox`: hold `i_data`, read `o_data`, `ref=ref.SBOX_byte`.
  - `RotWord[i]`: hold the `expanded_key_ff` word it reads, read `RotWord[i]`, `ref=ref.RotWord`.
  - `SubWord[i]`: hold `RotWord[i]`, read `SubWord[i]`, `ref=ref.SubWord`.
  - `RconXor[i]`: hold `SubWord[i]`, read `RconXor[i]`, `ref` = a function built from `ref.RotWord`/`ref.SubWord`/`RCON`.
  - `step_key[i]`: hold `expanded_key_ff` + `RconXor`, read `step_key[i]`, `ref` = the corresponding words of `ref.KeyExpansion`.
  - `expanded_key_nx`: hold `valid_key` + `step_key[0..9]`, read `expanded_key_nx`, `ref=ref.KeyExpansion` output.
  - `valid_key`: hold `i_key` with `i_start=1`, read `valid_key`, `ref` = key loading.
- Print `piececheck.text_against(r)` for each; append one line to `notes.md` per run (what was run, what it showed, what follows).
- If the scope has load/unload pieces (`valid_key` brings the key in; `o_expanded_key` takes the schedule out), also do the **port-to-port** path (skill point 5): drive `i_key`, read `expanded_key_ff`/`o_expanded_key`, compare to `ref.KeyExpansion`.

### Step E — Key expansion as a unit, if it needs several cycles
- Determine how many cycles `aes128_key_expansion` takes (read the `key_exp_steps_ff` counter logic; run with `sigdump`).
- If multi-cycle: run from the start condition (`i_start=1`, `i_key` set) and compare after each cycle, part by part (each word/byte), using `sigdump.set_state` + `sigdump.step_once` (or `piececheck` with `start=`/`state=`). Record which parts are right after which cycle in `notes.md`.

### Step F — For each differing piece, locate and prove with a switch (skill points 6, 7)
- Find the first wrong part (first cycle, first element).
- Use `piececheck.run` to print the operands of the statement computing that part; compare each operand to the ref's operand.
- Identify the statement reading the wrong operand (wrong index/element/bit) or giving a wrong result from right operands.
- Add a switch in `rtl_model.py`: change one operand/index/condition/constant/statement-position, guarded by `if "name" in fix`; add the entry to `SWITCHES` (name → {RTL file, line, change}).
- Re-run with `fix="all"`; if the part is now right, keep the switch, else remove it; move to the next wrong part.
- After every change, run `python3 /code/lib/basecheck.py` and confirm it still says "no difference" (i.e. `RtlModel()` with no switch still matches the RTL as written).

### Step G — Write `/code/work/block_check_1.md`
- Table of pieces (lines, matching ref function, agree/differ).
- Table of spec steps run as one (step, signal held, signal read, agree/differ).
- For a multi-cycle unit: table of its parts per cycle.
- For each differing piece: the first wrong part + operand table.
- Each switch: RTL line, the change, and the values without and with it.

### Step H — Create `/code/work/DONE` (empty) once `block_check_1.md` is written and `rtl_model.py` has the switches.

**Library functions used:** `piececheck.against`, `piececheck.befores`, `piececheck.text_against`,
`piececheck.run`; `sigdump.load_model`, `sigdump.set_state`, `sigdump.step_once`; `basecheck` via
shell (`python3 /code/lib/basecheck.py`); `svvec` `V`/`X`/`sel`/`bit`/`put`/`cat`/`bxor`/`add`/`shl`/
`eq`/`ne`/`gt`/`lt`/`ge`/`land`/`lor`/`true`.

---

## 3. What is not clear

Quoted sentences that are unclear, ambiguous, contradictory, or redundant, plus things the order
does not say but I would need to know.

### Ambiguities / contradictions in the order's text

1. *"the module aes128_key_expansion with the modules it instantiates that instantiate nothing (sbox), piece by piece, and as a unit where it needs several cycles to finish."*
   - Does `aes128_key_expansion` finish in **one** clock edge or **several**? The RTL's
     `always_comb main_operation` computes all ten `step_key[i]` in a single combinational pass from
     `expanded_key_ff`, which looks like one cycle; but the `key_exp_steps_ff` counter (lines 44–53)
     shifts left over several edges, which looks like multi-cycle. "as a unit where it needs several
     cycles to finish" does not say how many cycles, or whether this clause even applies here.

2. *"What the design computes in one step() of RtlModel (one clock edge) is judged by this order, ...; in which cycle a piece is used and how the steps of the whole operation follow one another over several step() calls is judged by a later order."*
   - This **tensions** with clause 1 ("as a unit where it needs several cycles to finish"). If the key
     expansion is a multi-cycle unit, this order is told to check it "as a unit," yet cross-cycle
     sequencing is "a later order." The boundary between "the multi-cycle unit check (this order)" and
     "how the steps follow over several step() calls (later order)" is not drawn.

3. *"The specification is /code/task.md."* and *"the pieces are judged against these two"* (task.md + the "Data at the ports" section of top_interface.md).
   - `task.md` is a **debugging task description**, not a formal spec; the golden reference model was
     written from **FIPS 197** (per `ref_model_notes.md`). The skill (point 4) says the reference is
     "the function of the reference model," but the order says "judged against these two." Is the golden
     the reference model, task.md, or both? They could disagree.

4. *"the section 'Data at the ports' of /code/work/spec/top_interface.md defines the data at the ports; the pieces are judged against these two."*
   - That section describes the **top module's** ports (`i_data`, `o_data`, `i_key`), not
     `aes128_key_expansion`'s own ports (`i_key`, `o_expanded_key`, `o_done`). For a port-to-port check
     of the key-expansion scope, which ports and which byte arrangement apply?

5. *"if the scope has the pieces that bring the data in and take it out, also the data path from port to port (point 5)."*
   - Does `aes128_key_expansion` have load/unload pieces? It has `input_data` (`valid_key` from
     `i_key`) and `o_expanded_key`. But the "data at the ports" arrangement is defined for the **top**
     module. Is the port-to-port path for key-expansion's own ports, or the top's? Unclear which.

6. *"If /code/work/arrangement.json exists, what it gives is used and not changed, and the data arrays of this scope that it does not give are added to it; if it does not exist, write it (skill, point 3)."*
   - `arrangement.json` does **not** currently exist (verified), so I would write it. But skill point 3
     says "The order that first matches a piece that computes along rows or columns to the reference
     model writes it." Key expansion has **no state matrix** (it works on words, not rows/columns), so
     it is unclear whether *this* order is the one that owns/creates `arrangement.json`, or whether the
     file is meant for the top module's state and is written by a different order. What exactly goes in
     `arrangement.json` for a word-based scope?

7. *"Write first in notes.md the arrangement of the data inside the design: which index of each data array of the scope is which index of the specification (row, column, word, byte), ..."*
   - For key expansion the data is **words/bytes**, not a 4×4 state, so "row" and "column" do not
     apply. Is "(row, column, word, byte)" generic language to be ignored where inapplicable, or does it
     imply key expansion should be expressed in row/column terms?

8. *"Keep in RtlModel a class attribute `SWITCHES`: a dict from every switch name to the RTL file, line and change; `RtlModel(fix="all")` turns all on."*
   - The current `KeyExpansion`/`RtlModel` in `rtl_model.py` has **no** `SWITCHES` attribute and no
     switch mechanism — this must be added. Also: "turns all on" — does `fix="all"` enable every entry
     in `SWITCHES`, or only the switches for pieces that differ? And what is the **naming convention**
     for switch names (e.g. `rotword_0`, `step_key_3`)? Not specified.

9. *"When block_check_1.md is written and rtl_model.py has the switches, create the empty file /code/work/DONE."*
   - This order (the future one) creates `/code/work/DONE`, and **this reading-order also** creates
     `/code/work/DONE` (same path). If both run, the DONE from this reading task would be overwritten by
     the real check order (or vice versa). The two orders share one DONE file with no way to tell them
     apart.

### Things the order does not say but I would need to know

- **How many clock cycles** `aes128_key_expansion` takes, and (if multi-cycle) which `step_key[i]` is
  produced per cycle. The RTL computes all ten steps combinationally but drives a shifting counter; the
  order does not resolve this, and it decides whether Step E (multi-cycle unit) applies.
- **Whether `Rcon[0..9]` (lines 62–71) is in scope.** `task.md` says "the Rcon values were previously
  tested, and they have no errors," which suggests exclusion, but the order does not explicitly exclude
  them as a piece.
- **The exact byte/word layout** of `expanded_key_ff[1408]` → `w[0..43]` and of each `step_key[i][128]`
  (four words) → `w[4i+1..4i+4]`. I would derive it from the select bases in lines 100/101/103–106, but
  the order does not give it.
- **Whether each of the 40 `sbox` instances is checked individually** (per byte) or only as the
  `SubWord` group. The order says "the modules it instantiates ... (sbox)" and "piece by piece," which
  leans toward per-instance, but does not state it.
- **The switch-name convention** for `SWITCHES` (see item 8 above).
- **Which ports** the port-to-port path uses (key-expansion's `i_key`/`o_expanded_key` vs the top's
  `i_data`/`o_data`) — see item 5.
- **What "a later order" will judge** in detail (cross-cycle sequencing), so I know what to deliberately
  leave out here.
