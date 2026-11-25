"""gflow for one problem from the first order to the hidden harness, from a problem file data/problems/NAME.json.

  python3 -m orch.run_flow NAME BASE [--from STAGE --carry TAG] [--ref TAG] [--timed TAG]

The problem file says what the architecture decided for this problem and which orders its modules get:
  {"pid": the CVDP id,
   "spec_dir": folder under data/stages/gflow with the timed specification of the architecture, or null ("not provided": no timed model, the port orders are left out),
   "timed_model": "given" (the architecture's model is in spec_dir and named by its given.json) or "order" (order T writes it from the schedule),
   "lower_units": [[step, name, {scope, report, script, notes}], ...]   orders for modules below the top that are units of their own (may be empty),
   "top": [[step, name, {scope, report, notes}], ...]}                  orders for the top module after the book of the switches is filled (LB)

Stages: m (reference model) -> a (RTL to Python; host: model = RTL) -> b (pieces against the specification, one order per module that instantiates others)
-> k (lower_units) -> t (timed model, when "order") -> top (LB, then the orders of "top"; after each the host applies the book to the RTL and compares it
with the model in a simulator, and an order LF corrects the entry it names) -> hidden harness.
One JSON line per order is printed, and one at the end ("passed": the hidden harness; "stopped": why the flow stopped itself).
"""
import argparse
import json
import os

os.environ.setdefault("GFLOW_DROP_REASONING", "1")
os.environ.setdefault("GFLOW_KEEP_REASONING", "6000")
from . import gflow, gflow_auto as ga
from . import grade as grader

STAGES = ["m", "a", "b", "k", "t", "top"]


class Stop(Exception):
    pass


def run(cfg, base, start="m", carry=None, ref_tag=None, timed_tag=None):
    pid = cfg["pid"]
    log, out, tag = [], {"pid": pid, "base": base, "from": start}, carry
    ga.MORE = tuple(dict.fromkeys(ga.MORE + ("E", "UA1", "UA2", "UB", "T", "TN", "LB", "UD", "UC", "UP")))
    todo = STAGES[STAGES.index(start):]
    spec0 = sorted((gflow.D / cfg["spec_dir"]).iterdir()) if cfg.get("spec_dir") else []

    def view(t):
        return gflow.run_dir(pid, t) / "view"

    def model_is_rtl(t, where):
        if not gflow.sim(pid, t)["ok"]:
            raise Stop(f"after {where} the model with no switch differs from the RTL")

    def host_check(t, stage, ref, spec):
        r = gflow.changes(pid, t)
        for name in ("f", "fb", "fc"):
            if r["ok"]:
                break
            t = ga.order(pid, base, log, "LF", t, stage + name, sim=t, ref=ref, spec=spec, fact="")
            if not ga.done(pid, t):
                raise ga.Unfinished(f"order {t} is not finished")
            if (view(t) / "fix_note.md").exists():
                raise Stop(f"after {t}: the agent says a switch of the model uses a value the RTL does not have (fix_note.md); a person looks")
            r = gflow.changes(pid, t)
        out.setdefault("host_checks", []).append({"stage": stage, "tag": t, "ok": bool(r["ok"]), "first_different": r.get("first_different")})
        if not r["ok"]:
            raise Stop(f"after {t}: the RTL of the book still differs from the model after three corrections")
        return t
    try:
        if not (gflow.pdir_of(pid) / "rtl").exists():
            gflow.prep(pid)
        (gflow.ROOT / "runs").mkdir(exist_ok=True)
        if "m" in todo:
            ref_tag = ga.with_retry(pid, base, log, "M", None, "")
        ref = [view(ref_tag) / n for n in ("ref_model.py", "ref_model_notes.md")]
        if not all(p.exists() for p in ref):
            raise Stop("the reference model order did not write its two files")
        if "a" in todo:
            tag = ga.order(pid, base, log, "A", None)
            if log[-1]["reason"] not in ("done",) + ga.CUT and not ga.done(pid, tag):
                raise ga.Hang(f"order {tag} ended without DONE (reason: {log[-1]['reason']}); find the cause before it is run again")
            r = gflow.sim(pid, tag)
            for name in ("a2", "a2b"):
                if r["ok"]:
                    break
                tag = ga.order(pid, base, log, "A2", tag, name, sim=tag)
                r = gflow.sim(pid, tag)
            if not r["ok"]:
                raise Stop("the model does not equal the RTL after A2")
        if "b" in todo or "k" in todo:
            gflow.BASE_RECORD = gflow.base_record(pid, tag)      # the model with no switch equals the RTL here (host check after A, or the run the round is continued from)
        if "b" in todo:
            sc = ga.b_scopes(pid)
            for n, (s, rep) in enumerate(sc, 1):
                name = "b" if len(sc) == 1 else f"b{n}"
                tag = ga.with_retry(pid, base, log, "B", tag, ga.SIM_FACT, name, scope=s, report=rep, ref=ref)
                if not ga.done(pid, tag):        # the later orders take the pieces as checked: an unfinished B stops the round (r2, 2026-11-21)
                    raise ga.Unfinished(f"order {tag} is not finished after its continuation")
                model_is_rtl(tag, name)
        if "k" in todo:
            for step, name, kw in cfg.get("lower_units", []):
                tag = ga.with_retry(pid, base, log, step, tag, "", name, ref=ref, **kw)
                model_is_rtl(tag, name)
        spec = list(spec0)
        if spec0 and cfg.get("timed_model") == "order":
            if "t" in todo:
                timed_tag = ga.with_retry(pid, base, log, cfg.get("t_step", "T"), None, "", "t", ref=ref, spec=spec0)
            files = [f for f in view(timed_tag).glob("*.py") if f.name != "timed_check.py"]
            if len(files) != 1:
                raise ga.Unfinished(f"order T left {[f.name for f in files]}: one model file expected")
            spec = spec0 + files
        out["ref_tag"], out["timed"] = ref_tag, (cfg.get("timed_model") if spec0 else "not provided")
        tag = ga.with_retry(pid, base, log, "LB", tag, "", "lb", ref=ref, spec=spec or None)
        tag = host_check(tag, "lb", ref, spec or None)
        model_is_rtl(tag, "lb")
        gflow.BASE_RECORD = gflow.base_record(pid, tag)
        for step, name, kw in cfg.get("top", []):
            if step in ("UP", "UC") and not spec0:
                out.setdefault("skipped", []).append(f"{step}: no timed specification (the ports are not judged)")
                continue
            tag = ga.with_retry(pid, base, log, step, tag, "", name, ref=ref, spec=spec, **kw)
            model_is_rtl(tag, name)
            tag = host_check(tag, name, ref, spec)
        g = grader.grade(pid, view(tag) / "rtl_fixed", image="lora-rtl:dev")
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
    ap.add_argument("problem")
    ap.add_argument("base")
    ap.add_argument("--from", dest="start", default="m", choices=STAGES)
    ap.add_argument("--carry")
    ap.add_argument("--ref")
    ap.add_argument("--timed")
    a = ap.parse_args()
    run(json.loads((gflow.ROOT / "data" / "problems" / f"{a.problem}.json").read_text()), a.base, a.start, a.carry, a.ref, a.timed)
