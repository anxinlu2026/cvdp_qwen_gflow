#!/usr/bin/env python3
"""Recording proxy between the agent (Qwen Code, OpenAI-compatible client) and Ollama.

Every request is forwarded unchanged and the answer is streamed back unchanged. For each chat request
(/v1/chat/completions, /api/chat) one JSON line is appended to the record file:
  request (the full JSON body), the raw response lines exactly as received (SSE or JSON), the assembled
  assistant message (content, reasoning, tool_calls, finish_reason, usage), timing, HTTP status,
  the labels read from --label-file at request time (problem, round, order, flow version ...),
  and the environment (Ollama version, model digest, read once at start and per model).

usage: record_proxy.py --out DIR [--port 11500] [--target 127.0.0.1:11434] [--label-file FILE]
The agent's base URL becomes http://host.docker.internal:PORT/v1 (from a container) or http://127.0.0.1:PORT/v1.
"""
import argparse
import datetime
import http.client
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

def spec_decode_label(req):
    """Recorded with every chat request as 'inferred_spec_decode_from_logprobs' (REVIEW_LOG #26, #27): 'off' when the request asks for logprobs, 'on' otherwise. Inferred from the request, not reported by the engine:
    in Ollama 0.35.1 the MLX runner decodes speculatively unless logprobs are requested (server.log prints 'speculative decode stats' only for requests without logprobs)."""
    if isinstance(req, dict) and (req.get("logprobs") or req.get("top_logprobs")):
        return "off"
    return "on"


CHAT_PATHS = ("/v1/chat/completions", "/api/chat")
HOP = ("host", "content-length", "connection", "transfer-encoding", "keep-alive")


JSON_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
LEAK_MARKS = ("<function=", "<parameter", "<tool_call")


def check_value(v, schema):
    t = (schema or {}).get("type")
    ts = t if isinstance(t, list) else [t]
    known = [x for x in ts if x in JSON_TYPES or x == "null"]
    if not known:
        return True
    for x in known:
        if x == "null":
            if v is None:
                return True
        elif isinstance(v, JSON_TYPES[x]) and not (isinstance(v, bool) and x in ("integer", "number")):
            return True
    return False


def slip_reason(msg, tools):
    """Why the assistant message is a slipped tool call, or None. The check is against the request's own tool schemas:
    the name is declared, the arguments are a JSON object, required parameters are present, no parameter is undeclared
    (a junk key such as '<parameter name="command"' is undeclared), the values have the declared types. A reply that
    carries tool-call markup as text without any tool call is a leak."""
    if "finish_reason" in msg and msg["finish_reason"] is None:
        return "incomplete_response"      # the stream ended without a finish reason (Ollama drops it when its tool-call parser fails)
    calls = msg.get("tool_calls") or []
    ct = (msg.get("usage") or {}).get("completion_tokens")
    if ct and not calls and msg.get("finish_reason") == "stop":
        # most of the generated tokens are not in the answer (seen twice: 0.38 and 0.67 visible characters per token, normal is 2 to 5)
        if (len(msg.get("reasoning") or "") + len(msg.get("content") or "")) / ct < 1.0:
            return "output_missing"
    if not calls:
        return "leak" if any(m in (msg.get("content") or "") for m in LEAK_MARKS) else None
    decl = {}
    for t in tools or []:
        fn = t.get("function") or {}
        if fn.get("name"):
            decl[fn["name"]] = fn.get("parameters") or {}
    for c in calls:
        fn = c.get("function") or {}
        name = fn.get("name")
        if name not in decl:
            return "undeclared_tool"
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            return "arguments_not_json"
        if not isinstance(args, dict):
            return "arguments_not_object"
        sch = decl[name]
        props = sch.get("properties") or {}
        for r in sch.get("required") or []:
            if r not in args:
                return "missing_required"
        if props and sch.get("additionalProperties") is not True:
            if any(k not in props for k in args):
                return "undeclared_parameter"
        if any(not check_value(v, props.get(k)) for k, v in args.items()):
            return "wrong_type"
    return None


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


class Recorder:
    def __init__(self, out, target, label_file, resamples=2, model_override=None, inject=None, backend_label=None, save_partials=False, allow=None, drop_reasoning=False, keep_tail=0):
        self.keep_tail = keep_tail               # characters of the last answer's thinking that are still sent back when drop_reasoning is on
        self.drop_reasoning = drop_reasoning     # the thinking of earlier answers is not sent back to the model (the answer text, tool calls and tool results stay)
        self.model_override, self.inject = model_override, inject or {}
        self.save_partials = save_partials      # M7: every piece of an upstream answer is appended to <out>/partials/<request id>-a<attempt>.sse as it arrives (the answer of a generation still running when the proxy stops is kept)
        self.backend_label = backend_label
        self.allow = {tuple(x.split(None, 1)) for x in allow} if allow else None      # MAP stage 2 (R2 A2): only these (method, path) pairs are forwarded; everything else gets 403 and is logged in blocked.jsonl. None = forward everything (default, as before)
        self.resamples = resamples
        self.keepalive_s = 5
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.host, port = target.split(":")
        self.port = int(port)
        self.label_file = Path(label_file) if label_file else None
        self.lock = threading.Lock()
        self.digests = {}
        self.env = {"proxy_started": now(), "target": target, "ollama_version": self._get("/api/version").get("version"), "backend_label": backend_label}
        (self.out / "proxy_meta.json").write_text(json.dumps(self.env, indent=1))

    def _get(self, path):
        try:
            c = http.client.HTTPConnection(self.host, self.port, timeout=10)
            c.request("GET", path)
            return json.loads(c.getresponse().read() or b"{}")
        except Exception as e:
            return {"error": repr(e)}

    def digest(self, model):
        if model not in self.digests:
            tags = self._get("/api/tags").get("models", [])
            self.digests[model] = next((m.get("digest") for m in tags if m.get("name") == model or m.get("model") == model), None)
        return self.digests[model]

    def labels(self):
        if not self.label_file:
            return {}
        try:
            return json.loads(self.label_file.read_text())
        except Exception as e:
            return {"label_error": repr(e)}

    def heartbeat(self, rid, attempt, nbytes, chunks, t_last):
        """progress.json: the generation of the request in flight (bytes received so far, time of the last piece), for the orchestrator's idle rule."""
        try:
            (self.out / "progress.json").write_text(json.dumps({"t": time.time(), "request": rid, "attempt": attempt, "bytes": nbytes, "chunks": chunks, "t_last_chunk": t_last}))
        except OSError:
            pass

    def inflight_change(self, d):
        with self.lock:
            self.inflight = getattr(self, "inflight", 0) + d
            self.inflight_writes = getattr(self, "inflight_writes", 0) + 1
            try:
                (self.out / "inflight.json").write_text(json.dumps({"t": time.time(), "inflight": self.inflight, "writes": self.inflight_writes}))
            except OSError:
                pass

    def write(self, rec):
        line = json.dumps(rec, ensure_ascii=False)
        with self.lock, open(self.out / f"requests-{datetime.date.today():%Y%m%d}.jsonl", "a") as f:
            f.write(line + "\n")


def assemble(raw_lines, streamed, path):
    """Rebuild the assistant message from the response the client received."""
    msg = {"content": "", "reasoning": "", "tool_calls": [], "finish_reason": None, "usage": None}
    calls = {}

    def take(d):
        if path.startswith("/api/"):  # Ollama native: {"message": {...}, "done": ...}
            m = d.get("message") or {}
            msg["content"] += m.get("content") or ""
            msg["reasoning"] += m.get("thinking") or ""
            for tc in m.get("tool_calls") or []:
                msg["tool_calls"].append(tc)
            if d.get("done"):
                msg["finish_reason"] = d.get("done_reason")
                msg["usage"] = {k: d.get(k) for k in ("prompt_eval_count", "eval_count", "total_duration") if k in d}
            return
        for ch in d.get("choices") or []:
            part = ch.get("delta") if streamed else ch.get("message")
            part = part or {}
            msg["content"] += part.get("content") or ""
            msg["reasoning"] += part.get("reasoning") or part.get("reasoning_content") or ""
            for tc in part.get("tool_calls") or []:
                slot = calls.setdefault(tc.get("index", len(calls)), {"id": None, "type": "function", "function": {"name": "", "arguments": ""}})
                slot["id"] = tc.get("id") or slot["id"]
                fn = tc.get("function") or {}
                slot["function"]["name"] += fn.get("name") or ""
                slot["function"]["arguments"] += fn.get("arguments") or ""
            if ch.get("finish_reason"):
                msg["finish_reason"] = ch["finish_reason"]
        if d.get("usage"):
            msg["usage"] = d["usage"]

    for line in raw_lines:
        s = line.strip()
        if s.startswith("data:"):
            s = s[5:].strip()
        if not s or s == "[DONE]":
            continue
        try:
            take(json.loads(s))
        except ValueError:
            continue
    if calls:
        msg["tool_calls"] = [calls[k] for k in sorted(calls)]
    return msg


LOOP_TAIL, LOOP_WINDOW, LOOP_COUNT = 600, 60000, 4


def stream_text(buf, state):
    """Append to state["text"] the text (thinking, content, tool-call arguments) of the complete SSE lines of buf that were not read yet."""
    end = buf.rfind(b"\n")
    if end < state["off"]:
        return
    for line in bytes(buf[state["off"]:end]).decode("utf-8", "replace").split("\n"):
        if not line.startswith("data: ") or line[6:].strip() == "[DONE]":
            continue
        try:
            d = (json.loads(line[6:]).get("choices") or [{}])[0].get("delta") or {}
        except Exception:  # noqa: BLE001
            continue
        state["text"] += (d.get("reasoning_content") or d.get("reasoning") or "") + (d.get("content") or "")
        for tc in d.get("tool_calls") or []:
            state["text"] += (tc.get("function") or {}).get("arguments") or ""
    state["off"] = end + 1
    state["text"] = state["text"][-2 * LOOP_WINDOW:]


def drop_history_reasoning(messages, keep_tail=0):
    """The messages without the thinking of the assistant messages (fields reasoning, reasoning_content), and the number of characters left out.
    keep_tail > 0: the last assistant message keeps the last keep_tail characters of its thinking (where its conclusion and plan stand),
    so that the next answer goes on from them and does not work them out again."""
    last = max((i for i, m in enumerate(messages) if isinstance(m, dict) and m.get("role") == "assistant" and (m.get("reasoning") or m.get("reasoning_content"))), default=None)
    out, n = [], 0
    for i, m in enumerate(messages):
        if isinstance(m, dict) and m.get("role") == "assistant" and (m.get("reasoning") or m.get("reasoning_content")):
            size = max(len(m.get("reasoning") or ""), len(m.get("reasoning_content") or ""))
            if keep_tail and i == last:
                m = dict(m)
                for k in ("reasoning", "reasoning_content"):
                    if m.get(k) and len(m[k]) > keep_tail:
                        cut = m[k][-keep_tail:]
                        m[k] = "[the earlier part of this thinking is left out]\n" + cut[cut.find("\n") + 1:]
                n += max(size - keep_tail, 0)
            else:
                n += size
                m = {k: v for k, v in m.items() if k not in ("reasoning", "reasoning_content")}
        out.append(m)
    return out, n


def repeat_loop(text):
    """True when the generation repeats itself word for word: the last LOOP_TAIL characters stand LOOP_COUNT times or more in the last LOOP_WINDOW characters."""
    if len(text) < LOOP_WINDOW:
        return False
    tail = text[-LOOP_TAIL:]
    if len(set(tail)) < 12:       # a run of one character (a rule, blanks) is not judged here
        return False
    return text[-LOOP_WINDOW:].count(tail) >= LOOP_COUNT


def make_handler(rec):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def guarded(self, body, req, entry, hdr, rec, t0):
            """Buffer each answer, check it against the request's tool schemas, ask again with another seed (at most
            rec.resamples times) when it is slipped, and send the first accepted answer (the last one when none is) as it
            was received. While the answer is buffered the client gets SSE comment lines so its connection stays alive."""
            streamed = bool(req.get("stream"))
            attempts, sent_headers = [], False
            stop, gone, client_gone = threading.Event(), threading.Event(), False
            wlock = threading.Lock()

            def write(b):
                with wlock:
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(b), b))
                    self.wfile.flush()

            def keepalive():
                while not stop.wait(rec.keepalive_s):
                    try:
                        write(b": keepalive\n\n")
                    except Exception:  # noqa: BLE001
                        gone.set()
                        return
            ka = threading.Thread(target=keepalive, daemon=True)
            if streamed:       # the first token can be minutes away (prompt evaluation): answer now and keep the line alive
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                sent_headers = True
                ka.start()
            for n in range(rec.resamples + 1):
                b = dict(req)
                if rec.model_override:
                    b["model"] = rec.model_override
                b.update(rec.inject)
                if rec.drop_reasoning and isinstance(b.get("messages"), list):
                    kept, dropped = drop_history_reasoning(b["messages"], rec.keep_tail)
                    b["messages"], entry["dropped_history_reasoning_chars"] = kept, dropped
                if n:
                    b["seed"] = int.from_bytes(uuid.uuid4().bytes[:4], "big")
                data = json.dumps(b).encode()
                h = dict(hdr)
                h["Content-Length"] = str(len(data))
                up = http.client.HTTPConnection(rec.host, rec.port, timeout=7200)
                ta = time.monotonic()
                box, done = {"buf": bytearray(), "chunks": 0, "t_last": time.time()}, threading.Event()

                def fetch():
                    pf = None
                    if rec.save_partials:
                        try:
                            (rec.out / "partials").mkdir(exist_ok=True)
                            pf = open(rec.out / "partials" / f"{entry['id']}-a{n}.sse", "ab")
                        except OSError:
                            pf = None      # no file, no partial answer: the request goes on (R2)
                    try:
                        up.request("POST", self.path, data, h)
                        r = up.getresponse()
                        box["status"], box["ctype"] = r.status, r.getheader("Content-Type", "")
                        while True:                  # read in pieces: the progress (bytes, time of the last piece) is written to progress.json while waiting
                            piece = r.read1(65536)
                            if not piece:
                                break
                            if pf:      # the file first, the counters after: progress.json never counts more bytes than the file holds (R2)
                                try:
                                    pf.write(piece)
                                    pf.flush()
                                except OSError:
                                    # a full disk must not break the request
                                    try:
                                        pf.close()
                                    except OSError:
                                        pass
                                    pf = None
                            box["buf"] += piece
                            box["chunks"] += 1
                            box["t_last"] = time.time()
                        box["raw"] = bytes(box["buf"])
                    except Exception as e:  # noqa: BLE001
                        box["error"] = repr(e)
                    finally:
                        if pf:
                            try:
                                pf.close()
                            except OSError:
                                pass
                        done.set()
                threading.Thread(target=fetch, daemon=True).start()
                st, tick = {"off": 0, "text": ""}, 0
                while not done.wait(1):
                    rec.heartbeat(entry["id"], n, len(box["buf"]), box["chunks"], box["t_last"])
                    if gone.is_set():              # the client gave up (its own idle timeout, or it was killed): stop the generation so that it does not queue the retry
                        up.close()
                        break
                    tick += 1
                    if streamed and tick % 5 == 0:      # a generation that repeats itself word for word never ends by itself: stop it and ask again with another seed
                        try:
                            stream_text(box["buf"], st)
                            if repeat_loop(st["text"]):
                                box["loop"] = True
                                up.close()
                                break
                        except Exception:  # noqa: BLE001
                            pass
                if box.get("loop"):
                    part = bytes(box["buf"]).decode("utf-8", "replace").split("\n")
                    attempts.append({"attempt": n, "seed": b.get("seed"), "reject_reason": "repeat_loop", "accepted": False, "seconds": round(time.monotonic() - ta, 3),
                                     "lines": part[-400:], "msg": {"loop_tail": st["text"][-3000:]}, "partial_bytes": len(box["buf"])})
                    continue
                if gone.is_set() and "raw" not in box:
                    part = bytes(box["buf"]).decode("utf-8", "replace").split("\n")
                    attempts.append({"attempt": n, "seed": b.get("seed"), "reject_reason": "client_gone", "seconds": round(time.monotonic() - ta, 3),
                                     "partial_lines": part, "partial_bytes": len(box["buf"])})
                    client_gone = True
                    break
                up.close()
                if "error" in box:
                    raise RuntimeError(box["error"])
                if box["status"] != 200:
                    err = box["raw"]
                    if not sent_headers:
                        self.send_response(box["status"])
                        self.send_header("Content-Type", box["ctype"] or "application/json")
                        self.send_header("Content-Length", str(len(err)))
                        self.end_headers()
                        self.wfile.write(err)
                    else:
                        self.close_connection = True      # headers are gone: the client sees the line drop
                    entry["status"] = box["status"]
                    attempts.append({"attempt": n, "seed": b.get("seed"), "http_status": box["status"], "reject_reason": "upstream_error"})
                    break
                raw, ctype = box["raw"], box["ctype"]
                lines = raw.decode("utf-8", "replace").split("\n")
                msg = assemble(lines, streamed, self.path)
                why = slip_reason(msg, req.get("tools"))
                attempts.append({"attempt": n, "seed": b.get("seed"), "reject_reason": why, "accepted": why is None,
                                 "seconds": round(time.monotonic() - ta, 3), "raw": raw, "ctype": ctype, "lines": lines, "msg": msg})
                if why is None:
                    break
            stop.set()
            last = attempts[-1]
            entry["sampling_override"] = {"model": rec.model_override, "inject": rec.inject}
            entry["guard"] = {"enabled": True, "resamples_allowed": rec.resamples, "attempts": len(attempts),
                              "first_sample_valid": attempts[0].get("reject_reason") is None,
                              "resample_seconds": round(sum(a.get("seconds", 0) for a in attempts[:-1]), 3),
                              "rejected": [{k: a[k] for k in ("attempt", "seed", "reject_reason", "seconds", "lines", "msg")} for a in attempts if a.get("accepted") is False]}
            if client_gone:                            # keep what happened: the request, the attempts, and the part of the answer that had been generated
                entry["client_disconnected"] = True
                part = attempts[-1].get("partial_lines", [])
                entry["partial"] = True
                entry["partial_bytes"] = attempts[-1].get("partial_bytes", 0)
                return part, assemble(part, streamed, self.path), streamed
            if last.get("reject_reason") == "repeat_loop":      # every attempt repeated itself: drop the line, the client asks again
                entry["status"] = "repeat_loop"
                self.close_connection = True
            if "raw" not in last:                      # upstream error answered above
                return None, None, None
            if streamed:
                ka.join(timeout=6)
                try:
                    write(last["raw"])
                    with wlock:
                        self.wfile.write(b"0\r\n\r\n")
                        self.wfile.flush()
                except Exception:  # noqa: BLE001
                    entry["client_disconnected"] = True      # the answer is kept in the record all the same
            else:
                self.send_response(200)
                self.send_header("Content-Type", last["ctype"])
                self.send_header("Content-Length", str(len(last["raw"])))
                self.end_headers()
                self.wfile.write(last["raw"])
            entry["status"] = 200
            entry["content_type"] = last["ctype"]
            return last["lines"], last["msg"], streamed

        def handle_any(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            path = self.path.split("?")[0]
            if rec.allow is not None and (self.command, path) not in rec.allow:
                with rec.lock:
                    with open(rec.out / "blocked.jsonl", "a") as bf:
                        bf.write(json.dumps({"t": now(), "method": self.command, "path": self.path[:200], "bytes": len(body)}) + "\n")
                msg = b'{"error": "this path is not allowed by the recording proxy"}'
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
                return
            chat = self.command == "POST" and path in CHAT_PATHS
            entry = {"id": uuid.uuid4().hex, "t_request": now(), "path": self.path, "labels": rec.labels() if chat else None}
            t0 = time.monotonic()
            hdr = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
            hdr["Content-Length"] = str(len(body))
            if chat and path == "/v1/chat/completions" and rec.resamples >= 0:
                try:
                    req = json.loads(body)
                except ValueError:
                    req = None
                if chat:
                    entry["inferred_spec_decode_from_logprobs"] = spec_decode_label(req)
                if isinstance(req, dict) and req.get("tools"):
                    try:
                        lines, msg, streamed = self.guarded(body, req, entry, hdr, rec, t0)
                    except Exception as e:  # client gone or upstream error
                        entry["error"] = repr(e)
                        lines = None
                    if lines is not None:
                        entry.update({"t_first_byte_s": None, "t_total_s": round(time.monotonic() - t0, 3), "model": rec.model_override or req.get("model"),
                                      "model_digest": rec.digest(rec.model_override or req.get("model")), "ollama_version": rec.env.get("ollama_version"), "backend_label": rec.backend_label,
                                      "request": req, "response_raw_lines": lines, "response": msg,
                                      "slipped_tool_call": slip_reason(msg, req.get("tools")) is not None})
                        rec.write(entry)
                    return
            up = http.client.HTTPConnection(rec.host, rec.port, timeout=7200)
            raw, first = bytearray(), None
            try:
                up.request(self.command, self.path, body, hdr)
                r = up.getresponse()
                self.send_response(r.status)
                for k, v in r.getheaders():
                    if k.lower() not in HOP:
                        self.send_header(k, v)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                while True:
                    chunk = r.read1(65536)
                    if not chunk:
                        break
                    if first is None:
                        first = time.monotonic()
                    if chat:
                        raw += chunk
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
                entry["status"] = r.status
                entry["content_type"] = r.getheader("Content-Type", "")
            except Exception as e:  # client gone or upstream error: still record what we have
                entry["error"] = repr(e)
            finally:
                up.close()
            if not chat:
                return
            try:
                req = json.loads(body)
            except ValueError:
                req = {"unparsed_body": body.decode("utf-8", "replace")}
            text = raw.decode("utf-8", "replace")
            streamed = "event-stream" in entry.get("content_type", "") or (path.startswith("/api/") and req.get("stream", True))
            lines = text.split("\n")
            entry.update({
                "t_first_byte_s": round(first - t0, 3) if first else None,
                "t_total_s": round(time.monotonic() - t0, 3),
                "model": req.get("model"), "model_digest": rec.digest(req.get("model")),
                "ollama_version": rec.env.get("ollama_version"), "backend_label": rec.backend_label,
                "inferred_spec_decode_from_logprobs": spec_decode_label(req) if chat else None,
                "request": req,
                "response_raw_lines": lines,
                "response": assemble(lines, streamed, path),
            })
            entry["slipped_tool_call"] = slip_reason(entry["response"], req.get("tools")) is not None if req.get("tools") else False
            rec.write(entry)

        def counted(self):
            """REVIEW_LOG #119 (R2): count the chat requests in flight (+1 when one arrives, -1 when it is answered or broken off) and write
            inflight.json, so the orchestrator knows whether a generation is still running (the M test's end-on-write rule)."""
            chat = self.command == "POST" and "chat/completions" in self.path or self.path.startswith("/api/chat")
            if chat:
                rec.inflight_change(+1)
            try:
                self.handle_any()
            finally:
                if chat:
                    rec.inflight_change(-1)

        do_POST = counted
        do_GET = do_PUT = do_DELETE = do_HEAD = handle_any

        def log_message(self, *_):
            pass

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=11500)
    ap.add_argument("--target", default="127.0.0.1:11434")
    ap.add_argument("--label-file")
    ap.add_argument("--resamples", type=int, default=2, help="answers asked again when slipped (0 = check and label only); -1 = guard off")
    ap.add_argument("--model-override", help="model name sent to Ollama instead of the one the agent asks for (sampling arms)")
    ap.add_argument("--inject", default="{}", help="JSON object of request fields added to every chat request (sampling arms)")
    ap.add_argument("--backend-label", help="free text naming a non-Ollama backend (e.g. the mlx_lm.server version and model path); recorded in proxy_meta.json and in every record")
    ap.add_argument("--save-partials", action="store_true", help="append every piece of an upstream answer to <out>/partials/<request id>-a<attempt>.sse as it arrives (guarded requests only)")
    ap.add_argument("--keepalive", type=float, default=5, help="seconds between SSE comment lines while an answer is buffered")
    ap.add_argument("--keep-last-reasoning", type=int, default=0, help="with --drop-history-reasoning: the last answer keeps this many characters from the end of its thinking")
    ap.add_argument("--drop-history-reasoning", action="store_true", help="do not send the thinking of earlier answers back to the model")
    ap.add_argument("--allow", action="append", help='allow only this request, e.g. --allow "POST /v1/chat/completions" (repeatable); any other method and path gets 403 and a line in blocked.jsonl; without --allow everything is forwarded')
    a = ap.parse_args()
    rec = Recorder(a.out, a.target, a.label_file, a.resamples, a.model_override, json.loads(a.inject), a.backend_label, a.save_partials, a.allow, a.drop_history_reasoning, a.keep_last_reasoning)
    rec.keepalive_s = a.keepalive
    print(f"recording proxy on 127.0.0.1:{a.port} -> {a.target}, records in {a.out}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(rec)).serve_forever()


if __name__ == "__main__":
    main()
