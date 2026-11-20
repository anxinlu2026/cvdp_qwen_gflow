"""Host-side fact tool of the general flow (never inside Qwen's cell): does /code/work/stimulus.json do what the testbench does?

A simulator runs the task's own testbench on the RTL and records, at every rising clock edge with the reset not active, the inputs of the top module at the edge and its outputs after it.
RtlModel() (no switch: it equals the RTL) is run on stimulus.json with sigdump; its edges with the reset not active are compared with the simulator's, edge by edge: inputs and outputs (an input the testbench leaves X is not compared, nor an output the simulator has X in).
The comparison says where the stimulus file leaves the testbench; it does not judge the design.

usage: python3 stimcheck.py --rtl DIR --verif DIR --work DIR [--out DIR]
"""
import argparse, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

IMAGE = "lora-s3xcell:v4-20261111"
HERE = Path(__file__).resolve().parent
MAX_EDGES = 5000
RUNNER = r'''
import json, sys, traceback
sys.path.insert(0, "/code/lib")
out = {"error": None, "edges": []}
try:
    import sigdump
    recs = sigdump.run(sigdump.load_model("/code/work/rtl_model.py").RtlModel(), "/code/work/stimulus.json")
    for r in recs:
        out["edges"].append({"step": r["step"], "label": r["label"], "inputs": r["inputs"], "outputs": {k: (v.bin() if hasattr(v, "bin") else None if v is None else format(int(v), "b")) for k, v in r["outputs"].items()}})
    out["steps"] = [{"step": s["step"], "label": s["label"], "edges": s["edges"], "reached": s["reached"]} for s in recs.steps]
except Exception:
    out["error"] = traceback.format_exc()[-1500:]
json.dump(out, open("/w/model_out.json", "w"))
'''


def probe(itf, tbmod, inst):
    ins = [n for n in itf["inputs"]]
    outs = list(itf["outputs"])
    rst = (itf.get("reset") or {}).get("name")
    if rst and rst not in ins:
        ins.append(rst)
    p = f"{tbmod}.{inst}"
    L = ["module stimcheck_probe;", "integer f, n;"]
    L += [f"reg [{max(int(itf['inputs'].get(n, 1)), 1) - 1}:0] s_{n};" for n in ins]
    L += ["initial begin f = $fopen(\"probe.txt\", \"w\"); n = 0; end",
          f"always @(posedge {p}.{itf['clock']}) begin"]
    L += [f"  s_{n} = {p}.{n};" for n in ins]
    L += ["  #1;",
          "  $fdisplay(f, \"" + " ".join(["%b"] * (len(ins) + len(outs))) + "\", " + ", ".join([f"s_{n}" for n in ins] + [f"{p}.{n}" for n in outs]) + ");",
          f"  n = n + 1; if (n >= {MAX_EDGES}) begin $fclose(f); $finish; end",
          "end", "endmodule"]
    return "\n".join(L), ins, outs


def tb_edges(rtl, verif, itf):
    tbs = [f for f in sorted(Path(verif).iterdir()) if f.suffix in (".sv", ".v")]
    text = "\n".join(f.read_text() for f in tbs)
    mm = re.search(r"^\s*module\s+(\w+)", text, re.M)
    mi = re.search(r"\b" + re.escape(itf["top"]) + r"\b\s*(?:#\s*\((?:[^()]|\([^()]*\))*\))?\s*(\w+)\s*\(", text, re.S)
    if not (mm and mi):
        return None, "no testbench module that instantiates the top module was found in the verif files"
    src, ins, outs = probe(itf, mm.group(1), mi.group(1))
    with tempfile.TemporaryDirectory(dir=Path.home()) as d:
        Path(d, "zz_probe.sv").write_text(src)
        for f in tbs:
            shutil.copy(f, Path(d, f.name))
        srcs = " ".join([f.name for f in tbs] + ["zz_probe.sv"] + [f"/r/{s.name}" for s in sorted(Path(rtl).iterdir()) if s.suffix in (".sv", ".v")])
        p = subprocess.run(["docker", "run", "--rm", "--network", "none", "--user", "root", "-v", f"{d}:/w", "-v", f"{Path(rtl).resolve()}:/r:ro", "-w", "/w", "--entrypoint", "sh", IMAGE, "-c",
                            f"iverilog -g2012 -s {mm.group(1)} -s stimcheck_probe -o sim {srcs} && timeout 600 vvp -n sim >vvp.txt 2>&1; test -f probe.txt"], capture_output=True, text=True, timeout=900)
        if p.returncode or not Path(d, "probe.txt").exists():
            return None, "the simulator did not run the testbench: " + (p.stderr + p.stdout)[-1500:]
        rows = []
        for l in Path(d, "probe.txt").read_text().splitlines():
            w = l.split()
            if len(w) == len(ins) + len(outs):
                rows.append({"inputs": dict(zip(ins, w[:len(ins)])), "outputs": dict(zip(outs, w[len(ins):]))})
        return rows, None


def model_edges(work, rtl):
    with tempfile.TemporaryDirectory(dir=Path.home()) as d:
        w = Path(d, "work")
        shutil.copytree(work, w)
        s = Path(d, "s"); s.mkdir()
        lib = Path(d, "lib"); lib.mkdir()
        for n in ("svvec.py", "sigdump.py"):
            shutil.copy(HERE / n, lib / n)
        (s / "runner.py").write_text(RUNNER)
        p = subprocess.run(["docker", "run", "--rm", "--network", "none", "--user", "root", "-v", f"{w}:/code/work", "-v", f"{Path(rtl).resolve()}:/code/rtl:ro", "-v", f"{s}:/w", "-v", f"{lib}:/code/lib:ro", "-w", "/code/work",
                            "--entrypoint", "python3", IMAGE, "/w/runner.py"], capture_output=True, text=True, timeout=1800)
        f = s / "model_out.json"
        if not f.exists():
            return None, (p.stderr + p.stdout)[-2000:]
        o = json.loads(f.read_text())
        return (o, None) if not o["error"] else (None, o["error"])


def _iv(v):
    return "x" if v is None else format(int(v), "x")


def _hex(b):
    b = b.lower().replace("z", "x")
    return b if "x" in b else format(int(b, 2), "x")


def check(rtl, verif, work, out=None):
    work = Path(work)
    res = {"ok": False}
    lines = []
    if not (work / "stimulus.json").exists():
        res["error"] = "there is no /code/work/stimulus.json"
    else:
        itf = json.loads((work / "interface.json").read_text())
        rst = itf.get("reset") or {}
        sim, err = tb_edges(rtl, verif, itf)
        mod, err2 = (None, None) if err else model_edges(work, rtl)
        if err or err2:
            res["error"] = err or ("sigdump could not run RtlModel() on stimulus.json:\n" + err2)
        else:
            def active(v):
                return rst.get("name") and str(v) in (str(rst.get("active", 0)), format(int(rst.get("active", 0)), "b"))
            a = [r for r in sim if not active(r["inputs"].get(rst.get("name"), ""))]
            b = [r for r in mod["edges"] if not active(r["inputs"].get(rst.get("name"), ""))]
            names_in = [n for n in itf["inputs"] if n != rst.get("name")]
            first = None
            for i in range(min(len(a), len(b))):
                for n in names_in:
                    sa = a[i]["inputs"][n].lower()
                    vb = b[i]["inputs"][n]
                    if not ("x" in sa or "z" in sa) and (vb is None or int(sa, 2) != int(vb)):   # an input the testbench leaves X: any value of the stimulus file is taken
                        first = first or (i, "input", n, _hex(sa), _iv(vb))
                for n in itf["outputs"]:
                    sa, sb = a[i]["outputs"][n].lower().replace("z", "x"), (b[i]["outputs"].get(n) or "x")
                    if "x" not in sa and _hex(sa) != _hex(sb.zfill(len(sa)) if "x" not in sb else sb):   # outputs the simulator has X in (from X inputs) are not compared
                        first = first or (i, "output", n, _hex(sa), _hex(sb))
                if first:
                    break
            res.update(edges_testbench=len(a), edges_stimulus=len(b), first_difference=first, steps=mod.get("steps"))
            res["ok"] = first is None and len(b) > 0 and abs(len(a) - len(b)) <= max(4, len(a) // 20)
            lines.append("A simulator ran the testbench of the task on the RTL; RtlModel() (no switch) was run on /code/work/stimulus.json with sigdump. Compared edge by edge, counting only the rising clock edges with the reset not active (edge 0 is the first of them): the inputs of the top module at the edge and its outputs after it. An input that the testbench leaves X at an edge is not compared at that edge.")
            lines.append(f"The testbench has {len(a)} such edges; stimulus.json gives {len(b)}.")
            if first:
                i, kind, n, va, vb = first
                st = b[i]
                lines.append(f"First difference at edge {i} (step {st['step']}" + (f", {st['label']}" if st["label"] else "") + f" of stimulus.json): {kind} {n}: testbench {va}, stimulus.json {vb}.")
                lo = max(0, i - 2)
                for j in range(lo, min(i + 2, len(a), len(b))):
                    lines.append(f"  edge {j}: testbench inputs " + " ".join(f"{k}={_hex(a[j]['inputs'][k])}" for k in names_in) + "   stimulus.json inputs " + " ".join(f"{k}={_iv(b[j]['inputs'][k])}" for k in names_in))
            else:
                lines.append("No difference in the edges both have.")
                if not res["ok"]:
                    lines.append("The numbers of edges are not the same: one of the two stops earlier or runs longer.")
            for s in mod.get("steps") or []:
                if not s["reached"]:
                    lines.append(f"Step {s['step']}" + (f" ({s['label']})" if s["label"] else "") + f" of stimulus.json did not reach its `until` in {s['edges']} edges.")
    if res.get("error"):
        lines.append(res["error"])
    res["text"] = "\n".join(lines)
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "stim_check.txt").write_text(res["text"] + "\n")
        (Path(out) / "stim_result.json").write_text(json.dumps(res, default=str))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtl", required=True); ap.add_argument("--verif", required=True); ap.add_argument("--work", required=True); ap.add_argument("--out")
    a = ap.parse_args()
    r = check(a.rtl, a.verif, a.work, a.out)
    print(r["text"])
    sys.exit(0 if r["ok"] else 1)
