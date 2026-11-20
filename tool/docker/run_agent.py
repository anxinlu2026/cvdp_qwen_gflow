#!/usr/bin/env python3
"""Runs inside the container as the agent: writes the Qwen Code settings, reads the order from /tmp/agent/order.txt and
runs Qwen Code in /code/work. The stream-json output goes to stdout. Arguments come from /tmp/agent/qwen_args.json."""
import json
import os
import subprocess
import sys

args = json.load(open("/tmp/agent/qwen_args.json"))
env = os.environ.copy()
env.update(args["env"])
os.makedirs(env["HOME"] + "/.qwen", exist_ok=True)
settings = dict(args["settings"])
if env.get("QWEN_REQUEST_TIMEOUT_MS"):
    gc = settings.setdefault("model", {}).setdefault("generationConfig", {})
    gc["timeout"] = int(env["QWEN_REQUEST_TIMEOUT_MS"])
    # the recording proxy buffers an answer until it has been checked, so no chunk reaches the agent for as long as the generation takes
    gc["streamIdleTimeoutMs"] = int(env["QWEN_REQUEST_TIMEOUT_MS"])
    # Qwen Code 0.25.0 also ends a stream that has not completed within 900 s (DEFAULT_STREAM_MAX_LIFETIME_MS) and retries it;
    # the setting is not a generationConfig field, only the environment variable sets it
    env["QWEN_STREAM_MAX_LIFETIME_MS"] = env["QWEN_REQUEST_TIMEOUT_MS"]
if env.get("QWEN_CONTEXT_WINDOW"):
    # REVIEW_LOG #92: the window Qwen Code assumes (its automatic compaction starts at min(0.85 x window, window - 33000)); without this setting it assumes 200000
    settings.setdefault("model", {}).setdefault("generationConfig", {})["contextWindowSize"] = int(env["QWEN_CONTEXT_WINDOW"])
json.dump(settings, open(env["HOME"] + "/.qwen/settings.json", "w"))
cmd = ["qwen", "--yolo", "--output-format", "stream-json", "--include-partial-messages", "-m", env["QWEN_MODEL"],
       "--openai-base-url", env["OPENAI_BASE_URL"], "--openai-api-key", env["OPENAI_API_KEY"],
       "--exclude-tools"] + args["exclude_tools"]
sys.exit(subprocess.run(cmd, input=open("/tmp/agent/order.txt").read(), text=True, env=env, cwd=args["cwd"]).returncode)
