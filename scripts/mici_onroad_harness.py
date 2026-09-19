#!/usr/bin/env python3
"""Visible 600-second Mici on-road UI harness for Carlosthon REPORT testing."""
from __future__ import annotations

import time

import pyray as rl
from openpilot.cereal import log, messaging
from openpilot.common.prefix import OpenpilotPrefix
from openpilot.selfdrive.ui.tests.diff.replay import setup_state
from openpilot.selfdrive.ui.tests.diff.replay_script import setup_calibration_params, setup_developer_params

DURATION_SECONDS = 600
FPS = 60


def main() -> None:
    setup_state()
    setup_calibration_params()
    setup_developer_params()

    from openpilot.selfdrive.ui.ui_state import device, ui_state
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.selfdrive.ui.mici.layouts.main import MiciMainLayout

    gui_app.init_window("Carlosthon · Mici On-road REPORT", fps=FPS)
    MiciMainLayout()
    device.set_override_interactive_timeout(99999)

    pm = messaging.PubMaster(["deviceState", "pandaStates", "driverStateV2", "selfdriveState", "carState"])
    started_at = time.monotonic()
    print("Mici on-road harness started")
    print("The on-road camera page should appear after the startup transition.")
    print("REPORT button is in the upper-right of the on-road view.")
    print("Press Ctrl+C in this terminal to stop early.")

    try:
        for _ in gui_app.render():
            device_state = messaging.new_message("deviceState")
            device_state.deviceState.started = True
            device_state.deviceState.networkType = log.DeviceState.NetworkType.wifi
            pm.send("deviceState", device_state)

            panda = messaging.new_message("pandaStates", 1)
            panda.pandaStates[0].pandaType = log.PandaState.PandaType.dos
            panda.pandaStates[0].ignitionLine = True
            pm.send("pandaStates", panda)

            selfdrive = messaging.new_message("selfdriveState")
            selfdrive.selfdriveState.enabled = False
            pm.send("selfdriveState", selfdrive)

            ui_state.update()
            if time.monotonic() - started_at >= DURATION_SECONDS:
                break
    finally:
        gui_app.close()
        print("Mici on-road harness finished")


if __name__ == "__main__":
    with OpenpilotPrefix():
        main()
