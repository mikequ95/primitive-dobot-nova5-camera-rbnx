# SPDX-License-Identifier: MulanPSL-2.0
"""Acquire RGB paired with stationary Nova5 feedback; never submit motion."""
import argparse
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("calibration_config", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--arm-provider-id", default="nova5_arm")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    from handeye.camera import Camera
    from handeye.cli import _stationary_snapshot, _save_image
    from handeye.workflow import (load_config, load_intrinsics, load_handeye,
                                  load_plane, check_camera_identity, save_json)
    from nova5_hardware.client import HardwareClient

    config = load_config(args.calibration_config)
    intrinsic = load_intrinsics(config)
    load_handeye(config)
    load_plane(config)
    deadline = time.monotonic() + 30
    with HardwareClient(provider_id=args.arm_provider_id,
                        consumer_id="nova5_wrist_rgb") as robot, Camera(config["camera"]) as camera:
        check_camera_identity(camera, intrinsic)
        frame, sample = _stationary_snapshot(camera, robot, deadline=deadline)
        _save_image(output / "rgb.png", frame)
        import cv2
        if not cv2.imwrite(str(output / "rgb.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 90]):
            raise RuntimeError("Failed to encode Nova5 RGB JPEG")
        (output / "rgb.bgr").write_bytes(frame.tobytes())
        metadata = {"sample": sample, "status": robot.status(), "motion_sent": False,
                    "width": frame.shape[1], "height": frame.shape[0],
                    "host_frame_received_at": sample["host_frame_received_at"],
                    "stamp_sec": 0, "stamp_nanosec": 0}
        save_json(output / "capture.json", metadata)
        print(json.dumps({"image": str(output / "rgb.png"), "motion_sent": False}))


if __name__ == "__main__":
    main()
