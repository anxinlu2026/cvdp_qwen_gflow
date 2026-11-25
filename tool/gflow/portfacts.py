r"""portfacts: every output port of ONE unit, edge by edge, next to a timed specification model of the same unit.

It runs the design model (RtlModel of /code/work/rtl_model.py, through sigdump) and a timed specification
model (a class whose step() is one clock edge and returns the outputs after the edge) on the same port
stimulus and compares every output after every edge. It prints facts: where the two differ, and the values.
It does not say which line of the source is wrong and it changes nothing. It needs no end signal and no
kind of handshake: a level, a pulse, a valid mark and a data port are all compared the same way.

All values are the values AFTER an edge (what a reader of the ports sees before the next edge).
"+N" counts edges from the start edge of an operation: +0 is the edge that samples the start. Where several operations
are on their way at an edge (a unit that takes a new start before the one before it has ended), the print gives the count
for each of them: which of them the value at the port belongs to follows from how many edges the unit takes.
Where the specification model returns None for an output, the specification does not fix that value in
that edge: it is not judged (printed "-").

The description file (JSON), written once for the unit:
    {"start":  "start",                        the input that marks an operation (a start, or the valid mark of the inputs)
     "modes":  {"run": {}},                    every way an operation can be given: name -> the inputs set together with the start
     "data":   [{"a": "0x1234", "b": "0x0f"}, {"a": "0xbeef", "b": "0x31"}],
                                               two sets of data inputs (the first and the second operation of a case differ)
     "control": ["state_ff"],                  optional: registers of the unit to print beside the ports, by the names sigdump prints
     "spec":   {"file": "/code/work/spec/top_model.py", "class": "Top",
                "inputs": {"rst_n": "reset_n"},          argument of step() -> input of the design, where the names differ
                "outputs": ["done", "sum"]},             what step() returns, in its order (a dict needs no list)
                                               (when the host gives the specification model, this entry is in spec/given.json
                                               beside the description and is read from there)
     "ports":  ["done", "sum"],                optional: the outputs that are compared (default: every output of interface.json)
     "tail": 12}                               edges run after a start (more than the longest operation takes)
The names above are examples; take the names of your unit from its ports and from the model.

The cases are made from "modes": no start after reset; for each mode a start in the first edge after reset and
a start after some edges without a start; for each pair of modes a second start after the first has run its
tail; for each mode two starts in edges that follow each other ("busy": the second is given while the first runs);
for each mode a start in every edge for some edges ("stream"); for each mode a start after which the data inputs
change although no start is given ("change").
After a start the data inputs keep the values of that operation (the start input goes back to 0) until the next
start or, in the case "change", until they are changed; before the first start they are 0.

usage: python3 /code/lib/portfacts.py /code/work/handshake.json [options]
    --fix a,b | all | all,c | none   switches of the design model (default: none). "all" means the names in the class
                               attribute SWITCHES of RtlModel (the kept switches); a candidate that is not yet in
                               SWITCHES is on only when it is named: --fix all,candidate
    --case NAME                only this case (names as printed)
    --edges                    also print, per edge, the inputs, the control registers and the outputs of both
    --out FILE                 write the per-edge print of every case to FILE
In Python: `import portfacts`; `r = portfacts.measure("/code/work/handshake.json", fix=("all", "candidate"))` gives
    r["cases"][name]["ports"][port] = {"different": [edges], "not_judged": count, "first": (edge, ((operation, +N), ...), design, spec) or None},
    r["different"] = [(case, first edge, "port NAME")], and `portfacts.text(r)` is the print.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hsfacts  # noqa: E402
import sigdump  # noqa: E402

STREAM = 6    # starts in edges that follow each other in the case "stream"


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
        out[f"stream_{m}"] = [("start", m, d0)] + [("next", m, d1 if k % 2 == 0 else d0) for k in range(STREAM - 1)]
        out[f"change_{m}"] = [("start", m, d0), ("change", m, d1)]
    return out


def _stimulus(hs, plan, interface):
    """One dict of inputs per edge, and the list of (edge, mode, kind) of the starts."""
    rst, act = interface["reset"]["name"], int(interface["reset"]["active"])
    zero = {k: 0 for k in interface["inputs"]}
    off = dict(zero, **{rst: 1 - act})
    edges, starts = [dict(zero, **{rst: act})], []
    tail = int(hs.get("tail", 12))
    held = {}                                          # the data inputs of the last operation: kept after its start edge
    for kind, mode, data in plan:
        if kind == "idle":
            edges += [dict(off) for _ in range(hsfacts.IDLE if len(plan) > 1 else tail)]
            continue
        vals = {k: hsfacts._int(v) for k, v in hs["modes"][mode].items()}
        vals.update({k: hsfacts._int(v) for k, v in data.items()})
        if kind == "change":                           # no start: the data inputs take other values some edges after the start
            keep = tail // 2
            del edges[len(edges) - tail + keep:]
            held = {k: v for k, v in vals.items() if k in data}
            edges += [dict(off, **held) for _ in range(tail)]
            continue
        if kind in ("busy", "next"):
            del edges[len(edges) - tail:]              # the edge right after the start before it
        starts.append((len(edges), mode, kind))
        held = {k: v for k, v in vals.items() if k in data}
        edges += [dict(off, **{hs["start"]: 1}, **vals)] + [dict(off, **held) for _ in range(tail)]
    return edges, starts


def _design(model_path, interface, fix, edges, hs, names):
    mod = sigdump.load_model(model_path)
    if "all" in fix:
        fix = tuple(dict.fromkeys(list(getattr(mod.RtlModel, "SWITCHES", {})) + [x for x in fix if x != "all"]))
    hs["_fix"] = fix
    recs = sigdump.run(mod.RtlModel(fix=fix), {"steps": [{"set": e, "edges": 1} for e in edges]}, interface=interface)
    out = []
    for rec in recs:
        heads = {}
        for n, v in rec["signals"].items():
            heads.setdefault(n.split("[")[0], []).append(v)
        bad = [c for c in hs.get("control", []) if c not in heads]
        if bad:
            raise ValueError(f"\"control\" of the description names {bad}: no such signal in the model; the names sigdump prints are {sorted(heads)[:60]}")
        out.append({"out": {n: (hsfacts._val(rec["outputs"].get(n)) if n in rec["outputs"] else "missing") for n in names},
                    "ctl": tuple(hsfacts._val(heads[c][0]) if c in heads else None for c in hs.get("control", []))})
    return out


def _spec(spec, interface, edges, names):
    """The outputs of the specification model after every edge (None: not fixed); from the edge at which its step() raises, all None."""
    import importlib.util
    import inspect
    s = importlib.util.spec_from_file_location("portfacts_spec_model", spec["file"])
    m = importlib.util.module_from_spec(s)
    d = os.path.dirname(os.path.abspath(spec["file"]))
    if d not in sys.path:
        sys.path.insert(0, d)
    s.loader.exec_module(m)
    obj = getattr(m, spec.get("class", "Top"))()
    params = [p for p in inspect.signature(obj.step).parameters]
    amap = dict(spec.get("inputs", {}))
    free = [p for p in params if p not in amap and p not in edges[0]]
    rst, act = interface["reset"]["name"], int(interface["reset"]["active"])
    if len(free) == 1 and rst not in params:        # the one argument that is not an input of the design is the reset
        amap[free[0]] = rst
    logical = spec.get("reset_active_high_argument", [])   # arguments of step() that mean "reset active" (1 = active) whatever the polarity of the pin
    order = spec.get("outputs") or list(interface.get("outputs", {}))
    out, err = [], None
    for i, e in enumerate(edges):
        if err is None:
            try:
                kw = {p: e[amap.get(p, p)] for p in params}
                for p in logical:
                    kw[p] = 1 if e[amap.get(p, p)] == act else 0
                r = obj.step(**kw)
                if not isinstance(r, dict):
                    r = dict(zip(order, r if isinstance(r, (tuple, list)) else (r,)))
                out.append({"out": {n: (None if r.get(n) is None else int(r[n])) for n in names}})
                continue
            except Exception as ex:                  # noqa: BLE001  the model has no behaviour for this input order
                err = f"edge {i}: {type(ex).__name__}: {ex}"
        out.append({"out": {n: None for n in names}})
    return out, err


def measure(hs, fix=(), model="/code/work/rtl_model.py", interface=None, only=None):
    hs = hsfacts.load(hs)
    if interface is None:
        interface = os.path.join(os.path.dirname(os.path.abspath(model)), "interface.json")
    if isinstance(interface, str):
        interface = json.load(open(interface))
    if isinstance(fix, str):
        fix = tuple(p for p in fix.split(",") if p and p != "none")
    names = list(hs.get("ports") or interface["outputs"])
    r = {"fix": fix, "cases": {}, "different": [], "hs": hs, "names": names, "widths": {n: int(interface["outputs"].get(n, 0)) for n in names}}
    if only and only not in cases(hs):
        raise ValueError(f"no case {only!r}; the cases are {list(cases(hs))}")
    for name, plan in cases(hs).items():
        if only and name != only:
            continue
        edges, starts = _stimulus(hs, plan, interface)
        d = _design(model, interface, fix, edges, hs, names)
        s, err = _spec(hs["spec"], interface, edges, names)
        c = {"edges": edges, "design": d, "spec": s, "starts": starts, "spec_error": err, "ports": {}}
        if err:
            r.setdefault("spec_errors", []).append((name, err))

        def op_of(i):
            """Every start sampled at or before edge i, as (operation number, edges since its start edge)."""
            return tuple((n, i - e) for n, (e, _, _) in enumerate(starts, 1) if e <= i)
        for n in names:
            diff = [i for i in range(len(edges)) if s[i]["out"][n] is not None and d[i]["out"][n] != s[i]["out"][n]]
            nj = sum(1 for i in range(len(edges)) if s[i]["out"][n] is None)
            first = None
            if diff and not err:
                i = diff[0]
                first = (i, op_of(i), d[i]["out"][n], s[i]["out"][n])
                r["different"].append((name, i, f"port {n}"))
            c["ports"][n] = {"different": [] if err else diff, "not_judged": nj, "first": first}
        r["cases"][name] = c
    return r


def _v(x, w=0):
    """A value in hex; wider than one byte: the bytes apart (9c_d2_a5_6b), the most significant first."""
    if x is None or isinstance(x, str):
        return "-" if x is None else x
    t = f"{x:0{(w + 3) // 4}x}"
    return t if len(t) <= 2 else "_".join(([t[:len(t) % 2]] if len(t) % 2 else []) + [t[k:k + 2] for k in range(len(t) % 2, len(t), 2)])


def text(r, edges=False):
    hs, L = r["hs"], []
    L.append(f"portfacts  switches: {', '.join(hs.get('_fix') or r['fix']) or 'none'}   start={hs['start']}   outputs compared: {', '.join(r['names'])}   values after each edge; +0 = the start edge; - = not fixed by the specification, not judged")
    for name, c in r["cases"].items():
        st = ", ".join(f"edge {e}" for e, _, k in c["starts"]) or "none"
        L.append("")
        L.append(f"case {name}  ({len(c['edges'])} edges, edge 0 = reset; starts sampled at: {st})")
        if c.get("spec_error"):
            L.append(f"  THE SPECIFICATION MODEL RAISED AN ERROR at {c['spec_error']}   -- nothing of this case is compared; the model must give outputs for every order of inputs")
        for n, p in c["ports"].items():
            w = r["widths"][n]
            if p["first"] is None:
                L.append(f"  {n:16s} same in every judged edge" + (f"   (not judged: {p['not_judged']} edges)" if p["not_judged"] else ""))
            else:
                i, ops, a, b = p["first"]
                where = f"edge {i}" + (" = " + ", ".join(f"+{k} of operation {o}" for o, k in ops) if ops else " (before any start)")
                d = p["different"]
                run = f"{len(d)} edges" + (f": {d[0]}..{d[-1]}" if d == list(range(d[0], d[-1] + 1)) and len(d) > 1 else ": " + ",".join(map(str, d[:14])) + (",..." if len(d) > 14 else ""))
                L.append(f"  {n:16s} DIFFERENT in {run}; first at {where}: design {_v(a, w)} | spec {_v(b, w)}" + (f"   (not judged: {p['not_judged']} edges)" if p["not_judged"] else ""))
        if edges:
            L.append("    edge | inputs | control (design)" + (": " + ", ".join(hs.get("control", [])) if hs.get("control") else "") + " | design outputs | spec outputs | different")
            for i, e in enumerate(c["edges"]):
                ins = " ".join(f"{k}={hsfacts._hex(v)}" for k, v in e.items() if v)
                dd = [n for n in r["names"] if i in c["ports"][n]["different"]]
                L.append(f"    {i:4d} | {ins} | {hsfacts._hex(c['design'][i]['ctl'])} | " + " ".join(f"{n}={_v(c['design'][i]['out'][n], r['widths'][n])}" for n in r["names"])
                         + " | " + " ".join(f"{n}={_v(c['spec'][i]['out'][n], r['widths'][n])}" for n in r["names"]) + " | " + (",".join(dd) if dd else ""))
    L.append("")
    if r["different"]:
        L.append(f"ports that are not the same ({len(r['different'])}):")
        for name, n, k in r["different"]:
            L.append(f"  {name}: {k} (first at edge {n})")
    else:
        L.append("ports that are not the same: none")
    if r.get("spec_errors"):
        L.append(f"NOT COMPARED because of the specification model ({len(r['spec_errors'])}): this is a fault of the timed specification model, not of the design; it is reported, the model is not replaced")
        for name, e in dict.fromkeys(r["spec_errors"]):
            L.append(f"  {name}: {e}")
    return "\n".join(L)


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
        print(f"portfacts: not run ({type(ex).__name__}: {ex})" + ("; an entry of the description is missing: see the text at the top of /code/lib/portfacts.py" if isinstance(ex, KeyError) else ""))
        sys.exit(2)
    print(text(res, a.edges))
    tl = text(res).split("\n")
    hsfacts.log(a.description, "portfacts", sys.argv[2:], tl[max(i for i, x in enumerate(tl) if x.startswith("ports that are not the same")):])
    if a.out:
        open(a.out, "w").write(text(res, True) + "\n")
