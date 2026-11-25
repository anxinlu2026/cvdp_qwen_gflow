"""Give Qwen an order of the flow to read, not to carry out: it writes the order in its own words, how it would carry it out, and what is unclear
(user request 2026-11-25). The cell is the one the order itself would get (same files, skills, carried work).
  python3 -m orch.read_order read-aes0005-B1-01 --carry r1-a2 --ref r1-m"""
import argparse
import json

from . import gflow, gflow_auto as ga, run_aes0005 as ra

PRE = """This order is about another order. The text between the two lines of dashes below is an order that will be given later, in a cell like this one (the files it names are here). Do not carry it out: do not change rtl_model.py and do not write its report.

Read it, and read the files it says to read first (/code/lib/usage.md and the two skills) as far as you need to understand it. Then write /code/work/order_reading.md with three parts:
1. The order in your own words, as short as you can make it without losing anything it asks for.
2. How you would carry it out: the steps in the sequence you would do them, and for each step the files you would read or write and the functions of the libraries you would call.
3. What is not clear to you: each sentence (quoted) that you do not understand, that can be read in more than one way, that seems to contradict another one, or that says again what another sentence already said; and anything you would need to know that the order does not say.

When order_reading.md is written, create the empty file /code/work/DONE. This order ends after {M} minutes.

------------------------------------------------------------
"""
POST = "\n------------------------------------------------------------\n"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--carry", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--scope", type=int, default=1, help="which scope of B the order is for")
    ap.add_argument("--minutes", type=int, default=30)
    a = ap.parse_args()
    s, rep = ga.b_scopes(ra.PID)[a.scope - 1]
    gflow.BASE_RECORD = gflow.base_record(ra.PID, a.carry)
    inner = gflow.compose

    def compose(pid, step, *args, **kw):
        args, kw2 = list(args), dict(kw)
        if len(args) > 4:               # the order that is read keeps its own time limit
            args[4] = 45
        else:
            kw2["minutes"] = 45
        inp, order = inner(pid, step, *args, **kw2)
        return inp, PRE.replace("{M}", str(a.minutes)) + order + POST
    gflow.compose = compose
    row = gflow.run(ra.PID, a.tag, "B", a.carry, scope=s, report=rep, fact=ga.SIM_FACT, ref=[ra.view(a.ref) / n for n in ("ref_model.py", "ref_model_notes.md")], spec=ra.SPEC0, minutes=a.minutes)
    res = row.get("order_result") or {}
    print(json.dumps({"tag": a.tag, "reason": res.get("reason"), "minutes": round((res.get("seconds") or 0) / 60), "requests": res.get("requests")}))
