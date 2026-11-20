"""The scripted model: a local endpoint in the OpenAI Chat Completions shape that
answers a session with a fixed sequence of tool calls, so CI tests the wiring,
the consent, the refusals and the record with no model, no key and no variance.

Usage: python3 scripted_model.py PORT SCRIPT LOG_DIR

SCRIPT is a JSON list of steps, taken in order, one per model turn:
  {"tool": "dashboard__list_prepared", "arguments": {...}, "say": "optional text"}
A step's tool is matched by the end of an offered tool's name, so it does not
depend on how the client prefixes a server's tools. String arguments may name
an environment variable as "${NAME}". After the last step it answers with text
naming any PC- identifier the last tool answered, and ends the turn.

A request with no tools (a title, a summary) is answered with plain text.

It writes to LOG_DIR, names only and never an argument's value or an answer:
  offered-tools.json  every tool name a request offered
  steps.jsonl         each step taken, or why it stopped
Standard library only; it listens on 127.0.0.1 alone.
"""

import json
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT, SCRIPT, LOG_DIR = int(sys.argv[1]), sys.argv[2], sys.argv[3]
with open(SCRIPT) as given:
    STEPS = json.load(given)
OFFERED = set()
VARIABLE = re.compile(r"\$\{([A-Z0-9_]+)\}")
PREPARED = re.compile(r"\bPC-[A-Za-z0-9]+\b")


def log_step(record):
    with open(os.path.join(LOG_DIR, "steps.jsonl"), "a") as out:
        out.write(json.dumps(record) + "\n")


def filled(value):
    if isinstance(value, str):
        return VARIABLE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [filled(v) for v in value]
    if isinstance(value, dict):
        return {k: filled(v) for k, v in value.items()}
    return value


def chunk(delta, finish=None):
    return {"id": "scripted", "object": "chat.completion.chunk", "created": int(time.time()),
            "model": "flow", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


def answer(body):
    tools = [t.get("function", {}).get("name", "") for t in body.get("tools") or []]
    if not tools:
        return [chunk({"role": "assistant", "content": "Scripted run"}), chunk({}, "stop")]
    OFFERED.update(tools)
    with open(os.path.join(LOG_DIR, "offered-tools.json"), "w") as out:
        json.dump(sorted(OFFERED), out)

    messages = body.get("messages") or []
    taken = sum(1 for m in messages if m.get("role") == "assistant" and m.get("tool_calls"))
    if taken >= len(STEPS):
        last = next((m for m in reversed(messages) if m.get("role") == "tool"), {})
        content = last.get("content")
        content = content if isinstance(content, str) else json.dumps(content)
        ids = sorted(set(PREPARED.findall(content or "")))
        log_step({"step": taken, "end": True, "prepared": ids})
        said = ("Done. Prepared " + ", ".join(ids) + "; a person makes it on the Prepared page."
                if ids else "Done.")
        return [chunk({"role": "assistant", "content": said}), chunk({}, "stop")]

    step = STEPS[taken]
    matches = [name for name in tools if name.endswith(step["tool"])]
    if len(matches) != 1:
        log_step({"step": taken, "tool": step["tool"], "stopped": f"{len(matches)} offered tools match"})
        return [chunk({"role": "assistant", "content": f"Stopped: {step['tool']} is not offered."}),
                chunk({}, "stop")]
    log_step({"step": taken, "tool": matches[0]})
    arguments = json.dumps(filled(step.get("arguments", {})))
    first = {"role": "assistant"}
    if step.get("say"):
        first["content"] = step["say"]
    call = {"index": 0, "id": f"call_{taken}", "type": "function",
            "function": {"name": matches[0], "arguments": arguments}}
    return [chunk(first), chunk({"tool_calls": [call]}), chunk({}, "tool_calls")]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            return self.send_json({"object": "list", "data": [{"id": "flow", "object": "model"}]})
        self.send_error(404)

    def send_json(self, value):
        data = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self.send_error(404)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        chunks = answer(body)
        if not body.get("stream"):
            content = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
            calls = [t for c in chunks for t in c["choices"][0]["delta"].get("tool_calls", [])]
            message = {"role": "assistant", "content": content or None}
            if calls:
                message["tool_calls"] = [{k: v for k, v in t.items() if k != "index"} for t in calls]
            return self.send_json({"id": "scripted", "object": "chat.completion", "model": "flow",
                                   "choices": [{"index": 0, "message": message,
                                                "finish_reason": chunks[-1]["choices"][0]["finish_reason"]}],
                                   "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for c in chunks:
            self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
        usage = {"id": "scripted", "object": "chat.completion.chunk", "created": int(time.time()),
                 "model": "flow", "choices": [],
                 "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        self.wfile.write(f"data: {json.dumps(usage)}\n\ndata: [DONE]\n\n".encode())
        self.wfile.flush()


if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
