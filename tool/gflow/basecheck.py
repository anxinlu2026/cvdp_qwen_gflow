r"""basecheck: RtlModel() with no switch against the record of a simulator.

The record (/code/lib/base_record.json, put there with the order) holds what a simulator gave for the RTL as written (/code/rtl, nothing changed):
random inputs in several scenarios (the reset in the first two edges), and every output after every rising clock edge.
This library runs RtlModel() - no switch - on the same inputs and compares every output after every edge, bit by bit, unknown bits included.

usage: python3 /code/lib/basecheck.py [--model /code/work/rtl_model.py] [--record /code/lib/base_record.json] [--scenario N --edges A-B]
  with no option: one line per scenario and the first differences; the last line is "no difference" or "edges with a difference: N".
  --scenario N --edges A-B: the inputs, the outputs of the record and the outputs of RtlModel() for these edges of one scenario.
Edge 0 is the first step() call of a new RtlModel; step() gets every input as V(width, value).
In Python: `import basecheck; r = basecheck.measure(model_path, record_path)` -> {"ok", "differences", "first": (scenario, edge, output, record, model) or None, "lines"}; None when there is no record file.
The record says what the RTL as written does, right or wrong; it does not say what the design should do.
"""
import argparse, importlib.util, json, os, sys

RECORD = "/code/lib/base_record.json"


def _bits(v, w):
    if v is None:
        return "x" * w
    if hasattr(v, "bin") and hasattr(v, "w"):
        b = v.bin()
        return b if len(b) == w else f"a V of {len(b)} bits (the port has {w})"
    if isinstance(v, int):
        return format(v, f"0{w}b") if 0 <= v < (1 << w) else f"{v:#x} (does not fit the {w} bits of the port)"
    return f"{type(v).__name__} (a V, an int or None is expected)"


def _hex(b):
    if not b or any(c not in "01x" for c in b):
        return b
    b = b.rjust((len(b) + 3) // 4 * 4, "0")
    return "".join(format(int(g, 2), "x") if "x" not in g else "x" if g == "xxxx" else "X" for g in (b[i:i + 4] for i in range(0, len(b), 4)))


def _show(b, other):
    return b if b != other and _hex(b) == _hex(other) else _hex(b)   # binary only where the hex texts would hide the difference


def _model(path):
    d = os.path.dirname(os.path.abspath(path))
    for p in (d, os.path.dirname(os.path.abspath(__file__))):
        if p not in sys.path:
            sys.path.insert(0, p)
    s = importlib.util.spec_from_file_location("rtl_model_basecheck", path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def traces(model, rec, only=None):
    import svvec
    m = _model(model)
    out = []
    for n, stim in enumerate(rec["stims"]):
        if only is not None and n != only:
            out.append(None); continue
        t = m.RtlModel()
        out.append([{k: _bits(o[k], w) if k in o else "missing" for k, w in rec["outputs"].items()}
                    for o in (t.step(**{k: svvec.V(int(rec["inputs"].get(k, 1)), v) for k, v in c.items()}) for c in stim)])
    return out


def measure(model="/code/work/rtl_model.py", record=RECORD):
    if not os.path.exists(record):
        return None
    rec = json.load(open(record))
    mt = traces(model, rec)
    lines, tot, first = [], 0, None
    for i, (r, m) in enumerate(zip(rec["rtl"], mt)):
        diffs = [(e, n, r[e][n], m[e][n]) for e in range(min(len(r), len(m))) for n in rec["outputs"] if r[e][n] != m[e][n]]
        edges = len(set(d[0] for d in diffs))
        tot += edges
        lines.append(f"scenario {i}: {len(r)} edges, {edges} edges with a difference")
        for e, n, rv, mv in diffs[:3]:
            lines.append(f"  edge {e} output {n}: simulator (RTL as written) = {_show(rv, mv)}   RtlModel() = {_show(mv, rv)}")
        if diffs and first is None:
            first = (i, diffs[0][0], diffs[0][1], _show(diffs[0][2], diffs[0][3]), _show(diffs[0][3], diffs[0][2]))
    lines.insert(0, "The record of a simulator for the RTL as written (/code/rtl) against RtlModel() with no switch, on the same inputs; outputs compared after every edge, bit by bit (hex; x = digit unknown, X = digit partly unknown).")
    lines.append("no difference" if not tot else f"edges with a difference: {tot}")
    return {"ok": tot == 0, "differences": tot, "first": first, "lines": lines}


def edges(model, record, scenario, a, b):
    rec = json.load(open(record))
    mt = traces(model, rec, only=scenario)[scenario]
    L = [f"scenario {scenario}, edges {a}..{b} (inputs given before the edge; outputs after it)"]
    for e in range(max(a, 0), min(b + 1, len(rec["stims"][scenario]))):
        L.append(f"edge {e}: inputs " + ", ".join(f"{k}={v:#x}" for k, v in rec["stims"][scenario][e].items()))
        for n in rec["outputs"]:
            r, m = rec["rtl"][scenario][e][n], mt[e][n]
            L.append(f"    {n}: simulator = {_show(r, m)}   RtlModel() = {_show(m, r)}" + ("" if r == m else "   <- different"))
    return L


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--model", default="/code/work/rtl_model.py"); ap.add_argument("--record", default=RECORD); ap.add_argument("--scenario", type=int); ap.add_argument("--edges")
    a = ap.parse_args(argv)
    if not os.path.exists(a.record):
        print(f"there is no record file {a.record}"); return 2
    try:
        if a.scenario is not None:
            lo, _, hi = (a.edges or "0-9").partition("-")
            print("\n".join(edges(a.model, a.record, a.scenario, int(lo), int(hi or lo)))); return 0
        r = measure(a.model, a.record)
    except Exception as ex:
        print(f"basecheck: RtlModel() could not be run on the inputs of the record ({type(ex).__name__}: {ex})"); return 2
    print("\n".join(r["lines"]))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
