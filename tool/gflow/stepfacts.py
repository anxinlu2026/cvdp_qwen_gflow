"""stepfacts: which block of ONE unit is at fault, measured edge by edge against the reference's record of steps.

The unit is the design model (RtlModel of /code/work/rtl_model.py). It has control registers, a data
register, and it may read the result of a unit below. The reference gives, for one operation, the
record of steps: the value of the data after the load and after every operation applied to it.

Part 1, the data path alone. The data register is set to the value of a step of the record, the
control registers are set to every value in turn, ONE edge is run, and the data register is looked
at: it holds a later step of the record (this control value goes on from here; ANY later step, not
only the next one: one edge of a design usually applies several operations of the record), it kept
its value, or it holds something that is not in the record. The control block is not used in part 1: its
registers are forced. A step from which no control value goes on is a place where the data path
cannot do what the record needs: the fault is in the data path, at this step.
    The same is done while the unit below is still working: the edges in which no control value
    goes on are the edges in which the unit must wait.

Part 2, the control. The design runs by itself from reset, case by case. Every edge is judged with
part 1: the data register took the load, went on to a later step, kept its value, or left the
record. At an edge where it left the record (or changed although the operation was finished or not
started) the control values that would have gone on, or kept the data, at THIS edge are printed:
    CONTROL    another value of the control registers would have gone on or kept the data:
               the control block gave the wrong value at this edge.
    DATA PATH  no value of the control registers goes on from this step.
The edges of an operation after its first difference are not judged.

It prints facts. It does not say which line of the source is wrong and it changes nothing. The level
of the end signal and the result at the ports are not judged here (hsfacts does that); the end
signal after each edge is printed.

The description file is the one of hsfacts (start, end, result, modes, data, control,
data_registers, lower, needs_before, tail) with one more entry:
    "reference": {"file": "/code/work/ref_steps.py", "function": "steps"}      (a file you write, with this name)
The function is called as steps(mode, data, before):
    mode    the name of the mode of this operation (a key of "modes")
    data    the data inputs of this operation, {input: int}
    before  the operations that ended before it in the same run, oldest first: [(mode, data), ...]
            (for a mode that uses what an earlier operation stored)
and returns the record as a list, in the order the specification applies them (the texts of "op" are yours; they are only printed):
    [{"op": "load", "state": S0}, {"op": "name of the operation (its parameter)", "state": S1}, ...]
The values in `data` are the port values as ints; bringing them into the form the reference model takes
(bytes, words, their order) is done in this function. When no edge hits the record, look at this first.
The first entry is the data right after the inputs were taken, the last is the final data. A state
is an int, a list of ints, or a list of rows of ints (the elements of the data register). How a state
sits in the data register (rows or columns first, most or least significant element first) is given in the
description as "arrangement": one of "rows as written", "rows and columns exchanged" (a state that is a list
of rows), "as written", "reversed" (a list), "most significant element first", "least significant element
first" (an int). It is the arrangement of the specification, the one the pieces of the design work on; the
tool uses it and does not look for another. The print also gives, as a fact, how many forced edges hit the
record in each arrangement. Without "arrangement" the tool takes the one with the most hits and says so.
The design may do several steps of the record in one edge, or one step at a time: both are found.

usage: python3 /code/lib/stepfacts.py /code/work/handshake.json [options]
    --fix a,b | all | all,c | none   switches of the design model, as in hsfacts ("all" = the names in SWITCHES)
    --case NAME                      part 2 for this case only (names as printed)
    --step K                         only this: part 1 in detail for step K of the record. For every control value what one
                                     edge does, and for every signal with the shape of the data register (the pieces of the
                                     chain) the step of the record it holds after the edge, or the nearest step and the
                                     elements that differ. Control values with the same print are listed together.
    --table                          the one-edge table of the control block: for every control value the next value
                                     without a start and with a start in each mode, and what the data register does
    --all                            print every edge of part 2 (default: runs of edges that keep the data are shortened)
    --model PATH                     default /code/work/rtl_model.py
In Python: `import stepfacts`; `r = stepfacts.measure("/code/work/handshake.json", fix=("all", "candidate"))`;
    r["part1"]["dead"] = steps from which no control value goes on, r["different"] = the differences of part 2
    as (case, operation, edge, block, text), and `stepfacts.text(r)` is the print.
Every run appends its last lines to tool_runs.log beside the description file.
"""
import argparse
import importlib.util
import itertools
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sigdump  # noqa: E402
import hsfacts  # noqa: E402

MAXBITS = 8      # control registers with more bits than this in all: only the values seen in the runs are forced


class DescriptionError(Exception):
    pass


def _val(v):
    return v.int() if v.is_known() else None


def _elems(sig, name):
    names = [n for n in sig if n == name or n.startswith(name + "[")]
    if not names:
        raise DescriptionError(f"{name!r} is not a signal of the model; names: {sorted({n.split('[')[0] for n in sig})}")
    return names


def _arrangements(state, n, width):
    """The ways a state of the record can sit in a data register of n elements: {name: tuple of n ints}."""
    out = {}
    if isinstance(state, int):
        mask = (1 << width) - 1
        parts = [(state >> (width * i)) & mask for i in range(n)]
        out["most significant element first"] = tuple(reversed(parts))
        out["least significant element first"] = tuple(parts)
        return out
    if state and isinstance(state[0], (list, tuple)):
        rows = [list(r) for r in state]
        flat = [x for r in rows for x in r]
        if len(flat) == n:
            out["rows as written"] = tuple(flat)
            if all(len(r) == len(rows[0]) for r in rows):
                out["rows and columns exchanged"] = tuple(rows[i][j] for j in range(len(rows[0])) for i in range(len(rows)))
        return out
    flat = list(state)
    if len(flat) == n:
        out["as written"] = tuple(flat)
        out["reversed"] = tuple(reversed(flat))
    return out


def _rng(vals, fmt):
    """Control values as text; runs of single-register values are shortened."""
    vals = sorted(vals)
    if not vals:
        return "none"
    if len(vals[0]) != 1:
        return " ".join(fmt(v) for v in vals)
    xs, out, i = [v[0] for v in vals], [], 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[j] + 1:
            j += 1
        out.append(f"{xs[i]:x}" if i == j else f"{xs[i]:x}-{xs[j]:x}")
        i = j + 1
    return ",".join(out)


class Unit:
    def __init__(self, hs, fix, model, interface):
        self.hs = hs
        self.mod = sigdump.load_model(model)
        if isinstance(fix, str):
            fix = tuple(p for p in fix.split(",") if p and p != "none")
        if "all" in fix:
            fix = tuple(dict.fromkeys(list(getattr(self.mod.RtlModel, "SWITCHES", {})) + [x for x in fix if x != "all"]))
        self.fix = tuple(fix)
        self.interface = interface
        self.rst, self.act = interface["reset"]["name"], int(interface["reset"]["active"])
        self.m = self.mod.RtlModel(fix=self.fix)
        sig = sigdump.signals(self.m)
        self.ctl = list(hs.get("control", []))
        if not self.ctl:
            raise DescriptionError("the description names no control register (\"control\")")
        for c in self.ctl:
            if c not in sig:
                raise DescriptionError(f"control register {c!r} is not a signal of the model (a register that is an array is named by its elements); names: {sorted({n.split('[')[0] for n in sig})}")
        self.cw = [sig[c].w for c in self.ctl]
        regs = hs.get("data_registers", [])
        if len(regs) != 1:
            raise DescriptionError("stepfacts follows ONE data register: give exactly one name in \"data_registers\" (the register the record of steps describes)")
        self.data = regs[0]
        self.dnames = _elems(sig, self.data)
        self.dw = sig[self.dnames[0]].w
        ref = hs.get("reference")
        if not ref:
            raise DescriptionError("the description has no \"reference\": {\"file\": ..., \"function\": \"steps\"}")
        s = importlib.util.spec_from_file_location("stepfacts_reference", ref["file"])
        r = importlib.util.module_from_spec(s)
        d = os.path.dirname(os.path.abspath(ref["file"]))
        if d not in sys.path:
            sys.path.insert(0, d)
        s.loader.exec_module(r)
        self.steps_fn = getattr(r, ref.get("function", "steps"))
        self.off = dict({k: 0 for k in interface["inputs"]}, **{self.rst: 1 - self.act})
        self.arr = None
        self.seen = set()

    # ---- the reference's record
    def record(self, mode, data, before):
        rec = self.steps_fn(mode, {k: hsfacts._int(v) for k, v in data.items()}, [(m, {k: hsfacts._int(v) for k, v in d.items()}) for m, d in before])
        if not isinstance(rec, list) or len(rec) < 2 or not all(isinstance(x, dict) and "state" in x for x in rec):
            raise DescriptionError("the reference function must return a list of at least two entries {\"op\": text, \"state\": value}: the data after the load, then after every operation")
        return rec

    def flat(self, rec, arr=None):
        out = []
        for x in rec:
            a = _arrangements(x["state"], len(self.dnames), self.dw)
            if not a:
                raise DescriptionError(f"a state of the record does not have the {len(self.dnames)} elements of {self.data}: {x['state']!r}")
            out.append(a if arr is None else a[arr])
        return out

    # ---- running
    def fmt(self, c):
        return "/".join("x" if v is None else f"{v:x}" for v in c)

    def ctl_of(self, sig):
        return tuple(_val(sig[c]) for c in self.ctl)

    def data_of(self, sig):
        return tuple(_val(sig[n]) for n in self.dnames)

    def values(self):
        if sum(self.cw) <= MAXBITS:
            return list(itertools.product(*[range(1 << w) for w in self.cw]))
        return sorted(v for v in self.seen if None not in v)

    def run(self, edges):
        recs = sigdump.run(self.mod.RtlModel(fix=self.fix), {"steps": [{"set": e, "edges": 1} for e in edges]}, interface=self.interface)
        for r in recs:
            self.seen.add(self.ctl_of(r["signals"]))
        return recs

    def force(self, base, c, data, inputs):
        st = dict(base)
        for n, v in zip(self.ctl, c):
            st[n] = v
        if data is not None:
            for n, v in zip(self.dnames, data):
                st[n] = v
        return sigdump.step_once(self.m, inputs, state=st, interface=self.interface)

    def outcome(self, rec, flat, k):
        """What one edge did to the data register, seen from step k of the record (None: before the load)."""
        a, b = self.data_of(rec["signals"]), self.data_of(rec["before"])
        if None in a:
            return "x", None
        if a == b:
            return "keep", k
        for j, f in enumerate(flat):
            if f == a and (k is None or j > k or j == 0):
                return "step", j
        return "off", None

    def pieces(self, rec, flat, k):
        """Every signal of the model with the shape of the data register (the pieces of the chain), after this edge:
        the step of the record whose value it has, or the nearest later step and the elements that differ."""
        heads = {}
        for n, v in rec["signals"].items():
            heads.setdefault(n.split("[")[0], []).append((n, v))
        out = []
        for h, vs in heads.items():
            if h == self.data or len(vs) != len(self.dnames) or any(v.w != self.dw for _, v in vs):
                continue
            val = tuple(_val(v) for _, v in vs)
            if None in val:
                unk = [vs[i][0][len(h):] for i in range(len(val)) if val[i] is None]
                if len(unk) == len(val):
                    out.append((h, "unknown values"))
                    continue
                j = next((j for j in range(len(flat)) if all(a is None or a == b for a, b in zip(val, flat[j]))), None)
                out.append((h, f"{len(unk)} of {len(val)} elements unknown ({' '.join(unk)}); the others " + (f"are those of step {j}" if j is not None else "fit no step of the record")))
                continue
            j = next((j for j in range(len(flat)) if flat[j] == val), None)
            if j is not None:
                out.append((h, f"= step {j}"))
                continue
            best = min(range(k, len(flat)), key=lambda j: (sum(a != b for a, b in zip(flat[j], val)), j))
            bad = [vs[i][0][len(h):] for i in range(len(val)) if flat[best][i] != val[i]]
            out.append((h, "no step of the record" if len(bad) > len(val) // 2 else f"no step of the record; nearest is step {best}, {len(bad)} of {len(val)} elements differ: {' '.join(bad)}"))
        return out

    def start_inputs(self, mode, data):
        e = dict(self.off, **{self.hs["start"]: 1})
        e.update({k: hsfacts._int(v) for k, v in self.hs["modes"][mode].items()})
        e.update({k: hsfacts._int(v) for k, v in data.items()})
        return e


def _names(rec):
    return [str(x.get("op", f"step {i}")) for i, x in enumerate(rec)]


def measure(hs, fix=(), model="/code/work/rtl_model.py", interface=None, only=None, step=None, table=False):
    path = hs if isinstance(hs, str) else None
    hs = hsfacts.load(hs)
    if interface is None:
        interface = os.path.join(os.path.dirname(os.path.abspath(model)), "interface.json")
    if isinstance(interface, str):
        interface = json.load(open(interface))
    u = Unit(hs, fix, model, interface)
    r = {"hs": hs, "fix": u.fix, "unit": u, "different": [], "path": path, "notes": []}
    modes, d0 = list(hs["modes"]), hs["data"][0]
    need = hs.get("needs_before", {})
    prime = next((need[m] for m in modes if need.get(m)), modes[0])
    tail = int(hs.get("tail", 40))
    # the base state of part 1: one operation in the mode others need has run; the lower result is complete
    edges = [dict(u.off, **{u.rst: u.act}), u.start_inputs(prime, d0)] + [dict(u.off) for _ in range(tail)]
    recs = u.run(edges)
    base = dict(recs[-1]["signals"])
    ref = u.record(prime, d0, [])
    N = len(ref) - 1
    names = _names(ref)
    idle_in = dict(u.off, **{k: hsfacts._int(v) for k, v in d0.items()})
    # runs of part 2 first, so that the control values seen are known when the registers are wide
    plans = {n: p for n, p in hsfacts.cases(hs).items() if not any(k == "busy" for k, _, _ in p) and (not only or n == only)}
    runs = {}
    for name, plan in plans.items():
        e, starts = hsfacts._stimulus(hs, plan, interface)
        runs[name] = (plan, e, starts, u.run(e))
    vals = u.values()
    r["values"] = vals
    if sum(u.cw) > MAXBITS:
        r["notes"].append(f"the control registers have {sum(u.cw)} bits: only the {len(vals)} values seen in the runs are forced")
    # arrangement
    cand = u.flat(ref)
    score = {}
    for arr in cand[0]:
        fl = [c[arr] for c in cand]
        n = 0
        for c in vals:
            for m in modes:
                w, j = u.outcome(u.force(base, c, None, u.start_inputs(m, d0)), fl, None)
                n += w == "step" and j == 0
            for k in range(N):
                w, j = u.outcome(u.force(base, c, fl[k], idle_in), fl, k)
                n += w == "step"
        score[arr] = n
    given = hs.get("arrangement")
    if given is not None and given not in score:
        raise DescriptionError(f"\"arrangement\": {given!r} is not a way a state of this record sits in {u.data}; the ways: {sorted(score)}")
    arr = given if given is not None else max(score, key=score.get)
    u.arr = arr
    r["arrangement"] = (arr, score, given is not None)
    fl = [c[arr] for c in cand]
    # part 1
    hit, info, near = {}, {}, {}
    for k in range(N + 1):
        hit[k] = {}
        for c in vals:
            rec = u.force(base, c, fl[k], idle_in)
            w, j = u.outcome(rec, fl, k)
            info[(k, c)] = (w, j, u.ctl_of(rec["signals"]), rec)
            hit[k].setdefault(j if w == "step" else w, []).append(c)
            if w == "off" and k < N:                 # a near hit: the edge does the operations up to a later step and is wrong in a part of the elements
                a = u.data_of(rec["signals"])
                jb = min(range(k + 1, N + 1), key=lambda j: (sum(x != y for x, y in zip(fl[j], a)), j))
                nd = sum(x != y for x, y in zip(fl[jb], a))
                if nd <= len(a) // 2:
                    near.setdefault(k, {}).setdefault((jb, nd), []).append(c)
    load = {}
    for m in modes:
        for c in vals:
            w, j = u.outcome(u.force(base, c, None, u.start_inputs(m, d0)), fl, None)
            if w == "step" and j == 0:
                load.setdefault(m, []).append(c)
    reach, todo = {0}, [0]
    while todo:
        k = todo.pop()
        for j in hit[k]:
            if isinstance(j, int) and j not in reach:
                reach.add(j)
                todo.append(j)
    goes = [k for k in range(N) if any(isinstance(j, int) for j in hit[k])]
    dead = [k for k in sorted(reach) if k != N and k not in goes]
    r["part1"] = {"N": N, "names": names, "hit": hit, "load": load, "reach": sorted(reach), "dead": dead, "goes": goes, "final": N in reach, "info": info, "near": near, "elems": len(u.dnames)}
    # part 1, while a unit below is working
    low = []
    for lw in hs.get("lower", []):
        h = lw["result"]
        final = recs[-1]["signals"][h].hex() if h in recs[-1]["signals"] else None
        rows = []
        for t in range(1, len(recs) - 1):
            b = recs[1 + t]["before"]
            done = h in b and b[h].hex() == final
            ok = [c for c in vals if u.outcome(u.force(dict(b), c, fl[0], idle_in), fl, 0)[0] == "step"]
            rows.append((t, done, tuple(ok)))
            if done and len(rows) > 2 and rows[-2][1]:
                break
        low.append((lw.get("name", h), rows))
    r["part1"]["lower"] = low
    if step is not None:
        if not 0 <= step <= N:
            raise DescriptionError(f"--step {step}: the record has the steps 0..{N}")
        det = []
        for c in vals:
            w, j, nxt, rec = info[(step, c)]
            det.append((c, w, j, nxt, sigdump.same_as(rec, u.data), u.pieces(rec, fl, step)))
        r["detail"] = (step, det)
    if table:
        rows = []
        for c in vals:
            row = {"c": c, "none": info[(0, c)][2], "start": {}}
            for m in modes:
                rec = u.force(base, c, None, u.start_inputs(m, d0))
                w, j = u.outcome(rec, fl, None)
                row["start"][m] = (u.ctl_of(rec["signals"]), "takes the load" if (w == "step" and j == 0) else "keeps" if w == "keep" else "changes the data")
            ks = [k for k in range(N) if info[(k, c)][0] == "step"]
            row["data"] = "keeps the data" if all(info[(k, c)][0] == "keep" for k in range(N + 1)) else ("goes on from step " + ",".join(map(str, ks))) if ks else "changes the data, never to a later step of the record" if not any(info[(k, c)][0] == "x" for k in range(N + 1)) else "gives unknown values"
            rows.append(row)
        r["table"] = rows
    # part 2
    r["cases"] = {}
    for name, (plan, e, starts, rr) in runs.items():
        datas = [d for kind, m, d in plan if kind == "start"]
        ops, before = [], []
        for n, (se, mode, kind) in enumerate(starts):
            unmet = need.get(mode) and not any(m == need[mode] for m, _ in before)
            ops.append({"edge": se, "mode": mode, "data": datas[n], "judged": not unmet,
                        "flat": None if unmet else [c[arr] for c in u.flat(u.record(mode, datas[n], list(before)))],
                        "names": None if unmet else _names(u.record(mode, datas[n], list(before))), "need": need.get(mode)})
            before.append((mode, datas[n]))
        lines, op, k, stopped, fl2, nm = [], None, None, False, fl, names
        lowfinal = {}
        for n, o in enumerate(ops):
            last = (ops[n + 1]["edge"] if n + 1 < len(ops) else len(rr)) - 1
            lowfinal[n] = {lw["result"]: rr[last]["signals"][lw["result"]].hex() for lw in hs.get("lower", []) if lw["result"] in rr[last]["signals"]}
        nop = -1

        def close(nop, k, i):
            if nop >= 0 and ops[nop]["judged"] and not stopped and k != len(ops[nop]["flat"]) - 1:
                adv = [c for c in vals if u.outcome(u.force(dict(rr[i]["before"]), c, None, dict(rr[i]["inputs"])), ops[nop]["flat"], k)[0] == "step"] if k is not None else []
                t = (f"the operation ends with the data at step {k} of {len(ops[nop]['flat']) - 1}" if k is not None else "the load was not taken") + (f"; control {_rng(adv, u.fmt)} would go on at the last edge" if adv else "")
                lines.append((i, "", "", "DIFFERENT", "CONTROL" if (adv or k is None) else "DATA PATH", t))
                r["different"].append((name, nop + 1, i, "CONTROL" if (adv or k is None) else "DATA PATH", t))

        for i in range(1, len(rr)):
            rec = rr[i]
            if nop + 1 < len(ops) and ops[nop + 1]["edge"] == i:
                close(nop, k, i - 1)
                nop += 1
                op, k, stopped = ops[nop], None, False
                if op["judged"] and any(d[0] == name for d in r["different"]):
                    op["judged"], op["need"] = False, None
                lines.append((i, "", "", "op", "", f"operation {nop + 1}: mode {op['mode']}" + ("" if op["judged"] else "   -- not judged: " + (f"no operation in mode {op['need']} before it, its result has no requirement" if op["need"] else "the case has a difference before it"))))
            cb = u.fmt(u.ctl_of(rec["before"]))
            end = rec["outputs"].get(hs["end"])
            end = "x" if end is None or not end.is_known() else f"{end.int():x}"
            a, b = u.data_of(rec["signals"]), u.data_of(rec["before"])
            lowc = "" if not hs.get("lower") else ("complete" if nop >= 0 and all(rec["before"][h].hex() == v for h, v in lowfinal[nop].items()) else "working ") if nop >= 0 else "        "
            head = (i, cb, end, lowc)
            if stopped or (op is not None and not op["judged"]):
                lines.append(head + ("fact", "keeps" if a == b else "changes"))
                continue
            flat = op["flat"] if op is not None else fl
            nmm = op["names"] if op is not None else names
            if op is not None and ops[nop]["edge"] == i:
                w, j = u.outcome(rec, flat, None)
                if w == "step" and j == 0:
                    k = 0
                    lines.append(head + ("ok", "takes the load (step 0)"))
                else:
                    ok = [c for c in vals if (lambda x: x[0] == "step" and x[1] == 0)(u.outcome(u.force(dict(rec["before"]), c, None, dict(rec["inputs"])), flat, None))]
                    t = "the start edge does not take the load" + (f"; control {_rng(ok, u.fmt)} would take it" if ok else "; no control value takes it")
                    lines.append(head + ("DIFFERENT", "CONTROL" if ok else "DATA PATH", t))
                    r["different"].append((name, nop + 1, i, "CONTROL" if ok else "DATA PATH", t))
                    stopped = True
                continue
            w, j = u.outcome(rec, flat, k)
            final = op is not None and k == len(flat) - 1
            if w == "step" and k is not None and not final:
                lines.append(head + ("ok", f"-> step {j} ({' '.join(nmm[k + 1:j + 1])})"))
                k = j
                continue
            if w == "keep":
                if k is None or final:
                    lines.append(head + ("keep", "keeps"))
                else:
                    adv = [c for c in vals if u.outcome(u.force(dict(rec["before"]), c, None, dict(rec["inputs"])), flat, k)[0] == "step"]
                    lines.append(head + ("keep", "keeps; " + (f"control {_rng(adv, u.fmt)} would go on" if adv else "no control value would go on at this edge")))
                continue
            adv, keep = [], []
            for c in vals:
                ww, _ = u.outcome(u.force(dict(rec["before"]), c, None, dict(rec["inputs"])), flat, k)
                if ww == "step" and k is not None and not final:
                    adv.append(c)
                if ww == "keep":
                    keep.append(c)
            what = "unknown values in the data register" if w == "x" else "the data register changes"
            if k is None:                            # before any load the register may hold a value that many control values keep by chance: only those that keep the data in part 1
                keep = [c for c in keep if c in hit[0].get("keep", [])] or keep
            if k is None:
                block, why = ("CONTROL", f"{what} without a start; control {_rng(keep, u.fmt)} would keep it") if keep else ("DATA PATH", f"{what} without a start; no control value keeps it")
            elif final:
                block, why = ("CONTROL", f"{what} after the final step; control {_rng(keep, u.fmt)} would keep it") if keep else ("DATA PATH", f"{what} after the final step; no control value keeps it")
            elif adv:
                block, why = "CONTROL", f"{what} to a value that is not in the record; control {_rng(adv, u.fmt)} would go on from step {k}"
            elif lowc.strip() == "working" and keep:
                block, why = "CONTROL", f"{what} to a value that is not in the record while the unit below is working; no control value goes on at this edge, control {_rng(keep, u.fmt)} would keep the data"
            else:
                block, why = "DATA PATH", f"{what} to a value that is not in the record; no control value goes on from step {k}" + (f" (control {_rng(keep, u.fmt)} would keep the data)" if keep else "")
            lines.append(head + ("DIFFERENT", block, why))
            r["different"].append((name, max(nop + 1, 0), i, block, why))
            if op is None:
                break
            stopped = True
        close(nop, k, len(rr) - 1)
        r["cases"][name] = {"lines": lines, "edges": len(rr)}
    return r


def text(r, every=False):
    u, p, hs = r["unit"], r["part1"], r["hs"]
    N, names, hit = p["N"], p["names"], p["hit"]
    L = [f"stepfacts  switches: {', '.join(r['fix']) or 'none'}   control: {', '.join(u.ctl)}   data register: {u.data}   record: {N + 1} steps (0 = the load, {N} = final)"]
    L += ["  note: " + n for n in r["notes"]]
    arr, score, given = r["arrangement"]
    L.append(f"arrangement of the record in the data register: {arr}" + (" (given in the description)" if given else " (NOT given in the description: the one with the most hits)") + "   (forced edges after which the data register held a later step of the record: " + ", ".join(f"{a}: {n}" for a, n in score.items()) + ")")
    if not max(score.values()):
        L.append("  NO edge hits the record in any arrangement: see that \"reference\" gives the record of this unit, that \"data_registers\" names the register it describes, and that the pieces of the data path were checked alone; when these are right, the data path has a fault in every step: look at --step 0")
    L += ["", "== part 1: the data path alone (control registers forced, one edge, the unit below has finished) =="]
    L.append("  the load: " + ("; ".join(f"start in mode {m}: control {_rng(v, u.fmt)}" for m, v in p["load"].items()) or "NO control value takes the load in any mode"))
    for k in range(N + 1):
        adv = {j: cs for j, cs in hit[k].items() if isinstance(j, int)}
        nr = p["near"].get(k, {})
        if not adv and k not in p["reach"] and not nr:
            continue
        t = f"  from step {k:2d} [{names[k]}]: "
        t += " | ".join(f"control {_rng(cs, u.fmt)} -> step {j} ({' '.join(names[k + 1:j + 1])})" for j, cs in sorted(adv.items())) if adv else ("the final step" if k == N else "NO control value goes on")
        if nr and not adv:
            t += "; NEAR: " + " | ".join(f"control {_rng(cs, u.fmt)} gives the value of step {j} but for {nd} of {p['elems']} elements ({' '.join(names[k + 1:j + 1])})" for (j, nd), cs in sorted(nr.items()))
        t += f"   [keeps: {_rng(hit[k].get('keep', []), u.fmt)}; unknown values: {_rng(hit[k].get('x', []), u.fmt)}; not in the record: {_rng(hit[k].get('off', []), u.fmt)}]"
        L.append(t + ("" if k in p["reach"] else "   (not reached from the load)"))
    ends = sorted({j for k in range(N) for j in hit[k] if isinstance(j, int)} | {j for k in p["near"] for (j, nd) in p["near"][k]})
    starts = sorted({k for k in range(N) if any(isinstance(j, int) for j in hit[k])} | set(p["near"]))
    if ends:
        L.append(f"  how this design cuts the record into edges (from the hits and near hits above): an edge starts at step {' '.join(map(str, starts))} and ends at step {' '.join(map(str, ends))}")
        L.append("    the steps between are passed inside an edge; the data register never holds them, and that is no difference")
        for k in p["dead"]:
            nxt = next((j for j in sorted(set(starts) | set(ends)) if j > k), None)
            if nxt is not None and k not in starts:
                L.append(f"    no edge starts at step {k}, which is reached; the next edge starts at step {nxt}: to get there, one edge from step {k} applies {' '.join(names[k + 1:nxt + 1])} and nothing else")
    L.append(f"  steps reached from the load: {' '.join(map(str, p['reach']))}")
    L.append(f"  steps from which some control value goes on: {' '.join(map(str, p['goes'])) or 'none'}")
    L.append(f"  the final step {N} is reached from the load: {'yes' if p['final'] else 'NO'}")
    L.append("  DATA PATH: reached steps from which no control value goes on: " + (" ".join(str(k) for k in p["dead"]) or "none"))
    for name, rows in p["lower"]:
        L.append(f"  while the unit below ({name}) works, the control values that go on from step 0, by edges after its start:")
        i = 0
        while i < len(rows):
            j = i
            while j + 1 < len(rows) and rows[j + 1][1:] == rows[i][1:]:
                j += 1
            L.append(f"    {rows[i][0]}{'' if i == j else '..' + str(rows[j][0])}: {_rng(rows[i][2], u.fmt)}   (its result is {'complete' if rows[i][1] else 'not complete'})")
            i = j + 1
    if "detail" in r:
        k, det = r["detail"]
        L += ["", f"== step {k} [{names[k]}] in detail: one edge for every control value =="]
        L.append("  (for every control value: what the edge does to the data register; then every signal that has the shape of the data register.")
        L.append("   Such a signal is a piece of the chain: a stage computed inside this one edge, each from the one before it. \"X = step J\" says that")
        L.append("   stage X, inside the edge, has brought the data to step J of the record. The register takes the value of the last stage; it is")
        L.append("   not expected to hold the step of an earlier stage. A piece with unknown elements read something not yet written in this evaluation.")
        L.append(f"   The record after step {k}: " + "; ".join(f"step {j} = after {names[j]}" for j in range(k + 1, min(k + 6, N + 1))) + ")")
        groups = {}
        for c, w, j, nxt, same, pcs in det:
            what = f"-> step {j} ({' '.join(names[k + 1:j + 1])})" if w == "step" else {"keep": "keeps", "x": "unknown values", "off": "not in the record"}[w]
            groups.setdefault((what, tuple(same), tuple(pcs)), []).append((c, nxt))
        for (what, same, pcs), cs in groups.items():
            L.append(f"  control {_rng([c for c, _ in cs], u.fmt)}: {what}; the data register holds the value of: {', '.join(same) or 'no other signal'}")
            for h, t in pcs:
                if t not in ("no step of the record", "unknown values"):
                    L.append(f"      {h:18s} {t}")
            for word in ("unknown values", "no step of the record"):
                rest = [h for h, t in pcs if t == word]
                if rest:
                    L.append(f"      {word}: {', '.join(rest)}")
        return "\n".join(L)
    if "table" in r:
        L += ["", "== the one-edge table of the control block (the unit below has finished) =="]
        for row in r["table"]:
            L.append(f"  control {u.fmt(row['c'])}: no start -> {u.fmt(row['none'])}; " + "; ".join(f"start in mode {m} -> {u.fmt(n)} ({w})" for m, (n, w) in row["start"].items()) + f"; data: {row['data']}")
    L += ["", "== part 2: the design's own walk (edge | control before the edge | end signal after it | unit below | data register) =="]
    for name, c in r["cases"].items():
        L.append(f"case {name}  ({c['edges']} edges, edge 0 = reset)")
        run = 0
        for i, ln in enumerate(c["lines"]):
            if ln[3] == "op":
                L.append("  " + ln[5])
                run = 0
                continue
            kind = ln[4]
            nxt = c["lines"][i + 1] if i + 1 < len(c["lines"]) else None
            quiet = kind in ("keep", "fact") and not every
            if quiet:
                run += 1
                if run > 2 and nxt is not None and nxt[3] != "op" and nxt[4] == kind and nxt[5] == ln[5]:
                    if run == 3:
                        L.append("        ...")
                    continue
            else:
                run = 0
            t = f"  {ln[0]:4d} | {ln[1]:>3s} | {ln[2]} | {ln[3]} | "
            L.append(t + (f"DIFFERENT  {ln[5]}: {ln[6]}" if kind == "DIFFERENT" else ln[5]))
            if kind == "DIFFERENT" and ln[1] != "":
                L.append("        (the edges of this operation after this one are not judged)")
    L.append("")
    seen, uniq = set(), []
    for name, n, i, block, why in r["different"]:
        if (block, why) not in seen:
            seen.add((block, why))
            uniq.append((name, n, i, block, why))
    n1 = len(p["dead"]) or (0 if p["final"] else 1)
    L.append(f"part 1, data path: {'the final step is reached, no step without a control value that goes on' if p['final'] and not p['dead'] else 'DIFFERENT: ' + ('no control value goes on from step ' + ', '.join(map(str, p['dead'])) if p['dead'] else 'the final step is not reached')}")
    if uniq:
        L.append(f"part 2, differences ({len(uniq)}; the same difference in several cases is listed once):")
        for name, n, i, block, why in uniq:
            L.append(f"  {block}: {why}   (first in case {name}, operation {n}, edge {i})")
    else:
        L.append("part 2, differences: none")
    L.append(f"differences: part 1 (data path) {n1}, part 2 {len(uniq)}" + (f" (data path {sum(1 for x in uniq if x[3] == 'DATA PATH')}, control {sum(1 for x in uniq if x[3] == 'CONTROL')})" if uniq else ""))
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("description")
    ap.add_argument("--fix", default="none")
    ap.add_argument("--case")
    ap.add_argument("--step", type=int)
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--model", default="/code/work/rtl_model.py")
    a = ap.parse_args()
    try:
        res = measure(a.description, a.fix, a.model, only=a.case, step=a.step, table=a.table)
    except (DescriptionError, sigdump.StimulusError) as ex:
        print("stepfacts: " + str(ex))
        sys.exit(2)
    except (OSError, KeyError, ValueError) as ex:
        print(f"stepfacts: the description, the record file or the model could not be used ({type(ex).__name__}: {ex}); see the text at the top of /code/lib/stepfacts.py for the entries of the description")
        sys.exit(2)
    out = text(res, a.all)
    print(out)
    lines = out.split("\n")
    hsfacts.log(a.description, "stepfacts", sys.argv[2:], lines[next((i for i, x in enumerate(lines) if x.startswith("part 1, data path:")), max(len(lines) - 12, 0)):])
