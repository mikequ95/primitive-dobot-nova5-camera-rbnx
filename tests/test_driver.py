# SPDX-License-Identifier: MulanPSL-2.0
import asyncio
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from wrist_rgb import driver as camera
from robonix_api import Err, Ok


class CameraLoopTest(unittest.IsolatedAsyncioTestCase):
    async def test_capture_does_not_block_mcp_event_loop(self):
        started, release = threading.Event(), threading.Event()

        def capture():
            started.set()
            if not release.wait(timeout=2):
                raise TimeoutError("MCP event loop did not resume during capture")
            return {"height": 1, "width": 1, "stamp_sec": 1, "stamp_nanosec": 0}, {"jpeg": b"test"}

        with patch.object(camera, "capture", capture):
            task = asyncio.create_task(camera.snapshot_for_pilot(None))
            try:
                for _ in range(100):
                    if started.is_set():
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(started.is_set())
                self.assertFalse(task.done())
            finally:
                release.set()
            image = await asyncio.wait_for(task, timeout=2)
            self.assertEqual(image.data, b"test")


class CaptureInstallationTest(unittest.TestCase):
    def test_capture_entrypoint_is_installed_outside_checkout(self):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-m", "wrist_rgb.capture_rgb", "--help"],
                cwd=directory, env=env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("calibration_config", result.stdout)


class CaptureLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config = Path(self.directory.name) / "config.json"
        self.config.write_text("{}")
        self.assertIsInstance(camera.initialize({"calibration_config": str(self.config),
                                                "arm_provider_id": "test_arm"}), Ok)
        self.assertIsInstance(camera.activate(), Ok)

    def tearDown(self):
        if camera._process is not None:
            camera._process.poll.return_value = 0
            camera._process.communicate.side_effect = None
            camera._process.communicate.return_value = ("", "")
        camera.deactivate()
        self.directory.cleanup()

    @staticmethod
    def process(returncode):
        process = Mock(returncode=returncode, stdout=io.StringIO(), stderr=io.StringIO())
        process.poll.return_value = returncode
        process.communicate.return_value = ("", "")
        return process

    def test_capture_passes_provider_and_atlas_and_releases_files(self):
        process = self.process(0)

        def launch(command, **kwargs):
            self.assertEqual(command[-2:], ["--arm-provider-id", "test_arm"])
            self.assertEqual(kwargs["env"]["ROBONIX_ATLAS"], "127.0.0.1:50151")
            self.assertEqual(kwargs["env"]["PYTHONPATH"], "/generated/client/interfaces")
            output = Path(kwargs["cwd"])
            (output / "capture.json").write_text(json.dumps({"width": 1, "height": 1,
                                                            "stamp_sec": 0, "stamp_nanosec": 0}))
            (output / "rgb.bgr").write_bytes(b"\x00\x00\x00")
            (output / "rgb.jpg").write_bytes(b"jpeg")
            return process

        with patch.dict(os.environ, {"ROBONIX_ATLAS": "127.0.0.1:50151",
                                     "PYTHONPATH": "/generated/client/interfaces"}), \
                patch.object(camera.subprocess, "Popen", side_effect=launch):
            metadata, pixels = camera.capture()
        self.assertEqual(metadata["stamp_sec"], 0)
        self.assertEqual(pixels["jpeg"], b"jpeg")
        self.assertIsNone(camera._process)
        self.assertIsNone(camera._temporary)

    def test_timeout_retains_owner_until_bounded_deactivation_succeeds(self):
        process = self.process(None)
        process.communicate.side_effect = subprocess.TimeoutExpired("capture", .01)
        with patch.object(camera, "CAPTURE_TIMEOUT_S", .01), \
                patch.object(camera.subprocess, "Popen", return_value=process) as launch:
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                camera.capture()
            output = Path(camera._temporary.name)
            self.assertTrue(output.is_dir())
            with self.assertRaisesRegex(RuntimeError, "deactivation"):
                camera.capture()
            launch.assert_called_once()
            self.assertIsInstance(camera.deactivate(), Err)
            self.assertIs(camera._process, process)
            self.assertTrue(output.is_dir())
            process.kill.assert_not_called()
            process.terminate.assert_not_called()
            process.poll.return_value = 0
            process.communicate.side_effect = None
            process.communicate.return_value = ("", "")
            self.assertIsInstance(camera.deactivate(), Ok)
            self.assertFalse(output.exists())
            self.assertIsNone(camera._process)
            with self.assertRaisesRegex(RuntimeError, "inactive"):
                camera.capture()

    def test_deactivation_rejects_new_capture_while_waiting_for_owner(self):
        camera._lock.acquire()
        try:
            with patch.object(camera, "CAPTURE_TIMEOUT_S", .01):
                self.assertIsInstance(camera.deactivate(), Err)
        finally:
            camera._lock.release()
        with self.assertRaisesRegex(RuntimeError, "inactive"):
            camera.capture()


if __name__ == "__main__":
    unittest.main()
