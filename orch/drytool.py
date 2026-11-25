"""Dry run of an order by a stand-in for the agent (a person or another model session), outside a cell of the flow.

  python3 -m orch.drytool prep PROBLEM STEP NAME [--carry NAME] [--ref NAME] [--timed NAME] [--sim RUN_TAG] [--fact TEXT]
      makes runs/dry_<PROBLEM>/<NAME>/: code/ (what the cell of this step holds: /code), order.md, skills/, run.sh
      (--carry: /code/work starts with the files of that earlier dry order; --ref: the dry order that wrote the reference model;
       --timed: the dry order that wrote the timed model; scope, report and notes come from the problem file)
  python3 -m orch.drytool pack PROBLEM NAME
      packs code/work as runs/dry_<PROBLEM>/<NAME>/after-01-DRY/work_all.tar and prints the entry for a GFLOW_REPLAY file,
      so that the driver can run its host checks on these files (GFLOW_REPLAY_ONLY=1: the model is never called)
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import gflow, gflow_auto as ga

RUN = '''#!/bin/sh
# usage: ./run.sh 'shell command'   -- runs the command inside the cell (code/ of this folder is /code; only /code/work can be written; no network, no simulator)
D="$(cd "$(dirname "$0")" && pwd)"
RO=""
for p in spec model; do [ -d "$D/code/work/$p" ] && RO="$RO -v $D/code/work/$p:/code/work/$p:ro"; done
exec docker run --rm --network none --user root -e PYTHONDONTWRITEBYTECODE=1 -v "$D/code:/code:ro" -v "$D/code/work:/code/work" $RO -w /code --entrypoint sh IMAGE -c "$1"
'''


def root(problem):
    return gflow.ROOT / "runs" / f"dry_{problem}"


def prep(a):
    cfg = json.loads((gflow.ROOT / "data" / "problems" / f"{a.problem}.json").read_text())
    pid = cfg["pid"]
    if not (gflow.pdir_of(pid) / "rtl").exists():
        gflow.prep(pid)
    d = root(a.problem) / a.name
    if d.exists():
        sys.exit(f"{d} exists")
    kw = {}
    plan = {n: (s, k) for s, n, k in cfg.get("lower_units", []) + cfg.get("data_path", []) + cfg.get("top", [])}
    if a.name in plan:
        kw = dict(plan[a.name][1])
    else:                                        # names of dry runs follow docs/NAMES.md (dry-PROBLEM-STEP-NN): the order's settings are those of its step
        same = [k for s, k in plan.values() if s == a.step]
        if len(same) == 1:
            kw = dict(same[0])
    if a.step == "B":
        sc = ga.b_scopes(pid)
        import re
        mo = re.search(r"(?i)(?:^b|-B)(\d+)(?:p\d+)?(?:-|r|$)", a.name)     # b2 (an order of a round) or dry-aes0005-B2-01 (docs/NAMES.md)
        n = int(mo.group(1)) if mo else 1
        kw = {"scope": sc[n - 1][0], "report": sc[n - 1][1]}
        pm = re.search(r"(?i)B\d+(p\d+)", a.name)                # a part of the scope (problem file "b_parts")
        if pm:
            kw["scope"] = dict(cfg.get("b_parts", {}).get(str(n), []))[pm.group(1).lower()]
        a.fact = a.fact or ga.SIM_FACT
    spec = sorted((gflow.D / cfg["spec_dir"]).iterdir()) if cfg.get("spec_dir") and a.step not in ("M", "A", "A2") else None
    if spec and a.timed:
        tdir = root(a.problem) / a.timed / "code" / "work"
        if not tdir.exists():                    # a run of the flow
            tdir = gflow.run_dir(pid, a.timed) / "view"
        spec += [f for f in tdir.glob("*.py") if f.name != "timed_check.py"]
    rdir = root(a.problem) / a.ref / "code" / "work" if a.ref else None
    if rdir is not None and not rdir.exists():
        rdir = gflow.run_dir(pid, a.ref) / "view"
    ref = [rdir / n for n in ("ref_model.py", "ref_model_notes.md")] if a.ref else None
    sim_tag = a.sim
    if a.base:
        gflow.BASE_RECORD = a.base
    inp, order = gflow.compose(pid, a.step, fact=a.fact or "", sim=sim_tag, ref=ref, spec=spec, **kw)
    (d / "code" / "work").mkdir(parents=True)
    if a.carry:
        src = root(a.problem) / a.carry / "code" / "work"
        if not src.exists():                     # a run of the flow: its files after the order
            src = gflow.run_dir(pid, a.carry) / "view"
        for f in sorted(src.iterdir()):
            if f.name in ("DONE", "spec", "model", "__pycache__", "stimulus.json", "rtl_fixed") or f.name.startswith(".") or f.name.startswith("sim_check"):
                continue
            (shutil.copytree if f.is_dir() else shutil.copy)(f, d / "code" / "work" / f.name)
    for dest, (srcf, _, _) in inp.items():
        t = d / dest.lstrip("/")
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(srcf, t)
    (d / "order.md").write_text(order)
    for n in gflow.STEPS[a.step][1]:
        (d / "skills" / n).mkdir(parents=True)
        shutil.copy(gflow.SK / n / "SKILL.md", d / "skills" / n / "SKILL.md")
    (d / "run.sh").write_text(RUN.replace("IMAGE", gflow.IMAGE))
    (d / "run.sh").chmod(0o755)
    print(d)


def pack(a):
    d = root(a.problem) / a.name
    out = d / "after-01-DRY"
    out.mkdir(exist_ok=True)
    subprocess.run(["tar", "-cf", str(out / "work_all.tar"), "--exclude", "./spec", "--exclude", "./model", "--exclude", "__pycache__", "-C", str(d / "code" / "work"), "."], check=True)
    print(json.dumps({a.name: str(d)}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("prep", "pack"))
    ap.add_argument("problem")
    ap.add_argument("rest", nargs="+")
    ap.add_argument("--carry"); ap.add_argument("--ref"); ap.add_argument("--timed"); ap.add_argument("--sim"); ap.add_argument("--fact"); ap.add_argument("--base", help="base_record.json written by the host (gflow.base_record) for the orders that get it")
    a = ap.parse_args()
    if a.cmd == "prep":
        a.step, a.name = a.rest
        prep(a)
    else:
        a.name = a.rest[0]
        pack(a)
