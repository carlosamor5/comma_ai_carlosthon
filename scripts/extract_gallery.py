from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from openpilot.common.transformations.camera import DEVICE_CAMERAS, view_frame_from_device_frame
from openpilot.common.transformations.orientation import rot_from_euler
from openpilot.tools.lib.framereader import FrameReader
from openpilot.tools.lib.logreader import LogReader
from extract_sample import draw_overlay, points

ROUTE = "5beb9b58bd12b691|0000010a--a51155e496"
SEGMENT = "000"
ROOT = Path("/mnt/d/comma_ai/offline_data/tool_routes") / ROUTE / SEGMENT
OUT = Path(__file__).resolve().parents[1] / "outputs/gallery"
TARGETS = [66, 200, 400, 600, 800, 1000]


def main() -> None:
    events = list(LogReader(str(ROOT / "rlog.zst")))
    models = [e for e in events if e.which() == "modelV2"]
    cameras = [e for e in events if e.which() == "narrowRoadCameraState"]
    encodes = [e for e in events if e.which() == "narrowRoadEncodeIdx"]
    devices = [e for e in events if e.which() == "deviceState"]
    calibrations = [e for e in events if e.which() == "extrinsicsCalibration" and str(e.extrinsicsCalibration.calStatus) == "calibrated"]
    device_type = str(devices[0].deviceState.deviceType) if devices else "mici"
    sensor = str(cameras[0].narrowRoadCameraState.sensor) if cameras else "os04c10"
    camera_config = DEVICE_CAMERAS.get((device_type, sensor), DEVICE_CAMERAS[("tici", "ar0231")]).narrow_road
    reader = FrameReader(str(ROOT / "fcamera.hevc"), pix_fmt="rgb24", hwaccel="none", loglevel="error")
    transform_base = camera_config.intrinsics
    OUT.mkdir(parents=True, exist_ok=True)
    tiles = []
    for target in TARGETS:
        model_event = min(models, key=lambda e: abs(int(e.modelV2.frameId) - target))
        model = model_event.modelV2
        model_id = int(model.frameId)
        camera_event = min(cameras, key=lambda e: abs(int(e.narrowRoadCameraState.frameId) - model_id))
        camera_id = int(camera_event.narrowRoadCameraState.frameId)
        calib_event = min(calibrations, key=lambda e: abs(int(e.logMonoTime) - int(model_event.logMonoTime)))
        calib = calib_event.extrinsicsCalibration
        view_from_calib = view_frame_from_device_frame @ rot_from_euler(list(calib.rpyCalib))
        transform = transform_base @ view_from_calib
        model_json = {
            "frameId": camera_id,
            "position_points": points(model.position),
            "lane_lines": [points(line) for line in model.laneLines],
            "road_edges": [points(edge) for edge in model.roadEdges],
            "confidence": str(model.confidence),
        }
        frame = reader.get(camera_id)
        output = OUT / f"frame-{target:04d}-model-{model_id:04d}.jpg"
        draw_overlay(frame, model_json, transform, float(calib.height[0]) if calib.height else 1.35, output)
        image = Image.open(output).convert("RGB")
        image.thumbnail((672, 380))
        canvas = Image.new("RGB", (672, 420), "#111318")
        canvas.paste(image, (0, 0))
        ImageDraw.Draw(canvas).text((12, 390), f"requested {target} · model {model_id} · camera {camera_id} · dt {int(camera_event.logMonoTime)-int(model_event.logMonoTime)} ns", fill="white")
        tiles.append(canvas)
    sheet = Image.new("RGB", (1344, 1260), "#111318")
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % 2) * 672, (i // 2) * 420))
    sheet.save(OUT / "contact-sheet.jpg", quality=92)
    (OUT / "manifest.json").write_text(json.dumps({"route": ROUTE, "segment": SEGMENT, "targets": TARGETS}, indent=2))
    print(f"Created {len(tiles)} overlays in {OUT}")
    print(f"Contact sheet: {OUT / 'contact-sheet.jpg'}")


if __name__ == "__main__":
    main()
