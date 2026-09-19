from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
INCIDENTS = ROOT / "outputs" / "incidents"
PORT = 8000


def json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, indent=2).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/incidents":
            incidents = []
            if INCIDENTS.exists():
                for path in sorted(INCIDENTS.iterdir()):
                    metadata = path / "metadata.json"
                    if metadata.exists():
                        incidents.append(json.loads(metadata.read_text()))
            return json_response(self, incidents)
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/report":
            return json_response(self, {"error": "not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            INCIDENTS.mkdir(parents=True, exist_ok=True)
            existing = [p for p in INCIDENTS.glob("incident-*") if p.is_dir()]
            number = len(existing) + 1
            destination = INCIDENTS / f"incident-{number:03d}"
            destination.mkdir()
            source = ROOT / "outputs" / "sample-incident"
            for name in ("frame.jpg", "overlay.jpg", "model.json"):
                if (source / name).exists():
                    shutil.copy2(source / name, destination / name)
            metadata = {
                "incident": f"incident-{number:03d}",
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "route": payload.get("route", "5beb9b58bd12b691|0000010a--a51155e496"),
                "frameId": payload.get("frameId", 66),
                "label": payload.get("label", "unclassified"),
                "severity": payload.get("severity", "unknown"),
                "note": payload.get("note", ""),
            }
            (destination / "metadata.json").write_text(json.dumps(metadata, indent=2))
            return json_response(self, metadata, 201)
        except Exception as exc:
            return json_response(self, {"error": str(exc)}, 400)


if __name__ == "__main__":
    print(f"Carlosthon viewer: http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
