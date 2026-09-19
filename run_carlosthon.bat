@echo off
wsl -d Ubuntu-24.04 -e bash -lc "cd /mnt/d/comma_ai/carlosthon && source /mnt/d/comma_ai/openpilot/.venv/bin/activate && source /mnt/d/comma_ai/openpilot/launch_env.sh && python scripts/extract_sample.py && python scripts/viewer.py"
