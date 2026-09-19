from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from openpilot.common.transformations.camera import DEVICE_CAMERAS, view_frame_from_device_frame
from openpilot.common.transformations.orientation import rot_from_euler
from openpilot.tools.lib.framereader import FrameReader
from openpilot.tools.lib.logreader import LogReader

ROUTE = "5beb9b58bd12b691|0000010a--a51155e496"
SEGMENT = "000"
DATA_ROOT = Path("/mnt/d/comma_ai/offline_data/tool_routes")
OUTPUT = Path("outputs/sample-incident")


def points(series) -> list[dict[str, float]]:
    return [{"x": float(x), "y": float(y), "z": float(z)} for x, y, z in zip(series.x, series.y, series.z)]


def project(points_3d: list[dict[str, float]], transform: np.ndarray, width: int, height: int,
            max_distance: float = 100.0) -> list[tuple[int, int]]:
    """Project model car-frame points using the openpilot UI matrix."""
    points = np.array([[p["x"], p["y"], p["z"]] for p in points_3d], dtype=np.float32)
    if len(points) == 0:
        return []
    points = points[(points[:, 0] >= 0) & (points[:, 0] <= max_distance)]
    if len(points) == 0:
        return []
    projected = (transform @ points.T).T
    valid = np.abs(projected[:, 2]) > 1e-6
    projected = projected[valid]
    if len(projected) == 0:
        return []
    pixels = projected[:, :2] / projected[:, 2:3]
    result = []
    for x, y in pixels:
        if -500 < x < width + 500 and -500 < y < height + 500:
            result.append((round(float(x)), round(float(y))))
    return result


def draw_overlay(frame: np.ndarray, model_json: dict, transform: np.ndarray, path_height: float, output: Path) -> None:
    image = Image.fromarray(frame).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    colors = [(0, 255, 100, 220), (255, 220, 0, 220), (255, 140, 0, 220), (255, 80, 80, 220)]
    width, height = image.size

    path_points = [{**point, "z": point["z"] + path_height} for point in model_json["position_points"]]
    path = project(path_points, transform, width, height)
    if len(path) > 1:
        draw.line(path, fill=(40, 220, 255, 235), width=7)

    for index, lane in enumerate(model_json["lane_lines"]):
        projected = project(lane, transform, width, height)
        if len(projected) > 1:
            draw.line(projected, fill=colors[index], width=4)

    for edge in model_json["road_edges"]:
        projected = project(edge, transform, width, height)
        if len(projected) > 1:
            draw.line(projected, fill=(255, 70, 70, 190), width=3)

    draw.rectangle((18, 18, 470, 112), fill=(0, 0, 0, 180))
    draw.text((32, 30), "CARLOSTHON · DIAGNOSTIC OVERLAY", fill="white")
    draw.text((32, 55), f"frame {model_json['frameId']} · confidence {model_json['confidence']}", fill="white")
    draw.text((32, 80), "cyan path · colored lanes · red road edges", fill="white")
    image.save(output, quality=92)


def main() -> None:
    segment_dir = DATA_ROOT / ROUTE / SEGMENT
    rlog_path = segment_dir / "rlog.zst"
    video_path = segment_dir / "fcamera.hevc"
    if not rlog_path.exists():
        raise FileNotFoundError(rlog_path)
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    model = None
    event_time = None
    camera_candidates = []
    encode_candidates = []
    device_type = "mici"
    sensor = "os04c10"
    rpy_calib = None
    calibration_candidates = []
    for event in LogReader(str(rlog_path)):
        name = event.which()
        if name == "deviceState":
            device_type = str(event.deviceState.deviceType)
        elif name == "narrowRoadCameraState":
            sensor = str(event.narrowRoadCameraState.sensor)
            camera_candidates.append((int(event.logMonoTime), int(event.narrowRoadCameraState.frameId)))
        elif name == "narrowRoadEncodeIdx":
            encode_candidates.append((int(event.logMonoTime), int(event.narrowRoadEncodeIdx.frameId)))
        elif name == "extrinsicsCalibration":
            calib = event.extrinsicsCalibration
            if len(calib.rpyCalib) == 3 and str(calib.calStatus) == "calibrated":
                calibration_candidates.append((int(event.logMonoTime), list(calib.rpyCalib), list(calib.height)))
        elif name == "modelV2" and model is None:
            model = event.modelV2
            event_time = int(event.logMonoTime)
    if model is None:
        raise RuntimeError("No modelV2 message found")
    if not calibration_candidates:
        raise RuntimeError("No calibrated extrinsicsCalibration found")
    _, rpy_calib, calibration_height = min(calibration_candidates, key=lambda item: abs(item[0] - event_time))

    model_frame_id = int(model.frameId)
    if not camera_candidates:
        raise RuntimeError("No narrowRoadCameraState messages found")
    exact_camera = [item for item in camera_candidates if item[1] == model_frame_id]
    camera_time, camera_frame_id = exact_camera[0] if exact_camera else min(camera_candidates, key=lambda item: abs(item[1] - model_frame_id))
    exact_encode = [item for item in encode_candidates if item[1] == model_frame_id]
    nearest_encode = exact_encode[0] if exact_encode else (min(encode_candidates, key=lambda item: abs(item[1] - model_frame_id)) if encode_candidates else None)
    frame_id = camera_frame_id
    reader = FrameReader(str(video_path), pix_fmt="rgb24", hwaccel="none", loglevel="error")
    if frame_id >= reader.frame_count:
        raise RuntimeError(f"model frameId {frame_id} exceeds video frame count {reader.frame_count}")
    frame = reader.get(frame_id)
    try:
        camera_config = DEVICE_CAMERAS[(device_type, sensor)]
    except KeyError:
        camera_config = DEVICE_CAMERAS[("tici", "ar0231")]
    camera = camera_config.narrow_road
    device_from_calib = rot_from_euler(rpy_calib)
    view_from_calib = view_frame_from_device_frame @ device_from_calib
    camera_from_model = camera.intrinsics @ view_from_calib

    model_json = {
        "frameId": frame_id,
        "modelFrameId": model_frame_id,
        "cameraFrameId": camera_frame_id,
        "cameraFrameLogMonoTime": camera_time,
        "modelFrameLogMonoTime": event_time,
        "frameIdExtra": int(model.frameIdExtra),
        "frameAge": int(model.frameAge),
        "frameDropPerc": float(model.frameDropPerc),
        "laneLineProbs": list(model.laneLineProbs),
        "roadEdgeStds": list(model.roadEdgeStds),
        "position_points": points(model.position),
        "lane_lines": [points(line) for line in model.laneLines],
        "road_edges": [points(edge) for edge in model.roadEdges],
        "confidence": str(model.confidence),
        "desiredCurvature": float(model.action.desiredCurvature),
        "desiredAcceleration": float(model.action.desiredAcceleration),
        "shouldStop": bool(model.action.shouldStop),
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frame).save(OUTPUT / "frame.jpg", quality=90)
    path_height = float(calibration_height[0]) if calibration_height else 1.35
    draw_overlay(frame, model_json, camera_from_model, path_height, OUTPUT / "overlay.jpg")
    (OUTPUT / "model.json").write_text(json.dumps(model_json, indent=2))
    metadata = {
        "route": ROUTE,
        "segment": SEGMENT,
        "source_rlog": str(rlog_path),
        "source_camera": str(video_path),
        "anchor_logMonoTime": int(event_time),
        "anchor_frameId": frame_id,
        "model_frameId": model_frame_id,
        "camera_frameId": camera_frame_id,
        "encode_frameId": nearest_encode[1] if nearest_encode else None,
        "model_camera_time_delta_ns": camera_time - event_time,
        "camera_width": reader.w,
        "camera_height": reader.h,
        "camera_frame_count": reader.frame_count,
        "label": "unclassified",
        "severity": "unknown",
        "note": "First Carlosthon extraction artifact",
        "camera_device_type": device_type,
        "camera_sensor": sensor,
        "rpyCalib": rpy_calib,
        "overlay_note": "Uses openpilot camera intrinsics and calibrated rpyCalib transform.",
    }
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"Created {OUTPUT}")
    print(f"Frame: {frame_id} ({reader.w}x{reader.h})")
    print(f"Overlay: {OUTPUT / 'overlay.jpg'}")
    print(f"Model event time: {event_time}")


if __name__ == "__main__":
    main()
