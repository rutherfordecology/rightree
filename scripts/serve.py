"""Build the static site (scripts/build_site.py) and serve it locally.

Usage:
    python scripts/serve.py [port]                  # default 7882

Then open http://127.0.0.1:<port>. The model runs in the browser, so this is
only a file server; any static host serves the same folder.
"""
import functools
import os
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript",
                      ".bin": "application/octet-stream", ".gz": "application/octet-stream"}

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


def main():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_site.py"), str(SITE)], check=True)
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 7882))
    srv = ThreadingHTTPServer((host, port), functools.partial(Handler, directory=str(SITE)))
    print(f"Rightree on http://{host}:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
