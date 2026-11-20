"""Offline: label each recorded request with what the rtl tool answered to its tool calls.

For request k, the tool calls in its RESPONSE are answered in request k+1: its messages contain role=tool entries whose
tool_call_id equals the call id. The answer text carries the tool's markers `[ev N <result>]`. Joined with events.jsonl
this gives, per request: event ids, results, rule codes, reason classes. A call whose answer carries no marker (cut by a
pipe) is labelled `unmapped`. A refusal for a syntax error is not a violation (reason class syntax).

usage: python3 -m orch.map_events RUN_DIR      (reads proxy/requests-*.jsonl and final/state/events.jsonl)
"""
import glob
import json
import re
import sys
from pathlib import Path

EV = re.compile(r"\[ev (\d+) ([^\]]+)\]")
RTL_CALL = re.compile(r"(^|[\s;&|(])rtl\s")
VALID_TOOLS = {"run_shell_command", "read_file", "write_file", "edit", "glob", "grep_search"}


def malformed(call):
    """A call the agent's own tool layer cannot execute: unknown tool name, unparsable arguments, or no `command` for the shell."""
    n = call["function"]["name"]
    try:
        a = json.loads(call["function"]["arguments"])
    except ValueError:
        return True
    if n not in VALID_TOOLS:
        return True
    return n == "run_shell_command" and not (isinstance(a, dict) and "command" in a)


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(p.get("text", "") for p in content if isinstance(p, dict))


def load_requests(proxy_dir):
    recs = []
    for f in sorted(glob.glob(str(Path(proxy_dir) / "requests-*.jsonl"))):
        with open(f) as fh:
            recs += [json.loads(l) for l in fh if l.strip()]
    return recs


def load_events(path):
    p = Path(path)
    if not p.exists():
        return {}
    with open(p) as fh:
        return {e["ev"]: e for e in (json.loads(l) for l in fh if l.strip())}


def map_run(run_dir):
    run_dir = Path(run_dir)
    recs = load_requests(run_dir / "proxy")
    events = load_events(run_dir / "final" / "state" / "events.jsonl")
    out = []
    for k, r in enumerate(recs):
        calls = r["response"]["tool_calls"]
        answers = {}
        if k + 1 < len(recs):
            for m in recs[k + 1]["request"]["messages"]:
                if m.get("role") == "tool":
                    answers[m.get("tool_call_id")] = text_of(m.get("content"))
        labels = []
        for c in calls:
            if malformed(c):
                labels.append({"call": c["id"], "kind": "malformed", "events": []})
                continue
            try:
                command = str(json.loads(c["function"]["arguments"]).get("command", ""))
            except ValueError:
                command = c["function"]["arguments"]
            is_rtl = bool(RTL_CALL.search(command))
            ans = answers.get(c["id"])
            evs = [int(x.group(1)) for x in EV.finditer(ans or "")]
            if not is_rtl:
                labels.append({"call": c["id"], "kind": "other", "events": []})
            elif ans is None:
                labels.append({"call": c["id"], "kind": "no_answer", "events": []})
            elif not evs:
                labels.append({"call": c["id"], "kind": "unmapped", "events": []})
            else:
                ev = events.get(evs[0], {})
                labels.append({"call": c["id"], "kind": "rtl", "events": sorted(set(evs)), "result": ev.get("result"),
                               "reason_class": ev.get("reason_class"), "stage": ev.get("stage")})
        out.append({"request": k + 1, "seq": (r.get("labels") or {}).get("seq"), "labels": labels,
                    "malformed_tool_call": any(l["kind"] == "malformed" for l in labels),
                    "no_call_end": not calls and r["response"].get("finish_reason") == "stop",
                    "violation": any(l.get("result", "ok") not in ("ok", None) and l.get("reason_class") not in ("syntax", "tool", "check") for l in labels),
                    "bypass_attempt": any("Permission denied" in a for a in answers.values())})
    # requests of the same conversation (same seq) that follow the first malformed call
    seen = set()
    for row in out:
        key = row["seq"]
        row["after_malformed"] = key in seen
        if row["malformed_tool_call"]:
            seen.add(key)
    return out


if __name__ == "__main__":
    for row in map_run(sys.argv[1]):
        print(json.dumps(row))
