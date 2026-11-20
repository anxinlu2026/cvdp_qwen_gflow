"""Host-side fact tool of the general flow (never inside Qwen's cell): run an RTL with Icarus and a Python model `RtlModel` on the same random inputs and report where the outputs differ.
The top interface comes from interface.json (written by the agent in order A): {"top", "clock" (name or null), "reset": {"name", "active"} or null, "inputs": {name: width}, "outputs": {name: width}}.
The model: RtlModel() or RtlModel(fix="all"); step(**inputs), every input a V of its declared width -> {output: a V of the library svvec (tool/gflow/svvec.py, in the cell /code/lib), or an int, or None for all bits X};
the outputs are compared bit by bit, X included; one call = one rising clock edge (or one evaluation when there is no clock).
usage: python3 simcheck.py --rtl DIR --work DIR [--model-rtl DIR] [--fix all] [--edges 200] [--out DIR]
  --work: the agent's files (rtl_model.py, interface.json); --model-rtl: what the model sees at /code/rtl (default: --rtl).
Prints one JSON line; with --out writes sim_check.txt (the facts, for the agent) and sim_check_case.json (the inputs up to the first difference and the RTL outputs)."""
import argparse, json, random, shutil, subprocess, sys, tempfile
from pathlib import Path

IMAGE = "lora-s3xcell:v4-20261111"
RUNNER = r'''
import json, sys, importlib.util, traceback
sys.path.insert(0, "/code/work"); sys.path.insert(0, "/code/lib")
fix = sys.argv[1]
stims = json.load(open("/w/stim.json"))
widths = json.load(open("/code/work/interface.json"))["inputs"]
import svvec
out = {"error": None, "traces": []}
try:
    s = importlib.util.spec_from_file_location("rtl_model", "/code/work/rtl_model.py"); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    for stim in stims:
        fx = tuple(x for x in fix[5:].split(",") if x) if fix.startswith("list:") else fix   # "list:a,b": these switch names, as a tuple
        t = m.RtlModel(fix=fx) if fix != "-" else m.RtlModel()
        tr = []
        for c in stim:
            o = t.step(**{k: svvec.V(int(widths.get(k, 1)), v) for k, v in c.items()})
            tr.append({k: (None if v is None else "b" + v.bin() if hasattr(v, "bin") and hasattr(v, "w") else int(v)) for k, v in o.items()})
        out["traces"].append(tr)
except Exception:
    out["error"] = traceback.format_exc()[-1500:]
json.dump(out, open("/w/model_out.json", "w"))
'''


def stimuli(itf, edges, seeds=(1, 2, 3, 4)):
    rst = itf.get("reset") or None
    out = []
    for n, seed in enumerate(seeds):
        r = random.Random(seed)
        p1 = (0.5, 0.1, 0.9, 0.03)[n % 4]
        stim, prev = [], {}
        for e in range(edges):
            c = {}
            for name, w in itf["inputs"].items():
                if rst and name == rst["name"]:
                    on = e < 2 or (n == 0 and e > 40 and r.random() < 0.01)
                    c[name] = rst["active"] if on else 1 - rst["active"]
                elif w == 1:
                    c[name] = int(r.random() < p1)
                else:
                    x = r.random()
                    c[name] = prev.get(name, 0) if x < 0.15 and e else 0 if x < 0.18 else (1 << w) - 1 if x < 0.21 else r.getrandbits(w)
            prev = c
            stim.append(c)
        out.append(stim)
    return out


def tb(itf, stim, dump=False):
    clk, rst = itf.get("clock"), itf.get("reset")
    L = ["`timescale 1ns/1ps", "module tb;"]
    if clk:
        L.append(f"logic {clk}=0;")
    for n, w in itf["inputs"].items():
        init = rst["active"] if rst and n == rst["name"] else 0
        L.append(f"logic [{w - 1}:0] {n}={init};")
    for n, w in itf["outputs"].items():
        L.append(f"logic [{w - 1}:0] {n};")
    ports = ([clk] if clk else []) + list(itf["inputs"]) + list(itf["outputs"])
    L.append(f"{itf['top']} dut({', '.join(f'.{p}({p})' for p in ports)});")
    fmt = " ".join("%b" for _ in itf["outputs"])
    L.append("integer f; initial begin " + ("$dumpfile(\"dump.vcd\"); $dumpvars(0, dut); " if dump else "") + "f=$fopen(\"out.txt\"); #2;")
    for c in stim:
        L.append("#2 " + " ".join(f"{n}={w}'h{c[n]:x};" for n, w in itf["inputs"].items()))
        L.append((f"#6 {clk}=1; #1 " if clk else "#1 ") + f"$fdisplay(f, \"{fmt}\", {', '.join(itf['outputs'])});" + (f" #1 {clk}=0;" if clk else ""))
    L += ["$fclose(f); $finish; end", "endmodule"]
    return "\n".join(L)


def rtl_traces(rtl_dir, itf, stims):
    out = []
    with tempfile.TemporaryDirectory() as d:
        for i, stim in enumerate(stims):
            Path(d, f"tb{i}.sv").write_text(tb(itf, stim))
        srcs = " ".join(f"/r/{s.name}" for s in sorted(Path(rtl_dir).iterdir()) if s.suffix in (".sv", ".v"))
        script = " && ".join(f"iverilog -g2012 -s tb -o sim{i} tb{i}.sv {srcs} && vvp -n sim{i} >/dev/null && mv out.txt out{i}.txt" for i in range(len(stims)))
        p = subprocess.run(["docker", "run", "--rm", "--network", "none", "--user", "root", "-v", f"{d}:/w", "-v", f"{Path(rtl_dir).resolve()}:/r:ro", "-w", "/w", "--entrypoint", "sh", IMAGE, "-c", script],
                           capture_output=True, text=True, timeout=900)
        if p.returncode:
            return None, _errtext(p.stderr + p.stdout)
        for i in range(len(stims)):
            tr = []
            for l in Path(d, f"out{i}.txt").read_text().splitlines():
                if l.strip():
                    tr.append({n: v.lower().replace("z", "x") for n, v in zip(itf["outputs"], l.split())})
            out.append(tr)
    return out, None


def rtl_signals(rtl_dir, itf, stim, edge):
    """Internal signals of the RTL (all that the simulator's dump holds: no unpacked arrays; ports of submodule instances are in it) around `edge`:
    just before the edge (the inputs of this edge applied, combinational logic settled) and just after it. Timing of tb(): edge e rises at 10+10e ns (timescale 1ns/1ps -> x1000)."""
    with tempfile.TemporaryDirectory() as d:
        Path(d, "tb.sv").write_text(tb(itf, stim[:edge + 1], dump=True))
        srcs = " ".join(f"/r/{s.name}" for s in sorted(Path(rtl_dir).iterdir()) if s.suffix in (".sv", ".v"))
        p = subprocess.run(["docker", "run", "--rm", "--network", "none", "--user", "root", "-v", f"{d}:/w", "-v", f"{Path(rtl_dir).resolve()}:/r:ro", "-w", "/w", "--entrypoint", "sh", IMAGE, "-c",
                            f"iverilog -g2012 -s tb -o sim tb.sv {srcs} && vvp -n sim >/dev/null"], capture_output=True, text=True, timeout=900)
        if p.returncode or not Path(d, "dump.vcd").exists():
            return None
        names, scope, val, snaps, t = {}, [], {}, {}, 0
        marks = sorted({(10 * e + 9) * 1000: f"before edge {e}" for e in (edge - 1, edge) if e >= 0}.items() | {(10 * e + 11) * 1000: f"after edge {e}" for e in (edge - 1, edge) if e >= 0}.items())
        pending = list(marks)
        for l in Path(d, "dump.vcd").read_text().splitlines():
            w = l.split()
            if not w:
                continue
            if w[0] == "$scope":
                scope.append(w[2])
            elif w[0] == "$upscope":
                scope.pop()
            elif w[0] == "$var":
                names.setdefault(w[3], []).append(".".join(scope[1:] + [w[4]]) + (w[5] if len(w) > 6 and w[5].startswith("[") else ""))
            elif w[0].startswith("#"):
                nt = int(w[0][1:])
                while pending and pending[0][0] < nt:
                    snaps[pending.pop(0)[1]] = dict(val)
                t = nt
            elif l[0] in "bB" and len(w) == 2:
                val[w[1]] = w[0][1:]
            elif l[0] in "01xXzZ" and not l.startswith("$"):
                val[l[1:]] = l[0]
        for _, lab in pending:
            snaps[lab] = dict(val)

        def fmt(b):
            return "x" if any(c in "xXzZ" for c in b) and len(b) == 1 else b if any(c in "xXzZ" for c in b) else format(int(b, 2), "x")
        out = []
        for _, lab in marks:
            out.append(f"== {lab} ==")
            sn = snaps.get(lab, {})
            for code, ns in sorted(names.items(), key=lambda kv: kv[1][0]):
                for n in ns:
                    out.append(f"{n} = {fmt(sn[code]) if code in sn else '?'}")
        return "\n".join(out)


def _errtext(t, limit=3000):
    """The compiler's messages without its 'sorry:' notes (what it does not support; they are not errors and can fill the whole text)."""
    lines = t.splitlines()
    kept = [l for l in lines if "sorry:" not in l]
    n = len(lines) - len(kept)
    return "\n".join(kept)[-limit:] + (f"\n({n} lines with 'sorry:' of the simulator are left out; they are notes, not errors)" if n else "")


def model_traces(work, model_rtl, stims, fix):
    with tempfile.TemporaryDirectory() as d:
        w = Path(d, "work")
        shutil.copytree(work, w)
        s = Path(d, "s"); s.mkdir()
        lib = Path(d, "lib"); lib.mkdir()
        shutil.copy(Path(__file__).resolve().parent / "svvec.py", lib / "svvec.py")
        (s / "stim.json").write_text(json.dumps(stims)); (s / "runner.py").write_text(RUNNER)
        p = subprocess.run(["docker", "run", "--rm", "--network", "none", "--user", "root", "-v", f"{w}:/code/work", "-v", f"{Path(model_rtl).resolve()}:/code/rtl:ro", "-v", f"{s}:/w", "-v", f"{lib}:/code/lib:ro", "-w", "/code/work",
                            "--entrypoint", "python3", IMAGE, "/w/runner.py", fix or "-"], capture_output=True, text=True, timeout=1800)
        f = s / "model_out.json"
        if not f.exists():
            return None, _errtext(p.stderr + p.stdout)
        o = json.loads(f.read_text())
        return (o["traces"], None) if not o["error"] else (None, o["error"])


def check(rtl, work, model_rtl=None, fix=None, edges=200, out=None):
    itf_file = Path(work) / "interface.json"
    res = {"ok": False, "rtl": str(rtl), "fix": fix}
    lines = []
    try:
        itf = json.loads(itf_file.read_text())
        if itf.get("reset") and itf["reset"]["name"] not in itf["inputs"]:   # the reset is an input port also when the agent listed it only under "reset"
            itf["inputs"] = {itf["reset"]["name"]: 1, **itf["inputs"]}
        assert isinstance(itf["inputs"], dict) and isinstance(itf["outputs"], dict) and itf["top"]
    except Exception as e:
        res["error"] = f"interface.json cannot be used: {e!r}"
        lines.append(res["error"])
        return _finish(res, lines, out, None)
    stims = stimuli(itf, edges)
    rt, err = rtl_traces(rtl, itf, stims)
    if err:
        res["error"] = "the simulator could not build the RTL with the testbench made from interface.json:\n" + err
        lines.append(res["error"])
        return _finish(res, lines, out, None)
    mt, err = model_traces(work, model_rtl or rtl, stims, fix)
    if err:
        res["error"] = "RtlModel raised an error when it was run on the inputs of the check:\n" + err
        lines.append(res["error"])
        return _finish(res, lines, out, None)
    case, tot = None, 0
    res["scenarios"] = []
    for i, (r, m) in enumerate(zip(rt, mt)):
        diffs = []
        for e in range(min(len(r), len(m))):
            for n in itf["outputs"]:
                rv = r[e][n]
                mv = _bits(m[e].get(n, "missing"), itf["outputs"][n])
                if rv != mv:
                    diffs.append((e, n, rv, mv))
        tot += len(diffs)
        res["scenarios"].append({"scenario": i, "edges": len(r), "differences": len(diffs), "first": diffs[:1]})
        lines.append(f"scenario {i}: {len(r)} edges, {len(set(d[0] for d in diffs))} edges with a difference")
        for e, n, text, mv in diffs[:4]:
            lines.append(f"  edge {e} output {n}: RTL (simulator) = {_show(text, mv)}   RtlModel = {_show(mv, text)}")
        if diffs and case is None:
            last = min(len(r), diffs[0][0] + 3)
            sig = rtl_signals(rtl, itf, stims[i], diffs[0][0])
            if sig and out:
                Path(out).mkdir(parents=True, exist_ok=True)
                Path(out, "sim_check_signals.txt").write_text("Signals of the RTL in the simulator for the case of sim_check_case.json (hex; a value with x is printed in binary). Unpacked arrays are not in the list; the ports of the submodule instances are.\n" + sig + "\n")
            case = {"scenario": i, "first_difference_edge": diffs[0][0], "inputs_per_edge": stims[i][:last], "rtl_outputs_per_edge": [{n: _hex(v) for n, v in x.items()} for x in r[:last]]}
    res["ok"] = tot == 0
    res["differences"] = tot
    lines.insert(0, "A simulator ran the RTL, and RtlModel" + (f"(fix={fix!r})" if fix else "()") + " was run on the same inputs (random values, reset in the first two edges). Outputs compared after every edge, bit by bit (hex; x = digit unknown, X = digit partly unknown; a value is printed in binary where the hex texts would be the same).")
    lines.append("no difference" if res["ok"] else "the signals of the RTL just before and just after the edge of the first difference (and the edge before it) are in sim_check_signals.txt; the inputs up to the first difference and the RTL outputs per edge are in sim_check_case.json (edge 0 is the first step() call of a new RtlModel; step() gets every input as V(width, value))")
    return _finish(res, lines, out, case)


def record(rtl, work, edges=200, out=None):
    """What the simulator gives for the RTL alone: {"inputs", "outputs", "stims", "rtl"} (the outputs per edge as bit texts); for basecheck.py in the cell."""
    itf = json.loads((Path(work) / "interface.json").read_text())
    if itf.get("reset") and itf["reset"]["name"] not in itf["inputs"]:
        itf["inputs"] = {itf["reset"]["name"]: 1, **itf["inputs"]}
    stims = stimuli(itf, edges)
    rt, err = rtl_traces(rtl, itf, stims)
    if err:
        raise RuntimeError(err)
    rec = {"inputs": itf["inputs"], "outputs": itf["outputs"], "stims": stims, "rtl": rt}
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(rec))
    return rec


def _bits(v, w):
    """A model output as a text of w bits (0, 1, x); another text when it cannot be one."""
    if v is None:
        return "x" * w
    if isinstance(v, str):
        if v.startswith("b"):
            return v[1:] if len(v) - 1 == w else f"a V of {len(v) - 1} bits (the port has {w})"
        return v
    return format(v, f"0{w}b") if 0 <= v < (1 << w) else f"{v:#x} (does not fit the {w} bits of the port)"


def _hex(b):
    if not b or any(c not in "01x" for c in b):
        return b
    b = b.rjust((len(b) + 3) // 4 * 4, "0")
    return "".join(format(int(g, 2), "x") if "x" not in g else "x" if g == "xxxx" else "X" for g in (b[i:i + 4] for i in range(0, len(b), 4)))


def _show(b, other):
    return b if _hex(b) == _hex(other) else _hex(b)


def _finish(res, lines, out, case):
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        Path(out, "sim_check.txt").write_text("\n".join(lines) + "\n")
        if case:
            Path(out, "sim_check_case.json").write_text(json.dumps(case))
        elif Path(out, "sim_check_case.json").exists():
            Path(out, "sim_check_case.json").unlink()
    res["text"] = "\n".join(lines)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtl", required=True); ap.add_argument("--work", required=True); ap.add_argument("--model-rtl"); ap.add_argument("--fix"); ap.add_argument("--edges", type=int, default=200); ap.add_argument("--out")
    a = ap.parse_args()
    r = check(a.rtl, a.work, a.model_rtl, a.fix, a.edges, a.out)
    print(r.pop("text")); print(json.dumps(r, default=str)[:1500])
