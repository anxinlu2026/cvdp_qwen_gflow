You are working in /code.

Files (all read-only):
{FILES}

In this order you can read files, write files in /code/work, and run commands with the shell and python3. There is no network and no Verilog simulator. Use only these files. The skills rtl-to-python and sv-semantics describe the method for this order; read them before you read the RTL.

Task: translate the RTL into Python exactly as it is written. The RTL is not verified and may contain faults. This order does not ask you to find or correct them: a line that looks wrong is translated as written.

1. Write /code/work/interface.json for the top module (the module that no other module instantiates): {"top": module name, "clock": clock port name or null, "reset": {"name": reset port name, "active": 0 or 1} or null, "inputs": {port name: width in bits, for every input port except the clock}, "outputs": {port name: width in bits}}. Parameters take their default values.
2. Write /code/work/rtl_model.py: a class `RtlModel` in the form of the skill rtl-to-python, built with the library svvec. Use only the Python standard library and svvec.
3. Write /code/work/translation_table.md: the list of pieces (name, RTL lines, signals read, signals assigned), then one row per assignment of the RTL: the RTL line number and text, the Python line, the bit ranges of its selects printed from the select helper's record, and whether the two are the same. Below the table, list every error the helpers raised while you worked: the RTL line, and what it turned out to be (a reading error that you corrected, X in the RTL, or a read before the write in the RTL).
4. Run RtlModel: reset, then input values of your choice for 40 calls of step. Put the printed outputs and control registers per call at the end of translation_table.md.
5. Write /code/work/stimulus.json: what the testbench in /code/verif does to the inputs, in the form that /code/lib/sigdump.py reads (described at the top of that file): every operation of the testbench in its order, each wait of the testbench as an `until`, and each value the testbench checks as an `expect`. Run `python3 /code/lib/sigdump.py /code/work/stimulus.json --summary` and put its print at the end of translation_table.md.

When the four files are written, create the empty file /code/work/DONE. After this order a simulator will run the RTL and RtlModel on the same random inputs and compare the outputs bit by bit, X included. An order ends after {MINUTES} minutes.
