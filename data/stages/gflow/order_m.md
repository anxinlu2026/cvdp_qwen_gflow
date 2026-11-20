You are working in /code.

Files (all read-only):
{FILES}

In this order you can read files, write files in /code/work, and run commands with the shell and python3. There is no network. Use only these files. The source of the design is not given in this order.

Task: write /code/work/ref_model.py: a reference model of what the specification asks, as your own reading of these files. It is used in later orders to check a design piece by piece, so it must be right before it is used. Use only the Python standard library.

1. One function for each operation the specification names (with the specification's name for it), working on plain Python values, and one function for the whole operation that is built from them: it takes the values of the module's data inputs and returns the values of its data outputs. Where the specification defines an arrangement of the data (rows, columns, word, byte and bit order), the functions use this arrangement and say so in a comment.
2. The function for the whole operation also has a form that returns a step record with the result (for example one more argument): a list with one line for every time an operation is applied, in the order of the specification. A line holds the name of the operation, its parameter (round, index, selection), and the value of the data after it. The first line is the input after it is brought into the arrangement the specification defines; the last line is the value before it is taken out. The data values are in the specification's arrangement; a comment says which.
3. Check every function on the worked examples of these files: the inputs, every intermediate value that is printed there, and the result. Run the checks with a script (/code/work/ref_check.py) that prints one line per example: the function, agree or differ. A function with no example in these files is listed as "no example". Where an example prints intermediate values, every line of the step record is checked against them.
4. The model gives values. It does not need to follow clock cycles; how many cycles a part takes is written down only where a sentence of the specification states it.

Write /code/work/ref_model_notes.md: the list of functions with the sentence or section of the specification each rests on; how the step record is called and what a line of it holds; the output of ref_check.py; what the specification states about timing and handshake (start, busy, done, reset), each with its sentence; and a list "Open points": every behaviour these files do not fix (the question, and "not stated"). Do not choose silently.

When ref_model.py and ref_model_notes.md are written and ref_check.py shows no "differ", create the empty file /code/work/DONE. An order ends after {MINUTES} minutes.
