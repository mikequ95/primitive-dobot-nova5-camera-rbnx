# SPDX-License-Identifier: MulanPSL-2.0
"""Stationary RGB observations for Robonix Pilot and gRPC clients."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

import builtin_interfaces_mcp
import camera_mcp
import camera_pb2
import grpc
import sensor_msgs_mcp
import sensor_msgs_pb2
import std_msgs_mcp
from robonix_api import Err, Ok, Primitive


camera = Primitive(id="nova5_wrist_rgb", namespace="robonix/primitive/camera")
_config = None
_arm_provider_id = "nova5_arm"
_lock = threading.Lock()
_accepting = False
_blocked = False
_process = None
_temporary = None
CAPTURE_TIMEOUT_S = 35


@camera.on_init
def initialize(config):
    global _config, _arm_provider_id
    path = config.get("calibration_config")
    if not isinstance(path, str) or not path:
        return Err("calibration_config must name an absolute calibration JSON file")
    path = Path(path)
    if not path.is_absolute() or not path.is_file():
        return Err("calibration_config must name an existing absolute calibration JSON file")
    provider = config.get("arm_provider_id", "nova5_arm")
    if not isinstance(provider, str) or not provider.strip():
        return Err("arm_provider_id must name a hardware provider instance")
    _config = path.resolve()
    _arm_provider_id = provider
    return Ok()


@camera.on_activate
def activate():
    global _accepting
    with _lock:
        if _config is None or _blocked or _process is not None:
            return Err("Initialize the camera and complete deactivation before activating")
        _accepting = True
    return Ok()


def release_capture():
    global _process, _temporary
    if _process is not None:
        if _process.poll() is None:
            return
        for stream in (_process.stdout, _process.stderr):
            if stream is not None:
                stream.close()
        _process = None
    if _temporary is not None:
        _temporary.cleanup()
        _temporary = None


@camera.on_deactivate
def deactivate():
    global _accepting, _blocked
    _accepting = False
    deadline = time.monotonic() + CAPTURE_TIMEOUT_S
    if not _lock.acquire(timeout=CAPTURE_TIMEOUT_S):
        return Err("RGB capture has not exited; camera ownership is retained")
    try:
        if _process is not None:
            try:
                _process.communicate(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                return Err("RGB capture has not exited; camera ownership is retained")
        release_capture()
        _blocked = False
        return Ok()
    finally:
        _lock.release()


@camera.on_shutdown
def shutdown():
    return deactivate()


def capture():
    global _process, _temporary, _blocked
    if not _lock.acquire(blocking=False):
        raise RuntimeError("RGB capture is already running")
    try:
        if not _accepting or _config is None or _blocked:
            raise RuntimeError("Camera is inactive or requires completed deactivation")
        _temporary = tempfile.TemporaryDirectory(prefix="nova5-rgb-")
        output = Path(_temporary.name)
        env = os.environ.copy()
        env.pop("PYTHONHOME", None)
        _process = subprocess.Popen(
            [sys.executable, "-m", "wrist_rgb.capture_rgb", str(_config), str(output),
             "--arm-provider-id", _arm_provider_id],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=output)
        try:
            stdout, stderr = _process.communicate(timeout=CAPTURE_TIMEOUT_S)
        except subprocess.TimeoutExpired as error:
            # Keep the SDK process and its files owned until it closes the camera.
            _blocked = True
            raise RuntimeError("RGB capture timed out; complete deactivation before retrying") from error
        if _process.returncode:
            raise RuntimeError(f"RGB capture failed: {(stderr or stdout)[-1600:]}")
        return json.loads((output / "capture.json").read_text()), {
            "raw": (output / "rgb.bgr").read_bytes(),
            "jpeg": (output / "rgb.jpg").read_bytes(),
        }
    finally:
        release_capture()
        _lock.release()


@camera.grpc("robonix/primitive/camera/snapshot")
def snapshot(request, context):
    try:
        metadata, pixels = capture()
    except (RuntimeError, subprocess.SubprocessError, OSError, ValueError) as error:
        context.abort(grpc.StatusCode.UNAVAILABLE, str(error))
    image = sensor_msgs_pb2.Image(
        height=metadata["height"], width=metadata["width"], encoding="bgr8",
        step=metadata["width"] * 3, data=pixels["raw"])
    image.header.frame_id = "nova5_wrist_camera_optical"
    image.header.stamp.sec = metadata["stamp_sec"]
    image.header.stamp.nanosec = metadata["stamp_nanosec"]
    return camera_pb2.GetCameraImage_Response(image=image)


@camera.mcp("robonix/primitive/camera/snapshot")
async def snapshot_for_pilot(request: camera_mcp.GetCameraImage_Request) -> sensor_msgs_mcp.Image:
    """Give Pilot one stationary RGB image of the current Nova5 work surface."""
    metadata, pixels = await asyncio.to_thread(capture)
    # MCP carries a compressed frame for the model; gRPC keeps raw bgr8.
    jpeg = pixels["jpeg"]
    return sensor_msgs_mcp.Image(
        header=std_msgs_mcp.Header(
            stamp=builtin_interfaces_mcp.Time(sec=metadata["stamp_sec"],
                                             nanosec=metadata["stamp_nanosec"]),
            frame_id="nova5_wrist_camera_optical"),
        height=metadata["height"], width=metadata["width"], encoding="jpeg",
        step=len(jpeg), data=jpeg)


if __name__ == "__main__":
    camera.run()
