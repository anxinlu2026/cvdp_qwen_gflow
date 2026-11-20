You are working in /code.

Files (read-only):
{FILES}

Files from an earlier order (you may change them): /code/work/rtl_model.py (a class `RtlModel`, a Python translation of the RTL as written), /code/work/interface.json, /code/work/translation_table.md.

In this order you can read files, write files in /code/work, and run commands with the shell and python3. There is no network and no Verilog simulator. The skills rtl-to-python and sv-semantics describe the method; read them first.

Task: RtlModel does not do what the RTL does. /code/work/sim_check.txt is the result of a simulator run of the RTL compared with RtlModel on the same inputs; /code/work/sim_check_case.json (if present) holds the inputs of the first case that differs and the outputs of the RTL per edge; /code/work/sim_check_signals.txt holds the values of the RTL's signals in the simulator just before and just after the edge of the first difference. Reproduce the difference with RtlModel, find the lines of the translation that do not do what the RTL text does, and correct them. Do not correct the RTL's own faults: the model follows the RTL as written.

Write what you changed at the end of /code/work/translation_table.md. When RtlModel gives the RTL's outputs on the case, create the empty file /code/work/DONE. An order ends after {MINUTES} minutes.
