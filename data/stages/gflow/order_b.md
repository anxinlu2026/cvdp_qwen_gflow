You are working in /code.

Files (read-only):
{FILES}

Files from earlier orders (you may change them): /code/work/rtl_model.py (a class `RtlModel(fix=())`, a Python translation of the RTL as written, cut into pieces), /code/work/interface.json, /code/work/translation_table.md, and the reports of earlier orders in /code/work.
{FACT}

In this order you can read files, write files in /code/work, and run commands with the shell and python3. There is no network and no Verilog simulator. Use only these files. The skills check-pieces-against-spec and sv-semantics describe the method for this order; read them first.

Task: the RTL is not verified and may contain faults. Check the pieces of this scope one by one against the specification, and locate and prove the faults inside them: {SCOPE}.
The specification is /code/task.md with the files in /code/docs. This order does not judge in which cycle a piece is used or how the whole operation is sequenced; a later order does that.

1. List the pieces of the scope and what each must compute (skill, points 2 and 3). If a method of the translation computes several named signals one after the other, first cut it into one method per signal without moving a statement, and check on random inputs that RtlModel gives the same outputs as before the cut (keep a copy of the file from before).
2. Write a reference for each piece and check it on the specification's worked example (point 4).
3. Compare each piece with its reference (point 5).
4. For each piece that differs: locate the place and prove it with a switch in RtlModel (points 6 and 7). With no switch on, RtlModel still does what the RTL as written does. Keep in RtlModel a class attribute `SWITCHES`: a dict from every switch name to the RTL file, line and change; `RtlModel(fix="all")` turns all on.
5. When every piece that differs has its switches: walk through the step record of the reference model with all switches on (skill, point 8). A line that does not agree goes back to points 3 and 4, until the whole walk agrees.

Keep /code/work/notes.md while you work: after each run that settles something, append one line (what was run, what it showed, what follows from it). If the order is cut off, the work is continued from this file.

Write the result in /code/work/{REPORT}: the table of pieces (lines, what it must compute, agree or differ), for a unit of several cycles the table of its parts per cycle, for each piece that differs the first wrong part and the operand table, and each switch with the RTL line, the change, and the values without and with it. If the reference model gives a step record: the table of the walk (each line of the record, the piece, agree or differ).

When {REPORT} is written, rtl_model.py has the switches and the walk through the step record agrees (where the reference model gives one), create the empty file /code/work/DONE. An order ends after {MINUTES} minutes.
