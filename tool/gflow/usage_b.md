# The libraries of this order

Import in your own script:

```python
import sys
sys.path.insert(0, "/code/lib"); sys.path.insert(0, "/code/work/model")
import sigdump, piececheck
import ref_model as ref                      # the reference model: its functions are the references
from svvec import *
mod = sigdump.load_model("/code/work/rtl_model.py")   # mod.RtlModel is the class
```

## piececheck: compare a piece or a step of the design with a function of the reference model

```python
record = ...                                          # the step record of the reference model: its notes name the function that returns it
inputs = piececheck.befores(record, "StepName")       # the states before each step of this name in the record
inputs += [...]                                       # and at least 20 random ones, in the form of the reference model

r = piececheck.against(mod.RtlModel(fix="all"), "SignalBefore", "SignalAfter", ref.StepFunction, inputs,
                       place="rows as written", name="StepName")
print(piececheck.text_against(r))   # | StepName | SignalBefore | SignalAfter | agree (29 inputs) |  or the first difference
```

- `hold`: the signal that holds the input; for a piece that reads several signals, a dict
  `{signal: function(input) -> its value}` built from functions of the reference model, e.g.
  `{"PartA": lambda s: [[ref.f(b) for b in row] for row in s], "PartB": ...}`.
- `read`: the signal read after one `step()`. `ref`: the function of the reference model for this piece or step.
- `place`: how an input of the reference model is put in the design's array: `"rows as written"`, `"rows and columns exchanged"`,
  `"as written"`, `"reversed"`, or your own function. `take`: the way back (default: the inverse of `place`).
- `inputs_ports`: the ports driven at the edge, `{port: value}`, or a function `input -> {port: value}` when a port carries the input (for a piece whose input is a port, `hold` is `{}`).
- `place`: when it is not given, the arrangement of /code/work/arrangement.json is used (skill, point 3) for the values of its shape; a word, a whole key or a port value is passed as it is. A different arrangement is printed as such.
- `start="StateReg"`: the register set to the input before the step (not held): read the same register to compare one whole step() from state to state.
- An output port can be read like a signal (`read="OutPort"`, with `start=` for the register that drives it).
- `state={"count_ff": 2}`: registers set before the step (names as sigdump prints them), or a function `input -> {register: value}`. Each input runs on a fresh copy of the model.
- An element the design leaves unknown prints as `x` and differs.
- If `step()` never reads a held signal (the model computes the read signal from other values), `text_against` says so: that row compares no piece.
- Every comparison of `against` is added to /code/work/against_log.jsonl (what was compared, the switches on, the result); the host reads it.

From port to port (skill, point 5), with the arrangement of /code/work/arrangement.json:

```python
to_port = lambda b: int.from_bytes(bytes(b), "big")          # how the bytes sit on a port: the interface of the top, section on the data at the ports
a = piececheck.against(mod.RtlModel(fix="all"), {}, "StateReg", ref.LoadFunction, byte_inputs,
                       inputs_ports=lambda b: {"start": 1, "InPort": to_port(b)}, name="in")
b = piececheck.against(mod.RtlModel(fix="all"), {}, "StateReg", one_step, inputs, start="StateReg",
                       state={"count_ff": 5}, name="one step()")        # one_step: the functions of the reference model between the two states
c = piececheck.against(mod.RtlModel(fix="all"), {}, "OutPort", lambda s: to_port(ref.UnloadFunction(s)), inputs,
                       start="StateReg", name="out")
```

One piece with values you choose (to print the operands of a part, point 6 of the skill):

```python
r = piececheck.run(mod.RtlModel(fix=()), hold={"SignalBefore": a}, read=["PieceOut"], state={})
r["read"]["PieceOut"]          # nested ints, None = a bit is X
r["writes_ignored"]            # {held signal: writes not applied}; 0 = step() does not write it: the piece reads another signal
```

A signal of a submodule is named with a dot: `"sub.reg_ff"`.

## basecheck: the model with no switch is still the RTL as written

```
python3 /code/lib/basecheck.py          # last line: "no difference" or "edges with a difference: N"
```

Run it after every change of rtl_model.py.

## sigdump: one edge from a state you choose (when piececheck is not enough)

```python
m = mod.RtlModel(fix="all")
sigdump.set_state(m, {"count_ff": 3, "data_ff": [[0x12, ...], ...]})
rec = sigdump.step_once(m, {"start": 1}, None)     # rec["signals"]["PieceOut[0][1]"] is a V after the edge; rec["before"] before it
```

## svvec: the values of the model

The model computes with `V` (a width, the bits, which bits are unknown); write a switch in the form of the code around it.

- `V(width, value)`, `X(width)`; `v.int()` (raises on an X bit), `v.int_or_none()`, `v.hex()`, `v.is_known()`
- `sel(v, "-:", base, width, line)`, `bit(v, i, line)`, `put(...)`, `cat([...], width, line)`, `fit(v, width, line)`
- `band bor bxor bnot`, `add sub`, `shl shr`, `eq ne lt`, `mux(c, a, b)`, `true(c)` for an `if`

The full text of each library is at the top of its file in /code/lib; read it only for a function this page does not show.
