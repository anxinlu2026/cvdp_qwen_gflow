"""gflow for cvdp_agentic_AES_encryption_decryption_0005 from the first order to the hidden harness, without a person between the orders.

  python3 -m orch.run_aes0005 --check
  python3 -m orch.run_aes0005 BASE [--from STAGE --carry TAG] [--ref TAG] [--timed TAG]

Stages, in this order (name of the stage: orders):
  m     M    a reference model from the task and the documents only (no RTL)
  a     A    the RTL translated to a Python model with no change; the host compares it with the RTL in a simulator (A2 while they differ, at most twice)
  b     B    one order per module that instantiates others, lowest first: every piece against the documents (switches for the faults found)
  k     E, UA1, UA2, UB   the lower module (key expansion) as a unit: one edge, the walk at its ports, switches, sequence and values
  t     T    a timed specification model of the top module from the schedule in data/stages/gflow/spec_aes0005 (no RTL)
  top   LB, UX, UY   the top module: the switches so far entered in the book with their RTL edits; the data path against the step record of the reference
                     (UX); control and handshake against the timed model (UY). After each the host applies the book to the RTL and compares with the model in a
                     simulator; while they differ an order LF corrects the one entry the host names (at most three).
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
import subprocess
import sys

os.environ.setdefault("GFLOW_DROP_REASONING", "1")       # the proxy does not send the thinking of earlier answers back to the model
os.environ.setdefault("GFLOW_KEEP_REASONING", "6000")    # but the last answer keeps the end of its thinking (its conclusion and plan)
from . import dataset, gflow, gflow_auto as ga
from . import grade as grader

PID = "cvdp_agentic_AES_encryption_decryption_0005"
STAGES = ["m", "a", "b", "k", "t", "top"]
S1 = "the module aes128_key_expansion (its pieces were checked in block_check_1.md)"
S1U = S1[:-1] + "; its one-edge report is edge_check_1.md with the script edge_table_1.py)"
S2U = ("the module aes128_decrypt, which has the module aes128_key_expansion inside it (the pieces of aes128_decrypt were checked in block_check_2.md; "
       "aes128_key_expansion has edge_check_1.md and unit_check_1.md)")
K_PLAN = [("E", "e1", dict(scope=S1, report="edge_check_1.md", script="edge_table_1.py", notes="notes_e_1.md")),
          ("UA1", "u1a", dict(scope=S1U, report="unit_check_1.md", script="walk_check_1.py", notes="notes_ua1_1.md")),
          ("UA2", "u1b", dict(scope=S1U, report="unit_check_1.md", script="walk_check_1.py", notes="notes_ua2_1.md")),
          ("UB", "u1c", dict(scope=S1U, report="unit_check_1.md", script="edge_table_1.py", notes="notes_ub_1.md"))]
TOP_PLAN = [("UX", "ud", dict(scope=S2U, report="unit_check_2.md", notes="notes_ud_2.md")),
            ("UY", "uc", dict(scope=S2U, report="unit_check_2.md", notes="notes_uc_2.md"))]
SPEC0 = sorted((gflow.D / "spec_aes0005").iterdir())


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


def model_is_rtl(tag, where):
    if not gflow.sim(PID, tag)["ok"]:
        raise Stop(f"after {where} the model with no switch differs from the RTL")


def host_check(base, log, out, tag, stage, ref, spec):
    """The book of the switches applied to the RTL and compared with RtlModel in the simulator; while they differ, one order LF per result (at most three)."""
    r = gflow.changes(PID, tag)
    for name in ("f", "fb", "fc"):
        if r["ok"]:
            break
        tag = ga.order(PID, base, log, "LF", tag, stage + name, sim=tag, ref=ref, spec=spec, fact="")
        if not ga.done(PID, tag):
            raise ga.Unfinished(f"order {tag} is not finished")
        if (view(tag) / "fix_note.md").exists():
            raise Stop(f"after {tag}: the agent says a switch of the model uses a value the RTL does not have (fix_note.md); a person looks")
        r = gflow.changes(PID, tag)
    out.setdefault("host_checks", []).append({"stage": stage, "tag": tag, "ok": bool(r["ok"]), "first_different": r.get("first_different")})
    if not r["ok"]:
        raise Stop(f"after {tag}: the RTL of the book still differs from the model after three corrections")
    return tag


def run(base, start="m", carry=None, ref_tag=None, timed_tag=None):
    log, out, tag = [], {"pid": PID, "base": base, "from": start}, carry
    ga.MORE = tuple(dict.fromkeys(ga.MORE + ("E", "UA1", "UA2", "UB", "T", "LB", "UX", "UY")))
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
        if "b" in todo:
            sc = ga.b_scopes(PID)
            for n, (s, rep) in enumerate(sc, 1):
                name = "b" if len(sc) == 1 else f"b{n}"
                tag = ga.with_retry(PID, base, log, "B", tag, ga.SIM_FACT, name, scope=s, report=rep, ref=ref)
                model_is_rtl(tag, name)
        if "k" in todo:
            for step, name, kw in K_PLAN:
                tag = ga.with_retry(PID, base, log, step, tag, "", name, ref=ref, **kw)
                model_is_rtl(tag, name)
        if "t" in todo:
            timed_tag = ga.with_retry(PID, base, log, "T", None, "", "t", ref=ref, spec=SPEC0)
        files = [f for f in view(timed_tag).glob("*.py") if f.name != "timed_check.py"]
        if len(files) != 1:
            raise ga.Unfinished(f"order T left {[f.name for f in files]}: one model file expected")
        spec = SPEC0 + files
        out["ref_tag"], out["timed_tag"], out["timed_model"] = ref_tag, timed_tag, files[0].name
        tag = ga.with_retry(PID, base, log, "LB", tag, "", "lb", ref=ref, spec=spec)
        tag = host_check(base, log, out, tag, "lb", ref, spec)
        model_is_rtl(tag, "lb")
        gflow.BASE_RECORD = gflow.base_record(PID, tag)
        for step, name, kw in TOP_PLAN:
            tag = ga.with_retry(PID, base, log, step, tag, "", name, ref=ref, spec=spec, **kw)
            model_is_rtl(tag, name)
            tag = host_check(base, log, out, tag, name, ref, spec)
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
    ap.add_argument("--timed", help="run tag of order T (needed when the round starts at top)")
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
    run(a.base, a.start, a.carry, a.ref, a.timed)
