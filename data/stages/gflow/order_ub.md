You are working in /code.

Files (read-only):
{FILES}

Files from earlier orders (you may change them): /code/work/rtl_model.py (a class `RtlModel(fix=())`, a Python translation of the RTL as written, cut into pieces, with switches for the faults found so far), /code/work/interface.json, and the reports of the earlier orders in /code/work (block_check_*.md: the pieces checked alone against the specification; edge_check_*.md with their scripts: what one edge stores in each control state; unit_check_*.md where they exist: modules below that were checked as units).
{FACT}
From the reports and scripts of other modules, this order needs only what such a module gives the module above (the end of its unit_check report); the one-edge script of this module is run or imported; its text is read only where it must be changed.

In this order you can read files, write files in /code/work, and run commands with the shell and python3. There is no network and no Verilog simulator. Use only these files. The skills check-unit-operation, check-one-edge, check-pieces-against-spec and sv-semantics describe the method; read them first. This order is part B of the skill check-unit-operation; part A is in /code/work/{REPORT}, and its walk checker is a script named there (run it after each switch of this order: the points of part A still hold).

Task: the RTL is not verified and may contain faults. For {SCOPE}, driven at its own ports, with all switches of the earlier orders on: find the faults that are left in the sequence of operations it applies to the data and in its results, and prove each with a switch. The specification is /code/task.md with the files in /code/docs; for the handshake at the ports of the top module also what the testbench in /code/verif does, and for a module below what the module above reads from it.

1. Write with a script the design's flat list from the walk and the one-edge table, and the specification's list (skill, B1 and B2). Compare the two files with listdiff.
2. For each difference: the control state, the statement that decides it and its switch (B3). With no switch on, RtlModel still does what the RTL as written does.
3. When the lists are the same: compare the results of every case with the reference model (B4).{STIM}

Keep /code/work/{NOTES} while you work: after each run that settles something, append one line (what was run, what it showed, what follows from it). If the order is cut off, the work is continued from this file.

Write the result in /code/work/{REPORT}, under a heading "Part B": the two flat lists side by side, the print of listdiff, each switch with the RTL file, line and change and the line it repairs, and the results of the cases against the reference. Keep the class attribute `SWITCHES` of RtlModel complete. End the report with a list "run again": the exact commands (script and arguments) that reproduce the results of this report, each with the last line it prints.

When part B is written in {REPORT}, listdiff reports the two lists the same and every result of a case that has a requirement equals the reference, create the empty file /code/work/DONE. If something still differs when the time is nearly over, write what and create DONE. An order ends after {MINUTES} minutes.
