r"""tasks: gives the differences of the design one at a time. It runs stepfacts (and, when stepfacts has no difference left, hsfacts) with all switches of the model,
and gives the first difference as the task. A task is closed when its difference is gone and the switch that removed it is in the book of the switches (ledger.py).

usage:
  python3 /code/lib/tasks.py next                   the task to work on now: the open one, or the next one when the open one is closed; "none" when no difference is left
  python3 /code/lib/tasks.py giveup "REASON"        the open task cannot be closed: what was tried and what the prints showed; it is set aside and the next one is given
  python3 /code/lib/tasks.py show                   the tasks given so far and how each ended
  options: --description /code/work/handshake.json  --model /code/work/rtl_model.py
Which differences an order gets is set with the order (the data path, part 1 of stepfacts; or part 2 and the handshake; or, for a unit without a step record,
the output ports edge by edge from portfacts: one task per port, the first case in which it differs); the commands are the same in all.

next, when a task is open, measures again:
- the difference of the task is still there: the task stays open. It prints the task once more, the minutes since it was given, the stepfacts and hsfacts runs recorded since,
  the switches added to the model since, and differences that were not there when the task was given.
- the difference is gone, but a switch added to the model since the task was given has no entry "kept" in the book: the task stays open; enter the switch (or take it out of the model and enter it as dropped), then ask again.
- the difference is gone and the book is complete: the task is closed. It prints what closed it: the switches, the number of RTL lines of their entries, the number of places of the model that ask for them,
  and the other differences that went with it. Then it gives the next task.
One task is one difference; the full print of stepfacts or hsfacts is still the place to see that a candidate loses nothing that was right before.
A task names one difference: the print line of the tool, the case, operation and edge where it shows first, and the command that prints this case in full.
Tasks are given in the order of the tools: the data path (the first step of part 1 from which no control value goes on), then part 2 in the order of the cases, then the handshake lines that are not a count.
"none" lists the tasks that were set aside and the handshake lines that are only a count; they belong in the report.
next and giveup first run basecheck (when the order has the record /code/lib/base_record.json): RtlModel() with no switch against what a simulator recorded for the RTL as written.
While the two differ no task is closed or given; the print says the first edge that differs.
The state is /code/work/tasks.json (written by this library only).
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import basecheck, hsfacts, ledger, stepfacts
LAST_BASE = None   # the result of basecheck at the last call (printed as its first line, so that a pass is seen too)


def _measure(desc, model, part):
    """The differences now, in the order in which they are given: [{"key", "line", "where", "cmd"}], and the handshake lines that are only a count."""
    items, counts = [], []
    if part == 3:                         # an order whose unit has no step record: every output port, edge by edge, against the timed specification model
        import portfacts
        h = portfacts.measure(desc, "all", model)
        seen = set()
        for name, n, k in h["different"]:
            if k not in seen:
                seen.add(k)
                items.append({"key": f"port|{k}|{name}|{n}", "line": f"PORTS (portfacts): {k} is not what the specification model gives", "where": f"first in case {name}, at edge {n}",
                              "cmd": f"python3 /code/lib/portfacts.py {desc} --fix all --case {name} --edges"})
        for name, e in dict.fromkeys(h.get("spec_errors") or []):
            counts.append(f"NOT COMPARED because of the specification model: {name}: {e}")
        return items, counts
    r = stepfacts.measure(desc, "all", model)
    p = r["part1"]
    if part in (None, 1):
        if p["dead"]:
            k = p["dead"][0]
            items.append({"key": f"part1|{k}", "line": f"DATA PATH (part 1): from step {k} of the record no control value goes on",
                          "where": f"step {k}", "cmd": f"python3 /code/lib/stepfacts.py {desc} --fix all --step {k}"})
        elif not p["final"]:
            items.append({"key": "part1|final", "line": "DATA PATH (part 1): the final step of the record is not reached", "where": "part 1", "cmd": f"python3 /code/lib/stepfacts.py {desc} --fix all"})
    if part in (None, 2):
        seen = set()
        for name, n, i, block, why in r["different"]:
            if (block, why) not in seen:
                seen.add((block, why))
                items.append({"key": f"part2|{block}|{why}", "line": f"{block} (part 2): {why}", "where": f"first in case {name}, operation {n}, edge {i}",
                              "cmd": f"python3 /code/lib/stepfacts.py {desc} --fix all --case {name} --all"})
        if not items:
            h = hsfacts.measure(desc, "all", model)
            seen = set()
            for name, n, k in h["different"]:
                if k in hsfacts.COUNT:
                    counts.append(f"{name} operation {n}: {k}")
                elif k not in seen:
                    seen.add(k)
                    items.append({"key": f"hs|{k}", "line": f"HANDSHAKE (hsfacts): {k}", "where": f"first in case {name}, operation {n}",
                                  "cmd": f"python3 /code/lib/hsfacts.py {desc} --fix all --case {name} --edges"})
            for name, e in dict.fromkeys(h.get("spec_errors") or []):
                counts.append(f"NOT COMPARED because of the specification model: {name}: {e}")
    return items, counts


def _runs(desc):
    try:
        return sum(1 for l in open(os.path.join(os.path.dirname(os.path.abspath(desc)), "tool_runs.log")) if l.startswith("--- ") and (" stepfacts " in l or " hsfacts " in l or " portfacts " in l))
    except OSError:
        return 0


def _load(state):
    try:
        return json.load(open(state))
    except (OSError, ValueError):
        return {"open": None, "done": []}


def _task_text(t, left):
    return [f"task {t['n']}: {t['line']}", f"  {t['where']}", f"  in full: {t['cmd']}"] + ([f"  differences listed now, this one included: {left}"] if not t["key"].startswith("part1|") else ["  (the data path is given step by step: the first step that does not go on; later steps show when this one goes on)"])


def run(cmd, reason, desc, model, part, state, book):
    st = _load(state)
    L = []
    if cmd == "show":
        for t in st["done"]:
            L.append(f"task {t['n']}: {t['line']}   -> {t['end']}" + (f" ({t['by']})" if t.get("by") else "") + (f": {t['reason']}" if t.get("reason") else ""))
        if st["open"]:
            L.append(f"task {st['open']['n']}: {st['open']['line']}   -> open")
        return L or ["no task was given yet"]
    b = basecheck.measure(model)
    global LAST_BASE
    LAST_BASE = b
    keep = state + ".base.py"            # the model file as it was at the last call at which the comparison had no difference
    if b is not None and b["ok"]:
        open(keep, "w").write(open(model).read())
    if b is not None and not b["ok"]:
        sc, e, n, rv, mv = b["first"]
        L = ["no task is closed or given now: RtlModel() with no switch does not give the outputs that a simulator recorded for the RTL as written (/code/lib/base_record.json).",
             f"  first: scenario {sc}, edge {e}, output {n}: simulator (RTL as written) = {rv}   RtlModel() = {mv}; edges with a difference: {b['differences']}",
             "  the record is what the RTL as written does, right or wrong, not what the design should do; no switch takes part in this comparison.",
             "  in full: python3 /code/lib/basecheck.py   (and --scenario N --edges A-B for the values edge by edge)"]
        if os.path.exists(keep):
            import difflib
            new = open(model).read().splitlines()
            rng = [f"{j1 + 1}-{j2}" if j2 > j1 + 1 else str(j1 + 1) if j2 > j1 else f"after {j1} (lines removed)"
                   for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, open(keep).read().splitlines(), new, autojunk=False).get_opcodes() if tag != "equal"]
            L.append(f"  the two were the same at an earlier call of this order; lines of {model} changed since then ({len(rng)} place(s)): " + ", ".join(rng[:12]) + (" ..." if len(rng) > 12 else "") + f"   (the file as it was then: {keep})")
        else:
            L.append("  the two were the same when this order began.")
        L.append("  ask again when the two are the same once more; the differences are then measured again on that model.")
        return L
    cell = part
    if st["open"] and part == 1 and not st["open"]["key"].startswith("part1|"):   # an open task is judged in the part it was given in
        part = None
    items, counts = _measure(desc, model, part)
    aside = {t["key"] for t in st["done"] if t["end"] == "set aside"}
    now = ledger.model_switches(model) or []
    booked = {}
    for e in ledger.load(book):
        booked.setdefault(e["switch"], []).append(e)
    t = st["open"]
    if t:
        added = [s for s in now if s not in t["switches"]]
        fresh = [i for i in items if i["key"] not in t["keys"] and i["key"] != t["key"]]
        mins = round((time.time() - t["time"]) / 60)
        there = any(i["key"] == t["key"] for i in items)
        if cmd == "giveup":
            if not (reason or "").strip():
                return ['giveup needs the reason: python3 /code/lib/tasks.py giveup "what was tried and what the prints showed"']
            st["done"].append({"n": t["n"], "key": t["key"], "line": t["line"], "end": "set aside", "reason": reason.strip(), "minutes": mins})
            aside.add(t["key"])
            L.append(f"task {t['n']} is set aside (minutes since it was given: {mins})" + (f"; switches added since it was given and still in the model: {', '.join(added)}" if added else ""))
            st["open"] = t = None
        elif there:
            L.append(f"task {t['n']} is open: its difference is still there.")
            L += _task_text(t, len([i for i in items if i["key"] not in aside]))
            L.append(f"  minutes since it was given: {mins}; stepfacts and hsfacts runs since: {_runs(desc) - t['runs']}; switches added to the model since: {', '.join(added) or 'none'}")
            if fresh:
                L.append("  differences that were not there when the task was given:")
                L += [f"    {i['line']}   ({i['where']})" for i in fresh]
            L.append('  when it cannot be closed: python3 /code/lib/tasks.py giveup "what was tried and what the prints showed"')
            json.dump(st, open(state, "w"), indent=1)
            return L
        else:
            nobook = [s for s in added if not any(e["state"] == "kept" for e in booked.get(s, []))]
            if nobook:
                L.append(f"task {t['n']}: its difference is gone, but the task is not closed: added to the model since it was given and without an entry \"kept\" in the book of the switches: {', '.join(nobook)}.")
                L.append("  enter each with /code/lib/ledger.py (or take it out of the model and enter it as dropped), then ask again.")
                json.dump(st, open(state, "w"), indent=1)
                return L
            newent = [e for es in booked.values() for e in es if e["n"] > t.get("book", 0) and e["state"] == "kept"]
            if not added and not newent:
                L.append(f"task {t['n']}: its difference is gone and no switch was added to the model, but the task is not closed: the book of the switches has no new entry \"kept\" since the task was given.")
                L.append("  a switch that was corrected in its place is entered again with /code/lib/ledger.py (its entry then says what it is now), then ask again.")
                json.dump(st, open(state, "w"), indent=1)
                return L
            changed = sorted({e["switch"] for e in newent if e["switch"] not in added})
            gone = [k for k in t["keys"] if k not in {i["key"] for i in items} and k != t["key"]]
            src = open(model).read()
            size = []
            for s in added:
                ent = [e for e in booked.get(s, []) if e["state"] == "kept"]
                size.append(f"{s}: RTL lines in its book entr{'y' if len(ent) == 1 else 'ies'}: {sum(len(e['lines']) for e in ent)}; places of the model that ask for it: {src.count(chr(34) + s + chr(34)) - 1}")
            L.append(f"task {t['n']} is closed (minutes since it was given: {mins}): its difference is gone. " + ("Closed by: " + "; ".join(size) + "." if size else "No switch was added to the model since it was given.") + (f" Entered again in the book since it was given: {', '.join(changed)}." if changed else ""))
            if gone:
                L.append(f"  other differences that were there when it was given and are gone now ({len(gone)}): " + "; ".join(k.split("|", 1)[1].replace("|", ": ") for k in gone))
            if fresh:
                L.append("  listed now and not listed when it was given (a step or an edge after a difference is not judged until the difference before it is gone): " + "; ".join(f"{i['line']} ({i['where']})" for i in fresh))
            st["done"].append({"n": t["n"], "key": t["key"], "line": t["line"], "end": "closed", "by": ", ".join(added + changed), "minutes": mins})
            st["open"] = t = None
    elif cmd == "giveup":
        return ["no task is open; python3 /code/lib/tasks.py next"]
    left = [i for i in items if i["key"] not in aside and (cell is None or (cell == 1) == i["key"].startswith("part1|"))]
    if left:
        i = left[0]
        st["open"] = dict(i, n=len(st["done"]) + 1, time=time.time(), runs=_runs(desc), switches=now, keys=[x["key"] for x in items], book=max([e["n"] for e in ledger.load(book)], default=0))
        L += _task_text(st["open"], len(left))
    else:
        L.append("none: no difference is left to give.")
        for d in st["done"]:
            if d["end"] == "set aside":
                L.append(f"  set aside, still to be said in the report: task {d['n']}: {d['line']}: {d['reason']}")
        if counts:
            L.append(f"  handshake lines that differ only in a count ({len(counts)}; a difference only when the task text or its documents give the number): " + "; ".join(counts))
    json.dump(st, open(state, "w"), indent=1)
    return L


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("cmd", choices=("next", "giveup", "show")); ap.add_argument("reason", nargs="?")
    ap.add_argument("--description", default="/code/work/handshake.json"); ap.add_argument("--model", default="/code/work/rtl_model.py"); ap.add_argument("--part", type=int, choices=(1, 2, 3))
    ap.add_argument("--state", default="/code/work/tasks.json"); ap.add_argument("--book", default=ledger.BOOK)
    a = ap.parse_args(argv)
    if a.part is None:                   # the order's part: a file beside this library, put there with the order
        try:
            a.part = int(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.part")).read().strip()) or None
        except (OSError, ValueError):
            pass
    try:
        L = run(a.cmd, a.reason, a.description, a.model, a.part, a.state, a.book)
    except (stepfacts.DescriptionError, stepfacts.sigdump.StimulusError) as ex:
        print("tasks: stepfacts could not measure: " + str(ex)); return 2
    except (OSError, KeyError, ValueError, SyntaxError, AttributeError, TypeError, NameError) as ex:
        print(f"tasks: the description, the record file or the model could not be used ({type(ex).__name__}: {ex}); run stepfacts itself to see the message"); return 2
    if LAST_BASE is not None and LAST_BASE["ok"]:
        L = ["basecheck: RtlModel() with no switch gives what the simulator recorded for the RTL as written (no difference)."] + L
    print("\n".join(L))
    hsfacts.log(a.description, "tasks", [a.cmd], L[:6])
    return 0


if __name__ == "__main__":
    sys.exit(main())
