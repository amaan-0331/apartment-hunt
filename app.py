"""Local dashboard.  Run:  python3 app.py   then open the printed URL (also works on phones on the same Wi-Fi)."""
import json, os, subprocess, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import hunt

PORT = 8000
state = {"running": False, "log": []}


def refresh_job():
    state.update(running=True, log=[])
    try:
        hunt.build(refresh=True, log=state["log"].append)
    except Exception as e:
        state["log"].append(f"Failed: {e}")
    state["running"] = False


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send(200, open(hunt.path("dashboard.html"), "rb").read(), "text/html; charset=utf-8")
        elif self.path == "/api/listings":
            self.send(200, open(hunt.path("listings.json"), "rb").read())
        elif self.path == "/api/status":
            self.send(200, state)
        else:
            self.send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/refresh":
            if not state["running"]:
                threading.Thread(target=refresh_job, daemon=True).start()
            self.send(202, {"started": True})
        else:
            self.send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    if not os.path.exists(hunt.path("listings.json")):
        hunt.build(refresh=False)
    ip = subprocess.run(["ipconfig", "getifaddr", "en0"], capture_output=True, text=True).stdout.strip()
    print(f"Dashboard:  http://localhost:{PORT}")
    if ip:
        print(f"On a phone on the same Wi-Fi:  http://{ip}:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
