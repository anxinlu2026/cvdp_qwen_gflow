"""The general flow for CVDP bug-fix problems (docs/GFLOW.md): orders A (translate the RTL to Python), B (check the pieces alone against the specification), C (control and sequence of the
whole operation), D (write the changes into the RTL). Each order runs in a new cell without a simulator; the files of the agent are carried from the run before.
Between the orders the host compares the RTL with the model in a simulator (tool/gflow/simcheck.py) and gives the result as a fact file; at the end the hidden harness grades rtl_fixed/.

usage:
  python3 -m orch.gflow prep  --pid PID                      (the visible files of the problem -> data/stages/gflow/<short>/)
  python3 -m orch.gflow run   --pid PID --tag T --step M|A|A2|B|C1|C2A|C2B|D|D2 [--carry RUN_TAG] [--scope TEXT] [--report NAME] [--fact TEXT] [--sim RUN_TAG] [--minutes N]
  python3 -m orch.gflow view  --pid PID --tag T              (unpack the agent's files of a run to <run>/view)
  python3 -m orch.gflow sim   --pid PID --tag T [--fixed]    (simcheck of the run's view: the RTL against RtlModel(); --fixed: rtl_fixed/ against RtlModel(fix="all"))
  python3 -m orch.gflow grade --pid PID --tag T              (the hidden harness on <run>/view/rtl_fixed)"""
import argparse
import hashlib
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import dataset, grade as grader
from . import support as s2
from .support import facts, sha
from .map_s3x_cell import IMAGE, S3Cell
from .run_order import run_order

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "stages" / "gflow"
OUT = ROOT / "data" / "pilot" / "gflow_results.jsonl"
SK = ROOT / "tool" / "skills"
sys.path.insert(0, str(ROOT / "tool" / "gflow"))
CONTEXT_LIMIT = 175000   # tokens; above about 170k the backend (64 GB machine) slows down and at 196k it stalled (h2-b2, f1-a2b): the order is cut and continued in a new cell
KEEP_REASONING = int(os.environ.get("GFLOW_KEEP_REASONING", "0"))   # with DROP_REASONING: characters from the end of the last answer's thinking that are still sent back (its conclusion and plan)
DROP_REASONING = os.environ.get("GFLOW_DROP_REASONING") == "1"   # trial: the proxy does not send the thinking of earlier answers back to the model
LIB = ROOT / "tool" / "gflow" / "svvec.py"
REPLAY = json.loads(Path(os.environ["GFLOW_REPLAY"]).read_text()) if os.environ.get("GFLOW_REPLAY") else {}   # dry run: {order name of the round: run directory whose files stand in for the agent's work}
LIB_TOOLS = [ROOT / "tool" / "gflow" / n for n in ("listdiff.py", "sigdump.py", "hsfacts.py", "stepfacts.py", "rtlapply.py", "ledger.py", "tasks.py", "basecheck.py", "portfacts.py", "piececheck.py")]   # in /code/lib of every cell that has the RTL; named in the order texts of the steps that use them
STEPS = {"M": ("order_m.md", [], 45),
         "A": ("order_a.md", ["rtl-to-python", "sv-semantics"], 60),
         "A2": ("order_a2.md", ["rtl-to-python", "sv-semantics"], 45),
         "B": ("order_b.md", ["check-pieces-against-spec", "sv-semantics"], 45),   # 75 -> 45 (f7-05): past ~45 min the prompt passed the cache limit (f7-04 b2p1, b2p2); a continuation starts short
         "C1": ("order_c1.md", ["check-whole-operation", "check-pieces-against-spec", "sv-semantics"], 75),
         "C2": ("order_c2.md", ["check-whole-operation", "check-pieces-against-spec", "sv-semantics"], 75),   # the undivided order (runs before 2026-11-16)
         "C2A": ("order_c2a.md", ["check-whole-operation", "check-pieces-against-spec", "sv-semantics"], 75),
         "C2B": ("order_c2b.md", ["check-whole-operation", "check-pieces-against-spec", "sv-semantics"], 75),
         "E": ("order_e.md", ["check-one-edge", "check-pieces-against-spec", "sv-semantics"], 60),      # per module, after B: what one edge stores in each control state
         "UA": ("order_ua.md", ["check-unit-operation", "check-one-edge", "check-pieces-against-spec", "sv-semantics"], 60),   # per module: the walk of the unit at its own ports
         "UA1": ("order_ua1.md", ["check-unit-operation", "check-one-edge", "sv-semantics"], 45),   # walk checker only, model unchanged
         "UA2": ("order_ua2.md", ["check-unit-operation", "check-one-edge", "check-pieces-against-spec", "sv-semantics"], 60),   # switches, candidates judged by the checker
         "T": ("order_t.md", [], 45),     # timed specification model of the top module, from the architecture's schedule and interface (no RTL)
         "UT": ("order_ut.md", ["check-unit-against-timed-spec", "check-one-edge", "sv-semantics"], 60),   # per module with a timed specification model: handshake and control by hsfacts, in place of UA1 and UA2


         "UB": ("order_ub.md", ["check-unit-operation", "check-one-edge", "check-pieces-against-spec", "sv-semantics"], 75),   # per module: sequence from walk x edge table, then values
         "D": ("order_d.md", ["sv-semantics"], 45),
         "D2": ("order_d2.md", ["sv-semantics"], 45),
         "DL": ("order_dl.md", ["sv-semantics"], 45),     # the list of changes; rtlapply writes the RTL (user decision 2026-11-19)
         "DL2": ("order_dl2.md", ["sv-semantics"], 45),
         # the book of the switches carries the RTL change of every switch; the host applies and simulates (user decision 2026-11-20)
         "LB": ("order_lb.md", ["sv-semantics"], 45),     # enter the switches of earlier orders with their edits
         "LF": ("order_lf.md", ["sv-semantics"], 45),     # correct the edits of the entry the host names
         "UD": ("order_ud.md", ["check-unit-by-step-record", "sv-semantics"], 60),   # per module with a step record: the data path by stepfacts part 1, with the edits of each switch in the book (named UW, then UX, before 2026-11-22; docs/NAMES.md)
         "UC": ("order_uc.md", ["check-unit-by-step-record", "sv-semantics"], 60),   # the control by stepfacts part 2 and the handshake by hsfacts, with the edits in the book (named UQ, then UY, before 2026-11-22)
         # a unit without a step record (no control walk through the steps of a reference): every output port, edge by edge, against the timed specification model
         "TN": ("order_tn.md", [], 45),   # T for a specification that marks what it does not fix: the model returns None there
         "UP": ("order_up.md", ["check-ports-against-timed-spec", "sv-semantics"], 60)}
ALIAS = {"LB": "DL", "LF": "DL2", "TN": "T"}   # the files and tool lines of a new step are those of the step it stands on
# public standards added to the docs of a problem (reference library), and reference models written by an earlier order from the task and the docs only (no RTL)
EXTRA_DOCS = {"agentic_AES_encryption_decryption_0005": {"fips197.txt": ROOT / "docs" / "standards" / "fips197_fixed.txt"}}
REF = {}   # reference models of an earlier order are passed with ref=
DESC = {"task": "- /code/task.md: the task text.", "docs": "- /code/docs/: documents of the task ({n}).", "verif": "- /code/verif/: the testbench of the task ({n}).",
        "rtl": "- /code/rtl/: the SystemVerilog source ({n}).",
        "ref": "- /code/work/model/: a reference model written earlier from the task and the documents only, without the RTL ({n}). It was not verified. Its function for the whole operation can return a step record (see its notes).",
        "lib": "- /code/lib/svvec.py: a library of SystemVerilog vectors with unknown bits (X); it was checked against a simulator. Read the text at its top before you use it. Import: `sys.path.insert(0, \"/code/lib\")`, then `from svvec import *`.",
        "tools": "- /code/lib/sigdump.py runs RtlModel on /code/work/stimulus.json (the stimulus of the testbench, written by an earlier order) and prints every signal of the model after every edge. /code/lib/listdiff.py compares two lists of lines as sequences. Read the text at the top of each before you use it. Do not write another driver for the model.",
        "tools_lib": "- /code/lib/sigdump.py: a library for your own Python scripts. It runs RtlModel, or the class of a submodule, for one edge from a state you choose or on a list of steps, and returns every signal before and after each edge. /code/lib/piececheck.py runs one piece of RtlModel with the signals it reads held at values you give; piececheck.against compares it with a function of the reference model on many inputs. /code/lib/listdiff.py compares two lists of lines as sequences. Read the text at the top of each before you use it.",
        "spec_t": "- /code/work/spec/: the timed specification of the top module, written by the architecture from the task and the documents only ({n}): the interface of a model with one step() per clock edge, and the cycle schedule.",
        "spec_b": "- /code/work/spec/top_interface.md: the interface of the top module, written by the architecture from the task and the documents only; its section on the data at the ports says how the bytes of the ports are numbered and arranged in the state of the specification.",
        "spec": "- /code/work/spec/: the timed specification of the top module ({n}): the interface and the cycle schedule written by the architecture from the task and the documents only, and the timed specification model an earlier order wrote from them (one step() per clock edge; it was checked on the examples of the documents). The file given.json there holds the entries of the description file that the host gives; the libraries read them from it.",
        "stepfacts": "- /code/lib/stepfacts.py: sets the data register of RtlModel to each step of the reference's record, forces every control value and runs one edge; it prints whether a fault is in the data path or in the control, and at which step or edge. Read the text at its top before you use it. /code/lib/sigdump.py is the library it uses; you need it only to look at a single signal.",
        "hsfacts": "- /code/lib/hsfacts.py: runs RtlModel and the timed specification model on the same port stimulus and prints, for every operation, what each does at the ports. Read the text at its top before you use it.",
        "sim": "- /code/work/sim_check.txt (with sim_check_case.json and sim_check_signals.txt): the result of a simulator run, see the task."}


def short(pid):
    return pid[5:] if pid.startswith("cvdp_") else pid


def pdir_of(pid):
    return D / short(pid)


def run_dir(pid, tag):
    return ROOT / "runs" / f"gf_{short(pid)[-34:]}-{tag}"


def prep(pid):
    r = None
    for path, kind in ((dataset.AGENTIC, "agentic"), (dataset.NONAGENTIC, "nonagentic")):
        with open(path) as f:
            for line in f:
                if f'"id": "{pid}"' in line[:300]:
                    r = json.loads(line)
                    prompt, files = (r["prompt"], r["context"]) if kind == "agentic" else (r["input"]["prompt"], r["input"].get("context") or {})
    if r is None:
        raise KeyError(pid)
    d = pdir_of(pid)
    if d.exists():
        shutil.rmtree(d)
    for k in ("rtl", "docs", "verif"):
        (d / k).mkdir(parents=True)
    (d / "task.md").write_text(prompt)
    for k, v in files.items():
        top, name = k.split("/", 1)
        if top not in ("rtl", "docs", "verif") or "/" in name:
            raise ValueError(f"unexpected path {k}")
        (d / top / name).write_text(v)
    for name, src in EXTRA_DOCS.get(short(pid), {}).items():
        shutil.copy(src, d / "docs" / name)
    return d


BASE_RECORD = None   # set by a driver: the file written by base_record(); the steps UD and UC get it as /code/lib/base_record.json


def base_record(pid, tag):
    """Host: what the simulator gives for the RTL as written, on the inputs of simcheck (interface.json of the run `tag`); for basecheck.py and tasks.py in the cell."""
    import simcheck
    out = run_dir(pid, tag) / "sim" / "base_record.json"
    simcheck.record(pdir_of(pid) / "rtl", run_dir(pid, tag) / "view", out=out)
    return out


def inputs(pid, step, sim_dir=None, ref=None, spec=None):
    inp, flist = _inputs(pid, ALIAS.get(step, step), sim_dir, ref, spec)
    if step in ("UD", "UC", "UP", "B", "E", "UA1", "UA2", "UB") and BASE_RECORD:   # from B on: r1 (2026-11-21) lost the model = RTL property inside order B, as z11 did in UD
        inp["/code/lib/base_record.json"] = (Path(BASE_RECORD), sha(Path(BASE_RECORD)), "444")
        flist += ("\n- /code/lib/base_record.json and /code/lib/basecheck.py: the record of a simulator for the RTL as written (random inputs, every output after every edge), and the library that runs "
                  "RtlModel() with no switch against it (the text at its top)." + (" tasks.py runs it at every call." if step in ("UD", "UC", "UP") else " `python3 /code/lib/basecheck.py` says whether RtlModel() with no switch still does what the RTL as written does."))
    if step in ALIAS or step in ("UD", "UC", "UP"):
        f = ROOT / "tool" / "gflow" / "ledger_edits.txt"
        inp["/code/lib/ledger.edits"] = (f, sha(f), "444")     # ledger.py asks for the edits of a kept switch
        if step in ("UD", "UC", "UP"):
            flist += "\n- /code/lib/rtlapply.py: the form of the edits of a switch (the text at its top); ledger.py uses it to write the RTL of the kept switches."
    if step == "B":     # 2026-11-23 (user agreed): a page of use with examples instead of the source texts of the libraries (B read ~68 KB of library source per order)
        f = ROOT / "tool" / "gflow" / "usage_b.md"
        inp["/code/lib/usage.md"] = (f, sha(f), "444")
        keep = []
        for l in flist.split("\n"):
            if l == DESC["lib"]:
                keep.append("- /code/lib/: the libraries svvec (vectors with unknown bits, as the model uses them), sigdump, piececheck and basecheck. "
                            "/code/lib/usage.md shows how to use them in this order, with examples; read it first.")
            elif l == DESC["tools_lib"]:
                continue
            elif l.startswith("- /code/lib/base_record.json and /code/lib/basecheck.py:"):
                keep.append("- /code/lib/base_record.json: the record of a simulator for the RTL as written (random inputs, every output after every edge); "
                            "`python3 /code/lib/basecheck.py` says whether RtlModel() with no switch still does what the RTL as written does.")
            else:
                keep.append(l)
        assert len(keep) == len(flist.split("\n")) - 1, "order B: the texts of the libraries were not found"
        flist = "\n".join(keep)
    return inp, flist


def ref_fact(ref):
    """The host runs ref_check.py, written by the reference model order next to its model, in a cell; its lines become a fact of the order text."""
    view = Path(ref[0]).resolve().parent
    if not (view / "ref_check.py").exists():
        return " It was not verified."
    r = subprocess.run(["docker", "run", "--rm", "--network", "none", "-e", "PYTHONDONTWRITEBYTECODE=1", "-v", f"{view}:/code/work:ro", "-w", "/code/work",
                        "--entrypoint", "python3", IMAGE, "/code/work/ref_check.py"], capture_output=True, text=True, timeout=600)
    got = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    if r.returncode != 0 or not got:
        return " It was not verified (its check ref_check.py did not run to its end)."
    return (" The host ran the check that order wrote with it (ref_check.py, the specification's examples) on it: " + "; ".join(got)
            + " (\"no example\": the specification gives no example for that function alone).")


def _inputs(pid, step, sim_dir=None, ref=None, spec=None):
    d = pdir_of(pid)
    inp, lines = {}, []

    def add(kind, files, dest):
        files = sorted(files)
        if files:
            for f in files:
                inp[f"{dest}/{f.name}"] = (f, sha(f), "444")
            lines.append(DESC[kind].format(n=", ".join(f.name for f in files)))
    if step == "T":
        inp["/code/task.md"] = (d / "task.md", sha(d / "task.md"), "444")
        lines.append(DESC["task"])
        add("docs", (d / "docs").iterdir(), "/code/docs")
        add("spec_t", [Path(x) for x in spec if Path(x).name != "given.json"], "/code/work/spec")   # given.json is for the libraries of the later orders
        add("ref", [Path(x) for x in ref], "/code/work/model")
        return inp, "\n".join(lines)
    if step not in ("A", "A2"):
        inp["/code/task.md"] = (d / "task.md", sha(d / "task.md"), "444")
        lines.append(DESC["task"])
        if step != "B" or not ref:      # flow f7 (2026-11-22): B works from the reference model and the interface; the documents are given to M and T
            add("docs", (d / "docs").iterdir(), "/code/docs")
        # the testbench is not given after order A: no step after A uses it, and with it order B judged the whole operation (r1, 2026-11-21)
    else:
        add("verif", (d / "verif").iterdir(), "/code/verif")   # A writes the stimulus file from the testbench
    if step != "M":
        add("rtl", (d / "rtl").iterdir(), "/code/rtl")
        add("lib", [LIB], "/code/lib")
        for f in LIB_TOOLS:
            inp[f"/code/lib/{f.name}"] = (f, sha(f), "444")
        if step in ("C1", "C2A", "C2B"):
            lines.append(DESC["tools"])
        if step in ("B", "E", "UA", "UA1", "UA2", "UB", "UT"):
            lines.append(DESC["tools_lib"])
        if step in ("UD", "UC"):
            lines.append(DESC["stepfacts"])
        if step == "UP":
            f3 = ROOT / "tool" / "gflow" / "tasks_part3.txt"
            inp["/code/lib/tasks.part"] = (f3, sha(f3), "444")   # tasks.py gives the ports from portfacts
            lines.append("- /code/lib/portfacts.py: runs RtlModel and the timed specification model on the same port stimulus and compares every output after every edge; it prints where they differ and the values. Read the text at its top before you use it. /code/lib/sigdump.py is the library it uses (the text at its top says how one model is run and what a record holds).")
            lines.append("- /code/lib/tasks.py: gives the differences of the design one at a time (it runs portfacts itself) and says when one is closed. Read the text at its top before you use it.")
            lines.append("- /code/lib/ledger.py: the book of the switches (/code/work/ledger.json): `add` writes one entry per switch that is kept or dropped, after comparing its RTL lines with the entries already there; `show` prints the book. Read the text at its top before you use it.")
        if step == "UD":
            inp["/code/lib/tasks.part"] = (ROOT / "tool" / "gflow" / "tasks_part1.txt", sha(ROOT / "tool" / "gflow" / "tasks_part1.txt"), "444")   # tasks.py gives the data path only
        if step in ("UD", "UC"):
            lines.append("- /code/lib/tasks.py: gives the differences of the design one at a time (it runs stepfacts and hsfacts itself) and says when one is closed. Read the text at its top before you use it.")
        if step in ("UD", "UC", "DL", "DL2"):
            lines.append("- /code/lib/ledger.py: the book of the switches (/code/work/ledger.json): `add` writes one entry per switch that is kept or dropped, after comparing its RTL lines with the entries already there; `show` prints the book. Read the text at its top before you use it.")
        if step in ("DL", "DL2"):
            lines.append("- /code/lib/rtlapply.py: writes /code/work/rtl_fixed/ from the original RTL files and a list of changes (text replaced in a copy), and prints every edit that could not be applied. Read the text at its top before you use it.")
        if step in ("UT", "UC", "UD") or (spec and step in ("UB", "D", "D2", "DL", "DL2")):   # UD: the description file is the one of hsfacts
            lines.append(DESC["hsfacts"])
    if spec and step == "B":     # flow f7 (2026-11-22): B judges the load and unload against the data definition of the interface
        add("spec_b", [Path(x) for x in spec if Path(x).name == "top_interface.md"], "/code/work/spec")
    elif spec:
        add("spec", [Path(x) for x in spec], "/code/work/spec")
    if step in ("B", "C1", "C2", "C2A", "C2B", "E", "UA", "UA1", "UA2", "UB", "UT", "UD", "UC", "UP") or (step in ("D", "D2", "DL", "DL2") and ref is not None):   # D/D2 run the scripts of the reports again; these import the reference model
        add("ref", [Path(x) for x in ref] if ref is not None else REF.get(short(pid), []), "/code/work/model")
        if step == "B" and ref:     # 2026-11-23 (user agreed): B takes the reference model as its reference; the host's run of its own check replaces "not verified"
            lines[-1] = lines[-1].replace(" It was not verified.", ref_fact(ref))
    if sim_dir:
        for n in ("sim_check.txt", "sim_check_case.json", "sim_check_signals.txt"):
            if (Path(sim_dir) / n).exists():
                inp[f"/code/work/{n}"] = (Path(sim_dir) / n, sha(Path(sim_dir) / n), "444")
        lines.append(DESC["sim"])
    return inp, "\n".join(lines)


class GCell(S3Cell):
    def __init__(self, pid, tag):
        super().__init__(ROOT / "runs", tag, egress_port=s2.PORT, tools=False)
        self.problem["id"] = f"gf_{short(pid)}"
        self.run_dir = run_dir(pid, tag)
        self.name = f"lora_{self.run_dir.name.replace('-', '_')}"[:60]


def carry_files(cell, src_run):
    """The agent's files of an earlier run (all of /code/work that the agent owned, without DONE) into this cell, agent-owned."""
    tar = next(src_run.glob("after-01-*/work_all.tar"))
    d = Path(tempfile.mkdtemp())
    subprocess.run(["tar", "-xf", str(tar), "-C", str(d)], check=True)
    out = {}
    for f in sorted(d.iterdir()):
        if f.name in ("DONE", "align", "QWEN.md", "model", "map", "spec", "stimulus.json") or f.name.startswith(".") or f.name.startswith("sim_check") or f.name == "__pycache__":
            continue
        subprocess.run(["docker", "cp", str(f), f"{cell.name}:/code/work/{f.name}"], check=True)
        cell.exec_root("sh", "-c", f"chown -R agent:agent '/code/work/{f.name}' && chmod -R u+rwX,go+rX '/code/work/{f.name}'")
        out[f.name] = sha(f) if f.is_file() else "dir"
    return out


BACKEND_MODEL = "qwen3.8-nopen-exp-dflash2"  # the model the proxy sends every request to (arm d2)


def backend_ready(url="http://127.0.0.1:11435/api/generate"):
    """The backend runner sometimes stops answering after a long session; unload the model and ask a small question before each order."""
    import urllib.request
    def post(body, t):
        return urllib.request.urlopen(urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=t).read()
    for k in range(3):
        try:
            post({"model": BACKEND_MODEL, "keep_alive": 0}, 60)
            time.sleep(5)
            post({"model": BACKEND_MODEL, "prompt": "Say ok.", "stream": False, "options": {"num_predict": 8}}, 300)
            return True
        except Exception as e:
            print("backend not ready:", e, flush=True)
            time.sleep(20)
    return False


STIM_TEXT = "\n4. This unit is the top of the design: also run the stimulus of the testbench on one model with sigdump.run and compare the values the testbench expects. If /code/work/stimulus.json does not exist, write it from the testbench in /code/verif in the form of sigdump: every operation of the testbench in its order, each input change as `set`, each wait for a signal as `until` or `until_rise`, each checked value as `expect`; the clock edges that pass between two events of the testbench are counted from its delays and written as `edges`."


def compose(pid, step, scope="", report="block_check.md", fact="", sim=None, minutes=None, ref=None, script="edge_table.py", stim_text="", notes="notes.md", spec=None, ports=False):
    """The files a cell of this step gets and the text of its order."""
    of, skills, m0 = STEPS[step]
    minutes = minutes or m0
    sim_dir = run_dir(pid, sim) / "sim" if sim else None
    inp, flist = inputs(pid, step, sim_dir, ref, spec)
    text = (D / of).read_text()
    if step == "A":     # the point that writes stimulus.json from the testbench is not given: no later step uses that file (user decisions 2026-11-21)
        lines5 = [l for l in text.split("\n") if l.startswith("5. Write /code/work/stimulus.json")]
        if lines5 and "When the four files are written" in text:
            text = text.replace(lines5[0] + "\n", "").replace("When the four files are written", "When the three files are written")
    if step == "B":     # short order (user agreed 2026-11-25, after read-aes0005-B1-01): its own file list; of the generated list only the host's check of the reference model is used
        refl = next((l for l in flist.split("\n") if l.startswith("- /code/work/model/")), "")
        m = re.search(r" (The host ran the check|It was not verified).*", refl)
        reff = (" " + m.group(0).strip()) if m else ""
        reff = reff.replace("The host ran the check that order wrote with it (ref_check.py, the specification's examples) on it:", "The host ran its check on the examples of the specification (ref_check.py):")
        fact = re.sub(r"^A simulator run of the original RTL against RtlModel\(\) with no switch \(\d+ random stimulus scenarios\) showed no difference in the outputs\.", "", fact).strip()   # said in the file list
        text = text.replace("{REF}", reff).replace("{FACT}\n", (fact + "\n\n") if fact else "\n").replace("{PORTS}", " Also compare the data path from port to port (skill, point 5)." if ports else "")
    order = text.replace("{FILES}", flist).replace("{MINUTES}", str(minutes)).replace("{SCOPE}", scope).replace("{REPORT}", report).replace("{FACT}", fact).replace("{SCRIPT}", script).replace("{STIM}", stim_text).replace("{NOTES}", notes)
    return inp, order


def run(pid, tag, step, carry=None, scope="", report="block_check.md", fact="", sim=None, minutes=None, target=None, ref=None, script="edge_table.py", stim_text="", notes="notes.md", spec=None, ports=False):
    of, skills, m0 = STEPS[step]
    minutes = minutes or m0
    if step not in ("A", "M", "T", "TN") and not carry:
        sys.exit("this step needs --carry")
    inp, order = compose(pid, step, scope, report, fact, sim, minutes, ref, script, stim_text, notes, spec, ports)
    skills = {n: SK / n / "SKILL.md" for n in skills}
    row = {"test": "gflow", "pid": pid, "step": step, "tag": tag, "carry": carry, "scope": scope, "order_sha256": hashlib.sha256(order.encode()).hexdigest(), "image": IMAGE,
           "model_labels": {"model": s2.MODEL, "arm": s2.ARM, "max_tokens": s2.MAX_TOKENS, "minutes": minutes}}
    cell = GCell(pid, tag)
    rdir = cell.run_dir
    if rdir.exists():
        sys.exit(f"{rdir} exists")
    if os.environ.get("GFLOW_REPLAY_ONLY") and not REPLAY.get(tag.split("-", 1)[-1]):
        sys.exit(f"dry run: no stand-in files for the order {tag.split('-', 1)[-1]} (the model is not called)")
    if not REPLAY.get(tag.split("-", 1)[-1]) and not backend_ready():     # a dry run with stand-in files does not touch the backend: backend_ready unloads the model, which disturbs a round that is running
        sys.exit("backend does not answer")
    proxy = None
    try:
        empty = Path(tempfile.mkdtemp()) / "QWEN.md"
        empty.write_text("")
        cell.start(inp, empty, skills)
        (rdir / "order.md").write_text(order)
        row["skills"] = {n: sha(p) for n, p in skills.items()}
        if carry:
            row["carry_files"] = carry_files(cell, run_dir(pid, carry))
        row["inputs"] = {d: v[1] for d, v in inp.items()}
        c0 = cell.checks(start=True)
        (rdir / "checks_start.json").write_text(json.dumps(c0, indent=1, default=str))
        row["checks_start_ok"] = c0["ok"]
        if not c0["ok"]:
            row["aborted"] = "cell_checks failed before the order"
            _append(row)
            return row
        if REPLAY.get(tag.split("-", 1)[-1]):      # dry run with stand-in files: no proxy (its port may belong to a round that is running)
            pdir = rdir / "proxy"
            pdir.mkdir(parents=True, exist_ok=True)
        else:
            proxy, pdir = s2.start_proxy(rdir, target, extra=(["--drop-history-reasoning"] + (["--keep-last-reasoning", str(KEEP_REASONING)] if KEEP_REASONING else [])) if DROP_REASONING else [])
        row["drop_history_reasoning"] = DROP_REASONING
        row["keep_last_reasoning"] = KEEP_REASONING
        labels = {"test": "gflow", "tag": tag, "step": step, "arm": s2.ARM, "minutes": minutes, "max_tokens": s2.MAX_TOKENS, "image": IMAGE, "order_sha": row["order_sha256"][:16]}
        (rdir / "labels.json").write_text(json.dumps(labels))
        gate = s2.DoneGate(cell, pdir)
        agent = "qwen"
        if os.environ.get("GFLOW_REPLAY_ONLY") and not REPLAY.get(tag.split("-", 1)[-1]):
            sys.exit(f"dry run: no stand-in files for the order {tag.split('-', 1)[-1]} (the model is not called)")
        if REPLAY.get(tag.split("-", 1)[-1]):      # dry run of the flow without the model: the files an earlier run of this order left are put into the cell by a script in place of the agent
            src = next(Path(REPLAY[tag.split("-", 1)[-1]]).glob("after-01-*/work_all.tar"))
            subprocess.run(["docker", "cp", str(src), f"{cell.name}:/tmp/replay.tar"], check=True)
            cell.exec_root("chmod", "644", "/tmp/replay.tar")
            fake = Path(tempfile.mkdtemp())
            (fake / f"G{step}.sh").write_text("cd /code/work && tar -xf /tmp/replay.tar --exclude=./spec --exclude=./model --exclude=spec --exclude=model 2>/dev/null; touch /code/work/DONE; exit 0\n")
            agent = f"fake:{fake}"
            row["replay_of"] = str(src)
        opts = {"request_timeout_ms": 1800000, "agent": agent, "model": s2.MODEL, "order_timeout": minutes * 60, "idle_timeout": 15 * 60, "context_limit": CONTEXT_LIMIT, "poll": 2, "proxy_dir": pdir,
                "base_url": f"http://host.docker.internal:{s2.PORT}/v1", "order_text": order, "labels": labels, "network_policy": "proxy-only", "done_reason": "done", "done_check": gate}
        t0 = time.time()
        res = run_order(cell, f"G{step}", {"round": 1}, 1, opts)
        row["order_result"] = res
        row["seconds"] = round(time.time() - t0, 1)
        row["done_written"] = gate.t_done is not None
        if proxy is not None:
            proxy.terminate()
            proxy.wait(timeout=20)
        proxy = None
        c1 = cell.checks()
        (rdir / "checks_end.json").write_text(json.dumps(c1, indent=1, default=str))
        row["checks_end_ok"] = c1["ok"]
        row["facts"] = facts(pdir)
    finally:
        if proxy is not None:
            proxy.terminate()
        cell.stop()
    view(pid, tag)
    subprocess.run([str(ROOT / "backup_run.sh"), str(rdir.relative_to(ROOT))], check=False, capture_output=True)
    _append(row)
    return row


def view(pid, tag):
    rdir = run_dir(pid, tag)
    v = rdir / "view"
    if v.exists():
        shutil.rmtree(v)
    v.mkdir()
    subprocess.run(["tar", "-xf", str(next(rdir.glob("after-01-*/work_all.tar"))), "-C", str(v)], check=True)
    return v


def sim(pid, tag, fixed=False):
    import simcheck
    rdir = run_dir(pid, tag)
    v = rdir / "view"
    rtl = pdir_of(pid) / "rtl"
    r = simcheck.check(v / "rtl_fixed" if fixed else rtl, v, model_rtl=rtl, fix="all" if fixed else None, out=rdir / "sim")
    (rdir / "sim" / ("result_fixed.json" if fixed else "result.json")).write_text(json.dumps(r, default=str))
    return r


def changes(pid, tag):
    """Host gate of the orders DL/DL2: rtl_fixed/ written from the agent's list of changes, compared with RtlModel in the simulator (all switches, and the entries one more at a time)."""
    import changecheck
    rdir = run_dir(pid, tag)
    r = changecheck.check(rdir / "view", pdir_of(pid) / "rtl", out=rdir / "sim")
    (rdir / "sim" / "result_changes.json").write_text(json.dumps(r, default=str))
    return r


def data_gate(pid, tag, ref, spec):
    """Host gate after order UD: blockfacts (stepfacts part 1, piece by piece) on the files the order left, all switches on.
    It passes when the data path alone (control forced) goes from the load to the final step of the record."""
    rdir = run_dir(pid, tag)
    out = rdir / "sim"
    out.mkdir(exist_ok=True)
    work = out / "blockfacts_work"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(rdir / "view", work)
    for sub, files in (("model", ref), ("spec", spec)):
        (work / sub).mkdir(exist_ok=True)
        for f in files:
            shutil.copy(f, work / sub / Path(f).name)
    lib = ROOT / "tool" / "gflow"
    r = subprocess.run(["docker", "run", "--rm", "--network", "none", "-e", "PYTHONDONTWRITEBYTECODE=1",
                        "-v", f"{work}:/code/work", "-v", f"{lib}:/code/lib:ro", "-v", f"{pdir_of(pid) / 'rtl'}:/code/rtl:ro", "-w", "/code", "--entrypoint", "python3", IMAGE,
                        "/code/lib/blockfacts.py", "/code/work/handshake.json", "--json", "/code/work/blockfacts.json"],
                       capture_output=True, text=True)
    text = (r.stdout + r.stderr).strip()
    (out / "blockfacts.txt").write_text(text + "\n")
    res = {"ok": False, "text": text, "ran": r.returncode == 0}
    if r.returncode == 0:
        m = json.loads((work / "blockfacts.json").read_text())["measure"]
        res.update(ok=m["final"] and not m["dead"], final=m["final"], dead=m["dead"], arrangement_given=m["arrangement_given"])
    (out / "result_blockfacts.json").write_text(json.dumps(res))
    return res


def stim(pid, tag):
    """Host check of the stimulus file an order wrote: the task's testbench in a simulator against RtlModel() on stimulus.json."""
    import stimcheck
    rdir = run_dir(pid, tag)
    return stimcheck.check(pdir_of(pid) / "rtl", pdir_of(pid) / "verif", rdir / "view", out=rdir / "sim")


def stim_model(pid, tag):
    """Host check after the write-back orders: RtlModel(fix="all") of this run on its stimulus.json (the task's testbench) still gives the values the testbench expects."""
    rdir = run_dir(pid, tag)
    view = rdir / "view"
    if not (view / "stimulus.json").exists():
        return {"ok": None, "text": "no stimulus.json"}
    r = subprocess.run(["docker", "run", "--rm", "--network", "none", "--user", "root", "-e", "PYTHONDONTWRITEBYTECODE=1", "-v", f"{view}:/code/work:ro", "-v", f"{ROOT / 'tool' / 'gflow'}:/code/lib:ro",
                        "-v", f"{pdir_of(pid) / 'rtl'}:/code/rtl:ro", "-w", "/code/work", "--entrypoint", "python3", IMAGE, "/code/lib/sigdump.py", "/code/work/stimulus.json", "--fix", "all", "--summary"],
                       capture_output=True, text=True, timeout=600)
    text = r.stdout + r.stderr
    ok = r.returncode == 0 and "expect" in text and "DIFFERENT" not in text
    (rdir / "sim").mkdir(exist_ok=True)
    (rdir / "sim" / "stim_model.txt").write_text(text)
    return {"ok": ok, "text": text}


def _append(row):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prep", "run", "view", "sim", "grade"])
    ap.add_argument("--pid", required=True)
    ap.add_argument("--tag")
    ap.add_argument("--step", choices=list(STEPS))
    ap.add_argument("--carry")
    ap.add_argument("--scope", default="")
    ap.add_argument("--report", default="block_check.md")
    ap.add_argument("--fact", default="")
    ap.add_argument("--sim")
    ap.add_argument("--minutes", type=int)
    ap.add_argument("--fixed", action="store_true")
    ap.add_argument("--target")
    a = ap.parse_args()
    if a.cmd == "prep":
        print(prep(a.pid))
    elif a.cmd == "run":
        row = run(a.pid, a.tag, a.step, a.carry, a.scope, a.report, a.fact, a.sim, a.minutes, a.target)
        print(json.dumps({k: row.get(k) for k in ("aborted", "checks_start_ok", "checks_end_ok", "seconds", "done_written", "order_result")}, indent=1, default=str))
    elif a.cmd == "view":
        print(view(a.pid, a.tag))
    elif a.cmd == "sim":
        r = sim(a.pid, a.tag, a.fixed)
        print(r["text"])
        print(json.dumps({k: r.get(k) for k in ("ok", "differences", "error")}))
    elif a.cmd == "grade":
        print(json.dumps(grader.grade(a.pid, run_dir(a.pid, a.tag) / "view" / "rtl_fixed", image="lora-rtl:dev")))
