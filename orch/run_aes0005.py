"""gflow for cvdp_agentic_AES_encryption_decryption_0005 from the first order to the hidden harness, without a person between the orders.

  python3 -m orch.run_aes0005 --check
  python3 -m orch.run_aes0005 BASE [--from STAGE --carry TAG] [--ref TAG] [--timed TAG]

Stages, in this order (name of the stage: orders), flow version f7 (docs/NAMES.md; plan A of 2026-11-22):
  m     M    a reference model from the task and the documents only (no RTL)
  t     T    a timed specification model of the top module from the schedule in data/stages/gflow/spec_aes0005 (no RTL; it needs only M)
  a     A    the RTL translated to a Python model with no change; the host compares it with the RTL in a simulator (A2 while they differ, at most twice)
  b     B    one order per module that instantiates others, lowest first: every piece against the documents (switches for the faults found)
  d     LB, UD   the switches of B entered in the book with their RTL edits (LB, host check); then the data path of the top module against the
             step record of the reference (stepfacts part 1). The host checks the book and runs blockfacts: while the data path alone does not go
             from the load to the final step, one more order UD gets its print (at most two more)
  k     E, UA1, UA2, UB   the lower module (key expansion) as a unit: one edge, the walk at its ports, switches, sequence and values
  top   LB, UC   the switches of k entered in the book (LB); control and handshake against the timed model (UC).
  After every order that writes the book the host applies the book to the RTL and compares with the model in a simulator; while they differ an
  order LF corrects the one entry the host names (at most three).
  then the hidden harness of CVDP on the RTL the book gives.

BASE names the round; every order is a new cell with the run directory runs/gf_...-BASE-<order>.
--from STAGE --carry TAG continues a round at a stage from the run TAG of an earlier order (with --ref TAG: the run of order M; --timed TAG: the run of order T).
One JSON line per order is printed, and one at the end ("passed": the hidden harness; "stopped": why the flow stopped itself).
An order cut by its time limit is continued in a new cell; an order that hangs stops the flow (the cause is found before it is run again).
The texts below that name modules and report files belong to this problem; the orders, skills and tools do not.
"""
import argparse
import json
import os
import re
import subprocess
import sys

os.environ.setdefault("GFLOW_DROP_REASONING", "1")       # the proxy does not send the thinking of earlier answers back to the model
os.environ.setdefault("GFLOW_KEEP_REASONING", "6000")    # but the last answer keeps the end of its thinking (its conclusion and plan)
from . import dataset, gflow, gflow_auto as ga
from . import grade as grader

PID = "cvdp_agentic_AES_encryption_decryption_0005"
STAGES = ["m", "t", "a", "b", "d", "k", "top"]
S1 = "the module aes128_key_expansion (its pieces were checked in block_check_1.md)"
S1U = S1[:-1] + "; its one-edge report is edge_check_1.md with the script edge_table_1.py)"
S2U = ("the module aes128_decrypt, which has the module aes128_key_expansion inside it (the pieces of aes128_decrypt were checked in block_check_2.md; "
       "aes128_key_expansion has edge_check_1.md and unit_check_1.md)")
K_PLAN = [("E", "e1", dict(scope=S1, report="edge_check_1.md", script="edge_table_1.py", notes="notes_e_1.md")),
          ("UA1", "u1a", dict(scope=S1U, report="unit_check_1.md", script="walk_check_1.py", notes="notes_ua1_1.md")),
          ("UA2", "u1b", dict(scope=S1U, report="unit_check_1.md", script="walk_check_1.py", notes="notes_ua2_1.md")),
          ("UB", "u1c", dict(scope=S1U, report="unit_check_1.md", script="edge_table_1.py", notes="notes_ub_1.md"))]
S2D = ("the module aes128_decrypt, which has the module aes128_key_expansion inside it (the pieces of aes128_decrypt were checked in block_check_2.md, "
       "those of aes128_key_expansion in block_check_1.md)")
D_PLAN = ("UD", "ud", dict(scope=S2D, report="unit_check_2.md", notes="notes_ud_2.md"))
TOP_PLAN = [("UC", "uc", dict(scope=S2U, report="unit_check_2.md", notes="notes_uc_2.md"))]
# the fact an order UD gets after the host gate did not pass (agreed by the user 2026-11-22)
GATE_FACT = ("\nAfter the order before this one, the host ran /code/lib/blockfacts.py on /code/work/handshake.json and RtlModel with all switches on. "
             "It sets the data register to each step of the record, every control value in turn, runs one edge, and says from which steps each piece "
             "of the chain inside that edge has the value of a later step of the record. Its print:\n{print}\n"
             "A piece that lands from no step is wrong, or reads a wrong piece in the same edge, or is not a stage of the record (a part of a stage).")
SPEC0 = sorted((gflow.D / "spec_aes0005").iterdir())
# order B of aes128_decrypt in two parts (flow f7, 2026-11-22): first the pieces that decide the arrangement, then the pieces that bring data in and out with it
B_PARTS = {2: [("p1", "the pieces of the module aes128_decrypt that compute along the rows or the columns of its data: the xtimes signals, MixColumns and ShiftRows, piece by piece (its submodule aes128_key_expansion was checked in block_check_1.md; the other pieces of aes128_decrypt are checked by the next order, which takes the arrangement you write in notes.md)"), ("p2", "the other pieces of the module aes128_decrypt with the modules it instantiates that instantiate nothing (inv_sbox): the load of i_data, the output o_data, AddRoundKey and SubBytes, piece by piece (its submodule aes128_key_expansion was checked in block_check_1.md; xtimes, MixColumns and ShiftRows were checked by the order before this one: its arrangement of the data is in notes.md and its table in block_check_2.md; add the rows of your pieces to that table)")]}


class Stop(Exception):
    pass


def check():
    ok = True

    def line(good, text):
        nonlocal ok
        ok = ok and bool(good)
        print(("ok      " if good else "MISSING ") + text)
    line(dataset.AGENTIC.exists(), f"CVDP dataset {dataset.AGENTIC}")
    imgs = subprocess.run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], capture_output=True, text=True).stdout.split()
    for i in (gflow.IMAGE, "lora-rtl:dev"):
        line(i in imgs, f"docker image {i}")
    try:
        import urllib.request
        names = [m["name"] for m in json.loads(urllib.request.urlopen("http://127.0.0.1:11435/api/tags", timeout=10).read()).get("models", [])]
        line(True, "backend answers on 127.0.0.1:11435")
        line(any(n.split(":")[0] == gflow.BACKEND_MODEL for n in names), f"backend model {gflow.BACKEND_MODEL}")
    except Exception as e:  # noqa: BLE001
        line(False, f"backend on 127.0.0.1:11435 ({e})")
    if dataset.AGENTIC.exists():
        d = gflow.pdir_of(PID) if (gflow.pdir_of(PID) / "rtl").exists() else gflow.prep(PID)
        line((d / "rtl").exists() and (d / "docs" / "fips197.txt").exists(), f"problem files {d}")
    return ok


def view(tag):
    return gflow.run_dir(PID, tag) / "view"


B_FACT_SCRIPT = r"""
import sys, glob, os, json
sys.path.insert(0, "/code/lib")
import sigdump, rtlapply
mod = sigdump.load_model("/code/work/rtl_model.py")
top = list(getattr(mod.RtlModel, "SWITCHES", {}) or {})
every = rtlapply.model_switches("/code/work/rtl_model.py") or []
calls = sorted(os.path.basename(f) for f in glob.glob("/code/work/*.py")
               if not os.path.basename(f).startswith("rtl_model") and "piececheck.against(" in open(f, errors="ignore").read())
print(json.dumps({"top": top, "other": [n for n in every if n not in top], "against": calls}))
"""


def b_facts(tag, prev=None, ports=False, finished=True):
    """Host check after an order B (user agreed 2026-11-23): the scripts the order left that call piececheck.against, and switch names that are
    in a SWITCHES of the model file but not in RtlModel.SWITCHES. Facts only; returns the text of a continuation, or "" when there is nothing to say."""
    v = view(tag).resolve()
    r = subprocess.run(["docker", "run", "--rm", "--network", "none", "-e", "PYTHONDONTWRITEBYTECODE=1", "-v", f"{v}:/code/work:ro",
                        "-v", f"{(gflow.ROOT / 'tool' / 'gflow').resolve()}:/code/lib:ro", "-w", "/code/work", "--entrypoint", "python3",
                        gflow.IMAGE, "-c", B_FACT_SCRIPT], capture_output=True, text=True, timeout=600)
    try:
        f = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return ""
    out = []
    if not f["against"]:
        out.append("no script in /code/work calls piececheck.against: no row of the table rests on a comparison with a function of the reference model")
    if f["other"]:
        out.append(f"the switches {', '.join(f['other'])} are in a SWITCHES of the model file but not in RtlModel.SWITCHES (names there: {', '.join(f['top']) or 'none'}); "
                   "the later orders and the host take the switches from RtlModel.SWITCHES")
    p = view(prev) / "against_log.jsonl" if prev else None
    out += against_facts(v / "against_log.jsonl", f["top"], carried_lines(p, v / "against_log.jsonl"), ports, (v / "arrangement.json").exists(), finished)
    out += arrangement_facts(view(prev) / "arrangement.json" if prev else None, v / "arrangement.json")
    if not out:
        return ""
    if not finished:       # for the continuation of a cut order: the same facts, read from the files it had left when it was cut
        return " The host read the comparisons and the arrangement file it left: " + "; ".join(out) + "."
    return (" The order was finished (DONE). Facts from the host about the files it left: " + "; ".join(out) + "."
            " This order is given again: complete it from these facts, then create DONE again.")


PLACE_NAMES = ("rows as written", "rows and columns exchanged", "as written", "reversed")


def arrangement_facts(prev_file, file):
    """/code/work/arrangement.json after an order (user agreed 2026-11-24): each arrangement is a name piececheck.place knows, and what the file gave before the order is not changed."""
    def load(p):
        try:
            a = json.loads(p.read_text())
            return a if isinstance(a, dict) else None
        except (OSError, ValueError, AttributeError):
            return None
    def entries(a):
        e = {f'"signals": {k}': x for k, x in (a.get("signals") if isinstance(a.get("signals"), dict) else {}).items()}
        if "place" in a and not e:          # with entries under "signals", "place" is only what a signal without an entry gets (f7-15)
            e['"place"'] = a["place"]
        return e
    new, old = load(file), load(prev_file) if prev_file else None
    if new is None:
        return []
    now, out = entries(new), []
    bad = [k for k, x in now.items() if x not in PLACE_NAMES]
    if bad:
        out.append(f"in /code/work/arrangement.json the value of {', '.join(bad)} is not one of the names piececheck.place knows ({', '.join(PLACE_NAMES)}): "
                   "piececheck.against cannot use it; the description goes in \"basis\"")
    for k, x in entries(old or {}).items():
        if x in PLACE_NAMES and now.get(k) != x:
            out.append(f"/code/work/arrangement.json gave {k} = {x} before this order and now gives {now.get(k, 'nothing')}: what the file gives is not changed by a later order (skill, point 3)")
    return out


def carried_lines(prev_log, log):
    """How many lines at the head of `log` are the lines of the order before (the file is carried); an order that wrote the file anew carries none (f7-11)."""
    if not (prev_log and prev_log.exists() and log.exists()):
        return 0
    old, new = prev_log.read_text().splitlines(), log.read_text().splitlines()
    return len(old) if new[:len(old)] == old else 0


def against_facts(log_file, top, skip=0, ports=False, arranged=True, finished=True):
    """From the log piececheck.against writes: the comparisons whose last run with every switch of the model on still differed (user agreed 2026-11-23)."""
    if not log_file.exists():
        return ["no comparison of the order is in /code/work/against_log.jsonl"] if ports else []
    last, seen_differ, own_place, latest = {}, {}, False, {}
    for line in log_file.read_text().splitlines()[skip:]:     # only the lines this order wrote (the file is carried from the order before)
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("held_not_read"):         # step() did not read what was held: the row compares no piece (piececheck says so to the order)
            continue
        if "all" in e.get("switches_on", ()):      # a model that keeps fix="all" as a list: every switch is on
            e["all_on"], e["switches_on"] = True, sorted(e["switches_of_model"])
        own = lambda s: ", ".join(x.strip().rsplit(".", 1)[-1] for x in s.split(","))     # a signal of a submodule under its own name or under the path from the top is one signal (f7-16)
        key = (own(e["hold"]), own(e["read"]), own(e.get("start") or ""), tuple(e.get("ports_in") or ()))   # one comparison = what is held, set, driven and read; the name is the order's own label
        own_place |= bool(e.get("place")) and e.get("arrangement") is None
        latest[key] = e
        if e.get("all_on"):
            if set(e["switches_of_model"]) == set(top) or key not in last or set(last[key]["switches_of_model"]) != set(top):
                last[key] = e              # the last run with the switches of the model now, else the last run with every switch on then
                if not e["differ"]:        # it agrees: the same comparison with fewer ports driven that differed was the test's (f7-17: reset not driven)
                    for k in [k for k in list(last) + list(seen_differ) if k[:3] == key[:3] and set(k[3]) < set(key[3])]:
                        if k in last and last[k]["differ"]:
                            del last[k]
                            seen_differ.pop(k, None)
                        elif k not in last:
                            seen_differ.pop(k, None)
        elif e.get("differ"):
            seen_differ[key] = e
        elif key in seen_differ and seen_differ[key]["switches_on"] == e["switches_on"]:
            del seen_differ[key]           # the same comparison with the same switches agreed later: the earlier difference was the test's (f7-12)
    def lab(e):
        return f"{e['name']} (" + ", ".join(x for x in (f"held {e['hold']}" if e["hold"] else "", f"set {e['start']}" if e.get("start") else "",
                                                       f"ports {', '.join(e['ports_in'])}" if e.get("ports_in") else "", f"read {e['read']}") if x) + ")"
    groups = {}                            # comparisons that differ only in an index are one fact (f7-12)
    for k, e in seen_differ.items():
        if k not in last:
            groups.setdefault((re.sub(r"\d+", "N", lab(e)), e["differ"], e["compared"], tuple(e["switches_on"])), []).append(e)
    out = []
    for g in (groups.values() if finished else ()):     # a cut order has not come to these yet: its continuation gets the facts below only
        e = g[0]
        more = f" (and {len(g) - 1} more of the same form, to {lab(g[-1])})" if len(g) > 1 else ""
        out.append(f"{lab(e)}{more} differed on {e['differ']} of {e['compared']} inputs with the switches {', '.join(e['switches_on']) or 'none'} on "
                   "and was not compared with every switch of the model on")
    now = [e for e in last.values() if set(e["switches_of_model"]) == set(top)]
    for e in now:      # arrangement (skill point 3; user agreed 2026-11-24)
        if e.get("place_differs"):
            out.append(f"{lab(e)} was compared with the arrangement {e['place']}, not the one of /code/work/arrangement.json ({e['arrangement']})")
    miss = [lab(e) for e in latest.values() if e.get("arrangement_missing")]
    if len(miss) > 4:
        miss = miss[:3] + [f"{len(miss) - 3} more"]
    if miss:
        out.append(f"{'; '.join(miss)}: /code/work/arrangement.json gives no arrangement for the arrays of these comparisons "
                   "(no entry under \"signals\", and its \"place\" does not fit their shape)")
    if own_place and not arranged:
        out.append("comparisons give their own arrangement and there is no /code/work/arrangement.json: the arrangement is written once there (skill, point 3)")
    if ports and finished:          # the order with the pieces that bring the data in and out: the data path from port to port (skill point 5)
        need = [("the data brought in from the input ports (drive the ports, hold nothing, read the register they load)", lambda e: e.get("ports_in") and not e["hold"] and not e.get("read_is_output")),
                ("one whole step() of the data path (set the register that holds the state, read the same register after the edge)", lambda e: e["read"] in ([e.get("start")] + list(e.get("state_from_input") or ()))),
                ("the data taken out at the output ports (set the register, read the output port)", lambda e: e.get("read_is_output"))]
        for what, f in need:
            if not any(f(e) for e in now):      # one that differs is reported below with its first values
                out.append(f"there is no comparison of {what} with the reference model with every switch of the model on")
    for e in last.values():
        if not e["differ"]:
            continue
        what = f"{lab(e)} differed on {e['differ']} of {e['compared']} inputs with every switch on"
        if set(e["switches_of_model"]) == set(top):
            out.append(what + (f" (first: input {e['first']['input']}, design {e['first']['design']}, wanted {e['first']['wanted']})" if e.get("first") else "")
                       + ": this is a difference inside one step(), in the scope of this order, and the order is finished only when this comparison agrees with every switch on")
        else:
            out.append(what + f" then ({', '.join(e['switches_on'])}); it was not compared again with the switches of the model now")
    return out


def model_is_rtl(tag, where):
    if not gflow.sim(PID, tag)["ok"]:
        raise Stop(f"after {where} the model with no switch differs from the RTL")


def unbooked(tag):
    """The switches of the model of run `tag` that have no entry in its book (read from the files; the host concludes nothing else)."""
    sys.path.insert(0, str(gflow.ROOT / "tool" / "gflow"))
    import ledger
    v = view(tag)
    try:
        booked = {e["switch"] for e in ledger.load(v / "ledger.json")}
    except (ValueError, OSError):
        booked = set()
    return [s for s in (ledger.model_switches(v / "rtl_model.py") or []) if s not in booked]


def book(base, log, out, tag, name, ref, spec):
    """Order LB when the model has switches without an entry in the book, then the host check of the book."""
    if not unbooked(tag):
        out.setdefault("books", []).append({"stage": name, "skipped": "every switch of the model has an entry"})
        return tag
    tag = ga.with_retry(PID, base, log, "LB", tag, "", name, ref=ref, spec=spec)
    tag, _ = host_check(base, log, out, tag, name, ref, spec)
    model_is_rtl(tag, name)
    return tag


# the fact an order A2 gets when an order LF found that the edits of the book are what the switches say, but RtlModel reads a value the RTL does not have (flow f7, 2026-11-22)
MODEL_FACT = (" In this order the simulator run in /code/work/sim_check.txt compares RtlModel with the switches of the book on and rtl_fixed/, the original RTL "
              "with the edits of the book (/code/work/rtl_changes.json): here the RTL is rtl_fixed/. The order before this one found that the edits are what the "
              "switches say and wrote in /code/work/fix_note.md where RtlModel uses a value the RTL does not have at that time. Correct the translation so that "
              "it does what rtl_fixed/ does with the switches on and what the original RTL does with no switch; a switch keeps the change it names. After this "
              "order the host compares RtlModel() with the original RTL and RtlModel with the switches with rtl_fixed/.")


def host_check(base, log, out, tag, stage, ref, spec):
    """The book of the switches applied to the RTL and compared with RtlModel in the simulator; while they differ, one order LF per result (at most three).
    When LF finds that the edits are right but the model reads a value the RTL does not have (fix_note.md), an order A2 corrects the model.
    Returns (tag, corrected): corrected is True when the model was changed, so that the order that relied on it is given again."""
    r = gflow.changes(PID, tag)
    corrected = False
    for name in ("f", "fb", "fc"):
        if r["ok"]:
            break
        if gflow.run_dir(PID, f"{base}-{stage + name}").exists():   # a round continued at this check: the name of an earlier order is not used again
            continue
        prev = tag
        tag = ga.with_retry(PID, base, log, "LF", prev, "", stage + name, sim=prev, ref=ref, spec=spec)
        if (view(tag) / "fix_note.md").exists():
            note = tag
            tag = ga.with_retry(PID, base, log, "A2", tag, MODEL_FACT, stage + name + "m", sim=prev)
            model_is_rtl(tag, stage + name + "m")
            out.setdefault("model_corrected", []).append({"stage": stage, "note": note, "tag": tag})
            corrected = True
            (view(tag) / "fix_note.md").unlink(missing_ok=True)   # the note is answered; a later LF writes its own
        r = gflow.changes(PID, tag)
    out.setdefault("host_checks", []).append({"stage": stage, "tag": tag, "ok": bool(r["ok"]), "first_different": r.get("first_different"), "model_corrected": corrected})
    if not r["ok"]:
        raise Stop(f"after {tag}: the RTL of the book still differs from the model after three corrections")
    return tag, corrected


def top(base, log, out, tag, ref, spec, check_from=None):
    """Stage top: each order of TOP_PLAN, the host check after it; when the check corrected the model, the order is given once more on the corrected model."""
    for step, name, kw in TOP_PLAN:
        for nm in (name, name + "b"):
            if check_from is None:
                tag = ga.with_retry(PID, base, log, step, tag, "", nm, ref=ref, spec=spec, **kw)
                model_is_rtl(tag, nm)
            check_from = None
            tag, corrected = host_check(base, log, out, tag, nm, ref, spec)
            if not corrected:
                break
        else:
            raise Stop(f"after {tag}: the model was corrected again after the second order {step}")
    return tag


def run(base, start="m", carry=None, ref_tag=None, timed_tag=None, skip_b=0, to=None, check_from=None):
    log, out, tag = [], {"pid": PID, "base": base, "from": start}, carry
    ga.MORE = tuple(dict.fromkeys(ga.MORE + ("E", "UA1", "UA2", "UB", "T", "LB", "UD", "UC")))
    spec = None
    todo = STAGES[STAGES.index(start):]
    try:
        if not (gflow.pdir_of(PID) / "rtl").exists():
            gflow.prep(PID)
        (gflow.ROOT / "runs").mkdir(exist_ok=True)
        if "m" in todo:
            ref_tag = ga.with_retry(PID, base, log, "M", None, "")
        ref = [view(ref_tag) / n for n in ("ref_model.py", "ref_model_notes.md")]
        if not all(p.exists() for p in ref):
            raise Stop("the reference model order did not write its two files")
        if "t" in todo or timed_tag is None:
            timed_tag = ga.with_retry(PID, base, log, "T", None, "", "t", ref=ref, spec=SPEC0)
        files = [f for f in view(timed_tag).glob("*.py") if f.name != "timed_check.py"]
        if len(files) != 1:
            raise ga.Unfinished(f"order T left {[f.name for f in files]}: one model file expected")
        spec = SPEC0 + files
        out["ref_tag"], out["timed_tag"], out["timed_model"] = ref_tag, timed_tag, files[0].name
        if "a" in todo:
            tag = ga.order(PID, base, log, "A", None)
            if log[-1]["reason"] not in ("done",) + ga.CUT and not ga.done(PID, tag):
                raise ga.Hang(f"order {tag} ended without DONE (reason: {log[-1]['reason']}); find the cause before it is run again")
            r = gflow.sim(PID, tag)
            for name in ("a2", "a2b"):
                if r["ok"]:
                    break
                tag = ga.order(PID, base, log, "A2", tag, name, sim=tag)
                r = gflow.sim(PID, tag)
            if not r["ok"]:
                raise Stop("the model does not equal the RTL after A2")
            out["stimulus_equals_testbench"] = bool(gflow.stim(PID, tag)["ok"])   # recorded only: the later stages of this flow do not use stimulus.json (the round h2 that gave the start of z1..z14 had none)
        if "b" in todo or "d" in todo or "k" in todo:
            gflow.BASE_RECORD = gflow.base_record(PID, tag)      # the model with no switch equals the RTL here (host check after A, or the run the round is continued from)
        if "b" in todo:
            sc = ga.b_scopes(PID)
            for n, (s0, rep) in enumerate(sc, 1):
                if n <= skip_b:
                    continue
                name0 = "b" if len(sc) == 1 else f"b{n}"
                parts = B_PARTS.get(n, [("", s0)])
                for part, s in parts:
                    name = name0 + part
                    ports = n == len(sc) and (part, s) == parts[-1]   # the last order of the top module: the data path from port to port is compared (skill point 5)
                    prev = tag
                    try:
                        tag = ga.with_retry(PID, base, log, "B", tag, ga.SIM_FACT, name, scope=s, report=rep, ref=ref, spec=SPEC0, ports=ports,
                                            cut_more=lambda t, prev=prev, ports=ports: b_facts(t, prev, ports, finished=False))
                    except ga.Unfinished as e:       # flow f7: order UD and the host gate after it make up for what B did not finish (2026-11-22)
                        tag = log[-1]["tag"]
                        out.setdefault("b_unfinished", []).append(str(e))
                    if not ga.done(PID, tag):       # no later order on an unfinished order B: the cause is found first (f7-11, f7-12; user agreed 2026-11-24)
                        out.setdefault("b_unfinished", []).append(tag)
                        raise Stop(f"order {tag} is not finished after its continuation; the cause is found before the next order")
                    else:
                        extra, suffix = b_facts(tag, prev, ports), "h"
                        while extra and len(suffix) <= 2:   # continuations "h", "hh" (host check of order B, NAMES.md; DONE is not accepted while the facts remain, 2026-11-23)
                            tag = ga.order(PID, base, log, "B", tag, name + suffix, fact=ga.SIM_FACT + extra, scope=s, report=rep, ref=ref, spec=SPEC0, ports=ports)
                            out.setdefault("b_checked", []).append({"tag": tag, "fact": extra})
                            if not ga.done(PID, tag):
                                out.setdefault("b_unfinished", []).append(tag)
                                break
                            extra, suffix = b_facts(tag, prev, ports), suffix + "h"   # prev stays the order before this B order: the log of all its continuations is read
                        if extra and ga.done(PID, tag):
                            out.setdefault("b_facts_left", []).append({"tag": tag, "fact": extra})
                    model_is_rtl(tag, name)
        if to == "b":
            raise Stop("stopped after stage b (--to b)")
        if "d" in todo:
            tag = book(base, log, out, tag, "lb1", ref, spec)   # the book first: UD edits lines that switches of B changed (dry run UD-01, 2026-11-22)
            step, name, kw = D_PLAN
            kw = dict(kw)
            if not (view(tag) / "block_check_2.md").exists():   # B was cut off before its report
                kw["scope"] = ("the module aes128_decrypt, which has the module aes128_key_expansion inside it (the pieces of aes128_decrypt were checked by an earlier order "
                               "that was cut off before it wrote block_check_2.md: its switches are in RtlModel and its notes in /code/work; the pieces of aes128_key_expansion "
                               "were checked in block_check_1.md)")
            fact = ""
            for nm in (name, name + "b", name + "c"):
                tag = ga.with_retry(PID, base, log, step, tag, fact, nm, ref=ref, spec=spec, **kw)
                model_is_rtl(tag, nm)
                tag, _ = host_check(base, log, out, tag, nm, ref, spec)
                g = gflow.data_gate(PID, tag, ref, spec)
                out.setdefault("data_gates", []).append({"tag": tag, "ok": g["ok"], "ran": g["ran"], "dead": g.get("dead"), "final": g.get("final")})
                if g["ok"]:
                    break
                if not g["ran"]:
                    raise Stop(f"after {tag}: blockfacts did not run on the description the order left (see sim/blockfacts.txt)")
                fact = GATE_FACT.format(print=g["text"])
            else:
                raise Stop(f"after {tag}: the data path alone still does not reach the final step of the record after three orders UD")
        if to == "d":
            raise Stop("stopped after stage d (--to d)")
        if "k" in todo:
            for step, name, kw in K_PLAN:
                tag = ga.with_retry(PID, base, log, step, tag, "", name, ref=ref, **kw)
                model_is_rtl(tag, name)
        if check_from is None:
            tag = book(base, log, out, tag, "lb2", ref, spec)
        gflow.BASE_RECORD = gflow.base_record(PID, tag)
        tag = top(base, log, out, tag, ref, spec, check_from)
        g = grader.grade(PID, view(tag) / "rtl_fixed", image="lora-rtl:dev")
        out["passed"], out["tests"] = g.get("passed"), g.get("tests")
    except (ga.Hang, ga.Unfinished, Stop) as e:
        out["stopped"] = str(e)
    except SystemExit as e:
        out["stopped"] = f"exit: {e}"
    out["final_tag"] = tag
    out["minutes"] = sum(r["minutes"] or 0 for r in log)
    print(json.dumps(out), flush=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", nargs="?")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--from", dest="start", default="m", choices=STAGES)
    ap.add_argument("--carry", help="run tag whose files the first order of the stage starts from (stages b, k, top)")
    ap.add_argument("--ref", help="run tag of order M (needed when the round does not start at m)")
    ap.add_argument("--skip-b", type=int, default=0, help="with --from b: leave out the first N orders B (the run of --carry already holds them)")
    ap.add_argument("--to", choices=["b", "d"], help="stop after this stage")
    ap.add_argument("--timed", help="run tag of order T (needed when the round starts at top)")
    ap.add_argument("--check-only", action="store_true", help="with --from top: the order UC of --carry is done; start at the host check after it")
    a = ap.parse_args()
    if a.check:
        sys.exit(0 if check() else 1)
    if not a.base:
        ap.error("BASE is needed")
    if a.start != "m" and not a.ref:
        ap.error("--ref is needed when the round does not start at m")
    if a.start in ("b", "k", "top") and not a.carry:
        ap.error("--carry is needed for this stage")
    if a.start == "top" and not a.timed:
        ap.error("--timed is needed when the round starts at top")
    if a.check_only and a.start != "top":
        ap.error("--check-only needs --from top")
    run(a.base, a.start, a.carry, a.ref, a.timed, a.skip_b, a.to, a.carry if a.check_only else None)
