"""piececheck: run ONE piece of RtlModel on inputs you choose and compare its output with values you give (a library).

A piece of the design reads signals that other pieces compute in the same step(). To give a piece its own inputs,
hold those signals: a held signal keeps the value you give for the whole step(); the statements of the model that
write it are not applied (the print counts them). The piece then reads your values, and its output is read after
the step(). Registers are set with state= (as sigdump.set_state) and take their new value at the edge as usual.

    import sys; sys.path.insert(0, "/code/lib")
    import sigdump, piececheck
    mod = sigdump.load_model("/code/work/rtl_model.py")
    r = piececheck.run(mod.RtlModel(fix="all"), hold={"AddRoundKey": a}, read=["MixColumns"],
                       state={"round_ff": 2}, inputs={})
        hold:   {signal: value}   signals by the names sigdump prints ("sub.name", "name[1]"); a value is an int,
                                  a text like "0x1f", "x", a V, or a nested list of these in the shape the model has
        read:   [signal, ...]     signals read after the step()
        state, inputs, interface: as sigdump.step_once
      -> {"read": {signal: nested ints (None = a bit is X)}, "writes_ignored": {signal: n}, "record": the sigdump record}
         writes_ignored 0 means that step() does not write this signal: then the piece reads it from somewhere else
         (a register: use state=; a local variable: cut the method so that the piece reads the signal).

    piececheck.check(model, hold, read, want, ...)   as run(), and compares read[signal] with want[signal] element by
                                                     element; returns {"same": bool, "diff": [(signal, index, got, want)], ...}
                                                     and print(piececheck.text(result)) prints it.

Compare with a function of the reference model on many inputs (one call = one row of the table):
    import ref_model as ref     # sys.path.insert(0, "/code/work/model")
    r = piececheck.against(mod.RtlModel(fix="all"), "AddRoundKey", "MixColumns", ref.InvMixColumns, inputs,
                           place="rows as written", name="InvMixColumns")
    print(piececheck.text_against(r))
        hold, read: the signal that holds the input (the state before) and the signal read after one step();
                    a piece that reads several signals: hold = {signal: function(input) -> its value in the reference's form, ...}
                    (for example {"xtimes0e": lambda s: [[ref.gf_mul(0x0e, b) for b in row] for row in s], ...}); each value is placed as `place` says
        ref:        the function of the reference model for this step: ref(input) -> wanted output
        inputs:     inputs in the form of the reference model (a state, a word, ...): piececheck.befores(record, op)
                    gives the states before each step `op` of a step record; add random ones
        place:      how an input is put in the design's form: an arrangement (as place() below) or your function
        take:       how the design's value is brought back to the reference's form; default: the inverse of place
        state=, inputs_ports=, interface=: as run(), the same for every input; each input runs on a copy of `model`
      -> {"name", "hold", "read", "compared", "differ": [(k, input, design, wanted)], "same"}
    A wanted value is never changed to make the design agree; X bits of the design are None and differ.

A record of the reference model (a list of states, or of {"op", "state"}, or of tuples whose last element is the state) gives the pairs of a piece:
    piececheck.pairs(record) -> [(k, op, state before, state after)]: the step k+1 of the record applied to state k.
    piececheck.place(state, "rows as written" | "rows and columns exchanged" | "as written" | "reversed")
        a state of the record (a list of rows, or a list) in the form of the design's array; arrangement as in stepfacts.
    piececheck.take(value, arrangement)  the inverse: the design's array as a state of the record.
Which signal holds the input of a piece and which its output, and the arrangement, are yours to say (notes.md).
The tool prints facts; it does not say which piece or statement is wrong.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sigdump  # noqa: E402
from svvec import V, short_hex as svvec_short_hex  # noqa: E402


class _Held(list):
    """A list whose elements are not written (all, or the indexes in `only`)."""

    def __init__(self, items, log, name, only=None, reads=None):
        super().__init__(items)
        self._log, self._name, self._only, self._reads = log, name, only, reads

    def __getitem__(self, i):
        v = super().__getitem__(i)
        if self._reads is not None and (self._only is None or i in self._only) and not isinstance(v, list):
            self._reads[self._name] = self._reads.get(self._name, 0) + 1     # a value read (x[i][j] = v reads only the row, to write in it)
        return v

    def __setitem__(self, i, v):
        if self._only is None or i in self._only:
            self._log[self._name] += 1
        else:
            super().__setitem__(i, v)

    def _no(self, *a, **k):
        self._log[self._name] += 1

    append = extend = insert = pop = remove = clear = sort = reverse = __delitem__ = __iadd__ = _no


def _held(value, log, name, reads=None):
    if isinstance(value, list):
        return _Held([_held(x, log, name, reads) for x in value], log, name, reads=reads)
    return value


def _path(name):
    parts = re.findall(r"[A-Za-z_]\w*|\[\d+\]", name)
    if "".join(parts) != name.replace(".", ""):
        raise sigdump.StimulusError(f"{name!r}: not a name of the form a.b[1][2]")
    return [int(q[1:-1]) if q.startswith("[") else q for q in parts]


def _get(obj, steps, name):
    for q in steps:
        try:
            obj = obj[q] if isinstance(q, int) else getattr(obj, q)
        except (AttributeError, IndexError, TypeError):
            raise sigdump.StimulusError(f"{name!r}: the model has no such signal")
    return obj


def _ints(x):
    if isinstance(x, (list, tuple)):
        return [_ints(y) for y in x]
    if isinstance(x, V):
        return x.int_or_none()
    return x


def _set(obj, k, v):
    if isinstance(k, int):
        list.__setitem__(obj, k, v)
    else:
        object.__setattr__(obj, k, v)


def _plain(x):
    return [_plain(y) for y in x] if isinstance(x, list) else x


def run(model, hold=None, read=(), state=None, inputs=None, interface=None):
    log, undo, reads = {}, [], {}
    if state:
        sigdump.set_state(model, state)
    try:
        for name, value in (hold or {}).items():
            steps = _path(name)
            if len(steps) == 1 and isinstance(steps[0], int):
                raise sigdump.StimulusError(f"{name!r}: not a signal name")
            parent, last = _get(model, steps[:-1], name), steps[-1]
            target = _get(parent, [last], name)
            log[name] = 0
            new = _held(sigdump._conv(target, value, name), log, name, reads)
            if isinstance(last, int):          # one element of a list: the list ignores writes to this index
                gp, k = _get(model, steps[:-2], name), steps[-2]
                rep = _Held(list(parent), log, name, only={last}, reads=reads)
                list.__setitem__(rep, last, new)
                _set(gp, k, rep)
                undo.append(("item", gp, k, parent, rep))
            else:                              # a whole signal: the object ignores assignments to this attribute
                old_cls = parent.__class__
                names = {**getattr(old_cls, "_piececheck_held", {}), last: name}

                def _sa(self, k, v, _n=names, _base=old_cls):
                    if k in _n:
                        log[_n[k]] += 1
                    else:
                        _base.__setattr__(self, k, v)
                object.__setattr__(parent, last, new)
                parent.__class__ = type(old_cls.__name__, (old_cls,), {"__setattr__": _sa, "_piececheck_held": names})
                undo.append(("attr", parent, last, old_cls, None))
        rec = sigdump.step_once(model, inputs, None, interface)
        got = {r: _ints(rec["outputs"][r]) if (r in rec.get("outputs", {}) and not _has(model, r)) else _ints(_get(model, _path(r), r)) for r in read}   # an output port is read from the outputs of the edge
    finally:
        for kind, obj, k, a, b in reversed(undo):
            if kind == "attr":
                obj.__class__ = a
                object.__setattr__(obj, k, _plain(getattr(obj, k)))
            else:
                for i, v in enumerate(b):
                    list.__setitem__(a, i, _plain(v))
                _set(obj, k, a)
    # reads_of_held: {held signal: times step() read it}; only for a held list (a scalar has no count). 0 = step() did not read the held value
    return {"read": got, "writes_ignored": log, "reads_of_held": {n: reads.get(n, 0) for n in log if isinstance(_get_safe(model, n), list)}, "record": rec}


def _has(model, name):
    try:
        _get(model, _path(name), name)
        return True
    except sigdump.StimulusError:
        return False


def _get_safe(model, name):
    try:
        return _get(model, _path(name), name)
    except sigdump.StimulusError:
        return None


def _flat(x, idx=()):
    if isinstance(x, (list, tuple)):
        for i, y in enumerate(x):
            yield from _flat(y, idx + (i,))
    else:
        yield idx, x


def _want_int(x):
    if isinstance(x, V):
        return x.int_or_none()
    if isinstance(x, str):
        return None if x.strip().lower() == "x" else int(x.replace("_", ""), 0)
    return x


def check(model, hold, read, want, state=None, inputs=None, interface=None):
    r = run(model, hold, read, state, inputs, interface)
    diff, n = [], 0
    for sig, w in want.items():
        g = r["read"].get(sig)
        if g is None and sig not in r["read"]:
            raise sigdump.StimulusError(f"{sig!r}: give it in read= to compare it")
        gf, wf = dict(_flat(g)), dict(_flat(w))
        if set(gf) != set(wf):
            raise sigdump.StimulusError(f"{sig!r}: the model has the shape {_shape(g)}, the wanted value {_shape(w)}")
        for i in gf:
            n += 1
            if gf[i] != _want_int(wf[i]):
                diff.append((sig, i, gf[i], _want_int(wf[i])))
    return {**r, "same": not diff, "diff": diff, "compared": n}


def _shape(x):
    s = []
    while isinstance(x, (list, tuple)):
        s.append(len(x))
        x = x[0] if x else None
    return s


def _hx(v):
    return "x" if v is None else svvec_short_hex(v)


def text(res):
    L = [("same" if res["same"] else f"DIFFERENT in {len(res['diff'])} of {res['compared']} elements")]
    for sig, i, g, w in res["diff"][:32]:
        L.append(f"  {sig}{''.join(f'[{k}]' for k in i)}: design {_hx(g)}, wanted {_hx(w)}")
    if len(res["diff"]) > 32:
        L.append(f"  ... {len(res['diff']) - 32} more")
    for name, n in res["writes_ignored"].items():
        L.append(f"held {name}: {n} writes of step() not applied" + ("  (step() does not write it: the piece may read another signal)" if n == 0 else ""))
    return "\n".join(L)


def pairs(record):
    def st(x):
        if isinstance(x, dict):
            return x.get("op"), x["state"]
        if isinstance(x, tuple) and len(x) >= 2 and isinstance(x[0], str):
            return " ".join(str(y) for y in x[:-1]), x[-1]     # (op, state) or (name, parameter, state)
        return None, x
    r = [st(x) for x in record]
    return [(k, r[k + 1][0], r[k][1], r[k + 1][1]) for k in range(len(r) - 1)]


def place(state, arrangement):
    if isinstance(state, (list, tuple)) and state and isinstance(state[0], (list, tuple)):
        rows = [list(x) for x in state]
        if arrangement == "rows as written":
            return rows
        if arrangement == "rows and columns exchanged":
            return [[rows[i][j] for i in range(len(rows))] for j in range(len(rows[0]))]
    elif isinstance(state, (list, tuple)):
        if arrangement == "as written":
            return list(state)
        if arrangement == "reversed":
            return list(reversed(state))
    raise ValueError(f"arrangement {arrangement!r} does not fit a state of the shape {_shape(state)}")


def take(value, arrangement):
    return place(value, arrangement)   # each of these arrangements is its own inverse


def befores(record, op):
    """The states before each step named `op` of a step record (the first word of the step's name)."""
    return [b for k, o, b, a in pairs(record) if o and str(o).split()[0] == op]


def _ints_all(x):
    if isinstance(x, (list, tuple)):
        return [_ints_all(y) for y in x]
    return _want_int(x)


ARRANGEMENT = "/code/work/arrangement.json"


def arrangement():
    """The arrangement written once in /code/work/arrangement.json (skill check-pieces-against-spec, point 3), or None:
    {"place": "<the arrangement of the data arrays>", "signals": {signal: arrangement, ...}, "basis": "<pieces and lines that decide it>"}."""
    import json
    try:
        return json.load(open(ARRANGEMENT))
    except (OSError, ValueError):
        return None


PLACE_NAMES = ("rows as written", "rows and columns exchanged", "as written", "reversed")


def _file_place(names):
    """The arrangement the file gives for these signals: the entry of one of them under "signals", else "place"; only a name place() knows counts."""
    a = arrangement()
    if not isinstance(a, dict):
        return None
    sig = a.get("signals") if isinstance(a.get("signals"), dict) else {}
    for n in names:
        for k in (n, re.sub(r"(\[[^\]]*\])+$", "", n)):     # an entry for the array also holds for its elements
            if sig.get(k) in PLACE_NAMES:
                return sig[k]
    return a.get("place") if a.get("place") in PLACE_NAMES else None


def against(model, hold, read, ref, inputs, place=None, take=None, name=None, state=None, inputs_ports=None, interface=None, start=None):
    """Compare a piece or a step with a function of the reference model on many inputs (see the text at the top).
    start: a register set to the input before the step (it is not held, so it can also be the signal read after the step: the state before and after one edge).
    place: when not given, the arrangement of /code/work/arrangement.json is used for the signals of the design (not for ports)."""
    import copy, json
    try:
        ports_of = json.load(open(interface if isinstance(interface, str) else "/code/work/interface.json")) if not isinstance(interface, dict) else interface
    except (OSError, ValueError):
        ports_of = {}
    outs = set((ports_of or {}).get("outputs", {}))
    sigs = [h for h in (hold if isinstance(hold, dict) else ([hold] if hold else []))] + ([start] if start else []) + ([] if read in outs else [read])
    filed = _file_place(sigs) if sigs else None
    defaulted = place is None and filed is not None
    if defaulted:
        place = filed
    arrays, fitted = [], []     # the arrays of the design this comparison places or takes, and whether the arrangement of the file fits their shape

    def fits(v, p):        # an arrangement applies to the values of its shape; another value (a word, a whole key, a port) is passed as it is
        try:
            globals()["place"](v, p)
            return True
        except (ValueError, TypeError, IndexError):
            return False
    if isinstance(place, str):
        put = lambda v: globals()["place"](v, place) if fits(v, place) else v
    else:
        put = place or (lambda v: v)
    same_as_file = [] if (filed is not None and not isinstance(place, str) and place is not None) else None
    back = take if callable(take) else ((lambda v: globals()["take"](v, take)) if isinstance(take, str)
                                       else ((lambda v: globals()["take"](v, place) if fits(v, place) else v) if isinstance(place, str) and read not in outs else (lambda v: v)))
    differ, n, unread, pin, sset = [], 0, set(), set(), set()
    for k, x in enumerate(inputs):
        want = _ints_all(ref(copy.deepcopy(x)))
        raw = {h: f(copy.deepcopy(x)) for h, f in hold.items()} if isinstance(hold, dict) else ({hold: copy.deepcopy(x)} if hold else {})
        if start:
            raw[start] = copy.deepcopy(x)
        for v in raw.values():
            if isinstance(v, (list, tuple)):
                arrays.append(1); fitted.append(filed is not None and fits(v, filed))
        if same_as_file is not None:       # a function of the order: is it the arrangement of the file on these values?
            for v in raw.values():
                if fits(v, filed) and isinstance(put(copy.deepcopy(v)), (list, tuple)):   # a function that packs the value into another form is not judged here
                    same_as_file.append(_ints_all(put(copy.deepcopy(v))) == _ints_all(globals()["place"](copy.deepcopy(v), filed)))
        held = {h: put(v) for h, v in raw.items() if h != start}
        st = dict(state(copy.deepcopy(x)) if callable(state) else (state or {}))    # state may depend on the input: a function(input) -> {register: value}
        if callable(state):
            sset |= set(st)                # registers set from the input, as start= does (f7-16)
        if start:
            st[start] = put(raw[start])
        ports = inputs_ports(copy.deepcopy(x)) if callable(inputs_ports) else inputs_ports   # ports may depend on the input: a function(input) -> {port: value}
        pin |= set(ports or {})
        r = run(copy.deepcopy(model), held, [read], st, ports, interface)
        got = back(r["read"][read])
        if read not in outs and isinstance(r["read"][read], (list, tuple)):
            arrays.append(1); fitted.append(filed is not None and fits(r["read"][read], filed))
        if same_as_file is not None and read not in outs and fits(r["read"][read], filed):
            same_as_file.append(_ints_all(got) == _ints_all(globals()["take"](copy.deepcopy(r["read"][read]), filed)))
        unread |= {h for h, c in r.get("reads_of_held", {}).items() if c == 0}
        n += 1
        if dict(_flat(got)) != dict(_flat(want)):
            differ.append((k, x, got, want))
    missing = arrangement() is not None and bool(arrays) and not any(fitted)    # the file is there and gives nothing for the arrays of this comparison
    if missing:
        filed, place = None, (None if defaulted else place)
    judged = bool(same_as_file)
    used = place if isinstance(place, str) or place is None else (filed if judged and all(same_as_file) else "a function of the order")
    res = {"name": name or getattr(ref, "__name__", "step"), "hold": ", ".join(hold) if isinstance(hold, dict) else (hold or ""), "read": read,
           "compared": n, "differ": differ, "same": not differ, "held_not_read": sorted(unread),
           "start": start or "", "state_from_input": sorted(sset), "ports_in": sorted(pin), "read_is_output": read in outs,
           "place": used, "arrangement": filed, "place_differs": filed is not None and ((isinstance(place, str) and place != filed) or (judged and not all(same_as_file))), "arrangement_missing": missing}
    _log(model, res)
    return res


LOG = "/code/work/against_log.jsonl"


def _log(model, res):
    """Every comparison is appended to /code/work/against_log.jsonl (when /code/work exists): what was compared, the switches on, the result."""
    import json
    if not os.path.isdir(os.path.dirname(LOG)):
        return
    names = list(getattr(type(model), "SWITCHES", {}) or {})
    fix = getattr(model, "fix", ())
    on = [x for x in (fix if isinstance(fix, (list, tuple, set)) else [fix]) if x]
    if "all" in on:            # fix="all", or a model that keeps it as ["all"] (f7-12)
        on = names
    first = res["differ"][0] if res["differ"] else None
    row = {"name": res["name"], "hold": res["hold"], "read": res["read"], "switches_on": sorted(map(str, on)), "switches_of_model": names,
           "all_on": bool(names) and set(names) <= set(map(str, on)), "compared": res["compared"], "differ": len(res["differ"]),
           "first": None if first is None else {"input": _short(first[1]), "design": _short(first[2]), "wanted": _short(first[3])},
           "held_not_read": res.get("held_not_read", []),
           **{k: res.get(k) for k in ("start", "state_from_input", "ports_in", "read_is_output", "place", "arrangement", "place_differs", "arrangement_missing")}}
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass


def _short(v):
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_short(y) for y in v) + "]"
    return _hx(v) if (v is None or isinstance(v, int)) else str(v)


def text_against(res):
    L = [f"| {res['name']} | {res['hold']} | {res['read']} | "
         + ("agree" if res["same"] else f"differ on {len(res['differ'])} of {res['compared']} inputs") + f" ({res['compared']} inputs) |"]
    if res["differ"]:
        k, x, g, w = res["differ"][0]
        L.append(f"  first: input {k} = {_short(x)}\n    design {_short(g)}\n    wanted {_short(w)}")
    if res.get("place_differs"):
        L.append(f"  the arrangement used ({res['place']}) is not the one of /code/work/arrangement.json ({res['arrangement']})")
    if res.get("arrangement_missing"):
        L.append(f"  /code/work/arrangement.json gives no arrangement for the arrays of this comparison (no entry under \"signals\", and its \"place\" does not fit their shape)")
    if res.get("held_not_read"):
        L.append(f"  step() did not read the held signal(s) {', '.join(res['held_not_read'])}: the model computes {res['read']} without them, so this row does not compare that piece")
    return "\n".join(L)
