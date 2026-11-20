"""Load the files that Qwen may see for a problem. The hidden harness is never read here.

Only paths under rtl/, verif/, docs/ are accepted from the dataset context; anything else stops the run.
A directory problem (dir:PATH with task.md, spec.md, rtl/, verif/) is used for tests."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASETS = Path(os.environ.get("CVDP_DATASETS") or ROOT / "datasets")   # the CVDP .jsonl files; not in git (a link or a copy here, or the environment variable CVDP_DATASETS)
AGENTIC = DATASETS / "cvdp_v1.1.0_agentic_code_generation_no_commercial.jsonl"
NONAGENTIC = DATASETS / "cvdp_v1.1.0_nonagentic_code_generation_no_commercial.jsonl"
ALLOWED_TOP = ("rtl", "verif", "docs")


def _check_paths(paths):
    for p in paths:
        parts = Path(p).parts
        if not parts or parts[0] not in ALLOWED_TOP or ".." in parts or Path(p).is_absolute():
            raise ValueError(f"path outside rtl/verif/docs in the dataset context: {p}")


def load(pid, arch_root=None):
    arch_root = Path(arch_root) if arch_root else ROOT / "arch"
    if pid.startswith("dir:"):
        d = Path(pid[4:])
        files = {str(p.relative_to(d)): p.read_text() for top in ALLOWED_TOP for p in (d / top).rglob("*") if p.is_file()}
        _check_paths(files)
        return {"id": d.name, "task": (d / "task.md").read_text(), "spec": (d / "spec.md").read_text(), "files": files,
                "converted": not any(k.startswith("verif/") for k in files), "redacted": False, "source": "dir"}
    for path, kind in ((AGENTIC, "agentic"), (NONAGENTIC, "nonagentic")):
        with open(path) as f:
            for line in f:
                if f'"id": "{pid}"' not in line[:300]:
                    continue
                r = json.loads(line)
                if r["id"] != pid:
                    continue
                if kind == "agentic":
                    prompt, files = r["prompt"], dict(r["context"])
                else:
                    prompt, files = r["input"]["prompt"], dict(r["input"].get("context") or {})
                _check_paths(files)
                red = arch_root / pid / "redacted" / "task.md"
                spec = arch_root / pid / "spec.md"
                if not spec.exists():
                    raise FileNotFoundError(f"no spec.md for {pid}")
                return {"id": pid, "task": red.read_text() if red.exists() else prompt, "spec": spec.read_text(), "files": files,
                        "converted": kind == "nonagentic", "redacted": red.exists(), "source": kind}
    raise KeyError(pid)
