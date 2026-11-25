r"""rtlapply: write the RTL of a list of changes. It copies the original source files and replaces text in the copy; it edits nothing by hand and runs no simulator.

The list of changes is a JSON file, one entry per switch of the model, in the order in which the switches were kept:

  {"changes": [
     {"switch": "name_of_the_switch",
      "edits": [{"file": "unit.sv", "old": "text as it is in the file", "new": "text that replaces it"},
                {"file": "lower.sv", "old": "...", "new": "..."}]},
     ...
  ]}

- "old" is text of the file as it is when this edit is applied: the original file with the edits of the entries before it (and of the edits before it in the same entry).
  It must occur exactly once in the file; take as many characters (also several lines, with their line ends and leading blanks) as are needed for that.
- "new" replaces it. To add lines, take a line next to the place as "old" and give it again in "new" together with the added lines (this is not a rewrite of that line). To remove text, "new" is "".
- in the JSON text a line end is written \n and a tab \t; to remove whole lines, "old" holds the lines with their line ends.
- an entry may have several edits and edits in several files (a new port: the declaration and the assignment in the lower file, the connection in the upper file).
- every switch of the model has one entry; an entry is the whole RTL change of its switch, nothing of another switch.

usage: python3 /code/lib/rtlapply.py CHANGES.json [--rtl /code/rtl] [--out /code/work/rtl_fixed] [--upto NAME] [--show NAME|all] [--model /code/work/rtl_model.py]
  --upto NAME  apply the entries up to and with the switch NAME only
  --show NAME  print the changed lines of the entry NAME (default: of the last entry applied); --show all: of every entry
  --model      compare the names of the entries with the names in SWITCHES of the model (default /code/work/rtl_model.py when it exists)
It prints one line per edit (applied, or why not; "at line N" is the line in the file as it is at this edit) and the changed lines of one entry
(the file before this entry against the file after it; line numbers of the file as it is then); the directory --out is written new at every run
(a file changed there by hand is lost: the list of changes is the only place where the RTL is changed). The last line is
"all edits applied: N" or "edits not applied: N".
In Python: `import rtlapply; r = rtlapply.apply(changes, rtl_dir, out_dir, upto=None)` -> {"ok", "lines", "applied", "failed", "names"}.
"""
import argparse, ast, difflib, json, shutil, sys
from pathlib import Path


def load(path):
    try:
        d = json.loads(Path(path).read_text())
    except Exception as e:
        raise ValueError(f"{path} cannot be read as JSON: {e}")
    ch = d.get("changes") if isinstance(d, dict) else d
    if not isinstance(ch, list):
        raise ValueError(f'{path}: a list is expected under "changes"')
    for n, c in enumerate(ch):
        if not isinstance(c, dict) or not isinstance(c.get("switch"), str) or not isinstance(c.get("edits"), list):
            raise ValueError(f'{path}: entry {n} needs "switch" (a name) and "edits" (a list)')
        for k, e in enumerate(c["edits"]):
            if not isinstance(e, dict) or not all(isinstance(e.get(x), str) for x in ("file", "old", "new")):
                raise ValueError(f'{path}: entry {n} ({c["switch"]}), edit {k} needs "file", "old" and "new" as texts')
    return ch


def switch_entries(model):
    """The entries of every dictionary SWITCHES of the model file, in the order of the source: [(name, value node or None)].
    Read from the source (the model is not run). The forms found: `SWITCHES = {...}` (also a set, list or tuple of names),
    `SWITCHES = dict(...)` / `{**Other.SWITCHES, ...}` (the literal entries), `SWITCHES.update({...})`, `SWITCHES["name"] = ...`,
    `SWITCHES |= {...}`, with SWITCHES a name or an attribute (`RtlModel.SWITCHES`)."""
    try:
        tree = ast.parse(Path(model).read_text())
    except Exception:
        return None

    def is_sw(t):
        return (isinstance(t, ast.Name) and t.id == "SWITCHES") or (isinstance(t, ast.Attribute) and t.attr == "SWITCHES")

    def lit(v):
        if isinstance(v, ast.Dict):
            return [(k.value, x) for k, x in zip(v.keys, v.values) if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        if isinstance(v, (ast.Set, ast.List, ast.Tuple)):
            return [(k.value, None) for k in v.elts if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "dict":
            return [x for a in v.args for x in lit(a)] + [(k.arg, k.value) for k in v.keywords if k.arg]
        return []
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if is_sw(t):
                    found += [(node.lineno, i, n, v) for i, (n, v) in enumerate(lit(node.value))]
                elif isinstance(t, ast.Subscript) and is_sw(t.value) and isinstance(t.slice, ast.Constant) and isinstance(t.slice.value, str):
                    found.append((node.lineno, 0, t.slice.value, node.value))
        elif isinstance(node, ast.AugAssign) and is_sw(node.target):
            found += [(node.lineno, i, n, v) for i, (n, v) in enumerate(lit(node.value))]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "update" and is_sw(node.func.value):
            found += [(node.lineno, i, n, v) for a in node.args for i, (n, v) in enumerate(lit(a))]
    out, seen = [], set()
    for _, _, n, v in sorted(found, key=lambda x: (x[0], x[1])):
        if n not in seen:
            seen.add(n)
            out.append((n, v))
    return out


def model_switches(model):
    """The names in every dictionary SWITCHES of the model file, in the order of the file (read from the source, the model is not run)."""
    e = switch_entries(model)
    return None if e is None else [n for n, _ in e]


def _where(text, old):
    """Help for an "old" that is not in the file: the line of the file nearest to its first line."""
    first = next((l for l in old.splitlines() if l.strip()), "")
    lines = text.splitlines()
    best = difflib.get_close_matches(first.strip(), [l.strip() for l in lines], n=1, cutoff=0.6)
    if not best:
        return ""
    i = [l.strip() for l in lines].index(best[0])
    return f'; the nearest line of the file is line {i + 1}: "{lines[i].strip()[:160]}"'


def _nlines(t):
    return 0 if not t else t.count("\n") + (0 if t.endswith("\n") else 1)


def apply(changes, rtl_dir, out_dir=None, upto=None, show=None):
    rtl_dir = Path(rtl_dir)
    orig = {f.name: f.read_text() for f in sorted(rtl_dir.iterdir()) if f.is_file()}
    cur = dict(orig)
    lines, applied, failed, names, diffs = [], 0, 0, [], {}
    for c in changes:
        names.append(c["switch"])
        before = dict(cur)
        if not c["edits"]:
            lines.append(f'{c["switch"]}: no edit in this entry')
        for k, e in enumerate(c["edits"], 1):
            head = f'{c["switch"]} edit {k} ({e["file"]})'
            if e["file"] not in cur:
                lines.append(f'{head}: NOT APPLIED, there is no file {e["file"]} (files: {", ".join(orig)})'); failed += 1; continue
            if e["old"] == e["new"]:
                lines.append(f'{head}: NOT APPLIED, "old" and "new" are the same text'); failed += 1; continue
            if e["old"] == "":
                lines.append(f'{head}: NOT APPLIED, "old" is empty'); failed += 1; continue
            n = cur[e["file"]].count(e["old"])
            if n != 1:
                why = (f'"old" is not in the file as it is at this edit' + (" (it is in the original file: an edit before this one changed this place)" if orig[e["file"]].count(e["old"]) else _where(cur[e["file"]], e["old"]))) if n == 0 \
                    else f'"old" occurs {n} times in the file; it must occur once (take more of the text around it)'
                lines.append(f"{head}: NOT APPLIED, {why}"); failed += 1; continue
            at = cur[e["file"]][:cur[e["file"]].index(e["old"])].count("\n") + 1
            cur[e["file"]] = cur[e["file"]].replace(e["old"], e["new"])
            lines.append(f'{head}: applied at line {at} ({_nlines(e["old"])} line(s) -> {_nlines(e["new"])})'); applied += 1
        dl = []
        for name in orig:
            if cur[name] != before[name]:
                dl.append(f'== changed lines of the entry {c["switch"]} in {name} (- before this entry, + after it) ==')
                dl += ["  " + l[:240] for l in difflib.unified_diff(before[name].splitlines(), cur[name].splitlines(), lineterm="", n=0) if not l.startswith(("---", "+++"))]
        diffs[c["switch"]] = dl
        if upto and c["switch"] == upto:
            break
    else:
        if upto:
            lines.append(f"--upto {upto}: no entry has this switch name; all entries were applied")
    for n in (names if show == "all" else [show] if show else names[-1:]):
        lines += diffs.get(n) or [f"--show {n}: no entry with this name was applied" if n not in diffs else f"the entry {n} changed no line"]
    if out_dir:
        out_dir = Path(out_dir)
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)
        for name, text in cur.items():
            (out_dir / name).write_text(text)
        lines.append(f"written: {out_dir} ({len(cur)} files, {sum(cur[n] != orig[n] for n in orig)} changed)")
    return {"ok": failed == 0, "lines": lines, "applied": applied, "failed": failed, "names": names}


def compare_names(names, model):
    sw = model_switches(model)
    if sw is None:
        return [f"the names in SWITCHES of {model} could not be read"]
    out = []
    miss = [s for s in sw if s not in names]
    extra = [n for n in names if n not in sw]
    dup = sorted({n for n in names if names.count(n) > 1})
    if miss:
        out.append("switches of the model without an entry in the list of changes: " + ", ".join(miss))
    if extra:
        out.append("entries whose name is not in SWITCHES of the model: " + ", ".join(extra))
    if dup:
        out.append("names with more than one entry: " + ", ".join(dup))
    if not out:
        out.append(f"every switch of the model has one entry ({len(sw)})")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("changes"); ap.add_argument("--rtl", default="/code/rtl"); ap.add_argument("--out", default="/code/work/rtl_fixed"); ap.add_argument("--upto"); ap.add_argument("--show"); ap.add_argument("--model")
    a = ap.parse_args(argv)
    try:
        ch = load(a.changes)
    except ValueError as e:
        print(e); return 2
    r = apply(ch, a.rtl, a.out, a.upto, a.show)
    print("\n".join(r["lines"]))
    model = a.model or ("/code/work/rtl_model.py" if Path("/code/work/rtl_model.py").exists() else None)
    if model and not a.upto:
        print("\n".join(compare_names(r["names"], model)))
    print(f'all edits applied: {r["applied"]}' if r["ok"] else f'edits not applied: {r["failed"]} (applied: {r["applied"]})')
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
