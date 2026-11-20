"""Small pieces the flow needs around an order: the recording proxy in front of the model backend, the end-of-order gate, and facts read from the proxy records.
(Taken unchanged from the modules map_stage2_series, mspec_series, run_problem and map_cell of the project cvdp_qwen_lora_traj.)"""


import glob
import hashlib
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


PORT = 11500                                   # the proxy; the cell may reach only this port of the host
ARM = "d2"
MODEL = "qwen3.8:27b-mxfp8-v3-ctx262144"        # the name the agent asks for; the proxy sends every request to the model of the arm
MAX_TOKENS = 150000
ALLOW = ["POST /v1/chat/completions", "GET /v1/models"]
BACKEND = "127.0.0.1:11435"                     # the model backend (Ollama)
BACKEND_MODEL = "qwen3.8-nopen-exp-dflash2"
# the sampling arm of all gflow rounds: presence penalty 1.0, no repeat penalty; the output cap is replaced by MAX_TOKENS when the proxy is started
ARM_ARGS = {"d2": ["--target", BACKEND, "--model-override", BACKEND_MODEL, "--inject", '{"max_tokens": 32000, "presence_penalty": 1.0}',
                   "--backend-label", "Ollama 0.40.15, port 11435, with the DFlash2 draft model"]}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def arm_args(arm, extra):
    """The proxy arguments of a sampling arm, with extra request fields merged into its --inject (REVIEW_LOG #114)."""
    args = list(ARM_ARGS[arm])
    if not extra:
        return args
    if "--inject" in args:
        i = args.index("--inject")
        args[i + 1] = json.dumps({**json.loads(args[i + 1]), **json.loads(extra)})
    else:
        args += ["--inject", extra]
    return args


def start_proxy(rdir, target=None, partials=True, extra=()):
    if not free(PORT):
        sys.exit(f"port {PORT} is in use")
    pdir = rdir / "proxy"
    (rdir / "labels.json").write_text("{}")
    cmd = [sys.executable, str(ROOT / "proxy" / "record_proxy.py"), "--out", str(pdir), "--port", str(PORT), "--label-file", str(rdir / "labels.json"), "--keepalive", "5"]
    if partials:
        cmd.append("--save-partials")
    cmd += arm_args(ARM, json.dumps({"max_tokens": MAX_TOKENS}))
    cmd += list(extra)
    if target:
        cmd += ["--target", target]        # the dry runs: a scripted fake model instead of Ollama (argparse: the last --target wins)
    for a in ALLOW:
        cmd += ["--allow", a]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    return p, pdir


class DoneGate:
    """End of the order: /code/work/DONE exists and no request is in flight (the proxy's counter), as DoneMarker of M5C; nothing else is saved."""
    def __init__(self, cell, pdir):
        self.cell, self.pdir, self.t_done, self.inflight_at_done = cell, Path(pdir), None, None

    def __call__(self, reader):
        try:
            inf = json.loads((self.pdir / "inflight.json").read_text())["inflight"]
        except (OSError, ValueError, KeyError):
            inf = None
        r = subprocess.run(["docker", "exec", self.cell.name, "sh", "-c", "[ -e /code/work/DONE ] && echo yes || echo no"], capture_output=True, text=True).stdout.strip()
        if r == "yes" and self.t_done is None:
            self.t_done = time.time()
        if r == "yes" and inf == 0:
            self.inflight_at_done = inf
            return True
        return False


def requests(pdir):
    return [json.loads(l) for f in sorted(glob.glob(str(Path(pdir) / "requests-*.jsonl"))) for l in open(f)]


def facts(pdir, t_end=None):
    rq = requests(pdir)
    tools = sorted({tuple(sorted(t["function"]["name"] for t in (x.get("request") or {}).get("tools") or [])) for x in rq})
    calls = [((tc.get("function") or {}).get("name")) for x in rq for tc in (x.get("response") or {}).get("tool_calls") or []]
    out = {"requests": len(rq), "tool_sets": tools, "shell_offered": any("run_shell_command" in t for t in tools), "calls": calls,
           "status": sorted({x.get("status") for x in rq}, key=str), "ollama_version": sorted({str(x.get("ollama_version")) for x in rq}),
           "reasoning_chars": sum(len((x.get("response") or {}).get("reasoning") or "") for x in rq),
           "longest_generation_s": round(max([x.get("t_total_s") or 0 for x in rq] or [0])),
           "max_prompt_tokens": max([((x.get("response") or {}).get("usage") or {}).get("prompt_tokens") or 0 for x in rq] or [0])}
    if t_end is not None:     # requests that started after the order was ended (should be 0)
        import datetime
        out["requests_after_end"] = sum(1 for x in rq if datetime.datetime.fromisoformat(x["t_request"]).timestamp() > t_end)
    return out
