# SPDX-License-Identifier: MulanPSL-2.0
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from handeye import camera as camera_module, cli, workflow

from wrist_rgb import capture_rgb


class CaptureMetadataTest(unittest.TestCase):
    def capture(self, output, snapshot):
        client = MagicMock()
        client.__enter__.return_value.status.return_value = {"capture_idle": True}
        client_type = MagicMock(return_value=client)
        module = types.ModuleType("nova5_hardware.client")
        module.HardwareClient = client_type
        camera = MagicMock()
        with patch.dict(sys.modules, {"nova5_hardware.client": module}), \
                patch.object(camera_module, "Camera", return_value=camera), \
                patch.object(cli, "_robot", side_effect=AssertionError("Direct hardware access")), \
                patch.object(cli, "_stationary_snapshot", side_effect=snapshot), \
                patch.object(workflow, "load_config", return_value={"camera": {}}), \
                patch.object(workflow, "load_intrinsics"), \
                patch.object(workflow, "load_handeye"), \
                patch.object(workflow, "load_plane"), \
                patch.object(workflow, "check_camera_identity"), \
                patch.object(sys, "argv", ["capture_rgb", "/calibration/config.json", str(output),
                                           "--arm-provider-id", "test_arm"]):
            try:
                capture_rgb.main()
            finally:
                camera.__exit__.assert_called_once()
                client.__exit__.assert_called_once()
        client_type.assert_called_once_with(provider_id="test_arm", consumer_id="nova5_wrist_rgb")

    def test_receipt_time_is_not_published_as_acquisition_time(self):
        frame = np.zeros((2, 3, 3), dtype=np.uint8)

        def snapshot(camera, robot, *, deadline):
            self.assertGreater(deadline, 0)
            return frame, {"host_frame_received_at": 1234.5}

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.capture(output, snapshot)
            metadata = json.loads((output / "capture.json").read_text())
            self.assertEqual((metadata["stamp_sec"], metadata["stamp_nanosec"]), (0, 0))
            self.assertEqual(metadata["host_frame_received_at"], 1234.5)
            self.assertEqual((metadata["width"], metadata["height"]), (3, 2))
            self.assertEqual((output / "rgb.bgr").read_bytes(), frame.tobytes())

    def test_deadline_closes_camera_and_client_without_publishing_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(TimeoutError, "deadline"):
                self.capture(output, TimeoutError("capture deadline"))
            self.assertFalse((output / "capture.json").exists())


if __name__ == "__main__":
    unittest.main()
