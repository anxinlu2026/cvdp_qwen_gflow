r"""ledger: the book of the switches of the model. One entry per switch that was kept or tried and dropped, written when it is decided, not at the end of the order.
The book is /code/work/ledger.json; it is written only by this library (a line added by hand is not checked and is lost at the next write).

usage:
  python3 /code/lib/ledger.py add SWITCH --file unit.sv --lines 103-106 --fact "TEXT" [--edits FILE] [--state kept|dropped] [--review "TEXT"]
  python3 /code/lib/ledger.py show [--file unit.sv]
  python3 /code/lib/ledger.py apply [--show NAME|all]

  SWITCH   the name of the switch in SWITCHES of the model
  --file   the RTL file the switch changes; --lines its lines in the original file: "71", "103-106", or several parts "64-65,68"
           (a switch that changes two files has two add calls, one per file). For something the RTL does not have (a new register,
           a new port): the lines of the statements that are changed to use it, and the line next to which it is declared
  --fact   what the decision stands on: the tool, its command and the line it printed (the count before and after), in one sentence
  --state  kept (default): the switch stays in the model.  dropped: it was tried and taken out again; --fact then says why
  --edits  a JSON file with the RTL change of the switch: [{"file": "unit.sv", "old": "text as it is in the file", "new": "text that replaces it"}, ...]
           (the form of the edits is the one of /code/lib/rtlapply.py: read the text at its top). The library keeps the edits with the entry, writes
           /code/work/rtl_changes.json from the kept entries (in the order in which the switches were first entered) and /code/work/rtl_fixed/ from it,
           and prints for every edit of this entry whether it was applied. An entry whose own edits are not applied is NOT written.
           To change the edits of a switch, enter the switch again with the new file (the earlier entry is marked replaced; the switch keeps its place in the order;
           no --review is asked for the switch's own earlier entry). One edit may hold several statements that stand together; --lines names the lines of the
           original file that the edits change (lines between them may be included).
           `apply` writes rtl_changes.json and rtl_fixed/ again and prints the whole result.
  --review see below

Before an entry is written, the library compares its lines with the entries already in the book:
- no entry of the book has a line of the same file in common with it: the entry is written.
- an entry has lines in common (another switch at the same place, the same switch once more, or a place that was tried and dropped):
  the entry is NOT written. The library prints the entries concerned and the RTL lines they share. Read them and decide which is right:
  two switches may change the same line for two different faults, or one of the two is the other said again, or the earlier one was wrong.
  Then run the same command again with --review "what you found and what holds now". With --review the entry is written and the text is kept with it.
  --review is taken only after the library has printed the entries concerned for this same add call; given at the first call, they are printed and nothing is written.
  The switches of the model that earlier orders kept and that are not in the book are compared in the same way, where SWITCHES of the model names their file and lines.
  An entry of the same switch for the same file replaces the earlier one (the earlier one stays in the book, marked replaced).
  An earlier entry of another switch that no longer holds is closed by an add call for that switch with --state dropped.

A kept switch is entered after it is in SWITCHES of the model (the library prints when the name is not there).
It prints the RTL lines the entry names and as the last line "written: entry N" or "NOT WRITTEN: ...".
show prints the book: per file, in the order of the lines, the entries that hold, then the dropped and replaced ones.
In Python: `import ledger; r = ledger.add(book, rtl_dir, switch, file, lines, fact, state="kept", review=None)` -> {"written", "lines", "overlap"}.
"""
import argparse, ast, json, os, sys, time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BOOK, RTL, MODEL = "/code/work/ledger.json", "/code/rtl", "/code/work/rtl_model.py"


def parse_lines(text):
    """ "64-65,68" -> sorted list of line numbers; None when it cannot be read."""
    out = set()
    try:
        for part in str(text).replace(" ", "").split(","):
            if not part:
                continue
            a, _, b = part.partition("-")
            a, b = int(a), int(b or a)
            if a < 1 or b < a:
                return None
            out.update(range(a, b + 1))
    except ValueError:
        return None
    return sorted(out) or None


def show_lines(nums):
    """[64,65,68] -> "64-65,68" """
    parts, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        parts.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return ",".join(parts)


def load(book):
    p = Path(book)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())["entries"]
    except Exception as e:
        raise ValueError(f"{book} cannot be read: {e}")


def model_switches(model):
    try:
        tree = ast.parse(Path(model).read_text())
    except Exception:
        return None
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SWITCHES" for t in node.targets) and isinstance(node.value, (ast.Dict, ast.Set, ast.List, ast.Tuple)):
            for k in (node.value.keys if isinstance(node.value, ast.Dict) else node.value.elts):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) and k.value not in names:
                    names.append(k.value)
    return names


def model_places(model):
    """Switches of the model whose value in SWITCHES starts with a file name and a text of lines: {name: (file, [lines])}."""
    try:
        tree = ast.parse(Path(model).read_text())
    except Exception:
        return {}
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SWITCHES" for t in node.targets) and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and isinstance(v, (ast.Tuple, ast.List)) and len(v.elts) >= 2 and all(isinstance(x, ast.Constant) for x in v.elts[:2]):
                    nums = parse_lines(str(v.elts[1].value).replace("lines", "").replace("line", ""))
                    if isinstance(v.elts[0].value, str) and nums:
                        out[k.value] = (v.elts[0].value, nums)
    return out


def changes_of(entries):
    """The list of changes of the book: one item per switch that has edits in an entry that holds, in the order in which the switches were first entered."""
    first, edits = {}, {}
    for e in entries:
        first.setdefault(e["switch"], e["n"])
        if e["state"] == "kept" and e.get("edits"):
            edits.setdefault(e["switch"], []).extend(e["edits"])
    return [{"switch": s, "edits": edits[s]} for s in sorted(edits, key=lambda s: first[s])]


def write_rtl(entries, book, rtl_dir, show=None):
    """rtl_changes.json and rtl_fixed/ beside the book, from the entries; returns the result of rtlapply."""
    import rtlapply
    ch = changes_of(entries)
    work = Path(book).parent
    (work / "rtl_changes.json").write_text(json.dumps({"changes": ch}, indent=1) + "\n")
    return rtlapply.apply(ch, rtl_dir, work / "rtl_fixed", show=show)


def load_edits(path):
    try:
        d = json.loads(Path(path).read_text())
    except Exception as e:
        raise ValueError(f"NOT WRITTEN: {path} cannot be read as JSON: {e}")
    d = d.get("edits") if isinstance(d, dict) else d
    if not isinstance(d, list) or not d or not all(isinstance(x, dict) and all(isinstance(x.get(k), str) for k in ("file", "old", "new")) for x in d):
        raise ValueError(f'NOT WRITTEN: {path} must be a list of edits, each with "file", "old" and "new" as texts')
    return [{k: x[k] for k in ("file", "old", "new")} for x in d]


def _row(e):
    if e.get("n") is None:
        return f'{e["switch"]}  {e["file"]} lines {show_lines(e["lines"])}  a switch of the model from an earlier order, not in the book'

    return f'entry {e["n"]}: {e["switch"]}  {e["file"]} lines {show_lines(e["lines"])}  {e["state"]}  fact: {e["fact"]}' + (f'  edits: {len(e["edits"])}' if e.get("edits") else "") + (f'  review: {e["review"]}' if e.get("review") else "")


def add(book, rtl_dir, switch, file, lines, fact, state="kept", review=None, model=None, edits=None, need_edits=False):
    out = []
    def no(why):
        out.append(f"NOT WRITTEN: {why}")
        return {"written": None, "lines": out, "overlap": []}
    entries = load(book)
    f = Path(rtl_dir) / file
    if not f.is_file():
        return no(f"there is no file {file} in {rtl_dir} (files: {', '.join(sorted(x.name for x in Path(rtl_dir).iterdir() if x.is_file()))})")
    src = f.read_text().splitlines()
    nums = parse_lines(lines)
    if nums is None:
        return no(f'--lines "{lines}" cannot be read; write "71", "103-106" or "64-65,68"')
    if nums[-1] > len(src):
        return no(f"{file} has {len(src)} lines; --lines names line {nums[-1]}")
    if state not in ("kept", "dropped"):
        return no('--state is "kept" or "dropped"')
    if not (fact or "").strip():
        return no("--fact is empty; it names the tool run and the printed line the decision stands on")
    out.append(f"{file} lines {show_lines(nums)}:")
    out += [f"  {n:4d}: {src[n - 1][:200]}" for n in nums]
    fact, review = fact.replace('\\"', '"'), (review or "").replace('\\"', '"')
    live = [e for e in entries if e["state"] in ("kept", "dropped") and e["file"] == file]
    if model:
        sw = model_switches(model)
        if sw is not None and state == "kept" and switch not in sw:
            out.append(f"the name {switch} is NOT in SWITCHES of the model (names there: {', '.join(sw)})")
        booked = {e["switch"] for e in entries}
        live += [{"n": None, "switch": s, "file": f2, "lines": l2, "state": "kept", "fact": ""} for s, (f2, l2) in model_places(model).items() if s not in booked and s != switch and f2 == file]
    over = [e for e in live if set(e["lines"]) & set(nums)]
    same = [e for e in live if e["switch"] == switch and e not in over]
    key = [switch, file, nums, state]
    pend = Path(str(book) + ".asked")
    asked = pend.exists() and json.loads(pend.read_text()) == key
    gate = [e for e in over + same if not (edits and state == "kept" and e["switch"] == switch)]   # the same switch entered again with edits replaces its entry: no review
    if gate and not (review.strip() and asked):
        if over:
            out.append("entries of the book with lines in common with this one:")
            for e in over:
                out.append("  " + _row(e))
                out.append(f'    lines in common: {show_lines(sorted(set(e["lines"]) & set(nums)))}' + ("  (the same switch)" if e["switch"] == switch else "  (tried and dropped before)" if e["state"] == "dropped" else "  (another switch that is kept)"))
        if same:
            out.append("entries of the book for the same switch and file at other lines (this entry would replace them):")
            out += ["  " + _row(e) for e in same]
        pend.write_text(json.dumps(key))
        out.append('NOT WRITTEN: read the entries above and the RTL lines, decide what holds, and run the same command again with --review "what you found and what holds now"'
                   + (" (the review given with this call was not taken: it comes after this print)" if review.strip() else ""))
        return {"written": None, "lines": out, "overlap": [e["n"] for e in over + same]}
    if pend.exists():
        pend.unlink()
    n = max([e["n"] for e in entries], default=0) + 1
    if state == "kept" and need_edits and not edits and not any(e["switch"] == switch and e["state"] == "kept" and e.get("edits") and e["file"] != file for e in entries):
        out.append("NOT WRITTEN: a kept switch is entered with its RTL change: write the edits of this switch in a JSON file and give it with --edits FILE (see the text at the top of this library and of /code/lib/rtlapply.py)")
        return {"written": None, "lines": out, "overlap": []}
    if edits and state == "kept":       # the entry is written only when its own edits are applied
        import copy
        trial = copy.deepcopy(entries)
        for e in trial:
            if e["switch"] == switch and e["file"] == file and e["state"] == "kept":
                e["state"] = "replaced"
        trial.append({"n": n, "switch": switch, "file": file, "lines": nums, "state": "kept", "fact": fact, "edits": edits})
        import rtlapply
        r = rtlapply.apply(changes_of(trial), rtl_dir, None, show=switch)
        mine = [l for l in r["lines"] if l.startswith(switch + " edit ") or l.startswith("== changed lines of the entry " + switch) or l.startswith("  ")]
        out += mine
        if any(l.startswith(switch + " edit ") and "NOT APPLIED" in l for l in r["lines"]):
            out.append("NOT WRITTEN: an edit of this entry is not applied; correct the file of the edits and run the same command again")
            return {"written": None, "lines": out, "overlap": []}
    for e in over + same:
        if e["switch"] == switch:
            e["state"] = "replaced"
    if edits:
        for e in entries:
            if e["switch"] == switch and e["file"] == file and e["state"] == "kept" and e.get("n") is not None:
                e["state"] = "replaced"
    over, same = [e for e in over if e["n"] is not None], same
    against = [e["switch"] if e.get("n") is None else e["n"] for e in live if set(e["lines"]) & set(nums)]
    new = {"n": n, "switch": switch, "file": file, "lines": nums, "state": state, "fact": fact.strip(), "time": time.strftime("%H:%M:%S")}
    if (review or "").strip():
        new["review"] = review.strip()
        new["reviewed_against"] = against
    if edits and state == "kept":
        new["edits"] = edits
    entries.append(new)
    Path(book).write_text(json.dumps({"entries": entries}, indent=1) + "\n")
    if any(e.get("edits") for e in entries):
        r = write_rtl(entries, book, rtl_dir)
        bad = [l for l in r["lines"] if "NOT APPLIED" in l]
        if bad:
            out.append("edits of other entries that are not applied now (enter these switches again with edits that fit the file as it is at their place):")
            out += ["  " + l for l in bad]
        out.append(f'the list of changes of the book: {len(changes_of(entries))} switches, edits applied: {r["applied"]}, not applied: {r["failed"]}; written: rtl_changes.json and rtl_fixed/')
        if model:
            import rtlapply
            miss = [l for l in rtlapply.compare_names(r["names"], model) if not l.startswith("every switch")]
            out += miss
    out.append(f"written: entry {n}" + (f' (replaces entry {", ".join(str(e["n"]) for e in over + same if e["switch"] == switch)})' if any(e["switch"] == switch for e in over + same) else ""))
    return {"written": n, "lines": out, "overlap": [e["n"] for e in over + same]}


def show(book, file=None):
    entries = [e for e in load(book) if not file or e["file"] == file]
    if not entries:
        return ["the book has no entry" + (f" for {file}" if file else "")]
    out = []
    kept = sorted([e for e in entries if e["state"] == "kept"], key=lambda e: (e["file"], e["lines"][0]))
    out.append(f"entries that hold ({len(kept)}), per file in the order of the lines:")
    out += ["  " + _row(e) for e in kept]
    for st, head in (("dropped", "tried and dropped"), ("replaced", "replaced by a later entry of the same switch")):
        rest = [e for e in entries if e["state"] == st]
        if rest:
            out.append(f"{head} ({len(rest)}):")
            out += ["  " + _row(e) for e in rest]
    shared = []
    for i, a in enumerate(kept):
        for b in kept[i + 1:]:
            if a["file"] == b["file"] and set(a["lines"]) & set(b["lines"]):
                shared.append(f'  {a["switch"]} and {b["switch"]}: {a["file"]} lines {show_lines(sorted(set(a["lines"]) & set(b["lines"])))}')
    if shared:
        out.append("kept switches with lines in common (each was written after a review):")
        out += shared
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("cmd", choices=("add", "show", "apply")); ap.add_argument("switch", nargs="?")
    ap.add_argument("--file"); ap.add_argument("--lines"); ap.add_argument("--fact"); ap.add_argument("--state", default="kept"); ap.add_argument("--review"); ap.add_argument("--edits"); ap.add_argument("--show")
    ap.add_argument("--book", default=BOOK); ap.add_argument("--rtl", default=RTL); ap.add_argument("--model", default=MODEL)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "show":
            print("\n".join(show(a.book, a.file))); return 0
        if a.cmd == "apply":
            import rtlapply
            r = write_rtl(load(a.book), a.book, a.rtl, a.show)
            print("\n".join(r["lines"]))
            if Path(a.model).exists():
                print("\n".join(rtlapply.compare_names(r["names"], a.model)))
            print(f'all edits applied: {r["applied"]}' if r["ok"] else f'edits not applied: {r["failed"]} (applied: {r["applied"]})')
            return 0 if r["ok"] else 1
        if not (a.switch and a.file and a.lines):
            print("NOT WRITTEN: add needs SWITCH, --file, --lines and --fact"); return 2
        need = (Path(__file__).resolve().parent / "ledger.edits").exists()
        r = add(a.book, a.rtl, a.switch, a.file, a.lines, a.fact or "", a.state, a.review, a.model if Path(a.model).exists() else None, load_edits(a.edits) if a.edits else None, need)
    except ValueError as e:
        print(e); return 2
    print("\n".join(r["lines"]))
    return 0 if r["written"] else 1


if __name__ == "__main__":
    sys.exit(main())
