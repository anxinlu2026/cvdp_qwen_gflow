---
name: check-pieces-against-spec
description: Find the faults inside the pieces of a hardware design with its executable Python translation: each piece is run alone on the same inputs as a reference written from the specification, the first wrong part is traced to one statement, and a switch that changes one place proves the fault.
---
Work in this order.

1. Principle. Reading gives a hypothesis; running gives a fact. A piece is judged alone: the same inputs go into the piece of the design and into a reference for that piece, and the outputs are compared. In which cycle the piece is used, and what the other pieces do, play no part in this judgement.

2. List the pieces of the scope from the translation: name, source lines, inputs, outputs, and kind (combinational, register, or a unit that needs several cycles to finish).

3. Say what each piece must compute: the step of the specification, with its sentence or section. A piece may be one step, a part of a step, or several steps. A design may group and order the steps differently from the text of the specification; that is its choice and not a fault. Pieces that only bring data into or out of the design's internal arrangement (load, unload, select a part) are taken as a pair: bringing in and taking out must give back the input, and the arrangement between them must be the one of the specification (its rows, columns, word and byte order), because the other pieces work on it.

4. Reference for each piece: a function written from the specification, or taken from a reference model written earlier. Before use it is run on the specification's worked example and compared with its intermediate values. Never change a reference to make a piece agree.

5. The model's values are `V` (library svvec); a reference works on integers. Give the piece `V(width, value)` and take the integer of its output with `.int()`. `.int()` raises when a bit is X: print the output with `.bin()` and find the operand that is X (point 6). Compare each piece with its reference and write one table row per piece (agree, or differ on how many inputs):
   - inputs: the values of the worked example and at least 20 random inputs;
   - a combinational piece is also called twice with the same inputs after different earlier inputs: a different result means that it reads something before it writes it in the same pass. A piece is called once per comparison. If it agrees only when it is called twice, that is a difference (point 6), not something to settle by a second call;
   - a unit of several cycles is run from its start condition and compared after each cycle, part by part (each word, byte or element): the table shows which parts are right after which cycle.

6. Locate inside each piece that differs, before you judge it:
   - find the first part of its output that is wrong (for a unit: the first cycle and the first part);
   - take the statement that computes this part, print every operand it reads, and compare each with the operand the reference uses for the same part. If a wrong operand is computed inside the piece, go to its statement and repeat. The place is the statement that reads the wrong operand (a wrong index, element or bit) or gives a wrong result from right operands.
   - "The structure is wrong" or "one change cannot repair it" is not a result. The result is the first wrong part and the operand table.

7. Prove the place with a switch. A switch changes one place: one operand, index, condition or constant, the position of a statement relative to a loop or to another statement, or one added condition that makes a statement not apply in a named control state (the same kind of change on parallel lines is one switch). It is written in the source's form, has a name in `fix`, and with no switch on the model is the design as written. Never replace a piece by its reference. With the switch on, compare again: if the part is now right the switch stays, and the next wrong part gets the next switch, until the piece agrees on all inputs; a switch that does not make its part right is removed.

8. Walk through the step record of the reference model. If the reference model can return a step record of the whole operation (one line for every time an operation is applied: name, parameter, value of the data after it), then after the pieces of the scope were compared and with all switches on:
   - match every line of the record with one piece of the design (point 3 says which step of the specification each piece is);
   - line by line: give the value of the record's line before to the piece and compare its output with the value of this line. The first line is compared with the piece that brings the data in, the last value goes through the piece that takes it out;
   - in one run: start from the input and give every piece its own output of the step before, to the end, and compare with the result of the reference model. A piece is called the way the model's step calls it, with the values it keeps from one call to the next;
   - the first line that differs names the piece and the parameter; this piece goes back to points 6 and 7;
   - the walk follows the order of the specification. In which cycle the design uses a piece is not judged here.

9. Report: the table of pieces, the table of the walk (point 8), and for each switch the source line, the change, and the values of the part without and with it. Say which statements rest on a run and which on reading only.
