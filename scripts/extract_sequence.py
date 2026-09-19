from __future__ import annotations

import json
from pathlib import Path


from extract_sample import draw_overlay, points
from openpilot.common.transformations.camera import DEVICE_CAMERAS, view_frame_from_device_frame
from openpilot.common.transformations.orientation import rot_from_euler
from openpilot.tools.lib.framereader import FrameReader
from openpilot.tools.lib.logreader import LogReader

ROUTE = "5beb9b58bd12b691|0000010a--a51155e496"
SEGMENT = "000"
ANCHOR_FRAME_ID = 600
WINDOW_SECONDS = 10
OUTPUT = Path(__file__).resolve().parents[1] / "outputs" / "sequence"
FPS = 10


def main() -> None:
    root = Path("/mnt/d/comma_ai/offline_data/tool_routes") / ROUTE / SEGMENT
    events = list(LogReader(str(root / "rlog.zst")))
    models = [e for e in events if e.which() == "modelV2"]
    cameras = [e for e in events if e.which() == "narrowRoadCameraState"]
    encodes = [e for e in events if e.which() == "narrowRoadEncodeIdx"]
    calibrations = [e for e in events if e.which() == "extrinsicsCalibration" and str(e.extrinsicsCalibration.calStatus) == "calibrated"]
    devices = [e for e in events if e.which() == "deviceState"]
    onroad = [e for e in events if e.which() == "onroadEvents" and len(e.onroadEvents)]

    anchor = min(models, key=lambda e: abs(int(e.modelV2.frameId) - ANCHOR_FRAME_ID))
    anchor_time = int(anchor.logMonoTime)
    half_window = WINDOW_SECONDS * 1_000_000_000 // 2
    selected = [e for e in models if abs(int(e.logMonoTime) - anchor_time) <= half_window]
    selected = selected[::max(1, round(20 / FPS))]

    device_type = str(devices[0].deviceState.deviceType) if devices else "mici"
    sensor = str(cameras[0].narrowRoadCameraState.sensor) if cameras else "os04c10"
    camera = DEVICE_CAMERAS.get((device_type, sensor), DEVICE_CAMERAS[("tici", "ar0231")]).narrow_road
    reader = FrameReader(str(root / "fcamera.hevc"), pix_fmt="rgb24", hwaccel="none", loglevel="error")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frames = []

    for index, model_event in enumerate(selected):
        model = model_event.modelV2
        model_id = int(model.frameId)
        camera_event = min(cameras, key=lambda e: abs(int(e.narrowRoadCameraState.frameId) - model_id))
        camera_id = int(camera_event.narrowRoadCameraState.frameId)
        if camera_id >= reader.frame_count:
            continue
        calibration_event = min(calibrations, key=lambda e: abs(int(e.logMonoTime) - int(model_event.logMonoTime)))
        calibration = calibration_event.extrinsicsCalibration
        transform = camera.intrinsics @ view_frame_from_device_frame @ rot_from_euler(list(calibration.rpyCalib))
        model_json = {
            "frameId": camera_id,
            "position_points": points(model.position),
            "lane_lines": [points(line) for line in model.laneLines],
            "road_edges": [points(edge) for edge in model.roadEdges],
            "confidence": str(model.confidence),
            "laneLineProbs": list(model.laneLineProbs),
            "desiredCurvature": float(model.action.desiredCurvature),
            "desiredAcceleration": float(model.action.desiredAcceleration),
        }
        image = reader.get(camera_id)
        overlay_path = OUTPUT / f"frame-{index:04d}.jpg"
        draw_overlay(image, model_json, transform, float(calibration.height[0]) if calibration.height else 1.35, overlay_path)
        frames.append({
            "index": index,
            "image": overlay_path.name,
            "modelFrameId": model_id,
            "cameraFrameId": camera_id,
            "modelLogMonoTime": int(model_event.logMonoTime),
            "cameraLogMonoTime": int(camera_event.logMonoTime),
            "timeSeconds": (int(model_event.logMonoTime) - anchor_time) / 1_000_000_000,
            "confidence": str(model.confidence),
            "desiredCurvature": float(model.action.desiredCurvature),
            "desiredAcceleration": float(model.action.desiredAcceleration),
            "laneLineProbs": list(model.laneLineProbs),
        })

    event_markers = []
    for event in onroad:
        delta = (int(event.logMonoTime) - anchor_time) / 1_000_000_000
        if -WINDOW_SECONDS / 2 <= delta <= WINDOW_SECONDS / 2:
            event_markers.append({"timeSeconds": delta, "events": [str(x.name) for x in event.onroadEvents]})

    manifest = {
        "route": ROUTE,
        "segment": SEGMENT,
        "anchorModelFrameId": int(anchor.modelV2.frameId),
        "anchorLogMonoTime": anchor_time,
        "windowSeconds": WINDOW_SECONDS,
        "playbackFps": FPS,
        "inspectionStepSeconds": 1,
        "camera": {"deviceType": device_type, "sensor": sensor, "width": reader.w, "height": reader.h},
        "frames": frames,
        "eventMarkers": event_markers,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Created {len(frames)} synchronized frames in {OUTPUT}")
    print(f"Events in window: {len(event_markers)}")
    print(f"Manifest: {OUTPUT / 'manifest.json'}")


if __name__ == "__main__":
    main()
