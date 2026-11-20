"""Run one order in a cell: label file, order clock, ledger summary, the agent, monitoring (45 minute limit, 15 minutes
without a tool call), and the files back to the host."""
import glob
import hashlib
import json
import os
import threading
import time
from pathlib import Path

from . import cell as cellmod
from . import map_events

ROOT = Path(__file__).resolve().parent.parent
sys_path = str(ROOT / "orders")


NETWORK_POLICY = "open"      # label of a run whose container egress is open (fake agents); Qwen runs set opts["network_policy"] = "proxy-only" (REVIEW_LOG #28: egress only to the recording proxy); a run is excluded from evaluation when orch.netuse finds network use
FLOW_VERSION = "v5.4"      # v4 = the baseline of stage 2/3 and the first S2/S4 ladder runs; v4.1 = image lock + probe names + spec_decode label (environment/tool); v5 = P1 trial wording + rtl trial none (order text); v5.1 = rtl find mark --status confirmed (evidenced by a run), apply sets fixed, probe lists the signals of a scope, edit_outside_finding is recorded (REVIEW_LOG #32, #33); v5.2 = testbench mode: the repro takes a run of the provided testbench when it reports failures on the design, otherwise the agent writes one; H2 notes by mode (REVIEW_LOG #39, #40); v5.3 = rtl probe takes elements of unpacked arrays (hierarchical sampling) and states array facts in its refusals; the ledger summary and rtl status list the trials with their results (REVIEW_LOG #53, #54); v5.4 = rtl probe takes bits of a vector (name[hi:lo], name[n]); rtl trial --with Tm stacks the edits of an improved or same trial Tm on the new edits (REVIEW_LOG #58)


def tree_hash(paths):
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(str(p.name).encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def idle_exceeded(now, started, last_tool, idle_limit, last_progress=None):
    """True when the time since the last sign of work is above the limit. Signs of work: a completed tool call, the start of the order, and (flow v4)
    a piece of a generation that the model is still producing (the recording proxy writes progress.json while an answer is being generated)."""
    return now - max(started, last_tool or 0, last_progress or 0) > idle_limit


class ProxyReader:
    """Follows the recording proxy files and tells when the last tool call was seen and how many requests there were."""
    def __init__(self, proxy_dir):
        self.dir, self.offsets, self.last_tool, self.requests = Path(proxy_dir) if proxy_dir else None, {}, None, 0
        self.last_total = 0     # tokens of the last recorded answer (prompt + completion): the size of the next prompt
        self.resample_seconds, self.slipped_run = 0.0, 0     # time spent asking again (not the agent's time); slipped answers delivered in a row
        if self.dir:        # start at the end of what is already recorded: only this order's requests are counted
            for f in glob.glob(str(self.dir / "requests-*.jsonl")):
                self.offsets[f] = Path(f).stat().st_size

    def progress(self):
        """Time of the last piece received from the model for a generation that is in flight now (the heartbeat is fresh), else None."""
        try:
            p = json.loads((self.dir / "progress.json").read_text())
        except (OSError, ValueError):
            return None
        return p["t_last_chunk"] if time.time() - p["t"] < 10 else None

    def poll(self):
        if not self.dir:
            return
        for f in sorted(glob.glob(str(self.dir / "requests-*.jsonl"))):
            with open(f, "rb") as fh:
                fh.seek(self.offsets.get(f, 0))
                data = fh.read()
            end = data.rfind(b"\n") + 1
            self.offsets[f] = self.offsets.get(f, 0) + end
            for line in data[:end].splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                self.requests += 1
                self.resample_seconds += (r.get("guard") or {}).get("resample_seconds", 0)
                self.slipped_run = self.slipped_run + 1 if r.get("slipped_tool_call") else 0
                self.last_total = ((r.get("response") or {}).get("usage") or {}).get("total_tokens") or self.last_total
                calls = r["response"]["tool_calls"]
                # only calls the agent can execute count as activity: a malformed call is not a tool call
                if calls and not any(map_events.malformed(c) for c in calls):
                    self.last_tool = time.time()


def body_hash(order):
    """Hash of the text of the order body that render uses (the variant file when ORDER_VARIANT_<order> is set): lets a control arm be checked against the body of earlier runs (REVIEW_LOG #75)."""
    v = os.environ.get(f"ORDER_VARIANT_{order}", "")
    return hashlib.sha256((ROOT / "orders" / (f"{order}_{v}.md" if v else f"{order}.md")).read_bytes()).hexdigest()[:16]


def make_labels(cell, order, rnd, opts, decision, seq=0, attempt=1):
    p = cell.problem
    tool_files = list((ROOT / "tool" / "rtlreal").glob("*.py")) + [ROOT / "tool" / "docker" / "Dockerfile"]
    order_files = list((ROOT / "orders").glob("*.md"))
    lab = {"problem": p["id"], "family": opts.get("family"), "leak_level": opts.get("leak_level"), "prompt_redacted": p["redacted"],
           "task_variant": "converted" if p["converted"] else "agentic", "round": rnd, "order": order, "seq": seq, "attempt": attempt, "flow_version": opts.get("flow_version", FLOW_VERSION), "network": opts.get("network_policy", NETWORK_POLICY), "testbench_mode": getattr(cell, "tb_mode", None),
           "rtl_tool_hash": tree_hash(tool_files), "order_template_hash": tree_hash(order_files), "image": cell.image,
           "reasoning_effort": opts.get("reasoning_effort", "medium"), "intervention_level": "L0",
           "task_md_hash": hashlib.sha256(p["task"].encode()).hexdigest()[:16], "spec_hash": hashlib.sha256(p["spec"].encode()).hexdigest()[:16],
           "sampling_arm": opts.get("sampling_arm", "default"), "proxy_guard_hash": tree_hash([ROOT / "proxy" / "record_proxy.py"]), "decision_reason": decision.get("reason"), "order_variant": os.environ.get(f"ORDER_VARIANT_{order}", ""), "order_body_hash": body_hash(order)}
    cv = os.environ.get("COMMON_VARIANT", "")       # REVIEW_LOG #106: the common header variant and the skill installed in the cell
    lab["common_variant"] = cv
    lab["common_hash"] = hashlib.sha256((ROOT / "orders" / (f"common_{cv}.md" if cv else "common.md")).read_bytes()).hexdigest()[:16]
    lab["skill_dir"] = opts.get("skill_dir")
    return lab


def run_order(cell, order, decision, seq, opts):
    rnd = decision["round"]
    run_dir = cell.run_dir
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    if opts.get("order_text"):     # REVIEW_LOG #119: an order outside the H1-H6 flow (the M test): fixed text, no ledger
        text = opts["order_text"]
    else:
        import sys
        sys.path.insert(0, sys_path)
        import render
        cell.ctl("setorder", order)
        text = render.render(order, rnd, cell.ctl("summary"), converted=cell.problem["converted"], files=list(cell.problem["files"]), tb_mode=getattr(cell, "tb_mode", None))
    cell.put_text(text, "/tmp/agent/order.txt")
    (run_dir / "logs" / f"{seq:02d}-{order}-order.txt").write_text(text)
    attempt = 1 + sum(1 for f in (run_dir / "logs").glob(f"*-{order}-result.json"))
    labels = opts["labels"] if opts.get("order_text") else make_labels(cell, order, rnd, opts, decision, seq, attempt)
    (run_dir / "labels.json").write_text(json.dumps(labels))
    agent = opts["agent"]
    if agent.startswith("fake:"):
        script = Path(agent[5:]) / f"{order}.sh"
        alt = Path(agent[5:]) / f"{order}_r{rnd}.sh"
        script = alt if alt.exists() else script
        cell.put_text(script.read_text(), "/tmp/agent/fake_agent.sh")
        argv, env = ["sh", "/tmp/agent/fake_agent.sh"], {}
    else:
        argv = ["python3", "/tmp/agent/run_agent.py"]
        env = {"QWEN_MODEL": opts["model"], "OPENAI_BASE_URL": opts["base_url"], "QWEN_REQUEST_TIMEOUT_MS": str(opts.get("request_timeout_ms", 1800000))}
        if opts.get("context_window"):   # REVIEW_LOG #89: tells Qwen Code a smaller window so that its own compaction starts before the server runs out of GPU memory
            env["QWEN_CONTEXT_WINDOW"] = str(opts["context_window"])
    reader = ProxyReader(opts.get("proxy_dir"))
    out_path = run_dir / "logs" / f"{seq:02d}-{order}.stdout"
    err_path = run_dir / "logs" / f"{seq:02d}-{order}.stderr"
    started = time.time()
    proc = cell.popen_agent(argv, env)

    def drain(stream, path):
        with open(path, "w") as f:
            for line in stream:
                f.write(line)
                f.flush()
    threads = [threading.Thread(target=drain, args=(proc.stdout, out_path), daemon=True),
               threading.Thread(target=drain, args=(proc.stderr, err_path), daemon=True)]
    for t in threads:
        t.start()
    reason = "finished"
    while proc.poll() is None:
        time.sleep(opts.get("poll", 2))
        reader.poll()
        if opts.get("relay"):
            opts["relay"].poll()
        now = time.time() - reader.resample_seconds     # time the guard spent asking again does not count
        if now - started > opts["order_timeout"]:
            reason = "timeout"
        elif reader.dir and idle_exceeded(now, started, reader.last_tool, opts["idle_timeout"], reader.progress() if opts.get("progress_idle", True) else None):
            reason = "idle"
        elif opts.get("context_limit") and reader.last_total > opts["context_limit"]:
            reason = "context"     # the conversation is larger than the backend can hold in memory without stalling: the order ends here and is continued in a new cell
        elif reader.slipped_run >= 3:
            reason = "slipped"     # stop rule: three delivered answers in a row are slipped tool calls although asked again
        elif opts.get("done_check") and opts["done_check"](reader):
            reason = opts.get("done_reason", "done")     # REVIEW_LOG #119: the order's deliverable is complete (M test: end-on-write)
        if reason != "finished":
            cell.kill_agent()
            proc.wait(timeout=60)
            break
    for t in threads:
        t.join(timeout=10)
    proc.stdout.close()
    proc.stderr.close()
    reader.poll()
    if reason == "finished" and proc.returncode != 0:
        reason = "error"
    after = run_dir / f"after-{seq:02d}-{order}"
    cell.pull(after)
    res = {"seq": seq, "order": order, "round": rnd, "reason": reason, "exit_code": proc.returncode, "seconds": round(time.time() - started, 1),
           "requests": reader.requests, "stdout": str(out_path)}
    (run_dir / "logs" / f"{seq:02d}-{order}-result.json").write_text(json.dumps(res))
    return res
