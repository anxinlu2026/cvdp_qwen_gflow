You are working in /code.

Files (read-only):
{FILES}

Files from earlier orders (you may change them): /code/work/rtl_model.py (a class `RtlModel(fix=())`, a Python translation of the RTL as written, cut into pieces, with switches for the faults found so far), /code/work/interface.json, and the reports of the earlier orders in /code/work (block_check_*.md: the pieces checked alone against the specification; edge_check_*.md with their scripts: what one edge stores in each control state; unit_check_*.md where they exist: modules below that were checked as units).
{FACT}
From the reports and scripts of other modules, this order needs only what such a module gives the module above (the end of its unit_check report); the one-edge script of this module is run or imported; its text is read only where it must be changed.

In this order you can read files, write files in /code/work, and run commands with the shell and python3. There is no network and no Verilog simulator. Use only these files. The skills check-unit-operation, check-one-edge, check-pieces-against-spec and sv-semantics describe the method; read them first. This order is the first half of part A of the skill check-unit-operation (A1 to A3): the walk checker and the tables. The model is not changed in this order.

Task: the RTL is not verified and may contain faults. For {SCOPE}, driven at its own ports: write the script that checks the walk of its control registers and its handshake, and run it on the model with the switches found so far. The data values are not judged (a later order does that); the checker only looks at whether a data register is kept or written, which it takes from the one-edge table for the control state of the edge. The specification is /code/task.md with the files in /code/docs; for the handshake at the ports of the top module also what the testbench in /code/verif does, and for a module below what the module above reads from it.

1. Write down the cases (skill, A1).{STIM}
2. Write /code/work/{SCRIPT}: `check(fix)` (fix: a list of switch names) runs every case from reset, writes the per-edge print of every case (control registers, handshake signals, for each data register whether it changed) to a file, and prints for every case and every point of A5 one line: holds, fails at edge N with the values at that edge, or no requirement with the reason (A2, A3). Called from the shell it takes the switches as its argument.
3. Run it with all switches of the earlier orders on. For each control register write its table from this run: one row for each value together with each condition its next value depends on, and the next value the design gives.

Keep /code/work/{NOTES} while you work: after each run that settles something, append one line (what was run, what it showed, what follows from it). If the order is cut off, the work is continued from this file.

Write the result in /code/work/{REPORT}, under a heading "Part A, checker": the cases, for each point of A5 where its requirement comes from (the sentence, the wait of the testbench, the module above, or no requirement), the table of each control register, the name of the file with the print of the checker, and the list of the points that fail with case and edge. No switch is written in this order.

When this is written in {REPORT}, create the empty file /code/work/DONE. An order ends after {MINUTES} minutes.
