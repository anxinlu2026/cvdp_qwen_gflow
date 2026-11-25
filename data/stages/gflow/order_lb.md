You are working in /code.

Files (read-only):
{FILES}

Files from earlier orders: /code/work/rtl_model.py (a class `RtlModel(fix=())`, a Python translation of the RTL as written; its switches change the places of the faults that were found, `RtlModel(fix="all")` turns all on), and the reports and notes of the earlier orders in /code/work. Each report names its switches with the RTL file, line and change.
{FACT}

In this order you can read files, write files in /code/work, and run commands with the shell and python3. There is no network and no Verilog simulator. The skill sv-semantics describes how SystemVerilog evaluates; read it first.

Task: some switches of RtlModel that earlier orders kept have no RTL change in the book of the switches yet. Enter each of them in the book with its RTL change, with /code/lib/ledger.py (read the text at its top first, and the text at the top of /code/lib/rtlapply.py for the form of the edits). The RTL itself is not edited by hand: the library writes /code/work/rtl_changes.json and /code/work/rtl_fixed/ from the entries.

1. `python3 /code/lib/ledger.py apply` names the switches of the model without an entry. Take them in this order: the switches of the modules below first, then in the order in which they are written in the model (a switch that a later one builds on is before it).
2. One switch at a time. Read the switch in the model (what it does when it is on) and the lines of the RTL it names; write its edits in a JSON file; run
   `python3 /code/lib/ledger.py add SWITCH --file FILE --lines LINES --fact "kept in an earlier order: REPORT" --edits EDITS.json`
   and read what it prints for this entry and the changed lines. The edits are the whole RTL change of the switch: every statement the switch changes in the model has its edit (a switch that is one function in the model used by four statements of the RTL has four changed statements; the code of the model decides, not the line numbers a report gives), and nothing that belongs to another switch. The new text has the form of the model code with the switch on, not the form of the lines it replaces: where the model has a branch (one expression per value of a loop variable, a condition), the new text has the same branch, and the number of lines of "new" need not be that of "old". Do not change the ports of the top module, and do not rewrite or reformat lines that no switch changes.
3. A switch whose change in the model uses something the RTL does not have at that place needs, in its edits, what gives the RTL this thing, with what the switch does kept as it is: a new register of the model (its declaration, its reset value, its update); a register of a module below that is not a port (a port, its assignment and its connection); a value after the edge (the condition on the values before the edge that is the same).
4. When `python3 /code/lib/ledger.py apply` prints "all edits applied" and "every switch of the model has one entry": create the empty file /code/work/DONE.

After this order the host runs a simulator on rtl_fixed/ and on RtlModel with the same switches, on the same random inputs, and compares the outputs, with all entries and with the entries one more at a time. If the order is cut off, `python3 /code/lib/ledger.py show` says which switches are entered. An order ends after {MINUTES} minutes.
