"""gflow for one problem from start to end, without a person between the orders.

  python3 -m orch.gflow_auto --pid PID --base T [T2 ...] [--model] [--from STEP --carry TAG]

(--model: M, a reference model from the task and the documents, given to B, C1, C2) -> A -> simcheck (A2 while the model differs from the RTL, at most twice) -> B (one order per module that instantiates others, the lowest first) -> C1 -> C2 (C1 and C2 only for a design with a clock)
-> D -> simcheck of rtl_fixed against RtlModel(fix="all") (D2 while they differ, at most twice) -> hidden harness.
An order that reaches its time limit (or the context limit of orch.gflow) without DONE is given once more in a new cell with the files it left (its notes.md says where it was).
C1 and C2 are continued a second time if needed; when one of them is still not finished the flow stops (D is not given an unfinished check).
An order that ends by itself or hangs without DONE stops the driver: the cause is found before anything is run again.
After B, C1 and C2 the model with no switch must still equal the RTL; if it does not, the flow stops (a person looks).
Every order is a new cell: orch.gflow.run. One line per problem is appended to data/pilot/gflow_auto.jsonl.
"""
import argparse
import json
import re
import time

from . import gflow, grade as grader

OUT = gflow.ROOT / "data" / "pilot" / "gflow_auto.jsonl"
SIM_FACT = ("A simulator run of the original RTL against RtlModel() with no switch (4 random stimulus scenarios) "
            "showed no difference in the outputs.")
CUT_FACT = (" An earlier run of this order ended before it was finished: the notes file this order names, the scripts and any switches or files it had "
            "started are in /code/work (not all checked).")
SCOPE = "the whole design: every module (the modules that instantiate no other module first), piece by piece"
OWN_FACT = (" An earlier run of this order ended by itself before the order was finished (the file DONE was not written): what it had done is in /code/work (not all checked); "
            "the order is the whole text above, not only its last step.")
CUT = ("timeout", "context")   # ends that are continued in a new cell: the time limit, and a conversation too large for the backend's memory
MORE = ("C1", "C2A", "C2B")   # orders that are continued a second time; the flow stops when they are still not finished
ORDER = ["A", "B", "C1", "C2A", "C2B", "D"]


class Hang(Exception):
    pass


class Unfinished(Exception):
    pass


def done(pid, tag):
    return (gflow.run_dir(pid, tag) / "view" / "DONE").exists()


def b_scopes(pid):
    """One order B per module that instantiates others (the lowest first), each with the submodules that instantiate nothing; a design of one module is one order."""
    text = "\n".join(f.read_text() for f in sorted((gflow.pdir_of(pid) / "rtl").iterdir()))
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
    mods = dict(re.findall(r"\bmodule\s+(\w+)(.*?)\bendmodule\b", text, flags=re.S))
    kids = {m: [k for k in mods if k != m and re.search(r"\b%s\b\s*(#\s*\(|\w+\s*\()" % k, body)] for m, body in mods.items()}
    depth = {}

    def dep(m):
        if m not in depth:
            depth[m] = 0
            depth[m] = 1 + max([dep(k) for k in kids[m]], default=-1)
        return depth[m]
    parents = sorted((m for m in mods if kids[m]), key=lambda m: (dep(m), m))
    if not parents:
        return [("the module%s %s, piece by piece" % ("s" if len(mods) > 1 else "", ", ".join(sorted(mods))), "block_check.md")]
    out, seen = [], set()
    for n, m in enumerate(parents, 1):
        leaves = [k for k in kids[m] if not kids[k] and k not in seen]
        before = [k for k in kids[m] if kids[k]]
        t = f"the module {m}" + (f" with the modules it instantiates that instantiate nothing ({', '.join(leaves)})" if leaves else "")
        t += ", piece by piece, and as a unit where it needs several cycles to finish"
        if before:
            t += " (" + ", ".join(f"its submodule {k} was checked in block_check_{[x for x in parents].index(k) + 1}.md" for k in before) + ")"
        out.append((t, f"block_check_{n}.md"))
        seen.update(leaves)
    return out


def order(pid, base, log, step, carry, name=None, **kw):
    tag = f"{base}-{name or step.lower()}"
    row = gflow.run(pid, tag, step, carry, **kw)
    res = row.get("order_result") or {}
    log.append({"tag": tag, "step": step, "scope": kw.get("scope"), "reason": res.get("reason"), "minutes": round((res.get("seconds") or 0) / 60), "requests": res.get("requests"), "done": done(pid, tag)})
    print(json.dumps(log[-1]), flush=True)
    return tag


def cut_facts(pid, tag, start, n):
    """Facts of the host for a continuation: which continuation it is, the last tool run the cut order recorded, and the switches it added to the model that have no entry in the book.
    Read from the files the order left; nothing is concluded from them."""
    import sys
    sys.path.insert(0, str(gflow.ROOT / "tool" / "gflow"))
    import ledger
    view = gflow.run_dir(pid, tag) / "view"
    out = [f" Facts from the host about the files it left (this is continuation {n} of the order):"]
    log_file = view / "tool_runs.log"
    if log_file.exists():
        runs = log_file.read_text().split("\n--- ")
        last = [l.rstrip() for l in runs[-1].splitlines() if l.strip()]
        if last:
            out.append(f" {len(runs)} tool runs are recorded in tool_runs.log; the last one was `{last[0].lstrip('- ').strip()}` and its print ended:\n" + "\n".join("    " + l.strip()[:300] for l in last[1:][-6:]))
    model = view / "rtl_model.py"
    if model.exists():
        now = ledger.model_switches(model) or []
        before = (ledger.model_switches(gflow.run_dir(pid, start) / "view" / "rtl_model.py") or []) if start else []
        try:
            booked = {e["switch"] for e in ledger.load(view / "ledger.json")}
        except ValueError:
            booked = set()
        new = [s for s in now if s not in before]
        out.append(f" SWITCHES of the model has {len(now)} names; added since this order was first given: {', '.join(new) or 'none'}."
                   + (f" Of these, without an entry in the book of the switches: {', '.join(s for s in new if s not in booked)}." if any(s not in booked for s in new) else ""))
    return "\n".join(out)


def with_retry(pid, base, log, step, carry, fact, name=None, **kw):
    start = carry
    name = name or step.lower()
    tag = order(pid, base, log, step, carry, name, fact=fact, **kw)
    if not done(pid, tag):
        own = log[-1]["reason"] == "finished"   # the agent ended its turn without DONE: continued once (user decision 2026-11-20); a hang still stops the driver
        if log[-1]["reason"] not in CUT and not own:   # the order hung or failed: the cause is found before anything is run again
            raise Hang(f"order {tag} ended without DONE (reason: {log[-1]['reason']}); find the cause before it is run again")
        tag = order(pid, base, log, step, tag, name + "r", fact=fact + (OWN_FACT if own else CUT_FACT) + cut_facts(pid, tag, start, 1), **kw)
        if own and not done(pid, tag) and log[-1]["reason"] not in CUT:
            raise Hang(f"order {tag} ended without DONE a second time (reason: {log[-1]['reason']}); find the cause before it is run again")
        if step in MORE and not done(pid, tag):     # the whole-operation orders: one more continuation, and no later order on an unfinished one
            if log[-1]["reason"] not in CUT:
                raise Hang(f"order {tag} ended without DONE (reason: {log[-1]['reason']}); find the cause before it is run again")
            tag = order(pid, base, log, step, tag, name + "rr", fact=fact + CUT_FACT + cut_facts(pid, tag, start, 2) + " This is the last continuation.", **kw)
            if not done(pid, tag):
                raise Unfinished(f"order {tag} is not finished after two continuations")
    return tag


def auto(pid, base, start="A", carry=None, model=False, ref_tag=None):
    log = []
    out = {"pid": pid, "base": base, "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "orders": log}
    try:
        if not gflow.pdir_of(pid).exists():
            gflow.prep(pid)
        steps = ORDER[ORDER.index(start):]
        tag = carry
        ref = None
        if model or ref_tag:
            mt = ref_tag or with_retry(pid, base, log, "M", None, "")
            ref = [p for p in (gflow.run_dir(pid, mt) / "view" / n for n in ("ref_model.py", "ref_model_notes.md")) if p.exists()]
            out["ref_model"] = [str(p) for p in ref]
            if len(ref) < 2:
                out["stopped"] = "the reference model order did not write its two files"
                return out
        if "A" in steps:
            tag = order(pid, base, log, "A", None)
            if log[-1]["reason"] not in ("done",) + CUT:
                raise Hang(f"order {tag} ended without DONE (reason: {log[-1]['reason']}); find the cause before it is run again")
            r = gflow.sim(pid, tag)
            for name in ("a2", "a2b"):
                if r["ok"]:
                    break
                tag = order(pid, base, log, "A2", tag, name, sim=tag)
                r = gflow.sim(pid, tag)
            out["model_equals_rtl"] = bool(r["ok"])
            if not r["ok"]:
                out["stopped"] = "the model does not equal the RTL after A2"
                return out
            st = gflow.stim(pid, tag)
            out["stimulus_equals_testbench"] = bool(st["ok"])
            if not st["ok"]:
                out["stopped"] = "stimulus.json does not do what the testbench does (see sim/stim_check.txt)"
                return out
        itf = json.loads((gflow.run_dir(pid, tag) / "view" / "interface.json").read_text())
        todo = []
        for step in steps:
            if step == "B":
                sc = b_scopes(pid)
                todo += [("B", "b" if len(sc) == 1 else f"b{n}", {"scope": s, "report": r}) for n, (s, r) in enumerate(sc, 1)]
            elif step in ("C1", "C2A", "C2B") and itf.get("clock"):
                todo.append((step, step.lower(), {}))
        for step, name, kw in todo:
            if ref is not None:
                kw["ref"] = ref
            tag = with_retry(pid, base, log, step, tag, SIM_FACT, name, **kw)
            if not gflow.sim(pid, tag)["ok"]:
                out["stopped"] = f"after {name} the model with no switch differs from the RTL"
                return out
        tag = with_retry(pid, base, log, "D", tag, "")
        if not (gflow.run_dir(pid, tag) / "view" / "rtl_fixed").exists():
            out["stopped"] = "no rtl_fixed"
            return out
        r = gflow.sim(pid, tag, fixed=True)
        for name in ("d2", "d2b"):
            if r["ok"]:
                break
            tag = order(pid, base, log, "D2", tag, name, sim=tag)
            r = gflow.sim(pid, tag, fixed=True)
        out["fixed_equals_model"] = bool(r["ok"])
        out["final_tag"] = tag
        g = grader.grade(pid, gflow.run_dir(pid, tag) / "view" / "rtl_fixed", image="lora-rtl:dev")
        out["passed"], out["tests"] = g.get("passed"), g.get("tests")
        return out
    except Unfinished as e:
        out["stopped"] = str(e)
        return out
    except Hang as e:
        out["stopped"], out["hang"] = str(e), True
        return out
    except SystemExit as e:
        out["stopped"] = f"exit: {e}"
        return out
    except Exception as e:  # noqa: BLE001
        import traceback
        out["stopped"] = f"error: {e!r}"
        out["trace"] = traceback.format_exc()[-1500:]
        return out
    finally:
        with open(OUT, "a") as f:
            f.write(json.dumps(out, default=str) + "\n")
        print(json.dumps({k: v for k, v in out.items() if k != "orders"}, default=str), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", required=True, nargs="+")
    ap.add_argument("--base", required=True, nargs="+")
    ap.add_argument("--from", dest="start", default="A", choices=ORDER)
    ap.add_argument("--carry")
    ap.add_argument("--ref", help="tag of an earlier M run of this problem whose reference model is used (only with one --base)")
    ap.add_argument("--model", action="store_true", help="first an order that writes a reference model from the task and the documents")
    a = ap.parse_args()
    for b in a.base:
        for p in a.pid:
            if auto(p, b, a.start, a.carry, a.model, a.ref).get("hang"):
                raise SystemExit("stopped: an order hung or ended by itself")
