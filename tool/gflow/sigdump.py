"""sigdump: drive a Python model of an RTL with a stimulus file and print every signal after every edge.

The model is the class RtlModel of /code/work/rtl_model.py: RtlModel(fix=...) and
step(**inputs) with every input a V of the width given in interface.json. No driver script is
needed: the stimulus file says what the testbench does.

Stimulus file (JSON): {"steps": [step, ...]}. The steps run in order on ONE model, so a later
operation sees the state an earlier operation left (as in a testbench). A step may have:
    "set":    {input: value, ...}   inputs to change; an input keeps its value until it is set again.
                                    A value is an int, a text like "0x2b7e", or "x" (all bits
                                    unknown: an input the testbench has not driven yet). At the
                                    start every input is 0 and the reset is not active.
    "edges":  N                     run N clock edges (default 1) ...
    "until":  {output: value, ...}  ... or run edges until every named output has this value
    "until_rise": {output: value}   ... or run edges until every named output has this value after it
                                    had another value in this step (an end signal that is already 1
                                    before the operation starts: wait for it to go away and come back)
    "max":    N                     the most edges "until" may take (default 1000)
    "expect": {output: value, ...}  compared with the outputs after the last edge of the step
    "label":  "text"                printed with the edges of the step
Example (reset, start one operation, wait for the end, read the result):
    {"steps": [
      {"label": "reset", "set": {"rst_n": 0}},
      {"label": "start", "set": {"rst_n": 1, "start": 1, "data": "0x1234"}},
      {"label": "run",   "set": {"start": 0, "data": 0}, "until": {"done": 1}, "max": 200},
      {"label": "read",  "expect": {"result": "0xabcd"}}]}

What is printed for an edge: the inputs of this step() call, the outputs it returned, and every
attribute of the model that is a V or a list of V (also inside the sub-objects of the model),
complete, in hex (x = unknown). These are the values the model holds after the call: a register
has its value after the edge; a combinational signal has the value this call computed from the
register values before the edge (printed at the edge before).

usage: python3 /code/lib/sigdump.py STIMULUS [options]
    --fix a,b | --fix all    switches of the model (default: none)
    --fix2 a,b | all | none  a second run with these switches; only the signals that differ
                             between the two runs are printed, edge by edge
    --edges A:B              print only edges A..B (numbers as printed; default all)
    --signals name,name      print only signals whose name starts with one of these
    --summary                print only the steps: edges taken, outputs, expect OK or DIFFERENT
    --all                    print everything even when it is long (without --edges or --signals a
                             print of more than 300 lines is replaced by the steps and the signal names)
    --model PATH             default /code/work/rtl_model.py (interface.json is read beside it)
In Python (import it in your own script: `sys.path.insert(0, "/code/lib")`, `import sigdump`):
    mod = sigdump.load_model("/code/work/rtl_model.py")        # the module; mod.RtlModel is the class
    recs = sigdump.run(mod.RtlModel(fix="all"), "/code/work/stimulus.json")
        One record per edge: {"edge", "step", "label", "inputs", "outputs", "before", "signals"}.
        "signals" maps a name such as "MixColumns[0][1]" or "key_exp.valid_key" to its V after the
        edge (use .hex(), .int(), .is_known()); "before" is the same map from before the edge.
        "outputs" is what step() returned. When the step() of a class returns outputs computed
        from the registers BEFORE the edge (read its text), name in the interface the signal each
        such output shows: "outputs_after": {"o_done": "count_ff[10]", "o_key": "key_ff"} (a signal
        name as printed, or one bit of it). "outputs", until, until_rise and expect then use the
        value after the edge for these outputs.
        recs.steps has one summary per step of the stimulus file.
    rec = sigdump.step_once(model, inputs, state=None)
        ONE edge from a state you choose. state: {name: value} written into the model before the
        edge (see set_state); inputs: {input: value}, an input not named is 0 and the reset is not
        active. Returns the same kind of record.
        For the class of a submodule (its own step() and ports) give run() or step_once() its ports:
        interface={"inputs": {name: width, ...}, "outputs": {name: width, ...}, "reset": {"name": "rst_n", "active": 0}, "outputs_after": {...}},
        and give run() the stimulus as a dict {"steps": [...]} with these port names.
    sigdump.set_state(model, {"count_ff": 5, "sub.flag": 1, "data_ff": [[0x12, ...], ...], "data_ff[0][1]": "x"})
        Writes registers by the names sigdump prints. A value is an int, a text like "0x1f", "x",
        a V, or a nested list of these for an array. The width is the one the model already has.
    sigdump.whole(rec["signals"], "data_ff")       all elements of one signal as a tuple of hex texts
    sigdump.changed(rec)                           the signals whose value after the edge is not the one before
    sigdump.same_as(rec, "data_ff")                the other signals that hold, after the edge, exactly the value
                                                   "data_ff" holds after it (a register that took the result of a
                                                   piece shows that piece here), and "(its value before the edge)"
                                                   when it kept its value
    sigdump.same_parts(rec, "key_ff", 128)         for a wide register built from parts: cuts it into parts of this many
                                                   bits (part 0 = the most significant) and gives for each part the signals,
                                                   and the parts of the register before the edge, that have its value
    sigdump.changed_parts(rec, "key_ff", 128)      the numbers of the parts of a wide register whose value changed in this edge
    sigdump.applied(rec, "PieceB", "PieceA")       True when the value of PieceB after the edge is not the value of PieceA
                                                   (PieceB, which comes after PieceA in a chain, did something in this edge);
                                                   False when PieceB only passes PieceA's value on
    sigdump.edge_table(rec)                        text: for every signal that changed, before -> after and same_as
                                                   (a value of more than 64 hex digits is shortened)
"""
import argparse
import importlib.util
import inspect
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svvec  # noqa: E402

V = svvec.V


class StimulusError(Exception):
    pass


def load_model(path="/code/work/rtl_model.py"):
    d = os.path.dirname(os.path.abspath(path))
    if d not in sys.path:
        sys.path.insert(0, d)
    s = importlib.util.spec_from_file_location("rtl_model_sigdump_" + str(abs(hash(path))), path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _num(x, what):
    if isinstance(x, str) and x.strip().lower() == "x":
        return None
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, int):
        return x
    if isinstance(x, str):
        try:
            return int(x.replace("_", ""), 0)
        except ValueError:
            pass
    raise StimulusError(f"{what}: the value {x!r} is not an int, a text like \"0x1f\", or \"x\"")


def _leaves(x, name, out, depth, seen):
    if isinstance(x, V):
        out[name] = x
    elif isinstance(x, (list, tuple)):
        for i, y in enumerate(x):
            _leaves(y, f"{name}[{i}]", out, depth, seen)
    elif isinstance(x, dict):
        for k, y in x.items():
            if isinstance(k, (str, int)):
                _leaves(y, f"{name}[{k}]", out, depth, seen)
    elif hasattr(x, "__dict__") and depth < 4 and id(x) not in seen and not isinstance(x, type):
        seen.add(id(x))
        for k, y in vars(x).items():
            if not k.startswith("_"):
                _leaves(y, f"{name}.{k}" if name else k, out, depth + 1, seen)


def signals(model):
    """Every V the model holds, by name (lists flattened: a[0][1]; sub-objects: sub.name)."""
    out = {}
    _leaves(model, "", out, 0, set())
    return out


def _as_v(x, width=None):
    if isinstance(x, V) or x is None:
        return x
    if isinstance(x, int) and width:
        return V(width, x)
    return x


def _text(x):
    if x is None:
        return "x"
    if isinstance(x, V):
        return x.hex()
    return f"{x:x}" if isinstance(x, int) else str(x)


def _same(got, want):
    if want is None:
        return isinstance(got, V) and not got.is_known() or got is None
    if isinstance(got, V):
        return got.is_known() and got.int() == want
    return isinstance(got, int) and got == want


def run(model, stimulus, interface=None):
    """Run the stimulus on the model. stimulus: a path or the loaded dict. Returns one record per edge;
    the list has the attribute .steps (one summary per step)."""
    if isinstance(stimulus, str):
        stim_dir = os.path.dirname(os.path.abspath(stimulus))
        stimulus = json.load(open(stimulus))
    else:
        stim_dir = "/code/work"
    if interface is None:
        interface = os.path.join(stim_dir, "interface.json")
    if isinstance(interface, str):
        interface = json.load(open(interface))
    widths = {k: int(w) for k, w in interface["inputs"].items()}
    outw = {k: int(w) for k, w in interface.get("outputs", {}).items()}
    rst = interface.get("reset")
    cur = {k: 0 for k in widths}
    if isinstance(rst, dict) and rst.get("name"):
        widths.setdefault(rst["name"], 1)
        cur[rst["name"]] = 0 if int(rst.get("active", 0)) else 1
    steps = stimulus["steps"] if isinstance(stimulus, dict) else stimulus
    par = inspect.signature(model.step).parameters
    takes_all = any(p.kind == p.VAR_KEYWORD for p in par.values())
    not_taken = [] if takes_all else [k for k in cur if k not in par]

    class Records(list):
        pass

    recs = Records()
    recs.steps = []
    recs.not_taken = not_taken
    edge = 0
    for si, st in enumerate(steps):
        unknown = set(st) - {"set", "edges", "until", "until_rise", "max", "expect", "label"}
        if unknown:
            raise StimulusError(f"step {si}: unknown key {sorted(unknown)}")
        for k, v in st.get("set", {}).items():
            if k not in widths:
                raise StimulusError(f"step {si}: {k!r} is not an input of interface.json ({sorted(widths)})")
            cur[k] = _num(v, f"step {si} set {k}")
        rise = "until_rise" in st
        until = {k: _num(v, f"step {si} until {k}") for k, v in (st.get("until_rise") if rise else st.get("until", {})).items()}
        away = not rise
        limit = int(st.get("max", 1000)) if until else int(st.get("edges", 1))
        reached = not until
        n = 0
        outs = {}
        while n < limit:
            before = signals(model)
            outs = model.step(**{k: (svvec.X(widths[k]) if v is None else V(widths[k], v)) for k, v in cur.items() if k not in not_taken}) or {}
            outs = {k: _as_v(v, outw.get(k)) for k, v in outs.items()}
            after = signals(model)
            outs = _after(outs, after, interface)
            recs.append({"edge": edge, "step": si, "label": st.get("label", ""), "inputs": dict(cur),
                         "outputs": outs, "before": before, "signals": after, "widths": widths})
            edge += 1
            n += 1
            if until:
                for k in until:
                    if k not in outs:
                        raise StimulusError(f"step {si}: {k!r} is not an output step() returned ({sorted(outs)})")
                hit = all(_same(outs[k], v) for k, v in until.items())
                if not hit:
                    away = True
                elif away:
                    reached = True
                    break
        exp = {}
        for k, v in st.get("expect", {}).items():
            want = _num(v, f"step {si} expect {k}")
            if k not in outs:
                raise StimulusError(f"step {si}: {k!r} is not an output step() returned ({sorted(outs)})")
            exp[k] = (want, _same(outs[k], want))
        recs.steps.append({"step": si, "label": st.get("label", ""), "edges": n, "first_edge": edge - n,
                           "until": until, "reached": reached, "outputs": outs, "expect": exp})
    return recs


def _after(outs, sig, interface):
    for k, name in (interface.get("outputs_after") or {}).items():
        if name in sig:
            outs[k] = sig[name]
            continue
        head, _, idx = name.rpartition("[")
        if head in sig and idx.endswith("]") and idx[:-1].isdigit():
            outs[k] = svvec.bit(sig[head], int(idx[:-1]), "sigdump outputs_after")
        else:
            raise StimulusError(f"outputs_after {k}: {name!r} is not a signal of the model or one bit of it; names: {sorted({n.split('[')[0] for n in sig})}")
    return outs


def _conv(target, value, name):
    if isinstance(target, (list, tuple)):
        if not isinstance(value, (list, tuple)) or len(value) != len(target):
            raise StimulusError(f"{name}: the model has a list of {len(target)} here; give a list of the same length")
        return [_conv(t, x, f"{name}[{i}]") for i, (t, x) in enumerate(zip(target, value))]
    if not isinstance(target, V):
        raise StimulusError(f"{name}: is not a V or a list of V in the model")
    if isinstance(value, V):
        if value.w != target.w:
            raise StimulusError(f"{name}: has {target.w} bits in the model, the value has {value.w}")
        return value
    n = _num(value, name)
    if n is None:
        return svvec.X(target.w)
    if n < 0 or n >> target.w:
        raise StimulusError(f"{name}: the value has {n.bit_length() if n >= 0 else 'a negative'} bits ({svvec.short_hex(n)}); it does not fit the {target.w} bits of the model")
    return V(target.w, n)


def set_state(model, values):
    """Write values into the model by the names sigdump prints (a.b[1][2])."""
    import re
    for name, value in values.items():
        obj, parts = model, re.findall(r"[A-Za-z_]\w*|\[\d+\]", name)
        if "".join(parts) != name.replace(".", ""):
            raise StimulusError(f"{name!r}: not a name of the form a.b[1][2]")
        steps = [int(q[1:-1]) if q.startswith("[") else q for q in parts]
        for q in steps[:-1]:
            try:
                obj = obj[q] if isinstance(q, int) else getattr(obj, q)
            except (AttributeError, IndexError, TypeError):
                raise StimulusError(f"{name!r}: the model has no such signal; names: {sorted({n.split('[')[0] for n in signals(model)})}")
        last = steps[-1]
        try:
            target = obj[last] if isinstance(last, int) else getattr(obj, last)
        except (AttributeError, IndexError, TypeError):
            raise StimulusError(f"{name!r}: the model has no such signal; names: {sorted({n.split('[')[0] for n in signals(model)})}")
        new = _conv(target, value, name)
        if isinstance(last, int):
            obj[last] = new
        else:
            setattr(obj, last, new)


def step_once(model, inputs=None, state=None, interface=None):
    """One edge from a chosen state. Returns the record of this edge (see the text at the top)."""
    if interface is None:
        interface = "/code/work/interface.json"
    if isinstance(interface, str):
        interface = json.load(open(interface))
    widths = {k: int(w) for k, w in interface["inputs"].items()}
    outw = {k: int(w) for k, w in interface.get("outputs", {}).items()}
    rst = interface.get("reset")
    cur = {k: 0 for k in widths}
    if isinstance(rst, dict) and rst.get("name"):
        widths.setdefault(rst["name"], 1)
        cur[rst["name"]] = 0 if int(rst.get("active", 0)) else 1
    for k, v in (inputs or {}).items():
        if k not in widths:
            raise StimulusError(f"{k!r} is not an input of interface.json ({sorted(widths)})")
        cur[k] = v if isinstance(v, V) else _num(v, f"input {k}")
    if state:
        set_state(model, state)
    par = inspect.signature(model.step).parameters
    takes_all = any(p.kind == p.VAR_KEYWORD for p in par.values())
    before = signals(model)
    outs = model.step(**{k: (v if isinstance(v, V) else svvec.X(widths[k]) if v is None else V(widths[k], v))
                         for k, v in cur.items() if takes_all or k in par}) or {}
    outs = {k: _as_v(v, outw.get(k)) for k, v in outs.items()}
    after = signals(model)
    outs = _after(outs, after, interface)
    return {"edge": 0, "step": 0, "label": "", "inputs": cur, "outputs": outs, "before": before, "signals": after, "widths": widths}


def _heads(sig):
    out = {}
    for n, v in sig.items():
        out.setdefault(n.split("[")[0], []).append(v)
    return out


def whole(sig, name):
    """All elements of one signal (a.b, without index) as a tuple of hex texts, in the order of the indexes."""
    vs = [v for n, v in sig.items() if n == name or n.startswith(name + "[")]
    if not vs:
        raise KeyError(f"{name!r}: no such signal; names: {sorted(_heads(sig))}")
    return tuple(v.hex() for v in vs)


def changed(rec):
    """Names (without index) of the signals whose value after the edge is not the one before it."""
    a, b = _heads(rec["signals"]), _heads(rec["before"])
    return [n for n in a if n not in b or [(v.w, v.hex()) for v in a[n]] != [(v.w, v.hex()) for v in b[n]]]


def same_as(rec, name):
    """The other signals that hold after the edge exactly the value `name` holds after it."""
    a = _heads(rec["signals"])
    if name not in a:
        raise KeyError(f"{name!r}: no such signal; names: {sorted(a)}")
    key = [(v.w, v.hex()) for v in a[name]]
    out = [n for n in a if n != name and [(v.w, v.hex()) for v in a[n]] == key]
    b = _heads(rec["before"])
    if name in b and [(v.w, v.hex()) for v in b[name]] == key:
        out.append("(its value before the edge)")
    for k, v in rec["inputs"].items():
        if len(key) == 1 and key[0][0] > 1 and rec.get("widths", {}).get(k) == key[0][0] and isinstance(v, (int, V)) and not isinstance(v, bool):
            t = v.hex() if isinstance(v, V) else f"{v:x}"
            if t.lstrip("0") == key[0][1].lstrip("0"):
                out.append(f"(the input {k})")
    return out


def same_parts(rec, name, width):
    """A wide register cut into parts of `width` bits (part 0 = most significant): for each part the signals and the parts of the register before the edge with the same value."""
    a, b = rec["signals"], rec["before"]
    if name not in a:
        raise KeyError(f"{name!r}: no such single signal; names: {sorted(n for n in a)[:40]}")
    def cut(v):
        t = v.bin()
        if len(t) % width:
            raise StimulusError(f"{name}: {len(t)} bits is not a multiple of {width}")
        return [t[i:i + width] for i in range(0, len(t), width)]
    now = cut(a[name])
    old = cut(b[name]) if name in b else []
    heads = _heads(a)
    out = []
    for p, t in enumerate(now):
        eq = []
        for n, vs in heads.items():
            if n == name:
                continue
            for i, v in enumerate(vs):
                if v.w == width and v.bin() == t:
                    eq.append(n if len(vs) == 1 else f"{n} element {i}")
        eq += [f"part {q} of {name} before the edge" for q, u in enumerate(old) if u == t]
        for k, v in rec["inputs"].items():
            if rec.get("widths", {}).get(k) == width and v is not None and (v.bin() if isinstance(v, V) else format(v, f"0{width}b")) == t:
                eq.append(f"the input {k}")
        out.append((p, V_hex(t), eq))
    return out


def changed_parts(rec, name, width):
    """The numbers of the parts (part 0 = most significant) of a wide register whose value changed in this edge."""
    a, b = rec["signals"][name].bin(), rec["before"][name].bin()
    if len(a) % width:
        raise StimulusError(f"{name}: {len(a)} bits is not a multiple of {width}")
    return [i // width for i in range(0, len(a), width) if a[i:i + width] != b[i:i + width]]


def applied(rec, piece, piece_before):
    """True when the value of `piece` after the edge is not the value of `piece_before` (the piece did something in this edge)."""
    return whole(rec["signals"], piece) != whole(rec["signals"], piece_before)


def V_hex(bits):
    return svvec.from_bin(bits).hex()


def _short(texts):
    t = " ".join(texts)
    return t if len(t) <= 80 else f"{t[:32]} ... {t[-32:]} ({len(texts)} element{'s' if len(texts) > 1 else ''}, {len(t)} characters)"


def edge_table(rec):
    """Text: every signal that changed in this edge, its value before and after, and the signals with the same value after."""
    a, b = _heads(rec["signals"]), _heads(rec["before"])
    lines = ["inputs: " + " ".join(f"{k}={_text(v)}" for k, v in rec["inputs"].items())
             + "   outputs: " + " ".join(f"{k}={_text(v)}" for k, v in rec["outputs"].items())]
    ch = changed(rec)
    for n in ch:
        lines.append(f"  {n}: before " + (_short([v.hex() for v in b[n]]) if n in b else "-") + "  after " + _short([v.hex() for v in a[n]])
                     + "  same value after the edge: " + (", ".join(same_as(rec, n)) or "(no other signal)"))
    keep = [n for n in a if n not in ch]
    lines.append("  not changed: " + (", ".join(keep) or "(none)"))
    return "\n".join(lines)


def _group(sig):
    """Lines for printing: a list whose last index runs over V of at most 16 bits is one row."""
    rows, order = {}, []
    for name, v in sig.items():
        if name.endswith("]") and v.w <= 16:
            head = name[:name.rindex("[")]
            key = head + "[*]"
        else:
            key = name
        if key not in rows:
            rows[key] = []
            order.append(key)
        rows[key].append(v.hex())
    return [(k, " ".join(rows[k])) for k in order]


def _summary(recs, lines):
    for s in recs.steps:
        t = f"step {s['step']}" + (f" ({s['label']})" if s["label"] else "") + f": {s['edges']} edge{'s' if s['edges'] != 1 else ''}"
        if s["edges"]:
            t += f" (edge {s['first_edge']}" + (f"..{s['first_edge'] + s['edges'] - 1})" if s["edges"] > 1 else ")")
        if s["until"]:
            u = ", ".join(f"{k}={'0x' + _text(v)}" for k, v in s["until"].items())
            t += f"; until {u}: " + ("reached" if s["reached"] else f"NOT reached in {s['edges']} edges")
        t += "; outputs after it: " + ", ".join(f"{k}={_text(v)}" for k, v in s["outputs"].items())
        for k, (want, ok) in s["expect"].items():
            t += f"; expect {k}={_text(want)}: " + ("OK" if ok else "DIFFERENT")
        lines.append(t)


def _fixarg(x):
    if x is None or x in ("", "none", "-"):
        return ()
    return "all" if x == "all" else tuple(p for p in x.split(",") if p)


def main(argv=None):
    ap = argparse.ArgumentParser(description="print every signal of RtlModel after every edge of a stimulus file")
    ap.add_argument("stimulus")
    ap.add_argument("--fix")
    ap.add_argument("--fix2")
    ap.add_argument("--edges")
    ap.add_argument("--signals")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--model", default="/code/work/rtl_model.py")
    a = ap.parse_args(argv)
    mod = load_model(a.model)
    itf = os.path.join(os.path.dirname(os.path.abspath(a.model)), "interface.json")
    lo, hi = 0, 10 ** 9
    if a.edges:
        p = a.edges.split(":")
        lo = int(p[0]) if p[0] else 0
        hi = int(p[-1]) if p[-1] else 10 ** 9
    want = [s for s in (a.signals or "").split(",") if s]

    def keep(name):
        return not want or any(name.startswith(w) for w in want)

    try:
        recs = run(mod.RtlModel(fix=_fixarg(a.fix)), a.stimulus, itf)
        recs2 = run(mod.RtlModel(fix=_fixarg(a.fix2)), a.stimulus, itf) if a.fix2 is not None else None
    except StimulusError as e:
        print("stimulus error:", e)
        return 2
    lines = [f"RtlModel(fix={_fixarg(a.fix)!r}), stimulus {a.stimulus}"]
    if recs.not_taken:
        lines.append(f"step() of this model has no parameter {', '.join(recs.not_taken)}: not passed")
    _summary(recs, lines)
    if recs2 is not None:
        lines.append(f"second run: RtlModel(fix={_fixarg(a.fix2)!r})")
        _summary(recs2, lines)
        if len(recs) != len(recs2):
            lines.append(f"the two runs take a different number of edges ({len(recs)} and {len(recs2)}): edges are compared by number as far as both exist")
    nhead = len(lines)
    if not a.summary:
        lines.append("")
        for i, r in enumerate(recs):
            if not lo <= r["edge"] <= hi:
                continue
            head = (f"edge {r['edge']} step {r['step']}" + (f" ({r['label']})" if r["label"] else "") + "  inputs: "
                    + " ".join(f"{k}={_text(v)}" for k, v in r["inputs"].items())
                    + "  outputs: " + " ".join(f"{k}={_text(v)}" for k, v in r["outputs"].items()))
            if recs2 is None:
                lines.append(head)
                lines += [f"    {k} = {t}" for k, t in _group({n: v for n, v in r["signals"].items() if keep(n)})]
            elif i < len(recs2):
                s2 = recs2[i]["signals"]
                diff = [(n, v, s2.get(n)) for n, v in r["signals"].items()
                        if keep(n) and (s2.get(n) is None or s2[n].hex() != v.hex() or s2[n].w != v.w)]
                lines.append(head + (f"  -- {len(diff)} signals differ" if diff else "  -- no signal differs"))
                lines += [f"    {n}: first run {v.hex()}   second run {_text(w)}" for n, v, w in diff]
    if len(lines) > 300 and not (a.all or a.edges or a.signals):
        names = {}
        for n, v in recs[-1]["signals"].items():
            head = n.split("[")[0]
            names[head] = names.get(head, 0) + 1
        lines = lines[:nhead] + ["", f"The full print has {len(lines) - nhead} lines for {len(recs)} edges: choose edges with --edges A:B and/or "
                                 "signals with --signals name,name (or --all). Signals of the model (number of elements):",
                                 "    " + ", ".join(f"{n} ({c})" if c > 1 else n for n, c in names.items())]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
