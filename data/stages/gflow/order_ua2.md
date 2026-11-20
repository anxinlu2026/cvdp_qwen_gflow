You are working in /code.

Files (read-only):
{FILES}

Files from earlier orders (you may change them): /code/work/rtl_model.py (a class `RtlModel(fix=())`, a Python translation of the RTL as written, cut into pieces, with switches for the faults found so far), /code/work/interface.json, and the reports of the earlier orders in /code/work (block_check_*.md: the pieces checked alone against the specification; edge_check_*.md with their scripts: what one edge stores in each control state; unit_check_*.md where they exist: modules below that were checked as units).
{FACT}
From the reports and scripts of other modules, this order needs only what such a module gives the module above (the end of its unit_check report); the one-edge script of this module is run or imported; its text is read only where it must be changed.

In this order you can read files, write files in /code/work, and run commands with the shell and python3. There is no network and no Verilog simulator. Use only these files. The skills check-unit-operation, check-one-edge, check-pieces-against-spec and sv-semantics describe the method; read them first. This order is the second half of part A of the skill check-unit-operation (A4, A5). The first half is in /code/work/{REPORT} under "Part A, checker"; the walk checker is /code/work/{SCRIPT} (run it first and read its print).

Task: the RTL is not verified and may contain faults. For {SCOPE}, driven at its own ports: for each point the walk checker reports as failing, find the statement that decides it and prove it with a switch, until the checker prints that every point holds in every case. The data values are not judged in this order (the next order does that). The specification is /code/task.md with the files in /code/docs; for the handshake at the ports of the top module also what the testbench in /code/verif does, and for a module below what the module above reads from it.

1. Run the checker with all switches of the earlier orders on; list the failing points, the earliest in the walk first.
2. For one failing point at a time: the row of the table, the candidate places, each as a switch; run the checker with each candidate and choose from the prints (A4). With no switch on, RtlModel still does what the RTL as written does.
3. When a kept switch changes what an edge stores or which control values are walked, run the one-edge script again and bring it up to date.
4. If the checker itself is wrong about a point (it does not measure what A5 says), correct the checker, say so in the report, and run it again with every kept switch.

Keep /code/work/{NOTES} while you work: after each run that settles something, append one line (what was run, what it showed, what follows from it). If the order is cut off, the work is continued from this file.

Write the result in /code/work/{REPORT}, under a heading "Part A, switches": for each failing point the row, the candidates with the checker's lines for each, the switch that was kept with the RTL file, line and change; then the print of the checker with all switches on. Keep the class attribute `SWITCHES` of RtlModel complete. End the report with a list "run again": the exact commands (script and arguments) that reproduce the results of this report, each with the last line it prints.

When this is written in {REPORT} and the checker prints that every point holds or has no requirement in every case, create the empty file /code/work/DONE. If points still fail when the time is nearly over, write which and create DONE. An order ends after {MINUTES} minutes.
