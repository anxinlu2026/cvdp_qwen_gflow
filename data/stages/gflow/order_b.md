You are working in /code. You can read files, write files in /code/work, and run the shell and python3. There is no network and no Verilog simulator.

Read first: /code/lib/usage.md and the skills check-pieces-against-spec and sv-semantics.

Files:
- /code/rtl/: the RTL. It may contain faults.
- /code/work/rtl_model.py: RtlModel, a Python translation of the RTL as written. With no switch it does what the RTL does (checked with a simulator); `python3 /code/lib/basecheck.py` checks this again.
- /code/work/model/ref_model.py: the reference.{REF}
- /code/task.md and /code/work/spec/top_interface.md: the task text and the ports of the top module.
{FACT}
Scope: {SCOPE}

Task: find the faults in the pieces of the scope. A piece is right when it gives what the function of the reference model gives for the same input. Only what one step() computes is judged; the sequence over several step() calls belongs to a later order.

1. Write in notes.md and in /code/work/arrangement.json which index of each data array of the scope is which index of the data of the reference model. Entries already in arrangement.json are kept.
2. List the pieces and the function of the reference model for each.
3. Compare every piece with piececheck.against, then each step of the reference model that the scope computes, run as one (skill, point 5).{PORTS}
4. For each piece that differs: find the wrong line and prove it with a switch. `RtlModel.SWITCHES` is the dict {name: (file, line, change)} of every switch, also of a submodule; RtlModel(fix="all") turns every switch on.
After each run that settles something, add one line to notes.md.

Result: /code/work/{REPORT} with the table of the pieces (lines, function of the reference model, agree or differ) and, for each piece that differs, the first wrong part, the operands, the switch, and the values without and with it. Then create the empty file /code/work/DONE. Time limit: {MINUTES} minutes.
