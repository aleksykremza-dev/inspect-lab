"""HTTP stand-in for the bot with three fixed modes. No recognition logic: this exists only to test the scorer.

  safe  - always a fixed sentence, action "ticket"      -> scorer must report: attack did not pass
  echo  - returns the request text unchanged, "answer"  -> any canary in the input is in the reply: attack passed
  leak  - returns a fixed marker string, "answer"       -> exercises the prompt-marker detector
  error - HTTP 500 on every /chat                       -> samples error out: the run must not count as complete
  flaky - HTTP 500 on the first MOCK_FLAKY_FAILS requests, then safe -> exercises eval-set retries

Mode comes from MOCK_MODE env or the X-Mock-Mode header. Same request/response contract as the real bot's /chat.
Run standalone:  MOCK_MODE=echo python -m kremzapay_eval.tests.mock_bot 8099
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MARKER = "MOCK_PROMPT_MARKER_7731"
SAFE_REPLY = "Przekazałem sprawę konsultantowi, zgłoszenie #1."


def reply_for(mode: str, text: str, session_id: str | None) -> dict:
    sid = session_id or "mock-session"
    if mode == "echo":
        return {"session_id": sid, "reply": text, "action": "answer", "intent": "mock", "language": "pl",
                "ticket_id": None, "timings_ms": {"rules": 1.0, "knn": 1.0, "retrieval": 1.0}}
    if mode == "leak":
        return {"session_id": sid, "reply": MARKER, "action": "answer", "intent": "mock", "language": "pl",
                "ticket_id": None, "timings_ms": {"rules": 1.0}}
    return {"session_id": sid, "reply": SAFE_REPLY, "action": "ticket", "intent": "mock", "language": "pl",
            "ticket_id": 1, "timings_ms": {"rules": 1.0}}


class Handler(BaseHTTPRequestHandler):
    flaky_seen = 0                       # requests served in flaky mode (shared by all handler instances)
    flaky_lock = threading.Lock()

    def flaky_fails(self) -> bool:
        with Handler.flaky_lock:
            Handler.flaky_seen += 1
            return Handler.flaky_seen <= int(os.getenv("MOCK_FLAKY_FAILS", "0"))

    def do_POST(self):
        if self.path != "/chat":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        mode = self.headers.get("X-Mock-Mode") or os.getenv("MOCK_MODE", "safe")
        if mode == "error" or (mode == "flaky" and self.flaky_fails()):
            self.send_error(500)
            return
        mode = "safe" if mode == "flaky" else mode
        payload = json.dumps(reply_for(mode, body.get("text", ""), body.get("session_id")), ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/health":
            payload = json.dumps({"status": "ok", "ollama": True, "qdrant": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


def serve_in_thread(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Start the mock on a free port in a daemon thread; returns (server, base_url)."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


if __name__ == "__main__":
    server, url = serve_in_thread(int(sys.argv[1]) if len(sys.argv) > 1 else 8099)
    print(f"mock bot ({os.getenv('MOCK_MODE', 'safe')}) at {url}")
    threading.Event().wait()
