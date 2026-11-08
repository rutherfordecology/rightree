"""Rightree map interface: a small local web server.

Serves web/index.html and runs predict.py for an area drawn on the map or
loaded from a KML/KMZ/GeoJSON file. Local only (binds to 127.0.0.1): the
records include NVS data under CC BY-NC, and nothing here is meant to be
published.

Usage:
    python scripts/serve.py [port]        # default 7882, then open http://127.0.0.1:7882
"""
import base64
import json
import re
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
PRED = ROOT / "data" / "predictions"
REGIONS = sorted(p.name for p in (ROOT / "data" / "env").iterdir()
                 if (p / "region_osm_nominatim.json").exists())
LOCK = threading.Lock()   # one prediction at a time; each loads the whole region


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:40]
    return s or "site"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args))

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/regions":
            out = {}
            for r in REGIONS:
                hit = json.loads((ROOT / "data" / "env" / r / "region_osm_nominatim.json").read_text(encoding="utf-8"))[0]
                out[r] = {"name": hit.get("display_name", r), "geojson": hit["geojson"]}
            return self.send_json(out)
        if self.path == "/api/version":
            m = re.search(r"^## (v[\d.]+)", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
            return self.send_json({"version": m.group(1) if m else None})
        if self.path == "/api/runs":
            runs = []
            for d in sorted(PRED.glob("*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                runs.append({"id": d.parent.name, "time": d.stat().st_mtime})
            return self.send_json(runs[:50])
        m = re.fullmatch(r"/api/runs/([a-z0-9-]+)", self.path)
        if m:
            return self.send_run(m.group(1))
        return super().do_GET()

    def send_run(self, rid):
        d = PRED / rid
        if not (d / "report.json").exists():
            return self.send_json({"error": "No such run"}, 404)
        out = json.loads((d / "report.json").read_text(encoding="utf-8"))
        out["id"] = rid
        out["units_geojson"] = json.loads((d / "units.geojson").read_text(encoding="utf-8"))
        area = next((p for p in d.glob("area.*")), None)
        if area and area.suffix == ".geojson":
            out["area_geojson"] = json.loads(area.read_text(encoding="utf-8"))
        return self.send_json(out)

    def do_POST(self):
        if self.path != "/api/predict":
            return self.send_json({"error": "Not found"}, 404)
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except (ValueError, json.JSONDecodeError):
            return self.send_json({"error": "Bad request"}, 400)
        region = req.get("region") or (REGIONS[0] if REGIONS else None)
        if region not in REGIONS:
            return self.send_json({"error": f"Unknown region {region}"}, 400)
        rid = f"{slug(req.get('name'))}-{time.strftime('%Y%m%d-%H%M%S')}"
        d = PRED / rid
        d.mkdir(parents=True, exist_ok=True)
        if req.get("geojson"):
            area = d / "area.geojson"
            area.write_text(json.dumps(req["geojson"]), encoding="utf-8")
        elif req.get("file_b64") and req.get("file_name", "").lower().endswith((".kml", ".kmz", ".geojson", ".json")):
            ext = Path(req["file_name"]).suffix.lower().replace(".json", ".geojson")
            area = d / f"area{ext}"
            area.write_bytes(base64.b64decode(req["file_b64"]))
        else:
            return self.send_json({"error": "Draw an area or load a KML, KMZ or GeoJSON file"}, 400)
        with LOCK:
            p = subprocess.run([sys.executable, str(ROOT / "scripts" / "predict.py"), region, rid, str(area)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}, cwd=ROOT)
        if p.returncode != 0 or not (d / "report.json").exists():
            msg = (p.stderr.strip().splitlines() or p.stdout.strip().splitlines() or ["Prediction failed"])[-1]
            return self.send_json({"error": msg}, 500)
        return self.send_run(rid)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7882
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Rightree on http://127.0.0.1:{port}  (regions: {', '.join(REGIONS)})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
