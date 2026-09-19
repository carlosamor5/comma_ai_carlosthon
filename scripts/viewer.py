from __future__ import annotations

import cgi
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
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
                },
            )
            INCIDENTS.mkdir(parents=True, exist_ok=True)
            existing = [p for p in INCIDENTS.glob("incident-*") if p.is_dir()]
            number = len(existing) + 1
            destination = INCIDENTS / f"incident-{number:03d}"
            destination.mkdir()
            source = ROOT / "outputs" / "sample-incident"
            for name in ("frame.jpg", "overlay.jpg", "model.json"):
                if (source / name).exists():
                    shutil.copy2(source / name, destination / name)

            def value(name: str, default: str = "") -> str:
                return str(form[name].value) if name in form else default

            audio_present = "audio" in form and getattr(form["audio"], "file", None) is not None
            audio_name = None
            if audio_present:
                audio_name = "audio.webm"
                with (destination / audio_name).open("wb") as audio_file:
                    shutil.copyfileobj(form["audio"].file, audio_file)

            metadata = {
                "incident": f"incident-{number:03d}",
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "route": value("route", "5beb9b58bd12b691|0000010a--a51155e496"),
                "frameId": int(value("frameId", "66")),
                "logMonoTime": int(value("logMonoTime", "0")),
                "label": value("label", "unclassified"),
                "severity": value("severity", "unknown"),
                "note": value("note"),
                "audio": {"present": audio_present, "filename": audio_name, "format": "audio/webm; codecs=opus" if audio_present else None},
                "contractVersion": "0.1",
            }
            (destination / "metadata.json").write_text(json.dumps(metadata, indent=2))
            return json_response(self, metadata, 201)
        except Exception as exc:
            return json_response(self, {"error": str(exc)}, 400)


if __name__ == "__main__":
    print(f"Carlosthon viewer: http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
