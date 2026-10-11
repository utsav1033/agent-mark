"""
A scripted, OpenAI-compatible chat-completions server for $0 end-to-end tests.

It speaks just enough of /v1/chat/completions (streaming SSE + usage) for a real
agent binary such as pi to run a full tool loop against it. Each response is taken
from a script, indexed by how many assistant turns the request already contains:

    script = [
        {"tool_calls": [{"name": "bash", "arguments": {"command": "ls"}}]},
        {"content": "All done."},
    ]

Usage:
    with FakeLLM(script) as base_url:   # e.g. http://127.0.0.1:54321/v1
        ...point the agent at base_url...
    python -m tests.fake_llm script.json  # standalone, prints base URL
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeLLM:
    def __init__(self, script: list[dict], prompt_tokens: int = 1000, completion_tokens: int = 50) -> None:
        self.script = script
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.requests: list[dict] = []
        self._server: ThreadingHTTPServer | None = None

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:  # silence stderr
                pass

            def do_GET(self) -> None:  # /v1/models probes
                self._json({"object": "list", "data": [{"id": "fake-model", "object": "model"}]})

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                fake.requests.append(body)
                turn = sum(1 for m in body.get("messages", []) if m.get("role") == "assistant")
                step = fake.script[min(turn, len(fake.script) - 1)]
                if body.get("stream"):
                    self._stream(body.get("model", "fake-model"), step)
                else:
                    self._json(fake._completion(body.get("model", "fake-model"), step))

            def _json(self, obj: dict) -> None:
                data = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _stream(self, model: str, step: dict) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for chunk in fake._chunks(model, step):
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        return Handler

    def _usage(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
        }

    @staticmethod
    def _tool_calls(step: dict) -> list[dict]:
        return [
            {
                "index": i,
                "id": f"call_{i}_{int(time.time() * 1000)}",
                "type": "function",
                "function": {"name": tc["name"], "arguments": json.dumps(tc.get("arguments", {}))},
            }
            for i, tc in enumerate(step.get("tool_calls", []))
        ]

    def _chunks(self, model: str, step: dict) -> list[dict]:
        base = {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "created": int(time.time()), "model": model}
        out = [{**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}]
        if step.get("content"):
            out.append({**base, "choices": [{"index": 0, "delta": {"content": step["content"]}, "finish_reason": None}]})
        if step.get("tool_calls"):
            out.append({**base, "choices": [{"index": 0, "delta": {"tool_calls": self._tool_calls(step)}, "finish_reason": None}]})
        finish = "tool_calls" if step.get("tool_calls") else "stop"
        out.append({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
        out.append({**base, "choices": [], "usage": self._usage()})
        return out

    def _completion(self, model: str, step: dict) -> dict:
        message: dict = {"role": "assistant", "content": step.get("content")}
        if step.get("tool_calls"):
            message["tool_calls"] = self._tool_calls(step)
        return {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if step.get("tool_calls") else "stop"}],
            "usage": self._usage(),
        }

    def __enter__(self) -> str:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def __exit__(self, *exc: object) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()


if __name__ == "__main__":
    script = json.loads(open(sys.argv[1], encoding="utf-8").read())
    with FakeLLM(script) as url:
        print(url, flush=True)
        threading.Event().wait()
