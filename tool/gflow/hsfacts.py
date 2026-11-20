"""hsfacts: the handshake of ONE unit, measured, next to a timed specification model of the same unit.

It runs the design model (RtlModel of /code/work/rtl_model.py, through sigdump) and a timed
specification model (a class whose step() is one clock edge and returns the outputs after the edge)
on the same port stimulus, and prints for every operation what each of them does at the ports.
It prints facts. It does not say which line of the source is wrong and it changes nothing.

All values are the values AFTER an edge (what a reader sees before the next edge).
"+N" counts edges from the start edge of an operation: +0 is the edge that samples the start.

The description file (JSON), written once for the unit:
    {"start":  "start",                        the input that starts an operation
     "end":    "done",                         the output that says the end
     "result": ["result"],                     the outputs that carry the result
     "modes":  {"with_setup": {"setup": 1}, "plain": {"setup": 0}},
                                               every way an operation can be started: name -> the inputs set with the start
                                               (a unit with one way: {"run": {}})
     "data":   [{"din": "0x1234", "param": "0x0f"}, {"din": "0xbeef", "param": "0x31"}],
                                               two sets of data inputs (the first and the second operation of a case differ)
     "control": ["state_ff"],                  control registers of the unit, by the names sigdump prints
     "data_registers": ["acc_ff"],             data registers of the unit
     "lower":  [{"name": "sub", "result": "sub.out_ff"}],
                                               units below (optional): the register the unit above reads from each
     "spec":   {"file": "/code/work/timed_model.py", "class": "Top",
                "inputs": {"rst_n": "reset_n"},          argument of step() -> input of the design, where the names differ
                "outputs": ["done", "result"]},          what step() returns, in its order (a dict needs no list)
                                               (when the host gives the specification model, this entry is in spec/given.json
                                               beside the description and is read from there)
     "needs_before": {"plain": "with_setup"},  optional: a mode whose result is defined only after an operation in another mode
     "tail": 40}                               edges run after a start (more than the longest operation takes)
The names above are examples; take the names of your unit from its ports and from the model (python3 -c
"import sys; sys.path.insert(0,'/code/lib'); import sigdump; m=sigdump.load_model('/code/work/rtl_model.py');
print(sorted({n.split('[')[0] for n in sigdump.signals(m.RtlModel())}))" prints the signal names).

The cases are made from "modes": no start after reset; for each mode a start in the first edge after
reset and a start after some edges without a start; for each pair of modes a second start after the
end of the first; for each mode a start while the unit is busy.

usage: python3 /code/lib/hsfacts.py /code/work/handshake.json [options]
    --fix a,b | all | all,c | none
                               switches of the design model (default: none). "all" means the names in the class
                               attribute SWITCHES of RtlModel (the kept switches); a candidate that is not yet in
                               SWITCHES is on only when it is named: --fix all,candidate
    --case NAME                only this case (names as printed)
    --edges                    also print, per edge, the inputs, the control registers and the outputs of both
    --out FILE                 write the per-edge print of every case to FILE
In Python: `import hsfacts`; `r = hsfacts.measure("/code/work/handshake.json", fix=("all", "candidate"))` gives
    r["cases"][name]["ops"][n] = {"design": {...}, "spec": {...}, "different": [fact names]},
    r["different"] = [(case, operation, fact)], and `hsfacts.text(r)` is the print.

What is printed for an operation (design | specification | same or DIFFERENT):
    end before the start edge     the end signal the start edge sees (0: the unit is busy and the start is sampled while it runs)
    end after the start edge      the end signal after +0
    end falls                     the first edge after which the end signal is 0
    end rises                     the first edge after which the end signal is 1 again        (a count)
    result at the rise            the result outputs after that edge; compared with the specification's result at ITS rise
    end is 1 before the rise      the edges from +0 to the rise after which the end signal is 1: the level says "finished" there
    result changes after the rise the edges after the rise, until the next start, in which a result output changes
    end leaves 1 without a start  the edges after the rise, until the next start, after which the end signal is 0
Lines marked (a count) differ when the two take a different number of edges; that is a difference only when a
sentence of the specification states the number; the line says whether the design is later or earlier. In the control walk
"3*5" means the value 3 after five edges in a row. For the design it also prints:
    control walk                  the values of the control registers after each edge, runs of equal values shortened
    data written while a lower result is not final
                                  the edges in which a data register of this unit changed although the register read
                                  from the unit below did not yet have the value it has at the end of this operation
                                  (with the control registers before that edge)
    unknown values                the edges after which a signal has unknown bits (x) that it does not have in every edge of
                                  the operation, with the control registers before that edge and the names of the signals
"""
import argparse
import importlib.util
import inspect
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sigdump  # noqa: E402

IDLE = 3      # edges without a start before a start "after idle"
BUSY = 2      # a start while busy comes this many edges after the first


def _int(x):
    if isinstance(x, str):
        return int(x, 0)
    return int(x)


def _val(v):
    """A value of the design as an int, or None when it has unknown bits."""
    if v is None:
        return None
    if hasattr(v, "is_known"):
        return v.int() if v.is_known() else None
    return int(v)


def _hex(x):
    if isinstance(x, tuple):
        return "(" + ", ".join(_hex(y) for y in x) + ")"
    return "x" if x is None else f"{x:x}"


def load(hs):
    """The description as a dict. Entries that the host gives for this unit (the file given.json in the folder
    spec beside the description: the timed specification model, the reference) are taken from there."""
    if not isinstance(hs, str):
        return hs
    d = json.load(open(hs))
    g = os.path.join(os.path.dirname(os.path.abspath(hs)), "spec", "given.json")
    if os.path.exists(g):
        d.update(json.load(open(g)))
    return d


def log(description, tool, args, lines):
    """Append the end of a print to tool_runs.log beside the description file."""
    if not isinstance(description, str):
        return
    try:
        import time
        with open(os.path.join(os.path.dirname(os.path.abspath(description)), "tool_runs.log"), "a") as f:
            f.write(f"--- {time.strftime('%H:%M:%S')}  {tool} {' '.join(args)}\n" + "\n".join("    " + x for x in lines if x.strip()) + "\n")
    except OSError:
        pass


def cases(hs):
    modes, data = hs["modes"], hs["data"]
    d0, d1 = data[0], data[1 if len(data) > 1 else 0]
    out = {"no_start": [("idle", None, None)]}
    for m in modes:
        out[f"first_{m}"] = [("start", m, d0)]
        out[f"idle_{m}"] = [("idle", None, None), ("start", m, d0)]
    for a in modes:
        for b in modes:
            out[f"second_{a}_{b}"] = [("start", a, d0), ("start", b, d1)]
    for m in modes:
        out[f"busy_{m}"] = [("start", m, d0), ("busy", m, d1)]
    return out


def _stimulus(hs, plan, interface):
    """One dict of inputs per edge, and the list of (edge, mode, kind) of the starts."""
    rst, act = interface["reset"]["name"], int(interface["reset"]["active"])
    zero = {k: 0 for k in interface["inputs"]}
    off = dict(zero, **{rst: 1 - act})
    edges, starts = [dict(zero, **{rst: act})], []
    tail = int(hs.get("tail", 40))
    for kind, mode, data in plan:
        if kind == "idle":
            edges += [dict(off) for _ in range(IDLE if len(plan) > 1 else tail)]
            continue
        if kind == "busy":
            del edges[len(edges) - tail + BUSY:]
        e = dict(off, **{hs["start"]: 1})
        e.update({k: _int(v) for k, v in hs["modes"][mode].items()})
        e.update({k: _int(v) for k, v in data.items()})
        starts.append((len(edges), mode, kind))
        edges += [e] + [dict(off) for _ in range(tail)]
    return edges, starts


def _run_design(model_path, interface, fix, edges, hs):
    mod = sigdump.load_model(model_path)
    if "all" in fix:                               # "all" = the names in SWITCHES (the kept switches); a candidate is on only when it is named
        fix = tuple(dict.fromkeys(list(getattr(mod.RtlModel, "SWITCHES", {})) + [x for x in fix if x != "all"]))
    hs["_fix"] = fix
    recs = sigdump.run(mod.RtlModel(fix=fix), {"steps": [{"set": e, "edges": 1} for e in edges]}, interface=interface)
    names = [hs["end"]] + list(hs["result"])
    out = []
    for rec in recs:
        heads = {}
        for n, v in rec["signals"].items():
            heads.setdefault(n.split("[")[0], []).append(v)
        before = {}
        for n, v in rec["before"].items():
            before.setdefault(n.split("[")[0], []).append(v)
        out.append({"out": {n: _val(rec["outputs"].get(n)) for n in names},
                    "ctl": tuple(_val(heads[c][0]) if c in heads else None for c in hs.get("control", [])),
                    "ctl_before": tuple(_val(before[c][0]) if c in before else None for c in hs.get("control", [])),
                    "sig": {h: tuple(_val(v) for v in vs) for h, vs in heads.items()},
                    "sig_before": {h: tuple(_val(v) for v in vs) for h, vs in before.items()}})
    return out


def _run_spec(spec, interface, edges, hs):
    """The outputs of the specification model after every edge; from the edge at which its step() raises, None."""
    s = importlib.util.spec_from_file_location("hsfacts_spec_model", spec["file"])
    m = importlib.util.module_from_spec(s)
    d = os.path.dirname(os.path.abspath(spec["file"]))
    if d not in sys.path:
        sys.path.insert(0, d)
    s.loader.exec_module(m)
    obj = getattr(m, spec.get("class", "Top"))()
    params = [p for p in inspect.signature(obj.step).parameters]
    amap = dict(spec.get("inputs", {}))
    free = [p for p in params if p not in amap and p not in edges[0]]
    rst = interface["reset"]["name"]
    if len(free) == 1 and rst not in params:        # the one argument that is not an input of the design is the reset
        amap[free[0]] = rst
    names = [hs["end"]] + list(hs["result"])
    order = spec.get("outputs") or list(interface.get("outputs", {}))
    out, err = [], None
    for i, e in enumerate(edges):
        if err is None:
            try:
                r = obj.step(**{p: e[amap.get(p, p)] for p in params})
                if not isinstance(r, dict):
                    r = dict(zip(order, r if isinstance(r, (tuple, list)) else (r,)))
                out.append({"out": {n: (None if r.get(n) is None else int(r[n])) for n in names}})
                continue
            except Exception as ex:                  # the model has no behaviour for this input order
                err = f"edge {i}: {type(ex).__name__}: {ex}"
        out.append({"out": {n: None for n in names}})
    return out, err


def _op(run, s, end_edge, hs, design=False):
    """The facts of one operation: the start is sampled at edge s; the next start (or the end of the case) is end_edge."""
    en, res = hs["end"], hs["result"]
    lvl = [run[i]["out"][en] for i in range(s, end_edge)]
    val = [tuple(run[i]["out"][r] for r in res) for i in range(s, end_edge)]
    fall = next((k for k, x in enumerate(lvl) if x == 0), None)
    rise = next((k for k in range(fall + 1, len(lvl)) if lvl[k] == 1), None) if fall is not None else None
    f = {"end before the start edge": run[s - 1]["out"][en] if s > 0 else None, "end after the start edge": lvl[0], "end falls": fall, "end rises": rise,
         "result at the rise": val[rise] if rise is not None else "no rise",
         "end is 1 before the rise": [k for k in range(0, rise if rise is not None else len(lvl)) if lvl[k] == 1],
         "result changes after the rise": [k for k in range(rise + 1, len(lvl)) if val[k] != val[k - 1]] if rise is not None else "no rise",
         "end leaves 1 without a start": [k for k in range(rise + 1, len(lvl)) if lvl[k] != 1] if rise is not None else "no rise"}
    if design:
        f["control walk"] = [run[i]["ctl"] for i in range(s, end_edge)]
        last = (rise if rise is not None else len(lvl) - 1) + s
        early = []
        for low in hs.get("lower", []):
            h = low["result"].split("[")[0]
            final = run[last]["sig"].get(h)
            for i in range(s, last + 1):
                if run[i]["sig_before"].get(h) != final:
                    w = [d for d in hs.get("data_registers", []) if run[i]["sig"].get(d) != run[i]["sig_before"].get(d)]
                    if w:
                        early.append((i - s, low.get("name", h), w, run[i]["ctl_before"]))
        f["data written while a lower result is not final"] = early
        unk = {}
        for i in range(s, last + 1):
            for h, vs in run[i]["sig"].items():
                if any(v is None for v in vs):
                    unk.setdefault(h, []).append(i - s)
        n = last + 1 - s
        by_edge = {}
        for h, k in sorted(unk.items()):
            if len(k) < n:
                for j in k:
                    by_edge.setdefault(j, []).append(h)
        f["unknown values"] = [(j, run[s + j]["ctl_before"], hs_) for j, hs_ in sorted(by_edge.items())]
        f["always unknown"] = sorted(h for h, k in unk.items() if len(k) == n)
    return f


COMPARED = ["end before the start edge", "end after the start edge", "end falls", "end rises", "result at the rise", "end is 1 before the rise",
            "result changes after the rise", "end leaves 1 without a start"]
COUNT = {"end rises"}


def measure(hs, fix=(), model="/code/work/rtl_model.py", interface=None, only=None):
    hs = load(hs)
    if interface is None:
        interface = os.path.join(os.path.dirname(os.path.abspath(model)), "interface.json")
    if isinstance(interface, str):
        interface = json.load(open(interface))
    if isinstance(fix, str):
        fix = tuple(p for p in fix.split(",") if p and p != "none")
    WIDTH[:] = [int(interface["outputs"].get(q, 0)) for q in hs["result"]]
    r = {"fix": fix, "cases": {}, "different": [], "hs": hs}
    for name, plan in cases(hs).items():
        if only and name != only:
            continue
        edges, starts = _stimulus(hs, plan, interface)
        d = _run_design(model, interface, fix, edges, hs)
        s, err = _run_spec(hs["spec"], interface, edges, hs)
        c = {"edges": edges, "design": d, "spec": s, "ops": [], "starts": starts, "spec_error": err}
        if err:
            r.setdefault("spec_errors", []).append((name, err))
        if not starts:
            en = hs["end"]
            c["idle"] = {"design": [x["out"][en] for x in d], "spec": [x["out"][en] for x in s], "control walk": [x["ctl"] for x in d],
                         "result design": [tuple(x["out"][q] for q in hs["result"]) for x in d], "result spec": [tuple(x["out"][q] for q in hs["result"]) for x in s]}
            for what, a, b in (("end signal without a start", c["idle"]["design"], c["idle"]["spec"]), ("result without a start", c["idle"]["result design"], c["idle"]["result spec"])):
                if a != b and not err:
                    r["different"].append((name, 0, what))
        for n, (e, mode, kind) in enumerate(starts):
            nxt = starts[n + 1][0] if n + 1 < len(starts) else len(edges)
            if kind == "start" and n + 1 < len(starts) and starts[n + 1][2] == "busy":
                nxt = len(edges)                     # the operation that is disturbed by a start while busy: looked at to the end of the case
            op = {"mode": mode, "kind": kind, "edge": e, "design": _op(d, e, nxt, hs, True), "spec": _op(s, e, nxt, hs)}
            op["different"] = [k for k in COMPARED if op["design"][k] != op["spec"][k]]
            if kind == "busy":
                op["different"] = []
            if err or (op["spec"]["end falls"] is not None and op["spec"]["end rises"] is None):
                op["no_spec"] = "the specification model raised an error in this case" if err else "the specification model does not end this operation"
                op["different"] = []
                r.setdefault("spec_errors", []).append((name, f"operation {n + 1}: {op['no_spec']}"))
            need = hs.get("needs_before", {}).get(mode)
            if need and not any(m == need and k == "start" for _, m, k in starts[:n]):
                op["no_result"] = need
                op["different"] = [k for k in op["different"] if k != "result at the rise"]
            for k in op["different"]:
                r["different"].append((name, n + 1, k))
            c["ops"].append(op)
        r["cases"][name] = c
    return r


def _one(ctl):
    return _hex(ctl[0]) if isinstance(ctl, tuple) and len(ctl) == 1 else _hex(ctl)


def _short(walk):
    out, prev, n = [], object(), 0
    for w in list(walk) + [object()]:
        if w == prev:
            n += 1
            continue
        if n:
            t = _hex(prev) if not (isinstance(prev, tuple) and len(prev) == 1) else _hex(prev[0])
            out.append(t if n == 1 else f"{t}*{n}")
        prev, n = w, 1
    return " ".join(out)


WIDTH = []


def _show(k, v):
    if k == "result at the rise" and isinstance(v, tuple):
        return "(" + ", ".join("x" if x is None else f"{x:0{(w + 3) // 4}x}" for x, w in zip(v, WIDTH or [0] * len(v))) + ")"
    if isinstance(v, list):
        if len(v) > 14:
            return f"{len(v)} edges: +{v[0]}..+{v[-1]}" if v == list(range(v[0], v[-1] + 1)) else f"{len(v)} edges: " + ",".join(f"+{x}" for x in v[:14]) + ",..."
        return ",".join(f"+{x}" for x in v) if v else "none"
    if k in ("end falls", "end rises"):
        return "never" if v is None else f"+{v}"
    return str(v)


def text(r, edges=False):
    hs, L = r["hs"], []
    L.append(f"hsfacts  switches: {', '.join(hs.get('_fix') or r['fix']) or 'none'}   start={hs['start']} end={hs['end']} result={','.join(hs['result'])}   values after each edge; +0 = the start edge")
    for name, c in r["cases"].items():
        L.append("")
        L.append(f"case {name}  ({len(c['edges'])} edges, edge 0 = reset)")
        if c.get("spec_error"):
            L.append(f"  THE SPECIFICATION MODEL RAISED AN ERROR at {c['spec_error']}   -- nothing of this case is compared; the model must give outputs for every order of inputs")
        if "idle" in c:
            i = c["idle"]
            L.append(f"  end signal after each edge   design {''.join(_hex(x) for x in i['design'])}")
            L.append(f"                               spec   {''.join(_hex(x) for x in i['spec'])}   {'same' if i['design'] == i['spec'] else 'DIFFERENT'}")
            L.append(f"  result changes               design {_show('', [k for k in range(1, len(i['result design'])) if i['result design'][k] != i['result design'][k - 1]])} | spec {_show('', [k for k in range(1, len(i['result spec'])) if i['result spec'][k] != i['result spec'][k - 1]])}   (edge numbers of the case)")
            L.append(f"  control walk (design)        {_short(i['control walk'])}")
        for n, op in enumerate(c["ops"], 1):
            L.append(f"  operation {n}: mode {op['mode']}, start sampled at edge {op['edge']}" + ("   -- a START WHILE BUSY: printed, not compared; it has a requirement only when a sentence says what must happen" if op["kind"] == "busy" else ""))
            for k in COMPARED:
                a, b = op["design"][k], op["spec"][k]
                mark = "same" if a == b else ("DIFFERENT" if k not in COUNT else "different (a count: the design is later)" if (a is None or (b is not None and a > b)) else "different (a count: the design is EARLIER than the specification)")
                if op["kind"] == "busy":
                    mark = ""
                if op.get("no_spec"):
                    mark = "not compared: " + op["no_spec"]
                if k == "result at the rise" and op.get("no_result"):
                    mark = f"not compared: no operation in mode {op['no_result']} before it, the result has no requirement"
                L.append(f"    {k:32s} design {_show(k, a)} | spec {_show(k, b)}   {mark}")
            d = op["design"]
            L.append(f"    control walk (design)            {_short(d['control walk'])}")
            e = d["data written while a lower result is not final"]
            L.append("    data written while a lower result is not final: " + ("none" if not e else f"{len(e)} edges, +edge(control before the edge): " + " ".join(f"+{k}({_one(ctl)})" for k, low, w, ctl in e[:30]) + (" ..." if len(e) > 30 else "") + "   registers: " + ",".join(sorted({x for _, _, w, _ in e for x in w})) + "; lower: " + ",".join(sorted({low for _, low, _, _ in e}))))
            u = d["unknown values"]
            L.append("    unknown values (x) in part of the operation: " + ("none" if not u else "; ".join(f"+{j} (control before the edge {_one(ctl)}): {','.join(names[:10])}{' ...' if len(names) > 10 else ''}" for j, ctl, names in u[:8]) + (" ..." if len(u) > 8 else "")))
        if edges:
            L += _edges(c, hs)
    L.append("")
    if r["different"]:
        L.append(f"lines that are not the same ({len(r['different'])}):")
        for name, n, k in r["different"]:
            L.append(f"  {name} operation {n}: {k}" + ("   (a count)" if k in COUNT else ""))
        L.append(f"of these, not a count: {sum(1 for _, _, k in r['different'] if k not in COUNT)}")
    else:
        L.append("lines that are not the same: none")
    if r.get("spec_errors"):
        L.append(f"NOT COMPARED because of the specification model ({len(r['spec_errors'])}): this is a fault of the timed specification model, not of the design; it is reported, the model is not replaced")
        for name, e in dict.fromkeys(r["spec_errors"]):
            L.append(f"  {name}: {e}")
    return "\n".join(L)


def _edges(c, hs):
    L = ["    edge | inputs | control (design) | design outputs | spec outputs"]
    names = [hs["end"]] + list(hs["result"])
    for i, e in enumerate(c["edges"]):
        ins = " ".join(f"{k}={_hex(v)}" for k, v in e.items() if v)
        L.append(f"    {i:4d} | {ins} | {_hex(c['design'][i]['ctl'])} | " + " ".join(f"{n}={_hex(c['design'][i]['out'][n])}" for n in names) + " | " + " ".join(f"{n}={_hex(c['spec'][i]['out'][n])}" for n in names))
    return L


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("description")
    ap.add_argument("--fix", default="none")
    ap.add_argument("--case")
    ap.add_argument("--edges", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--model", default="/code/work/rtl_model.py")
    a = ap.parse_args()
    try:
        res = measure(a.description, a.fix, a.model, only=a.case)
    except (OSError, KeyError, ValueError, sigdump.StimulusError) as ex:
        print(f"hsfacts: the description or a model could not be used ({type(ex).__name__}: {ex}); see the text at the top of /code/lib/hsfacts.py for the entries of the description")
        sys.exit(2)
    print(text(res, a.edges))
    tl = text(res).split("\n")
    log(a.description, "hsfacts", sys.argv[2:], tl[max(i for i, x in enumerate(tl) if x.startswith("lines that are not the same")):])
    if a.out:
        open(a.out, "w").write(text(res, True) + "\n")
