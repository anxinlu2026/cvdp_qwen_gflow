You are working in /code.

Files (read-only):
{FILES}

Files from earlier orders (you may change them): /code/work/rtl_model.py (a class `RtlModel(fix=())`, a Python translation of the RTL as written, cut into pieces, with switches for the faults found so far), /code/work/interface.json, and the reports of the earlier orders in /code/work (block_check_*.md: the pieces that were checked alone against the specification, with their references and switches; edge_check_*.md and unit_check_*.md where they exist: the same work of this order and the next for a module below).
{FACT}

In this order you can read files, write files in /code/work, and run commands with the shell and python3. There is no network and no Verilog simulator. Use only these files. The skills check-one-edge, check-pieces-against-spec and sv-semantics describe the method; read them first.

Task: the RTL is not verified and may contain faults. For {SCOPE}, driven at its own ports: find by runs of one clock edge what every register takes in every control state, and check that the pieces computed together in one edge give what they give alone. This order does not run a whole operation and does not judge whether a control state should be reached; the next order does that with the table of this one.

1. List the registers and the cases (skill, point 1).
2. Write /code/work/{SCRIPT}: it runs one edge per case and prints the table (points 2 and 4). It also has the function of the skill's point 5 (for a control state and the inputs: what each data register takes); the next order uses it.
3. Compare the pieces of the chain in each case with their references, on a new model and after another edge (point 3). Each piece that differs: the statement and its switch. With no switch on, RtlModel still does what the RTL as written does.

Keep /code/work/{NOTES} while you work: after each run that settles something, append one line (what was run, what it showed, what follows from it). If the order is cut off, the work is continued from this file.

Write the result in /code/work/{REPORT}: the cases, the table, the list of rows left for the next order, and each switch with the RTL file, line and change and the values without and with it. Keep the class attribute `SWITCHES` of RtlModel complete (every switch name, also those of the earlier orders, to the RTL file, line and change); `RtlModel(fix="all")` turns all on.

When {REPORT} is written and {SCRIPT} prints the table, create the empty file /code/work/DONE. An order ends after {MINUTES} minutes.
