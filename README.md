# Carlosthon

Carlosthon is an experimental developer-facing openpilot route and incident review tool.

## First vertical slice

The first script reads one local `rlog.zst`, selects a `modelV2` message, decodes the matching `fcamera.hevc` frame, and writes a portable incident artifact:

```text
outputs/sample-incident/
├── metadata.json
├── model.json
└── frame.jpg
```

## Run from WSL

```bash
cd /mnt/d/comma_ai/carlosthon
source /mnt/d/comma_ai/openpilot/.venv/bin/activate
source /mnt/d/comma_ai/openpilot/launch_env.sh

python scripts/extract_sample.py
```

No internet, authentication, Chestnut, or openpilot source modification is required.

## Generate the overlay artifact

```bash
cd /mnt/d/comma_ai/carlosthon
source /mnt/d/comma_ai/openpilot/.venv/bin/activate
source /mnt/d/comma_ai/openpilot/launch_env.sh
python scripts/extract_sample.py
```

This additionally creates:

```text
outputs/sample-incident/overlay.jpg
```

The overlay now uses openpilot's camera intrinsics and calibrated `rpyCalib` transform from `selfdrive/ui/onroad/augmented_road_view.py`. Exact UI zoom/cropping can be refined later.

## Easiest way to run

From PowerShell or Windows Explorer, run:

```text
D:\comma_ai\carlosthon\run_carlosthon.bat
```

It regenerates the calibrated overlay and starts the local viewer. Then open:

```text
http://localhost:8000
```

If you prefer WSL manually:

```bash
cd /mnt/d/comma_ai/carlosthon
source /mnt/d/comma_ai/openpilot/.venv/bin/activate
source /mnt/d/comma_ai/openpilot/launch_env.sh
python scripts/extract_sample.py
python scripts/viewer.py
```

Open this in the Windows browser:

```text
http://localhost:8000
```

The viewer shows a synchronized six-frame sequence, model metrics, a legend, a local REPORT form, and saved incidents. REPORT writes a local `outputs/incidents/incident-NNN/` package containing metadata, frame, overlay, and model JSON.
