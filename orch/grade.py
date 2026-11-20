"""P2 grader: run the hidden cocotb harness of a problem on a design directory. The harness stays on this side; Qwen never sees it or its result.

usage: python3 -m orch.grade PROBLEM_ID DESIGN_DIR [--image lora-rtl:dev]
DESIGN_DIR holds the rtl files (the content of /code/rtl). Prints one JSON line: {"problem", "passed", "tests", "output_tail", "seconds"}.
The design is copied to /code/rtl of a scratch container, the harness 'src/' files to /src, the environment is read from src/.env."""
import argparse
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

from . import dataset


def harness_of(pid):
    for path in (dataset.AGENTIC, dataset.NONAGENTIC):
        with open(path) as f:
            for line in f:
                if f'"id": "{pid}"' not in line[:300]:
                    continue
                r = json.loads(line)
                if r["id"] == pid:
                    h = r.get("harness") or {}
                    return h.get("files", h) if isinstance(h.get("files", h), dict) else h
    raise KeyError(pid)


def grade(pid, design_dir, image="lora-rtl:dev", timeout=300):
    h = harness_of(pid)
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for name, text in h.items():
            if name.startswith("src/"):
                p = td / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text)
        env = {}
        for line in (h.get("src/.env") or "").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
        name = f"lora_grade_{int(t0 * 1000) % 10**8}"
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "run", "-d", "--name", name, "--entrypoint", "sleep", image, "infinity"], check=True, capture_output=True)
        try:
            subprocess.run(["docker", "exec", "-u", "root", name, "rm", "-rf", "/code", "/src"], check=True, capture_output=True)
            subprocess.run(["docker", "exec", "-u", "root", name, "mkdir", "-p", "/code/rundir"], check=True, capture_output=True)
            subprocess.run(["docker", "cp", str(Path(design_dir)), f"{name}:/code/rtl"], check=True, capture_output=True)
            subprocess.run(["docker", "cp", str(td / "src"), f"{name}:/src"], check=True, capture_output=True)
            envargs = [x for k, v in env.items() for x in ("-e", f"{k}={v}")]
            cmd = ["docker", "exec", "-u", "root", "-w", "/code/rundir"] + envargs + [name, "sh", "-c", "pytest -s -o cache_dir=/tmp/.pytest_cache /src/test_runner.py -v 2>&1 | tail -80"]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                out = r.stdout + r.stderr
            except subprocess.TimeoutExpired:
                out = "TIMEOUT"
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    m = re.search(r"(\d+) passed", out)
    f = re.search(r"(\d+) failed", out)
    e = re.search(r"(\d+) error", out)
    passed = bool(m) and not f and not e and "TIMEOUT" not in out
    return {"problem": pid, "passed": passed, "tests": {"passed": int(m.group(1)) if m else 0, "failed": int(f.group(1)) if f else 0, "errors": int(e.group(1)) if e else 0},
            "output_tail": out[-6000:], "seconds": round(time.time() - t0, 1)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("problem")
    ap.add_argument("design_dir")
    ap.add_argument("--image", default="lora-rtl:dev")
    a = ap.parse_args()
    print(json.dumps(grade(a.problem, a.design_dir, a.image)))
