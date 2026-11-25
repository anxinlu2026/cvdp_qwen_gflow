"""blockfacts: from which steps of the reference's record each piece of the data path of ONE unit lands on the record (host).

It uses the description and the model of stepfacts (/code/work/handshake.json, /code/work/rtl_model.py) and part 1 of
stepfacts: the data register is set to a step of the record, the control registers to every value in turn, and ONE edge
is run (the unit below has finished). Every signal of the model with the shape of the data register is a piece of the
chain inside that edge. A piece lands on the record from step K when, for some control value, its value after the edge
is a later step of the record.

    a piece that lands from no step:  its value is never a step of the record. Either it is wrong, or one it reads is
                                      wrong (a piece after a wrong one in the same edge cannot land), or it is not a
                                      stage of the record at all (a part of a stage, such as a partial product).
    a piece that lands from a step:   from this step it computes what the specification computes.

The tool prints facts. It does not order the pieces by the data flow, it does not say which piece is wrong, and it
changes nothing. With --confirm it also takes each switch out alone and prints from which steps the data register no
longer goes on: the steps that this switch is needed for.

usage: python3 blockfacts.py DESCRIPTION [--model PATH] [--fix a,b|all] [--confirm] [--json OUT]
In Python: blockfacts.measure(description, fix=("all",), model=...) -> {"N", "goes", "pieces": {name: [steps]}, "names"}
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stepfacts  # noqa: E402
import sigdump  # noqa: E402


def measure(description, fix=("all",), model="/code/work/rtl_model.py"):
    r = stepfacts.measure(description, tuple(fix) or ("none",), model)
    u, p, hs = r["unit"], r["part1"], r["hs"]
    need = hs.get("needs_before", {})
    prime = next((need[m] for m in hs["modes"] if need.get(m)), list(hs["modes"])[0])
    fl = [c[u.arr] for c in u.flat(u.record(prime, hs["data"][0], []))]
    land = {}
    for k in range(p["N"]):
        for c in r["values"]:
            for h, t in u.pieces(p["info"][(k, c)][3], fl, k):
                land.setdefault(h, set())
                if t.startswith("= step") and int(t.split()[-1]) > k:
                    land[h].add(k)
    return {"N": p["N"], "names": p["names"], "goes": sorted(p["goes"]), "dead": list(p["dead"]), "final": bool(p["final"]), "data": u.data, "fix": list(r["fix"]),
            "arrangement": r["arrangement"][0], "arrangement_given": r["arrangement"][2],
            "pieces": {h: sorted(v) for h, v in land.items()}}


def confirm(description, model="/code/work/rtl_model.py"):
    names = list(sigdump.load_model(model).RtlModel.SWITCHES)
    full = set(stepfacts.measure(description, tuple(names) or ("none",), model)["part1"]["goes"])
    out = {}
    for s in names:
        rest = tuple(x for x in names if x != s) or ("none",)
        out[s] = sorted(full - set(stepfacts.measure(description, rest, model)["part1"]["goes"]))
    return out


def _steps(ks):
    return ", ".join(map(str, ks)) if ks else "none"


def text(m, conf=None):
    L = [f"blockfacts  switches: {', '.join(m['fix']) or 'none'}   data register: {m['data']}   record: steps 0..{m['N']}",
         f"arrangement: {m['arrangement']}" + ("" if m["arrangement_given"] else "   (NOT given in the description)"),
         f"the data register goes on to a later step from: {_steps(m['goes'])}",
         "from the load, the data path alone (control forced) " + ("reaches the final step" if m["final"] else "does NOT reach the final step") + ("" if not m["dead"] else f"; it is stuck at step {_steps(m['dead'])}"),
         "pieces of the chain (signals with the shape of the data register), in the order of the model; from which steps each lands on the record:"]
    w = max(len(h) for h in m["pieces"]) if m["pieces"] else 0
    for h, ks in m["pieces"].items():
        L.append(f"  {h:{w}s}  " + (f"lands from steps {_steps(ks)}" if ks else "lands from NO step"))
    if conf is not None:
        L.append("switches taken out alone: the steps from which the data register then no longer goes on")
        for s, ks in conf.items():
            L.append(f"  {s}: " + (_steps(ks) if ks else "none (the chain does not show what this switch is needed for)"))
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("description")
    ap.add_argument("--model", default="/code/work/rtl_model.py")
    ap.add_argument("--fix", default="all")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    try:
        m = measure(a.description, tuple(x for x in a.fix.split(",") if x), a.model)
        conf = confirm(a.description, a.model) if a.confirm else None
    except stepfacts.DescriptionError as ex:
        print(f"blockfacts: not run (the description: {ex})")
        return 2
    print("\n".join(text(m, conf)))
    if a.json:
        json.dump({"measure": m, "confirm": conf}, open(a.json, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
