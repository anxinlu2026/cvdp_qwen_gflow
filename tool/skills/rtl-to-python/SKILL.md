---
name: rtl-to-python
description: Translate a SystemVerilog design statement by statement into an executable Python model whose helpers fail by themselves when a line was read wrongly, and check the translation against the source text.
---
Work in this order.

1. Aim. The model does what the source as written does, faults included. One source assignment becomes one Python assignment with the same operands, indices, conditions and order. Do not replace a piece by a function you know (a standard operation, a helper written from a specification) and do not correct what looks wrong.

2. Form.
   - A Python class `RtlModel(fix=())`. `step(**inputs)` takes every input port of the top module except the clock by its name (a `V`) and returns a dict with every output port (a `V` of the library svvec). One call is one rising clock edge: compute the combinational signals from the current registers and inputs, then all next register values, then update all registers together; the outputs returned are the settled values right after the edge. For a module without a clock, one call is one evaluation. `fix` is for later orders (names of switches); nothing reads it yet.
   - Cut each module into pieces without moving a statement. A piece is one `always_ff` block, one continuous assignment or generate group, or one `always_comb` block; when a block computes several named signals one after the other, each consecutive part that computes one named signal is a piece (a loop nest stays whole in one piece). Each piece is a method of its own: it takes the signals it reads as arguments and returns the signals it assigns. `step` calls the pieces. A submodule is a class of its own in the same form.
   - Each vector is one `V` of its declared width (library svvec: the bits, and which of them are known); an unpacked array is a list of `V`. A register or variable that the source does not initialise starts as `X(width)`. Parameters are named constants; the source's loops keep their nesting, order and index names. Do not convert positions into word or byte numbers of your own, and do not reorder or merge loops.
   - Above each Python assignment: the source text copied from the file with a tool, and its line number.

3. Helpers: the library svvec. Every select, assignment to a part of a vector, concatenation, operation, `if` condition and `case` goes through a function of svvec (the text at the top of the library lists them). Each select, assignment to a part and concatenation carries the source line number. Do not write helpers of your own for these, and do not take the integer out of a `V` inside the model. The functions follow the simulator bit by bit, X included, and raise by themselves:
   - a select or an assignment to a part whose range leaves the vector; the range that was selected is recorded per line number (`ranges(line)`);
   - a concatenation whose widths do not add up to the width of the target;
   - a constant that does not fit the width; a narrower target is reached only through `fit`, where the source assigns to it;
   - a read of the marker `NW`. At the start of each pass over an `always_comb` block, every variable the block assigns as a whole is set to `NW`. A variable the block assigns part by part starts the pass with the value the previous pass left (`X(width)` before the first pass).
   - What a raise means. First, that your reading of the line may be wrong: open the line again and evaluate it with the parameter values (skill sv-semantics). If the reading is right, the source itself does this, and the model follows SystemVerilog at that line only, with a note: a select that leaves the vector is called with `outside="x"`; a variable that is read before it is written in the pass keeps the value the previous pass left instead of `NW`.

4. Check the translation against the source, not against a specification.
   - A table with one row per source assignment: source text, Python line, the bit ranges printed from the select helper's record (not typed), same or not. "Same" is read off the two texts; a rewritten expression is "not same".
   - Test with what the source states directly: a register loaded from an input holds that input after the edge; a field placed in a concatenation is found at its position; a copied table gives the source's entry.
   - A wrong overall result says nothing about the translation: a faulty design and a faulty translation both give wrong results.

5. Report every error the helpers raised and what each turned out to be: a reading error (corrected), X in the source, or a read before the write in the source.
