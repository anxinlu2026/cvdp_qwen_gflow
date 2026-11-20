"""Stage 3 value check of align/ (exploration tool, runs on the host; the simulation runs in a throw-away container of the cell image).

For every block port of align/blk_*.json it evaluates "signal + index_map" on a simulation of the design and compares the result with the value
that blocks.py gives for the steps of the block (first decryption of the testbench). Two readings per port and step:
  anywhere: edges (1..26) at which the evaluated signal equals the model value (independent of the timeline)
  assigned: the edge(s) the timeline of align/ assigns to the step, and whether the value equals there
The model is not changed and the design is not changed; a difference is reported, not interpreted.

usage: python3 tool/stage3_check/index_values.py --align DIR --design DIR(with rtl/ and verif/) --out DIR [--image IMG]
"""
import argparse
import itertools
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] if len(Path(__file__).resolve().parents) > 2 else Path("/")
CELL = Path("/code/work/map").exists()  # inside the stage 3 cell: local simulation, map and model from /code/work
MAP = Path("/code/work/map") if CELL else ROOT / "runs" / "map2_aes0005-s2a1-r1" / "for_architecture" / "map"
MODEL = ROOT / "data" / "stages" / "aes0005_S4"  # only for the testbench text
KEY = "2b7e151628aed2a6abf7158809cf4f3c"
CT = "3925841d02dc09fbdc118597196a0b32"
TOP = "tb_aes128_dec"
EDGES = range(1, 27)


# ---------------------------------------------------------------- model
def model_steps():
    sys.path.insert(0, str(MAP))
    sys.path.insert(0, str(ROOT / "work_model_dummy"))
    import importlib
    # aes_model lives in the stage 2 inputs
    cand = [Path("/code/work/model/aes_model.py")] if CELL else list((ROOT / "data").rglob("aes_model.py"))
    sys.path.insert(0, str(cand[0].parent))
    blocks = importlib.import_module("blocks")
    B = blocks.BLOCKS
    ks = B["key_expansion"](KEY)
    w = lambda k: ks[k * 8:(k + 4) * 8]  # w(k): words k..k+3 as 16 bytes? (k = 4*round -> byte offset 16*round)
    rk = lambda r: ks[r * 32:(r + 1) * 32]
    steps = []
    n = 0

    def add(pos, rnd, blk, ins, outs, inst=None):
        nonlocal n
        steps.append({"n": n, "position": pos, "round": rnd, "block": blk, "in": ins, "out": outs, "inst": inst})
        n += 1
    add("prepare", None, "key_expansion", {"key": KEY}, {"ks": ks})
    # key expansion parts (not schedule steps of top.json; per instance i = round constant index)
    W = [ks[k * 8:(k + 1) * 8] for k in range(44)]
    parts = []
    for i in range(1, 11):
        t = W[4 * i - 1]
        r = B["rot_word"](t); s = B["sub_word"](r); rcon = format(blocks.RCON[i - 1], "02x") + "000000"; x = B["xor_with_rcon"](s, rcon)
        o = B["xor_with_prev_words"](W[4 * i - 4], x)
        parts.append((i - 1, {"rot_word": ({"word_in": t}, {"word_out": r}), "sub_word": ({"word_in": r}, {"word_out": s}),
                              "xor_with_rcon": ({"word_in": s, "rcon": rcon}, {"word_out": x}),
                              "xor_with_prev_words": ({"word_prev": W[4 * i - 4], "word_temp": x}, {"word_out": o})}))
    keyparts = parts
    st = B["load"](CT)
    add("prepare", None, "load", {"in": CT}, {"state": st})
    o = B["add_round_key"](st, rk(10)); add("initial", None, "add_round_key", {"state_in": st, "round_key": rk(10)}, {"state_out": o}); st = o
    for r in range(9, 0, -1):
        for b in ("inv_shift_rows", "inv_sub_bytes", "add_round_key", "inv_mix_columns"):
            if b == "add_round_key":
                o = B[b](st, rk(r)); add("loop", r, b, {"state_in": st, "round_key": rk(r)}, {"state_out": o})
            else:
                o = B[b](st); add("loop", r, b, {"state_in": st}, {"state_out": o})
            st = o
    for b in ("inv_shift_rows", "inv_sub_bytes", "add_round_key"):
        if b == "add_round_key":
            o = B[b](st, rk(0)); add("final", None, b, {"state_in": st, "round_key": rk(0)}, {"state_out": o})
        else:
            o = B[b](st); add("final", None, b, {"state_in": st}, {"state_out": o})
        st = o
    add("final", None, "store", {"state": st}, {"out": st})
    return steps, keyparts


# ---------------------------------------------------------------- declarations
def decls(design):
    d = {}
    params = {"STEPS": 10}
    for f in (design / "rtl").glob("*.sv"):
        mod = None
        for line in f.read_text().splitlines():
            mm = re.match(r"\s*module\s+(\w+)", line)
            if mm:
                mod = mm.group(1)
            m = re.match(r"\s*logic\s*(\[[^\]]*\])?\s*(\w+)\s*((?:\[[^\]]+\]\s*)*)\s*;", line)
            if m:
                dims = re.findall(r"\[([^\]]+)\]", m.group(3))
                vals = []
                for x in dims:
                    try:
                        vals.append(int(eval(x, {}, params)))
                    except Exception:
                        vals = None
                        break
                d.setdefault(m.group(2), vals)
                DECLMOD.setdefault(m.group(2), set()).add(mod)
    INSTANCES.clear()
    texts = [f.read_text() for f in (design / "rtl").glob("*.sv")]
    for mods in set(x for v in DECLMOD.values() for x in v):
        for t in texts:
            for im in re.finditer(r"\b%s\b\s*(?:#\s*\([^;]*?\)\s*)?(\w+)\s*\(" % re.escape(mods), t):
                if im.group(1) not in ("module",):
                    INSTANCES.setdefault(mods, set()).add(im.group(1))
    return d


# ---------------------------------------------------------------- name resolution (suffix of the hierarchical name, as rtl probe does)
SCOPES = []
VARS = {}
DECLMOD = {}
INSTANCES = {}


def load_scopes(vcd):
    stack, res = [], set()
    VARS.clear()
    for l in Path(vcd).read_text().splitlines():
        if l.startswith("$scope"):
            stack.append(l.split()[2]); res.add(".".join(stack))
        elif l.startswith("$upscope"):
            stack.pop()
        elif l.startswith("$var") and stack:
            VARS.setdefault(".".join(stack), set()).add(l.split()[4])
    SCOPES[:] = sorted(res)


def resolve_bare(name):
    """a name without a scope part: the one scope that has a variable of this name (arrays are not in the VCD: then the instances of the module that declares it)."""
    c = [sc for sc in SCOPES if name in VARS.get(sc, ())]
    if not c:
        for mod in DECLMOD.get(name, ()):
            for inst in INSTANCES.get(mod, ()):
                c += [sc for sc in SCOPES if sc == inst or sc.endswith("." + inst)]
    c = sorted(set(c))
    if len(c) != 1:
        raise ValueError("name %s matches %d signals%s" % (name, len(c), (": " + ", ".join(c[:6])) if c else ""))
    return c[0]


def resolve_path(segs, base=None):
    """segs: the scope part of a name (without the last identifier); returns the full scope path or raises."""
    if not segs:
        return resolve_bare(base) if base else TOP
    tail = ".".join(segs)
    c = [x for x in SCOPES if x == tail or x.endswith("." + tail)]
    if len(c) != 1:
        raise ValueError("name %s matches %d scopes" % (tail, len(c)))
    return c[0]


# ---------------------------------------------------------------- signal expansion
def split_selects(s):
    m = re.match(r"^(.*?)((?:\[[^\]]+\])*)$", s.strip())
    return m.group(1), re.findall(r"\[([^\]]+)\]", m.group(2))


def expand_signal(sig, decl, env):
    """-> list of (verilog expression, shape) for a signal string without '+', with the instance variable replaced by env values."""
    sig = sig.strip()
    for k, v in env.items():
        sig = re.sub(r"\[%s\]" % re.escape(k), "[%d]" % v, sig)
    segs = sig.split(".")
    base_last, sels = split_selects(segs[-1])
    if not re.fullmatch(r"[A-Za-z_]\w*", base_last) or not all(re.fullmatch(r"[A-Za-z_]\w*(\[\d+\])*", x.strip()) for x in segs[:-1]):
        return None, "signal name is not an identifier path: " + sig
    try:
        path = resolve_path(segs[:-1], base_last) + "." + base_last
    except ValueError as ex:
        return None, str(ex)
    dims = decl.get(base_last)
    if dims is None:
        dims = []
    # the selections of the last segment
    picked = []
    for x in sels:
        if re.fullmatch(r"\d+", x.strip()) or x.strip() == "*":
            picked.append(x.strip())
        else:
            return None, "part-select in signal: " + x
    lists = []
    free = 0
    for k, dsz in enumerate(dims):
        if k < len(picked) and picked[k] != "*":
            lists.append([int(picked[k])])
        else:
            lists.append(list(range(dsz))); free += 1
    return {"path": path, "dims": [len(l) for l in lists], "idx": [l for l in lists]}, None


# ---------------------------------------------------------------- simulation
def need_signals(blocks):
    """the set of (path, idxlists) the evaluation needs; keys by repr."""
    return {}


DROPPED = []


def simulate(design, out, image, probes, ctl):
    """probes: dict id -> verilog expressions list; prints V edge id k hex. A probe that cannot be bound by the compiler is dropped (listed in DROPPED) and the compilation is repeated."""
    out.mkdir(parents=True, exist_ok=True)
    dead = set()
    for attempt in range(30):
        lines = ["module mon; integer e = 0;", "always @(posedge %s.clk) begin e = e + 1;" % TOP]
        for pid, exprs in probes.items():
            for k, ex in enumerate(exprs):
                if ex not in dead:
                    lines.append('  $display("V %%0d %s %d %%h", e, %s);' % (pid, k, ex))
        for name in ctl:
            lines.append('  $display("C %%0d %s %%d", e, %s.uu_aes128_decrypt.%s);' % (name, TOP, name))
        lines.append("end\nendmodule")
        (out / "mon.sv").write_text("\n".join(lines))
        if CELL:
            iv, vv, d_, o_ = "/usr/local/bin/iverilog", "/usr/local/bin/vvp", str(design), str(out)
            run = lambda sc: subprocess.run(["bash", "-c", sc], capture_output=True, text=True)
        else:
            iv, vv, d_, o_ = "iverilog", "vvp", "/s", "/o"
            run = lambda sc: subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{design.resolve()}:/s:ro", "-v", f"{out.resolve()}:/o", image, "bash", "-c", sc], capture_output=True, text=True)
        r = run(f"cd {o_} && {iv} -g2012 -o a {d_}/rtl/*.sv {d_}/verif/*.sv mon.sv > comp.log 2>&1; echo rc=$?")
        comp = (out / "comp.log").read_text()
        bad = re.findall(r"Unable to bind wire/reg/memory `([^']+)' in `mon'", comp)
        if "rc=0" in r.stdout and not bad:
            break
        if not bad:
            return "compile failed: " + comp[:300]
        for b in bad:
            ex = re.sub(r"\['sd(\d+)\]", r"[\1]", b)
            hit = [e for exprs in probes.values() for e in exprs if e == ex or e.endswith(ex.split(".", 1)[-1]) and e not in dead and e == ex]
            dead.add(ex)
            DROPPED.append(ex)
    r = run(f"cd {o_} && {vv} a > run.log 2>&1; tail -3 run.log")
    return r.stdout + r.stderr


def parse_run(out):
    V, C = {}, {}
    for l in (out / "run.log").read_text().splitlines():
        p = l.split()
        if len(p) >= 5 and p[0] == "V":
            V[(int(p[1]), p[2], int(p[3]))] = p[4]
        elif len(p) == 4 and p[0] == "C":
            C[(int(p[1]), p[2])] = p[3]
    return V, C


# ---------------------------------------------------------------- index_map evaluation
def eval_int(expr, env):
    if not re.fullmatch(r"[0-9a-zA-Z_+\-*/%() ]*", expr):
        raise ValueError("characters")
    return eval(expr.replace("//", "//"), {"__builtins__": {}}, dict(env))


def port_value(sig_exprs, index_map, nbytes, env, getter):
    """sig_exprs: list of expanded signals ('a + b' gives several). getter(spec, k) -> hex of element k of spec.
    returns hex string of the port in byte order, or raises."""
    chunks = []
    for spec in sig_exprs:
        dims, nel = spec["dims"], 1
        for x in dims:
            nel *= x
        elems = [getter(spec, k) for k in range(max(nel, 1))]
        chunks.append((spec, elems))
    im = index_map.strip()
    if im == "":
        return "".join("".join(el) for _, el in chunks)
    groups = re.findall(r"\[([^\]]+)\]", im)
    if "".join("[%s]" % g for g in groups) != im.replace(" ", "") and "".join("[%s]" % g for g in groups) != im:
        raise ValueError("index_map form")
    out = []
    for n in range(nbytes):
        e = dict(env); e["n"] = n
        # a + b: the selection runs over the concatenation of the signals; here: each signal alone covers its own bytes
        for spec, elems in chunks:
            pass
        spec, elems = chunks[0]
        if len(chunks) > 1:
            raise ValueError("index_map on 'a + b'")
        dims = [x for x, l in zip(spec["dims"], spec["idx"])]
        free_pos = [k for k, l in enumerate(spec["idx"]) if len(l) > 1]
        dims = [spec["dims"][k] for k in free_pos]
        gi = 0
        flat = 0
        rest = [g for g in groups]
        arr_groups = [g for g in rest if ":" not in g]
        part = [g for g in rest if ":" in g]
        if len(arr_groups) != len(dims) and dims:
            raise ValueError("selection count %d != dims %d" % (len(arr_groups), len(dims)))
        flat = 0
        for g, dsz in zip(arr_groups, dims):
            ix = eval_int(g, e)
            if not (0 <= ix < dsz):
                raise ValueError("index %d out of range %d" % (ix, dsz))
            flat = flat * dsz + ix
        el = elems[flat]
        if part:
            hi_lo = part[0]
            m = re.fullmatch(r"(.+?)\s*-:\s*(\d+)", hi_lo)
            if m:
                hi = eval_int(m.group(1), e); w = int(m.group(2)); lo = hi - w + 1
            else:
                a, b = hi_lo.split(":"); hi = eval_int(a, e); lo = eval_int(b, e)
            bits = len(el) * 4
            v = int(el, 16)
            if lo < 0 or hi >= bits:
                raise ValueError("bit range %d:%d outside %d" % (hi, lo, bits))
            out.append(format((v >> lo) & ((1 << (hi - lo + 1)) - 1), "0%dx" % ((hi - lo + 1 + 3) // 4)))
        else:
            out.append(el)
    return "".join(out)


# ---------------------------------------------------------------- when evaluation
def eval_when(w, ctl, edge):
    expr = re.sub(r"\d+'[dhb]([0-9a-fA-F]+)", lambda m: str(int(m.group(1), 10)), w)
    expr = expr.replace("&&", " and ").replace("||", " or ")
    expr = re.sub(r"!(?!=)", " not ", expr)
    names = set(re.findall(r"[A-Za-z_]\w*", expr)) - {"and", "or", "not"}
    env = {}
    for nm in names:
        base = nm.split(".")[-1]
        v = ctl.get((edge, base))
        if v is None:
            return None
        env[nm] = int(v)
    return bool(eval(expr, {"__builtins__": {}}, env))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--align", default="/code/work/align" if CELL else None, required=not CELL)
    ap.add_argument("--design", default="/code" if CELL else str(MODEL))
    ap.add_argument("--out", default="/opt/s3/out" if CELL else None, required=not CELL)
    ap.add_argument("--image", default="lora-s3xcell:v2-20261111")
    ap.add_argument("--chain", action="store_true", help="for consecutive steps of the schedule: the design's own value of the output of one step and of the input of the next, at the cycles your timeline assigns (no model value)")
    ap.add_argument("--detail", action="store_true", help="one line per step: edges where the model value is found, and the values at the assigned cycles")
    a = ap.parse_args()
    align, design, out = Path(a.align), Path(a.design), Path(a.out)
    if CELL:
        import shutil
        shutil.rmtree(out, ignore_errors=True)
    steps, keyparts = model_steps()
    decl = decls(design)
    # collect ports
    items = []  # (block, direction, arch_port, signal str, index_map, entry or None, instances, latency)
    for f in sorted(align.glob("blk_*.json")):
        if f.is_symlink() or not f.is_file():
            continue
        j = json.loads(f.read_text())
        inst = j.get("instances")
        for d in ("inputs", "outputs"):
            for p in j["ports"][d]:
                r = p.get("rtl") or {}
                if r.get("signal") is not None:
                    items.append((j["name"], d, p["arch_port"], r["signal"], r.get("index_map", ""), None, inst, r.get("latency")))
                for be in p.get("by_entry", []) or []:
                    items.append((j["name"], d, p["arch_port"], be["signal"], be.get("index_map", ""), be["entry"], inst, be.get("latency")))
    # pass 0: scopes of the design (names are resolved by the end of the hierarchical name)
    simulate(design, out / "pass0", a.image, {}, [])
    load_scopes(out / "pass0" / "test.vcd")
    # probes
    probes, specs = {}, {}

    def prep(sig, env):
        parts = [s for s in sig.split("+")]
        if not sig.strip():
            return None, "empty signal"
        res = []
        for s in parts:
            sp, err = expand_signal(s, decl, env)
            if err:
                return None, err
            pid = "s%d" % len(probes)
            exprs = []
            for combo in itertools.product(*sp["idx"]) if sp["idx"] else [()]:
                exprs.append(sp["path"] + "".join("[%d]" % c for c in combo))
            key = (sp["path"], tuple(map(tuple, sp["idx"])))
            if key not in specs:
                probes[pid] = exprs; specs[key] = pid
            sp["pid"] = specs[key]
            res.append(sp)
        return res, None
    prepared = {}
    errors = []
    for it in items:
        blk, d, port, sig, im, entry, inst, lat = it
        var = inst["var"] if inst else None
        envs = [{}] if not (var and re.search(r"\b%s\b" % var, sig + im)) else [{var: v} for v in range(inst["count"])]
        lst = []
        for env in envs:
            sp, err = prep(sig, env)
            if err:
                errors.append({"block": blk, "port": port, "entry": entry, "problem": err}); lst = None; break
            lst.append((env, sp))
        prepared[(blk, d, port, sig, im, entry)] = lst
    # signals that must exist
    ctl = ["round_ff", "key_done", "i_start", "o_done", "key_exp_done", "i_update_key"]
    # control values come from the top of the decrypt module
    log = simulate(design, out, a.image, probes, ctl)
    V, C = parse_run(out)
    comp = (out / "comp.log").read_text()
    bad_sig = sorted(set(re.findall(r"(?:Unable to bind wire/reg/memory|Unknown module type|error:.*)", comp)))[:10]
    # timeline
    tl = json.loads((align / "timeline.json").read_text()) if ((align / "timeline.json").is_file() and not (align / "timeline.json").is_symlink()) else {"entries": []}

    def assigned(step):
        """edges at which the timeline assigns the step (Qwen's alignment), via its when conditions."""
        res = []
        for e in EDGES:
            for en in tl["entries"]:
                try:
                    h = eval_when(en["when"], C, e)
                except Exception:
                    h = None
                if not h:
                    continue
                for sg in en.get("segments", []):
                    env = {"round_ff": int(C.get((e, "round_ff"), 0)) if (e, "round_ff") in C else 0}
                    try:
                        fs = int(eval_int(str(sg["from_step"]), env)); ts = int(eval_int(str(sg["to_step"]), env))
                    except Exception:
                        continue
                    if fs <= step["n"] <= ts:
                        res.append((e, en["id"]))
        return res

    def getter_for(spec):
        def g(sp, k):
            return V[(spec_edge[0], sp["pid"], k)]
        return g
    spec_edge = [0]
    nbytes = {}
    for f in sorted(MAP.glob("blk_*.json")):
        j = json.loads(f.read_text())
        for d in ("inputs", "outputs"):
            for p in j["ports"][d]:
                nbytes[(j["name"], p["name"])] = p["layout"]["count"] if "layout" in p else p["width"] // 8
    report = []
    ksteps_by_block = {}
    for (i, parts) in keyparts:
        for b, (ins, outs) in parts.items():
            ksteps_by_block.setdefault(b, []).append({"inst": i, "in": ins, "out": outs})
    for key, lst in prepared.items():
        blk, d, port, sig, im, entry = key
        row = {"block": blk, "dir": d, "port": port, "signal": sig, "index_map": im, "entry": entry}
        if lst is None:
            row["status"] = "signal form not evaluable"; report.append(row); continue
        nb = nbytes.get((blk, port))
        want = []
        if blk in ksteps_by_block:
            for s in ksteps_by_block[blk]:
                want.append((s["inst"], None, (s["in"] if d == "inputs" else s["out"]).get(port)))
        else:
            for s in steps:
                if s["block"] == blk:
                    want.append((None, s, (s["in"] if d == "inputs" else s["out"]).get(port)))
        if not want or any(w[2] is None for w in want):
            row["status"] = "no model value for this port (not checked)"; report.append(row); continue
        per = []
        err = None
        for (inst_i, stp, val) in want:
            # the evaluation environment: instance value if the variable is used
            ev = None
            for env, sp in lst:
                if not env or list(env.values())[0] == inst_i:
                    ev = (env, sp)
                    break
            if ev is None:
                ev = lst[0]
            env, sp = ev
            hits = []
            for e in EDGES:
                spec_edge[0] = e
                try:
                    got = port_value(sp, im, nb, {**env, "round_ff": int(C.get((e, "round_ff"), 0))}, lambda s, k: V[(e, s["pid"], k)])
                except KeyError:
                    got = None
                except Exception as ex:
                    err = str(ex); got = None
                    continue
                if got is not None and got == val:
                    hits.append(e)
            asg = assigned(stp) if stp else []
            ok_asg = None
            if stp and asg:
                ok_asg = []
                for (e, eid) in asg:
                    spec_edge[0] = e
                    try:
                        got = port_value(sp, im, nb, {**env, "round_ff": int(C.get((e, "round_ff"), 0))}, lambda s, k: V[(e, s["pid"], k)])
                    except Exception:
                        got = None
                    ok_asg.append({"edge": e, "entry": eid, "equal": got == val, "model": val, "design": got})
            per.append({"eval_errors": err, "inst": inst_i, "step": stp["n"] if stp else None, "round": stp["round"] if stp else None, "position": stp["position"] if stp else None,
                        "anywhere_edges": hits, "assigned": ok_asg})
        row["error"] = err if err and not any(x["anywhere_edges"] for x in per) else None
        row["results"] = per
        report.append(row)
    chain = []
    if a.chain:
        def design_val(blk, d, port, e):
            ks = [k for k in prepared if k[0] == blk and k[1] == d and k[2] == port and prepared[k]]
            if not ks:
                return None, "no usable mapping for %s %s" % (blk, port)
            ks.sort(key=lambda k: (k[5] is not None, str(k[5])))
            k = ks[0]
            env, sp = prepared[k][0]
            nb = nbytes.get((blk, port))
            try:
                return port_value(sp, k[4], nb, {**env, "round_ff": int(C.get((e, "round_ff"), 0))}, lambda s_, kk: V[(e, s_["pid"], kk)]), None
            except Exception as ex:
                return None, str(ex)
        ports = lambda b, d: ({"load": ("in", "state"), "store": ("state", "out")}.get(b, ("state_in", "state_out")))
        for A, B in zip(steps[1:], steps[2:]):
            if A["block"] == "key_expansion" or B["block"] == "key_expansion":
                continue
            ea, eb = assigned(A), assigned(B)
            row = {"from": "step %d %s %s%s" % (A["n"], A["block"], A["position"], "" if A["round"] is None else " r%s" % A["round"]), "to": "step %d %s %s%s" % (B["n"], B["block"], B["position"], "" if B["round"] is None else " r%s" % B["round"])}
            if not ea or not eb:
                row["note"] = "a step has no assigned cycle: %s" % ("first" if not ea else "second"); chain.append(row); continue
            e1, e2 = ea[0][0], eb[0][0]
            ov, er1 = design_val(A["block"], "outputs", ports(A["block"], 0)[1], e1)
            iv, er2 = design_val(B["block"], "inputs", ports(B["block"], 0)[0], e2)
            row.update({"out_edge": e1, "in_edge": e2, "out_value": ov, "in_value": iv, "error": er1 or er2})
            if ov is not None and iv is not None:
                row["equal"] = ov == iv
                hits = []
                for e in EDGES:
                    g, _ = design_val(B["block"], "inputs", ports(B["block"], 0)[0], e)
                    if g is not None and g == ov:
                        hits.append(e)
                row["input_equals_output_at_edges"] = hits
            chain.append(row)
        sh2 = lambda v: "-" if v is None else (v if len(v) <= 16 else v[:8] + ".." + v[-8:])
        print("\nchain (design values only; output of a step at its assigned edge, input of the next step at its assigned edge)")
        for r in chain:
            if "note" in r or r.get("error"):
                print("  %s -> %s: %s" % (r["from"], r["to"], r.get("note") or r["error"])); continue
            print("  %s (edge %d) -> %s (edge %d): out %s, in %s: %s; input of the next step equals the output at edges %s" % (r["from"], r["out_edge"], r["to"], r["in_edge"], sh2(r["out_value"]), sh2(r["in_value"]), "equal" if r.get("equal") else "differs", r.get("input_equals_output_at_edges") or "none"))
    (out / "report.json").write_text(json.dumps({"chain": chain, "errors": errors, "dropped_probes": DROPPED, "compile_problems": bad_sig, "sim_tail": log, "rows": report}, indent=1))
    # readable summary
    for r in report:
        if r.get("status") or r.get("error"):
            print("%-20s %-8s %-9s %s %s" % (r["block"], r["dir"][:3], r["port"], r.get("status", ""), r.get("error", "")))
            continue
        res = r["results"]
        found = sum(1 for x in res if x["anywhere_edges"])
        asg = [x for x in res if x["assigned"]]
        asg_eq = sum(1 for x in asg for y in x["assigned"] if y["equal"])
        asg_all = sum(len(x["assigned"]) for x in asg)
        print("%-20s %-3s %-10s entry=%-9s anywhere %d/%d steps; assigned-cycle equal %d/%d" % (r["block"], r["dir"][:3], r["port"], r["entry"], found, len(res), asg_eq, asg_all))
    if a.detail:
        sh = lambda v: "-" if v is None else (v if len(v) <= 16 else v[:8] + ".." + v[-8:])
        for r in report:
            if r.get("status") or r.get("error"):
                continue
            print("\n%s %s %s  signal=%s index_map=%s entry=%s" % (r["block"], r["dir"], r["port"], r["signal"], r["index_map"], r["entry"]))
            for x in r["results"]:
                lab = ("inst %s" % x["inst"]) if x["inst"] is not None else "step %s %s r%s" % (x["step"], x["position"], x["round"])
                line = "  %-22s model value found at edges %s" % (lab, x["anywhere_edges"] or "none")
                if x["assigned"]:
                    line += " | assigned: " + "; ".join("edge %d (%s): %s" % (y["edge"], y["entry"], "equal" if y["equal"] else "differs (design " + sh(y["design"]) + ", model " + sh(y["model"]) + ")") for y in x["assigned"])
                print(line)
    if errors or bad_sig:
        print("problems:", errors[:5], bad_sig)


if __name__ == "__main__":
    main()
